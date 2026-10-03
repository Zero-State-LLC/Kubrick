#!/usr/bin/env python3
"""Plan-field matchers for known drift and technique triggers. Issue #79.

A missing camera block, an angle without a number, or a keep list we cannot
resolve does not match. Outputs that use these hits stay warnings.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence

from continuity_locks import frame_field, frame_id, warning

_CLOSE_TEXT = re.compile(
    r"\b(?:ecu|xcu|extreme\s+close[\s-]?up|close[\s-]?up|closeup)\b",
    re.IGNORECASE,
)
_CLOSE_SIZES = {
    "ecu", "xcu", "cu", "close", "close up", "closeup", "extreme close up",
}
_DEGREES = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:degrees|degree|°)",
    re.IGNORECASE,
)
_DIM = re.compile(r"\bdim\b", re.IGNORECASE)
_PRACTICAL = re.compile(r"\bpracticals?\b", re.IGNORECASE)
_STARTLE = re.compile(
    r"\b(?:startles?|startled|startling|jumps?|jumped|jumping)\b",
    re.IGNORECASE,
)
_SNAP = re.compile(
    r"\b(?:snap[\s-]?pan|whip[\s-]?pan|snaps?|whips?|whipped|whipping)\b",
    re.IGNORECASE,
)
# Action prose needs camera context: "the twig snaps" is not a snap pan.
_SNAP_MOVE = re.compile(
    r"\b(?:snap|whip)(?:s|ped|ping)?[\s-]?(?:pans?|panned|panning|tilts?|zooms?)\b"
    r"|\bcamera\s+(?:snaps?|whips?|snapped|whipped)\b",
    re.IGNORECASE,
)
_FLICKER_WORD = re.compile(
    r"\b(?:flicker|flickers|flickering|black[\s-]?out)\b",
    re.IGNORECASE,
)
_PEAK = re.compile(
    r"\b(?:sound|bass|audio)\s+peaks?\b",
    re.IGNORECASE,
)
_HEARD_NOT_SHOWN = re.compile(
    r"\bheard,?\s+not\s+(?:seen|shown)\b",
    re.IGNORECASE,
)
_OFFSCREEN = re.compile(r"\boff[\s-]?screen\b", re.IGNORECASE)
_HEARD = re.compile(r"\b(?:heard|sounding)\b", re.IGNORECASE)
_PEAK_TOKENS = {"sound peak", "bass peak", "audio peak", "peak"}
Hit = tuple[int, str | None]


def _strings(value: object) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _blob(frame: Mapping[str, object]) -> str:
    parts: list[str] = []
    for key in ("action", "prompt"):
        value = frame_field(frame, key)
        if isinstance(value, str) and value.strip():
            parts.append(value)
    return " ".join(parts)


def _mapping(frame: Mapping[str, object], key: str) -> Mapping[str, object] | None:
    raw = frame_field(frame, key)
    if isinstance(raw, Mapping):
        return raw
    return None


def _norm_size(value: str) -> str:
    return " ".join(value.casefold().replace("_", " ").replace("-", " ").split())


def _flatten(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        found: list[str] = []
        for item in value.values():
            found.extend(_flatten(item))
        return found
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        found = []
        for item in value:
            found.extend(_flatten(item))
        return found
    return []


def _chain_source(frame: Mapping[str, object]) -> str | None:
    raw = frame_field(frame, "join")
    if isinstance(raw, Mapping):
        source = raw.get("chain_from")
        if isinstance(source, str) and source.strip():
            return source.strip()
    return None


def _names(frame: Mapping[str, object] | None) -> list[str] | None:
    if frame is None:
        return None
    raw = frame_field(frame, "characters")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return None
    return [str(item).strip() for item in raw if str(item).strip()]


def _prior(source: str, frames: Sequence[Mapping[str, object]]) -> Mapping[str, object] | None:
    for index, item in enumerate(frames, start=1):
        if frame_id(item, index) == source:
            return item
    return None


def _removes(frame: Mapping[str, object], frames: Sequence[Mapping[str, object]]) -> bool:
    source = _chain_source(frame)
    current = _names(frame)
    if source is None or current is None:
        return False
    before = _names(_prior(source, frames))
    if not before:
        return False
    return len(current) < len(before) or bool(set(before) - set(current))


def _verb(text: str, verbs: Sequence[object]) -> bool:
    folded = text.casefold()
    for verb in verbs:
        token = str(verb).casefold().strip()
        if token and re.search(rf"\b{re.escape(token)}\b", folded):
            return True
    return False


def _close_size(frame: Mapping[str, object]) -> bool:
    camera = _mapping(frame, "camera")
    if camera is None:
        return False
    size = camera.get("size")
    if not isinstance(size, str) or not size.strip():
        return False
    token = _norm_size(size)
    if token in _CLOSE_SIZES:
        return True
    return "close up" in token or "extreme close" in token


def _close_framing(frame: Mapping[str, object]) -> bool:
    if _CLOSE_TEXT.search(_blob(frame)):
        return True
    return _close_size(frame)


def _dim_practical(frame: Mapping[str, object]) -> bool:
    text = " ".join(_flatten(frame_field(frame, "light_states")))
    return _DIM.search(text) is not None and _PRACTICAL.search(text) is not None


def _startle(frame: Mapping[str, object]) -> bool:
    action = frame_field(frame, "action")
    text = action if isinstance(action, str) else ""
    return _STARTLE.search(text) is not None


def _snap_text(value: object, pattern: re.Pattern[str] = _SNAP) -> bool:
    return isinstance(value, str) and pattern.search(value) is not None


def _snap_whip(frame: Mapping[str, object]) -> bool:
    if _snap_text(frame_field(frame, "action"), _SNAP_MOVE):
        return True
    camera = _mapping(frame, "camera")
    if camera is None:
        return False
    return _snap_text(camera.get("move"))


def _chained_snap(frame: Mapping[str, object]) -> bool:
    return _chain_source(frame) is not None and _snap_whip(frame)


def _explicit_flicker(frame: Mapping[str, object]) -> bool:
    if _FLICKER_WORD.search(_blob(frame)):
        return True
    applied = _strings(frame_field(frame, "apply_techniques"))
    for item in applied:
        folded = item.casefold()
        if "flicker" in folded or "blackout" in folded or "black-out" in folded:
            return True
    return False


def _keep_names(
    frame: Mapping[str, object], document: Mapping[str, object] | None,
) -> list[str]:
    found: list[str] = []
    found.extend(_strings(frame_field(frame, "keep")))
    if isinstance(document, Mapping):
        found.extend(_strings(document.get("keep")))
    ordered: list[str] = []
    for name in found:
        if name not in ordered:
            ordered.append(name)
    return ordered


def cleared_keep_names(
    frame: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
    document: Mapping[str, object] | None,
) -> list[str]:
    """Kept names a flicker would drop. Unknown casts yield nothing."""
    keep = _keep_names(frame, document)
    if not keep or not _explicit_flicker(frame):  # a cast cut alone is not a flicker
        return []
    current = _names(frame)
    if current is None:
        return []
    source = _chain_source(frame)
    before = _names(_prior(source, frames)) if source is not None else None
    if before is not None:
        gone = set(before) - set(current)
        return [name for name in keep if name in gone]
    return [name for name in keep if name not in current]


def _frame_hits(
    frames: Sequence[Mapping[str, object]],
    predicate: Callable[[Mapping[str, object]], bool],
) -> list[Hit]:
    return [(index, None) for index, frame in enumerate(frames) if predicate(frame)]


def _flicker_hits(
    document: Mapping[str, object], frames: Sequence[Mapping[str, object]],
) -> list[Hit]:
    found: list[Hit] = []
    for index, frame in enumerate(frames):
        for name in cleared_keep_names(frame, frames, document):
            found.append((index, name))
    return found


_FINDERS = {
    "close_framing": lambda _document, frames: _frame_hits(frames, _close_framing),
    "dim_practical": lambda _document, frames: _frame_hits(frames, _dim_practical),
    "startle_action": lambda _document, frames: _frame_hits(frames, _startle),
    "chained_snap": lambda _document, frames: _frame_hits(frames, _chained_snap),
    "flicker_keep": _flicker_hits,
}


def extended_drift_hits(
    kind: str,
    document: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
) -> list[Hit] | None:
    """Frame hits for an extended drift kind. None when the kind is older."""
    finder = _FINDERS.get(kind)
    if finder is None:
        return None
    return finder(document, frames)


def _peak_token(value: str) -> bool:
    token = " ".join(value.casefold().replace("_", " ").replace("-", " ").split())
    return token in _PEAK_TOKENS


def _sound_peak(frame: Mapping[str, object]) -> bool:
    if _PEAK.search(_blob(frame)):
        return True
    raw = frame_field(frame, "cut")
    if isinstance(raw, str):
        return _peak_token(raw)
    if not isinstance(raw, Mapping):
        return False
    for key in ("on", "sync", "at", "cue"):
        value = raw.get(key)
        if isinstance(value, str) and _peak_token(value):
            return True
    return False


def _as_degrees(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return float(text)
    found = _DEGREES.search(text)
    if found:
        return float(found.group(1))
    return None


def _angle_degrees(frame: Mapping[str, object]) -> float | None:
    camera = _mapping(frame, "camera")
    if camera is not None:
        for key in ("angle", "angle_degrees", "degrees", "angle_delta"):
            parsed = _as_degrees(camera.get(key))
            if parsed is not None:
                return parsed
    found = _DEGREES.search(_blob(frame))
    if found:
        return float(found.group(1))
    return None


def _resolved_index(
    frame: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
    index: int | None,
) -> int:
    if index is not None:
        return index
    for found, item in enumerate(frames):
        if item is frame:
            return found
    return 0


def _join_is_cut(frame: Mapping[str, object]) -> bool:
    raw = frame_field(frame, "join")
    if raw is None:
        return True
    return isinstance(raw, str) and raw.strip().casefold() == "cut"


def _after_cut(
    frame: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
    index: int | None,
) -> bool:
    if _resolved_index(frame, frames, index) <= 0:
        return False
    if _chain_source(frame) is not None:
        return False
    return _join_is_cut(frame)


def _offscreen_bits(frame: Mapping[str, object]) -> list[str]:
    """Action, prompt clauses, and state strings. Separate bits stay separate."""
    bits = [part.strip() for part in _blob(frame).split(";") if part.strip()]
    for key in ("node_states", "object_states"):
        raw = frame_field(frame, key)
        if isinstance(raw, Mapping):
            bits.extend(value.strip() for value in _flatten(raw) if value.strip())
    return bits


def _offscreen_event(frame: Mapping[str, object]) -> bool:
    for text in _offscreen_bits(frame):
        if _HEARD_NOT_SHOWN.search(text):
            return True
        if _OFFSCREEN.search(text) and _HEARD.search(text):
            return True
    return False


def _flag_ok(triggers: Mapping[str, object], key: str, actual: bool) -> bool:
    if key not in triggers:
        return True
    return bool(triggers.get(key)) == actual


def _angle_ok(
    triggers: Mapping[str, object],
    frame: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
    index: int | None,
) -> bool:
    if "min_angle_degrees" not in triggers:
        return True
    minimum = triggers.get("min_angle_degrees")
    if isinstance(minimum, bool) or not isinstance(minimum, (int, float)):
        return False
    angle = _angle_degrees(frame)
    if angle is None or angle < float(minimum):
        return False
    return _after_cut(frame, frames, index)


def _extended_ok(
    triggers: Mapping[str, object],
    frame: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
    document: Mapping[str, object] | None,
    index: int | None,
) -> bool:
    flicker = _explicit_flicker(frame)
    checks = (
        _flag_ok(triggers, "flicker_clear", flicker),
        _flag_ok(triggers, "keep_list", bool(_keep_names(frame, document))),
        _flag_ok(triggers, "sound_peak", _sound_peak(frame)),
        _flag_ok(triggers, "offscreen_event", _offscreen_event(frame)),
        _angle_ok(triggers, frame, frames, index),
    )
    return all(checks)


def _legacy_ok(
    triggers: Mapping[str, object],
    frame: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
) -> bool:
    chained = _chain_source(frame) is not None
    if "chained" in triggers and bool(triggers.get("chained")) != chained:
        return False
    fewer = triggers.get("fewer_characters_than_start")
    if fewer and not _removes(frame, frames):
        return False
    verbs = triggers.get("motion_verbs")
    if isinstance(verbs, Sequence) and not isinstance(verbs, (str, bytes)) and verbs:
        return _verb(_blob(frame), verbs)
    return True


def technique_matches(
    technique: Mapping[str, object],
    frame: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
    provider: str,
    document: Mapping[str, object] | None = None,
    index: int | None = None,
) -> bool:
    """True when provider, legacy triggers, and extended triggers all hold."""
    providers = technique.get("providers")
    if isinstance(providers, Sequence) and not isinstance(providers, (str, bytes)):
        if provider not in {str(item) for item in providers}:
            return False
    triggers = technique.get("triggers")
    if not isinstance(triggers, Mapping):
        return False
    if not _legacy_ok(triggers, frame, frames):
        return False
    return _extended_ok(triggers, frame, frames, document, index)


def keep_clear_warnings(
    document: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
) -> list[dict[str, str | None]]:
    """Warn when a flicker would clear a name on a frame or document keep list."""
    found: list[dict[str, str | None]] = []
    for index, frame in enumerate(frames):
        shot = frame_id(frame, index + 1)
        for name in cleared_keep_names(frame, frames, document):
            found.append(warning(
                "FLICKER_CLEARS_KEEP",
                shot,
                (
                    f"{name} on {shot} is on the keep list and a flicker "
                    "would clear that figure"
                ),
                f"leave {name} in the frame or remove {name} from the keep list",
                character=name,
            ))
    return found
