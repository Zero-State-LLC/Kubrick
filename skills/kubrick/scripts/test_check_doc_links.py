#!/usr/bin/env python3
"""Relative Markdown links resolve, including the repository tree."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from check_doc_links import collect  # noqa: E402


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_missing_relative_link_fails() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _write(root, "docs/README.md", "See [gone](missing.md) and ![x](no.jpg).\n")
        _write(root, "docs/ok.md", "[home](README.md)\n")
        found = collect(root)
    assert any("missing.md" in item for item in found)
    assert any("no.jpg" in item for item in found)
    assert not any("ok.md" in item and "README.md" in item for item in found)


def test_external_and_fenced_links_are_ignored() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _write(
            root,
            "README.md",
            "\n".join(
                [
                    "[site](https://example.com/missing)",
                    "<a href='https://example.com/also'>x</a>",
                    "```",
                    "[gone](not-a-file.md)",
                    "```",
                    "",
                ]
            ),
        )
        assert collect(root) == []


def test_repository_doc_links() -> None:
    assert collect(ROOT) == []


def main() -> None:
    test_missing_relative_link_fails()
    test_external_and_fenced_links_are_ignored()
    test_repository_doc_links()
    print("doc link tests: PASS")


if __name__ == "__main__":
    main()
