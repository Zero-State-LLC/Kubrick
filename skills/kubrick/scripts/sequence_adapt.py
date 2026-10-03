#!/usr/bin/env python3
"""Adapt every shot of a sequence into one adapter packet. Issue #63.

Each shot is adapted in order. A shot that is not an object, or whose frame
has no usable prompt, fails the whole adapt and the message names the shot.
"""
from __future__ import annotations

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


def _merge_shared(combined: dict[str, object], later: object) -> None:
    if not isinstance(later, dict):
        return
    for key, value in later.items():
        if not isinstance(value, list):
            continue
        existing = combined.get(key)
        if existing is None:
            combined[key] = list(value)
            continue
        if not isinstance(existing, list):
            continue
        for item in value:
            if item not in existing:
                existing.append(item)


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
    shared: dict[str, object] = {}
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
            base = packet.get("shared_constraints")
            if isinstance(base, dict):
                shared = {k: (list(v) if isinstance(v, list) else v) for k, v in base.items()}
        else:
            _merge_shared(shared, packet.get("shared_constraints"))
        seconds = _duration(shot.get("duration_seconds"))
        if seconds is not None and (longest is None or seconds > longest):
            longest = seconds
    combined["frames"] = _unique_ids(frames)
    combined["shared_constraints"] = shared
    combined.pop("duration_seconds", None)
    return combined, longest
