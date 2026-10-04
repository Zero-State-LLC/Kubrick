#!/usr/bin/env python3
"""Reject foreign deploy and pin workflows. Issue #105."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_FILE = re.compile(r"(noema|deploy|pin)", re.IGNORECASE)
_NAME = re.compile(r"(?m)^name:\s*.*\b(deploy|pin|noema)\b", re.IGNORECASE)
_BODY = re.compile(r"noema", re.IGNORECASE)


def scan(root: Path) -> list[str]:
    folder = root / ".github" / "workflows"
    if not folder.is_dir():
        return [f"missing workflow directory: {folder}"]
    problems: list[str] = []
    for path in sorted(folder.iterdir()):
        if not path.is_file():
            continue
        if _FILE.search(path.stem):
            problems.append(f"foreign workflow file: {path.name}")
        text = path.read_text(encoding="utf-8", errors="replace")
        if _BODY.search(text):
            problems.append(f"Noema reference in {path.name}")
        if _NAME.search(text):
            problems.append(f"foreign workflow name in {path.name}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    problems = scan(args.root)
    if problems:
        print("workflow check: FAIL", file=sys.stderr)
        for item in problems:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("workflow check: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
