#!/usr/bin/env python3
"""Tests for short beats, joins, holds, and techniques. Issues #25–#27 and #31."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import cast

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from adapt_keyframe import adapt_keyframe_packet  # noqa: E402
from adapt_provider import adapt  # noqa: E402
from build_model_adapter_packet import build as build_packet  # noqa: E402
from build_motif_graph import build as build_graph  # noqa: E402
from propagate_graph_state import propagate  # noqa: E402
from shot_plan import (  # noqa: E402
    _technique_matches,
    chain_source,
    enrich_prompts,
    exclusivity_reason,
    generation_seconds,
    load_techniques,
    match_techniques,
    merged_warnings,
    opens_with_exit,
    padding_error,
    padding_errors,
    short_beat_warnings,
    validate_joins,
)
from surface_compilers import video_adapt  # noqa: E402

FIXTURE = ROOT / "evals/fixtures/myslef"
EXAMPLE = ROOT / "examples/myslef-minder"
SCHEMA = json.loads(
    (ROOT / "schemas/keyframe-create-movie.schema.json").read_text(encoding="utf-8")
)
REASON = (
    "Seedance 2.5: startImage and referenceImages are mutually exclusive; "
    "references dropped on shot frame-002"
)
FLICKER = "lights flicker to near-black, figures gone on recovery"
PATH = "show the distance, the path, and the end state of the action"


def _load(path: Path) -> dict[str, object]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _shot(frame_id: str, seconds: float, **extra: object) -> dict[str, object]:
    frame: dict[str, object] = {
        "frame_id": frame_id,
        "prompt": "a room holds still",
        "provider_parameters": {"duration_seconds": seconds},
    }
    frame.update(extra)
    return frame


def _packet(frames: list[dict[str, object]], **extra: object) -> dict[str, object]:
    packet: dict[str, object] = {
        "source_graph_id": "prep-graph",
        "provider": "keyframe",
        "validation": {"status": "VALID", "errors": []},
        "referenceImages": ["ref://room"],
        "frames": frames,
    }
    packet.update(extra)
    return packet


def _rows(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise AssertionError(value)
    return [cast(dict[str, object], item) for item in value]


def _num(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AssertionError(value)
    return float(value)


def _codes(payload: dict[str, object], code: str) -> list[dict[str, object]]:
    raw = payload.get("prep_warnings")
    assert isinstance(raw, list)
    return [item for item in raw if isinstance(item, dict) and item.get("code") == code]


def test_short_beat_threshold_edges() -> None:
    frames = [_shot("frame-001", 2.0), _shot("frame-002", 1.0), _shot("frame-003", 2.01)]
    found = short_beat_warnings(frames, "keyframe")
    shots = [item["shot"] for item in found]
    assert shots == ["frame-001", "frame-002"]
    assert "frame-003" not in shots
    top = found[0]
    assert set(top) == {"code", "shot", "message", "recommendation"}
    assert top["code"] == "SHORT_BEAT"
    assert "frame-001" in top["message"] and "2s" in top["message"]
    assert "2s short-beat threshold" in top["message"]
    assert "multi-shot single clip" in top["message"]
    assert "own separate clip" in top["recommendation"]
    assert "minimum of 3s" in top["recommendation"] and "then trim" in top["recommendation"]
    assert (
        short_beat_warnings(frames, "keyframe", document={"short_beat_threshold_seconds": 1.0})[0][
            "shot"
        ] == "frame-002"
    )
    assert short_beat_warnings([_shot("only", 2.0)], "keyframe") == []
    assert short_beat_warnings(frames, "generic") == []
    assert short_beat_warnings(frames, "grok-imagine") == []
    stale = [{"code": "SHORT_BEAT", "shot": "old", "message": "old", "recommendation": "old"}]
    fresh = [
        {
            "code": "REFERENCE_LOCK_CONTRADICTION",
            "shot": "myslef",
            "message": "lock",
            "recommendation": "edit",
        }
    ]
    merged = merged_warnings({"prep_warnings": [*stale, *fresh]}, [])
    assert [item["code"] for item in merged] == ["REFERENCE_LOCK_CONTRADICTION"]


def test_joins_fail_closed_and_chain_is_non_adjacent() -> None:
    frames: list[dict[str, object]] = [
        {"frame_id": "frame-001", "join": "cut"},
        {"frame_id": "frame-002", "join": {"chain_from": "frame-001", "at_seconds": 2}},
        {"frame_id": "frame-003", "join": "cut"},
        {"frame_id": "frame-004", "join": {"chain_from": "frame-002"}},
    ]
    assert validate_joins(frames) == []
    assert chain_source(frames[3]) == "frame-002"
    unknown = validate_joins([{"frame_id": "frame-002", "join": {"chain_from": "missing"}}])
    assert "unknown frame" in unknown[0]
    same = validate_joins([{"frame_id": "frame-001", "join": {"chain_from": "frame-001"}}])
    assert "same frame" in same[0]
    later = validate_joins(
        [
            {"frame_id": "frame-001", "join": {"chain_from": "frame-002"}},
            {"frame_id": "frame-002", "join": "cut"},
        ]
    )
    assert "later frame" in later[0]
    assert "must be cut or chain_from" in validate_joins([{"frame_id": "a", "join": "fade"}])[0]
    assert (
        "chain_from is missing"
        in validate_joins([{"frame_id": "a", "join": {"chain_from": ""}}])[0]
    )
    assert (
        "not a number"
        in validate_joins([{"frame_id": "b", "join": {"chain_from": "a", "at_seconds": "soon"}}])[0]
    )
    assert exclusivity_reason("generic", "frame-002") is None
    assert exclusivity_reason("keyframe", "frame-002") == REASON


def test_chained_keyframe_drops_references() -> None:
    movie = adapt_keyframe_packet(
        _packet(
            [
                _shot("frame-001", 4, reference_images=["ref://keep"]),
                _shot(
                    "frame-002",
                    4,
                    join={"chain_from": "frame-001", "at_seconds": 1.5},
                    reference_images=["ref://drop"],
                ),
                _shot("frame-004", 4, join={"chain_from": "frame-001"}),
            ]
        )
    )
    jsonschema.validate(movie, SCHEMA)
    assert "referenceImages" not in movie
    first, second, third = movie["shots"]
    assert first["referenceImages"] == ["ref://keep"]
    assert "startImage" not in first
    assert second["startImage"] == {"sourceFrame": "frame-001", "atSeconds": 1.5}
    assert "referenceImages" not in second
    assert third["startImage"] == {"sourceFrame": "frame-001"}
    dropped = {item["shot"]: item for item in movie["dropped_references"]}
    assert dropped["frame-002"]["references"] == ["ref://drop"]
    assert dropped["frame-002"]["reason"] == REASON
    assert dropped["frame-004"]["references"] == ["ref://room"]
    assert "frame-001" not in dropped


def test_hold_padding_preserves_runtime_and_fails_past_max() -> None:
    generated, hold = generation_seconds(2.0, chained=True, exit_open=False, provider="keyframe")
    assert (generated, hold) == (3.6, 1.6)
    assert generation_seconds(2.0, chained=False, exit_open=False, provider="keyframe") == (
        3.0, 0.0)
    assert generation_seconds(4.0, chained=True, exit_open=True, provider="keyframe") == (4.0, 0.0)
    assert opens_with_exit({"opens_with": "exit"})
    assert opens_with_exit({"opens_with": "WALKS OUT"})
    assert opens_with_exit({"action": "the minder walks out of frame right"})
    assert opens_with_exit({"action": "the minder exits"})
    assert opens_with_exit({"prompt": "he leaves frame"})
    assert opens_with_exit({"action": "sits still; the minder walks out"}) is False
    exit_movie = adapt_keyframe_packet(
        _packet(
            [
                _shot("frame-001", 4, reference_images=["ref://keep"]),
                _shot(
                    "frame-002",
                    4,
                    join={"chain_from": "frame-001"},
                    opens_with="exit",
                    action="the minder walks out",
                ),
            ]
        )
    )
    jsonschema.validate(exit_movie, SCHEMA)
    assert exit_movie["shots"][1]["durationSeconds"] == 4
    cuts = {item["shot"]: item for item in exit_movie["cut_list"]}
    assert cuts["frame-002"]["source_in"] == 0
    assert cuts["frame-002"]["source_out"] == 4
    assert cuts["frame-002"]["planned_seconds"] == 4


def test_chained_hold_cut_list_and_max() -> None:
    held = adapt_keyframe_packet(
        _packet(
            [
                _shot("frame-001", 4),
                _shot(
                    "frame-002", 2, join={"chain_from": "frame-001"}, action="the minder springs up"
                ),
            ]
        )
    )
    jsonschema.validate(held, SCHEMA)
    assert held["shots"][1]["durationSeconds"] == 3.6
    held_cut = {item["shot"]: item for item in held["cut_list"]}["frame-002"]
    assert held_cut["source_in"] == 1.6
    assert held_cut["source_out"] == 3.6
    assert held_cut["generated_seconds"] - held_cut["source_in"] == held_cut["planned_seconds"]
    used = sum(item["source_out"] - item["source_in"] for item in held["cut_list"])
    assert used == 6
    past = padding_error("frame-009", 60.6, "keyframe", hold=1.6)
    assert past is not None
    for text in (
        "frame-009",
        "60.6",
        "keyframe",
        "maximum",
        "60",
        "refusing to clamp or drop the shot",
    ):
        assert text in past
    assert padding_error("frame-009", 60.0, "keyframe", hold=1.6) is None
    assert padding_error("frame-009", 90, "keyframe", hold=0) is None
    assert padding_error("frame-009", 90, "flux", hold=1.6) is None
    assert padding_errors([_shot("frame-001", 2)], "keyframe", 4) == []


def test_unpadded_duration_still_fails_closed() -> None:
    refused = adapt_keyframe_packet(
        _packet(
            [
                _shot("frame-001", 4),
                _shot("frame-009", 59, join={"chain_from": "frame-001"}),
            ]
        )
    )
    assert refused["status"] == "NOT_COMPUTABLE"
    assert "shots" not in refused
    assert "maximum" in refused["message"]
    assert "frame-009" in refused["message"]
    for seconds in (60.1, 61):
        plain = adapt_keyframe_packet(_packet([_shot("frame-001", seconds)], referenceImages=[]))
        assert plain["status"] == "NOT_COMPUTABLE"
        assert "shots" not in plain
        assert "outside the allowed 3–60 seconds" in plain["message"]
        assert "refusing to clamp or drop the shot" in plain["message"]


def test_techniques_are_suggestions_until_opt_in() -> None:
    library = load_techniques()
    jsonschema.validate(
        library, json.loads((ROOT / "schemas/techniques.schema.json").read_text(encoding="utf-8"))
    )
    ids = [str(item["id"]) for item in _rows(library["techniques"])]
    assert ids == ["clear-characters-by-flicker", "physical-action-distance-path"]
    frames: list[dict[str, object]] = [
        {"frame_id": "frame-001", "characters": ["minder", "myslef"], "action": "sits"},
        {
            "frame_id": "frame-002",
            "characters": ["minder", "myslef"],
            "join": {"chain_from": "frame-001"},
            "action": "the chair skids",
        },
        {"frame_id": "frame-003", "action": "the chair skids"},
        {
            "frame_id": "frame-004",
            "characters": [],
            "join": {"chain_from": "frame-002"},
            "action": "walks out",
            "apply_techniques": ["clear-characters-by-flicker"],
        },
        {"frame_id": "frame-005", "join": {"chain_from": "frame-001"}, "action": "gone"},
    ]
    found = match_techniques(frames, "keyframe")
    by_shot: dict[str, list[str]] = {}
    for item in found:
        by_shot.setdefault(str(item["shot"]), []).append(str(item["id"]))
    assert by_shot["frame-002"] == ["physical-action-distance-path"]
    assert by_shot["frame-003"] == ["physical-action-distance-path"]
    assert by_shot["frame-004"] == ["clear-characters-by-flicker"]
    assert found[-1]["applied"] is True and found[0]["applied"] is False
    assert "frame-001" not in by_shot and "frame-005" not in by_shot
    assert match_techniques(frames, "flux") == []
    assert match_techniques([{"frame_id": "a", "action": "empty and tipped"}], "keyframe") == []
    swapped: list[dict[str, object]] = [
        {"frame_id": "a", "characters": ["minder", "myslef"]},
        {"frame_id": "b", "characters": ["minder", "other"], "join": {"chain_from": "a"}},
    ]
    assert any(
        item["id"] == "clear-characters-by-flicker" for item in match_techniques(swapped, "generic")
    )
    assert _technique_matches({"providers": "keyframe", "triggers": {}}, frames[0], frames, "flux")
    assert _technique_matches({"triggers": "bad"}, frames[0], frames, "keyframe") is False
    prompts, prep = enrich_prompts(
        {},
        frames[:4],
        "generic",
        lambda frame: "base action",
    )
    assert FLICKER not in prompts[1]
    assert PATH not in prompts[1]
    assert FLICKER in prompts[3]
    assert prep.techniques[-1]["applied"] is True


def test_invalid_technique_library_fails() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "techniques.yaml"
        path.write_text("version: '1'\ntechniques:\n  - id: only\n", encoding="utf-8")
        try:
            load_techniques(path)
        except Exception as exc:
            assert type(exc).__name__ == "ValidationError"
        else:
            raise AssertionError("invalid technique library must fail")
    missing = ROOT / "assets/techniques/missing.yaml"
    try:
        load_techniques(missing)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("missing library must fail")


def _myslef_packet(provider: str) -> dict[str, object]:
    graph = build_graph(_load(FIXTURE / "minder-brief.yaml"))
    board = propagate(graph, _load(FIXTURE / "minder-storyboard.yaml"))
    assert board["validation"]["status"] == "VALID", board["validation"]
    packet = build_packet(graph, board, provider)
    return packet


def test_myslef_fixture_locks_and_keyframe_plan() -> None:
    assert (FIXTURE / "minder-brief.yaml").read_bytes() == (EXAMPLE / "brief.yaml").read_bytes()
    assert (FIXTURE / "minder-storyboard.yaml").read_bytes() == (
        EXAMPLE / "storyboard-plan.yaml"
    ).read_bytes()
    generic = _myslef_packet("generic")
    validation = _rows([generic["validation"]])[0]
    assert validation["status"] == "VALID", validation
    prompts = [str(frame["prompt"]) for frame in _rows(generic["frames"])]
    assert "the chair stays tipped" not in prompts[0]
    assert "tipped" not in prompts[0]
    assert "CHAIR LOCK: upright, occupied, at the bench" in prompts[0]
    assert "WARDROBE LOCK: minder wears" in prompts[0]
    assert prompts[0].count("WARDROBE LOCK:") == 1
    assert "CHAIR LOCK: shoved back from the bench; then tipped" in prompts[1]
    assert STABLE_PIECE in prompts[3]
    assert FLICKER not in prompts[3]
    adapted = adapt(generic, "generic")
    assert adapted["validation"]["status"] == "VALID", adapted["validation"]
    assert _codes(adapted, "SHORT_BEAT") == []
    assert _codes(adapted, "REFERENCE_LOCK_CONTRADICTION")
    assert any(
        item["id"] == "physical-action-distance-path" for item in adapted["technique_suggestions"]
    )
    refused = adapt(_myslef_packet("keyframe"), "keyframe")
    _assert_myslef_keyframe(refused)


def _assert_myslef_keyframe(movie: dict[str, object]) -> None:
    assert movie.get("status") != "NOT_COMPUTABLE" and movie["aspectRatio"] == "9:16"
    assert movie["targetDurationSeconds"] == 12 and movie["plannedDurationSeconds"] == 6
    assert {item["shot"] for item in _codes(movie, "SHORT_BEAT")} == {
        "frame-001", "frame-002", "frame-003", "frame-004",
    }
    assert _codes(movie, "KNOWN_DRIFT")[0]["shot"] == "frame-002"
    ref = _codes(movie, "REFERENCE_LOCK_CONTRADICTION")[0]
    assert ref["shot"] is None and ref["character"] == "myslef"
    shots = _rows(movie["shots"])
    _myslef_cuts(movie, shots)
    for index, shot in enumerate(shots):
        image, video = str(shot["imagePrompt"]), str(shot["videoPrompt"])
        assert "preserve prior object state chair" not in image + video
        if index == 1:
            assert "upright" not in image + video and "CHAIR LOCK" in video


def _myslef_cuts(movie: dict[str, object], shots: list[dict[str, object]]) -> None:
    cuts = {str(item["shot"]): item for item in _rows(movie["cut_list"])}
    expect = {
        "frame-001": (3, 0, 2),
        "frame-002": (3, 1.6, 2.6),
        "frame-003": (3, 0, 2),
        "frame-004": (3, 0, 1),
    }
    for shot_id, spec in expect.items():
        cut = cuts[shot_id]
        assert (cut["generated_seconds"], cut["source_in"], cut["source_out"]) == spec
    assert sum(_num(item["source_out"]) - _num(item["source_in"]) for item in cuts.values()) == 6
    start = shots[1]["startImage"]
    assert isinstance(start, dict) and start["sourceFrame"] == "frame-001" and _num(
        start.get("atSeconds")) == 2
    assert shots[3]["startImage"] == {"sourceFrame": "frame-002"}
    assert "referenceImages" not in shots[1] and "referenceImages" not in shots[3]
    assert shots[0].get("referenceImages") and shots[2].get("referenceImages")
    dropped = {str(item["shot"]): item for item in _rows(movie["dropped_references"])}
    assert dropped["frame-002"]["references"] == ["ref://chair"]
    assert dropped["frame-004"]["references"] == ["ref://exit"]
    assert "Seedance 2.5" in str(dropped["frame-002"]["reason"])
    suggestions = {str(item["shot"]): item for item in _rows(movie["technique_suggestions"])}
    assert suggestions["frame-002"]["id"] == "physical-action-distance-path"
    assert suggestions["frame-004"]["id"] == "clear-characters-by-flicker"
    assert all(item["applied"] is False for item in suggestions.values())


def test_myslef_video_and_unreachable_prop() -> None:
    video = video_adapt(
        (EXAMPLE / "storyboard-plan.yaml").read_text(encoding="utf-8"), "myslef", "keyframe"
    )
    assert video["status"] == "PROPOSED"
    _assert_myslef_keyframe(video["result"]["adapted_packet"])
    bad = build_packet(
        build_graph(_load(FIXTURE / "minder-brief.yaml")),
        {
            "frames": [
                {"frame_id": "frame-001", "node_states": {}, "prop_states": {"chair": "C3"}},
                {
                    "frame_id": "frame-002",
                    "node_states": {},
                    "prop_states": {"chair": "C3->beside the desk"},
                },
            ],
            "props": {
                "chair": {
                    "states": {
                        "C0": "beside the desk",
                        "C3": "tipped on its side",
                    }
                }
            },
        },
        "generic",
    )
    assert bad["validation"]["status"] == "INVALID"
    assert any(
        "prop chair" in item and "frame-001" in item and "frame-002" in item
        for item in bad["validation"]["errors"]
    )


STABLE_PIECE = "on its side at the far end of the aisle by the rack gap; it does not move"


def main() -> None:
    test_short_beat_threshold_edges()
    test_joins_fail_closed_and_chain_is_non_adjacent()
    test_chained_keyframe_drops_references()
    test_hold_padding_preserves_runtime_and_fails_past_max()
    test_chained_hold_cut_list_and_max()
    test_unpadded_duration_still_fails_closed()
    test_techniques_are_suggestions_until_opt_in()
    test_invalid_technique_library_fails()
    test_myslef_fixture_locks_and_keyframe_plan()
    test_myslef_video_and_unreachable_prop()
    print("shot plan tests: PASS")


if __name__ == "__main__":
    main()
