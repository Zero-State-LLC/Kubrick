#!/usr/bin/env python3
"""Take QC core. Scores fixture measurements. Does not call a detector or a paid API.

Samples are the first frame, the middle, the last frame, each cut, and the end
of the 1.6 s hold. A non-human head with no pose landmarks uses the head-dome
measurement. A clean take has an empty defect list. Reports stay PROPOSED.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence

from kubrick.runtime.io_safety import write_text_bounded
from kubrick.runtime.structured_io import load_mapping

HOLD_SECONDS = 1.6
_PUSH = frozenset({"push-in", "pull-out"})
_LIGHT_ASK = "emitting"


def sample_times(
    duration: float,
    cuts: Sequence[float] | None = None,
    hold_seconds: float = HOLD_SECONDS,
) -> list[float]:
    """Clock points a take QC reads. Empty when the duration is not positive."""
    if duration <= 0:
        return []
    points = [0.0, duration / 2.0, duration, min(hold_seconds, duration)]
    for cut in cuts or []:
        if 0.0 <= cut <= duration:
            points.append(cut)
    return sorted({round(point, 3) for point in points})


def resolve_head_ratio(
    frame: Mapping[str, object], subject: str,
) -> tuple[float | None, str]:
    """Pose ratio when landmarks exist. Otherwise the dome, for a non-human head."""
    ratio = _float(frame.get("head_ratio"))
    source = frame.get("head_source")
    source_name = source.strip() if isinstance(source, str) else ""
    pose = frame.get("pose_landmarks") is True
    if pose and source_name == "pose" and ratio is not None:
        return ratio, "pose"
    if subject != "human" and source_name == "dome" and ratio is not None:
        return ratio, "dome"
    if subject == "human" and pose and ratio is not None:
        return ratio, "pose"
    return None, "NOT_COMPUTABLE"


def score_take(document: Mapping[str, object]) -> dict[str, object]:
    """Score one take. ``expect`` is ignored so fixtures cannot grade themselves."""
    duration = _float(document.get("duration_seconds"))
    if duration is None or duration <= 0:
        return _closed(str(document.get("id") or ""), "duration_seconds is missing or not positive")
    frames = _frames(document.get("frames"))
    if not frames:
        return _closed(str(document.get("id") or ""), "frames are missing")
    ask = _mapping(document.get("ask")) or {}
    subject = str(document.get("subject") or "non_human")
    checks = [
        *_head(ask, frames, subject),
        *_crop(ask, frames),
        *_edges(frames),
        *_centroids(frames),
        *_lights(ask, frames),
        *_hands(ask, frames),
        *_aspect(ask, frames),
        *_lens(ask, frames),
        *_flag(document, "small_motion", "motion", "small_motion", None),
        *_flag(document, "open_copy", "open", "open_copy", "REF_OPEN_COPY"),
        *_flag(document, "ref_copy", "reference", "ref_copy", None),
        *_flag(document, "start_hold", "start", "start_hold", "START_HOLD"),
    ]
    blocked = any(row.get("status") == "NOT_COMPUTABLE" for row in checks)
    status = "NOT_COMPUTABLE" if blocked else "PROPOSED"
    defects = [_defect(row) for row in checks if row.get("score") == 2]
    hold = _float(document.get("hold_seconds")) or HOLD_SECONDS
    report: dict[str, object] = {
        "status": status,
        "authority": "NOT_COMPUTABLE" if blocked else "PROPOSED",
        "shot_id": str(document.get("id") or ""),
        "samples": sample_times(duration, _cuts(document), hold),
        "checks": checks,
        "defects": defects,
    }
    if document.get("partial") is True:
        report["partial"] = True
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score a take-QC fixture. No detector and no spend.",
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--case", help="case id when the file holds several")
    parser.add_argument("--out")
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        document = load_mapping(args.input)
    except (OSError, ValueError) as exc:
        print(json.dumps(_closed("", str(exc)), indent=2))
        return 2
    if args.case:
        found = _case(document, args.case)
        if found is None:
            print(json.dumps(_closed(args.case, "case is not in the fixture"), indent=2))
            return 2
        report: object = score_take(found)
    elif isinstance(document.get("cases"), list):
        report = [score_take(item) for item in _frames(document.get("cases"))]
    else:
        report = score_take(document)
    text = json.dumps(report, indent=2)
    if args.out:
        write_text_bounded(args.out, text + "\n")
    print(text)
    return 2 if _failed(report) else 0


def _failed(report: object) -> bool:
    rows = list(report) if isinstance(report, list) else [report]
    for item in rows:
        if isinstance(item, dict) and item.get("status") == "NOT_COMPUTABLE":
            return True
    return False


def _closed(shot_id: str, message: str) -> dict[str, object]:
    return {
        "status": "NOT_COMPUTABLE",
        "authority": "NOT_COMPUTABLE",
        "shot_id": shot_id,
        "samples": [],
        "checks": [],
        "defects": [],
        "message": message,
    }


def _float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _mapping(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    return {str(key): item for key, item in value.items()}


def _frames(value: object) -> list[dict[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [row for item in value if (row := _mapping(item)) is not None]


def _cuts(document: Mapping[str, object]) -> list[float]:
    raw = document.get("cuts")
    if not isinstance(raw, list):
        return []
    found: list[float] = []
    for item in raw:
        number = _float(item)
        if number is not None:
            found.append(number)
    return found


def _span(frames: Sequence[Mapping[str, object]]) -> tuple[float, float]:
    times = [number for frame in frames if (number := _float(frame.get("t"))) is not None]
    if not times:
        return 0.0, 0.0
    return min(times), max(times)


def _row(
    hold_id: str,
    score: int,
    start: float,
    end: float,
    code: str | None = None,
    warning: str | None = None,
) -> dict[str, object]:
    status = "FAIL" if score >= 2 else "MARGINAL" if score == 1 else "PASS"
    found: dict[str, object] = {
        "hold_id": hold_id,
        "score": score,
        "t_start": start,
        "t_end": end,
        "status": status,
    }
    if score >= 2 and code:
        found["defect_code"] = code
    if score >= 2 and warning:
        found["warning_code"] = warning
    return found


def _gap(hold_id: str, message: str) -> dict[str, object]:
    return {"hold_id": hold_id, "status": "NOT_COMPUTABLE", "message": message}


def _defect(row: Mapping[str, object]) -> dict[str, object]:
    found: dict[str, object] = {
        "hold_id": row.get("hold_id"),
        "score": 2,
        "t_start": row.get("t_start"),
        "t_end": row.get("t_end"),
        "defect_code": row.get("defect_code"),
    }
    warning = row.get("warning_code")
    if isinstance(warning, str):
        found["warning_code"] = warning
    return found


def _ratio_score(ratio: float, low: float, high: float) -> int:
    if low <= ratio <= high:
        return 0
    if low - 0.04 <= ratio <= high + 0.04:
        return 1
    return 2


def _band(ask: Mapping[str, object]) -> tuple[float, float] | None:
    raw = ask.get("head_ratio")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) != 2:
        return None
    low, high = _float(raw[0]), _float(raw[1])
    if low is None or high is None or low > high:
        return None
    return low, high


def _head(
    ask: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
    subject: str,
) -> list[dict[str, object]]:
    move = ask.get("move")
    push = isinstance(move, str) and move.strip() in _PUSH
    band = _band(ask)
    if band is None and not push:
        return []
    if band is None:
        return [_gap("head_size", "push or pull has no head_ratio band")]
    measured: list[tuple[float, float, str]] = []
    for frame in frames:
        ratio, source = resolve_head_ratio(frame, subject)
        if ratio is None:
            return [_gap("head_size", "head ratio is not computable from pose or the dome")]
        measured.append((_float(frame.get("t")) or 0.0, ratio, source))
    _start, end = measured[0][0], measured[-1][0]
    score = _ratio_score(measured[-1][1], band[0], band[1])
    code = "push_drift" if push and score >= 2 else "head_ratio" if score >= 2 else None
    row = _row("head_size", score, measured[-1][0] if score else _start, end, code)
    row["head_source"] = measured[-1][2]
    return [row]


def _crop(
    ask: Mapping[str, object], frames: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    crop = ask.get("crop")
    if not isinstance(crop, str) or crop.strip() != "knees_up":
        return []
    start, end = _span(frames)
    visible: list[bool] = []
    for frame in frames:
        flag = frame.get("ankles_visible")
        if not isinstance(flag, bool):
            return [_gap("crop", "ankles_visible is missing")]
        visible.append(flag)
    if any(visible):
        return [_row("crop", 2, start, end, "crop_line")]
    return [_row("crop", 0, start, end)]


def _edges(frames: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    if not any("edge_cut" in frame for frame in frames):
        return []
    start, end = _span(frames)
    for frame in frames:
        flag = frame.get("edge_cut")
        if not isinstance(flag, bool):
            return [_gap("edge", "edge_cut is missing")]
        if flag:
            return [_row("edge", 2, start, end, "edge_cut")]
    return [_row("edge", 0, start, end)]


def _centroids(frames: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    if not any("subject_centroid" in frame for frame in frames):
        return []
    start, end = _span(frames)
    off = False
    for frame in frames:
        raw = frame.get("subject_centroid")
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) != 2:
            return [_gap("centroid", "subject_centroid is missing")]
        x, y = _float(raw[0]), _float(raw[1])
        if x is None or y is None:
            return [_gap("centroid", "subject_centroid is missing")]
        if x < 0.18 or x > 0.82 or y < 0.12 or y > 0.88:
            off = True
    if off:
        return [_row("centroid", 2, start, end, "subject_centroid")]
    return [_row("centroid", 0, start, end)]


def _light_rows(value: object) -> list[dict[str, object]] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    return [row for item in value if (row := _mapping(item)) is not None]


def _lights(
    ask: Mapping[str, object], frames: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    asked = _light_rows(ask.get("lights"))
    if not asked:
        return []
    start, end = _span(frames)
    checks: list[dict[str, object]] = []
    for spec in asked:
        region = spec.get("region")
        want = spec.get(_LIGHT_ASK)
        if not isinstance(region, str) or not isinstance(want, bool):
            return [_gap("light", "light ask is incomplete")]
        seen: bool | None = None
        for frame in frames:
            rows = _light_rows(frame.get("lights"))
            if rows is None:
                return [_gap(region, "light measurement is missing")]
            for row in rows:
                if row.get("region") != region:
                    continue
                emitting = row.get(_LIGHT_ASK)
                if not isinstance(emitting, bool):
                    return [_gap(region, "light measurement is missing")]
                seen = emitting
        if seen is None:
            return [_gap(region, "light measurement is missing")]
        score = 2 if seen != want else 0
        checks.append(_row(region, score, start, end, "light_emitter" if score == 2 else None))
    return checks


def _hands(
    ask: Mapping[str, object], frames: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    want = ask.get("hands")
    if not isinstance(want, str) or not want.strip():
        return []
    start, end = _span(frames)
    for frame in frames:
        got = frame.get("hands")
        if not isinstance(got, str) or not got.strip():
            return [_gap("hands", "hands measurement is missing")]
        if got.strip() != want.strip():
            return [_row("hands", 2, start, end, "material")]
    return [_row("hands", 0, start, end)]


def _aspect(
    ask: Mapping[str, object], frames: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    want = ask.get("aspect")
    if not isinstance(want, str) or not want.strip():
        return []
    start, end = _span(frames)
    for frame in frames:
        got = frame.get("aspect")
        if not isinstance(got, str) or not got.strip():
            return [_gap("aspect", "aspect is missing")]
        if got.strip() != want.strip():
            return [_row("aspect", 2, start, end, "aspect")]
    return [_row("aspect", 0, start, end)]


def _lens(
    ask: Mapping[str, object], frames: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    if "lens_side" not in ask:
        return []
    start, end = _span(frames)
    for frame in frames:
        got = frame.get("lens_side")
        if not isinstance(got, str) or not got.strip():
            return [_gap("lens", "lens_side is missing")]
        if got.strip() == "flipped":
            return [_row("lens", 2, start, end, "lens_side")]
    return [_row("lens", 0, start, end)]


def _flag(
    document: Mapping[str, object],
    key: str,
    hold_id: str,
    code: str,
    warning: str | None,
) -> list[dict[str, object]]:
    if key not in document:
        return []
    value = document.get(key)
    frames = _frames(document.get("frames"))
    start, end = _span(frames)
    if not isinstance(value, bool):
        return [_gap(hold_id, f"{key} is not a boolean")]
    if value:
        return [_row(hold_id, 2, start, end, code, warning)]
    return [_row(hold_id, 0, start, end)]


def _case(document: Mapping[str, object], case_id: str) -> dict[str, object] | None:
    for item in _frames(document.get("cases")):
        if str(item.get("id") or "") == case_id:
            return item
    if str(document.get("id") or "") == case_id:
        return dict(document)
    return None


if __name__ == "__main__":
    sys.exit(main())
