"""Prep-only cut QA (issue #70). Emits PROPOSED ffmpeg commands; never runs them."""

from __future__ import annotations

import shlex
import sys
from collections.abc import Mapping, Sequence

from kubrick.providers.video_prep_common import (
    build_parser,
    closed,
    emit,
    frame_label_matches,
    frames_of,
    number,
    prepare,
    timeline,
)

ACTION = "cut-qa"
MAE_FILTER = (
    "[1:v][0:v]scale2ref[ref][cut];[cut][ref]blend=all_mode=difference,"
    "signalstats,metadata=print:key=lavfi.signalstats.YAVG"
)


def _grab(final: str, at: float, name: str) -> str:
    return (
        f"ffmpeg -hide_banner -ss {at:.3f} -i {shlex.quote(final)} "
        f"-frames:v 1 {shlex.quote(name)}"
    )


def _start_frame_commands(
    document: Mapping[str, object], rows: Sequence[Mapping[str, object]], final: str
) -> list[dict[str, object]]:
    commands: list[dict[str, object]] = []
    for frame in frames_of(document):
        start = frame.get("start_frame")
        asset = start.get("asset") if isinstance(start, Mapping) else None
        if not isinstance(asset, str) or not asset:
            continue
        row = next((r for r in rows if frame_label_matches(frame, r.get("shot"))), None)
        if row is None:
            continue
        at = number(row.get("start")) or 0.0
        command = (
            f"ffmpeg -hide_banner -ss {at:.3f} -i {shlex.quote(final)} -i {shlex.quote(asset)} "
            f'-frames:v 1 -lavfi "{MAE_FILTER}" -f null -'
        )
        commands.append({"kind": "start_frame_mae", "shot": row.get("shot"), "command": command})
    return commands


def cut_qa(
    document: Mapping[str, object],
    plan: Mapping[str, object],
    final: str,
    threshold: float,
    tolerance: float,
) -> dict[str, object]:
    try:
        rows = timeline(plan)
    except ValueError as exc:
        return closed(ACTION, "EDIT_PLAN_INVALID", str(exc))
    cuts = [number(r.get("start")) or 0.0 for r in rows[1:]]
    expected: list[dict[str, object]] = []
    commands: list[dict[str, object]] = []
    for i, at in enumerate(cuts, start=1):
        expected.append({"index": i, "at_seconds": at, "tolerance_seconds": tolerance})
        for suffix, t in (("before", at - 0.04), ("after", at + 0.04)):
            commands.append(
                {"kind": "frame_grab", "command": _grab(final, t, f"cut-{i:02d}-{suffix}.png")}
            )
    scene = (
        f"ffmpeg -hide_banner -i {shlex.quote(final)} "
        f"-filter:v \"select='gt(scene,{threshold})',showinfo\" -f null -"
    )
    commands.append({"kind": "scene_detect", "command": scene})
    commands.extend(_start_frame_commands(document, rows, final))
    return {
        "status": "PROPOSED",
        "authority": "PROPOSED",
        "executes": False,
        "final_clock": plan.get("final_clock"),
        "expected_cuts": expected,
        "commands": commands,
        "acceptance": {
            "scene_cut_tolerance_seconds": tolerance,
            "start_frame_mae_max": 8.0,
            "start_frame_mae_label": "INFERRED",
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser("PROPOSED ffmpeg cut QA commands (prep only)")
    parser.add_argument("--final", default="final.mp4")
    parser.add_argument("--scene-threshold", type=float, default=0.3)
    parser.add_argument("--tolerance", type=float, default=0.1)
    args = parser.parse_args(argv)
    prepared = prepare(args)
    if isinstance(prepared, dict):
        return emit(args, ACTION, prepared)
    document, plan = prepared
    payload = cut_qa(document, plan, args.final, args.scene_threshold, args.tolerance)
    return emit(args, ACTION, payload)


if __name__ == "__main__":
    sys.exit(main())
