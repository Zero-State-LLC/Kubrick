#!/usr/bin/env python3
"""Numeric framing. Fixture fields only. No provider call."""
from __future__ import annotations

import sys
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from adapt_keyframe import _prompts  # noqa: E402
from framing import (  # noqa: E402
    board_prompt,
    end_anchor,
    framing_warnings,
    motion_line,
    needs_end_anchor,
    safe_box,
)
from shot_plan import collect_prep  # noqa: E402
from structured_io import load_mapping  # noqa: E402

FIXTURE = ROOT / "evals" / "fixtures" / "ep01" / "framing_cases.yaml"
SCHEMA = ROOT / "schemas" / "storyboard-symbolic-state.schema.yaml"
SIX = (
    "VIDEO_REFRAME_IGNORED",
    "WIDE_PLATE_OVERRIDES_CROP",
    "ADJECTIVE_PROPORTION",
    "MOVE_WITHOUT_END_ANCHOR",
    "MOVE_TARGET_MISSING",
    "AXIS_CROSS_UNBRIDGED",
)
CASE_CODE = {
    "video-reframe": "VIDEO_REFRAME_IGNORED",
    "wide-plate": "WIDE_PLATE_OVERRIDES_CROP",
    "adjective": "ADJECTIVE_PROPORTION",
    "move-without-end": "MOVE_WITHOUT_END_ANCHOR",
    "move-target-missing": "MOVE_TARGET_MISSING",
    "axis-cross": "AXIS_CROSS_UNBRIDGED",
}


def _cases() -> dict[str, dict[str, object]]:
    document = load_mapping(FIXTURE)
    rows = document.get("cases")
    assert isinstance(rows, list)
    return {str(item["id"]): item for item in rows if isinstance(item, dict)}


def _frames(case: dict[str, object]) -> list[dict[str, object]]:
    rows = case.get("frames")
    assert isinstance(rows, list)
    return [item for item in rows if isinstance(item, dict)]


def _codes(frames: list[dict[str, object]]) -> list[str]:
    return [str(item["code"]) for item in framing_warnings({}, frames)]


def test_six_codes_and_the_passing_fixture() -> None:
    cases = _cases()
    for case_id, code in CASE_CODE.items():
        assert code in _codes(_frames(cases[case_id])), case_id
    plate = _codes(_frames(cases["wide-plate"]))
    assert "CROP_UNREACHABLE_FROM_PLATE" in plate
    precrop = _codes(_frames(cases["wide-plate-precrop"]))
    assert "WIDE_PLATE_OVERRIDES_CROP" not in precrop
    assert "CROP_UNREACHABLE_FROM_PLATE" not in precrop
    assert "AXIS_CROSS_UNBRIDGED" not in _codes(_frames(cases["axis-bridged"]))
    passing = _codes(_frames(cases["passing"]))
    banned = (*SIX, "CROP_UNREACHABLE_FROM_PLATE", "MOVE_CHAIN_CONFLICT", "END_IMAGE_UNSUPPORTED")
    for code in banned:
        assert code not in passing
    two = _codes(_frames(cases["two-moves"]))
    one = _codes(_frames(cases["one-move"]))
    assert "MOVE_CHAIN_CONFLICT" in two
    assert "MOVE_CHAIN_CONFLICT" not in one
    assert motion_line(_frames(cases["two-moves"])[0]) is None
    assert motion_line(_frames(cases["one-move"])[0]) == "steps as push-in"


def test_shot_09_anchor_prompt_and_motion_line() -> None:
    frame = _frames(_cases()["shot-09"])[0]
    framing = frame["framing"]
    end = frame["end_framing"]
    assert isinstance(framing, dict) and isinstance(end, dict)
    assert needs_end_anchor(framing, end) is True
    anchor = end_anchor(frame)
    assert anchor["needed"] is True
    assert anchor["head_ratio"] == [0.40, 0.45]
    last = anchor["last_frame"]
    assert isinstance(last, dict)
    assert last["supported"] is False
    assert last["field"] == "last_frame"
    reason = str(last["reason"])
    assert "startImage" in reason and "no end-image field" in reason
    prompt = board_prompt(framing, end)
    assert "0.55" in prompt and "0.60" in prompt
    assert "0.40" in prompt and "0.45" in prompt
    assert "the chest LED stays dark" in prompt
    assert prompt.index("35mm") < prompt.index("head ratio 0.55")
    assert prompt.index("head ratio 0.55") < prompt.index("head ratio 0.40")
    assert prompt.index("the chest LED stays dark") < prompt.index("left")
    line = motion_line(frame)
    assert line == "the figure steps back as push-in"
    assert "head ratio" not in str(line)
    image, video = _prompts(frame, [], [], {})
    assert video == line
    assert "head ratio" not in video
    assert image != video
    codes = _codes([frame])
    assert "END_IMAGE_UNSUPPORTED" in codes
    messages = [str(item["message"]) for item in framing_warnings({}, [frame])]
    assert any("0.40" in message and "0.45" in message for message in messages)
    prep = collect_prep({}, [frame], "keyframe")
    assert any(item.get("code") == "END_IMAGE_UNSUPPORTED" for item in prep.warnings)


def test_safe_box_scales_and_schema_accepts_framing() -> None:
    assert safe_box(478, 856) == {"x0": 62, "x1": 416, "y0": 98, "y1": 640}
    assert safe_box(768, 1376) == {"x0": 100, "x1": 668, "y0": 158, "y1": 1029}
    schema = yaml.safe_load(SCHEMA.read_text(encoding="utf-8"))
    frame = {
        "frame_id": "frame-001",
        "ordinal": 1,
        "node_states": {"observed_1": "present"},
        "motif_ownership": {"observed_1": None},
        "residue": [],
        "convergence_sites": ["primary"],
        "prohibited_resets": [],
        "framing": {"head_ratio": [0.55, 0.60], "crop": "mcu"},
        "end_framing": {"head_ratio": [0.40, 0.45]},
        "continuity": {"axis_side": "left"},
        "location_ref": {"plate": "wide", "precrop_to": "mcu"},
    }
    other = dict(frame)
    other["frame_id"] = "frame-002"
    other["ordinal"] = 2
    document = {
        "schema_version": "1.0.0",
        "storyboard_id": "framing",
        "graph_id": "framing",
        "frames": [frame, other],
        "delivery": {"platform": "9:16"},
        "validation": {"status": "VALID", "errors": [], "warnings": [], "frame_count": 2},
    }
    jsonschema.validate(document, schema)
