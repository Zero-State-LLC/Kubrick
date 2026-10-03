#!/usr/bin/env python3
"""Keyframe start-frame asset gate. Issue #38.

Kubrick emits an ffmpeg handoff string and does not run it. Grab time is
``start_frame.at_seconds``, else the join ``at_seconds``, else 0. ``verified``
counts only when it is boolean true. A missing asset does not also warn
``START_FRAME_UNVERIFIED``.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from continuity_locks import frame_field, frame_id, warning
from value_coerce import as_number as _number

_MISSING = (
    "verify the grab against the saved timestamp, not the UI label; "
    "Kubrick does not run ffmpeg"
)
_UNVERIFIED = "confirm the still matches the saved timestamp before spend"


def format_seconds(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _label(frame: Mapping[str, object], index: int) -> str:
    raw = frame_field(frame, "shot_id")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return frame_id(frame, index)


def grab(frame: Mapping[str, object]) -> tuple[float, str]:
    """Seconds and source clip for the handoff string."""
    raw = frame_field(frame, "start_frame")
    spec = raw if isinstance(raw, Mapping) else {}
    at = _number(spec.get("at_seconds"))
    if at is None:
        join = frame_field(frame, "join")
        if isinstance(join, Mapping):
            at = _number(join.get("at_seconds"))
    source = spec.get("source_take")
    if not isinstance(source, str) or not source.strip():
        source = "<source>"
    return 0.0 if at is None else at, source.strip()


def handoff(label: str, at: float, source: str) -> str:
    return f"ffmpeg -ss {format_seconds(at)} -i {source} -frames:v 1 {label}-start.png"


def _asset(frame: Mapping[str, object]) -> str | None:
    raw = frame_field(frame, "start_frame")
    if not isinstance(raw, Mapping):
        return None
    asset = raw.get("asset")
    if isinstance(asset, str) and asset.strip():
        return asset.strip()
    return None


def start_warnings(
    frames: Sequence[Mapping[str, object]],
    provider: str,
) -> list[dict[str, str | None]]:
    """Keyframe chained shots only. Other providers stay silent."""
    if provider.strip().casefold() != "keyframe":
        return []
    from shot_plan import chain_source

    found: list[dict[str, str | None]] = []
    for index, frame in enumerate(frames, start=1):
        if chain_source(frame) is None:
            continue
        shot = frame_id(frame, index)
        label = _label(frame, index)
        asset = _asset(frame)
        if asset is None:
            at, source = grab(frame)
            command = handoff(label, at, source)
            found.append(warning(
                "START_FRAME_MISSING",
                shot,
                f"BLOCKED_PRE_SPEND shot {label} has no start_frame.asset; {command}",
                _MISSING,
            ))
            continue
        spec = frame_field(frame, "start_frame")
        verified = isinstance(spec, Mapping) and spec.get("verified") is True
        if not verified:
            found.append(warning(
                "START_FRAME_UNVERIFIED",
                shot,
                f"shot {label} start_frame.asset is not verified",
                _UNVERIFIED,
            ))
    return found


def stamp_asset(shot: dict[str, object], frame: Mapping[str, object]) -> None:
    """Copy ``start_frame.asset`` onto an existing Keyframe ``startImage``."""
    image = shot.get("startImage")
    if not isinstance(image, dict):
        return
    asset = _asset(frame)
    if asset is None:
        return
    shot["startImage"] = {**image, "asset": asset}
