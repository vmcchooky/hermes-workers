#!/usr/bin/env python3
"""Deterministic stubgen checks; no worker inference, no network, temp dirs only."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STUBGEN = ROOT / "bin" / "hermes-stubgen.py"

FIXTURE = '''"""Backend module docstring."""

import os
from dataclasses import dataclass

API_SECRET = "s3cret-backend-key"
LIMIT: int = 5000


def compute_score(user_id: str, weight: float = 1.5) -> float:
    """Score a user with the proprietary ranking algorithm."""
    secret_salt = "rank-salt-9f31"
    raw = _internal_rank(user_id, secret_salt)
    return raw * weight + 0.42


@route("/internal/score")
def _internal_rank(user_id: str, salt: str) -> float:
    return hash(user_id + salt) % 100 / 100.0


@dataclass(frozen=True)
class ScoredUser:
    """Public result shape."""
    user_id: str
    score: float = 0.0

    def band(self) -> str:
        """Bucket the score into a display band."""
        if self.score > 0.9:
            return "top-secret-tier"
        return "normal"


print("module side effect on import")

if __name__ == "__main__":
    print(compute_score("demo"))
'''


class StubgenTests(unittest.TestCase):
    def run_stubgen(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(STUBGEN), *args],
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    def test_bodies_and_secrets_are_stripped_signatures_kept(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "backend.py"
            out = Path(tmp) / "stub.py"
            src.write_text(FIXTURE, encoding="utf-8")
            result = self.run_stubgen("--src", str(src), "--out", str(out))
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(len(summary["files"]), 1)
            stub = out.read_text(encoding="utf-8")
            # interface kept
            self.assertIn("def compute_score", stub)
            self.assertIn("class ScoredUser", stub)
            self.assertIn("def band", stub)
            self.assertIn("Backend module docstring", stub)
            self.assertIn("Score a user", stub)
            self.assertIn("import os", stub)
            self.assertIn("API_SECRET", stub)
            self.assertIn("LIMIT: int", stub)
            # implementation gone
            self.assertNotIn("s3cret-backend-key", stub)
            self.assertNotIn("rank-salt-9f31", stub)
            self.assertNotIn("top-secret-tier", stub)
            self.assertNotIn("0.42", stub)
            self.assertNotIn("module side effect", stub)
            self.assertNotIn('__main__', stub)
            self.assertNotIn("@route", stub)
            # stub parses and every def body is docstring + ...
            tree = compile(stub, "<stub>", "exec")
            self.assertIsNotNone(tree)

    def test_values_become_ellipsis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "a.py"
            out = Path(tmp) / "b.py"
            src.write_text('X = 42\nY: str = "hi"\n', encoding="utf-8")
            result = self.run_stubgen("--src", str(src), "--out", str(out))
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            stub = out.read_text(encoding="utf-8")
            self.assertIn("X = ...", stub)
            self.assertIn("Y: str = ...", stub)
            self.assertNotIn("42", stub)

    def test_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "bad.py"
            out = Path(tmp) / "out.py"
            src.write_text("def broken(:\n", encoding="utf-8")
            bad = self.run_stubgen("--src", str(src), "--out", str(out))
            self.assertEqual(bad.returncode, 2)
            self.assertFalse(out.exists())
            txt = Path(tmp) / "notes.txt"
            txt.write_text("x", encoding="utf-8")
            nonpy = self.run_stubgen("--src", str(txt), "--out", str(out))
            self.assertEqual(nonpy.returncode, 2)
            src2 = Path(tmp) / "same.py"
            src2.write_text("x = 1\n", encoding="utf-8")
            same = self.run_stubgen("--src", str(src2), "--out", str(src2))
            self.assertEqual(same.returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
