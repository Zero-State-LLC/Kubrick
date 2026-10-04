#!/usr/bin/env python3
"""Foreign deploy and pin workflows fail the workflow check. Issue #105."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import check_workflows  # noqa: E402


def _write(root: Path, name: str, text: str) -> None:
    folder = root / ".github" / "workflows"
    folder.mkdir(parents=True)
    (folder / name).write_text(text, encoding="utf-8")


def test_current_workflows_pass() -> None:
    assert check_workflows.scan(check_workflows.ROOT) == []


def test_deploy_pin_and_noema_are_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write(root, "deploy-worker.yml", "name: CI\n")
        assert any("deploy-worker.yml" in item for item in check_workflows.scan(root))
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write(root, "ci.yml", "name: pin release\n")
        assert any("foreign workflow name" in item for item in check_workflows.scan(root))
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write(root, "ci.yml", "name: CI\n# leftover Noema hook\n")
        assert any("Noema" in item for item in check_workflows.scan(root))


def main() -> None:
    test_current_workflows_pass()
    test_deploy_pin_and_noema_are_rejected()
    print("workflow check tests: PASS")


if __name__ == "__main__":
    main()
