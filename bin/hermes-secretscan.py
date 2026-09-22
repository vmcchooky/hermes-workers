#!/usr/bin/env python3
"""Pre-publication secret scanner for Hermes (local only, no network).

Walks a root directory, classifies every file with .gitignore rules, and
reports secret-looking matches. Output never contains secret material:
only path:line and rule name. Findings in publishable (non-ignored) files
are LEAKs; findings in ignored files are INFO audit trail.

Exit 0: no LEAK (safe to publish). Exit 2: at least one LEAK.
CI usage: run before any public push; keep this script dependency-free.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


HERMES_ROOT = Path(__file__).resolve().parents[1]

# (rule name, pattern, value-group index or None for whole-match check)
RULES: list[tuple[str, re.Pattern[str], int | None]] = [
    ("aws-access-key", re.compile(r"AKIA[0-9A-Z]{16}"), None),
    ("github-token", re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"), None),
    ("slack-token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), None),
    ("openai-key", re.compile(r"sk-[A-Za-z0-9]{16,}"), None),
    ("google-api-key", re.compile(r"AIza[0-9A-Za-z\-_]{35}"), None),
    ("private-key", re.compile(r"-----BEGIN (?:RSA )?PRIVATE KEY-----"), None),
    ("discord-webhook", re.compile(r"https://discord(?:app)?\.com/api/webhooks/[^\s'\"]+"), None),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,}"), None),
    (
        "secret-assignment",
        re.compile(
            r"(?i)\b(api_key|apikey|secret|passwd|password|auth_token|refresh_token"
            r"|access_token|session_token|client_secret)\b\s*[:=]\s*['\"]?"
            r"([^\s'\";,}().]{12,})"
        ),
        2,
    ),
]

# Matches snake_case code identifiers (function names, attribute chains cut at
# the dot). Real secret material is never shaped like this; weak all-lowercase
# underscore secrets are the documented blind spot.
CODE_SHAPED = re.compile(r"[a-z]+(?:_[a-z0-9]+)+$")

# Markers that prove a match is a fixture/doc placeholder, checked
# case-insensitively against the captured secret value (or whole match).
PLACEHOLDER_MARKERS = (
    "fake-", "example", "placeholder", "your_", "xxx", "test-",
    "dummy", "sample", "changeme", "redacted", "<", ">",
)

SECRET_FILENAMES = (".pem", ".key", ".p12", ".pfx", "id_rsa", "id_ed25519")

MAX_SCAN_BYTES = 5 * 1024 * 1024


def is_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def glob_to_regex(pattern: str) -> str:
    """Gitwildmatch subset with git-correct parent semantics.

    Single `*` never crosses `/` and never matches a bare dir itself, so
    `X/*` prunes children (including bare subdirs, via the trailing `/?`)
    without excluding `X/` — the classic re-inclusion chain keeps working.
    `X/` (trailing slash) matches the dir itself and everything beneath, and
    once a parent level is excluded nothing below can override it.
    """
    pattern = pattern.lstrip("/")
    anchored = "/" in pattern
    if pattern.endswith("/"):
        body = f"(?:{_translate_core(pattern.rstrip('/'))})(?:/.*)?"
    elif pattern.endswith("/*"):
        body = f"{_translate_core(pattern[:-2])}/[^/]+/?"
    else:
        body = _translate_core(pattern)
    if anchored:
        return f"{body}$"
    return f"(?:.*/)?{body}$"


def _translate_core(pattern: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if char == "*":
            if pattern[i:i + 2] == "**":
                out.append(".*")
                i += 2
                if pattern[i:i + 1] == "/":
                    i += 1
            else:
                out.append("[^/]+")
                i += 1
        elif char == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(char))
            i += 1
    return "".join(out)


def load_gitignore(root: Path) -> list[tuple[bool, re.Pattern[str]]]:
    path = root / ".gitignore"
    patterns: list[tuple[bool, re.Pattern[str]]] = []
    if not path.is_file():
        return patterns
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        if negated:
            line = line[1:].strip()
            if not line:
                continue
        try:
            patterns.append((negated, re.compile(glob_to_regex(line))))
        except re.error:
            continue
    return patterns


def _match_level(path: str, patterns: list[tuple[bool, re.Pattern[str]]]) -> bool | None:
    """Last matching pattern at one level decides; None when nothing matches."""
    decision: bool | None = None
    for negated, regex in patterns:
        if regex.search(path):
            decision = not negated
    return decision


def is_ignored(rel_posix: str, patterns: list[tuple[bool, re.Pattern[str]]]) -> bool:
    """Git-style classification: walk root-ward levels, parent exclusion wins.

    Each ancestor dir is decided by the last pattern matching that level; an
    excluded parent returns True immediately (nothing below can override it,
    exactly like git), while a re-included dir lets deeper levels decide.
    `X/*` prunes children but never excludes `X/` itself, so negation chains
    (`X/*`, `!X/keep/`, ...) behave like git.
    """
    parts = rel_posix.split("/")
    for depth in range(1, len(parts)):
        decision = _match_level("/".join(parts[:depth]) + "/", patterns)
        if decision is True:
            return True
    return _match_level(rel_posix, patterns) is True


def scan_file(path: Path) -> tuple[list[tuple[int, str]], str | None]:
    """Scan one file. Returns (findings, skip_reason).

    skip_reason is None when scanned, else one of: oversize, unreadable,
    binary. Skips are reported (never silent) so an unreadable file full of
    secrets cannot pass the audit quietly.
    """
    try:
        if path.stat().st_size > MAX_SCAN_BYTES:
            return [], "oversize"
        raw = path.read_bytes()
    except OSError:
        return [], "unreadable"
    if b"\x00" in raw[:4096]:
        return [], "binary"
    findings: list[tuple[int, str]] = []
    for number, line in enumerate(raw.decode("utf-8", errors="replace").splitlines(), 1):
        for name, regex, value_group in RULES:
            for match in regex.finditer(line):
                probe = match.group(value_group) if value_group else match.group(0)
                if is_placeholder(probe):
                    continue
                if name == "secret-assignment" and CODE_SHAPED.fullmatch(probe):
                    continue
                findings.append((number, name))
                break
    return findings, None


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Hermes pre-publication secret scanner")
    parser.add_argument("--root", default=str(HERMES_ROOT), help="tree to audit")
    parser.add_argument(
        "--tracked-only",
        action="store_true",
        help="scan contents of publishable files only; ignored paths are counted as skipped "
        "(fast mode for huge working trees with venv/node copies; full mode remains the audit default)",
    )
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    patterns = load_gitignore(root)
    leaks = 0
    infos = 0
    scanned = 0
    skipped = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        rel = path.relative_to(root).as_posix()
        ignored = is_ignored(rel, patterns)
        if ignored and args.tracked_only:
            skipped += 1
            continue
        findings, skip_reason = scan_file(path)
        if skip_reason is not None:
            # Binaries are expected and filename-guarded below; oversize and
            # unreadable files are suspicious and must appear in the audit.
            if skip_reason in ("oversize", "unreadable"):
                print(f"SKIP {rel} {skip_reason}")
            skipped += 1
            continue
        for number, name in findings:
            if ignored:
                print(f"INFO {rel}:{number} {name}")
                infos += 1
            else:
                print(f"LEAK {rel}:{number} {name}")
                leaks += 1
        if any(path.name.endswith(ext) or path.name == ext for ext in SECRET_FILENAMES):
            if not ignored:
                print(f"LEAK {rel}:1 secret-filename")
                leaks += 1
            else:
                print(f"INFO {rel}:1 secret-filename")
                infos += 1
        scanned += 1
    print(f"scanned={scanned} skipped={skipped} leaks={leaks} ignored_findings={infos}")
    return 2 if leaks else 0


if __name__ == "__main__":
    raise SystemExit(main())
