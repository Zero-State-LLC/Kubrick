#!/usr/bin/env python3
"""Brief character locks and Keyframe aspect / frame passthrough."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from adapt_provider import adapt  # noqa: E402
from build_model_adapter_packet import build as build_packet  # noqa: E402
from build_motif_graph import build as build_graph  # noqa: E402
from prompt_text import character_lock_positive, positive_prompt  # noqa: E402
from propagate_graph_state import propagate  # noqa: E402
from surface_compilers import video_adapt, video_shot  # noqa: E402

PY = sys.executable
EXAMPLE = ROOT / "examples/authority-transfer-storyboard"
TAIL = "the locked character has no tail; the tail stays absent in every frame"
NOSE = "smooth featureless skin where a nose would be"
FACE = "the locked character's face has no nose"
SOUND = "room tone of the empty office"


def test_prefixed_unknown_lock_and_plain_lock() -> None:
    assert character_lock_positive("character-lock: no tail") == TAIL
    assert character_lock_positive("identity-lock: no tail") == TAIL
    assert character_lock_positive("no tail") is None
    assert character_lock_positive("no tail", from_lock=True) == TAIL
    assert character_lock_positive("hairless scalp") is None
    assert "hairless scalp" not in positive_prompt("room", [], ["hairless scalp"])
    locked = positive_prompt("room", [], ["geometry reset"], ["hairless scalp", "no tail"])
    assert "hairless scalp" in locked
    assert TAIL in locked
    assert "geometry reset" not in locked


def _spec() -> dict[str, object]:
    return {
        "graph_id": "lock-graph",
        "symbolic_intent": {"desired_state_change": "the chair empties"},
        "observed_forms": [
            {"id": "observed_1", "observed_form": "cheap chair", "initial_state": "present"},
            {"id": "observed_2", "observed_form": "speaker grille", "initial_state": "present"},
        ],
        "relations": [
            {"source": "observed_2", "target": "observed_1", "relation": "transfers"},
        ],
        "layers": {
            "layout_geometry": ["racks around one chair"],
            "semantics_function": ["surveillance reversed"],
            "attributes_states": ["occupied seat"],
        },
        "convergence_sites": [
            {
                "site_id": "primary",
                "node_ids": ["observed_1", "observed_2"],
                "edge_ids": [0],
            }
        ],
        "residue": ["the chair stays tipped"],
        "surface_output": {
            "audience_prompt": "a basement room",
            "geometry": ["racks frame the room"],
            "light": [],
            "material": [],
            "state_differentials": [],
            "convergence": [],
            "residue": [],
        },
        "character_locks": ["no nose", "hairless scalp"],
        "production_constraints": [
            "9:16 vertical",
            "character-lock: no tail",
            "geometry reset",
        ],
    }


def _plan() -> dict[str, object]:
    return {
        "storyboard_id": "lock-board",
        "frames": [
            {
                "frame_id": "frame-001",
                "node_states": {"observed_1": "occupied", "observed_2": "silent"},
                "duration_seconds": 10,
                "title": "Minder startles",
                "scene": "basement",
                "sound": SOUND,
            },
            {
                "frame_id": "frame-002",
                "node_states": {"observed_1": "empty", "observed_2": "sounding"},
            },
        ],
    }


def _packet() -> dict[str, object]:
    graph = build_graph(_spec())
    assert graph["validation"]["status"] == "VALID", graph["validation"]
    storyboard = propagate(graph, _plan())
    assert storyboard["validation"]["status"] == "VALID", storyboard["validation"]
    first = storyboard["frames"][0]
    assert first["duration_seconds"] == 10
    assert first["sound"] == SOUND
    assert first["title"] == "Minder startles"
    assert first["scene"] == "basement"
    return build_packet(graph, storyboard, "generic")


def _assert_positive(text: str) -> None:
    assert NOSE in text
    assert FACE in text
    assert "hairless scalp" in text
    assert "the locked character has no tail" in text
    assert "the tail stays absent in every frame" in text
    assert "geometry reset" not in text


def _assert_shared(packet: dict[str, object]) -> None:
    shared = packet["shared_constraints"]
    assert isinstance(shared, dict)
    assert shared["character_locks"] == ["no nose", "hairless scalp", "no tail"]
    assert shared["aspect_ratio"] == "9:16"
    negatives = shared["negative_constraints"]
    assert isinstance(negatives, list)
    assert negatives.count("no nose") == 1
    assert "no tail" in negatives
    assert "hairless scalp" not in negatives


def test_packet_carries_locks_aspect_and_frame_fields() -> None:
    packet = _packet()
    _assert_shared(packet)
    frames = packet["frames"]
    assert isinstance(frames, list)
    params = frames[0]["provider_parameters"]
    assert params["duration_seconds"] == 10
    assert params["sound"] == SOUND
    assert params["title"] == "Minder startles"
    assert params["scene"] == "basement"
    generic = adapt(packet, "generic")
    assert generic["validation"]["status"] == "VALID", generic["validation"]
    for frame in generic["frames"]:
        _assert_positive(str(frame["prompt"]))
        assert "no nose" in frame["negative_constraints"]


def test_keyframe_passes_aspect_duration_sound_and_locks() -> None:
    movie = adapt(_packet(), "keyframe")
    assert movie["aspectRatio"] == "9:16"
    assert movie["targetDurationSeconds"] == 14
    assert movie["shots"][0]["durationSeconds"] == 10
    assert movie["shots"][0]["audio"]["sound"] == SOUND
    fallback = "no scored music; evidenced room presence only"
    assert movie["shots"][1]["audio"]["sound"] == fallback
    assert movie["shots"][0]["title"] == "Minder startles"
    assert movie["shots"][0]["scene"] == "basement"
    for shot in movie["shots"]:
        _assert_positive(str(shot["imagePrompt"]))
        _assert_positive(str(shot["videoPrompt"]))


def test_video_brief_shot_and_adapt_carry_locks() -> None:
    brief = {
        "dramatic_problem": "the minder is erased when the speaker sounds",
        "desired_state_change": "the chair empties",
        "character_locks": ["no nose", "hairless scalp"],
        "production_constraints": ["9:16 vertical", "character-lock: no tail"],
    }
    text = yaml.safe_dump(brief)
    shot = video_shot(text, None, "locks")
    assert shot.get("status") != "NOT_COMPUTABLE", shot
    body = shot["result"]["shot"]
    assert body["aspect_ratio"] == "9:16"
    assert body["character_locks"] == ["no nose", "hairless scalp", "no tail"]
    assert "no nose" in body["negative_constraints"]
    assert "no tail" in body["negative_constraints"]
    assert "geometry reset" in body["negative_constraints"]
    adapted = video_adapt(yaml.safe_dump(shot), "locks", "generic")
    assert adapted.get("status") != "NOT_COMPUTABLE", adapted.get("diagnostic")
    frame = adapted["result"]["adapted_packet"]["frames"][0]
    _assert_positive(str(frame["prompt"]))
    assert "geometry reset" in frame["negative_constraints"]
    movie_meta = video_adapt(yaml.safe_dump(shot), "locks", "keyframe")
    assert movie_meta.get("status") != "NOT_COMPUTABLE", movie_meta.get("diagnostic")
    movie = movie_meta["result"]["adapted_packet"]
    assert movie["aspectRatio"] == "9:16"
    _assert_positive(str(movie["shots"][0]["imagePrompt"]))
    _assert_positive(str(movie["shots"][0]["videoPrompt"]))


def _compile(provider: str, out: Path) -> None:
    brief = yaml.safe_load((EXAMPLE / "brief.yaml").read_text(encoding="utf-8"))
    plan = yaml.safe_load((EXAMPLE / "storyboard-plan.yaml").read_text(encoding="utf-8"))
    assert isinstance(brief, dict)
    assert isinstance(plan, dict)
    brief["character_locks"] = ["no nose"]
    constraints = list(brief.get("production_constraints") or [])
    constraints.append("9:16 vertical")
    brief["production_constraints"] = constraints
    frames = plan["frames"]
    assert isinstance(frames, list)
    frames[0]["duration_seconds"] = 10
    frames[0]["sound"] = SOUND
    brief_path = out / "brief.yaml"
    plan_path = out / "plan.yaml"
    brief_path.write_text(yaml.safe_dump(brief), encoding="utf-8")
    plan_path.write_text(yaml.safe_dump(plan), encoding="utf-8")
    proc = subprocess.run(
        [
            PY,
            str(ROOT / "scripts/kubrick_compile.py"),
            "--brief",
            str(brief_path),
            "--ledger",
            str(EXAMPLE / "symbolic-ledger.yaml"),
            "--mode",
            "storyboard",
            "--storyboard-plan",
            str(plan_path),
            "--provider",
            provider,
            "--out",
            str(out / provider),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    receipt = json.loads(proc.stdout)
    assert receipt["status"] == "COMPILED"


def test_compile_carries_nose_lock_and_vertical_frame() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        out = Path(temporary)
        _compile("generic", out)
        _compile("keyframe", out)
        generic_packet = yaml.safe_load(
            (out / "generic" / "model-adapter-packet.yaml").read_text(encoding="utf-8")
        )
        generic_prompt = yaml.safe_load(
            (out / "generic" / "generic-prompt-packet.yaml").read_text(encoding="utf-8")
        )
        movie = yaml.safe_load(
            (out / "keyframe" / "keyframe-prompt-packet.yaml").read_text(encoding="utf-8")
        )
        shared = generic_packet["shared_constraints"]
        assert "no nose" in shared["character_locks"]
        assert "no nose" in shared["negative_constraints"]
        assert shared["aspect_ratio"] == "9:16"
        for frame in generic_prompt["frames"]:
            assert NOSE in frame["prompt"]
            assert FACE in frame["prompt"]
            assert "geometry reset" not in frame["prompt"]
            assert "no nose" in frame["negative_constraints"]
        assert movie["aspectRatio"] == "9:16"
        assert movie["targetDurationSeconds"] == 18
        assert movie["shots"][0]["durationSeconds"] == 10
        assert movie["shots"][0]["audio"]["sound"] == SOUND
        for shot in movie["shots"]:
            assert NOSE in shot["imagePrompt"] and NOSE in shot["videoPrompt"]
            assert FACE in shot["imagePrompt"] and FACE in shot["videoPrompt"]
            assert "geometry reset" not in shot["imagePrompt"]
            assert "geometry reset" not in shot["videoPrompt"]


def main() -> None:
    test_prefixed_unknown_lock_and_plain_lock()
    test_packet_carries_locks_aspect_and_frame_fields()
    test_keyframe_passes_aspect_duration_sound_and_locks()
    test_video_brief_shot_and_adapt_carry_locks()
    test_compile_carries_nose_lock_and_vertical_frame()
    print("character lock tests: PASS")


if __name__ == "__main__":
    main()
