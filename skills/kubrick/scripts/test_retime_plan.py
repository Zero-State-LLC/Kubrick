#!/usr/bin/env python3
"""Proposed retime plans. Issue #36."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import intent_router as ir  # noqa: E402
from retime_plan import main as retime_main  # noqa: E402
from retime_plan import retime  # noqa: E402

from kubrick.paths import implementation_of  # noqa: E402

PY = sys.executable
EXAMPLE = ROOT / "examples/myslef-minder" / "storyboard-plan.yaml"


def _as_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AssertionError("expected a mapping")
    return {str(key): item for key, item in value.items()}


def _rows(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [_as_dict(item) for item in value if isinstance(item, dict)]


def _plan(*durations: float, **root: object) -> dict[str, object]:
    frames = [
        {"frame_id": f"frame-{index:03d}", "duration_seconds": duration}
        for index, duration in enumerate(durations, start=1)
    ]
    document: dict[str, object] = {"frames": frames}
    document.update(root)
    return document


def _modes(result: dict[str, object]) -> list[str]:
    return [str(row["mode"]) for row in _rows(result.get("generation_plan"))]


def _edit_clock(result: dict[str, object]) -> float:
    total = 0.0
    for row in _rows(result.get("edit_plan")):
        total += float(str(row["out"])) - float(str(row["in"]))
    return round(total, 4)


def _sum_generated(result: dict[str, object]) -> float:
    seen: set[str] = set()
    total = 0.0
    for row in _rows(result.get("generation_plan")):
        clip = row.get("clip_id")
        if isinstance(clip, str):
            if clip in seen:
                continue
            seen.add(clip)
        total += float(str(row["generated_seconds"]))
    return round(total, 4)


def test_router_sends_retime_to_its_script() -> None:
    call = ir.resolve(["do", "video", "--action", "retime", "--input", "plan.yaml"])
    assert call.script.name == "retime_plan.py"
    assert call.argv == ["--input", "plan.yaml"]


def test_myslef_beats_are_separate_and_long_beats_share() -> None:
    document = _as_dict(yaml.safe_load(EXAMPLE.read_text(encoding="utf-8")))
    result = retime(document, "keyframe")
    assert result["status"] == "PROPOSED"
    assert result["script_clock"] == 6 and result["final_clock"] == 6 and result["delta"] == 0
    assert result["generated_clock"] == 16
    assert _modes(result) == ["new_generation"] * 4
    edits = {str(row["shot"]): row for row in _rows(result["edit_plan"])}
    assert (edits["03"]["in"], edits["03"]["out"]) == (0, 2)
    assert (edits["04"]["in"], edits["04"]["out"]) == (1.6, 2.6)
    assert (edits["05"]["in"], edits["05"]["out"]) == (0, 2)
    assert (edits["06"]["in"], edits["06"]["out"]) == (0, 1)
    assert all(row["source"] == "generate" for row in edits.values())
    shared = retime(_plan(4, 4, 4), "keyframe")
    assert shared["status"] == "PROPOSED" and shared["delta"] == 0
    assert _modes(shared) == ["in_multi_shot_clip"] * 3
    assert shared["final_clock"] == 12 and shared["generated_clock"] == 12
    generated = [row["generated_seconds"] for row in _rows(shared["generation_plan"])]
    assert generated == [12, 12, 12]
    total = sum([float(str(item)) for item in generated])
    assert total != shared["final_clock"] and total != shared["generated_clock"]
    lone = retime(_plan(4), "keyframe")
    assert _modes(lone) == ["new_generation"]


def test_chain_breaks_a_group_and_threshold_overrides() -> None:
    frames = [
        {"frame_id": "frame-001", "duration_seconds": 4},
        {"frame_id": "frame-002", "duration_seconds": 4, "join": {"chain_from": "frame-001"}},
        {"frame_id": "frame-003", "duration_seconds": 4},
    ]
    result = retime({"frames": frames}, "keyframe")
    assert result["status"] == "PROPOSED" and result["delta"] == 0
    assert result["generated_clock"] == 14.0
    assert _modes(result) == ["new_generation"] * 3
    separate = retime(_plan(4, 4, short_beat_threshold_seconds=5), "keyframe")
    assert _modes(separate) == ["new_generation", "new_generation"]
    assert separate["delta"] == 0
    generic = retime(_plan(4, 4), "generic")
    assert generic["status"] == "PROPOSED" and generic["delta"] == 0
    assert _modes(generic) == ["in_multi_shot_clip", "in_multi_shot_clip"]
    grok = retime(_plan(4, 4), "grok-imagine")
    assert _modes(grok) == ["new_generation", "new_generation"]
    missing = retime({"frames": [{}, {}]}, "generic")
    assert missing["script_clock"] == 16 and missing["final_clock"] == 16
    raw_warnings = missing.get("prep_warnings")
    assert isinstance(raw_warnings, list)
    missing_codes: list[object] = []
    for item in raw_warnings:
        assert isinstance(item, dict)
        missing_codes.append(item.get("code"))
    assert missing_codes == ["DURATION_MISSING", "DURATION_MISSING"]


def test_reuse_takes_and_clock_delta() -> None:
    document = _as_dict(yaml.safe_load(EXAMPLE.read_text(encoding="utf-8")))
    document.pop("accept_clock_delta", None)
    takes = [
        {"shot": "03", "source_clip": "shot-03.mp4", "trim": {"in": 0, "out": 2}},
        {"shot": "05", "source_clip": "shot-05.mp4", "trim": {"in": 0.2, "out": 2.2}},
    ]
    reused = retime(document, "keyframe", takes)
    assert reused["status"] == "PROPOSED" and reused["delta"] == 0
    assert _modes(reused) == ["reuse_take", "new_generation", "reuse_take", "new_generation"]
    edits = {str(row["shot"]): row for row in _rows(reused["edit_plan"])}
    assert edits["03"]["source"] == "shot-03.mp4" and edits["03"]["out"] == 2
    short = retime(document, "keyframe", [{"shot": "03", "trim": {"in": 0, "out": 1}}])
    assert _modes(short)[0] == "new_generation"
    bare = retime(document, "keyframe", [{"shot": "frame-001", "trim": {"in": 0, "out": 2}}])
    assert _modes(bare)[0] == "reuse_take"
    unusable = retime(document, "keyframe", [{"shot": "03"}, {"shot": "03", "trim": {"in": 0}}])
    assert _modes(unusable)[0] == "new_generation"
    chained = {
        "frames": [{
            "frame_id": "frame-002",
            "shot_id": "04",
            "duration_seconds": 1,
            "join": {"chain_from": "frame-001"},
        }],
    }
    held = retime(chained, "keyframe", [{
        "shot": "04", "source_clip": "keep.mp4", "trim": {"in": 0, "out": 1},
    }])
    assert _modes(held) == ["reuse_take"]
    assert _rows(held["generation_plan"])[0]["generated_seconds"] == 0
    plain = retime(document, "keyframe")
    assert plain["status"] == "PROPOSED" and plain["delta"] == 0
    assert plain["final_clock"] == 6 and plain["generated_clock"] == 16


def test_final_clock_is_the_sum_of_edit_windows() -> None:
    text = EXAMPLE.read_text(encoding="utf-8")
    assert "accept_clock_delta" not in text
    document = _as_dict(yaml.safe_load(text))
    result = retime(document, "keyframe")
    rows = _rows(result["generation_plan"])
    generated = round(sum(float(str(row["generated_seconds"])) for row in rows), 4)
    assert result["status"] == "PROPOSED"
    assert result["script_clock"] == 6.0
    assert result["final_clock"] == _edit_clock(result) == 6.0
    assert result["generated_clock"] == generated == _sum_generated(result) == 16.0
    assert result["delta"] == 0.0
    shared = retime(_plan(4, 4, 4), "keyframe")
    assert shared["final_clock"] == _edit_clock(shared) == 12
    assert shared["generated_clock"] == _sum_generated(shared) == 12
    long_plan = {"frames": [{
        "frame_id": "frame-001", "shot_id": "03", "duration_seconds": 2,
    }]}
    take = [{"shot": "03", "source_clip": "keep.mp4", "trim": {"in": 0, "out": 5}}]
    refused = retime(long_plan, "keyframe", take)
    assert refused["status"] == "NOT_COMPUTABLE"
    assert refused["code"] == "CLOCK_DELTA_UNACCEPTED"
    assert refused["script_clock"] == 2 and refused["final_clock"] == 5
    assert refused["final_clock"] == _edit_clock(refused)
    assert refused["generated_clock"] == 0 and refused["delta"] == 3
    assert "3.0" in str(refused["message"])
    accepted = retime({**long_plan, "accept_clock_delta": True}, "keyframe", take)
    assert accepted["status"] == "PROPOSED" and accepted["delta"] == 3
    flagged = retime(long_plan, "keyframe", take, accept_clock_delta=True)
    assert flagged["status"] == "PROPOSED" and flagged["final_clock"] == 5


def test_model_overlay_does_not_change_retime() -> None:
    frames = [
        {"frame_id": "frame-001", "duration_seconds": 4},
        {
            "frame_id": "frame-002",
            "duration_seconds": 1,
            "join": {"chain_from": "frame-001"},
        },
    ]
    plain = retime({"frames": frames}, "keyframe")
    overlaid = retime({"frames": frames, "model": "seedance-lab"}, "keyframe")
    held = retime({"frames": frames, "input_mode": "lab-hold"}, "keyframe")
    assert overlaid == plain == held
    edits = {str(row["shot"]): row for row in _rows(plain["edit_plan"])}
    assert (edits["frame-002"]["in"], edits["frame-002"]["out"]) == (1.6, 2.6)


def test_fail_closed_and_no_provider_call() -> None:
    flux = retime(_plan(4), "flux")
    assert flux["code"] == "NO_FEASIBLE_PLAN" and "does not support video" in str(flux["message"])
    assert retime({"frames": []}, "generic")["code"] == "NO_FEASIBLE_PLAN"
    over = retime(_plan(61), "keyframe")
    assert over["code"] == "NO_FEASIBLE_PLAN"
    assert "61.0" in str(over["message"]) and "30.0" in str(over["message"])
    shared = retime(_plan(40, 40), "keyframe")
    assert shared["code"] == "NO_FEASIBLE_PLAN" and "80.0" in str(shared["message"])
    text = implementation_of(ROOT / "scripts/retime_plan.py").read_text(encoding="utf-8")
    for banned in ("import subprocess", "import requests", "urllib", "adapt_keyframe", "os.system"):
        assert banned not in text
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        plan = root / "plan.yaml"
        plan.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
        output = root / "retime.yaml"
        command = [
            PY, str(ROOT / "scripts/kubrick.py"), "video", "--action", "retime",
            "--provider", "keyframe", "--input", str(plan), "--output", str(output),
        ]
        opened = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
        assert opened.returncode == 0, opened.stdout + opened.stderr
        written = _as_dict(yaml.safe_load(output.read_text(encoding="utf-8")))
        assert written["status"] == "PROPOSED" and written["final_clock"] == 6
        assert written["script_clock"] == 6 and written["generated_clock"] == 16
        assert written["delta"] == 0
        long = root / "long.yaml"
        long.write_text(
            "frames:\n- frame_id: frame-001\n  shot_id: '03'\n  duration_seconds: 2\n",
            encoding="utf-8",
        )
        takes = root / "long-takes.yaml"
        takes.write_text(
            "- shot: '03'\n  source_clip: keep.mp4\n  trim: {in: 0, out: 5}\n",
            encoding="utf-8",
        )
        overrun = [
            PY, str(ROOT / "scripts/kubrick.py"), "video", "--action", "retime",
            "--provider", "keyframe", "--input", str(long), "--takes", str(takes),
            "--output", str(output),
        ]
        closed = subprocess.run(overrun, cwd=ROOT, text=True, capture_output=True, check=False)
        assert closed.returncode == 4
        failed = _as_dict(yaml.safe_load(output.read_text(encoding="utf-8")))
        assert failed["code"] == "CLOCK_DELTA_UNACCEPTED" and "3.0" in str(failed["message"])
        assert failed["final_clock"] == 5 and failed["delta"] == 3
        signed = subprocess.run(
            [*overrun, "--accept-clock-delta"],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        assert signed.returncode == 0, signed.stdout + signed.stderr
        listed = root / "list.yaml"
        listed.write_text("- shot: '03'\n  trim: {in: 0, out: 2}\n", encoding="utf-8")
        wrapped = root / "wrapped.yaml"
        wrapped.write_text("takes:\n- shot: '03'\n  trim: {in: 0, out: 2}\n", encoding="utf-8")
        printed = subprocess.run(
            [PY, str(ROOT / "scripts/retime_plan.py"), "--surface-action", "retime",
             "--input", str(EXAMPLE), "--provider", "keyframe", "--takes", str(wrapped)],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        assert printed.returncode == 0 and "script_clock" in printed.stdout
        assert retime_main(["--input", str(listed), "--provider", "generic"]) == 4
        empty = root / "empty.yaml"
        empty.write_text("[]\n", encoding="utf-8")
        assert retime_main(["--input", str(empty), "--provider", "keyframe"]) == 4


def main() -> None:
    test_router_sends_retime_to_its_script()
    test_myslef_beats_are_separate_and_long_beats_share()
    test_chain_breaks_a_group_and_threshold_overrides()
    test_reuse_takes_and_clock_delta()
    test_final_clock_is_the_sum_of_edit_windows()
    test_model_overlay_does_not_change_retime()
    test_fail_closed_and_no_provider_call()
    print("retime tests: PASS")


if __name__ == "__main__":
    main()
