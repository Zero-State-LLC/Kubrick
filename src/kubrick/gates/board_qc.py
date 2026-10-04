#!/usr/bin/env python3
"""Board gate. Fixture measurements only. No vision call and no video spend.

A contradicted lock or a knees-up ask on a full-body plate blocks the video
packet. A start frame with no image evidence is a warning, not a carrier.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence

from kubrick.plan.lock_carriers import carrier_for
from kubrick.qc.vision_observe import score_take
from kubrick.runtime.io_safety import write_text_bounded
from kubrick.runtime.structured_io import load_mapping

_SAFE = (0.13, 0.87, 0.115, 0.748)
_WARNINGS = {
    "edge_cut": "EDGE_CUT",
    "safe_zone": "SAFE_ZONE_VIOLATION",
    "ref_copy": "PREV_BOARD_REF_COPY",
    "asymmetry_turn": "ASYMMETRY_TURN_RISK",
}


def score_board(document: Mapping[str, object]) -> dict[str, object]:
    """Score one board. Shared checks reuse the take-QC fixture scorer."""
    frame = _one(document.get("frames"))
    measured = _measured(frame)
    ask = _mapping(document.get("ask")) or _mapping(frame.get("ask")) or {}
    take = score_take({
        "id": document.get("id") or frame.get("frame_id") or "board",
        "duration_seconds": 1,
        "subject": document.get("subject") or "non_human",
        "ask": ask,
        "frames": [measured],
        "ref_copy": measured.get("ref_copy") is True,
    })
    extra = _extra(ask, measured)
    defects = [
        *_defects(take.get("defects")),
        *[row for row in extra if row.get("score") == 2],
    ]
    missing = [
        row for row in [*_rows(take.get("checks")), *extra]
        if row.get("status") == "NOT_COMPUTABLE"
    ]
    status = "NOT_COMPUTABLE" if missing else "PROPOSED"
    return {
        "status": status,
        "authority": "NOT_COMPUTABLE" if status == "NOT_COMPUTABLE" else "PROPOSED",
        "shot_id": take.get("shot_id"),
        "checks": [*_rows(take.get("checks")), *extra],
        "defects": defects,
    }


def prep_effects(
    document: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
) -> tuple[list[dict[str, str | None]], list[str]]:
    """Warnings and blocking errors for frames that carry board measurements."""
    from kubrick.plan.continuity_locks import frame_id, warning

    warnings: list[dict[str, str | None]] = []
    errors: list[str] = []
    for index, frame in enumerate(frames, start=1):
        if "board_measurements" not in frame and "board_evidence" not in frame:
            continue
        shot = frame_id(frame, index)
        report = score_board({"id": shot, "ask": frame.get("ask") or {}, "frames": [frame]})
        for defect in _rows(report.get("defects")):
            code = str(defect.get("warning_code") or defect.get("defect_code") or "BOARD")
            if code in {"crop_line", "BOARD_LOCK_CONTRADICTED"} or defect.get("blocks"):
                errors.append(f"{code} shot {shot}")
            else:
                warnings.append(warning(
                    code, shot, f"{code} on {shot}", "fix the board before spend",
                ))
        for lock in _locks(document):
            record = carrier_for(
                document,
                frame,
                str(lock.get("kind") or "lock"),
                str(lock.get("negative") or lock.get("positive") or lock.get("id") or ""),
                None,
                lock,
            )
            if record.get("status") == "contradicted":
                code = str(record.get("code") or "BOARD_LOCK_CONTRADICTED")
                detail = record.get("detail")
                message = f"{code} shot {shot}"
                if isinstance(detail, str):
                    message = f"{message} {detail}"
                errors.append(message)
            elif record.get("code") == "BOARD_LOCK_UNVERIFIED":
                warnings.append(warning(
                    "BOARD_LOCK_UNVERIFIED",
                    shot,
                    f"start frame on {shot} has no image evidence",
                    "verify the board or use refs-only",
                ))
    return warnings, errors


def blocks_video_packet(
    document: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Refuse a video packet when the board contradicts a lock or the crop."""
    _warnings, errors = prep_effects(document, frames)
    if not errors:
        return {
            "status": "PROPOSED",
            "authority": "PROPOSED",
            "blocks_packet": False,
            "errors": [],
        }
    return {
        "status": "NOT_COMPUTABLE",
        "authority": "NOT_COMPUTABLE",
        "blocks_packet": True,
        "code": errors[0].split()[0],
        "errors": errors,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score a board fixture. No vision call and no spend.",
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--case")
    parser.add_argument("--out")
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        document = load_mapping(args.input)
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "NOT_COMPUTABLE", "message": str(exc)}, indent=2))
        return 2
    chosen = document
    if args.case:
        found = _find(document, args.case)
        if found is None:
            print(json.dumps({"status": "NOT_COMPUTABLE", "message": "case is missing"}, indent=2))
            return 2
        chosen = found
    report = score_board(chosen)
    text = json.dumps(report, indent=2)
    if args.out:
        write_text_bounded(args.out, text + "\n")
    print(text)
    return 2 if report.get("status") == "NOT_COMPUTABLE" else 0


def _extra(ask: Mapping[str, object], measured: Mapping[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    rows.extend(_band(ask, measured, "headroom_frac", "headroom"))
    rows.extend(_band(ask, measured, "eyeline_y", "eyeline"))
    rows.extend(_safe(measured))
    rows.extend(_tilt(ask, measured))
    rows.extend(_flag_off(measured, "lead_room_ok", "lead_room", "lead_room"))
    rows.extend(_axis(measured))
    rows.extend(_brightness(ask, measured))
    rows.extend(_text(ask, measured))
    rows.extend(_count(ask, measured))
    rows.extend(_turn(measured))
    return rows


def _band(
    ask: Mapping[str, object],
    measured: Mapping[str, object],
    key: str,
    hold_id: str,
) -> list[dict[str, object]]:
    raw = ask.get(key)
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) != 2:
        return []
    low, high = _float(raw[0]), _float(raw[1])
    value = _float(measured.get(key))
    if low is None or high is None or value is None:
        return [_gap_row(hold_id, f"{key} is missing")]
    score = 0 if low <= value <= high else 2
    return [_defect_row(hold_id, score, key if score == 2 else None)]


def _safe(measured: Mapping[str, object]) -> list[dict[str, object]]:
    if "face_point" not in measured:
        return []
    raw = measured.get("face_point")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) != 2:
        return [_gap_row("safe_zone", "face_point is missing")]
    x, y = _float(raw[0]), _float(raw[1])
    if x is None or y is None:
        return [_gap_row("safe_zone", "face_point is missing")]
    inside = _SAFE[0] <= x <= _SAFE[1] and _SAFE[2] <= y <= _SAFE[3]
    code = None if inside else "safe_zone"
    warning_code = None if inside else "SAFE_ZONE_VIOLATION"
    return [_defect_row("safe_zone", 0 if inside else 2, code, warning_code)]


def _tilt(ask: Mapping[str, object], measured: Mapping[str, object]) -> list[dict[str, object]]:
    if "horizon_tilt" not in measured:
        return []
    limit = _float(ask.get("horizon_tilt_max"))
    if limit is None:
        limit = 2.0
    value = _float(measured.get("horizon_tilt"))
    if value is None:
        return [_gap_row("horizon", "horizon_tilt is missing")]
    score = 2 if abs(value) > limit else 0
    return [_defect_row("horizon", score, "horizon_tilt" if score == 2 else None)]


def _flag_off(
    measured: Mapping[str, object], key: str, hold_id: str, code: str,
) -> list[dict[str, object]]:
    if key not in measured:
        return []
    value = measured.get(key)
    if not isinstance(value, bool):
        return [_gap_row(hold_id, f"{key} is missing")]
    return [_defect_row(hold_id, 0 if value else 2, None if value else code)]


def _axis(measured: Mapping[str, object]) -> list[dict[str, object]]:
    if "axis_crossed" not in measured:
        return []
    crossed = measured.get("axis_crossed")
    if not isinstance(crossed, bool):
        return [_gap_row("axis", "axis_crossed is missing")]
    bridged = measured.get("axis_bridge") is True
    score = 2 if crossed and not bridged else 0
    return [_defect_row("axis", score, "screen_dir_180" if score == 2 else None)]


def _brightness(
    ask: Mapping[str, object], measured: Mapping[str, object],
) -> list[dict[str, object]]:
    if "brightness" not in measured and "brightness_max" not in ask:
        return []
    limit = _float(ask.get("brightness_max"))
    value = _float(measured.get("brightness"))
    if limit is None or value is None:
        return [_gap_row("brightness", "brightness is missing")]
    score = 2 if value > limit else 0
    return [_defect_row("brightness", score, "brightness" if score == 2 else None)]


def _text(ask: Mapping[str, object], measured: Mapping[str, object]) -> list[dict[str, object]]:
    if "text_render" not in ask and "text_present" not in measured:
        return []
    present = measured.get("text_present")
    if not isinstance(present, bool):
        return [_gap_row("text", "text_present is missing")]
    allowed = ask.get("text_render") is True
    score = 2 if present and not allowed else 0
    return [_defect_row("text", score, "text_render" if score == 2 else None)]


def _count(ask: Mapping[str, object], measured: Mapping[str, object]) -> list[dict[str, object]]:
    if "char_count" not in ask and "char_count" not in measured:
        return []
    want = ask.get("char_count")
    got = measured.get("char_count")
    if isinstance(want, bool) or isinstance(got, bool):
        return [_gap_row("characters", "char_count is missing")]
    if not isinstance(want, int) or not isinstance(got, int):
        return [_gap_row("characters", "char_count is missing")]
    score = 0 if got == want else 2
    return [_defect_row("characters", score, "char_count" if score == 2 else None)]


def _turn(measured: Mapping[str, object]) -> list[dict[str, object]]:
    if measured.get("asymmetry_locked") is not True:
        return []
    pose = measured.get("pose")
    if not isinstance(pose, str):
        return [_gap_row("asymmetry", "pose is missing")]
    risk = pose.strip() in {"three_quarter", "three_quarter_l", "three_quarter_r"}
    return [_defect_row(
        "asymmetry",
        2 if risk else 0,
        "asymmetry_turn" if risk else None,
        "ASYMMETRY_TURN_RISK" if risk else None,
    )]


def _defect_row(
    hold_id: str,
    score: int,
    code: str | None,
    warning: str | None = None,
) -> dict[str, object]:
    status = "FAIL" if score >= 2 else "PASS"
    row: dict[str, object] = {
        "hold_id": hold_id,
        "score": score,
        "t_start": 0.0,
        "t_end": 0.0,
        "status": status,
    }
    if score >= 2 and code:
        row["defect_code"] = code
        row["warning_code"] = warning or _WARNINGS.get(code, code)
        if code in {"crop_line", "safe_zone"}:
            row["blocks"] = True
    return row


def _gap_row(hold_id: str, message: str) -> dict[str, object]:
    return {"hold_id": hold_id, "status": "NOT_COMPUTABLE", "message": message}


def _defects(value: object) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for row in _rows(value):
        code = row.get("defect_code")
        if code == "edge_cut":
            row = {**row, "warning_code": "EDGE_CUT", "blocks": False}
        elif code == "ref_copy":
            row = {**row, "warning_code": "PREV_BOARD_REF_COPY"}
        elif code == "crop_line":
            row = {**row, "blocks": True}
        found.append(row)
    return found


def _measured(frame: Mapping[str, object]) -> dict[str, object]:
    raw = frame.get("board_measurements")
    if isinstance(raw, dict):
        return {str(key): value for key, value in raw.items()}
    return {str(key): value for key, value in frame.items() if key != "board_measurements"}


def _one(value: object) -> dict[str, object]:
    rows = _rows(value)
    if rows:
        return rows[0]
    return {}


def _rows(value: object) -> list[dict[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _mapping(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    return {str(key): item for key, item in value.items()}


def _locks(document: Mapping[str, object]) -> list[dict[str, object]]:
    return _rows(document.get("locks"))


def _float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _find(document: Mapping[str, object], case_id: str) -> dict[str, object] | None:
    for item in _rows(document.get("cases")):
        if str(item.get("id") or "") == case_id:
            return item
    return None


if __name__ == "__main__":
    sys.exit(main())
