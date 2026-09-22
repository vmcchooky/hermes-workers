#!/usr/bin/env python3
"""Deterministic usage-report checks; temp fixtures only, never the live db."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTER = ROOT / "bin" / "hermes-usage-report.py"


def receipt(job_id: str, route: str, status: str, usage: dict, cost=None) -> dict:
    record = {
        "job_id": job_id, "route": route, "status": status,
        "usage": usage, "cost": {"usd": cost},
    }
    return record


class UsageReportTests(unittest.TestCase):
    def run_reporter(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(REPORTER), *args],
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    def test_sections_stay_separate_and_numbers_add_up(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log = root / "usage.jsonl"
            log.write_text("\n".join([
                json.dumps(receipt("j1", "codex-hard", "succeeded", {
                    "input": 100, "cached_input": 60, "output": 40, "reasoning": 15})),
                json.dumps(receipt("j2", "antigravity-normal", "timeout", {
                    "input": None, "cached_input": None, "output": None, "reasoning": None})),
                json.dumps(receipt("j3", "opencode-bedrock", "succeeded", {
                    "input": 10, "cached_input": 20, "output": 5, "reasoning": 0}, 1.5)),
                "not-json{{{",
            ]) + "\n", encoding="utf-8")
            db = root / "state.db"
            connection = sqlite3.connect(str(db))
            connection.execute(
                "create table session_model_usage (session_id text, model text,"
                " billing_provider text, billing_base_url text, billing_mode text,"
                " task text, api_call_count integer, input_tokens integer,"
                " output_tokens integer, cache_read_tokens integer,"
                " cache_write_tokens integer, reasoning_tokens integer)")
            connection.execute(
                "insert into session_model_usage values"
                " ('s1','m-a','p','u','m','t',3,1000,200,50,5,300),"
                " ('s2','m-a','p','u','m','t',1,500,100,0,0,0)")
            connection.commit()
            connection.close()
            verdicts = root / "verdicts.jsonl"
            verdicts.write_text(
                json.dumps({"job_id": "j1", "route": "x", "test_status": "pass"}) + "\n"
                + json.dumps({"job_id": "j3", "route": "y", "test_status": "fail"}) + "\n",
                encoding="utf-8",
            )
            result = self.run_reporter("--usage-log", str(log), "--state-db", str(db),
                                       "--verdicts", str(verdicts))
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            out = result.stdout
            self.assertIn("== WORKER", out)
            self.assertIn("== BRAIN", out)
            self.assertIn("== VERDICTS", out)
            self.assertIn("codex-hard: jobs=1 ok=1", out)
            self.assertIn("in=100 cached=60 out=40 think=15", out)
            self.assertIn("antigravity-normal: jobs=1 ok=0 timeout=1", out)
            self.assertIn("usd=1.5000", out)
            self.assertIn("m-a: calls=4 input=1500", out)
            self.assertIn("FPVR: 1/2 passed first try", out)
            self.assertEqual(sum(1 for line in out.splitlines() if line.startswith("==")), 3)
            self.assertNotIn("combined total", out.lower())
            self.assertIn("skipped (not JSON)", out)

    def test_missing_inputs_degrade_gracefully(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = self.run_reporter("--usage-log", str(root / "no.jsonl"),
                                       "--state-db", str(root / "no.db"),
                                       "--verdicts", str(root / "no2.jsonl"))
            self.assertEqual(result.returncode, 0)
            self.assertIn("(no worker jobs recorded)", result.stdout)
            self.assertIn("(no brain usage recorded)", result.stdout)
            self.assertIn("(no matched verdicts)", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
