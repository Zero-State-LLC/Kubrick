"""Lock positive lines the prompt compiler writes into each frame prompt (0.27.6).

A structured lock with a ``positive`` line is restated in every frame it applies
to. A lock with a ``character`` applies only where that character is cast, the
same rule the lock carrier table uses. Then ``LOCK_POSITIVE_NOT_IN_PROMPT`` only
fires when a later edit drops the line.

0.27.14: ``lock_negative_lines`` writes each lock's ``negative`` line the same way,
right after the positive lines, so the pre-spend phrase check finds every critical
line in the compiled prompt.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from kubrick.gates.hold_scope import frame_view
from kubrick.plan.lock_aspect import pov_skips
from kubrick.prompts.reference_lint import screen_mode


def _applies(frame: Mapping[str, object], character: str | None) -> bool:
    if not character:
        return True
    mode, present = screen_mode(frame)
    if not present and mode == "absent":
        return True
    return character in present


def lock_positive_lines(
    document: Mapping[str, object], frame: Mapping[str, object],
) -> list[str]:
    """Positive lines of the locks that apply to this frame, in plan order, once each."""
    locks = document.get("locks")
    if not isinstance(locks, Sequence) or isinstance(locks, (str, bytes)):
        return []
    view = frame_view(frame)
    seen: set[str] = set()
    lines: list[str] = []
    for lock in locks:
        if not isinstance(lock, Mapping):
            continue
        character = lock.get("character")
        owner = character.strip() if isinstance(character, str) and character.strip() else None
        if not _applies(frame, owner) or pov_skips(lock, view):
            continue
        positive = lock.get("positive")
        if not isinstance(positive, str) or not positive.strip():
            continue
        line = " ".join(positive.split())
        key = line.casefold()
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)
    return lines


def lock_negative_lines(
    document: Mapping[str, object], frame: Mapping[str, object],
) -> list[str]:
    """Negative lines of the locks that apply to this frame, in plan order, once each (0.27.14)."""
    locks = document.get("locks")
    if not isinstance(locks, Sequence) or isinstance(locks, (str, bytes)):
        return []
    view = frame_view(frame)
    seen: set[str] = set()
    lines: list[str] = []
    for lock in locks:
        if not isinstance(lock, Mapping):
            continue
        character = lock.get("character")
        owner = character.strip() if isinstance(character, str) and character.strip() else None
        if not _applies(frame, owner) or pov_skips(lock, view):
            continue
        negative = lock.get("negative")
        if not isinstance(negative, str) or not negative.strip():
            continue
        line = " ".join(negative.split())
        key = line.casefold()
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)
    return lines


def plan_lock_negatives(document: Mapping[str, object]) -> list[str]:
    """Every plan lock ``negative`` line; the gate lint does not call them conflicts (0.27.14)."""
    raw = document.get("locks")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    found: list[str] = []
    for lock in raw:
        if isinstance(lock, Mapping):
            negative = lock.get("negative")
            if isinstance(negative, str) and negative.strip():
                found.append(negative.strip())
    return found
