#!/usr/bin/env python3
"""Resolve relative CLI path flags against the caller's working directory.

``kubrick.py`` runs routed scripts with the skill root as their cwd. A relative
``--input`` would otherwise be opened inside that root. Rewrite path flags to
absolute paths under ``KUBRICK_CALLER_CWD`` before dispatch.

``--brief`` and ``--evidence`` are paths on some surfaces and prose or labels
on others. Those values are rewritten only when they look like paths. Inline
briefs and ledger evidence labels stay as typed.
"""
from __future__ import annotations

import os
from pathlib import Path

# Values of these flags are filesystem paths on every routed script.
PATH_FLAGS = frozenset(
    {
        "--adapter-packet",
        "--answers",
        "--artifact",
        "--artifact-root",
        "--compile-receipt",
        "--current",
        "--design",
        "--expected",
        "--expected-state",
        "--fidelity-report",
        "--final",
        "--forge-bundle",
        "--forge-export",
        "--graph",
        "--grok-packet",
        "--input",
        "--ledger",
        "--observation",
        "--observation-input",
        "--out",
        "--output",
        "--packet",
        "--plan",
        "--previous",
        "--previous-report",
        "--receipt",
        "--receipt-output",
        "--report",
        "--retrieval-receipt",
        "--root",
        "--schema",
        "--storyboard",
        "--storyboard-plan",
        "--takes",
        "--write-ledger",
    }
)

# Same spelling is a path, inline prose, or a non-path label depending on surface.
AMBIGUOUS_PATH_FLAGS = frozenset({"--brief", "--evidence"})

_PATH_SUFFIXES = frozenset(
    {
        ".fountain",
        ".jpeg",
        ".jpg",
        ".json",
        ".markdown",
        ".md",
        ".mov",
        ".mp4",
        ".png",
        ".txt",
        ".webp",
        ".yaml",
        ".yml",
    }
)


def _root(cwd: str) -> Path:
    text = cwd.strip() or os.getcwd()
    return Path(text).expanduser().resolve()


def _inline_prose(value: str) -> bool:
    stripped = value.strip()
    if "\n" in value or "\x00" in value:
        return True
    if stripped.startswith("dramatic_problem"):
        return True
    return len(value) > 512


def _looks_like_path(value: str, root: Path) -> bool:
    if "/" in value or "\\" in value or value.startswith((".", "~")):
        return True
    if Path(value).suffix.lower() in _PATH_SUFFIXES:
        return True
    try:
        return (root / value).exists()
    except OSError:
        return False


def _should_rewrite(flag: str, value: str, root: Path) -> bool:
    if value in {"", "-"} or "\n" in value or "\x00" in value:
        return False
    if Path(value).expanduser().is_absolute():
        return False
    if flag in PATH_FLAGS:
        return True
    if flag not in AMBIGUOUS_PATH_FLAGS or _inline_prose(value):
        return False
    return _looks_like_path(value, root)


def _absolute(value: str, root: Path) -> str:
    return str((root / Path(value).expanduser()).resolve())


def rewrite(argv: list[str], cwd: str) -> list[str]:
    """Return ``argv`` with relative path-flag values made absolute under ``cwd``."""
    root = _root(cwd)
    out: list[str] = []
    index = 0
    limit = len(argv)
    while index < limit:
        token = argv[index]
        if token == "--":
            out.extend(argv[index:])
            break
        name, equals, inline = token.partition("=")
        tracked = name in PATH_FLAGS or name in AMBIGUOUS_PATH_FLAGS
        if tracked and equals:
            if _should_rewrite(name, inline, root):
                out.append(f"{name}={_absolute(inline, root)}")
            else:
                out.append(token)
            index += 1
            continue
        if tracked and index + 1 < limit:
            value = argv[index + 1]
            out.append(token)
            if _should_rewrite(name, value, root):
                out.append(_absolute(value, root))
            else:
                out.append(value)
            index += 2
            continue
        out.append(token)
        index += 1
    return out
