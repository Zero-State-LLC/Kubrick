"""Shared helpers for prep-only video actions (runbook, cut-qa, cues).

Nothing here executes Keyframe, ElevenLabs, ffmpeg or any network call; every
output is a PROPOSED plan or a NOT_COMPUTABLE refusal.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence

PrepResult = tuple[dict[str, object], dict[str, object]] | dict[str, object]


def build_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--surface-action", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--input", required=True, help="storyboard plan (YAML/JSON)")
    parser.add_argument("--provider", default="keyframe")
    parser.add_argument("--takes", default=None)
    parser.add_argument("--take", action="append", default=None, metavar="SHOT=TAKE_ID")
    parser.add_argument("--output", default=None)
    parser.add_argument("--accept-clock-delta", action="store_true")
    return parser


def closed(action: str, code: str, message: str) -> dict[str, object]:
    return {
        "status": "NOT_COMPUTABLE",
        "authority": "NOT_COMPUTABLE",
        "action": action,
        "code": code,
        "message": message,
        "executes": False,
    }


def number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _retake_labels(document: Mapping[str, object], shots: Sequence[str]) -> set[str]:
    """Every frame_id/shot_id of the frames named by ``shots``."""
    labels = {str(s) for s in shots}
    for frame in rows_of(document.get("frames")):
        if any(frame_label_matches(frame, shot) for shot in shots):
            labels.update(str(frame.get(k)) for k in ("frame_id", "shot_id") if frame.get(k))
    return labels


def prepare(args: argparse.Namespace, regenerate: Sequence[str] | None = None) -> PrepResult:
    """Load and retime the plan. Shots in ``regenerate`` ignore existing takes."""
    from io_safety import load_structured
    from retime_plan import _load_takes, retime
    from take_select import parse_take_overrides

    try:
        raw = load_structured(args.input)
    except (OSError, ValueError) as exc:
        return closed("", "INPUT_INVALID", f"cannot load plan: {exc}")
    if not isinstance(raw, Mapping):
        return closed("", "INPUT_INVALID", "storyboard plan must be a mapping")
    document: dict[str, object] = {str(k): v for k, v in raw.items()}
    try:
        overrides = parse_take_overrides(args.take)
    except ValueError as exc:
        return closed("", "TAKE_OVERRIDE_INVALID", str(exc))
    try:
        takes = _load_takes(args.takes)
    except (OSError, ValueError) as exc:
        return closed("", "INPUT_INVALID", f"cannot load takes: {exc}")
    if regenerate:
        drop = _retake_labels(document, regenerate)
        if drop & set(overrides):
            return closed("", "TAKE_OVERRIDE_INVALID", "--take and --retake name the same shot")
        takes = [t for t in takes if str(t.get("shot", "")).strip() not in drop]
    plan = retime(
        document,
        args.provider,
        takes or None,
        accept_clock_delta=bool(args.accept_clock_delta),
        overrides=overrides or None,
    )
    if plan.get("status") != "PROPOSED":
        return closed(
            "",
            str(plan.get("code", "RETIME_NOT_COMPUTABLE")),
            str(plan.get("message", "retime did not produce a PROPOSED plan")),
        )
    return document, plan


def rows_of(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def timeline(plan: Mapping[str, object]) -> list[dict[str, object]]:
    """Edit-plan rows positioned on the final clock. ValueError on bad rows."""
    out: list[dict[str, object]] = []
    cursor = 0.0
    for row in rows_of(plan.get("edit_plan")):
        start_in = number(row.get("in"))
        end_out = number(row.get("out"))
        if start_in is None or end_out is None or end_out < start_in:
            raise ValueError(f"edit_plan row for shot {row.get('shot')!r} has invalid in/out")
        end = cursor + (end_out - start_in)
        out.append(
            {
                "shot": row.get("shot"),
                "source": row.get("source"),
                "in": start_in,
                "out": end_out,
                "start": round(cursor, 4),
                "end": round(end, 4),
            }
        )
        cursor = end
    return out


def frame_label_matches(frame: Mapping[str, object], shot: object) -> bool:
    label = str(shot)
    return any(
        frame.get(key) is not None and str(frame.get(key)) == label
        for key in ("frame_id", "shot_id")
    )


def frames_of(document: Mapping[str, object]) -> list[Mapping[str, object]]:
    return rows_of(document.get("frames"))


def emit(args: argparse.Namespace, action: str, payload: dict[str, object]) -> int:
    payload["action"] = action
    payload.setdefault("executes", False)
    if args.output:
        from io_safety import write_structured

        write_structured(args.output, payload)
    else:
        from runtime_deps import yaml_dump

        print(yaml_dump(payload, sort_keys=False))
    return 0 if payload.get("status") == "PROPOSED" else 4
