#!/usr/bin/env python3
"""Bounded filesystem and structured-intake helpers for Kubrick.

Stdlib-only. Used by CLI tools and the optional MCP surface to:
- contain path reads/writes under a project root (and skill root for reads)
- refuse writes into protected skill trees (references/, schemas/, scripts/, …)
- bound YAML/JSON intake by byte size before parse
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from kubrick.paths import SKILL_ROOT

DEFAULT_MAX_BYTES = 2_000_000
PATH_FLAG_NAMES = frozenset(
    {
        "--brief",
        "--ledger",
        "--out",
        "--output",
        "--write-ledger",
        "--write_ledger",
        "--packet",
        "--graph",
        "--plan",
        "--storyboard",
        "--storyboard-plan",
        "--expected",
        "--observation-input",
        "--observation",
        "--input",
        "--jev-verdicts",
        "--board-judge-answers",
        "--evidence",
        "--artifact",
        "--schema",
        "--receipt",
        "--receipt-output",
        "--bundle",
        "--root",
        "--run-ledger",
        "--project",
        "--design",
        "--script",
        "--source",
        "--report",
        "--state",
        "--grok-packet",
        "--expected-state",
        "--takes",
        "--answers",
    }
)
FLAG_RE = re.compile(r"^--[a-z][a-z0-9-]*$")
PROTECTED_WRITE_PREFIXES = (
    "references",
    "schemas",
    "scripts",
    "skills",
    "evals",
    ".git",
    ".github",
    "assets",
)


class PathSafetyError(ValueError):
    """Path escapes the allowed roots or targets a protected tree."""

    exit_code = 2


class IntakeError(ValueError):
    """Structured intake exceeds policy or fails to parse."""

    exit_code = 2


def skill_root() -> Path:
    return SKILL_ROOT


def project_root() -> Path:
    """Resolve the active project root.

    Preference order:
    1. ``KUBRICK_PROJECT_DIR``
    2. current working directory
    """
    env = os.environ.get("KUBRICK_PROJECT_DIR", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path.cwd().resolve()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _protected_skill_write(path: Path) -> bool:
    if not _is_relative_to(path, SKILL_ROOT):
        return False
    rel = path.relative_to(SKILL_ROOT).as_posix()
    # Mutable overlays allowed inside the skill tree.
    if rel == "out" or rel.startswith("out/"):
        return False
    for prefix in PROTECTED_WRITE_PREFIXES:
        if rel == prefix or rel.startswith(prefix + "/"):
            return True
    # Block overwriting core skill contract files in-place via operator tools.
    if rel in {
        "SKILL.md",
        "kubrick.manifest.yaml",
        "VERSION",
        "LICENSE",
        "pyproject.toml",
        "install.sh",
        "install.ps1",
    }:
        return True
    return False


def resolve_bounded_path(
    raw: str | Path,
    *,
    for_write: bool = False,
    root: Path | None = None,
    allow_skill_read: bool = True,
    enforce_project: bool | None = None,
) -> Path:
    """Resolve ``raw`` and enforce containment.

    Reads may come from the project root or (when ``allow_skill_read``) the skill
    root — so examples/, schemas/, and references/ remain usable.

    Writes never land in protected skill trees. When ``KUBRICK_PROJECT_DIR`` is set
    (or ``enforce_project=True``, as used by MCP), writes must also stay inside the
    project root or skill ``out/``. Local CLI without a pinned project root remains
    operator-trusted for output locations.
    """
    if raw is None or str(raw).strip() == "":
        raise PathSafetyError("empty path")
    text = str(raw)
    if "\x00" in text:
        raise PathSafetyError("nul byte in path")

    pinned = root is not None or bool(os.environ.get("KUBRICK_PROJECT_DIR", "").strip())
    if enforce_project is None:
        enforce_project = pinned
    proj = (root or project_root()).resolve()
    candidate = Path(text).expanduser()
    if not candidate.is_absolute():
        candidate = (Path.cwd() / candidate).resolve()
    else:
        candidate = candidate.resolve()

    in_project = _is_relative_to(candidate, proj)
    in_skill = _is_relative_to(candidate, SKILL_ROOT)

    if for_write:
        if _protected_skill_write(candidate):
            raise PathSafetyError(
                f"refusing write into protected skill path: {candidate}"
            )
        if enforce_project and not in_project and not (
            in_skill and _is_relative_to(candidate, SKILL_ROOT / "out")
        ):
            raise PathSafetyError(
                f"write path escapes project root {proj}: {candidate}"
            )
        return candidate

    if in_project:
        return candidate
    if allow_skill_read and in_skill:
        return candidate
    if enforce_project:
        raise PathSafetyError(
            f"read path escapes allowed roots ({proj}, skill): {candidate}"
        )
    # Unpinned local CLI: allow absolute reads outside the skill tree.
    return candidate


def load_structured(
    path: str | Path,
    *,
    root: Path | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    for_write: bool = False,
) -> Any:
    """Load JSON or YAML with a byte-size gate. YAML requires PyYAML."""
    resolved = resolve_bounded_path(path, for_write=for_write, root=root)
    size = resolved.stat().st_size
    if size > max_bytes:
        raise IntakeError(
            f"intake exceeds max_bytes ({size} > {max_bytes}): {resolved}"
        )
    text = resolved.read_text(encoding="utf-8")
    if len(text.encode("utf-8")) > max_bytes:
        raise IntakeError(f"intake exceeds max_bytes after decode: {resolved}")
    if resolved.suffix.lower() == ".json":
        data = json.loads(text)
        return data if data is not None else {}
    from kubrick.runtime.runtime_deps import yaml_load

    data = yaml_load(text)
    return data if data is not None else {}


def write_text_bounded(
    path: str | Path,
    text: str,
    *,
    root: Path | None = None,
    encoding: str = "utf-8",
) -> Path:
    resolved = resolve_bounded_path(path, for_write=True, root=root)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(text, encoding=encoding)
    return resolved


def write_structured(
    path: str | Path,
    data: Any,
    *,
    root: Path | None = None,
) -> Path:
    resolved = resolve_bounded_path(path, for_write=True, root=root)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    if resolved.suffix.lower() == ".json":
        resolved.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return resolved
    from kubrick.runtime.runtime_deps import yaml_dump

    resolved.write_text(yaml_dump(data, sort_keys=False), encoding="utf-8")
    return resolved


def validate_mcp_tool_args(
    intent: str,
    action: str | None,
    args: list[Any],
    *,
    intents: dict[str, Any],
    root: Path | None = None,
) -> list[str]:
    """Allowlist MCP ``kubrick_do`` arguments before subprocess dispatch."""
    if intent not in intents:
        raise PathSafetyError(f"unknown intent {intent!r}")
    spec = intents[intent]
    actions = spec.get("actions") or {}
    if action is not None and action not in actions:
        raise PathSafetyError(f"unknown action {action!r} for intent {intent!r}")

    cleaned: list[str] = []
    tokens = [str(a) for a in args]
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.startswith("-"):
            if tok in {"-h", "--help"}:
                raise PathSafetyError("help flags are not allowed via MCP args")
            if not FLAG_RE.match(tok):
                raise PathSafetyError(f"disallowed flag form: {tok!r}")
            cleaned.append(tok)
            # Flags with values: consume next token when present and not a flag
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                value = tokens[i + 1]
                if tok in PATH_FLAG_NAMES:
                    for_write = tok in {
                        "--out",
                        "--output",
                        "--write-ledger",
                        "--write_ledger",
                        "--receipt-output",
                    }
                    resolve_bounded_path(
                        value,
                        for_write=for_write,
                        root=root,
                        enforce_project=True,
                    )
                cleaned.append(value)
                i += 2
                continue
            i += 1
            continue
        # Positional tokens (ledger/operate actions) — tight pattern
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", tok):
            raise PathSafetyError(f"disallowed positional token: {tok!r}")
        cleaned.append(tok)
        i += 1
    return cleaned
