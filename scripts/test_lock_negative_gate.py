"""0.27.14: the example plan's critical negative lock line reaches the gate; lint keeps
real conflicts. Recorded verdicts only; no live Jev call."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from kubrick.gates.jev_client import RecordedJev, verdict_key  # noqa: E402
from kubrick.gates.jev_gate import gate_prompts  # noqa: E402
from kubrick.gates.jev_holds import compiled_prompts, hold_list  # noqa: E402
from kubrick.gates.lock_phrases import missing_lock_phrases  # noqa: E402
from kubrick.prompts.prompt_lint import lint_text  # noqa: E402

PLAN = ROOT / "examples" / "myslef-minder" / "storyboard-plan.yaml"


def test_example_plan_compiles_the_critical_negative() -> None:
    plan = yaml.safe_load(PLAN.read_text())
    lock = plan["locks"][0]
    assert lock["critical"] is True
    character = lock["character"]
    negative = lock["negative"]
    compiled = compiled_prompts(plan, "keyframe")
    assert isinstance(compiled, list)
    holds = hold_list(plan)
    assert isinstance(holds, list)
    targeted = [r for r in compiled if character in r.get("characters", [])]
    empty = [r for r in compiled if r.get("characters") == []]
    assert targeted
    assert empty
    for row in targeted:
        assert negative in row["prompt"]
    for row in empty:
        assert negative not in row["prompt"]
    assert missing_lock_phrases(compiled, holds) == []


def test_example_plan_clears_the_gate_with_recorded_passes() -> None:
    plan = yaml.safe_load(PLAN.read_text())
    compiled = compiled_prompts(plan, "keyframe")
    assert isinstance(compiled, list)
    holds = hold_list(plan)
    assert isinstance(holds, list)
    mapping = {
        verdict_key(row, holds): {"verdict": "pass", "findings": []}
        for row in compiled
    }
    client = RecordedJev(mapping)
    result = gate_prompts(plan, compiled, client=client)
    assert result["code"] == "CLEAR"


def test_declared_negative_is_not_a_conflict_but_others_are() -> None:
    neg = "no light on the head"
    text = "one small lamp gives the only light; no light on the head"
    assert "POSITIVE_NEGATIVE_CONFLICT" in {f["code"] for f in lint_text(text)}
    declared = {f["code"] for f in lint_text(text, declared=[neg])}
    assert "POSITIVE_NEGATIVE_CONFLICT" not in declared
    text2 = text + "; no lamp"
    others = {f["code"] for f in lint_text(text2, declared=[neg])}
    assert "POSITIVE_NEGATIVE_CONFLICT" in others
    spaced = "only light; No  light on THE head"
    matched = {f["code"] for f in lint_text(spaced, declared=[neg])}
    assert "POSITIVE_NEGATIVE_CONFLICT" not in matched


def test_explicit_empty_hold_list_still_masks_plan_lock_negatives() -> None:
    plan = copy.deepcopy(yaml.safe_load(PLAN.read_text()))
    plan["hold_list"] = []
    compiled = compiled_prompts(plan, "keyframe")
    assert isinstance(compiled, list)
    holds = hold_list(plan)
    assert isinstance(holds, list)
    mapping = {
        verdict_key(row, holds): {"verdict": "pass", "findings": []}
        for row in compiled
    }
    client = RecordedJev(mapping)
    result = gate_prompts(plan, compiled, client=client)
    assert result["code"] != "POSITIVE_NEGATIVE_CONFLICT"
