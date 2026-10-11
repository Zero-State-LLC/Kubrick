"""Repository roots that do not depend on a module's package depth."""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path, PureWindowsPath

SKILL_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = SKILL_ROOT / "scripts"

_IMPL = re.compile(r"^\s*import (kubrick(?:\.\w+)+) as _impl\b", re.MULTILINE)


def implementation_of(script: Path) -> Path:
    """Return the package file a ``scripts/`` entry loads, or the file itself.

    ``script`` is resolved from its own parent, so a copied tree hashes the
    copy rather than this checkout.
    """
    if not script.is_file():
        return script
    match = _IMPL.search(script.read_text(encoding="utf-8"))
    if match is None:
        return script
    relative = Path("src", *match.group(1).split(".")).with_suffix(".py")
    return script.parent.parent / relative


def telemetry_state_dir(
    *,
    platform: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the sole per-user location allowed for telemetry consent/queue state."""
    current_platform = platform or sys.platform
    env = os.environ if environ is None else environ
    home_dir = Path.home() if home is None else home

    if current_platform == "win32":
        configured = env.get("LOCALAPPDATA", "").strip()
        if configured and (
            Path(configured).is_absolute() or PureWindowsPath(configured).is_absolute()
        ):
            root = Path(configured)
        else:
            root = home_dir / "AppData" / "Local"
        return root / "Kubrick" / "telemetry"

    if current_platform == "darwin":
        return home_dir / "Library" / "Application Support" / "Kubrick" / "telemetry"

    configured = env.get("XDG_STATE_HOME", "").strip()
    root = (
        Path(configured)
        if configured and Path(configured).is_absolute()
        else home_dir / ".local" / "state"
    )
    return root / "kubrick" / "telemetry"
