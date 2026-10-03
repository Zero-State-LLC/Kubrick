#!/usr/bin/env python3
"""Keyframe create_movie adapter tests for issue #22, plus registration."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from adapt_keyframe import (  # noqa: E402
    MAX_SECONDS,
    MIN_SECONDS,
    _with_plan_duration,
    adapt_keyframe_packet,
)
from adapt_provider import PROVIDERS, adapt  # noqa: E402
from intent_router import resolve  # noqa: E402
from mcp_kubrick_server import TOOLS  # noqa: E402
from prompt_text import positive_prompt  # noqa: E402
from provider_capabilities import PROVIDER_CAPABILITIES, check_video_adapt  # noqa: E402
from surface_compilers import video_adapt  # noqa: E402
from test_prompt_render import (  # noqa: E402
    LABELS,
    MARKERS,
    myslef_document,
    myslef_packet,
)

SCHEMA_PATH = ROOT / "schemas/keyframe-create-movie.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
PY = sys.executable


def _movie(packet: dict[str, object] | None = None) -> dict[str, object]:
    movie = adapt(packet or myslef_packet(), "keyframe")
    assert movie.get("status") != "NOT_COMPUTABLE", movie
    assert "shots" in movie
    return movie


def _with_duration(seconds: object, frame_id: str = "frame-001") -> dict[str, object]:
    return {
        "source_graph_id": "duration-graph",
        "provider": "keyframe",
        "validation": {"status": "VALID", "errors": []},
        "frames": [
            {
                "frame_id": frame_id,
                "prompt": "a room holds still",
                "provider_parameters": {"duration_seconds": seconds},
            }
        ],
    }


def _assert_locked_shot(shot: dict[str, object], marker: str) -> None:
    image = str(shot["imagePrompt"])
    video = str(shot["videoPrompt"])
    assert marker in image
    assert LABELS["observed_1"] in image
    assert "observed_1" not in image
    assert "ownershi " not in image
    assert "motif ownership" in image
    assert "geometry reset" not in image
    assert "geometry reset" not in video
    assert "smooth featureless skin where a nose would be" in image
    audio = shot["audio"]
    assert isinstance(audio, dict)
    assert "speech" not in audio
    assert audio["sound"]
    assert "negative" not in shot


def test_create_movie_schema_and_duration_totals() -> None:
    movie = _movie()
    jsonschema.validate(movie, SCHEMA)
    assert movie["targetDurationSeconds"] == 22
    assert movie["qualityPreset"] == "draft"
    assert movie["aspectRatio"] == "16:9"
    assert movie["style"] == "continuity-locked photoreal"
    assert "referenceImages" not in movie
    assert "negative_constraints" not in movie
    shots = movie["shots"]
    assert isinstance(shots, list) and len(shots) == 4
    assert [shot["durationSeconds"] for shot in shots] == [3, 10, 4, 5]


def test_shots_are_distinct_and_identity_locked() -> None:
    movie = _movie()
    shots = movie["shots"]
    assert isinstance(shots, list)
    prompts = [shot["imagePrompt"] for shot in shots]
    assert len(set(prompts)) == 4
    for shot, marker in zip(shots, MARKERS, strict=True):
        assert isinstance(shot, dict)
        _assert_locked_shot(shot, marker)


def test_duration_bounds_fail_closed() -> None:
    accepted = _movie(_with_duration(10))
    assert accepted["shots"][0]["durationSeconds"] == 10
    assert accepted["targetDurationSeconds"] == 10
    edges = _movie(_with_duration(3))
    assert edges["shots"][0]["durationSeconds"] == 3
    top = _movie(_with_duration(60))
    assert top["shots"][0]["durationSeconds"] == 60
    fractional = _movie(_with_duration(10.5))
    assert fractional["shots"][0]["durationSeconds"] == 10.5
    for seconds in (60.1, 61):
        refused = adapt_keyframe_packet(_with_duration(seconds))
        assert refused["status"] == "NOT_COMPUTABLE"
        assert "shots" not in refused
        assert "outside the allowed 3–60 seconds" in refused["message"]
        assert "refusing to clamp or drop the shot" in refused["message"]
    missing = {
        "source_graph_id": "duration-graph",
        "provider": "generic",
        "validation": {"status": "VALID"},
        "frames": [{"frame_id": "frame-001", "prompt": "a room holds still"}],
    }
    defaulted = _movie(missing)
    assert defaulted["shots"][0]["durationSeconds"] == 4
    slow = adapt_keyframe_packet(_with_duration("slow"))
    assert slow["status"] == "NOT_COMPUTABLE"
    assert "is not a number" in slow["message"]
    assert "slow" in slow["message"]
    flagged = adapt_keyframe_packet(_with_duration(True))
    assert flagged["status"] == "NOT_COMPUTABLE"
    assert "is not a number" in flagged["message"]
    assert MIN_SECONDS == 3.0 and MAX_SECONDS == 60.0


def test_plan_duration_keeps_non_numeric_declarations() -> None:
    frame = {"frame_id": "frame-001", "provider_parameters": {"duration_seconds": "slow"}}
    kept = _with_plan_duration(frame, {"generated_seconds": "slow"}, 4.0)
    assert kept["provider_parameters"]["duration_seconds"] == "slow"
    padded = _with_plan_duration(frame, {"generated_seconds": 3.6}, 2.0)
    assert padded["provider_parameters"]["duration_seconds"] == 3.6


def _floor_packet(
    planned: float, join: dict[str, str] | None, opens: str | None,
) -> dict[str, object]:
    second: dict[str, object] = {
        "frame_id": "frame-002" if join else "frame-001",
        "prompt": "a room holds still",
        "provider_parameters": {"duration_seconds": planned},
    }
    if join is not None:
        second["join"] = join
    if opens is not None:
        second["opens_with"] = opens
    frames: list[dict[str, object]] = []
    if join is not None:
        frames.append(
            {
                "frame_id": "frame-001",
                "prompt": "a room holds still",
                "provider_parameters": {"duration_seconds": 4},
            }
        )
    frames.append(second)
    return {
        "source_graph_id": "duration-graph",
        "provider": "keyframe",
        "validation": {"status": "VALID", "errors": []},
        "frames": frames,
    }


def test_generated_duration_floors_then_trims() -> None:
    cases = (
        (1.0, {"chain_from": "frame-001"}, None, 3, 1.6, 2.6, 5),
        (2.0, {"chain_from": "frame-001"}, None, 3.6, 1.6, 3.6, 6),
        (1.0, {"chain_from": "frame-001"}, "exit", 3, 0.0, 1.0, 5),
        (2.0, None, None, 3, 0.0, 2.0, 2),
        (2.9, None, None, 3, 0.0, 2.9, 2.9),
    )
    for planned, join, opens, generated, source_in, source_out, total_planned in cases:
        movie = adapt_keyframe_packet(_floor_packet(planned, join, opens))
        assert movie.get("status") != "NOT_COMPUTABLE", movie
        jsonschema.validate(movie, SCHEMA)
        shots = movie["shots"]
        assert isinstance(shots, list)
        assert shots[-1]["durationSeconds"] == generated
        cuts = movie["cut_list"]
        assert isinstance(cuts, list)
        cut = cuts[-1]
        assert cut["shot"] == shots[-1]["title"]
        assert cut["source_in"] == source_in
        assert cut["source_out"] == source_out
        assert cut["planned_seconds"] == planned
        assert cut["generated_seconds"] == generated
        assert round(cut["source_out"] - cut["source_in"], 4) == planned
        assert movie["plannedDurationSeconds"] == total_planned
        assert movie["targetDurationSeconds"] == sum(item["durationSeconds"] for item in shots)
    held = adapt_keyframe_packet(_with_duration(10))
    assert "cut_list" not in held
    assert held["plannedDurationSeconds"] == 10
    assert held["targetDurationSeconds"] == 10


def test_first_bad_shot_refuses_the_movie() -> None:
    packet = _with_duration(4, "frame-001")
    packet["frames"].append(
        {
            "frame_id": "frame-002",
            "prompt": "the chair tips",
            "provider_parameters": {"duration_seconds": 61},
        }
    )
    refused = adapt_keyframe_packet(packet)
    assert refused["status"] == "NOT_COMPUTABLE"
    assert "frame-002" in refused["message"]
    assert "shots" not in refused


def test_dialogue_preset_references_and_failures() -> None:
    packet = _with_duration(10)
    packet["frames"][0]["dialogue"] = ["hello; there"]
    packet["frames"][0]["provider_parameters"]["scene"] = "basement"
    packet["frames"][0]["title"] = "Minder startles"
    packet["qualityPreset"] = "ultra"
    packet["style"] = "photoreal documentary"
    packet["title"] = "MYSLEF"
    packet["brief"] = "the speaker sounds once"
    spoken = _movie(packet)
    assert spoken["qualityPreset"] == "draft"
    assert spoken["title"] == "MYSLEF"
    assert spoken["brief"] == "the speaker sounds once"
    assert spoken["style"] == "photoreal documentary"
    shot = spoken["shots"][0]
    assert shot["scene"] == "basement"
    assert shot["title"] == "Minder startles"
    assert shot["audio"]["speech"] == {"mode": "native", "lines": ["hello; there"]}
    high = _with_duration(4)
    high["frames"][0]["provider_parameters"]["quality_preset"] = "high"
    high["frames"][0]["provider_parameters"]["aspect_ratio"] = "9:16"
    high["referenceImages"] = ["ref://chair"]
    shaped = _movie(high)
    assert shaped["qualityPreset"] == "high"
    assert shaped["aspectRatio"] == "9:16"
    assert shaped["referenceImages"] == ["ref://chair"]
    empty = adapt_keyframe_packet(
        {"provider": "keyframe", "frames": [], "validation": {"status": "VALID"}}
    )
    assert empty["status"] == "NOT_COMPUTABLE"
    assert "no frames available" in empty["message"]
    alien = adapt_keyframe_packet(
        {"provider": "flux", "frames": [{"prompt": "x"}], "validation": {"status": "VALID"}}
    )
    assert alien["status"] == "NOT_COMPUTABLE"
    assert "incompatible" in alien["message"]
    invalid = adapt_keyframe_packet(
        {
            "provider": "keyframe",
            "frames": [{"prompt": "x"}],
            "validation": {"status": "INVALID", "errors": ["source graph is not VALID"]},
        }
    )
    assert invalid["status"] == "NOT_COMPUTABLE"
    assert "source graph is not VALID" in invalid["errors"]
    broken = adapt_keyframe_packet(
        {"provider": "keyframe", "frames": ["not-a-frame"], "validation": {"status": "VALID"}}
    )
    assert broken["status"] == "NOT_COMPUTABLE"
    assert "not an object" in broken["message"]


def test_video_adapt_storyboard_and_grok_cap() -> None:
    document = myslef_document()
    for frame, seconds in zip(document["frames"], (3, 10, 4, 5), strict=True):
        assert isinstance(frame, dict)
        frame["duration_seconds"] = seconds
    text = yaml.safe_dump(document)
    adapted = video_adapt(text, "myslef", "keyframe")
    assert adapted["status"] != "NOT_COMPUTABLE", adapted.get("diagnostic")
    movie = adapted["result"]["adapted_packet"]
    jsonschema.validate(movie, SCHEMA)
    assert movie["targetDurationSeconds"] == 22
    assert "speech" not in movie["shots"][0]["audio"]
    short = myslef_document()
    short["frames"] = [short["frames"][0]]
    short["frames"][0]["duration_seconds"] = 61
    refused = video_adapt(yaml.safe_dump(short), "myslef", "keyframe")
    assert refused["status"] == "NOT_COMPUTABLE"
    assert "3–60" in refused["diagnostic"]["message"]
    grok = check_video_adapt("grok-imagine", duration=10)
    assert grok is not None and "8" in grok["message"]
    assert check_video_adapt("generic", duration=2) is None
    caps = PROVIDER_CAPABILITIES["keyframe"]
    assert caps["min_duration_seconds"] == 3.0
    assert caps["max_duration_seconds"] == 60.0
    assert caps["dialogue_audio"] is True and caps["multi_shot"] is True
    source = "a room holds still"
    assert positive_prompt(source, [], ["no nose"]).startswith(source)


def test_keyframe_is_registered() -> None:
    manifest = json.loads((ROOT / "kubrick.manifest.yaml").read_text(encoding="utf-8"))
    assert "keyframe" in manifest["providers"]
    assert "schemas/keyframe-create-movie.schema.json" in manifest["schemas"]
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "keyframe" in skill.lower()
    assert "keyframe" in readme.lower()
    assert "keyframe" in PROVIDERS
    description = TOOLS[0]["description"]
    assert "keyframe" in description
    call = resolve(["do", "adapt", "--action", "provider", "--provider", "keyframe"])
    assert call.script.name == "adapt_provider.py"
    help_text = subprocess.run(
        [PY, str(ROOT / "scripts/kubrick_compile.py"), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert help_text.returncode == 0, help_text.stderr
    assert "keyframe" in help_text.stdout


def main() -> None:
    test_create_movie_schema_and_duration_totals()
    test_shots_are_distinct_and_identity_locked()
    test_duration_bounds_fail_closed()
    test_generated_duration_floors_then_trims()
    test_plan_duration_keeps_non_numeric_declarations()
    test_first_bad_shot_refuses_the_movie()
    test_dialogue_preset_references_and_failures()
    test_video_adapt_storyboard_and_grok_cap()
    test_keyframe_is_registered()
    print("keyframe adapter tests: PASS")


if __name__ == "__main__":
    main()
