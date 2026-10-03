#!/usr/bin/env python3
"""Adapt every shot of a sequence into one adapter packet. Issue #63.

Each shot is adapted in order. A shot that is not an object, whose frame has
no usable prompt, or whose packet-wide shared constraints (negatives, locks)
differ from the first shot fails the whole adapt and the message names the
shot, because the provider applies shared constraints to every frame.
"""
from __future__ import annotations

import json
from collections.abc import Callable


def sequence_shot_name(shot: object, index: int) -> str:
    if isinstance(shot, dict):
        for key in ("shot_id", "frame_id", "id"):
            raw = shot.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    return f"index-{index}"


def _shot_frames(packet: dict[str, object], name: str) -> list[dict[str, object]]:
    raw = packet.get("frames")
    frames = [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
    if not frames:
        raise ValueError(f"sequence shot {name} is not adaptable: no prompt")
    for frame in frames:
        prompt = frame.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip() or prompt == "NOT_COMPUTABLE":
            raise ValueError(f"sequence shot {name} is not adaptable: no prompt")
    return frames


def _duration(raw: object) -> float | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        try:
            return float(raw.strip())
        except ValueError:
            return None
    return None


def _norm(value: object) -> object:
    if isinstance(value, list):
        return sorted(json.dumps(item, sort_keys=True, default=str) for item in value)
    return value


def _diverging_keys(base: object, later: object) -> list[str]:
    """Keys whose shared constraints differ between two shots (missing == empty)."""
    first = base if isinstance(base, dict) else {}
    second = later if isinstance(later, dict) else {}
    keys = {str(k) for k in first} | {str(k) for k in second}
    return sorted(
        key for key in keys if _norm(first.get(key) or []) != _norm(second.get(key) or [])
    )


def _unique_ids(frames: list[tuple[int, dict[str, object]]]) -> list[dict[str, object]]:
    seen: set[str] = set()
    out: list[dict[str, object]] = []
    for index, frame in frames:
        copy = dict(frame)
        fid = str(copy.get("frame_id"))
        if fid in seen:
            fid = f"{fid}-{index}"
        seen.add(fid)
        copy["frame_id"] = fid
        out.append(copy)
    return out


def sequence_adapter_packet(
    shots: list[object],
    to_packet: Callable[[dict[str, object]], dict[str, object]],
) -> tuple[dict[str, object], float | None]:
    """Combine every shot's adapter packet in order; ValueError names a failing shot."""
    combined: dict[str, object] = {}
    first_name = ""
    frames: list[tuple[int, dict[str, object]]] = []
    longest: float | None = None
    for index, shot in enumerate(shots):
        name = sequence_shot_name(shot, index)
        if not isinstance(shot, dict):
            raise ValueError(f"sequence shot {name} is not adaptable: shot must be an object")
        packet = to_packet(shot)
        frames.extend((index, frame) for frame in _shot_frames(packet, name))
        if index == 0:
            combined = dict(packet)
            first_name = name
        else:
            diverging = _diverging_keys(
                combined.get("shared_constraints"), packet.get("shared_constraints")
            )
            if diverging:
                raise ValueError(
                    f"sequence shot {name} is not adaptable: shared constraints "
                    f"{', '.join(diverging)} differ from shot {first_name}; "
                    "adapt these shots separately"
                )
        seconds = _duration(shot.get("duration_seconds"))
        if seconds is not None and (longest is None or seconds > longest):
            longest = seconds
    combined["frames"] = _unique_ids(frames)
    combined.pop("duration_seconds", None)
    return combined, longest
