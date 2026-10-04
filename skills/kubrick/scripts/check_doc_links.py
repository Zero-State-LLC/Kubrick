#!/usr/bin/env python3
"""Fail when a relative Markdown link or image points at a missing path.

External URLs are not fetched. The hub mirror under skills/ is skipped;
root is the source of truth and hub sync compares that tree.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
SKIP = frozenset({".git", "skills", "out", "dist", "__pycache__", ".venv"})
LINK = re.compile(r"!\[[^\]]*\]\(([^)]+)\)|\[[^\]]*\]\(([^)]+)\)")
HTML = re.compile(r"""(?:href|src)\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
REFERENCE = re.compile(r"^\s*\[[^\]]+\]:\s*(\S+)", re.MULTILINE)


def markdown_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in root.rglob("*.md"):
        if set(path.relative_to(root).parts) & SKIP:
            continue
        found.append(path)
    return found


def visible_text(text: str) -> str:
    kept: list[str] = []
    fenced = False
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            kept.append(line)
    return "".join(kept)


def location(raw: str) -> str | None:
    text = raw.strip()
    if text.startswith("<") and ">" in text:
        text = text[1 : text.index(">")]
    if " " in text:
        text = text.split(" ", 1)[0]
    if not text or text.startswith("#") or text.startswith("mailto:"):
        return None
    if "://" in text or text.startswith("//"):
        return None
    text = unquote(text.split("#", 1)[0].split("?", 1)[0])
    return text or None


def destinations(text: str) -> list[str]:
    body = visible_text(text)
    found: list[str] = []
    for match in LINK.finditer(body):
        raw = match.group(1) or match.group(2)
        target = location(raw)
        if target:
            found.append(target)
    for match in HTML.finditer(body):
        target = location(match.group(1))
        if target:
            found.append(target)
    for match in REFERENCE.finditer(body):
        target = location(match.group(1))
        if target:
            found.append(target)
    return found


def problems_in(root: Path, path: Path) -> list[str]:
    problems: list[str] = []
    relative = path.relative_to(root).as_posix()
    for target in destinations(path.read_text(encoding="utf-8")):
        resolved = (path.parent / target).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            problems.append(f"{relative}: link leaves the repo: {target}")
            continue
        if not resolved.exists():
            problems.append(f"{relative}: missing {target}")
    return problems


def collect(root: Path) -> list[str]:
    problems: list[str] = []
    for path in markdown_files(root):
        problems.extend(problems_in(root, path))
    return problems


def main() -> int:
    found = collect(ROOT)
    if found:
        print("\n".join(found))
        return 1
    print(f"doc links: PASS ({len(markdown_files(ROOT))} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
