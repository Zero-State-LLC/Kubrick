#!/usr/bin/env python3
"""Issue #108: video cues carry an SFX estimate from fixtures, for any project.

No ElevenLabs call. MYSLEF is only the test tenant here.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from structured_io import load_mapping  # noqa: E402
from video_cues import sfx_estimate  # noqa: E402

MYSLEF = ROOT / "examples" / "myslef-minder" / "storyboard-plan.yaml"
PLAN: dict[str, object] = {
    "frames": [
        {"frame_id": "f1", "shot_id": "01", "duration_seconds": 4,
         "speech_lines": ["host: Hello"]},
        {"frame_id": "f2", "shot_id": "02", "duration_seconds": 4},
    ],
    "characters": {"host": {"voice": {"speaks": True, "library_id": "lib-1"}}},
}


def _map(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value


def _rows(value: object) -> list[dict[str, object]]:
    assert isinstance(value, list) and all(isinstance(item, dict) for item in value)
    return value


def _cues(plan: dict[str, object]) -> tuple[int, dict[str, object]]:
    with tempfile.TemporaryDirectory() as tmp:
        inp = Path(tmp) / "plan.json"
        out = Path(tmp) / "out.json"
        inp.write_text(json.dumps(plan), encoding="utf-8")
        cmd = [
            sys.executable, "scripts/video_cues.py", "--surface-action", "x",
            "--input", str(inp), "--provider", "keyframe", "--output", str(out),
        ]
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
        assert out.exists(), proc.stderr
        data = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        return proc.returncode, data


def _with_effects(plan: dict[str, object], sfx: object = None) -> dict[str, object]:
    doc = copy.deepcopy(plan)
    frames = doc["frames"]
    assert isinstance(frames, list)
    _map(frames[0])["sfx"] = [{"effect": "door slam", "seconds": 1.5}]
    _map(frames[1])["sfx"] = ["rain bed"]
    if sfx is not None:
        doc["sfx"] = sfx
    return doc


def test_no_effects_is_an_explicit_zero_line() -> None:
    code, data = _cues(PLAN)
    assert code == 0
    sfx = _map(data["sfx_estimate"])
    assert sfx["line"] == "sfx 0" and sfx["credits"] == 0 and sfx["effects"] == 0


def test_frame_effects_without_a_rate_fail_closed() -> None:
    code, data = _cues(_with_effects(PLAN))
    assert code != 0
    assert data["code"] == "SFX_ESTIMATE_MISSING"
    assert "elevenlabs_estimate" not in data and "sfx_estimate" not in data


def test_frame_effects_are_priced_from_the_fixture_rate() -> None:
    code, data = _cues(_with_effects(PLAN, {"credits_per_second": 40, "default_seconds": 2}))
    assert code == 0, data
    sfx = _map(data["sfx_estimate"])
    assert sfx["status"] == "PROPOSED" and sfx["source"] == "fixture"
    assert sfx["credits"] == 140 and sfx["line"] == "sfx 140"
    assert [row["shot"] for row in _rows(sfx["effects_detail"])] == ["01", "02"]
    assert [row["credits"] for row in _rows(sfx["effects_detail"])] == [60, 80]


def test_bad_fixture_numbers_are_not_computable() -> None:
    frames = [{"shot_id": "01", "sfx": ["hum"]}]
    assert sfx_estimate({"sfx": {"credits_per_second": 10}}, frames)["status"] == "NOT_COMPUTABLE"
    for cfg in ({"credits_per_second": True}, {"credits_per_second": -1},
                {"credits_per_second": 1, "default_seconds": "x"}, "lots"):
        assert sfx_estimate({"sfx": cfg}, frames)["status"] == "NOT_COMPUTABLE", cfg
    flat = sfx_estimate({"sfx": {"credits": 7}}, frames)
    assert flat["line"] == "sfx 7" and flat["effects"] == 1


def test_myslef_tenant_as_a_test_case() -> None:
    plan = load_mapping(MYSLEF)
    frames = plan["frames"]
    assert isinstance(frames, list)
    assert sfx_estimate(plan, frames)["line"] == "sfx 0"
    noisy = _rows(copy.deepcopy(frames))
    noisy[0]["sfx"] = [{"effect": "chair scrape", "seconds": 1}]
    assert sfx_estimate(plan, noisy)["status"] == "MISSING"
    priced = dict(plan, sfx={"credits_per_second": 25})
    assert sfx_estimate(priced, noisy)["line"] == "sfx 25"
    source = (ROOT / "src" / "kubrick" / "providers" / "video_cues.py").read_text(encoding="utf-8")
    assert "myslef" not in source.casefold() and "requests" not in source
