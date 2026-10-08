#!/usr/bin/env python3
"""Critical lock lines and cast scope in the pre-spend phrase check.

Issue #107 and the #133 review. Recorded verdicts only; no live Jev call.
"""
from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from jev_client import RecordedJev, verdict_key  # noqa: E402
from jev_gate import check_before_spend  # noqa: E402


def _rows(value: object) -> list[dict[str, object]]:
    assert isinstance(value, list) and all(isinstance(item, dict) for item in value)
    return value


def _prompt(raw: Mapping[str, object]) -> dict[str, object]:
    row: dict[str, object] = {
        "shot": raw["shot"],
        "channel": "keyframe",
        "surfaces": ["image", "video"],
        "location": raw.get("location", "plan"),
        "prompt": raw["prompt"],
    }
    if "characters" in raw:
        row["characters"] = raw["characters"]
    return row


def _recorded(
    prompts: Sequence[Mapping[str, object]],
    holds: Sequence[Mapping[str, object]],
    verdicts: Sequence[Mapping[str, object]],
) -> RecordedJev:
    stored: dict[str, Mapping[str, object]] = {}
    for prompt, spec in zip(prompts, verdicts):
        stored[verdict_key(prompt, holds)] = {"verdict": spec["verdict"], "findings": []}
    return RecordedJev(stored)


def test_every_critical_lock_line_is_enforced_on_fixtures() -> None:
    """Issue #107: a lock with a positive and a negative line enforces both."""
    hold = {
        "id": "lit-badge",
        "kind": "light",
        "critical": True,
        "positive": "one small green badge light on the collar",
        "negative": "no light on the sleeves",
    }
    both = _prompt({"shot": "01", "prompt": "a figure; one small green badge light on the collar; "
                    "no light on the sleeves"})
    clear = check_before_spend(
        [hold], [both], client=_recorded([both], [hold], [{"verdict": "pass"}]),
    )
    assert clear["code"] == "CLEAR"
    for text, gone in (
        ("a figure; no light on the sleeves", "green badge light"),
        ("a figure; one small green badge light on the collar", "no light on the sleeves"),
    ):
        prompt = _prompt({"shot": "01", "prompt": text})
        gate = check_before_spend(
            [hold], [prompt], client=_recorded([prompt], [hold], [{"verdict": "pass"}]),
        )
        assert gate["blocks_spend"] is True
        assert gate["code"] == "JEV_HOLD"
        assert "MISSING_LOCK" in str(gate["message"]) and gone in str(gate["message"])


def test_character_lock_skips_shots_without_that_character() -> None:
    """#133 review: an empty-cast shot does not have to state a character's lock."""
    hold = {
        "id": "badge", "kind": "light", "critical": True, "character": "hero",
        "positive": "one green badge light on the collar",
    }
    empty = _prompt({"shot": "06", "characters": [], "prompt": "nobody is in frame"})
    other = _prompt({"shot": "07", "characters": ["guard"], "prompt": "a guard waits"})
    cast = _prompt({"shot": "08", "characters": ["Hero"], "prompt": "the hero waits"})
    prompts = [empty, other, cast]
    gate = check_before_spend(
        [hold], prompts,
        client=_recorded(prompts, [hold], [{"verdict": "pass"}] * 3),
    )
    assert gate["blocks_spend"] is True
    message = str(gate["message"])
    assert "MISSING_LOCK" in message
    shots = {str(row["shot"]) for row in _rows(gate["checks"]) if row["verdict"] == "fail"}
    assert shots == {"08"}


import copy  # noqa: E402

from io_safety import load_structured  # noqa: E402
from jev_holds import compiled_prompts, hold_list  # noqa: E402


def test_cast_only_empty_shot_skips_character_lock() -> None:
    plan = load_structured(ROOT / "examples" / "myslef-minder" / "storyboard-plan.yaml")
    assert isinstance(plan, dict)
    plan = copy.deepcopy(plan)
    frames = plan["frames"]
    assert isinstance(frames, list)
    frame = frames[3]
    assert isinstance(frame, dict)
    frame.pop("characters", None)
    frame["cast"] = []
    lock = plan["locks"][0]
    assert isinstance(lock, dict)
    positive = lock["positive"]
    assert isinstance(positive, str)
    rows = _rows(compiled_prompts(plan, "image"))
    row = rows[3]
    assert row.get("characters") == []
    prompt = row["prompt"]
    assert isinstance(prompt, str)
    assert positive not in prompt
    holds = _rows(hold_list(plan))
    client = _recorded([row], holds, [{"verdict": "pass"}])
    result = check_before_spend(holds, [row], client=client)
    assert isinstance(result, dict)
    assert result["code"] == "CLEAR"


def test_cast_wins_over_characters_in_gate_rows() -> None:
    plan = load_structured(ROOT / "examples" / "myslef-minder" / "storyboard-plan.yaml")
    assert isinstance(plan, dict)
    plan = copy.deepcopy(plan)
    frames = plan["frames"]
    assert isinstance(frames, list)
    frame2 = frames[2]
    assert isinstance(frame2, dict)
    frame2["cast"] = ["minder"]
    frame1 = frames[1]
    assert isinstance(frame1, dict)
    frame1.pop("characters", None)
    frame1.pop("cast", None)
    lock = plan["locks"][0]
    assert isinstance(lock, dict)
    positive = lock["positive"]
    assert isinstance(positive, str)
    rows = _rows(compiled_prompts(plan, "image"))
    row2 = rows[2]
    assert row2.get("characters") == ["minder"]
    prompt2 = row2["prompt"]
    assert isinstance(prompt2, str)
    assert positive not in prompt2
    row1 = rows[1]
    assert "characters" not in row1
