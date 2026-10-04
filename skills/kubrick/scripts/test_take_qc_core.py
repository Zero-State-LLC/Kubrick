#!/usr/bin/env python3
"""Take QC core. EP-01 fixtures only. No detector and no paid call."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
FIXTURE = ROOT / "evals" / "fixtures" / "ep01" / "take_qc_cases.yaml"
sys.path.insert(0, str(SCRIPTS))

import vision_observe  # noqa: E402
from structured_io import load_mapping  # noqa: E402

FAILING = {
    "b11r-t1": ["crop_line"],
    "v09-t1": ["push_drift"],
    "b09r-t2": ["head_ratio", "edge_cut", "subject_centroid"],
    "v07-t1": ["light_emitter"],
    "v12-t1": ["light_emitter"],
    "v01-t1": ["light_emitter"],
    "v09-debris-t1": ["small_motion"],
    "v09-debris-t2": ["small_motion"],
    "v13-t1": ["open_copy"],
    "landscape-rejected": ["aspect"],
    "b10-hands": ["material"],
    "lens-flip-34-left": ["lens_side"],
    "b11-b12-copy": ["ref_copy"],
}
PASSING = (
    "b11r-mid-thigh",
    "v09-t2",
    "b09r-t3",
    "v07-t2",
    "v12-t2",
    "v01-t2",
    "v13-trimmed",
    "b14r-t2",
    "b11-front",
    "b12-reverse",
    "start-hold-clear",
)


def _cases() -> dict[str, dict[str, object]]:
    document = load_mapping(FIXTURE)
    rows = document.get("cases")
    assert isinstance(rows, list)
    found: dict[str, dict[str, object]] = {}
    for item in rows:
        assert isinstance(item, dict)
        found[str(item["id"])] = item
    return found


def _codes(report: dict[str, object]) -> list[str]:
    defects = report["defects"]
    assert isinstance(defects, list)
    codes: list[str] = []
    for item in defects:
        assert isinstance(item, dict)
        assert item["score"] == 2
        assert "t_start" in item and "t_end" in item
        assert item["hold_id"]
        codes.append(str(item["defect_code"]))
    return codes


def test_ep01_failures_and_passing_counterparts() -> None:
    cases = _cases()
    for case_id, expected in FAILING.items():
        report = vision_observe.score_take(cases[case_id])
        assert report["status"] == "PROPOSED", case_id
        assert report["authority"] == "PROPOSED"
        assert _codes(report) == expected
    for case_id in PASSING:
        report = vision_observe.score_take(cases[case_id])
        assert report["status"] == "PROPOSED"
        assert _codes(report) == []
    marginal = vision_observe.score_take(cases["b09r-t3"])
    checks = marginal["checks"]
    assert isinstance(checks, list)
    head = next(
        item for item in checks if isinstance(item, dict) and item.get("hold_id") == "head_size"
    )
    assert isinstance(head, dict)
    assert head["score"] == 1
    assert head["head_source"] == "dome"
    copied = vision_observe.score_take(cases["v13-t1"])
    assert _codes(copied) == ["open_copy"]
    defect = copied["defects"]
    assert isinstance(defect, list) and isinstance(defect[0], dict)
    assert defect[0]["warning_code"] == "REF_OPEN_COPY"
    held = vision_observe.score_take(cases["start-hold-t1"])
    assert _codes(held) == ["start_hold"]
    held_defect = held["defects"]
    assert isinstance(held_defect, list) and isinstance(held_defect[0], dict)
    assert held_defect[0]["warning_code"] == "START_HOLD"
    partial = vision_observe.score_take(cases["b10-refs-only"])
    assert _codes(partial) == []
    assert partial["partial"] is True
    debris = [case_id for case_id in cases if case_id.startswith("v09-debris")]
    assert debris == ["v09-debris-t1", "v09-debris-t2"]
    for case_id in debris:
        assert _codes(vision_observe.score_take(cases[case_id])) == ["small_motion"]


def test_samples_cover_ends_middle_and_hold() -> None:
    assert vision_observe.sample_times(4.0, [1.5], 1.6) == [0.0, 1.5, 1.6, 2.0, 4.0]
    report = vision_observe.score_take(_cases()["v09-t1"])
    assert report["samples"] == [0.0, 1.6, 2.0, 4.0]


def test_non_human_head_uses_the_dome_and_does_not_invent_a_ratio() -> None:
    ratio, source = vision_observe.resolve_head_ratio(
        {"pose_landmarks": False, "head_source": "dome", "head_ratio": 0.41},
        "non_human",
    )
    assert ratio == 0.41
    assert source == "dome"
    missing, why = vision_observe.resolve_head_ratio(
        {"pose_landmarks": False, "head_source": "pose", "head_ratio": 0.41},
        "non_human",
    )
    assert missing is None
    assert why == "NOT_COMPUTABLE"
    report = vision_observe.score_take({
        "id": "dome-missing",
        "duration_seconds": 4,
        "subject": "non_human",
        "ask": {"head_ratio": [0.40, 0.45]},
        "frames": [{"t": 0, "pose_landmarks": False, "head_source": "pose", "head_ratio": 0.50}],
    })
    assert report["status"] == "NOT_COMPUTABLE"
    assert report["defects"] == []


def test_cli_scores_one_case_without_a_detector() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "vision_observe.py"),
            "--input",
            str(FIXTURE),
            "--case",
            "v09-t2",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["defects"] == []
    assert report["status"] == "PROPOSED"
