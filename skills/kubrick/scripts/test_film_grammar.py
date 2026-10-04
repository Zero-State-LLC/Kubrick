#!/usr/bin/env python3
"""Camera, cut, and film-grammar tests for issues #77 and #78."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from adapt_provider import adapt  # noqa: E402
from film_grammar import (  # noqa: E402
    direction_clauses,
    frame_prep_warnings,
    load_grammar,
    shot_camera,
)
from prompt_text import frame_state_clauses, join_clauses, render_frame_prompt  # noqa: E402
from propagate_graph_state import propagate  # noqa: E402
from storyboard_prompts import adapter_packet_from_document, shots_from_document  # noqa: E402

GRAMMAR = ROOT / "assets" / "grammar" / "film_grammar.yaml"
SCHEMA = ROOT / "schemas" / "film-grammar.schema.json"
STORY_SCHEMA = ROOT / "schemas" / "storyboard-symbolic-state.schema.yaml"
EXAMPLE = ROOT / "examples" / "myslef-minder" / "storyboard-plan.yaml"
LABELS = {"observed_1": "chair"}
DEFAULT_CAMERA = {
    "framing": "evidenced framing",
    "movement": "static unless evidenced",
}


def _load(path: Path) -> dict[str, object]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise AssertionError("expected a mapping")
    return {str(key): value for key, value in loaded.items()}


def _frame(frame_id: str, **extra: object) -> dict[str, object]:
    base: dict[str, object] = {
        "frame_id": frame_id,
        "node_states": {"observed_1": "present"},
        "motif_ownership": {"observed_1": None},
        "object_states": {"chair": "upright"},
        "light_states": {"room": "dim"},
        "material_states": {"chair": "wood"},
        "residue": [],
        "convergence_sites": ["primary"],
        "action": "holds still",
        "duration_seconds": 4,
    }
    base.update(extra)
    return base


def _board(frames: list[dict[str, object]]) -> dict[str, object]:
    return {
        "storyboard_id": "grammar-board",
        "title": "grammar",
        "graph_id": "grammar-graph",
        "node_labels": dict(LABELS),
        "frames": frames,
    }


def _graph() -> dict[str, object]:
    return {
        "graph_id": "grammar-graph",
        "validation": {"status": "VALID", "errors": []},
        "nodes": [{"id": "observed_1", "initial_state": "present"}],
        "convergence_sites": [{"site_id": "primary"}],
        "residue": [],
    }


def _codes(payload: object, code: str) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        return []
    raw = payload.get("prep_warnings")
    if not isinstance(raw, list):
        return []
    found: list[dict[str, object]] = []
    for item in raw:
        if isinstance(item, dict) and item.get("code") == code:
            found.append({str(key): value for key, value in item.items()})
    return found


def _warning_codes(frames: list[dict[str, object]]) -> list[str]:
    return [str(item.get("code") or "") for item in frame_prep_warnings(frames)]


def test_registry_schema_unique_ids_and_coverage() -> None:
    raw = _load(GRAMMAR)
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(raw, schema)
    library = load_grammar()
    entries = library.entries
    assert len(entries) >= 65
    ids = [str(entry.get("id")) for entry in entries]
    assert len(ids) == len(set(ids))
    categories = {str(entry.get("category")) for entry in entries}
    assert categories == {
        "shot_size",
        "angle",
        "lens_band",
        "move",
        "lighting",
        "edit",
        "composition_9_16",
        "composition",
        "blocking",
        "camera_height",
        "continuity",
    }
    assert raw.get("schema_version") == "1.1.0"
    by_id = {str(entry.get("id")): entry for entry in entries}
    fresh = (
        "rule-of-thirds-eyes", "joint-safe-crop", "both-shoulders-in",
        "head-proportion-numeric", "negative-space-top", "short-side",
        "foreground-layer", "frame-within-frame", "one-point-perspective",
        "two-shot-vertical", "shoulder-level", "hip-level", "ground-level",
        "front-on-square", "axis-anchor-body-part", "screen-direction-hold",
        "eyeline-match", "shot-reverse-shot", "buffer-shot", "three-point",
        "emitters-dark", "end-frame-anchor", "start-hold", "insert-i2v-start",
    )
    assert len(fresh) == 24
    for ident in fresh:
        assert ident in by_id
        assert None not in by_id[ident].values()
    assert by_id["two-shot-vertical"].get("category") == "composition_9_16"
    assert "untested" in str(by_id["normal-lens"].get("provider_notes"))
    assert "untested" in str(by_id["ots"].get("provider_notes"))
    assert by_id["ots"].get("targets")
    for entry in entries:
        assert str(entry.get("definition") or "").strip()
        phrase = str(entry.get("prompt_phrase") or "")
        assert phrase.strip()
        assert ";" not in phrase
        assert isinstance(entry.get("conflicts"), list)
        assert str(entry.get("evidence") or "").strip()
    cited = " ".join(str(entry.get("evidence") or "") for entry in entries)
    for needle in ("shot 03", "shot 04", "shot 05", "shot 06", "9.25"):
        assert needle in cited


def test_duplicate_id_is_rejected() -> None:
    raw = _load(GRAMMAR)
    entries = raw.get("entries")
    assert isinstance(entries, list) and entries
    first = entries[0]
    assert isinstance(first, dict)
    clone = dict(first)
    raw["entries"] = [*entries, clone]
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "dup.yaml"
        path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
        try:
            load_grammar(path)
        except ValueError as exc:
            assert "duplicate" in str(exc)
        else:
            raise AssertionError("duplicate id was accepted")


def test_prompt_expansion_and_lens_bands() -> None:
    wide = _frame("frame-001", camera={"lens_mm": 35, "move": "slow push-in", "size": "ws"})
    clauses = direction_clauses(wide)
    text = " ".join(clauses)
    assert "35 mm lens" in text
    assert "push-in" in text
    assert "wide shot" in text
    assert "28 to 35" in text
    tele = direction_clauses(
        _frame("frame-002", camera={"lens_mm": 85, "size": "ecu", "move": "locked"})
    )
    tele_text = " ".join(tele)
    assert "85 mm lens" in tele_text
    assert "ECU" in tele_text
    assert "locked-off" in tele_text
    assert "85" in tele_text
    normal = " ".join(direction_clauses(_frame("frame-003", camera={"lens_mm": 50})))
    assert "50 mm lens" in normal and "normal lens" in normal
    long_tele = " ".join(direction_clauses(_frame("frame-004", camera={"lens_mm": 135})))
    assert "135 mm lens" in long_tele and "long telephoto" in long_tele
    unmapped = frame_prep_warnings([_frame("frame-005", camera={"lens_mm": 10})])
    assert any(item.get("code") == "LENS_BAND_UNMAPPED" for item in unmapped)
    shown = " ".join(direction_clauses(_frame("frame-005", camera={"lens_mm": 10})))
    assert "10 mm lens" in shown
    assert "ultra-wide" not in shown


def test_round_trip_generic_and_keyframe() -> None:
    document = _board([
        _frame(
            "frame-001",
            camera={"lens_mm": 35, "move": "push-in", "size": "ws"},
            cut="hard-cut",
        ),
        _frame(
            "frame-002",
            camera={"lens_mm": 85, "move": "locked", "size": "ecu"},
            duration_seconds=4,
        ),
    ])
    packet = adapter_packet_from_document(document, provider="generic")
    generic = adapt(packet, "generic")
    generic_text = json.dumps(generic)
    for needle in ("35", "push-in", "hard cut", "85", "ECU", "locked-off"):
        assert needle in generic_text
    frames = generic.get("frames")
    assert isinstance(frames, list)
    first = frames[0]
    assert isinstance(first, dict)
    assert "35" in str(first.get("prompt")) and "push-in" in str(first.get("prompt"))
    movie = adapt(packet, "keyframe")
    shots = movie.get("shots")
    assert isinstance(shots, list) and len(shots) == 2
    opening = shots[0]
    closing = shots[1]
    assert isinstance(opening, dict) and isinstance(closing, dict)
    assert "35" in str(opening.get("videoPrompt"))
    assert "push-in" in str(opening.get("videoPrompt"))
    assert "hard cut" in str(opening.get("videoPrompt"))
    assert "85" in str(closing.get("videoPrompt"))
    assert "ECU" in str(closing.get("videoPrompt"))
    multi = str(movie.get("multi_shot_prompt") or "")
    assert "Shot 1" in multi and "35" in multi and "push-in" in multi
    assert "85" in multi and "ECU" in multi
    contract = shots_from_document(document)
    assert contract[0]["camera"] != DEFAULT_CAMERA
    assert "push-in" in str(contract[0]["camera"])
    assert "wide shot" in str(contract[0]["camera"])


def test_frames_without_camera_keep_current_output() -> None:
    bare = _frame("frame-001")
    other = _frame("frame-002")
    assert direction_clauses(bare) == []
    assert shot_camera(bare) == DEFAULT_CAMERA
    rendered = render_frame_prompt([], bare, LABELS)
    assert rendered == join_clauses([*frame_state_clauses(bare, LABELS), "holds still"])
    assert "push-in" not in rendered and "mm lens" not in rendered
    document = _board([bare, other])
    packet = adapter_packet_from_document(document, provider="generic")
    generic = json.dumps(adapt(packet, "generic"))
    assert "push-in" not in generic and "mm lens" not in generic
    movie = adapt(packet, "keyframe")
    blob = json.dumps(movie)
    assert "push-in" not in blob and "mm lens" not in blob
    assert shots_from_document(document)[0]["camera"] == DEFAULT_CAMERA
    assert "UNKNOWN_FIELD" not in _warning_codes([bare, other])
    assert "UNKNOWN_GRAMMAR_TERM" not in _warning_codes([bare, other])


def test_unknown_field_warns_and_is_not_copied() -> None:
    secret = _frame("frame-001", bogon="secret-lens")
    secret["camera"] = {"lens_mm": 35, "move": "push-in", "bogus": "nope"}
    plan = _board([secret, _frame("frame-002")])
    board = propagate(_graph(), plan)
    validation = board["validation"]
    assert isinstance(validation, dict)
    assert validation["status"] == "VALID"
    warnings = validation["warnings"]
    assert isinstance(warnings, list)
    text = " ".join(str(item) for item in warnings)
    assert "UNKNOWN_FIELD" in text and "bogon" in text and "bogus" in text
    frames = board["frames"]
    assert isinstance(frames, list)
    first = frames[0]
    assert isinstance(first, dict)
    assert "bogon" not in first
    camera = first.get("camera")
    assert isinstance(camera, dict)
    assert "bogus" not in camera
    assert camera.get("lens_mm") == 35
    assert "secret-lens" not in json.dumps(frames)
    schema = yaml.safe_load(STORY_SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(board, schema)
    packet = adapter_packet_from_document(plan, provider="generic")
    assert _codes(packet, "UNKNOWN_FIELD")
    prompt = packet["frames"]
    assert isinstance(prompt, list)
    opening = prompt[0]
    assert isinstance(opening, dict)
    assert "secret-lens" not in str(opening.get("prompt"))
    assert "35" in str(opening.get("prompt")) and "push-in" in str(opening.get("prompt"))


def test_unknown_term_and_chain_conflict() -> None:
    unknown = _frame("frame-001", camera={"move": "zorp"})
    warns = frame_prep_warnings([unknown, _frame("frame-002")])
    assert any(
        item.get("code") == "UNKNOWN_GRAMMAR_TERM" and "zorp" in str(item.get("message"))
        for item in warns
    )
    assert "zorp" not in " ".join(direction_clauses(unknown))
    chained = [
        _frame("frame-001"),
        _frame(
            "frame-002",
            join={"chain_from": "frame-001"},
            camera={"move": "snap-pan"},
        ),
    ]
    conflict = frame_prep_warnings(chained)
    assert any(item.get("code") == "MOVE_CHAIN_CONFLICT" for item in conflict)
    assert "snap pan" in " ".join(direction_clauses(chained[1]))
    whip = _frame("frame-009", join={"chain_from": "frame-001"}, camera={"move": "whip"})
    assert any(item.get("code") == "MOVE_CHAIN_CONFLICT" for item in frame_prep_warnings([whip]))
    safe = _frame(
        "frame-002",
        join={"chain_from": "frame-001"},
        camera={"move": "handheld, tilt-down"},
    )
    assert "MOVE_CHAIN_CONFLICT" not in _warning_codes([_frame("frame-001"), safe])
    stacked = _frame("frame-003", camera={"move": "push-in and pull-out"})
    assert any(
        item.get("code") == "MOVE_CHAIN_CONFLICT" and "primary" in str(item.get("message"))
        for item in frame_prep_warnings([stacked])
    )
    packet = adapter_packet_from_document(_board(chained), provider="keyframe")
    movie = adapt(packet, "keyframe")
    assert _codes(movie, "MOVE_CHAIN_CONFLICT")
    assert movie.get("status") != "NOT_COMPUTABLE"


def test_negated_and_focus_terms_do_not_borrow_moves() -> None:
    negated = _frame("frame-001", camera={"move": "no push-in"})
    warns = frame_prep_warnings([negated, _frame("frame-002")])
    assert any(
        item.get("code") == "UNKNOWN_GRAMMAR_TERM" and "negated" in str(item.get("message"))
        for item in warns
    )
    assert "push" not in " ".join(direction_clauses(negated))
    wrong_focus = _frame("frame-001", camera={"focus": "push-in"})
    assert "UNKNOWN_GRAMMAR_TERM" in _warning_codes([wrong_focus, _frame("frame-002")])
    assert "push" not in " ".join(direction_clauses(wrong_focus))
    rack = _frame("frame-001", camera={"focus": "rack focus"})
    assert "UNKNOWN_GRAMMAR_TERM" not in _warning_codes([rack, _frame("frame-002")])
    assert "rack focus" in " ".join(direction_clauses(rack))


def test_myslef_example_carries_the_shot_map() -> None:
    plan = _load(EXAMPLE)
    packet = adapter_packet_from_document(plan, provider="generic")
    generic = json.dumps(adapt(packet, "generic"))
    movie = adapt(packet, "keyframe")
    shots = movie.get("shots")
    assert isinstance(shots, list) and len(shots) == 4
    prompts = []
    for shot in shots:
        assert isinstance(shot, dict)
        prompts.append(str(shot.get("videoPrompt") or ""))
    assert "35" in prompts[0] and "push-in" in prompts[0]
    assert "handheld" in prompts[1] and "tilt" in prompts[1]
    assert "85" in prompts[2] and "ECU" in prompts[2] and "locked-off" in prompts[2]
    image = str(shots[3].get("imagePrompt") or "")
    assert "35" in image and "30 degrees" in image and "cut on a sound accent" in image
    assert prompts[3] == "the minder walks out of frame right as push-in"
    assert "head ratio" not in prompts[3].casefold()
    assert "30 degrees" not in prompts[3]
    multi = str(movie.get("multi_shot_prompt") or "")
    for needle in ("35", "push-in", "handheld", "tilt", "85", "ECU", "30 degrees"):
        assert needle in multi
        assert needle in generic
    codes = [str(item.get("code")) for item in frame_prep_warnings(plan.get("frames"))]
    assert "UNKNOWN_FIELD" not in codes
    assert "UNKNOWN_GRAMMAR_TERM" not in codes
    assert "MOVE_CHAIN_CONFLICT" not in codes
    assert "LENS_BAND_UNMAPPED" not in codes


def main() -> None:
    test_registry_schema_unique_ids_and_coverage()
    test_duplicate_id_is_rejected()
    test_prompt_expansion_and_lens_bands()
    test_round_trip_generic_and_keyframe()
    test_frames_without_camera_keep_current_output()
    test_unknown_field_warns_and_is_not_copied()
    test_unknown_term_and_chain_conflict()
    test_negated_and_focus_terms_do_not_borrow_moves()
    test_myslef_example_carries_the_shot_map()
    print("film grammar tests: PASS")


if __name__ == "__main__":
    main()
