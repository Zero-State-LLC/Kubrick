#!/usr/bin/env python3
"""Take selection by --take override, ``selected: true``, or a single take. Issue #64."""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from continuity_locks import warning


def parse_take_overrides(values: Sequence[str] | None) -> dict[str, str]:
    """Parse ``<shot>=<take_id>`` values; raise ValueError on bad or conflicting input."""
    found: dict[str, str] = {}
    for value in values or []:
        shot, sep, wanted = value.partition("=")
        shot, wanted = shot.strip(), wanted.strip()
        if not sep or not shot or not wanted:
            raise ValueError(f"--take expects <shot>=<take_id>, got {value!r}")
        if shot in found and found[shot] != wanted:
            raise ValueError(f"--take gives shot {shot} two takes: {found[shot]}, {wanted}")
        found[shot] = wanted
    return found


def unknown_override(
    overrides: Mapping[str, str], known: set[str]
) -> dict[str, str | None] | None:
    """TAKE_NOT_FOUND when a --take shot key names no storyboard frame."""
    unknown = sorted(key for key in overrides if key not in known)
    if not unknown:
        return None
    return warning(
        "TAKE_NOT_FOUND",
        unknown[0],
        f"--take names shot(s) not on the storyboard: {', '.join(unknown)}",
        "use a frame_id or shot_id from the storyboard",
    )


def take_id(take: Mapping[str, object]) -> str | None:
    raw = take.get("take_id")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _ambiguous(shot: str, message: str) -> dict[str, str | None]:
    return warning(
        "TAKE_AMBIGUOUS", shot, message, "set selected true on exactly one take for this shot"
    )


def select_take(
    matches: Sequence[Mapping[str, object]],
    labels: set[str],
    shot: str,
    overrides: Mapping[str, str],
) -> tuple[Mapping[str, object] | None, dict[str, str | None] | None]:
    """Pick one take or return a TAKE_NOT_FOUND / TAKE_AMBIGUOUS warning."""
    for label in sorted(labels):
        if label in overrides:
            wanted = overrides[label]
            for take in matches:
                if take_id(take) == wanted:
                    return take, None
            return None, warning(
                "TAKE_NOT_FOUND",
                shot,
                f"shot {shot} has no take {wanted}",
                "check --take against take_id values in takes.yaml",
            )
    selected = [take for take in matches if take.get("selected") is True]
    if len(selected) > 1:
        return None, _ambiguous(shot, f"shot {shot} has {len(selected)} takes marked selected")
    if len(selected) == 1:
        return selected[0], None
    if not matches:
        return None, None
    if len(matches) == 1:
        return matches[0], None
    return None, _ambiguous(shot, f"shot {shot} has several takes and none is selected")
