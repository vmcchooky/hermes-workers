#!/usr/bin/env python3
"""Extract redacted interface stubs from Python backend files (outer-ring pilot).

Brain runs this LOCALLY to produce signature-only context for external /
contributor workers. It never sends anything anywhere; it only reads --src
and writes --out. Stubs are a redaction aid, NOT an air gap: signatures,
defaults, and class decorators are preserved and MUST pass Brain review
(mandatory per worker-catalog.json outer_ring policy) before any external use.

Redaction rules (fail closed on unreadable/invalid input):
  - keep: imports, function/class signatures, docstrings, class decorators,
    assignment names + annotations (values replaced with ...).
  - drop: function/method bodies, function/method decorators, module-level
    executable statements, `if __name__ == ...` blocks.
Known limitation (review gate covers it): default argument values and class
decorator arguments are part of the signature and are preserved verbatim, so
secrets placed in defaults/decorators remain visible. Keyword-only redaction
of values would change call semantics, so the tool keeps them and review
decides.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path


class Stubber(ast.NodeTransformer):
    """Replace implementations with ... while keeping interface nodes."""

    @staticmethod
    def _stub_body(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> list[ast.stmt]:
        body: list[ast.stmt] = []
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            body.append(node.body[0])  # keep docstring
        body.append(ast.Expr(value=ast.Constant(value=Ellipsis)))
        return body

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        node.decorator_list = []
        node.body = self._stub_body(node)
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
        node.decorator_list = []
        node.body = self._stub_body(node)
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        new_body: list[ast.stmt] = []
        for item in node.body:
            if (
                isinstance(item, ast.Expr)
                and isinstance(item.value, ast.Constant)
                and isinstance(item.value.value, str)
            ):
                new_body.append(item)  # class docstring
            elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                new_body.append(self.visit(item))
            elif isinstance(item, (ast.Assign, ast.AnnAssign)):
                new_body.append(self.visit(item))
            # every other class-level statement is dropped
        node.body = new_body or [ast.Expr(value=ast.Constant(value=Ellipsis))]
        return node

    def visit_Assign(self, node: ast.Assign) -> ast.Assign:
        node.value = ast.Constant(value=Ellipsis)
        return node

    def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AnnAssign:
        node.value = ast.Constant(value=Ellipsis)
        return node


def _is_main_guard(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "__name__"
    )


def stub_source(source: str) -> str:
    """Parse one Python source string and return the redacted stub text."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError(f"unparseable python source: {exc}") from exc
    kept: list[ast.stmt] = []
    for node in tree.body:
        if _is_main_guard(node):
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            kept.append(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            kept.append(Stubber().visit(node))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            kept.append(Stubber().visit(node))
        elif (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
            and not kept
        ):
            kept.append(node)  # module docstring, only if first
        # every other module-level statement (calls, loops, try blocks) is dropped
    stub_tree = ast.Module(body=kept, type_ignores=[])
    text = ast.unparse(stub_tree)
    return text + "\n"


def stub_file(src: Path, out: Path) -> dict[str, str]:
    if src.suffix.lower() != ".py":
        raise ValueError(f"refusing non-python source: {src}")
    if src.resolve() == out.resolve():
        raise ValueError("src and out must differ; refusing to overwrite the backend file")
    text = stub_source(src.read_text(encoding="utf-8"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    return {"src": str(src), "out": str(out)}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Redacted Python stub extractor (outer-ring pilot)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--src", help="single python source file")
    group.add_argument("--src-dir", help="directory of python sources (batch, mirrors tree)")
    parser.add_argument("--out", help="stub output file (with --src)")
    parser.add_argument("--out-dir", help="stub output directory (with --src-dir)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args(argv)
    try:
        results: list[dict[str, str]] = []
        if args.src:
            if not args.out:
                print("error: --src requires --out", file=sys.stderr)
                return 2
            results.append(stub_file(Path(args.src), Path(args.out)))
        else:
            if not args.out_dir:
                print("error: --src-dir requires --out-dir", file=sys.stderr)
                return 2
            src_dir = Path(args.src_dir)
            out_dir = Path(args.out_dir)
            if not src_dir.is_dir():
                print(f"error: src dir missing: {src_dir}", file=sys.stderr)
                return 2
            for path in sorted(src_dir.rglob("*.py")):
                rel = path.relative_to(src_dir)
                results.append(stub_file(path, out_dir / rel))
        print(json.dumps({"schema": "hermes-stubgen/v1", "files": results}, ensure_ascii=False, indent=2))
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
