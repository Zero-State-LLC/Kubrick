#!/usr/bin/env python3
"""Matchers for issue #79 drift entries and technique triggers."""
from __future__ import annotations

import copy
import json
import sys
from datetime import date
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from adapt_provider import adapt  # noqa: E402
from build_model_adapter_packet import build as build_packet  # noqa: E402
from build_motif_graph import build as build_graph  # noqa: E402
from drift_registry import load_registry, registry_warnings  # noqa: E402
from planning_fields import document_from_packet  # noqa: E402
from propagate_graph_state import propagate  # noqa: E402
from shot_plan import collect_prep, load_techniques, match_techniques  # noqa: E402
from storyboard_prompts import adapter_packet_from_document  # noqa: E402

AS_OF = date(2026, 10, 2)
EXAMPLE = ROOT / "examples/myslef-minder/storyboard-plan.yaml"
DRIFT_IDS = (
    "framing-wider-than-asked",
    "brightness-over-directed",
    "weak-action-intensity",
    "chained-start-suppresses-move",
    "flicker-clears-all-figures",
)
TECH_IDS = (
    "scoped-flicker",
    "cut-on-sound-peak",
    "new-angle-after-cut",
    "offscreen-event",
)


def _frame(frame_id: str, **fields: object) -> dict[str, object]:
    frame: dict[str, object] = {"frame_id": frame_id}
    frame.update(fields)
    return frame


def _load(path: Path) -> dict[str, object]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _drift(
    document: dict[str, object], frames: list[dict[str, object]], provider: str = "keyframe",
) -> list[dict[str, str | None]]:
    return registry_warnings(document, frames, provider, as_of=AS_OF)


def _text(items: list[dict[str, str | None]]) -> str:
    return " ".join(str(item.get("message") or "") for item in items)


def _by_shot(
    frames: list[dict[str, object]], document: dict[str, object] | None = None,
) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for item in match_techniques(frames, "keyframe", document):
        found.setdefault(str(item["shot"]), []).append(str(item["id"]))
    return found


def test_catalog_evidence_and_schema() -> None:
    entries = load_registry()["entries"]
    assert isinstance(entries, list)
    by_id = {str(item["id"]): item for item in entries if isinstance(item, dict)}
    for ident in DRIFT_IDS:
        entry = by_id[ident]
        assert entry["model"] == "seedance-2.5"
        assert entry["observed_on"] == "2026-10-02"
        assert "MYSLEF EP-01" in str(entry["evidence"])
        assert "2026-10-02" in str(entry["evidence"])
    library = load_techniques()["techniques"]
    assert isinstance(library, list)
    ids = [str(item["id"]) for item in library if isinstance(item, dict)]
    assert ids[-4:] == list(TECH_IDS)
    for item in library:
        assert isinstance(item, dict)
        if str(item["id"]) in TECH_IDS:
            assert "MYSLEF EP-01" in str(item["evidence"])
            assert "2026-10-02" in str(item["evidence"])
    drift_schema = json.loads(
        (ROOT / "schemas/drift-registry.schema.json").read_text(encoding="utf-8")
    )
    kinds = drift_schema["properties"]["entries"]["items"]["properties"]["trigger"]["properties"]
    kind_enum = kinds["kind"]["enum"]
    for kind in (
        "close_framing", "dim_practical", "startle_action", "chained_snap", "flicker_keep",
    ):
        assert kind in kind_enum
    tech_schema = json.loads((ROOT / "schemas/techniques.schema.json").read_text(encoding="utf-8"))
    triggers = tech_schema["properties"]["techniques"]["items"]["properties"]["triggers"]
    for key in ("flicker_clear", "keep_list", "sound_peak", "min_angle_degrees", "offscreen_event"):
        assert key in triggers["properties"]


def test_close_framing_and_brightness() -> None:
    ecu = [_frame("s", action="ECU on the speaker grille")]
    sized = [_frame("s", camera={"size": "close-up"})]
    nested = [_frame("s", provider_parameters={"camera": {"size": "ECU"}})]
    closed = [_frame("s", action="the optic stays closed")]
    absent = [_frame("s", action="a wider view", camera="missing")]
    assert "framing-wider-than-asked" in _text(_drift({}, ecu))
    assert "framing-wider-than-asked" in _text(_drift({}, sized))
    assert "framing-wider-than-asked" in _text(_drift({}, nested))
    assert "framing-wider-than-asked" not in _text(_drift({}, closed))
    assert "framing-wider-than-asked" not in _text(_drift({}, absent))
    dim = [_frame("s", light_states={"room": "dim practical light"})]
    practical = [_frame("s", light_states={"room": "one practical"})]
    bright = [_frame("s", light_states={"room": "noon sun"})]
    assert "brightness-over-directed" in _text(_drift({}, dim))
    # The drift is dim *practicals* rendering bright: one cue alone does not match.
    assert "brightness-over-directed" not in _text(_drift({}, practical))
    dim_only = [_frame("s", light_states={"room": "dim moonlight"})]
    assert "brightness-over-directed" not in _text(_drift({}, dim_only))
    assert "brightness-over-directed" not in _text(_drift({}, bright))
    assert "brightness-over-directed" not in _text(_drift({}, [_frame("s")]))


def test_startle_and_chained_snap() -> None:
    startle = [_frame("s", action="he startles")]
    jump = [_frame("s", action="the minder jumps")]
    springs = [_frame("s", action="the minder springs up")]
    prompt_only = [_frame("s", action="sits", prompt="jumps")]
    assert "weak-action-intensity" in _text(_drift({}, startle))
    assert "weak-action-intensity" in _text(_drift({}, jump))
    assert "weak-action-intensity" not in _text(_drift({}, springs))
    assert "weak-action-intensity" not in _text(_drift({}, prompt_only))
    snap = [
        _frame("a"),
        _frame("b", join={"chain_from": "a"}, action="snap pan to the door"),
    ]
    whip = [
        _frame("a"),
        _frame("b", join={"chain_from": "a"}, camera={"move": "whip-pan"}),
    ]
    loose = [_frame("a", action="snap pan")]
    twig = [_frame("a"), _frame("b", join={"chain_from": "a"}, action="a twig snaps underfoot")]
    whip_prose = [
        _frame("a"), _frame("b", join={"chain_from": "a"}, action="the camera whips left"),
    ]
    held = [_frame("a"), _frame("b", join={"chain_from": "a"}, action="springs", camera=None)]
    assert "chained-start-suppresses-move" in _text(_drift({}, snap))
    assert "chained-start-suppresses-move" in _text(_drift({}, whip))
    assert "chained-start-suppresses-move" not in _text(_drift({}, loose))
    assert "chained-start-suppresses-move" not in _text(_drift({}, twig))
    assert "chained-start-suppresses-move" in _text(_drift({}, whip_prose))
    assert "chained-start-suppresses-move" not in _text(_drift({}, held))


def test_flicker_keep_drift_and_warning() -> None:
    frames = [
        _frame("a", characters=["minder", "myslef"]),
        _frame("b", characters=[], join={"chain_from": "a"}, action="lights flicker"),
    ]
    found = _drift({"keep": ["myslef"]}, frames)
    kept = [item for item in found if "flicker-clears-all-figures" in str(item.get("message"))]
    assert kept and kept[0]["character"] == "myslef"
    assert kept[0]["shot"] == "b"
    assert "MYSLEF EP-01" in str(kept[0]["evidence"])
    assert kept[0]["observed_on"] == "2026-10-02"
    frame_keep = [
        _frame("a", characters=["minder", "myslef"]),
        _frame(
            "b", characters=["minder"], join={"chain_from": "a"},
            keep=["myslef"], action="the lights flicker",
        ),
    ]
    assert "flicker-clears-all-figures" in _text(_drift({}, frame_keep))
    # A cast reduction with no flicker evidence is an ordinary edit, not a flicker.
    cut_only = [
        _frame("a", characters=["minder", "myslef"]),
        _frame("b", characters=["minder"], join={"chain_from": "a"}, keep=["myslef"]),
    ]
    assert "flicker-clears-all-figures" not in _text(_drift({}, cut_only))
    assert "scoped-flicker" not in _by_shot(cut_only, {"keep": ["myslef"]}).get("b", [])
    stays = [
        _frame("a", characters=["minder", "myslef"]),
        _frame("b", characters=["myslef"], join={"chain_from": "a"}, action="flicker"),
    ]
    assert "flicker-clears-all-figures" not in _text(_drift({"keep": ["myslef"]}, stays))
    assert "flicker-clears-all-figures" not in _text(_drift({}, frames))
    unknown = [_frame("b", action="lights flicker", keep=["myslef"])]
    assert "flicker-clears-all-figures" not in _text(_drift({}, unknown))
    prep = collect_prep({"keep": ["myslef"]}, frames, "keyframe")
    assert any(item.get("code") == "FLICKER_CLEARS_KEEP" for item in prep.warnings)
    generic = collect_prep({"keep": ["myslef"]}, frames, "generic")
    assert any(item.get("code") == "FLICKER_CLEARS_KEEP" for item in generic.warnings)
    assert "flicker-clears-all-figures" not in _text(generic.warnings)
    suggested = _by_shot(frames, {"keep": ["myslef"]})
    assert "scoped-flicker" in suggested["b"]
    assert "clear-characters-by-flicker" in suggested["b"]
    assert "scoped-flicker" not in _by_shot(frames).get("b", [])


def test_keep_is_carried_by_compiled_artifacts() -> None:
    example = ROOT / "examples" / "myslef-minder"
    graph = build_graph(_load(example / "brief.yaml"))
    plan = _load(example / "storyboard-plan.yaml")
    plan["keep"] = ["myslef"]
    frames = plan["frames"]
    assert isinstance(frames, list)
    exit_frame = frames[3]
    assert isinstance(exit_frame, dict) and exit_frame["frame_id"] == "frame-004"
    exit_frame["keep"] = ["myslef"]
    exit_frame["action"] = "the lights flicker as the minder walks out of frame right"
    board = propagate(graph, plan)
    assert board["validation"]["status"] == "VALID", board["validation"]
    assert board["keep"] == ["myslef"]
    assert board["frames"][3]["keep"] == ["myslef"]
    board_schema = yaml.safe_load(
        (ROOT / "schemas" / "storyboard-symbolic-state.schema.yaml").read_text(encoding="utf-8")
    )
    jsonschema.validate(board, board_schema)
    packet = build_packet(graph, board, "keyframe")
    packet_schema = yaml.safe_load(
        (ROOT / "schemas" / "model-adapter-packet.schema.yaml").read_text(encoding="utf-8")
    )
    jsonschema.validate(packet, packet_schema)
    assert packet["keep"] == ["myslef"]
    assert document_from_packet(packet)["keep"] == ["myslef"]
    assert any(
        item.get("code") == "FLICKER_CLEARS_KEEP" and item.get("shot") == "frame-004"
        for item in packet["prep_warnings"]
    )
    suggested = {(item["shot"], item["id"]) for item in packet["technique_suggestions"]}
    assert ("frame-004", "scoped-flicker") in suggested


def test_sound_peak_angle_and_offscreen() -> None:
    peak = [_frame("a"), _frame("b", join="cut", action="cut on the bass peak")]
    sync = [
        _frame("a"),
        _frame("b", join="cut", provider_parameters={"cut": {"on": "sound_peak"}}),
    ]
    quiet = [_frame("a"), _frame("b", join="cut", action="the room holds")]
    assert "cut-on-sound-peak" in _by_shot(peak)["b"]
    assert "cut-on-sound-peak" in _by_shot(sync)["b"]
    assert "cut-on-sound-peak" not in _by_shot(quiet).get("b", [])
    angle = [_frame("a"), _frame("b", join="cut", camera={"angle": 30})]
    prose = [_frame("a"), _frame("b", join="cut", action="a new angle, 45 degrees right")]
    low = [_frame("a"), _frame("b", join="cut", camera={"angle": 29})]
    opening = [_frame("a", join="cut", camera={"angle": 80})]
    chained = [_frame("a"), _frame("b", join={"chain_from": "a"}, camera={"angle": 40})]
    soft = [_frame("a"), _frame("b", join="cut", action="slightly right and closer")]
    assert "new-angle-after-cut" in _by_shot(angle)["b"]
    assert "new-angle-after-cut" in _by_shot(prose)["b"]
    assert "new-angle-after-cut" not in _by_shot(low).get("b", [])
    assert "new-angle-after-cut" not in _by_shot(opening).get("a", [])
    assert "new-angle-after-cut" not in _by_shot(chained).get("b", [])
    assert "new-angle-after-cut" not in _by_shot(soft).get("b", [])
    heard = [_frame("s", action="the chair tip is heard, not shown")]
    sounding = [_frame("s", action="the speaker is sounding offscreen")]
    bare = [_frame("s", action="the chair is offscreen")]
    only_heard = [_frame("s", action="a door is heard")]
    assert "offscreen-event" in _by_shot(heard)["s"]
    assert "offscreen-event" in _by_shot(sounding)["s"]
    assert "offscreen-event" not in _by_shot(bare).get("s", [])
    assert "offscreen-event" not in _by_shot(only_heard).get("s", [])


def test_myslef_regression_shows_applicable_warnings() -> None:
    source = _load(EXAMPLE)
    frames = source["frames"]
    assert isinstance(frames, list)
    direct = _drift(source, [item for item in frames if isinstance(item, dict)])
    bright = [item for item in direct if "brightness-over-directed" in str(item.get("message"))]
    assert [item.get("shot") for item in bright] == [
        "frame-001", "frame-002", "frame-003", "frame-004",
    ]
    assert "MYSLEF EP-01" in str(bright[0]["evidence"])
    assert bright[0]["observed_on"] == "2026-10-02"
    packet = adapter_packet_from_document(source)
    movie = adapt(copy.deepcopy(packet), "keyframe")
    raw = movie["prep_warnings"]
    assert isinstance(raw, list)
    warnings = [item for item in raw if isinstance(item, dict)]
    known = [item for item in warnings if item.get("code") == "KNOWN_DRIFT"]
    drift_text = _text(known)
    assert known[0]["shot"] == "frame-002"
    for shot in ("frame-001", "frame-002", "frame-003", "frame-004"):
        assert f"{shot} matches brightness-over-directed" in drift_text
    close = {"ecu", "cu", "extreme close-up", "close-up", "extreme close", "close"}
    close_shots = [
        str(item.get("frame_id"))
        for item in frames
        if isinstance(item, dict)
        and isinstance(item.get("camera"), dict)
        and str(item["camera"].get("size", "")).strip().lower() in close
    ]
    # A plan that states a close camera size (the #77 camera carrier) must trip
    # framing-wider-than-asked on those shots; a plan without one must not.
    if close_shots:
        for shot in close_shots:
            assert f"{shot} matches framing-wider-than-asked" in drift_text
    else:
        assert "framing-wider-than-asked" not in drift_text
    for absent in (
        "weak-action-intensity",
        "chained-start-suppresses-move",
        "flicker-clears-all-figures",
    ):
        assert absent not in drift_text
    assert not any(item.get("code") == "FLICKER_CLEARS_KEEP" for item in warnings)
    suggestions: dict[str, list[str]] = {}
    raw_tech = movie["technique_suggestions"]
    assert isinstance(raw_tech, list)
    for item in raw_tech:
        assert isinstance(item, dict)
        suggestions.setdefault(str(item["shot"]), []).append(str(item["id"]))
    assert "physical-action-distance-path" in suggestions["frame-002"]
    assert "clear-characters-by-flicker" in suggestions["frame-004"]
    assert suggestions["frame-004"].count("offscreen-event") == 1
    skipped = {"scoped-flicker", "cut-on-sound-peak", "new-angle-after-cut"}
    seen = {tech for group in suggestions.values() for tech in group}
    assert skipped.isdisjoint(seen)


def main() -> None:
    test_catalog_evidence_and_schema()
    test_close_framing_and_brightness()
    test_startle_and_chained_snap()
    test_flicker_keep_drift_and_warning()
    test_keep_is_carried_by_compiled_artifacts()
    test_sound_peak_angle_and_offscreen()
    test_myslef_regression_shows_applicable_warnings()
    print("issue 79 drift and technique tests: PASS")


if __name__ == "__main__":
    main()
