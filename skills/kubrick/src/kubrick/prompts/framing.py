#!/usr/bin/env python3
"""Numeric framing, motion-only video lines, and the Keyframe end-image limit.

Issue #102. Measurements and plates are plan fields. This module does not
call a provider.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from kubrick.plan.continuity_locks import frame_id, warning

WarningRow = dict[str, str | None]
_REF_W = 1080
_REF_H = 1920
_BOX = (140, 940, 220, 1436)
_PUSH = {"push_in", "pull_out"}
_TIGHT = {"knees_up", "ecu", "cu", "close_up", "extreme_close_up"}
_WIDE = {"wide", "ws", "full", "establishing", "wide_plate"}
_SCOPE = ("framing", "end_framing", "continuity", "location_ref", "video_prompt", "videoPrompt")
_REFRAME = re.compile(
    r"\b(?:wide|medium|close-?up|ecu|mcu|cu|full(?:\s+shot)?|knees-?up|head[\s-]?ratio)\b",
    re.IGNORECASE,
)
_END_REASON = "Keyframe create_movie schema has startImage and no end-image field"


def _map(value: object) -> Mapping[str, object] | None:
    if isinstance(value, Mapping):
        return value
    return None


def _text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _norm(value: object) -> str:
    return _text(value).casefold().replace("-", "_").replace(" ", "_")


def _view(frame: Mapping[str, object]) -> dict[str, object]:
    params = frame.get("provider_parameters")
    merged: dict[str, object] = {}
    if isinstance(params, Mapping):
        merged.update(params)
    merged.update(frame)
    return merged


def _band(value: object) -> tuple[float, float] | None:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != 2:
        return None
    lo, hi = value[0], value[1]
    if isinstance(lo, bool) or isinstance(hi, bool):
        return None
    if not isinstance(lo, (int, float)) or not isinstance(hi, (int, float)):
        return None
    return float(lo), float(hi)


def _start_used(frame: Mapping[str, object]) -> bool:
    start = _map(frame.get("start_frame"))
    if start is not None:
        for key in ("asset", "sourceFrame", "source_shot"):
            if _text(start.get(key)):
                return True
    join = frame.get("join")
    if isinstance(join, Mapping):
        return bool(_text(join.get("chain_from")))
    return False


def _move_parts(frame: Mapping[str, object]) -> tuple[list[str], bool]:
    camera = _map(frame.get("camera"))
    if camera is None:
        return [], False
    raw = camera.get("move")
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()], False
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        return [item.strip() for item in raw if isinstance(item, str) and item.strip()], True
    return [], False


def motion_line(frame: Mapping[str, object]) -> str | None:
    """One action and one camera move, joined by ``as``, when a start frame is used."""
    view = _view(frame)
    if not _start_used(view):
        return None
    action = _text(view.get("action"))
    moves, _listed = _move_parts(view)
    if not action or len(moves) != 1:
        return None
    return f"{action} as {moves[0]}"


def _slot(*parts: str) -> str:
    return ", ".join(part for part in parts if part)


def _lens(framing: Mapping[str, object]) -> str:
    raw = framing.get("lens_mm")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return _text(framing.get("lens"))
    number = int(raw) if float(raw).is_integer() else raw
    return f"{number}mm"


def _ratio_sentence(band: tuple[float, float]) -> str:
    return f"head ratio {band[0]:.2f} to {band[1]:.2f}"


def _emitters(framing: Mapping[str, object]) -> list[str]:
    raw = framing.get("emitters")
    if isinstance(raw, str) and raw.strip():
        return [f"the {raw.strip()} stays dark"]
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        return [
            f"the {item.strip()} stays dark"
            for item in raw
            if isinstance(item, str) and item.strip()
        ]
    return []


def board_prompt(
    framing: Mapping[str, object],
    end_framing: Mapping[str, object] | None = None,
) -> str:
    """Start-board sentence. Size, angle, placement, crop, ratios, facing, dark emitters, key."""
    parts: list[str] = []
    lead = _slot(_text(framing.get("size")), _lens(framing))
    if lead:
        parts.append(lead)
    angle = _slot(_text(framing.get("angle")), _text(framing.get("height")))
    if angle:
        parts.append(angle)
    for key in ("placement", "crop"):
        text = _text(framing.get(key))
        if text:
            parts.append(text)
    start = _band(framing.get("head_ratio"))
    if start is not None:
        parts.append(_ratio_sentence(start))
    if end_framing is not None:
        end = _band(end_framing.get("head_ratio"))
        if end is not None:
            parts.append(_ratio_sentence(end))
    facing = _text(framing.get("facing"))
    if facing:
        parts.append(facing)
    parts.extend(_emitters(framing))
    key_side = _text(framing.get("key_side"))
    if key_side:
        parts.append(key_side)
    return "; ".join(parts)


def _changed(start: Mapping[str, object], end: Mapping[str, object], key: str) -> bool:
    left, right = _norm(start.get(key)), _norm(end.get(key))
    return bool(left and right and left != right)


def needs_end_anchor(start: Mapping[str, object], end: Mapping[str, object] | None) -> bool:
    """Size, crop, or a head-ratio midpoint shift above 0.05 needs an end anchor."""
    if end is None:
        return False
    if _changed(start, end, "size") or _changed(start, end, "crop"):
        return True
    left, right = _band(start.get("head_ratio")), _band(end.get("head_ratio"))
    if left is None or right is None:
        return False
    return abs(((right[0] + right[1]) / 2) - ((left[0] + left[1]) / 2)) > 0.05


def end_anchor(frame: Mapping[str, object]) -> dict[str, object]:
    """Record the end framing. Keyframe has ``startImage`` and no end-image field."""
    view = _view(frame)
    framing = _map(view.get("framing")) or {}
    end = _map(view.get("end_framing"))
    limit: dict[str, object] = {
        "field": "last_frame",
        "supported": False,
        "reason": _END_REASON,
    }
    if end is not None:
        limit["end_framing"] = dict(end)
    found: dict[str, object] = {
        "needed": end is not None and needs_end_anchor(framing, end),
        "last_frame": limit,
    }
    if end is not None:
        band = _band(end.get("head_ratio"))
        if band is not None:
            found["head_ratio"] = [band[0], band[1]]
    return found


def safe_box(width: int, height: int) -> dict[str, int]:
    """Scale the 1080×1920 safe box. ``delivery.platform`` uses the same ratios."""
    x0, x1, y0, y1 = _BOX
    return {
        "x0": round(x0 / _REF_W * width),
        "x1": round(x1 / _REF_W * width),
        "y0": round(y0 / _REF_H * height),
        "y1": round(y1 / _REF_H * height),
    }


def _crop(frame: Mapping[str, object]) -> str:
    for key in ("framing", "ask"):
        source = _map(frame.get(key))
        if source is not None and _text(source.get("crop")):
            return _text(source.get("crop"))
    return ""


def _wide_plate(frame: Mapping[str, object]) -> bool:
    location = _map(frame.get("location_ref"))
    if location is None:
        return False
    plate = _norm(location.get("plate") or location.get("size"))
    return plate in _WIDE or plate.startswith("wide")


def _scoped(frame: Mapping[str, object]) -> bool:
    return any(frame.get(key) is not None for key in _SCOPE)


def _row(code: str, shot: str, message: str, recommendation: str) -> WarningRow:
    return warning(code, shot, message, recommendation)


def _explicit_video(frame: Mapping[str, object]) -> str:
    return _text(frame.get("video_prompt")) or _text(frame.get("videoPrompt"))


def _framing_rows(frame: Mapping[str, object], shot: str) -> list[WarningRow]:
    found: list[WarningRow] = []
    if _start_used(frame) and _REFRAME.search(_explicit_video(frame)):
        found.append(_row(
            "VIDEO_REFRAME_IGNORED",
            shot,
            "video prompt restates shot size or head ratio after a start frame",
            "keep the video line to one action and one camera move",
        ))
    crop = _crop(frame)
    location = _map(frame.get("location_ref")) or {}
    precrop = _text(location.get("precrop_to"))
    if crop and _norm(crop) in _TIGHT and _wide_plate(frame) and _norm(precrop) != _norm(crop):
        found.append(_row(
            "WIDE_PLATE_OVERRIDES_CROP",
            shot,
            f"tight crop {crop} is asked over a wide location plate",
            "set location_ref.precrop_to to the asked crop",
        ))
        found.append(_row(
            "CROP_UNREACHABLE_FROM_PLATE",
            shot,
            f"crop {crop} is unreachable from the wide plate without precrop_to",
            "pre-crop the plate, or ask for a crop the plate can reach",
        ))
    framing = _map(frame.get("framing")) or {}
    if _text(framing.get("proportion")) and _band(framing.get("head_ratio")) is None:
        found.append(_row(
            "ADJECTIVE_PROPORTION",
            shot,
            f"proportion {_text(framing.get('proportion'))!r} has no numeric head_ratio",
            "set framing.head_ratio to a low and high number",
        ))
    moves, _listed = _move_parts(frame)
    end = _map(frame.get("end_framing"))
    pushing = any(_norm(move) in _PUSH for move in moves)
    if pushing and end is None:
        found.append(_row(
            "MOVE_WITHOUT_END_ANCHOR",
            shot,
            f"{', '.join(moves)} has no end_framing anchor",
            "add end_framing with a head_ratio band or a crop",
        ))
    if end is not None and _band(end.get("head_ratio")) is None and not _text(end.get("crop")):
        found.append(_row(
            "MOVE_TARGET_MISSING",
            shot,
            "end_framing has no head_ratio or crop target",
            "set end_framing.head_ratio or end_framing.crop",
        ))
    if end is not None and needs_end_anchor(framing, end):
        band = _band(end.get("head_ratio"))
        target = ""
        if band is not None:
            target = f" Target head ratio {band[0]:.2f} to {band[1]:.2f}."
        found.append(_row(
            "END_IMAGE_UNSUPPORTED",
            shot,
            f"{_END_REASON}.{target}",
            "Record the end framing on prep. Do not add a last-frame shot field.",
        ))
    return found


def _axis(frame: Mapping[str, object]) -> str:
    continuity = _map(frame.get("continuity"))
    if continuity is None:
        return ""
    return _text(continuity.get("axis_side"))


def _bridged(frame: Mapping[str, object]) -> bool:
    continuity = _map(frame.get("continuity"))
    return continuity is not None and continuity.get("axis_bridge") is True


def framing_warnings(
    document: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
) -> list[WarningRow]:
    """Prep warnings for numeric framing. Legacy plans without these fields stay quiet."""
    del document
    found: list[WarningRow] = []
    previous = ""
    for index, frame in enumerate(frames, start=1):
        view = _view(frame)
        shot = frame_id(frame, index)
        moves, listed = _move_parts(view)
        if listed and len(moves) >= 2:
            found.append(_row(
                "MOVE_CHAIN_CONFLICT",
                shot,
                f"{', '.join(moves)} are two primary moves",
                "keep one primary move on the shot",
            ))
        if _scoped(view):
            found.extend(_framing_rows(view, shot))
            side = _axis(view)
            if side and previous and side.casefold() != previous.casefold() and not _bridged(view):
                found.append(_row(
                    "AXIS_CROSS_UNBRIDGED",
                    shot,
                    f"axis side {previous} to {side} is not bridged",
                    "set continuity.axis_bridge, or keep the axis side",
                ))
            if side:
                previous = side
    return found
