"""Lock positive lines the prompt compiler writes into each frame prompt (0.27.6).

A structured lock with a ``positive`` line is restated in every frame it applies
to. Lines follow the lock's ``scope`` and ``views`` with the hold gate's
``scoped_out`` rule (0.27.14). A lock with a ``character`` applies only where that
character is cast, the same rule the lock carrier table uses. Then
``LOCK_POSITIVE_NOT_IN_PROMPT`` only fires when a later edit drops the line.

0.27.14: ``lock_negative_lines`` writes each lock's ``negative`` line the same way,
right after the positive lines, so the pre-spend phrase check finds every critical
line in the compiled prompt.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from kubrick.gates.hold_scope import frame_view, scoped_out
from kubrick.prompts.reference_lint import screen_mode


def _applies(frame: Mapping[str, object], character: str | None) -> bool:
    if not character:
        return True
    mode, present = screen_mode(frame)
    if not present and mode == "absent":
        return True
    return character in present


def lock_applies(
    document: Mapping[str, object],
    frame: Mapping[str, object],
    lock: Mapping[str, object],
) -> bool:
    """Return whether the lock applies to this frame under the hold gate scope."""
    character = lock.get("character")
    owner = character.strip() if isinstance(character, str) and character.strip() else None
    if not _applies(frame, owner):
        return False

    from kubrick.gates.jev_holds import _labels, shot_location

    frames = document.get("frames")
    rows = frames if isinstance(frames, list) else []
    index = next((n for n, item in enumerate(rows, start=1) if item is frame), 0)
    labels = _labels(frame, index) if index else {
        str(frame.get(key)).strip() for key in ("frame_id", "shot_id")
        if isinstance(frame.get(key), str) and str(frame.get(key)).strip()
    }

    _, present = screen_mode(frame)
    characters = set(present) if present else set()

    location = shot_location(document, frame)
    view = frame_view(frame) or ""
    return not scoped_out(lock, location, labels, characters, view)


def lock_positive_lines(
    document: Mapping[str, object], frame: Mapping[str, object],
) -> list[str]:
    """Positive lines of the locks that apply to this frame, in plan order, once each."""
    locks = document.get("locks")
    if not isinstance(locks, Sequence) or isinstance(locks, (str, bytes)):
        return []
    seen: set[str] = set()
    lines: list[str] = []
    for lock in locks:
        if not isinstance(lock, Mapping):
            continue
        if not lock_applies(document, frame, lock):
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
    seen: set[str] = set()
    lines: list[str] = []
    for lock in locks:
        if not isinstance(lock, Mapping):
            continue
        if not lock_applies(document, frame, lock):
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
