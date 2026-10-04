"""Tests for shared helpers and the lint ratchet (issue #72)."""

from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import check_lint_ratchet  # noqa: E402
from structured_io import load_mapping  # noqa: E402
from value_coerce import as_float, as_number, is_blank  # noqa: E402

ROOT = SCRIPTS.parent

# New modules must stay under 500 lines. Pre-existing exceptions are listed here.
# #82 split the last oversized module (scripts/production_engine.py).
LEGACY_OVERSIZED: set[str] = set()


class ValueCoerceTests(unittest.TestCase):
    def test_as_float(self) -> None:
        self.assertEqual(as_float("2.5"), 2.5)
        self.assertIsNone(as_float(True))
        self.assertIsNone(as_float("x"))

    def test_as_number(self) -> None:
        self.assertIsNone(as_number("2"))
        self.assertEqual(as_number(3), 3.0)

    def test_is_blank(self) -> None:
        self.assertTrue(is_blank(" None "))
        self.assertFalse(is_blank("a"))


class StructuredIoTests(unittest.TestCase):
    def _write(self, name: str, text: str) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_json_mapping(self) -> None:
        self.assertEqual(load_mapping(self._write("a.json", '{"k": 1}')), {"k": 1})

    def test_empty_json_object(self) -> None:
        self.assertEqual(load_mapping(self._write("a.json", "{}")), {})

    def test_json_list_rejected(self) -> None:
        with self.assertRaises(ValueError):
            load_mapping(self._write("a.json", "[1, 2]"))

    @unittest.skipUnless(find_spec("yaml"), "PyYAML not installed")
    def test_yaml_mapping(self) -> None:
        self.assertEqual(load_mapping(self._write("a.yaml", "k: 1\n")), {"k": 1})


class RatchetPureTests(unittest.TestCase):
    def test_ruff_counts(self) -> None:
        root = check_lint_ratchet.ROOT
        items = [
            {"filename": str(root / "scripts" / "a.py")},
            {"filename": str(root / "scripts" / "a.py")},
            {"filename": str(root / "scripts" / "b.py")},
        ]
        self.assertEqual(
            check_lint_ratchet.ruff_counts(json.dumps(items)),
            {"scripts/a.py": 2, "scripts/b.py": 1},
        )

    def test_mypy_counts(self) -> None:
        text = (
            "scripts/a.py:3: error: Bad thing  [misc]\n"
            "scripts/a.py:7:5: error: Other thing  [arg-type]\n"
            "scripts/a.py:7: note: See docs\n"
        )
        self.assertEqual(check_lint_ratchet.mypy_counts(text), {"scripts/a.py": 2})
        moved = "src/kubrick/plan/a.py:4: error: Moved  [misc]\n"
        self.assertEqual(
            check_lint_ratchet.mypy_counts(moved),
            {"src/kubrick/plan/a.py": 1},
        )

    def test_compare(self) -> None:
        baseline = {"ruff": {"scripts/a.py": 2}, "mypy": {}}
        current = {"ruff": {"scripts/a.py": 1, "scripts/new.py": 1}, "mypy": {}}
        regressions, tightenings = check_lint_ratchet.compare(baseline, current)
        self.assertTrue(any("scripts/new.py" in line for line in regressions))
        self.assertTrue(any("scripts/a.py" in line for line in tightenings))
        self.assertFalse(any("scripts/a.py" in line for line in regressions))


class RatchetToolFailureTests(unittest.TestCase):
    def test_abnormal_exit_fails_ratchet(self) -> None:
        import subprocess
        from unittest import mock

        failed = subprocess.CompletedProcess(["ruff"], 2, stdout="", stderr="bad config")
        with mock.patch.object(check_lint_ratchet.subprocess, "run", return_value=failed):
            with self.assertRaises(check_lint_ratchet.ToolFailed):
                check_lint_ratchet.collect_ruff()
            self.assertEqual(check_lint_ratchet.main([]), 2)


class RepoShapeTests(unittest.TestCase):
    def test_baseline_file_shape(self) -> None:
        path = SCRIPTS / "lint_baseline.json"
        self.assertTrue(path.is_file(), "scripts/lint_baseline.json missing")
        data = json.loads(path.read_text(encoding="utf-8"))
        for tool in ("ruff", "mypy"):
            self.assertIn(tool, data)
            for key in data[tool]:
                self.assertTrue(
                    key.startswith("scripts/") or key.startswith("src/kubrick/"),
                    key,
                )
                self.assertTrue((ROOT / key).is_file(), key)

    def test_no_scripts_module_over_500_lines(self) -> None:
        paths = list(SCRIPTS.glob("*.py"))
        paths.extend((ROOT / "src" / "kubrick").rglob("*.py"))
        for path in sorted(paths):
            key = path.relative_to(ROOT).as_posix()
            if key in LEGACY_OVERSIZED:
                continue
            lines = len(path.read_text(encoding="utf-8").splitlines())
            self.assertLessEqual(lines, 500, f"{key} has {lines} lines")

    def test_cli_handlers_stay_under_complexity_gate(self) -> None:
        tree = ast.parse((ROOT / "src/kubrick/cli.py").read_text(encoding="utf-8"))
        scores = {
            node.name: _complexity(node)
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertIn("main", scores)
        self.assertLessEqual(scores["main"], 22)
        for name, score in scores.items():
            self.assertLessEqual(score, 22, f"{name} complexity {score}")


def _complexity(fn: ast.AST) -> int:
    """Count branches in one function. Nested defs are scored on their own."""
    score = 1

    def walk(node: ast.AST) -> None:
        nonlocal score
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            return
        if isinstance(
            node,
            (
                ast.If,
                ast.For,
                ast.AsyncFor,
                ast.While,
                ast.ExceptHandler,
                ast.With,
                ast.AsyncWith,
                ast.Assert,
                ast.IfExp,
            ),
        ):
            score += 1
        elif isinstance(node, ast.BoolOp):
            score += max(len(node.values) - 1, 0)
        elif isinstance(node, ast.comprehension):
            score += 1 + len(node.ifs)
        for child in ast.iter_child_nodes(node):
            walk(child)

    body = getattr(fn, "body", [])
    for stmt in body:
        walk(stmt)
    return score


if __name__ == "__main__":
    unittest.main()
