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
