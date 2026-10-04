#!/usr/bin/env python3
"""Fail when a change adds an em dash (U+2014). Lines already on the base are not checked.

About 150 Markdown files on main already contain em dashes, so this is a ratchet: it reads
``git diff --unified=0 BASE...HEAD`` and checks only the added lines. Rewrite a hit with a
period, comma, colon, or parentheses. A line that must keep one (a fixture that tests em dash
detection) carries the marker ``em-dash: allow`` on the same line.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

from kubrick.paths import SKILL_ROOT

ROOT = SKILL_ROOT
EM_DASH = "\u2014"
ALLOW_MARKER = "em-dash: allow"
PATTERNS = ("*.md", "*.py", "*.yaml", "*.yml", "*.json", "*.txt", "*.toml", "*.sh")
# The hub mirror is a copy of root, and check_hub_sync proves they match.
MIRROR_PREFIX = "skills/kubrick/"
FIX = "em dash; rewrite with a period, comma, colon, or parentheses"
_FILE = re.compile(r"^\+\+\+ (?:b/)?(.*)$")
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


class Hit(NamedTuple):
    path: str
    line: int
    text: str


class GitFailed(RuntimeError):
    """Raised when git cannot produce the diff (missing base ref, not a repo)."""


def added_lines(diff: str) -> list[Hit]:
    """Every added line in a ``--unified=0`` diff, with its new-file line number."""
    out: list[Hit] = []
    path, line, in_header = "", 0, False
    for raw in diff.splitlines():
        if raw.startswith("diff --git "):
            path, in_header = "", True
            continue
        file_match = _FILE.match(raw) if in_header else None
        if file_match:
            path = "" if file_match.group(1) == "/dev/null" else file_match.group(1)
            continue
        hunk = _HUNK.match(raw)
        if hunk:
            line, in_header = int(hunk.group(1)), False
            continue
        if raw.startswith("+") and path and not in_header:
            out.append(Hit(path, line, raw[1:]))
            line += 1
    return out


def find_hits(diff: str) -> list[Hit]:
    return [
        hit
        for hit in added_lines(diff)
        if EM_DASH in hit.text
        and ALLOW_MARKER not in hit.text
        and not hit.path.startswith(MIRROR_PREFIX)
    ]


def git_diff(base: str, root: Path) -> str:
    cmd = ["git", "-C", str(root), "-c", "core.quotePath=false", "diff", "--unified=0",
           "--no-color", "--no-ext-diff", "-M", f"{base}...HEAD", "--", *PATTERNS]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False)
    if proc.returncode != 0:
        raise GitFailed(proc.stderr.strip() or f"git diff exited {proc.returncode}")
    return proc.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="origin/main",
                        help="ref to compare against (default origin/main)")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        hits = find_hits(git_diff(args.base, args.root))
    except GitFailed as exc:
        print(f"em dash check: ERROR (fail closed): {exc}", file=sys.stderr)
        return 2
    if hits:
        print(f"em dash check: FAIL ({len(hits)} added line(s) since {args.base})", file=sys.stderr)
        for hit in hits:
            print(f"{hit.path}:{hit.line}: {FIX}", file=sys.stderr)
            print(f"    {hit.text.strip()[:160]}", file=sys.stderr)
        return 1
    print(f"em dash check: PASS (no em dash added since {args.base})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
