#!/usr/bin/env python3
"""Proposed generation and edit plan. Issue #36.

A short beat on a multi-shot single clip, a chained shot, a reused shot, or a
provider that is not multi-shot is its own generation. Two or more remaining
contiguous beats share one clip. `final_clock` is the edited runtime, the sum
of edit-plan out minus in. `generated_clock` sums generated seconds and counts
each shared clip once. This module does not call a provider, ffmpeg, or the
network. Missing duration uses 8.0 seconds and adds DURATION_MISSING.
``--take SHOT=TAKE_ID`` reuses the take with that ``take_id``; an unknown id is
TAKE_NOT_FOUND and several ``selected: true`` takes are TAKE_AMBIGUOUS.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence

from continuity_locks import frame_field, frame_id
from io_safety import load_structured, write_structured
from provider_capabilities import capabilities_for
from shot_plan import (
    chain_source,
    duration_warnings,
    generation_seconds,
    opens_with_exit,
    planned_duration,
)
from take_select import parse_take_overrides, select_take, unknown_override
from value_coerce import as_number as _number


def _threshold(provider: str, document: Mapping[str, object]) -> float:
    override = _number(document.get("short_beat_threshold_seconds"))
    if override is not None:
        return override
    parsed = _number(capabilities_for(provider).get("short_beat_threshold_seconds"))
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
    overrides: Mapping[str, str],
) -> Mapping[str, object] | None:
    labels = _labels(frame, index)
    matches = [
        take for take in takes
        if isinstance(take.get("shot"), str) and str(take.get("shot")).strip() in labels
    ]
    has_override = any(label in overrides for label in labels)
    if not has_override and not any(take.get("selected") is True for take in matches):
        for take in matches:
            if _usable(take, planned):
                return take
        return None
    chosen, issue = select_take(matches, labels, frame_id(frame, index), overrides)
    if issue is not None:
        raise _Refuse(f"{issue.get('code')}: {issue.get('message')}")
    if chosen is None:
        return None
    if not _usable(chosen, planned):
        raise _Refuse(
            f"TAKE_UNUSABLE: selected take {chosen.get('take_id')} for shot "
            f"{frame_id(frame, index)} has no trim covering {planned}s"
        )
    return chosen


def _separate(
    frame: Mapping[str, object],
    provider: str,
    threshold: float,
    reused: bool,
) -> bool:
    if reused or chain_source(frame) is not None:
        return True
    caps = capabilities_for(provider)
    if caps.get("is_multi_shot_single_clip") and planned_duration(frame) <= threshold:
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
    overrides: Mapping[str, str],
) -> list[list[tuple[int, Mapping[str, object], Mapping[str, object] | None]]]:
    groups: list[list[tuple[int, Mapping[str, object], Mapping[str, object] | None]]] = []
    current: list[tuple[int, Mapping[str, object], Mapping[str, object] | None]] = []
    for index, frame in enumerate(frames, start=1):
        planned = planned_duration(frame)
        take = _take_for(takes, frame, index, planned, overrides)
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
) -> tuple[dict[str, object], dict[str, object], float]:
    planned = planned_duration(frame)
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
    planned_sum = round(sum(planned_duration(frame) for _index, frame, _take in members), 4)
    generated = _clip_seconds(provider, planned_sum)
    blocked = _too_long(provider, generated)
    if blocked:
        raise _Refuse(blocked)
    rows: list[dict[str, object]] = []
    edits: list[dict[str, object]] = []
    cursor = 0.0
    for index, frame, _take in members:
        planned = planned_duration(frame)
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


def _edited_runtime(edits: Sequence[Mapping[str, object]]) -> float:
    total = 0.0
    for edit in edits:
        start = _number(edit.get("in")) or 0.0
        end = _number(edit.get("out"))
        width = (start if end is None else end) - start
        total = round(total + round(width, 4), 4)
    return total


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


def _note(
    missing: list[dict[str, str | None]],
    payload: dict[str, object],
) -> dict[str, object]:
    if missing:
        payload["prep_warnings"] = missing
    return payload


def retime(
    document: Mapping[str, object],
    provider: str,
    takes: Sequence[Mapping[str, object]] | None = None,
    *,
    accept_clock_delta: bool = False,
    overrides: Mapping[str, str] | None = None,
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
    known = set().union(*(_labels(frame, i) for i, frame in enumerate(frames, start=1)))
    stray = unknown_override(dict(overrides or {}), known)
    if stray is not None:
        return _closed(name, "TAKE_NOT_FOUND", str(stray.get("message")))
    missing = duration_warnings(frames)
    usable = [item for item in (takes or []) if isinstance(item, Mapping)]
    threshold = _threshold(name, document)
    script = round(sum(planned_duration(frame) for frame in frames), 4)
    try:
        generation, edits, generated_clock = _assemble(
            frames, name, usable, threshold, dict(overrides or {})
        )
    except _Refuse as refused:
        code = "NO_FEASIBLE_PLAN"
        if refused.message.startswith("TAKE_"):
            code = refused.message.split(":", 1)[0]
        return _note(
            missing,
            _closed(name, code, refused.message, script_clock=script),
        )
    final = _edited_runtime(edits)
    delta = round(final - script, 4)
    if abs(delta) > 1e-6 and not _accepted(document, accept_clock_delta):
        return _note(missing, _closed(
            name,
            "CLOCK_DELTA_UNACCEPTED",
            (
                f"script clock {script} and final clock {final} differ by {delta}; "
                "set accept_clock_delta to continue"
            ),
            script_clock=script,
            final_clock=final,
            generated_clock=generated_clock,
            delta=delta,
            generation_plan=generation,
            edit_plan=edits,
        ))
    return _note(missing, {
        "status": "PROPOSED",
        "authority": "PROPOSED",
        "action": "retime",
        "provider": name,
        "script_clock": script,
        "final_clock": final,
        "generated_clock": generated_clock,
        "delta": delta,
        "accept_clock_delta": _accepted(document, accept_clock_delta),
        "generation_plan": generation,
        "edit_plan": edits,
    })


def _assemble(
    frames: Sequence[Mapping[str, object]],
    provider: str,
    takes: Sequence[Mapping[str, object]],
    threshold: float,
    overrides: Mapping[str, str],
) -> tuple[list[dict[str, object]], list[dict[str, object]], float]:
    generation: list[dict[str, object]] = []
    edits: list[dict[str, object]] = []
    generated_clock = 0.0
    clip_index = 0
    for group in _groups(frames, provider, takes, threshold, overrides):
        if len(group) == 1:
            row, edit, generated = _one_shot(provider, *group[0])
            generation.append(row)
            edits.append(edit)
            generated_clock = round(generated_clock + generated, 4)
            continue
        clip_index += 1
        rows, shared_edits, generated = _shared(provider, group, f"clip-{clip_index}")
        generation.extend(rows)
        edits.extend(shared_edits)
        generated_clock = round(generated_clock + generated, 4)
    return generation, edits, generated_clock


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
    parser.add_argument("--take", action="append", default=None, metavar="SHOT=TAKE_ID")
    parser.add_argument("--output")
    parser.add_argument("--accept-clock-delta", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        overrides = parse_take_overrides(args.take)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    document = load_structured(args.input)
    if not isinstance(document, dict):
        print("retime input must be a mapping", file=sys.stderr)
        return 4
    result = retime(
        document,
        args.provider,
        _load_takes(args.takes),
        accept_clock_delta=args.accept_clock_delta,
        overrides=overrides,
    )
    if args.output:
        write_structured(args.output, result)
    else:
        from runtime_deps import yaml_dump

        print(yaml_dump(result, sort_keys=False))
    return 0 if result.get("status") == "PROPOSED" else 4


if __name__ == "__main__":
    raise SystemExit(main())
