#!/usr/bin/env python3
"""Deterministic routing/launcher checks; no worker inference is performed."""

from __future__ import annotations

import json
import copy
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
import argparse
import tempfile


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "worker-catalog.json"
LAUNCHER = ROOT / "bin" / "hermes-worker.py"
WORKDIR = ROOT / "synthetic_demo"


class HermesRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        cls.routes = cls.catalog["routes"]
        # Hermetic twin: identical gates with workdir roots relocated to this
        # checkout, so spawn-path tests pass on any machine (CI runners have
        # no D:/Hermes). Config-assertion tests keep using the real catalog.
        cls.test_catalog = copy.deepcopy(cls.catalog)
        cls.test_catalog["policy"]["allowed_workdir_roots"] = [str(ROOT)]
        for route in cls.test_catalog["routes"].values():
            if isinstance(route, dict) and route.get("allowed_workdir"):
                route["allowed_workdir"] = str(WORKDIR)
        # Directory policies resolve relative to the catalog file; pin them to
        # absolute repo paths so the temp catalog stays inside HERMES_ROOT
        # scope (dry-runs never write, this only satisfies validation).
        cls.test_catalog["policy"]["attempt_ledger"] = str(ROOT / "logs" / "worker_attempts")
        cls.test_catalog["policy"]["worktree_locks"] = str(ROOT / "logs" / "worker_worktrees")
        cls.test_catalog["policy"]["usage_log"] = str(ROOT / "logs" / "worker_usage.jsonl")
        cls.test_routes = cls.test_catalog["routes"]
        cls._catalog_tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._catalog_tmp.cleanup)
        cls.test_catalog_path = Path(cls._catalog_tmp.name) / "worker-catalog.test.json"
        cls.test_catalog_path.write_text(json.dumps(cls.test_catalog), encoding="utf-8")
        spec = importlib.util.spec_from_file_location("hermes_worker", LAUNCHER)
        assert spec and spec.loader
        cls.launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.launcher)

    def dry_run(self, route_id: str, *extra: str) -> dict:
        result = subprocess.run(
            [
                sys.executable,
                str(LAUNCHER),
                "--route",
                route_id,
                "--task",
                "synthetic routing validation only; do not execute",
                "--workdir",
                str(WORKDIR),
                "--catalog",
                str(self.test_catalog_path),
                "--dry-run",
                *extra,
            ],
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def test_catalog_has_one_allowlisted_route_per_id(self) -> None:
        self.assertTrue(self.catalog["policy"]["allowlisted_routes_only"])
        self.assertFalse(self.catalog["policy"]["provider_failover"])
        self.assertFalse(self.catalog["policy"]["pty"])
        self.assertEqual(len(self.routes), len(set(self.routes)))
        self.assertTrue(all(route["available"] for route in self.routes.values()))

    def test_every_route_resolves_without_spawning_a_worker(self) -> None:
        for route_id in self.routes:
            with self.subTest(route=route_id):
                dry_run = self.dry_run(route_id)
                self.assertEqual(dry_run["route"], route_id)
                self.assertFalse(dry_run["pty"])
                self.assertEqual(dry_run["stdin"], "closed")
                self.assertFalse(dry_run["provider_failover"])
                self.assertNotIn("danger-full-access", json.dumps(dry_run))

    def test_expected_adapter_flags(self) -> None:
        codex = self.dry_run("codex-normal")
        self.assertIn("--json", codex["argv"])
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", codex["argv"])
        self.assertTrue(codex["full_access"])
        self.assertIn("cli_auth_credentials_store=file", codex["argv"])
        self.assertIn("model_reasoning_effort=max", codex["argv"])
        self.assertEqual(codex["codex_home"], str(self.launcher.CODEX_WORKER_HOME))
        self.assertEqual(codex["auth_store"], "file")
        self.assertEqual(codex["identity_preflight"], "required_before_spawn")

        agy = self.dry_run("antigravity-review")
        self.assertNotIn("--effort", agy["argv"])
        self.assertEqual(agy["reasoning_requested"], "model-integrated/default, effort chưa xác nhận")
        self.assertEqual(agy["reasoning_actual"], "model-integrated/default, effort chưa xác nhận")
        self.assertEqual(agy["reasoning_mode"], "model-integrated/default")
        self.assertFalse(agy["effort_confirmed"])
        self.assertIn("--output-format", agy["argv"])
        self.assertIn("json", agy["argv"])
        self.assertIn("--dangerously-skip-permissions", agy["argv"])
        self.assertEqual(agy["argv"][agy["argv"].index("--print-timeout") + 1], "600s")

        zen = self.dry_run("opencode-zen-contributor")
        self.assertTrue(zen["argv"][0].endswith("opencode.exe"))
        self.assertEqual(zen["opencode_permission"], "allow")
        self.assertIn("opencode/muse-spark-1.3-contributor-free", zen["argv"])
        self.assertIn("xhigh", zen["argv"])

        bedrock = self.dry_run("opencode-bedrock")
        self.assertIn("amazon-bedrock/anthropic.claude-opus-4-6-v1", bedrock["argv"])
        self.assertIn("max", bedrock["argv"])

        bedrock_high = self.dry_run("opencode-bedrock", "--reasoning-override", "high")
        self.assertEqual(bedrock_high["reasoning_requested"], "max")
        self.assertEqual(bedrock_high["reasoning_actual"], "high")
        self.assertEqual(bedrock_high["invocation_corrections"], 1)

    def test_timeout_policy_requires_explicit_per_task_approval(self) -> None:
        policy = self.catalog["policy"]
        standard = argparse.Namespace(timeout=600, timeout_approval=None)
        timeout, metadata = self.launcher.resolve_timeout(standard, policy)
        self.assertEqual(timeout, 600)
        self.assertEqual(metadata["kind"], "standard")
        self.assertIsNone(metadata["approval_fingerprint"])

        default_timeout, default_metadata = self.launcher.resolve_timeout(
            argparse.Namespace(timeout=None, timeout_approval=None), policy
        )
        self.assertEqual(default_timeout, 600)
        self.assertEqual(default_metadata["kind"], "standard")

        with self.assertRaises(self.launcher.LauncherError) as missing:
            self.launcher.resolve_timeout(
                argparse.Namespace(timeout=1200, timeout_approval=None), policy
            )
        self.assertEqual(missing.exception.code, "timeout_override_requires_approval")

        approved_timeout, approved = self.launcher.resolve_timeout(
            argparse.Namespace(timeout=1200, timeout_approval="supervisor-approved checkpoint-2"),
            policy,
        )
        self.assertEqual(approved_timeout, 1200)
        self.assertEqual(approved["kind"], "approved_per_task_override")
        self.assertEqual(len(approved["approval_fingerprint"]), 64)
        self.assertNotIn("supervisor", json.dumps(approved))

        with self.assertRaises(self.launcher.LauncherError) as too_large:
            self.launcher.resolve_timeout(
                argparse.Namespace(timeout=1801, timeout_approval="approved"), policy
            )
        self.assertEqual(too_large.exception.code, "timeout_override_exceeds_maximum")

    def test_timeout_progress_snapshot_identifies_in_flight_command(self) -> None:
        stream = "\n".join(
            [
                json.dumps({"type": "item.started", "item": {"id": "cmd-1", "type": "command_execution"}}),
                json.dumps({"type": "item.completed", "item": {"id": "cmd-0", "type": "file_change"}}),
            ]
        )
        snapshot = self.launcher.progress_snapshot("codex", stream)
        self.assertEqual(snapshot["records_seen"], 2)
        self.assertEqual(snapshot["in_flight_item_types"], ["command_execution"])
        self.assertEqual(snapshot["last_event"], {"event_type": "item.completed", "item_type": "file_change"})
        self.assertNotIn('"command":', json.dumps(snapshot))

    def test_contributor_accepts_exact_child_not_sibling(self):
        args = argparse.Namespace(workdir=str(WORKDIR / "csv_counter_20260919T2345_plus0700"))
        actual = self.launcher.validate_workdir(args, self.test_catalog, self.test_routes["opencode-zen-contributor"])
        self.assertEqual(actual, Path(args.workdir).resolve())
        args.workdir = str(ROOT / "logs")
        with self.assertRaises(self.launcher.LauncherError):
            self.launcher.validate_workdir(args, self.test_catalog, self.test_routes["opencode-zen-contributor"])

    def test_cost_sum_dedup_and_ignore_nonterminal_payload(self):
        def step(key, cost):
            return {"type": "step_finish", "sessionID": "s", "part": {
                "id": key, "cost": cost, "tokens": {"input": 3, "output": 2}}}
        records = [step("a", 0.1), step("b", 0.2), step("a", 0.1),
                   {"type": "tool", "usage": {"input": 999}, "cost": 999}]
        result = self.launcher.parse_usage("opencode", "\n".join(map(json.dumps, records)))
        self.assertAlmostEqual(result["provider_cost"], 0.3)
        self.assertEqual(result["input"], 6)
        self.assertIsNone(result["cached_input"])
        self.assertIn("adapter_raw", result["semantics"]["input"])

    def test_unknown_adapter_does_not_guess_usage(self):
        result = self.launcher.parse_usage("antigravity-cli", '{"usage":{"input":9}}')
        self.assertIsNone(result["input"])

    def test_agy_permission_denial_is_not_success(self):
        record = {"conversation_id": "s", "status": "SUCCESS", "response": "",
                  "denied_actions": [{"action": "read_file"}],
                  "usage": {"input_tokens": 16217, "output_tokens": 384, "thinking_tokens": 298}}
        self.assertFalse(self.launcher.agy_response_usable(json.dumps(record)))
        parsed = self.launcher.parse_usage("antigravity-cli", json.dumps(record))
        self.assertEqual(parsed["input"], 16217)
        self.assertEqual(parsed["reasoning"], 298)
        self.assertEqual(parsed["worker_session_id"], "s")
        record.update(response="Heading", denied_actions=[])
        self.assertTrue(self.launcher.agy_response_usable(json.dumps(record)))

    def test_unicode_console_configuration_exists(self):
        # Execute actual main/dry-run under the encoding that broke the live run.
        import os
        env = dict(os.environ, PYTHONIOENCODING="cp1258")
        result = subprocess.run([sys.executable, str(LAUNCHER), "--route", "codex-normal",
            "--workdir", str(WORKDIR), "--catalog", str(self.test_catalog_path),
            "--task", "Kiểm tra", "--dry-run"],
            env=env, capture_output=True)
        self.assertEqual(result.returncode, 0)
        json.loads(result.stdout.decode("utf-8"))

    def test_codex_child_environment_isolated_from_parent_auth(self) -> None:
        child = self.launcher.build_child_env(
            {"tool": "codex"},
            full_access=True,
            base_env={
                "CODEX_HOME": "C:/shared",
                "CODEX_ACCESS_TOKEN": "fake-access",
                "CODEX_API_KEY": "fake-key",
                "OPENAI_API_KEY": "fake-api-key",
                "OPENAI_BASE_URL": "https://example.invalid",
                "OPENAI_ORG_ID": "fake-org",
                "OPENAI_PROJECT_ID": "fake-project",
            },
        )
        self.assertEqual(child["CODEX_HOME"], str(self.launcher.CODEX_WORKER_HOME))
        self.assertNotIn("CODEX_ACCESS_TOKEN", child)
        self.assertNotIn("CODEX_API_KEY", child)
        self.assertNotIn("OPENAI_API_KEY", child)
        self.assertNotIn("OPENAI_BASE_URL", child)
        self.assertNotIn("OPENAI_ORG_ID", child)
        self.assertNotIn("OPENAI_PROJECT_ID", child)

    def test_identity_metadata_is_masked_and_requires_distinct_fingerprints(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            brain_path = root / "brain-auth.json"
            worker_path = root / "worker-auth.json"
            brain_path.write_text(json.dumps({
                "providers": {"openai-codex": {"tokens": {
                    "account_id": "account-A",
                    "access_token": "fake-a",
                    "refresh_token": "fake-a-refresh",
                    "chatgpt_plan_type": "plus",
                }}},
            }), encoding="utf-8")
            worker_path.write_text(json.dumps({
                "tokens": {
                    "account_id": "account-B",
                    "access_token": "fake-b",
                    "refresh_token": "fake-b-refresh",
                    "chatgpt_plan_type": "plus",
                },
            }), encoding="utf-8")
            brain = self.launcher.read_auth_identity(
                brain_path, role="hermes-brain", auth_source="test-brain"
            )
            worker = self.launcher.read_auth_identity(
                worker_path, role="codex-worker", auth_source="test-worker"
            )
            check = self.launcher.require_codex_identity({
                "status": "unknown", "brain": brain, "worker": worker,
            })

        self.assertEqual(check["status"], "verified_distinct")
        self.assertEqual(check["brain"]["subscription"], "plus")
        self.assertEqual(check["worker"]["subscription"], "plus")
        self.assertNotEqual(check["brain"]["fingerprint"], check["worker"]["fingerprint"])
        self.assertNotIn("account_id", json.dumps(check))
        self.assertNotIn("fake-a", json.dumps(check))
        self.assertNotIn("fake-b", json.dumps(check))

    def test_identity_check_fails_closed_for_same_or_unknown_metadata(self) -> None:
        same = {
            "status": "unknown",
            "brain": {"status": "verified", "fingerprint": "same"},
            "worker": {"status": "verified", "fingerprint": "same"},
        }
        with self.assertRaises(self.launcher.LauncherError) as same_error:
            self.launcher.require_codex_identity(same)
        self.assertEqual(same_error.exception.code, "worker_identity_matches_brain")

        unknown = {
            "status": "unknown",
            "brain": {"status": "verified", "fingerprint": "brain"},
            "worker": {"status": "unknown", "fingerprint": None},
        }
        with self.assertRaises(self.launcher.LauncherError) as unknown_error:
            self.launcher.require_codex_identity(unknown)
        self.assertEqual(unknown_error.exception.code, "worker_identity_unknown")

    def test_usage_fields_keep_cached_and_reasoning_separate(self) -> None:
        codex = self.launcher.parse_usage(
            "codex",
            json.dumps(
                {
                    "type": "thread.started",
                    "thread_id": "worker-codex-1",
                }
            )
            + "\n"
            + json.dumps(
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 100,
                        "cached_input_tokens": 25,
                        "output_tokens": 40,
                        "reasoning_output_tokens": 15,
                    },
                }
            ),
        )
        self.assertEqual(codex["worker_session_id"], "worker-codex-1")
        self.assertEqual(codex["input"], 100)
        self.assertEqual(codex["cached_input"], 25)
        self.assertEqual(codex["output"], 40)
        self.assertEqual(codex["reasoning"], 15)

        opencode = self.launcher.parse_usage(
            "opencode",
            json.dumps(
                {
                    "type": "step_finish",
                    "sessionID": "worker-opencode-1",
                    "part": {
                        "type": "step-finish",
                        "tokens": {
                            "input": 200,
                            "output": 50,
                            "reasoning": 30,
                            "cache": {"read": 60, "write": 5},
                        },
                    },
                }
            ),
        )
        self.assertEqual(opencode["worker_session_id"], "worker-opencode-1")
        self.assertEqual(opencode["input"], 200)
        self.assertEqual(opencode["cached_input"], 60)
        self.assertEqual(opencode["cache_write_input"], 5)
        self.assertEqual(opencode["output"], 50)
        self.assertEqual(opencode["reasoning"], 30)

    def test_model_effort_allowlist_enforced(self) -> None:
        launcher = self.launcher
        allowlist = launcher.load_model_effort_allowlist(self.catalog)
        # Allowed pairs pass.
        launcher.validate_model_effort("gpt-5.6-luna", "max", allowlist)
        launcher.validate_model_effort("gpt-5.6-sol", "high", allowlist)
        launcher.validate_model_effort("gpt-5.6-sol", "xhigh", allowlist)
        launcher.validate_model_effort("gpt-5.6-terra", "high", allowlist)
        launcher.validate_model_effort("gpt-6-astra", "low", allowlist)
        launcher.validate_model_effort("gemini-3.8-flash-high", "high", allowlist)
        launcher.validate_model_effort("gemini-3.1-pro-high", "high", allowlist)
        with self.assertRaises(launcher.LauncherError):
            launcher.validate_model_effort("claude-opus-4-6-thinking", "high", allowlist)
        launcher.validate_model_effort("opencode/muse-spark-1.3-contributor-free", "xhigh", allowlist)
        launcher.validate_model_effort("amazon-bedrock/anthropic.claude-opus-4-6-v1", "max", allowlist)
        launcher.validate_model_effort("amazon-bedrock/anthropic.claude-opus-4-6-v1", "high", allowlist)
        # Forbidden pairs fail closed (never silently remapped).
        with self.assertRaises(launcher.LauncherError):
            launcher.validate_model_effort("gpt-5.6-sol", "max", allowlist)
        with self.assertRaises(launcher.LauncherError):
            launcher.validate_model_effort("gpt-5.6-sol", "ultra", allowlist)
        with self.assertRaises(launcher.LauncherError):
            launcher.validate_model_effort("gpt-5.6-terra", "max", allowlist)
        with self.assertRaises(launcher.LauncherError):
            launcher.validate_model_effort("gpt-6-astra", "high", allowlist)
        with self.assertRaises(launcher.LauncherError):
            launcher.validate_model_effort("gemini-3.8-flash-high", "medium", allowlist)
        with self.assertRaises(launcher.LauncherError):
            launcher.validate_model_effort("opencode/muse-spark-1.3-contributor-free", "high", allowlist)
        with self.assertRaises(launcher.LauncherError):
            launcher.validate_model_effort("invented-model-9", "high", allowlist)

    def test_allowlist_single_source_missing_table_fails_closed(self) -> None:
        import copy
        catalog = copy.deepcopy(self.catalog)
        del catalog["policy"]["model_effort_allowlist"]
        with self.assertRaises(self.launcher.LauncherError):
            self.launcher.load_model_effort_allowlist(catalog)

    def test_attempt_budgets_come_from_catalog(self) -> None:
        budgets = self.launcher.load_attempt_budgets(self.catalog)
        self.assertEqual(budgets["max_same_route_retries"], 1)
        self.assertEqual(budgets["max_fallback_routes"], 1)
        self.assertEqual(budgets["max_attempts_per_task"], 3)

    def test_every_catalog_route_passes_allowlist(self) -> None:
        allowlist = self.launcher.load_model_effort_allowlist(self.catalog)
        for route_id, route in self.routes.items():
            with self.subTest(route=route_id):
                if route.get("reasoning_mode") != "model-integrated/default":
                    self.launcher.validate_model_effort(
                        str(route.get("model_id") or ""),
                        str(route.get("reasoning_requested") or ""),
                        allowlist,
                    )
                fallback = str(route.get("adapter_fallback_reasoning") or "").strip()
                if fallback:
                    self.launcher.validate_model_effort(str(route.get("model_id") or ""), fallback, allowlist)

    def test_failure_classification_never_retries_task_failures(self) -> None:
        classify = self.launcher.classify_worker_failure
        self.assertEqual(
            classify(exit_code=None, status="timeout", error="worker timeout"), "timeout_verify"
        )
        self.assertEqual(
            classify(exit_code=0, status="blocked", error="denied"), "task_failure_no_retry"
        )
        self.assertEqual(
            classify(exit_code=1, status="failed", error="tests failed: 2 failing"),
            "task_failure_no_retry",
        )
        self.assertEqual(
            classify(exit_code=1, status="failed", error="review found bug in diff"),
            "task_failure_no_retry",
        )
        self.assertEqual(
            classify(exit_code=1, status="failed", error="upstream 429 rate limit"),
            "provider_retryable",
        )
        self.assertEqual(
            classify(
                exit_code=1,
                status="blocked",
                error='invalid model selection (--model "claude-opus-4-6-thinking" --effort "high"): '
                      '--effort is not supported for model "claude-opus-4-6-thinking"',
            ),
            "configuration_failure_no_retry",
        )
        quota = {
            "status": 429,
            "error": {
                "type": "usage_limit_reached",
                "message": "account quota exhausted",
                "resets_at": "2026-09-20T18:00:00Z",
            },
        }
        signal = self.launcher.usage_limit_signal(json.dumps(quota))
        self.assertEqual(signal["status"], "exhausted_checkpoint")
        self.assertEqual(signal["reset_at"], "2026-09-20T18:00:00Z")
        self.assertEqual(
            classify(exit_code=1, status="failed", error=quota),
            "quota_exhausted_checkpoint",
        )
        self.assertIsNone(
            self.launcher.usage_limit_signal(
                json.dumps({"status": 429, "error": {"type": "rate_limit", "message": "try again"}})
            )
        )
        self.assertEqual(
            classify(
                exit_code=1,
                status="failed",
                error={"status": 429, "error": {"type": "rate_limit", "message": "try again"}},
            ),
            "provider_retryable",
        )

    def test_attempt_budget_enforcement(self) -> None:
        import argparse
        launcher = self.launcher
        budgets = launcher.load_attempt_budgets(self.catalog)

        def ns(**kwargs):
            base = dict(attempt_kind="initial", fallback_from=None, reconciled=False)
            base.update(kwargs)
            return argparse.Namespace(**base)

        def ledger_of(*entries):
            return {"schema": "hermes-worker-attempts/v1", "attempts": list(entries)}

        def spawned_entry(route, kind="initial", status="failed", cls="provider_retryable", **extra):
            entry = {"route": route, "kind": kind, "spawned": True, "status": status,
                     "failure_class": cls, "exit_code": 1, "error": "upstream 429 rate limit"}
            entry.update(extra)
            return entry

        # Fresh task: initial allowed, retry/fallback kinds refused without priors.
        self.assertEqual(
            launcher.enforce_attempt_budget(ns(), "codex-normal", "t1", self.catalog, budgets, ledger_of()), 1
        )
        with self.assertRaises(launcher.LauncherError):
            launcher.enforce_attempt_budget(ns(attempt_kind="retry"), "codex-normal", "t1", self.catalog, budgets, ledger_of())
        with self.assertRaises(launcher.LauncherError):
            launcher.enforce_attempt_budget(
                ns(attempt_kind="fallback", fallback_from="codex-normal"), "antigravity-normal",
                "t1", self.catalog, budgets, ledger_of())

        # Same-route retry after a provider error: allowed once, then exhausted.
        one = ledger_of(spawned_entry("codex-normal"))
        self.assertEqual(
            launcher.enforce_attempt_budget(ns(attempt_kind="retry"), "codex-normal", "t1", self.catalog, budgets, one), 2
        )
        two = ledger_of(spawned_entry("codex-normal"), spawned_entry("codex-normal", kind="retry"))
        with self.assertRaises(launcher.LauncherError):
            launcher.enforce_attempt_budget(ns(attempt_kind="retry"), "codex-normal", "t1", self.catalog, budgets, two)

        # Task failure never authorizes a retry; timeout needs --reconciled.
        task_fail = ledger_of(spawned_entry("codex-normal", cls="task_failure_no_retry", error="tests failed"))
        with self.assertRaises(launcher.LauncherError):
            launcher.enforce_attempt_budget(ns(attempt_kind="retry"), "codex-normal", "t1", self.catalog, budgets, task_fail)
        quota_fail = ledger_of(
            spawned_entry(
                "codex-normal",
                cls="quota_exhausted_checkpoint",
                error="usage_limit_reached; resets_at=2026-09-20T18:00:00Z",
                quota_bucket="openai-codex-account",
            )
        )
        with self.assertRaises(launcher.LauncherError) as quota_error:
            launcher.enforce_attempt_budget(
                ns(attempt_kind="fallback", fallback_from="codex-normal"),
                "codex-review", "t1", self.catalog, budgets, quota_fail,
            )
        self.assertEqual(quota_error.exception.code, "no_fallback_for_exhausted_quota_bucket")
        legacy_opus = ledger_of(
            spawned_entry(
                "antigravity-review",
                status="blocked",
                cls="task_failure_no_retry",
                error="worker exited non-zero; no provider failover was attempted",
                reasoning="high",
            )
        )
        self.assertEqual(
            launcher.enforce_attempt_budget(
                ns(attempt_kind="retry"), "antigravity-review", "t1", self.catalog, budgets, legacy_opus,
            ),
            2,
        )
        timed_out = ledger_of(spawned_entry("codex-normal", status="timeout", cls="timeout_verify", error="worker timeout"))
        with self.assertRaises(launcher.LauncherError):
            launcher.enforce_attempt_budget(ns(attempt_kind="retry"), "codex-normal", "t1", self.catalog, budgets, timed_out)
        self.assertEqual(
            launcher.enforce_attempt_budget(
                ns(attempt_kind="retry", reconciled=True), "codex-normal", "t1", self.catalog, budgets, timed_out), 2
        )

        # Fallback needs a prior spawned route, counts once; total task cap is 3.
        self.assertEqual(
            launcher.enforce_attempt_budget(
                ns(attempt_kind="fallback", fallback_from="codex-normal"), "antigravity-normal",
                "t1", self.catalog, budgets, one), 2
        )
        with self.assertRaises(launcher.LauncherError):
            launcher.enforce_attempt_budget(
                ns(attempt_kind="fallback", fallback_from="codex-normal"), "codex-normal",
                "t1", self.catalog, budgets, one)
        full = ledger_of(spawned_entry("codex-normal"), spawned_entry("codex-normal", kind="retry"),
                         spawned_entry("antigravity-normal", kind="fallback"))
        with self.assertRaises(launcher.LauncherError):
            launcher.enforce_attempt_budget(ns(attempt_kind="retry", reconciled=True), "antigravity-normal",
                                            "t1", self.catalog, budgets, full)

    def test_private_data_refused_on_contributor_route(self) -> None:
        import argparse
        contributor = self.routes["opencode-zen-contributor"]
        with self.assertRaises(self.launcher.LauncherError):
            self.launcher.check_data_class(argparse.Namespace(data_class="private"), contributor)
        self.assertEqual(
            self.launcher.check_data_class(argparse.Namespace(data_class="synthetic"), contributor), "synthetic"
        )

    def test_contributor_scope_is_synthetic_only(self) -> None:
        route = self.routes["opencode-zen-contributor"]
        self.assertEqual(route.get("scope"), "synthetic-public-only")
        self.assertIn("synthetic_demo", str(route.get("allowed_workdir") or ""))
        self.assertEqual(self.catalog["policy"].get("contributor_scope"), "synthetic-public-only")

    def test_workflow_optimization_policy_present(self) -> None:
        policy = self.catalog["policy"]
        self.assertEqual(policy["timeout_tiers"]["small_seconds"], 180)
        self.assertEqual(policy["timeout_tiers"]["medium_seconds"], 300)
        self.assertEqual(policy["timeout_tiers"]["standard_seconds"], 600)
        self.assertTrue(policy["resume_policy"]["allowed"])
        self.assertTrue(policy["resume_policy"]["same_tool_only"])
        self.assertIn("tier1_draft", policy["routing_tiers"])
        self.assertIn("tier2_hard", policy["routing_tiers"])
        self.assertIn("tier3_review_paid", policy["routing_tiers"])
        self.assertLessEqual(policy["task_sizing"]["max_recommended_task_chars"], 3000)
        self.assertEqual(policy["task_sizing"]["warn_chars"], 2500)
        self.assertEqual(policy["task_sizing"]["hard_cap_chars"], 6000)
        self.assertEqual(policy["task_sizing"]["approval_argument"], "--size-approval")
        self.assertNotIn("default_timeout_seconds", policy)
        for route_id, route in self.routes.items():
            with self.subTest(route=route_id):
                self.assertTrue(route.get("resume_supported"))
                self.assertTrue(str(route.get("resume_flag") or "").strip())
                self.assertLessEqual(int(route.get("recommended_timeout_seconds") or 600), 600)

    def test_timeout_tier_labels(self) -> None:
        policy = self.catalog["policy"]
        for seconds, tier in ((120, "small"), (180, "small"), (300, "medium"), (600, "standard")):
            _, metadata = self.launcher.resolve_timeout(
                argparse.Namespace(timeout=seconds, timeout_approval=None), policy
            )
            self.assertEqual(metadata["tier"], tier)
        _, approved = self.launcher.resolve_timeout(
            argparse.Namespace(timeout=1200, timeout_approval="tier-test"), policy
        )
        self.assertEqual(approved["tier"], "approved_override")

    def test_resume_argv_construction(self) -> None:
        launcher = self.launcher
        workdir = Path(str(WORKDIR)).resolve()
        codex_route = self.catalog["routes"]["codex-normal"]
        argv, index = launcher.build_argv(
            codex_route, Path("codex"), "fixup task", workdir, 180, "max",
            True, "01a0b9f1-9bcd-7982-b9a6-44d258d929d0",
        )
        self.assertIn("resume", argv)
        self.assertIn("01a0b9f1-9bcd-7982-b9a6-44d258d929d0", argv)
        self.assertEqual(argv[index], "fixup task")
        agy_route = self.catalog["routes"]["antigravity-normal"]
        argv, index = launcher.build_argv(
            agy_route, Path("agy"), "fixup task", workdir, 180, "high",
            True, "378f5d8e-698d-407b-b1a9-9861df2bd5e9",
        )
        self.assertIn("--conversation", argv)
        self.assertEqual(argv[index], "fixup task")
        oc_route = self.catalog["routes"]["opencode-bedrock"]
        argv, index = launcher.build_argv(
            oc_route, Path("opencode"), "fixup task", workdir, 300, "max",
            True, "ses_f41fed68dffe8ymOlUSfRsNLFq",
        )
        self.assertIn("--session", argv)
        self.assertEqual(argv[index], "fixup task")

    def test_resume_validation_fails_closed(self) -> None:
        launcher = self.launcher
        workdir = Path(str(WORKDIR)).resolve()
        codex_route = self.catalog["routes"]["codex-normal"]
        with self.assertRaises(launcher.LauncherError):
            launcher.build_argv(codex_route, Path("codex"), "t", workdir, 180, "max", True, "bad id!")
        with self.assertRaises(launcher.LauncherError):
            launcher.build_argv(
                codex_route, Path("codex"), "t", workdir, 180, "max",
                False, "01a0b9f1-9bcd-7982-b9a6-44d258d929d0",
            )
        fresh, _ = launcher.build_argv(codex_route, Path("codex"), "t", workdir, 180, "max", True, None)
        self.assertNotIn("resume", fresh)

    def test_fixup_policy_present(self) -> None:
        policy = self.catalog["policy"]
        self.assertTrue(policy["fixup_policy"]["fixup_is_new_task_key"])
        self.assertEqual(policy["fixup_policy"]["max_consecutive_fixups"], 2)
        self.assertTrue(policy["ephemeral_worktree"]["requires_git_repo"])
        self.assertFalse(policy["ephemeral_worktree"]["launcher_auto_create"])
        self.assertTrue(policy["outer_ring"]["pilot"])
        self.assertFalse(policy["outer_ring"]["cline_integration"])
        self.assertEqual(policy["outer_ring"]["review_gate"], "mandatory-brain-review-before-external-use")

    def test_fixup_validation_caps_consecutive_fixups(self) -> None:
        launcher = self.launcher

        def ns(**kwargs):
            base = dict(fixup_of=None, fixup_depth=0)
            base.update(kwargs)
            return argparse.Namespace(**base)

        of, depth = launcher.validate_fixup(ns(), self.catalog)
        self.assertIsNone(of)
        self.assertEqual(depth, 0)
        of, depth = launcher.validate_fixup(ns(fixup_of="sha256:abc123", fixup_depth=1), self.catalog)
        self.assertEqual(of, "sha256:abc123")
        self.assertEqual(depth, 1)
        of, depth = launcher.validate_fixup(ns(fixup_of="origin-key", fixup_depth=2), self.catalog)
        self.assertEqual(depth, 2)
        with self.assertRaises(launcher.LauncherError) as over:
            launcher.validate_fixup(ns(fixup_of="origin-key", fixup_depth=3), self.catalog)
        self.assertEqual(over.exception.code, "fixup_budget_exhausted")
        with self.assertRaises(launcher.LauncherError) as missing:
            launcher.validate_fixup(ns(fixup_of="origin-key", fixup_depth=0), self.catalog)
        self.assertEqual(missing.exception.code, "fixup_depth_missing")
        with self.assertRaises(launcher.LauncherError):
            launcher.validate_fixup(ns(fixup_depth=-1), self.catalog)
        with self.assertRaises(launcher.LauncherError):
            launcher.validate_fixup(ns(fixup_of="bad key!", fixup_depth=1), self.catalog)

    def test_task_size_gate_warns_and_refuses(self) -> None:
        launcher = self.launcher
        policy = self.catalog["policy"]

        def ns(**kwargs):
            base = dict(size_approval=None)
            base.update(kwargs)
            return argparse.Namespace(**base)

        small = launcher.check_task_size("x" * 100, ns(), policy)
        self.assertFalse(small["oversize_warn"])
        self.assertEqual(small["chars"], 100)
        self.assertEqual(small["prompt_est_tokens"], 25)
        large = launcher.check_task_size("x" * 3000, ns(), policy)
        self.assertTrue(large["oversize_warn"])
        self.assertIsNone(large["approval_fingerprint"])
        with self.assertRaises(launcher.LauncherError) as refused:
            launcher.check_task_size("x" * 7000, ns(), policy)
        self.assertEqual(refused.exception.code, "task_oversize_requires_approval")
        approved = launcher.check_task_size(
            "x" * 7000, ns(size_approval="supervisor-approved scaffold"), policy
        )
        self.assertTrue(approved["oversize_warn"])
        self.assertEqual(len(approved["approval_fingerprint"]), 64)
        self.assertNotIn("supervisor", json.dumps(approved))
        with self.assertRaises(launcher.LauncherError) as too_big:
            launcher.check_task_size(
                "x" * 31000, ns(size_approval="even-approved-is-too-big"), policy
            )
        self.assertEqual(too_big.exception.code, "task_exceeds_win32_command_limit")

    def test_task_size_policy_rejects_bad_catalog(self) -> None:
        import copy
        launcher = self.launcher
        for bad in ({"warn_chars": True, "hard_cap_chars": 6000},
                    {"warn_chars": 2500, "hard_cap_chars": "lots"},
                    {"warn_chars": 6000, "hard_cap_chars": 2500}):
            catalog = copy.deepcopy(self.catalog)
            catalog["policy"]["task_sizing"] = bad
            with self.assertRaises(launcher.LauncherError, msg=str(bad)):
                launcher.check_task_size("x" * 100, argparse.Namespace(size_approval=None),
                                         catalog["policy"])
        catalog = copy.deepcopy(self.catalog)
        catalog["policy"]["task_sizing"] = "just-a-string"
        with self.assertRaises(launcher.LauncherError):
            launcher.check_task_size("x" * 100, argparse.Namespace(size_approval=None),
                                     catalog["policy"])

    def test_read_catalog_tolerates_bom(self) -> None:
        import tempfile
        launcher = self.launcher
        with tempfile.TemporaryDirectory() as temp_dir:
            bom_path = Path(temp_dir) / "catalog.json"
            bom_path.write_bytes(b"\xef\xbb\xbf" + CATALOG.read_bytes())
            catalog = launcher.read_catalog(bom_path)
            self.assertEqual(catalog["catalog_version"], self.catalog["catalog_version"])

    def test_worker_contract_header(self) -> None:
        launcher = self.launcher
        prompt = launcher.build_worker_prompt(Path(str(WORKDIR)).resolve(), "do the thing")
        self.assertIn("do the thing", prompt)
        self.assertIn("Work only in this exact directory", prompt)
        self.assertIn("do not run the repository test suite", prompt)
        self.assertIn("You are the implementer, not Brain, coordinator, or dispatcher", prompt)
        self.assertIn("Never read files outside the workdir", prompt)
        self.assertIn("Begin with the target file(s) directly", prompt)
        self.assertIn("ignore any auto-loaded repository instructions", prompt)
        self.assertLess(prompt.index("ROLE LOCK"), prompt.index("Workspace:"))
        self.assertIn("Files changed:", prompt)
        self.assertIn("Self-check:", prompt)
        self.assertIn("Verify with:", prompt)

    def test_verify_resumed_session(self) -> None:
        launcher = self.launcher
        self.assertIsNone(launcher.verify_resumed_session(None, None, {"attempts": []}))
        self.assertEqual(
            launcher.verify_resumed_session("sess-1", None, {"attempts": []}), "unverifiable"
        )
        self.assertEqual(
            launcher.verify_resumed_session("sess-1", "unknown-job", {"attempts": []}),
            "unverifiable",
        )
        ledger = {"attempts": [
            {"job_id": "job-a", "spawned": True, "worker_session_id": "sess-a"},
            {"job_id": "job-old", "spawned": True},
            {"job_id": "job-nos", "spawned": False, "worker_session_id": "sess-x"},
        ]}
        self.assertEqual(
            launcher.verify_resumed_session("sess-a", "job-a", ledger), "verified"
        )
        self.assertEqual(
            launcher.verify_resumed_session("sess-1", "job-old", ledger), "unverifiable"
        )
        self.assertEqual(
            launcher.verify_resumed_session("sess-1", "job-nos", ledger), "unverifiable"
        )
        with self.assertRaises(launcher.LauncherError) as wired:
            launcher.verify_resumed_session("sess-B", "job-a", ledger)
        self.assertEqual(wired.exception.code, "resume_session_mismatch")
        self.assertEqual(
            launcher.verify_resumed_session("sess-a", None, ledger, "retry"), "verified"
        )
        self.assertEqual(
            launcher.verify_resumed_session("sess-a", None, {"attempts": []}, "retry"),
            "unverifiable",
        )
        with self.assertRaises(launcher.LauncherError) as auto:
            launcher.verify_resumed_session("sess-B", None, ledger, "retry")
        self.assertEqual(auto.exception.code, "resume_session_mismatch")

    def test_fixup_depth_requires_origin(self) -> None:
        launcher = self.launcher
        with self.assertRaises(launcher.LauncherError) as orphan:
            launcher.validate_fixup(
                argparse.Namespace(fixup_of=None, fixup_depth=1), self.catalog
            )
        self.assertEqual(orphan.exception.code, "fixup_origin_missing")

    def test_count_fixups_in_dir(self) -> None:
        import tempfile
        launcher = self.launcher
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "a.json").write_text(json.dumps({"attempts": [
                {"job_id": "j1", "spawned": True, "fixup_of": "origin-1"},
                {"job_id": "j2", "spawned": True, "fixup_of": "origin-2"},
                {"job_id": "j3", "spawned": False, "fixup_of": "origin-1"},
            ]}), encoding="utf-8")
            (root / "b.json").write_text(json.dumps({"attempts": [
                {"job_id": "j4", "spawned": True, "fixup_of": "origin-1"},
            ]}), encoding="utf-8")
            (root / "broken.json").write_text("{not json", encoding="utf-8")
            self.assertEqual(launcher.count_fixups_in_dir("origin-1", root), 2)
            self.assertEqual(launcher.count_fixups_in_dir("origin-2", root), 1)
            self.assertEqual(launcher.count_fixups_in_dir("nobody", root), 0)

    def test_total_time_budget_gate(self) -> None:
        launcher = self.launcher
        policy = self.catalog["policy"]
        self.assertEqual(launcher.load_total_budget(policy), 1200.0)

        def ns(**kwargs):
            base = dict(timeout_approval=None)
            base.update(kwargs)
            return argparse.Namespace(**base)

        def ledger_of(*entries):
            return {"schema": "hermes-worker-attempts/v1", "attempts": list(entries)}

        def spawned(timeout, status="succeeded", cls="succeeded"):
            return {"spawned": True, "timeout_seconds": timeout, "status": status,
                    "failure_class": cls}

        empty = ledger_of()
        self.assertEqual(launcher.time_approval_triggers(ns(), policy, empty, 600), [])
        self.assertIsNone(launcher.gate_time_approval(ns(), []))

        two_walls = ledger_of(spawned(600), spawned(600))
        self.assertEqual(launcher.prior_time_spent(two_walls), 1200.0)
        triggers = launcher.time_approval_triggers(ns(), policy, two_walls, 300)
        self.assertIn("total_budget", triggers)
        with self.assertRaises(launcher.LauncherError) as blocked:
            launcher.gate_time_approval(ns(), triggers)
        self.assertEqual(blocked.exception.code, "time_approval_required")
        fp = launcher.gate_time_approval(ns(timeout_approval="burn-approved"), triggers)
        self.assertEqual(len(fp), 64)

        one_small = ledger_of(spawned(180))
        self.assertEqual(
            launcher.time_approval_triggers(ns(), policy, one_small, 300), []
        )

    def test_post_double_timeout_gate(self) -> None:
        launcher = self.launcher
        policy = self.catalog["policy"]

        def ns(**kwargs):
            base = dict(timeout_approval=None)
            base.update(kwargs)
            return argparse.Namespace(**base)

        timed_out = {"spawned": True, "timeout_seconds": 600, "status": "timeout",
                     "failure_class": "timeout_verify"}
        two = {"schema": "hermes-worker-attempts/v1",
               "attempts": [dict(timed_out), dict(timed_out)]}
        self.assertEqual(launcher.prior_timeouts(two), 2)
        triggers = launcher.time_approval_triggers(ns(), policy, two, 180)
        self.assertIn("post_double_timeout", triggers)
        with self.assertRaises(launcher.LauncherError) as blocked:
            launcher.gate_time_approval(ns(), triggers)
        self.assertEqual(blocked.exception.code, "time_approval_required")
        self.assertIsNotNone(
            launcher.gate_time_approval(ns(timeout_approval="third-try-approved"), triggers)
        )
        single = {"schema": "hermes-worker-attempts/v1", "attempts": [dict(timed_out)]}
        self.assertNotIn(
            "post_double_timeout",
            launcher.time_approval_triggers(ns(), policy, single, 180),
        )

    def test_build_ledger_entry_records_timeout(self) -> None:
        launcher = self.launcher
        receipt = {
            "job_id": "job-1", "worker_session_id": "sess-1",
            "resume": {"requested_session": None, "from_job": None},
            "fixup": {"of": None, "depth": 0},
            "process": {"timeout_seconds": 300.0},
            "reasoning": {"actual": "high"}, "quota_bucket": "q",
            "quota": "unknown", "quota_reset_at": None,
            "invocation_corrections": 0, "spawned": True, "status": "succeeded",
            "failure_class": "succeeded", "exit_code": 0, "error": None,
            "data_class": "synthetic", "billing": {"paid": False},
            "started_at": "t0", "finished_at": "t1",
        }
        entry = launcher.build_ledger_entry(
            receipt, argparse.Namespace(route="codex-normal", attempt_kind="initial",
                                        fallback_from=None, reconciled=False)
        )
        self.assertEqual(entry["timeout_seconds"], 300.0)
        self.assertEqual(entry["route"], "codex-normal")
        self.assertTrue(entry["spawned"])


    def test_recover_codex_session_usage(self) -> None:
        import tempfile
        launcher = self.launcher
        self.assertIsNone(launcher.recover_codex_session_usage(None))
        self.assertIsNone(launcher.recover_codex_session_usage("bad id!"))
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.assertIsNone(launcher.recover_codex_session_usage("nosuchsession", root))
            rollout = root / "rollout-2026-01-01T00-00-00-abcd1234.jsonl"
            rollout.write_text("\n".join([
                json.dumps({"type": "session_meta"}),
                json.dumps({"type": "token_usage_record", "payload": {
                    "thread_token_usage": {"input_tokens": 100, "cached_input_tokens": 10,
                                           "output_tokens": 5, "reasoning_output_tokens": 2}}}),
                "not-json{{{",
                json.dumps({"type": "token_usage_record", "payload": {
                    "thread_token_usage": {"input_tokens": 300, "cached_input_tokens": 200,
                                           "output_tokens": 9, "reasoning_output_tokens": 4}}}),
            ]) + "\n", encoding="utf-8")
            recovered = launcher.recover_codex_session_usage("abcd1234", root)
            assert recovered is not None
            self.assertEqual(recovered["input_tokens"], 300)
            self.assertEqual(recovered["cached_input_tokens"], 200)
            self.assertEqual(recovered["output_tokens"], 9)
            self.assertEqual(recovered["source"], "codex-session-store-posthoc")

    def test_owner_lock_exclusive_release_and_takeover(self) -> None:
        import tempfile
        launcher = self.launcher
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "k.lock"
            launcher.acquire_owner_lock(first, job_id="j1", scope="taskkey",
                                        entry_extra={"route": "r", "timeout_seconds": 60})
            with self.assertRaises(launcher.LauncherError) as busy:
                launcher.acquire_owner_lock(first, job_id="j2", scope="taskkey",
                                            entry_extra={})
            self.assertEqual(busy.exception.code, "taskkey_busy")
            launcher.release_owner_lock(first, job_id="j2")
            self.assertTrue(first.exists())
            launcher.release_owner_lock(first, job_id="j1")
            self.assertFalse(first.exists())
            launcher.acquire_owner_lock(first, job_id="j3", scope="taskkey",
                                        entry_extra={})
            stale = root / "s.lock"
            stale.write_text(json.dumps({"pid": 999999999, "job_id": "old"}),
                             encoding="utf-8")
            launcher.acquire_owner_lock(stale, job_id="j4", scope="worktree",
                                        entry_extra={})
            entry = json.loads(stale.read_text(encoding="utf-8"))
            self.assertTrue(entry.get("stale_lock_cleared"))
            self.assertEqual(entry.get("job_id"), "j4")
            third = root / "w.lock"
            launcher.acquire_worktree_lock(third, job_id="j1", route_id="r", timeout=60.0)
            with self.assertRaises(launcher.LauncherError) as wbusy:
                launcher.acquire_worktree_lock(third, job_id="j2", route_id="r", timeout=60.0)
            self.assertEqual(wbusy.exception.code, "worktree_busy")

    def test_taskkey_lock_path_scoped(self) -> None:
        import tempfile
        launcher = self.launcher
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            catalog = {"policy": {"taskkey_locks": str(root / "outside")}}
            with self.assertRaises(launcher.LauncherError) as scoped:
                launcher.taskkey_lock_path("some-key", catalog, root / "c.json")
            self.assertEqual(scoped.exception.code, "taskkey_locks_outside_scope")
            plain = launcher.taskkey_lock_path(
                "some-key", {"policy": {}}, CATALOG)
            self.assertEqual(plain.parent.name, "worker_taskkeys")
            self.assertEqual(len(plain.stem), 64)


if __name__ == "__main__":
    unittest.main(verbosity=2)
