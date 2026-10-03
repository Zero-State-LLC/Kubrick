#!/usr/bin/env python3
"""Proposed generation and edit plan. Issue #36.

A short beat on a multi-shot single clip, a chained shot, a reused shot, or a
provider that is not multi-shot is its own generation. Two or more remaining
contiguous beats share one clip. This module does not call a provider, ffmpeg,
or the network. Missing duration uses 4.0 seconds.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence

from continuity_locks import frame_field, frame_id
from io_safety import load_structured, write_structured
from provider_capabilities import capabilities_for, capabilities_for_document
from shot_plan import chain_source, generation_seconds, opens_with_exit

_DEFAULT_SECONDS = 4.0


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _planned(frame: Mapping[str, object]) -> float:
    for key in ("duration_seconds", "durationSeconds", "duration"):
        parsed = _number(frame_field(frame, key))
        if parsed is not None:
            return parsed
    return _DEFAULT_SECONDS


def _threshold(provider: str, document: Mapping[str, object]) -> float:
    override = _number(document.get("short_beat_threshold_seconds"))
    if override is not None:
        return override
    caps = capabilities_for_document(provider, document)
    parsed = _number(caps.get("short_beat_threshold_seconds"))
    return 2.0 if parsed is None else parsed


def _labels(frame: Mapping[str, object], index: int) -> set[str]:
    labels = {frame_id(frame, index)}
    raw = frame_field(frame, "shot_id")
    if isinstance(raw, str) and raw.strip():
        labels.add(raw.strip())
    return labels


def _shot_name(frame: Mapping[str, object], index: int) -> str:
    raw = frame_field(frame, "shot_id")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return frame_id(frame, index)


def _usable(take: Mapping[str, object], planned: float) -> bool:
    trim = take.get("trim")
    if not isinstance(trim, Mapping):
        return False
    start, end = _number(trim.get("in")), _number(trim.get("out"))
    if start is None or end is None:
        return False
    return end - start + 1e-9 >= planned


def _take_for(
    takes: Sequence[Mapping[str, object]],
    frame: Mapping[str, object],
    index: int,
    planned: float,
) -> Mapping[str, object] | None:
    labels = _labels(frame, index)
    for take in takes:
        shot = take.get("shot")
        if isinstance(shot, str) and shot.strip() in labels and _usable(take, planned):
            return take
    return None


def _separate(
    frame: Mapping[str, object],
    provider: str,
    threshold: float,
    reused: bool,
) -> bool:
    if reused or chain_source(frame) is not None:
        return True
    caps = capabilities_for(provider)
    if caps.get("is_multi_shot_single_clip") and _planned(frame) <= threshold:
        return True
    return not bool(caps.get("multi_shot"))


def _too_long(provider: str, generated: float) -> str | None:
    maximum = _number(capabilities_for(provider).get("max_duration_seconds"))
    if maximum is None or maximum <= 0 or generated <= maximum:
        return None
    return (
        f"NO_FEASIBLE_PLAN generated {generated}s exceeds {provider} maximum {maximum}s"
    )


def _clip_seconds(provider: str, planned_sum: float) -> float:
    floor = _number(capabilities_for(provider).get("min_duration_seconds")) or 0.0
    return round(max(planned_sum, floor), 4)


def _edit(shot: str, source: str, start: float, end: float) -> dict[str, object]:
    return {"shot": shot, "source": source, "in": start, "out": end}


def _entry(
    shot: str,
    frame_key: str,
    mode: str,
    start: float,
    end: float,
    planned: float,
    generated: float,
    clip_id: str | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "shot": shot,
        "frame_id": frame_key,
        "mode": mode,
        "edit_in": start,
        "edit_out": end,
        "planned_seconds": planned,
        "generated_seconds": generated,
    }
    if clip_id is not None:
        row["clip_id"] = clip_id
    return row


def _groups(
    frames: Sequence[Mapping[str, object]],
    provider: str,
    takes: Sequence[Mapping[str, object]],
    threshold: float,
) -> list[list[tuple[int, Mapping[str, object], Mapping[str, object] | None]]]:
    groups: list[list[tuple[int, Mapping[str, object], Mapping[str, object] | None]]] = []
    current: list[tuple[int, Mapping[str, object], Mapping[str, object] | None]] = []
    for index, frame in enumerate(frames, start=1):
        planned = _planned(frame)
        take = _take_for(takes, frame, index, planned)
        reused = take is not None
        if _separate(frame, provider, threshold, reused):
            if current:
                groups.append(current)
                current = []
            groups.append([(index, frame, take)])
            continue
        current.append((index, frame, None))
    if current:
        groups.append(current)
    return groups


def _one_shot(
    provider: str,
    index: int,
    frame: Mapping[str, object],
    take: Mapping[str, object] | None,
    document: Mapping[str, object] | None = None,
) -> tuple[dict[str, object], dict[str, object], float]:
    planned = _planned(frame)
    shot = _shot_name(frame, index)
    frame_key = frame_id(frame, index)
    if take is not None:
        trim = take.get("trim")
        window = trim if isinstance(trim, Mapping) else {}
        start = _number(window.get("in")) or 0.0
        end = _number(window.get("out")) or planned
        source = take.get("source_clip")
        origin = source.strip() if isinstance(source, str) and source.strip() else shot
        return (
            _entry(shot, frame_key, "reuse_take", start, end, planned, 0.0),
            _edit(shot, origin, start, end),
            0.0,
        )
    chained = chain_source(frame) is not None
    generated, hold = generation_seconds(
        planned,
        chained=chained,
        exit_open=opens_with_exit(frame),
        provider=provider,
        document=document,
    )
    start = hold
    end = round(hold + planned, 4)
    blocked = _too_long(provider, generated)
    if blocked:
        raise _Refuse(blocked)
    return (
        _entry(shot, frame_key, "new_generation", start, end, planned, generated),
        _edit(shot, "generate", start, end),
        generated,
    )


class _Refuse(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _shared(
    provider: str,
    members: Sequence[tuple[int, Mapping[str, object], Mapping[str, object] | None]],
    clip_id: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]], float]:
    planned_sum = round(sum(_planned(frame) for _index, frame, _take in members), 4)
    generated = _clip_seconds(provider, planned_sum)
    blocked = _too_long(provider, generated)
    if blocked:
        raise _Refuse(blocked)
    rows: list[dict[str, object]] = []
    edits: list[dict[str, object]] = []
    cursor = 0.0
    for index, frame, _take in members:
        planned = _planned(frame)
        end = round(cursor + planned, 4)
        shot = _shot_name(frame, index)
        rows.append(_entry(
            shot,
            frame_id(frame, index),
            "in_multi_shot_clip",
            cursor,
            end,
            planned,
            generated,
            clip_id,
        ))
        edits.append(_edit(shot, clip_id, cursor, end))
        cursor = end
    return rows, edits, generated


def _accepted(document: Mapping[str, object], flag: bool) -> bool:
    return flag or document.get("accept_clock_delta") is True


def _closed(provider: str, code: str, message: str, **fields: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "NOT_COMPUTABLE",
        "authority": "NOT_COMPUTABLE",
        "action": "retime",
        "provider": provider,
        "code": code,
        "message": message,
    }
    payload.update(fields)
    return payload


def retime(
    document: Mapping[str, object],
    provider: str,
    takes: Sequence[Mapping[str, object]] | None = None,
    *,
    accept_clock_delta: bool = False,
) -> dict[str, object]:
    """PROPOSED plan, or NOT_COMPUTABLE when no feasible plan exists."""
    name = provider.strip().casefold() or "generic"
    caps = capabilities_for(name)
    if not caps.get("video"):
        return _closed(name, "NO_FEASIBLE_PLAN", f"provider {name} does not support video")
    raw_frames = document.get("frames")
    frames = [
        frame for frame in raw_frames
        if isinstance(frame, Mapping)
    ] if isinstance(raw_frames, Sequence) and not isinstance(raw_frames, (str, bytes)) else []
    if not frames:
        return _closed(name, "NO_FEASIBLE_PLAN", "retime needs at least one frame")
    usable = [item for item in (takes or []) if isinstance(item, Mapping)]
    threshold = _threshold(name, document)
    script = round(sum(_planned(frame) for frame in frames), 4)
    try:
        generation, edits, final = _assemble(frames, name, usable, threshold, document)
    except _Refuse as refused:
        return _closed(name, "NO_FEASIBLE_PLAN", refused.message, script_clock=script)
    delta = round(final - script, 4)
    if abs(delta) > 1e-6 and not _accepted(document, accept_clock_delta):
        return _closed(
            name,
            "CLOCK_DELTA_UNACCEPTED",
            (
                f"script clock {script} and final clock {final} differ by {delta}; "
                "set accept_clock_delta to continue"
            ),
            script_clock=script,
            final_clock=final,
            delta=delta,
            generation_plan=generation,
            edit_plan=edits,
        )
    return {
        "status": "PROPOSED",
        "authority": "PROPOSED",
        "action": "retime",
        "provider": name,
        "script_clock": script,
        "final_clock": final,
        "delta": delta,
        "accept_clock_delta": _accepted(document, accept_clock_delta),
        "generation_plan": generation,
        "edit_plan": edits,
    }


def _assemble(
    frames: Sequence[Mapping[str, object]],
    provider: str,
    takes: Sequence[Mapping[str, object]],
    threshold: float,
    document: Mapping[str, object] | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]], float]:
    generation: list[dict[str, object]] = []
    edits: list[dict[str, object]] = []
    final = 0.0
    clip_index = 0
    for group in _groups(frames, provider, takes, threshold):
        if len(group) == 1:
            row, edit, generated = _one_shot(provider, *group[0], document)
            generation.append(row)
            edits.append(edit)
            final = round(final + generated, 4)
            continue
        clip_index += 1
        rows, shared_edits, generated = _shared(provider, group, f"clip-{clip_index}")
        generation.extend(rows)
        edits.extend(shared_edits)
        final = round(final + generated, 4)
    return generation, edits, final


def _load_takes(path: str | None) -> list[Mapping[str, object]]:
    if not path:
        return []
    loaded = load_structured(path)
    if isinstance(loaded, list):
        return [item for item in loaded if isinstance(item, Mapping)]
    if isinstance(loaded, dict):
        raw = loaded.get("takes")
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, Mapping)]
    return []


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Propose a retime plan. No provider call.")
    parser.add_argument("--surface-action", default=None)
    parser.add_argument("--input", required=True)
    parser.add_argument("--provider", default="generic")
    parser.add_argument("--takes")
    parser.add_argument("--output")
    parser.add_argument("--accept-clock-delta", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    document = load_structured(args.input)
    if not isinstance(document, dict):
        print("retime input must be a mapping", file=sys.stderr)
        return 4
    result = retime(
        document,
        args.provider,
        _load_takes(args.takes),
        accept_clock_delta=args.accept_clock_delta,
    )
    if args.output:
        write_structured(args.output, result)
    else:
        import yaml

        print(yaml.safe_dump(result, sort_keys=False))
    return 0 if result.get("status") == "PROPOSED" else 4


if __name__ == "__main__":
    raise SystemExit(main())
