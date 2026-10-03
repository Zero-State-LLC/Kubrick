#!/usr/bin/env python3
"""Tests for prop, wardrobe, and reference locks. Issues #28, #29, and #30."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_motif_graph import build as build_graph  # noqa: E402
from continuity_locks import (  # noqa: E402
    bind_strict,
    drift_warnings,
    introduced_residue,
    is_plain_top,
    prop_assignments,
    reference_block,
    reference_warnings,
    render_with_locks,
    strict_enabled,
    unbind_strict,
    wardrobe_lines,
)
from prompt_text import character_lock_feature, continuity_for_frame  # noqa: E402
from propagate_graph_state import propagate  # noqa: E402

FIXTURE = ROOT / "evals/fixtures/myslef"
EXAMPLE = ROOT / "examples/myslef-minder"
PY = sys.executable
CHAIR = {
    "C0": "beside the desk",
    "C1": "shoved back from the bench",
    "C2": "rolling down the aisle",
    "C3": "tipped on its side at the far end of the aisle by the rack gap",
    "C4": "on its side at the far end of the aisle by the rack gap; it does not move",
}
STABLE = "CHAIR LOCK: on its side at the far end of the aisle by the rack gap; it does not move"
WARDROBE = "plain solid black pullover hoodie, no logo, no print; charcoal sweatpants"
DRIFT = [
    {
        "id": "plain-top-motion-logo",
        "pattern": "plain top + motion",
        "effect": "invented chest logo/graphic",
        "providers": ["keyframe"],
    }
]
RECOMMEND = (
    "use a start frame that already shows the plain top in the moving pose, "
    "retouch after generation, or accept the drift"
)


def _load(path: Path) -> dict[str, object]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _frames(*states: str) -> list[dict[str, object]]:
    frames: list[dict[str, object]] = []
    for index, state in enumerate(states, start=1):
        frames.append(
            {
                "frame_id": f"frame-{index:03d}",
                "prop_states": {"chair": state},
            }
        )
    return frames


def test_plain_top_and_motion_words() -> None:
    assert is_plain_top("plain shirt")
    assert is_plain_top("solid black, no logo")
    assert is_plain_top("solid black, without a logo")
    assert is_plain_top("plain shirt with a logo") is False
    assert is_plain_top("striped shirt") is False
    document = {"characters": {"minder": {"wardrobe": WARDROBE}}}
    moving = [
        {"frame_id": "frame-002", "characters": ["minder"], "action": "the minder springs up"}
    ]
    static = [
        {"frame_id": "frame-001", "characters": ["minder"], "action": "the minder sits typing"}
    ]
    returned = [
        {"frame_id": "frame-003", "characters": ["minder"], "action": "the minder will return"}
    ]
    turning = [
        {"frame_id": "frame-004", "characters": ["minder"], "action": "she turns toward the rack"}
    ]
    assert drift_warnings(document, static, "keyframe", DRIFT) == []
    assert drift_warnings(document, returned, "keyframe", DRIFT) == []
    assert drift_warnings(document, moving, "generic", DRIFT) == []
    found = drift_warnings(document, moving, "keyframe", DRIFT)
    assert len(found) == 1
    assert found[0]["code"] == "KNOWN_DRIFT"
    assert found[0]["shot"] == "frame-002"
    assert "minder on frame-002 matches plain top + motion" in found[0]["message"]
    assert "invented chest logo/graphic" in found[0]["message"]
    assert found[0]["recommendation"] == RECOMMEND
    assert drift_warnings(document, turning, "keyframe", DRIFT)
    empty_providers = [{**DRIFT[0], "providers": []}]
    assert drift_warnings(document, moving, "generic", empty_providers)


def test_wardrobe_override_and_dedupe() -> None:
    document = {
        "characters": {"minder": {"wardrobe": WARDROBE}, "myslef": {"wardrobe": "grey coat"}}
    }
    both = {"characters": ["minder", "myslef"], "wardrobe": "ignored string"}
    lines = wardrobe_lines(document, both)
    assert lines[0] == f"WARDROBE LOCK: minder wears {WARDROBE}"
    assert lines[1] == "WARDROBE LOCK: myslef wears grey coat"
    one = {"characters": ["myslef"], "wardrobe": "red jacket"}
    assert wardrobe_lines(document, one) == ["WARDROBE LOCK: myslef wears red jacket"]
    mapped = {"characters": ["minder"], "wardrobe": {"minder": "blue shirt, no logo"}}
    assert wardrobe_lines(document, mapped) == ["WARDROBE LOCK: minder wears blue shirt, no logo"]
    assert wardrobe_lines(document, {}) == []
    rendered = render_with_locks(lines[0], [lines[0]], [])
    assert rendered.count("WARDROBE LOCK:") == 1
    ordered = render_with_locks(
        "room holds",
        ["WARDROBE LOCK: minder wears a coat", "CHAIR LOCK: upright"],
        ["lights flicker to near-black, figures gone on recovery"],
    )
    assert ordered.index("WARDROBE") < ordered.index("CHAIR") < ordered.index("flicker")
    assert ordered.index("flicker") < ordered.index("room holds")


def test_prop_order_carry_and_unreachable_jump() -> None:
    document = {"props": {"chair": {"states": CHAIR}}}
    first, errors = prop_assignments(document, _frames("C0"))
    assert errors == []
    assert first["frame-001"] == ["CHAIR LOCK: beside the desk"]
    carried, errors = prop_assignments(
        document,
        [
            {"frame_id": "frame-001", "prop_states": {"chair": "C0"}},
            {"frame_id": "frame-002"},
        ],
    )
    assert errors == []
    assert carried["frame-002"] == ["CHAIR LOCK: beside the desk"]
    absent, errors = prop_assignments(
        document,
        [
            {"frame_id": "frame-001"},
            {"frame_id": "frame-002", "prop_states": {"chair": "C1"}},
        ],
    )
    assert errors == []
    assert absent["frame-001"] == []
    assert absent["frame-002"] == ["CHAIR LOCK: shoved back from the bench"]
    stable, errors = prop_assignments(document, _frames("C4"))
    assert errors == [] and stable["frame-001"] == [STABLE]
    jump, errors = prop_assignments(document, _frames("C3", "C3->beside the desk"))
    assert jump["frame-002"] == []
    assert len(errors) == 1
    assert "prop chair on frame-001 and frame-002 is not reachable" in errors[0]
    assert "cannot move" in errors[0]
    unknown, errors = prop_assignments(document, _frames("C9"))
    assert "unknown state C9" in errors[0]
    ambiguous, errors = prop_assignments(document, _frames("rack gap"))
    assert "unknown state rack gap" in errors[0]
    explicit = {"props": {"chair": {"states": CHAIR, "transitions": [{"from": "C0", "to": "C1"}]}}}
    _lines, errors = prop_assignments(explicit, _frames("C0", "C0->C2"))
    assert "cannot move" in errors[0]
    same, errors = prop_assignments(explicit, _frames("C0", "C0"))
    assert errors == [] and same["frame-002"] == ["CHAIR LOCK: beside the desk"]
    assert prop_assignments({}, _frames("C0")) == ({}, [])


def test_cross_shot_prop_jump_must_be_reachable() -> None:
    document = {"props": {"chair": {"states": CHAIR}}}
    forward, errors = prop_assignments(document, _frames("C0", "C1->C3"))
    assert errors == []
    assert "shoved back" in forward["frame-002"][0]
    assert "tipped" in forward["frame-002"][0]
    backward, errors = prop_assignments(document, _frames("C3", "beside the desk"))
    assert backward["frame-002"] == []
    assert "prop chair on frame-001 and frame-002 is not reachable" in errors[0]
    assert "does not continue" in errors[0]
    explicit = {
        "props": {"chair": {"states": CHAIR, "transitions": [{"from": "C0", "to": "C1"}]}}
    }
    allowed, errors = prop_assignments(explicit, _frames("C0", "C1"))
    assert errors == [] and "shoved back" in allowed["frame-002"][0]
    blocked, errors = prop_assignments(explicit, _frames("C0", "C2"))
    assert blocked["frame-002"] == []
    assert "does not continue" in errors[0]


def test_residue_is_introduced_on_its_frame() -> None:
    kept, pending = introduced_residue(
        [],
        ["laptop cartoon audio under the hum"],
        [
            "laptop cartoon audio under the hum",
            "the chair stays tipped after the minder is gone",
        ],
    )
    assert "the chair stays tipped after the minder is gone" not in kept
    assert pending == ["the chair stays tipped after the minder is gone"]
    later, still = introduced_residue(kept, ["chair stays tipped"], pending)
    assert "the chair stays tipped after the minder is gone" in later
    assert still == []
    graph = build_graph(_load(FIXTURE / "minder-brief.yaml"))
    assert graph["validation"]["status"] == "VALID", graph["validation"]
    board = propagate(graph, _load(FIXTURE / "minder-storyboard.yaml"))
    assert board["validation"]["status"] == "VALID", board["validation"]
    first = board["frames"][0]["residue"]
    assert isinstance(first, list)
    blob = " ".join(str(item) for item in first)
    assert "chair stays tipped" not in blob
    assert "laptop cartoon audio under the hum" in blob
    last = " ".join(str(item) for item in board["frames"][3]["residue"])
    assert "the chair stays tipped after the minder is gone" in last


def test_reference_contradiction_and_strict_block() -> None:
    feature = character_lock_feature("no nose", from_lock=True)
    assert feature == "nose"
    document = {
        "character_locks": ["no nose"],
        "characters": {
            "myslef": {
                "references": [
                    {
                        "path": "head-lock-short-flush.png",
                        "role": "character",
                        "declares": ["nose"],
                    }
                ],
            },
            "extra": {
                "references": [{"mediaObjectId": "loc-1", "role": "location", "declares": ["nose"]}]
            },
            "quiet": {
                "references": [{"path": "ears.png", "role": "character", "declares": ["ears"]}]
            },
            "bare": {},
        },
    }
    found = reference_warnings(document)
    assert len(found) == 1
    assert found[0]["code"] == "REFERENCE_LOCK_CONTRADICTION"
    assert found[0]["shot"] is None
    assert found[0]["character"] == "myslef"
    assert (
        "character lock 'no nose' contradicts reference head-lock-short-flush.png"
        in found[0]["message"]
    )
    assert "declares nose" in found[0]["message"]
    assert found[0]["recommendation"] == "edit the reference, drop the lock, or accept the drift"
    assert reference_warnings({"characters": {"myslef": {}}}) == []
    assert reference_warnings({"character_locks": ["no nose"]}) == []
    assert reference_block(found, False) == []
    assert reference_block([{"code": "SHORT_BEAT", "message": "short"}], True) == []
    token = bind_strict(True)
    try:
        assert strict_enabled()
        assert reference_block(found, strict_enabled()) == [found[0]["message"]]
    finally:
        unbind_strict(token)
    assert strict_enabled() is False
    assert strict_enabled({"strict": True})
    assert reference_block(found, True) == [found[0]["message"]]


def test_declared_prop_drops_prior_chair_line() -> None:
    lines = [
        "preserve prior object state chair: upright, occupied, at the bench",
        "preserve prior light state room: dim",
        "object state chair: tipped on its side",
    ]
    kept = continuity_for_frame(lines, {"prop_states": {"chair": "C1->C3"}})
    assert kept == lines[1:]
    assert continuity_for_frame(lines, {}) == lines
    nested = {"provider_parameters": {"prop_states": {"Chair": "C0"}}}
    filtered = continuity_for_frame(
        ["preserve prior object state chair: upright", "preserve prior object state lamp: on"],
        nested,
    )
    assert filtered == ["preserve prior object state lamp: on"]


def _frame_blob(frame: dict[str, object], keys: tuple[str, ...]) -> str:
    parts: list[str] = []
    for key in keys:
        value = frame.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
        elif value is not None:
            parts.append(str(value))
    return "\n".join(parts)


def _assert_chair_authority(frames: list[dict[str, object]], keys: tuple[str, ...]) -> None:
    blobs = [_frame_blob(frame, keys) for frame in frames]
    for blob in blobs:
        assert "preserve prior object state chair" not in blob
    assert "upright" not in blobs[1]
    assert "CHAIR LOCK" in blobs[1]


def _compile(provider: str, out: Path, *, strict: bool) -> subprocess.CompletedProcess[str]:
    command = [
        PY,
        str(ROOT / "scripts/kubrick_compile.py"),
        "--brief",
        str(EXAMPLE / "brief.yaml"),
        "--mode",
        "storyboard",
        "--storyboard-plan",
        str(EXAMPLE / "storyboard-plan.yaml"),
        "--provider",
        provider,
        "--out",
        str(out),
    ]
    if strict:
        command.append("--strict")
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)


def test_compile_receipt_carries_prep_warnings() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        generic = _compile("generic", root / "generic", strict=False)
        assert generic.returncode == 0, generic.stdout + generic.stderr
        receipt = json.loads(generic.stdout)
        assert receipt["status"] == "COMPILED"
        codes = [item["code"] for item in receipt["prep_warnings"]]
        assert "REFERENCE_LOCK_CONTRADICTION" in codes
        assert "SHORT_BEAT" not in codes
        strict = _compile("generic", root / "strict", strict=True)
        assert strict.returncode != 0
        failed = json.loads(strict.stdout)
        assert "REFERENCE_LOCK_CONTRADICTION" in [item["code"] for item in failed["prep_warnings"]]
        assert "REFERENCE_LOCK_CONTRADICTION" in failed["reason_vector"]
        written = yaml.safe_load(
            (root / "strict" / "generic-prompt-packet.yaml").read_text(encoding="utf-8")
        )
        assert "REFERENCE_LOCK_CONTRADICTION" in [item["code"] for item in written["prep_warnings"]]
        generic_packet = yaml.safe_load(
            (root / "generic" / "generic-prompt-packet.yaml").read_text(encoding="utf-8")
        )
        generic_frames = generic_packet["frames"]
        assert generic_frames[0]["generation_parameters"]["aspect_ratio"] == "9:16"
        _assert_chair_authority(generic_frames, ("prompt",))
        adapter = yaml.safe_load(
            (root / "generic" / "model-adapter-packet.yaml").read_text(encoding="utf-8")
        )
        _assert_chair_authority(adapter["frames"], ("prompt", "continuity_from_previous"))
        keyframe = _compile("keyframe", root / "keyframe", strict=False)
        assert keyframe.returncode == 0, keyframe.stdout + keyframe.stderr
        movie = yaml.safe_load(
            (root / "keyframe" / "keyframe-prompt-packet.yaml").read_text(encoding="utf-8")
        )
        assert movie.get("status") != "NOT_COMPUTABLE"
        assert movie["aspectRatio"] == "9:16"
        assert movie["plannedDurationSeconds"] == 6
        assert movie["targetDurationSeconds"] == 12
        assert movie["cut_list"] and movie["prep_warnings"] and movie["technique_suggestions"]
        _assert_chair_authority(movie["shots"], ("imagePrompt", "videoPrompt"))


def main() -> None:
    test_plain_top_and_motion_words()
    test_wardrobe_override_and_dedupe()
    test_prop_order_carry_and_unreachable_jump()
    test_cross_shot_prop_jump_must_be_reachable()
    test_residue_is_introduced_on_its_frame()
    test_reference_contradiction_and_strict_block()
    test_declared_prop_drops_prior_chair_line()
    test_compile_receipt_carries_prep_warnings()
    print("continuity lock tests: PASS")


if __name__ == "__main__":
    main()
