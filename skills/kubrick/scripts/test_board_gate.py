#!/usr/bin/env python3
"""Board gate. Fixture measurements only. No vision call and no video spend."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import board_qc  # noqa: E402
from lock_carriers import carrier_for  # noqa: E402
from shot_plan import collect_prep  # noqa: E402
from structured_io import load_mapping  # noqa: E402

FIXTURE = ROOT / "evals" / "fixtures" / "ep01" / "board_gate_cases.yaml"
CHECKS = {
    "aspect-fail": "aspect",
    "head-ratio-fail": "head_ratio",
    "headroom-fail": "headroom_frac",
    "crop-fail": "crop_line",
    "centroid-fail": "subject_centroid",
    "edge-fail": "edge_cut",
    "safe-zone-fail": "safe_zone",
    "horizon-fail": "horizon_tilt",
    "lead-room-fail": "lead_room",
    "lens-fail": "lens_side",
    "axis-fail": "screen_dir_180",
    "eyeline-fail": "eyeline_y",
    "light-fail": "light_emitter",
    "brightness-fail": "brightness",
    "ref-copy-fail": "ref_copy",
    "text-fail": "text_render",
    "count-fail": "char_count",
    "asymmetry-fail": "asymmetry_turn",
}
WARNINGS = {
    "edge-fail": "EDGE_CUT",
    "safe-zone-fail": "SAFE_ZONE_VIOLATION",
    "ref-copy-fail": "PREV_BOARD_REF_COPY",
    "asymmetry-fail": "ASYMMETRY_TURN_RISK",
}
HANDS = {
    "id": "silicon-hands",
    "kind": "material",
    "text": "silicon hands",
    "critical": True,
}


def _cases() -> dict[str, dict[str, object]]:
    document = load_mapping(FIXTURE)
    rows = document.get("cases")
    assert isinstance(rows, list)
    return {str(item["id"]): item for item in rows if isinstance(item, dict)}


def _codes(report: dict[str, object]) -> list[str]:
    defects = report["defects"]
    assert isinstance(defects, list)
    return [str(item["defect_code"]) for item in defects if isinstance(item, dict)]


def test_board_checks_fail_and_a_clean_board_does_not() -> None:
    cases = _cases()
    assert len(CHECKS) == 18
    for case_id, code in CHECKS.items():
        report = board_qc.score_board(cases[case_id])
        assert report["status"] == "PROPOSED", case_id
        assert code in _codes(report)
    for case_id, warning in WARNINGS.items():
        report = board_qc.score_board(cases[case_id])
        defects = report["defects"]
        assert isinstance(defects, list)
        assert any(
            isinstance(item, dict) and item.get("warning_code") == warning for item in defects
        )
    clean = board_qc.score_board(cases["clean-board"])
    assert clean["status"] == "PROPOSED"
    assert _codes(clean) == []


def test_human_hands_block_and_silicon_hands_verify() -> None:
    contradicted = {
        "frame_id": "b10",
        "duration_seconds": 4,
        "characters": ["myslef"],
        "start_frame": {"asset": "b10.png"},
        "board_measurements": {"hands": "human"},
    }
    document = {"locks": [HANDS], "frames": [contradicted]}
    record = carrier_for(document, contradicted, "material", "silicon hands", "myslef", HANDS)
    assert record["carrier"] == "contradicted"
    assert record["status"] == "contradicted"
    assert record["code"] == "BOARD_LOCK_CONTRADICTED"
    assert record["detail"] == "HUMAN_HAND_ON_SILICON_LOCK"
    assert "refs-only" in str(record["recommendation"])
    gate = board_qc.blocks_video_packet(document, [contradicted])
    assert gate["blocks_packet"] is True
    assert gate["code"] == "BOARD_LOCK_CONTRADICTED"
    prep = collect_prep(document, [contradicted], "keyframe")
    assert any("BOARD_LOCK_CONTRADICTED" in item for item in prep.errors)
    assert any("HUMAN_HAND_ON_SILICON_LOCK" in item for item in prep.errors)
    verified = {
        "frame_id": "b10-ok",
        "duration_seconds": 4,
        "characters": ["myslef"],
        "start_frame": {"asset": "b10-silicon.png"},
        "board_measurements": {"hands": "silicon"},
    }
    ok = carrier_for(document, verified, "material", "silicon hands", "myslef", HANDS)
    assert ok["carrier"] == "start_frame"
    assert ok["status"] == "verified"


def test_full_body_plate_fails_knees_up_before_spend() -> None:
    frame = {
        "frame_id": "shot-11",
        "duration_seconds": 4,
        "ask": {"crop": "knees_up"},
        "board_measurements": {"ankles_visible": True},
    }
    gate = board_qc.blocks_video_packet({"frames": [frame]}, [frame])
    assert gate["blocks_packet"] is True
    assert gate["code"] == "crop_line"


def test_cut_does_not_inherit_a_start_and_a_chain_can() -> None:
    document = {"locks": [HANDS]}
    cut = {
        "frame_id": "cut-01",
        "join": "cut",
        "start_frame": {"asset": "prev.png", "source_shot": "prev"},
    }
    inherited = carrier_for(document, cut, "material", "silicon hands", None, HANDS)
    assert inherited["carrier"] != "start_frame"
    assert inherited["carrier"] != "unverified"
    chained = {
        "frame_id": "chain-01",
        "join": {"chain_from": "prev"},
        "board_evidence": [{"lock_id": "silicon-hands", "status": "verified"}],
    }
    kept = carrier_for(document, chained, "material", "silicon hands", None, HANDS)
    assert kept["carrier"] == "start_frame"
    assert kept["status"] == "verified"
    bare = {
        "frame_id": "bare-01",
        "start_frame": {"asset": "still.png"},
    }
    missing = carrier_for(
        document, bare, "light", "no glow", None, {"id": "glow", "negative": "no glow"},
    )
    assert missing["carrier"] == "unverified"
    assert missing["status"] == "unverified"
