#!/usr/bin/env python3
"""Scoped holds, rear wording, and per-hold verdicts. Issue #99. Recorded Jev only."""
from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from continuity_locks import prop_assignments  # noqa: E402
from hold_scope import holds_for_prompt  # noqa: E402
from jev_client import RecordedJev, judge_prompt, parse_verdict, verdict_key  # noqa: E402
from jev_gate import check_before_spend, gate_prompts  # noqa: E402
from reference_lint import prompt_lines  # noqa: E402

CHAIR = {
    "C0": "upright, occupied, at the bench",
    "C1": "shoved back from the bench",
}
REAR = "seen from behind there is NO visible light on the figure's right lens"
FOLDED = "no light on head, hood, back or spine"


def _rows(value: object) -> list[dict[str, object]]:
    assert isinstance(value, list)
    return [item for item in value if isinstance(item, dict)]


def _prompt(shot: str, location: str, *, view: str = "") -> dict[str, object]:
    row: dict[str, object] = {
        "shot": shot,
        "channel": "keyframe",
        "surfaces": ["image", "video"],
        "location": location,
        "prompt": f"{shot} at {location}",
    }
    if view:
        row["view"] = view
    return row


def _client(
    prompts: Sequence[Mapping[str, object]],
    holds: Sequence[Mapping[str, object]],
    payload: Mapping[str, object],
) -> RecordedJev:
    verdicts: dict[str, Mapping[str, object]] = {}
    for prompt in prompts:
        applicable = holds_for_prompt(holds, prompt)
        verdicts[verdict_key(judge_prompt(prompt), applicable)] = payload
    return RecordedJev(verdicts)


def test_chair_lock_stops_at_a_location_change() -> None:
    document = {"props": {"chair": {"states": CHAIR}}}
    frames: list[dict[str, object]] = [
        {"frame_id": "basement", "location": "basement", "prop_states": {"chair": "C0"}},
        {"frame_id": "alley", "location": "alley"},
        {"frame_id": "rooftop", "location": "rooftop"},
    ]
    lines, errors = prop_assignments(document, frames)
    assert errors == []
    basement = " ".join(prompt_lines(document, frames[0], lines["basement"]))
    alley = " ".join(prompt_lines(document, frames[1], lines["alley"]))
    rooftop = " ".join(prompt_lines(document, frames[2], lines["rooftop"]))
    assert "CHAIR LOCK: upright, occupied, at the bench" in basement
    assert "CHAIR LOCK" not in alley
    assert "CHAIR LOCK" not in rooftop
    stayed: list[dict[str, object]] = [
        {"frame_id": "frame-001", "location": "basement", "prop_states": {"chair": "C0"}},
        {"frame_id": "frame-002", "location": "basement"},
    ]
    carried, carry_errors = prop_assignments(document, stayed)
    assert carry_errors == []
    assert "CHAIR LOCK" in carried["frame-002"][0]


def test_rear_wording_and_pov_omissions() -> None:
    document = {
        "characters": {
            "myslef": {
                "wardrobe": "grey coat",
                "asymmetry": [{"feature": "lens", "figure_side": "right"}],
            },
        },
        "locks": [{
            "id": "back-led",
            "negative": FOLDED,
            "views": ["rear"],
            "anchor": "figure's right lens",
            "rear": REAR,
            "scope": {"locations": ["basement"], "shots": ["07"]},
        }],
    }
    rear = {
        "frame_id": "frame-007",
        "shot_id": "07",
        "view": "rear",
        "location": "basement",
        "characters": ["myslef"],
    }
    text = " ".join(prompt_lines(document, rear, []))
    assert REAR in text
    assert text.strip() != FOLDED
    pov = {
        "frame_id": "frame-008",
        "shot_id": "08",
        "view": "pov",
        "location": "basement",
        "characters": ["myslef"],
    }
    pov_lines = prompt_lines(document, pov, [])
    assert not any(line.startswith("WARDROBE LOCK:") for line in pov_lines)
    assert not any("never swap sides" in line for line in pov_lines)
    assert REAR not in " ".join(pov_lines)
    front = dict(rear)
    front["view"] = "front"
    assert REAR not in " ".join(prompt_lines(document, front, []))


def test_blank_location_blocks_a_location_scoped_hold() -> None:
    class _Boom:
        def judge(self, prompt: object, holds: object) -> dict[str, object]:
            raise AssertionError("Jev was called")

    holds = [{
        "id": "chair",
        "kind": "prop",
        "text": "CHAIR LOCK",
        "scope": {"locations": ["basement"]},
    }]
    for location in ("", "   "):
        prompt = {"shot": "01", "location": location, "prompt": "CHAIR LOCK stays"}
        refused = holds_for_prompt(holds, prompt)
        assert isinstance(refused, str)
        assert refused.startswith("LOCATION_UNSPECIFIED")
        gate = check_before_spend(holds, [prompt], client=_Boom())
        assert gate["blocks_spend"] is True
        assert gate["code"] == "LOCATION_UNSPECIFIED"
        assert gate["authority"] == "NOT_COMPUTABLE"
        routed = gate_prompts(
            {"frames": [{"frame_id": "01"}], "hold_list": holds},
            [prompt],
            client=_Boom(),
        )
        assert routed["code"] == "LOCATION_UNSPECIFIED"
        assert routed["blocks_spend"] is True
    other = holds_for_prompt(holds, {"shot": "02", "location": "alley", "prompt": "alley"})
    assert other == []

    class _Pass:
        def judge(self, prompt: object, holds: object) -> dict[str, object]:
            return {"verdict": "pass", "findings": []}

    alley = {"shot": "02", "location": "alley", "prompt": "walks the alley", "labels": ["02"]}
    cleared = gate_prompts(
        {"frames": [{"frame_id": "02"}], "hold_list": holds},
        [alley],
        client=_Pass(),
    )
    assert cleared["code"] == "CLEAR"
    assert cleared["blocks_spend"] is False


def test_scope_filters_the_holds_sent_to_jev() -> None:
    holds = [
        {"id": "chair", "kind": "prop", "text": "CHAIR LOCK", "scope": {"locations": ["basement"]}},
        {
            "id": "alley-light",
            "kind": "light",
            "text": "dim alley",
            "scope": {"locations": ["alley"]},
        },
    ]
    alley = _prompt("02", "alley")
    basement = _prompt("01", "basement")
    payload = {"verdict": "pass", "findings": []}
    client = _client([alley, basement], holds, payload)
    result = check_before_spend(holds, [alley, basement], client=client)
    assert result["blocks_spend"] is False
    assert client.seen_hold_ids[0] == ["alley-light"]
    assert client.seen_hold_ids[1] == ["chair"]


def test_one_weak_hold_fails_and_the_others_pass() -> None:
    payload = {
        "holds": [
            {"hold_id": "chair", "present": True, "located": True, "strong": True},
            {"hold_id": "back-led", "present": True, "located": False, "strong": False},
        ],
    }
    parsed = parse_verdict(payload)
    assert parsed["verdict"] == "fail"
    results = _rows(parsed["hold_results"])
    by_id = {str(item["hold_id"]): item for item in results}
    assert by_id["chair"]["passed"] is True
    assert by_id["back-led"]["passed"] is False
    assert by_id["back-led"]["located"] is False
    holds = [
        {"id": "chair", "kind": "prop", "text": "chair"},
        {"id": "back-led", "kind": "light", "text": "led"},
    ]
    prompt = _prompt("07", "basement", view="rear")
    client = _client([prompt], holds, payload)
    gate = check_before_spend(holds, [prompt], client=client)
    assert gate["blocks_spend"] is True
    check = _rows(gate["checks"])[0]
    judged = {str(item["hold_id"]): item for item in _rows(check["hold_results"])}
    assert judged["chair"]["passed"] is True
    assert judged["back-led"]["passed"] is False


def test_marginal_probability_is_resampled_and_not_a_pass() -> None:
    holds = [{"id": "back-led", "kind": "light", "text": "led"}]
    prompt = _prompt("07", "basement", view="rear")
    weak = {
        "holds": [{
            "hold_id": "back-led",
            "present": True,
            "located": True,
            "strong": True,
            "p": 0.51,
        }],
    }
    decisive = {
        "holds": [
            {"hold_id": "chair", "present": True, "located": True, "strong": True, "p": 0.9},
            {"hold_id": "back-led", "present": True, "located": False, "strong": False, "p": 0.2},
        ],
    }
    marginal = {"samples": [weak, {**weak, "holds": [{**weak["holds"][0], "p": 0.4}]}, weak]}
    applicable = holds_for_prompt(holds, prompt)
    key = verdict_key(judge_prompt(prompt), applicable)
    stayed = RecordedJev({key: marginal}).judge(judge_prompt(prompt), applicable)
    assert stayed["verdict"] == "fail"
    assert _rows(stayed["findings"])[0]["code"] == "JEV_MARGIN"
    mixed = RecordedJev({key: {"samples": [weak, decisive]}}).judge(
        judge_prompt(prompt), applicable,
    )
    judged = {str(item["hold_id"]): item for item in _rows(mixed["hold_results"])}
    assert judged["chair"]["passed"] is True
    assert judged["back-led"]["passed"] is False
    assert mixed["verdict"] == "fail"


def main() -> None:
    test_chair_lock_stops_at_a_location_change()
    test_rear_wording_and_pov_omissions()
    test_blank_location_blocks_a_location_scoped_hold()
    test_scope_filters_the_holds_sent_to_jev()
    test_one_weak_hold_fails_and_the_others_pass()
    test_marginal_probability_is_resampled_and_not_a_pass()
    print("scoped hold tests: PASS")


if __name__ == "__main__":
    main()
