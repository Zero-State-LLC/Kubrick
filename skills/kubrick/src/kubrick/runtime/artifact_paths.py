#!/usr/bin/env python3
"""Project-local artifact directories for Kubrick runtime outputs.

Runtime artifacts (retrieval caches, receipts, logs) live under
``<project_root>/out/kubrick/...`` and never inside protected skill trees.
Any failure to create or write those locations fails closed with a structured
``ARTIFACT_DIR_UNWRITABLE`` diagnostic (status NOT_COMPUTABLE, exit code 4).
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import NoReturn

import kubrick.runtime.diagnostics as diagnostics
import kubrick.runtime.io_safety as io_safety


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _protected_skill_location(path: Path) -> bool:
    skill = io_safety.SKILL_ROOT
    if not _is_within(path, skill):
        return False
    return not _is_within(path, skill / "out")


def _unwritable(path: Path, error: str) -> NoReturn:
    diagnostics.abort(
        diagnostics.diagnostic(
            status="NOT_COMPUTABLE",
            code="ARTIFACT_DIR_UNWRITABLE",
            exit_code=4,
            message="Kubrick artifact location is not writable; refusing to continue",
            context={"path": str(path), "error": error},
        ),
        stream=sys.stderr,
    )
    raise SystemExit(4)


def _artifact_root() -> Path:
    """KUBRICK_PROJECT_DIR, else the dispatcher caller's cwd, else this process's cwd."""
    if os.environ.get("KUBRICK_PROJECT_DIR", "").strip():
        return io_safety.project_root()
    caller = os.environ.get("KUBRICK_CALLER_CWD", "").strip()
    if caller:
        return Path(caller).expanduser().resolve()
    return io_safety.project_root()


def kubrick_out_dir(*parts: str) -> Path:
    """Return (and create) ``project_root()/out/kubrick/<parts>``, verified writable."""
    base = _artifact_root() / "out" / "kubrick"
    path = base.joinpath(*parts).resolve()
    if not _is_within(path, base.resolve()):
        _unwritable(path, "artifact path escapes out/kubrick")
    if _protected_skill_location(path):
        _unwritable(path, "artifact path lands inside a protected skill tree")
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, prefix=".kubrick-probe-"):
            pass
    except OSError as exc:
        _unwritable(path, str(exc))
    return path


def write_json_artifact(directory: Path, name: str, payload: str) -> Path:
    """Write ``payload`` to ``directory/name`` via the bounded writer."""
    path = directory / name
    if Path(name).name != name or name in {"", ".", ".."}:
        _unwritable(path, "artifact name must be a bare file name")
    try:
        return io_safety.write_text_bounded(path, payload)
    except (OSError, io_safety.PathSafetyError) as exc:
        _unwritable(path, str(exc))
