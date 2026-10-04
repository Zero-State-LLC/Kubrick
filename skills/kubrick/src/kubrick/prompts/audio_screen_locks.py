#!/usr/bin/env python3
"""Voice locks, dialogue length, asymmetry, and screen direction.

Issues #43 and #44. A speech line belongs to a character when it is a mapping
``{character, line}`` or a string that starts with ``"{id}:"``. Words are the
whitespace-separated tokens after that prefix. ``DIALOGUE_TOO_LONG`` fires
when words per planned second is greater than 2.5. ``speaks: false`` with any
attributed line, and a voice id equal to a ``never_clone_of`` entry, fail
closed. Comparison is full-string casefold. Figure-right is viewer-left.
``axis_change`` counts only as boolean true. ``mirrored`` counts only as
boolean true.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from kubrick.plan.continuity_locks import frame_field, frame_id, warning
from kubrick.prompts.reference_lint import screen_mode

_RATE = 2.5
_SIDES = {"left", "right"}


def guide_sound(sound: str, strategy: object) -> str:
    """Note that native audio is a guide when the strategy is external or muted."""
    if strategy not in {"external", "muted_native"}:
        return sound
    note = "native audio is a guide track only"
    if note in sound:
        return sound
    return f"{sound}; {note}"


def _table(document: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    raw = document.get("characters")
    if not isinstance(raw, Mapping):
        return {}
    return {str(key): value for key, value in raw.items() if isinstance(value, Mapping)}


def _voice(spec: Mapping[str, object]) -> Mapping[str, object]:
    raw = spec.get("voice")
    if isinstance(raw, Mapping):
        return raw
    return {}


def _lines(frame: Mapping[str, object]) -> list[object]:
    found: list[object] = []
    for key in ("speech_lines", "dialogue", "lines"):
        raw = frame_field(frame, key)
        if isinstance(raw, str) and raw.strip():
            found.append(raw.strip())
        elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            found.extend(raw)
    return found


def _spoken(line: object, character: str) -> str | None:
    """Return the spoken text when the line is this character's, else None."""
    if isinstance(line, Mapping):
        who = str(line.get("character") or line.get("speaker") or "")
        if who.casefold() != character.casefold():
            return None
        text = line.get("line")
        if text is None:
            text = line.get("text")
        return str(text or "").strip()
    if not isinstance(line, str):
        return None
    prefix = f"{character}:"
    stripped = line.strip()
    if not stripped.casefold().startswith(prefix.casefold()):
        return None
    return stripped[len(prefix):].strip()


def _words(text: str) -> int:
    return len([token for token in text.split() if token])


def _seconds(frame: Mapping[str, object]) -> float | None:
    value = frame_field(frame, "duration_seconds")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _voice_errors(
    document: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
) -> list[str]:
    errors: list[str] = []
    for name, spec in _table(document).items():
        voice = _voice(spec)
        errors.extend(_speech_lock(name, voice, frames))
        errors.extend(_clone_lock(name, voice, frames))
    return errors


def _speech_lock(
    name: str,
    voice: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
) -> list[str]:
    if voice.get("speaks") is not False:
        return []
    found: list[str] = []
    for index, frame in enumerate(frames, start=1):
        shot = frame_id(frame, index)
        for line in _lines(frame):
            if _spoken(line, name) is None:
                continue
            found.append(
                f"VOICE_LOCK_VIOLATION: {name} on {shot} has speaks false and a speech line"
            )
            break
    return found


def _clone_lock(
    name: str,
    voice: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
) -> list[str]:
    banned = {item.casefold() for item in _string_list(voice.get("never_clone_of"))}
    matched = [item for item in _voice_idents(voice) if item.casefold() in banned]
    if not matched:
        return []
    shot = _home_frame(name, frames)
    where = f" on {shot}" if shot else ""
    return [
        f"VOICE_LOCK_VIOLATION: {name}{where} voice {matched[0]} matches never_clone_of"
    ]


def _voice_idents(voice: Mapping[str, object]) -> list[str]:
    found: list[str] = []
    for key in ("library_id", "name"):
        value = voice.get(key)
        if isinstance(value, str) and value.strip():
            found.append(value.strip())
    return found


def _home_frame(name: str, frames: Sequence[Mapping[str, object]]) -> str | None:
    for index, frame in enumerate(frames, start=1):
        _mode, present = screen_mode(frame)
        if name in present:
            return frame_id(frame, index)
    if frames:
        return frame_id(frames[0], 1)
    return None


def _string_list(value: object) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dialogue_warnings(
    document: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
) -> list[dict[str, str | None]]:
    found: list[dict[str, str | None]] = []
    for name, spec in _table(document).items():
        voice = _voice(spec)
        limit = voice.get("max_words")
        cap = limit if isinstance(limit, int) and not isinstance(limit, bool) else None
        for index, frame in enumerate(frames, start=1):
            found.extend(_too_long(name, frame, index, cap))
    return found


def _too_long(
    name: str,
    frame: Mapping[str, object],
    index: int,
    cap: int | None,
) -> list[dict[str, str | None]]:
    shot = frame_id(frame, index)
    found: list[dict[str, str | None]] = []
    for line in _lines(frame):
        spoken = _spoken(line, name)
        if spoken is None:
            continue
        count = _words(spoken)
        seconds = _seconds(frame)
        if _over_rate(count, seconds) or (cap is not None and count > cap):
            found.append(_length_warning(name, shot, count, seconds))
    return found


def _over_rate(count: int, seconds: float | None) -> bool:
    if count <= 0 or seconds is None:
        return False
    if seconds <= 0:
        return True
    return count / seconds > _RATE


def _length_warning(
    name: str,
    shot: str,
    count: int,
    seconds: float | None,
) -> dict[str, str | None]:
    shown = "a missing duration" if seconds is None else f"{seconds}s"
    return warning(
        "DIALOGUE_TOO_LONG",
        shot,
        f"{name} on {shot} has {count} words in {shown}, above 2.5 words per second",
        "shorten the line or lengthen the beat",
        character=name,
    )


def asymmetry_lines(document: Mapping[str, object], frame: Mapping[str, object]) -> list[str]:
    """One positive line per on-screen asymmetric feature. Empty cast drops them."""
    mode, present = screen_mode(frame)
    if mode == "cast" and not present:
        return []
    if mode == "absent":
        return []
    lines: list[str] = []
    for name in present:
        spec = _table(document).get(name)
        if spec is None:
            continue
        lines.extend(_feature_lines(spec.get("asymmetry")))
    return lines


def _feature_lines(raw: object) -> list[str]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    lines: list[str] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        feature = item.get("feature")
        side = item.get("figure_side")
        if not isinstance(feature, str) or not feature.strip() or side not in _SIDES:
            continue
        viewer = "left" if side == "right" else "right"
        lines.append(
            f"{feature.strip()} on the figure's {side} (viewer's {viewer}); never swap sides"
        )
    return lines


def _screen_warnings(frames: Sequence[Mapping[str, object]]) -> list[dict[str, str | None]]:
    found: list[dict[str, str | None]] = []
    previous: Mapping[str, object] | None = None
    previous_id: str | None = None
    for index, frame in enumerate(frames, start=1):
        shot = frame_id(frame, index)
        if previous is not None and previous_id is not None:
            found.extend(_flips(previous, previous_id, frame, shot))
        previous, previous_id = frame, shot
    return found


def _side_map(frame: Mapping[str, object]) -> dict[str, str]:
    raw = frame_field(frame, "screen_side")
    if not isinstance(raw, Mapping):
        return {}
    return {str(key): str(value) for key, value in raw.items()}


def _flips(
    earlier: Mapping[str, object],
    earlier_id: str,
    later: Mapping[str, object],
    later_id: str,
) -> list[dict[str, str | None]]:
    if later.get("axis_change") is True or frame_field(later, "axis_change") is True:
        return []
    found: list[dict[str, str | None]] = []
    before, after = _side_map(earlier), _side_map(later)
    for name, side in before.items():
        other = after.get(name)
        if side not in _SIDES or other not in _SIDES or side == other:
            continue
        found.append(warning(
            "SCREEN_DIRECTION_FLIP",
            later_id,
            (
                f"{name} screen side flips from {side} on {earlier_id} "
                f"to {other} on {later_id}"
            ),
            "set axis_change true on the later frame or keep the side",
            character=name,
        ))
    return found


def _mirror_warnings(document: Mapping[str, object]) -> list[dict[str, str | None]]:
    found: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for ident in _mirrored_ids(document):
        if ident in seen:
            continue
        seen.add(ident)
        found.append(warning(
            "MIRRORED_REFERENCE",
            None,
            f"reference {ident} is mirrored; sides in the image are inverted",
            "treat the sides as swapped in this image, or supply an unmirrored reference",
        ))
    return found


def _mirrored_ids(document: Mapping[str, object]) -> list[str]:
    found: list[str] = []
    for spec in _table(document).values():
        found.extend(_mirrored_list(spec.get("references")))
    location = document.get("location")
    if isinstance(location, Mapping):
        found.extend(_mirrored_list(location.get("references")))
    found.extend(_mirrored_list(document.get("references")))
    return found


def _mirrored_list(raw: object) -> list[str]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    found: list[str] = []
    for ref in raw:
        if not isinstance(ref, Mapping) or ref.get("mirrored") is not True:
            continue
        ident = _ref_id(ref)
        found.append(ident)
    return found


def _ref_id(ref: Mapping[str, object]) -> str:
    for key in ("path", "mediaObjectId", "id"):
        value = ref.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "reference"


def lint(
    document: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
) -> tuple[list[dict[str, str | None]], list[str]]:
    """Warnings and fail-closed voice errors. Voice errors are prep errors."""
    warnings = [
        *_dialogue_warnings(document, frames),
        *_screen_warnings(frames),
        *_mirror_warnings(document),
    ]
    return warnings, _voice_errors(document, frames)
