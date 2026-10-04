"""Repository roots that do not depend on a module's package depth."""
from __future__ import annotations

import re
from pathlib import Path

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
