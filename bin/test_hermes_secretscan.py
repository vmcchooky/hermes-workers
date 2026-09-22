#!/usr/bin/env python3
"""Deterministic secretscanner checks; temp dirs only, no network.

Fixtures build realistic-format tokens DYNAMICALLY so no secret-shaped
literal ever lives in this repo. The scanner must also never echo secrets.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCANNER = ROOT / "bin" / "hermes-secretscan.py"


def load_module():
    spec = importlib.util.spec_from_file_location("hermes_secretscan", SCANNER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SecretscanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scanner = load_module()

    def run_scanner(self, root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCANNER), "--root", str(root), *extra],
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    def test_leak_in_tracked_file_fails_and_hides_value(self) -> None:
        gh_token = "ghp_" + "A" * 36
        aws_key = "AKIA" + "I" * 16
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".gitignore").write_text("ignored/\n", encoding="utf-8")
            (root / "tracked.py").write_text(f'token = "{gh_token}"\n', encoding="utf-8")
            ignored = root / "ignored"
            ignored.mkdir()
            (ignored / "secret.txt").write_text(f"key={aws_key}\n", encoding="utf-8")
            result = self.run_scanner(root)
            self.assertEqual(result.returncode, 2)
            self.assertIn("LEAK tracked.py", result.stdout)
            self.assertIn("INFO ignored/secret.txt", result.stdout)
            self.assertNotIn(gh_token, result.stdout)
            self.assertNotIn(aws_key, result.stdout)
            self.assertNotIn(gh_token, result.stderr)
            (root / "tracked.py").write_text('token = "fake-dev-token"\n', encoding="utf-8")
            clean = self.run_scanner(root)
            self.assertEqual(clean.returncode, 0)
            self.assertIn("leaks=0", clean.stdout)

    def test_placeholders_do_not_match(self) -> None:
        self.assertTrue(self.scanner.is_placeholder("fake-access-token"))
        self.assertTrue(self.scanner.is_placeholder("YOUR_API_KEY_HERE"))
        self.assertTrue(self.scanner.is_placeholder("example-secret-value"))
        self.assertFalse(self.scanner.is_placeholder("ghp_" + "B" * 36))

    def test_code_shaped_values_do_not_match(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".gitignore").write_text("", encoding="utf-8")
            code = "\n".join([
                "access_token = get_valid_token()",
                "img = render(page, password=args.password)",
                "ws.protection.password = args.protect",
                "password = _decode(credential.password)",
            ]) + "\n"
            (root / "code.py").write_text(code, encoding="utf-8")
            result = self.run_scanner(root)
            self.assertEqual(result.returncode, 0, msg=result.stdout)
            self.assertIn("leaks=0", result.stdout)

    def test_tracked_only_mode(self) -> None:
        gh_token = "ghp_" + "C" * 36
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".gitignore").write_text("ignored/\n", encoding="utf-8")
            (root / "clean.py").write_text("x = 1\n", encoding="utf-8")
            ignored = root / "ignored"
            ignored.mkdir()
            (ignored / "s.txt").write_text(f"k={gh_token}\n", encoding="utf-8")
            result = self.run_scanner(root, "--tracked-only")
            self.assertEqual(result.returncode, 0)
            self.assertIn("leaks=0", result.stdout)
            self.assertNotIn(gh_token, result.stdout)

    def test_gitignore_matcher(self) -> None:
        matcher = self.scanner
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".gitignore").write_text(
                "auth.json\nlogs/\n*.pem\n!keep.pem\n", encoding="utf-8"
            )
            patterns = matcher.load_gitignore(root)
            self.assertTrue(matcher.is_ignored("auth.json", patterns))
            self.assertTrue(matcher.is_ignored("logs/a.jsonl", patterns))
            self.assertTrue(matcher.is_ignored("sub/deep/logs/a.jsonl", patterns))
            self.assertTrue(matcher.is_ignored("cert.pem", patterns))
            self.assertFalse(matcher.is_ignored("keep.pem", patterns))
            self.assertFalse(matcher.is_ignored("bin/run.py", patterns))

    def test_ignored_parent_cannot_be_reincluded_below(self) -> None:
        matcher = self.scanner
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".gitignore").write_text(
                "skills/*\n!skills/keep/\nskills/keep/*\n!skills/keep/mine/\n",
                encoding="utf-8",
            )
            patterns = matcher.load_gitignore(root)
            self.assertTrue(matcher.is_ignored("skills/vendor/a.py", patterns))
            self.assertTrue(
                matcher.is_ignored("skills/keep/mine/doc.md", patterns) is False
            )
            self.assertTrue(matcher.is_ignored("skills/keep/other.md", patterns))
            self.assertTrue(
                matcher.is_ignored("skills/keep/mine/deep/x.md", patterns) is False
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
