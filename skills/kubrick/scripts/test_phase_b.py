#!/usr/bin/env python3
"""Drift registry, model capabilities, spend, and multi-shot text. Issues #39–#42."""
from __future__ import annotations

import copy
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from adapt_provider import adapt  # noqa: E402
from drift_registry import join_mitigations, load_registry, registry_warnings  # noqa: E402
from lock_carriers import _recommendation  # noqa: E402
from provider_capabilities import (  # noqa: E402
    capability_warnings,
    load_model_capabilities,
    model_blocks,
    pricing_for,
    provider_capabilities,
)
from shot_plan import collect_prep, generation_seconds, shot_directives  # noqa: E402
from spend_plan import CHECKLIST, budget_error, spend_estimate  # noqa: E402
from storyboard_prompts import adapter_packet_from_document  # noqa: E402
from test_corpus_hygiene import fixture_capabilities as _fixture_capabilities  # noqa: E402

PY = sys.executable
EXAMPLE = ROOT / "examples/myslef-minder/storyboard-plan.yaml"
AS_OF = date(2026, 10, 2)
WARDROBE = "plain solid black pullover hoodie, no logo, no print; charcoal sweatpants"
RECOMMEND = (
    "use a start frame that already shows the plain top in the moving pose, "
    "retouch after generation, or accept the drift"
)
KEYFRAME = {
    "image": True,
    "video": True,
    "min_duration_seconds": 3.0,
    "max_duration_seconds": 60.0,
    "camera_motion": True,
    "dialogue_audio": True,
    "multi_shot": True,
    "physics_hints": True,
    "identity_lock": True,
    "is_multi_shot_single_clip": True,
    "short_beat_threshold_seconds": 2.0,
    "start_frame_hold_seconds": 1.6,
    "exclusive_inputs": [["startImage", "referenceImages"]],
    "exclusivity_notes": {
        "startImage|referenceImages": (
            "Seedance 2.5: startImage and referenceImages are mutually exclusive; "
            "references dropped on shot {shot}"
        ),
    },
    "negative_prompt_effective": False,
}


def _load(path: Path) -> dict[str, object]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _codes(items: list[dict[str, str | None]], code: str) -> list[dict[str, str | None]]:
    return [item for item in items if item.get("code") == code]


def _frame(frame_id: str, **fields: object) -> dict[str, object]:
    frame: dict[str, object] = {"frame_id": frame_id}
    frame.update(fields)
    return frame


def _ids(items: list[dict[str, str | None]]) -> list[str]:
    return [str(item.get("message") or "") for item in items]


def test_registry_validates_and_invalid_fails() -> None:
    loaded = load_registry()
    entries = loaded["entries"]
    assert isinstance(entries, list)
    assert [item["id"] for item in entries] == [
        "plain-top-motion-logo",
        "no-ref-head-red-light",
        "char-ref-bleed-two-person",
        "location-ref-overrides-prompt",
        "start-frame-hold",
        "multi-shot-merges-short-beats",
        "framing-wider-than-asked",
        "brightness-over-directed",
        "weak-action-intensity",
        "chained-start-suppresses-move",
        "flicker-clears-all-figures",
    ]
    plain = entries[0]
    assert isinstance(plain, dict)
    assert join_mitigations(plain["mitigations"], plain["failed_mitigations"]) == RECOMMEND
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "bad.yaml"
        path.write_text("version: '1'\nentries:\n  - id: only\n", encoding="utf-8")
        try:
            load_registry(path)
        except ValueError as exc:
            assert "schema" in str(exc)
        else:
            raise AssertionError("invalid registry must fail closed")


def test_plain_top_motion_unchanged() -> None:
    document = {"characters": {"minder": {"wardrobe": WARDROBE}}}
    moving = [_frame("frame-002", characters=["minder"], action="the minder springs up")]
    static = [_frame("frame-001", characters=["minder"], action="the minder sits typing")]
    assert registry_warnings(document, static, "keyframe", as_of=AS_OF) == []
    found = _codes(registry_warnings(document, moving, "keyframe", as_of=AS_OF), "KNOWN_DRIFT")
    assert len(found) == 1
    assert found[0]["shot"] == "frame-002"
    assert "minder on frame-002 matches plain top + motion" in str(found[0]["message"])
    assert "invented chest logo/graphic" in str(found[0]["message"])
    assert found[0]["recommendation"] == RECOMMEND
    assert registry_warnings(document, moving, "generic", as_of=AS_OF) == []


def test_each_new_drift_entry() -> None:
    red = {
        "characters": {
            "myslef": {"references": [{"path": "head-lock-short-flush.png", "role": "character"}]},
        },
        "locks": [{
            "character": "myslef",
            "negative": "no red light on the head or chest",
        }],
    }
    hit = [_frame("frame-002", characters=["myslef"], reference_images=["ref://chair"])]
    miss = [_frame(
        "frame-001", characters=["myslef"], reference_images=["head-lock-short-flush.png"],
    )]
    assert "no-ref-head-red-light" in " ".join(_ids(_codes(
        registry_warnings(red, hit, "keyframe", as_of=AS_OF), "KNOWN_DRIFT",
    )))
    assert registry_warnings(red, miss, "keyframe", as_of=AS_OF) == []
    people = {
        "characters": {
            "myslef": {"references": [{"path": "head.png", "role": "character"}]},
            "minder": {"wardrobe": "grey coat"},
        },
    }
    both = [_frame("frame-001", characters=["minder", "myslef"], reference_images=["head.png"])]
    one = [_frame("frame-003", characters=["myslef"], reference_images=["head.png"])]
    bare = [_frame("frame-001", characters=["minder", "myslef"], reference_images=["ref://chair"])]
    assert "char-ref-bleed-two-person" in " ".join(_ids(_codes(
        registry_warnings(people, both, "keyframe", as_of=AS_OF), "KNOWN_DRIFT",
    )))
    assert "char-ref-bleed-two-person" not in " ".join(_ids(
        registry_warnings(people, one, "keyframe", as_of=AS_OF),
    ))
    assert "char-ref-bleed-two-person" not in " ".join(_ids(
        registry_warnings(people, bare, "keyframe", as_of=AS_OF),
    ))
    room = {"location": {"references": [{"path": "location-ref-v1"}]}}
    empty = {"location": {"locks": ["no lit doorway"]}}
    first = [_frame("frame-001", characters=["myslef"])]
    assert "location-ref-overrides-prompt" in " ".join(_ids(_codes(
        registry_warnings(room, first, "keyframe", as_of=AS_OF), "KNOWN_DRIFT",
    )))
    assert "location-ref-overrides-prompt" not in " ".join(_ids(
        registry_warnings(empty, first, "keyframe", as_of=AS_OF),
    ))
    chained = [_frame("frame-002", join={"chain_from": "frame-001"})]
    cut = [_frame("frame-001", join="cut")]
    assert "start-frame-hold" in " ".join(_ids(_codes(
        registry_warnings({}, chained, "keyframe", as_of=AS_OF), "KNOWN_DRIFT",
    )))
    assert "start-frame-hold" not in " ".join(_ids(
        registry_warnings({}, cut, "keyframe", as_of=AS_OF),
    ))
    short = [
        _frame("frame-001", duration_seconds=1.0),
        _frame("frame-002", duration_seconds=1.0),
    ]
    long = [
        _frame("frame-001", duration_seconds=4.0),
        _frame("frame-002", duration_seconds=4.0),
    ]
    assert "multi-shot-merges-short-beats" in " ".join(_ids(_codes(
        registry_warnings({}, short, "keyframe", as_of=AS_OF), "KNOWN_DRIFT",
    )))
    assert "multi-shot-merges-short-beats" not in " ".join(_ids(
        registry_warnings({}, long, "keyframe", as_of=AS_OF),
    ))
    assert "multi-shot-merges-short-beats" not in " ".join(_ids(
        registry_warnings({}, short, "generic", as_of=AS_OF),
    ))


def test_stale_drift_uses_injected_date() -> None:
    moving = [_frame("frame-002", characters=["minder"], action="springs")]
    document = {"characters": {"minder": {"wardrobe": WARDROBE}}}
    fresh = registry_warnings(document, moving, "keyframe", as_of=AS_OF + timedelta(days=180))
    stale = registry_warnings(document, moving, "keyframe", as_of=AS_OF + timedelta(days=181))
    assert _codes(fresh, "DRIFT_ENTRY_STALE") == []
    assert _codes(stale, "DRIFT_ENTRY_STALE")
    assert "plain-top-motion-logo" in str(_codes(stale, "DRIFT_ENTRY_STALE")[0]["message"])
    held = registry_warnings(
        {**document, "drift_max_age_days": 10000},
        moving,
        "keyframe",
        as_of=AS_OF + timedelta(days=181),
    )
    assert _codes(held, "DRIFT_ENTRY_STALE") == []


def test_keyframe_capabilities_regression_and_overlay() -> None:
    assert provider_capabilities("keyframe") == KEYFRAME
    blocks = model_blocks("keyframe", "seedance-2.5")
    assert blocks[0]["source"] == "vendor_claim"
    assert blocks[0]["start_frame_hold_seconds"] == 0.4
    assert blocks[1]["source"] == "observed"
    with _fixture_capabilities():
        lab = provider_capabilities("keyframe", "seedance-lab")
        assert lab["start_frame_hold_seconds"] == 0.5
        assert lab["negative_prompt_effective"] is False
        assert "max_references" not in lab
        assert "native_audio" not in lab
        generated, hold = generation_seconds(
            2.0, chained=True, exit_open=False, provider="keyframe",
            document={"model": "seedance-lab"},
        )
        assert (generated, hold) == (3.0, 0.5)
        directives = shot_directives(
            [_frame("frame-002", duration_seconds=2.0, join={"chain_from": "frame-001"})],
            "keyframe",
            [],
            document={"model": "seedance-lab"},
        )
        assert directives[0]["source_in"] == 0.5
        assert directives[0]["hold_seconds"] == 0.5
        assert "is false" not in _recommendation("keyframe", {"model": "seedance-effective"})
    held = provider_capabilities("keyframe", input_mode="lab-hold")
    assert held["start_frame_hold_seconds"] == 0.25
    assert "is false" in _recommendation("keyframe")


def _raises(action: Callable[[], object], *needles: str) -> None:
    try:
        action()
    except ValueError as exc:
        text = str(exc)
        assert all(needle in text for needle in needles), text
        return
    raise AssertionError("expected ValueError")


def _drift_yaml(ident: str, observed: str) -> str:
    return (
        "version: '1'\nentries:\n"
        f"  - id: {ident}\n"
        "    model: seedance-2.5\n"
        "    trigger:\n"
        "      kind: chained_start\n"
        "    effect: late start\n"
        "    mitigations:\n"
        "      - trim the hold\n"
        "    failed_mitigations: []\n"
        "    evidence: fixture\n"
        f"    observed_on: '{observed}'\n"
    )


def _caps_yaml(day: str) -> str:
    return (
        "version: '1'\nproviders:\n  keyframe:\n    models:\n      seedance-lab:\n"
        "        blocks:\n          - source: observed\n"
        f"            verified_on: '{day}'\n"
        "            start_frame_hold_seconds: 0.5\n"
    )


def test_impossible_calendar_dates_fail_closed() -> None:
    for day in ("2026-99-99", "2026-02-30"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            caps = root / "models.yaml"
            caps.write_text(_caps_yaml(day), encoding="utf-8")
            _raises(lambda: load_model_capabilities(caps), "seedance-lab", day, "calendar date")
            drift = root / "drift.yaml"
            drift.write_text(_drift_yaml("bad-date", day), encoding="utf-8")
            _raises(lambda: load_registry(drift), "bad-date", day, "calendar date")
    with tempfile.TemporaryDirectory() as directory:
        leap = Path(directory) / "leap.yaml"
        leap.write_text(_caps_yaml("2024-02-29"), encoding="utf-8")
        loaded = load_model_capabilities(leap)
        assert loaded["version"] == "1"


def test_registry_warnings_uses_drift_path_only() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "drift.yaml"
        path.write_text(_drift_yaml("alt-hold", "2026-10-02"), encoding="utf-8")
        found = registry_warnings(
            {},
            [_frame("frame-002", join={"chain_from": "frame-001"})],
            "keyframe",
            as_of=AS_OF,
            path=path,
        )
    text = " ".join(_ids(_codes(found, "KNOWN_DRIFT")))
    assert "alt-hold" in text
    assert "start-frame-hold" not in text


def test_capability_staleness_and_schema() -> None:
    fresh = capability_warnings("keyframe", as_of=AS_OF)
    with _fixture_capabilities():
        stale = capability_warnings("keyframe", {"model": "seedance-stale"}, as_of=AS_OF)
        assert stale and stale[0]["code"] == "CAPABILITY_STALE"
        assert "seedance-stale" in str(stale[0]["message"])
        kept = capability_warnings(
            "keyframe",
            {"model": "seedance-stale", "capability_max_age_days": 10000},
            as_of=AS_OF,
        )
        assert kept == []
    assert fresh == []
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "models.yaml"
        path.write_text(
            "version: '1'\nproviders:\n  keyframe:\n    models:\n      seedance-2.5:\n"
            "        blocks:\n          - verified_on: '2026-10-02'\n",
            encoding="utf-8",
        )
        try:
            load_model_capabilities(path)
        except ValueError as exc:
            assert "schema" in str(exc)
        else:
            raise AssertionError("missing source must fail schema validation")


def _movie() -> tuple[dict[str, object], dict[str, object]]:
    source = _load(EXAMPLE)
    packet = adapter_packet_from_document(source)
    movie = adapt(copy.deepcopy(packet), "keyframe")
    return packet, movie


def test_spend_estimate_budget_and_checklist() -> None:
    _packet, movie = _movie()
    estimate = movie["spend_estimate"]
    assert isinstance(estimate, dict)
    assert estimate["label"] == "INFERRED"
    assert estimate["status"] == "INFERRED"
    shots = estimate["shots"]
    assert isinstance(shots, list) and len(shots) == 4
    assert [item["generated_seconds"] for item in shots] == [3, 3, 3, 3]
    assert [item["credits"] for item in shots] == [46.5, 46.5, 46.5, 46.5]
    assert estimate["total_credits"] == 186
    assert estimate["rate"] == 15.5
    pricing = pricing_for("keyframe")
    assert pricing is not None and pricing["image_rate"] == 7
    assert movie["execution_checklist"] == list(CHECKLIST)


def test_budget_boundary_shared_clips_and_missing_price() -> None:
    _packet, movie = _movie()
    estimate = movie["spend_estimate"]
    assert isinstance(estimate, dict)
    assert budget_error(estimate, 186) is None
    assert str(budget_error(estimate, 185)).startswith("BUDGET_CAP_EXCEEDED")
    shared = [
        {"shot": "a", "generated_seconds": 3, "clip_id": "clip-1"},
        {"shot": "b", "generated_seconds": 3, "clip_id": "clip-1"},
        {"shot": "c", "generated_seconds": 3},
    ]
    folded = spend_estimate("keyframe", shared)
    assert folded["total_credits"] == 93
    generic = adapt(adapter_packet_from_document(_load(EXAMPLE)), "generic")
    missing = generic["spend_estimate"]
    assert isinstance(missing, dict)
    assert missing["status"] == "NOT_COMPUTABLE"
    assert missing["total_credits"] is None
    assert missing["shots"] == []
    assert generic["execution_checklist"] == list(CHECKLIST)
    assert "multi_shot_prompt" not in generic
    text = (ROOT / "scripts/spend_plan.py").read_text(encoding="utf-8")
    for banned in ("urllib", "requests", "httpx", "http.client"):
        assert banned not in text


def test_budget_cap_exit_codes() -> None:
    source = _load(EXAMPLE)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        low = root / "low.yaml"
        high = root / "high.yaml"
        below = dict(source)
        above = dict(source)
        below["budget_cap_credits"] = 1
        above["budget_cap_credits"] = 10000
        low.write_text(yaml.safe_dump(below, sort_keys=False), encoding="utf-8")
        high.write_text(yaml.safe_dump(above, sort_keys=False), encoding="utf-8")
        command = [
            PY, str(ROOT / "scripts/kubrick.py"), "video", "--action", "adapt",
            "--provider", "keyframe",
        ]
        low_out = root / "low-out.yaml"
        high_out = root / "high-out.yaml"
        failed = subprocess.run(
            [*command, "--input", str(low), "--output", str(low_out)],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        passed = subprocess.run(
            [*command, "--input", str(high), "--output", str(high_out)],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        failed_text = low_out.read_text(encoding="utf-8")
        passed_text = high_out.read_text(encoding="utf-8")
    assert failed.returncode != 0
    assert "BUDGET_CAP_EXCEEDED" in failed_text
    assert passed.returncode == 0, passed.stdout + passed.stderr
    assert "total_credits: 186" in passed_text


def _continuity_body(text: str) -> str:
    return text.split("Continuity:\n", 1)[1].split("\nEnding state:", 1)[0]


def test_multi_shot_prompt_and_preservation() -> None:
    packet, movie = _movie()
    text = str(movie["multi_shot_prompt"])
    assert text.startswith("4 shots, 12s generated, aspect 9:16, lighting:")
    assert "dim practical light" in text
    for index in range(1, 5):
        assert f"Shot {index} (3s):" in text
    assert text.count("Continuity:") == 1
    body = _continuity_body(text)
    lines = [line for line in body.splitlines() if line.strip()]
    assert lines and len(lines) == len(set(lines))
    wardrobe = (
        "WARDROBE LOCK: minder wears plain solid black pullover hoodie, "
        "no logo, no print; charcoal sweatpants"
    )
    assert lines.count(wardrobe) == 1
    assert body.count("never swap sides") == 1
    assert "smooth featureless skin where a nose would be" in body
    assert "Ending state: the minder walks out of frame right" in text
    _assert_prompts_survive(packet, movie)


def _assert_prompts_survive(packet: dict[str, object], movie: dict[str, object]) -> None:
    prompts = packet["frames"]
    shots = movie["shots"]
    assert isinstance(prompts, list) and isinstance(shots, list)
    for frame, shot in zip(prompts, shots):
        assert isinstance(frame, dict) and isinstance(shot, dict)
        assert str(frame["prompt"]) in str(shot["imagePrompt"])


def test_generic_preservation_and_shot_count() -> None:
    packet, _movie_payload = _movie()
    generic = adapt(copy.deepcopy(packet), "generic")
    report = generic["preservation_report"]
    assert isinstance(report, dict)
    assert report["critical_invariants_preserved"] is True
    assert "multi_shot_prompt" not in generic
    six = [_frame(f"frame-{index:03d}", duration_seconds=4) for index in range(1, 7)]
    assert _codes(collect_prep({}, six, "keyframe").warnings, "SHOT_COUNT_HIGH")
    assert _codes(collect_prep({}, six[:5], "keyframe").warnings, "SHOT_COUNT_HIGH") == []


def main() -> None:
    test_registry_validates_and_invalid_fails()
    test_plain_top_motion_unchanged()
    test_each_new_drift_entry()
    test_stale_drift_uses_injected_date()
    test_keyframe_capabilities_regression_and_overlay()
    test_impossible_calendar_dates_fail_closed()
    test_registry_warnings_uses_drift_path_only()
    test_capability_staleness_and_schema()
    test_spend_estimate_budget_and_checklist()
    test_budget_boundary_shared_clips_and_missing_price()
    test_budget_cap_exit_codes()
    test_multi_shot_prompt_and_preservation()
    test_generic_preservation_and_shot_count()
    print("phase B registry and spend tests: PASS")


if __name__ == "__main__":
    main()
