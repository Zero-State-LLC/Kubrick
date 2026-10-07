"""On a first-person (POV) shot the camera is the character, so lock lines about that
character's appearance are skipped; lines about what they hold or do stay.
"""

from __future__ import annotations

from collections.abc import Mapping

ASPECTS = frozenset({"appearance", "action"})


def lock_aspect(lock: Mapping[str, object]) -> str:
    """Return the lock aspect, defaulting from kind."""
    raw_aspect = lock.get("aspect")
    if isinstance(raw_aspect, str):
        aspect = raw_aspect.strip().casefold()
        if aspect in ASPECTS:
            return aspect

    raw_kind = lock.get("kind")
    if isinstance(raw_kind, str):
        kind = raw_kind.strip().casefold()
        if kind in {"identity", "wardrobe"}:
            return "appearance"

    return "action"


def pov_skips(lock: Mapping[str, object], view: str | None) -> bool:
    """Return True when a POV view skips an appearance lock."""
    if view is None:
        return False
    if view.strip().casefold() != "pov":
        return False

    character = lock.get("character")
    if not isinstance(character, str) or not character.strip():
        return False

    return lock_aspect(lock) == "appearance"
