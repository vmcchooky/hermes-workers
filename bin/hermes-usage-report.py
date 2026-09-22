#!/usr/bin/env python3
"""Read-only Brain-vs-worker usage report for Hermes (local only, no network).

Reads worker receipts (logs/worker_usage.jsonl), Brain CanonicalUsage
(state.db session_model_usage, opened read-only), and Brain test verdicts
(logs/brain_verdicts.jsonl), then prints three SEPARATE sections. Worker and
Brain meters have different semantics and must never be added together; this
script reports them side by side and refuses to print a combined total.

Exit 0 always unless arguments are unusable; missing inputs degrade to
`unavailable` warnings instead of failing (fresh installs have no history).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


HERMES_ROOT = Path(__file__).resolve().parents[1]


def read_receipts(path: Path) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    warnings: list[str] = []
    if not path.is_file():
        return rows, [f"worker log missing: {path}"]
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        return rows, [f"worker log unreadable: {type(exc).__name__}"]
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            warnings.append(f"worker log line {number}: skipped (not JSON)")
            continue
        rows.append(record if isinstance(record, dict) else {})
    return rows, warnings


def read_brain_usage(path: Path) -> tuple[list[dict], list[str]]:
    if not path.is_file():
        return [], [f"brain db missing: {path}"]
    try:
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return [], [f"brain db unavailable: {type(exc).__name__}"]
    try:
        tables = {row[0] for row in connection.execute(
            "select name from sqlite_master where type='table'")}
        if "session_model_usage" not in tables:
            return [], ["brain db has no session_model_usage table"]
        rows = [
            dict(zip(
                ("session_id", "model", "billing_provider", "billing_base_url",
                 "billing_mode", "task", "api_call_count", "input_tokens",
                 "output_tokens", "cache_read_tokens", "cache_write_tokens",
                 "reasoning_tokens"),
                row,
            ))
            for row in connection.execute(
                "select session_id, model, billing_provider, billing_base_url,"
                " billing_mode, task, api_call_count, input_tokens, output_tokens,"
                " cache_read_tokens, cache_write_tokens, reasoning_tokens"
                " from session_model_usage"
            )
        ]
        return rows, []
    except sqlite3.Error as exc:
        return [], [f"brain usage query failed: {type(exc).__name__}"]
    finally:
        connection.close()


def read_verdicts(path: Path) -> tuple[list[dict], list[str]]:
    if not path.is_file():
        return [], ["no verdicts recorded yet"]
    verdicts: list[dict] = []
    warnings: list[str] = []
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        return [], [f"verdict log unreadable: {type(exc).__name__}"]
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            verdicts.append(record if isinstance(record, dict) else {})
        except json.JSONDecodeError:
            warnings.append(f"verdict line {number}: skipped (not JSON)")
    return verdicts, warnings


def number(value) -> int | float:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def median(values: list) -> int | float | None:
    nums = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if not nums:
        return None
    ordered = sorted(nums)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def render(receipts: list[dict], brain: list[dict], verdicts: list[dict],
           warnings: list[str]) -> str:
    lines: list[str] = []
    lines.append("== WORKER (per-route meters; semantics differ per adapter) ==")
    by_route: dict[str, dict] = {}
    for record in receipts:
        route = str(record.get("route") or "unknown")
        bucket = by_route.setdefault(route, {
            "jobs": 0, "succeeded": 0, "timeout": 0, "failed": 0, "blocked": 0,
            "input": 0, "cached": 0, "output": 0, "reasoning": 0, "cost_usd": 0.0,
            "cost_seen": 0,
        })
        bucket["jobs"] += 1
        status = str(record.get("status") or "unknown")
        if status in bucket:
            bucket[status] += 1
        usage = record.get("usage") or {}
        bucket["input"] += number(usage.get("input"))
        bucket["cached"] += number(usage.get("cached_input"))
        bucket["output"] += number(usage.get("output"))
        bucket["reasoning"] += number(usage.get("reasoning"))
        cost = (record.get("cost") or {}).get("usd")
        if isinstance(cost, (int, float)) and not isinstance(cost, bool):
            bucket["cost_usd"] += cost
            bucket["cost_seen"] += 1
    if not by_route:
        lines.append("(no worker jobs recorded)")
    for route in sorted(by_route):
        bucket = by_route[route]
        lines.append(
            f"{route}: jobs={bucket['jobs']} ok={bucket['succeeded']} "
            f"timeout={bucket['timeout']} failed={bucket['failed']} blocked={bucket['blocked']} "
            f"in={bucket['input']} cached={bucket['cached']} out={bucket['output']} "
            f"think={bucket['reasoning']} usd={bucket['cost_usd']:.4f} "
            f"(covers {bucket['cost_seen']}/{bucket['jobs']} jobs)"
        )
    lines.append("== BRAIN (CanonicalUsage buckets; separate meter, never added to worker) ==")
    by_model: dict[str, dict] = {}
    for row in brain:
        model = str(row.get("model") or "unknown")
        bucket = by_model.setdefault(model, {
            "calls": 0, "input": 0, "output": 0, "cache_read": 0,
            "cache_write": 0, "reasoning": 0,
        })
        bucket["calls"] += number(row.get("api_call_count"))
        bucket["input"] += number(row.get("input_tokens"))
        bucket["output"] += number(row.get("output_tokens"))
        bucket["cache_read"] += number(row.get("cache_read_tokens"))
        bucket["cache_write"] += number(row.get("cache_write_tokens"))
        bucket["reasoning"] += number(row.get("reasoning_tokens"))
    if not by_model:
        lines.append("(no brain usage recorded)")
    for model in sorted(by_model):
        bucket = by_model[model]
        lines.append(
            f"{model}: calls={bucket['calls']} input={bucket['input']} "
            f"out={bucket['output']} cache_read={bucket['cache_read']} "
            f"cache_write={bucket['cache_write']} think={bucket['reasoning']}"
        )
    lines.append("== RESUME ECONOMICS (within-tool only; jobs without input telemetry excluded) ==")
    by_tool: dict[str, dict] = {}
    for record in receipts:
        tool = str(record.get("tool") or "unknown")
        mode = str((record.get("resume") or {}).get("mode") or "fresh")
        bucket = by_tool.setdefault(tool, {"fresh": [], "resume": []})
        if mode in bucket:
            bucket[mode].append((record.get("usage") or {}).get("input"))
        else:
            bucket["fresh"].append((record.get("usage") or {}).get("input"))
    if not by_tool:
        lines.append("(no worker jobs recorded)")
    for tool in sorted(by_tool):
        bucket = by_tool[tool]
        lines.append(
            f"{tool}: fresh_n={len(bucket['fresh'])} "
            f"median_in_fresh={median(bucket['fresh'])} "
            f"resume_n={len(bucket['resume'])} "
            f"median_in_resume={median(bucket['resume'])}"
        )
    lines.append("== VERDICTS (first-pass verification rate) ==")
    known_jobs = {str(r.get("job_id")) for r in receipts if r.get("job_id")}
    seen: dict[str, dict] = {}
    for verdict in verdicts:
        job_id = str(verdict.get("job_id") or "")
        if job_id in known_jobs:
            seen[job_id] = verdict if isinstance(verdict, dict) else {}
    matched = list(seen.values())
    passed = sum(1 for v in matched if str(v.get("test_status")) == "pass")
    unknown_jobs = sorted({str(v.get("job_id") or "") for v in verdicts
                           if str(v.get("job_id") or "") and str(v.get("job_id")) not in known_jobs})
    if matched:
        lines.append(f"FPVR: {passed}/{len(matched)} passed first try "
                     f"({len(unknown_jobs)} verdict(s) reference unknown jobs)")
    else:
        lines.append("(no matched verdicts)")
    for warning in warnings:
        lines.append(f"WARN {warning}")
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hermes read-only Brain-vs-worker usage report")
    parser.add_argument("--usage-log", default=str(HERMES_ROOT / "logs" / "worker_usage.jsonl"))
    parser.add_argument("--state-db", default=str(HERMES_ROOT / "state.db"))
    parser.add_argument("--verdicts", default=str(HERMES_ROOT / "logs" / "brain_verdicts.jsonl"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args(argv)
    receipts, warnings = read_receipts(Path(args.usage_log))
    brain, brain_warnings = read_brain_usage(Path(args.state_db))
    verdicts, verdict_warnings = read_verdicts(Path(args.verdicts))
    warnings.extend(brain_warnings)
    warnings.extend(verdict_warnings)
    sys.stdout.write(render(receipts, brain, verdicts, warnings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
