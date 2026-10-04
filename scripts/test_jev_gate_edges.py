#!/usr/bin/env python3
"""Jev pre-spend gate edge cases from the #90 review."""
from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from jev_client import JevUnreachable  # noqa: E402
from jev_gate import check_before_spend  # noqa: E402
from jev_holds import compiled_prompts, hold_list  # noqa: E402
from test_jev_gate import _Down, _locked_plan, _recorded, _run  # noqa: E402


def test_recorded_verdict_is_bound_to_holds_and_context() -> None:
    holds: list[dict[str, object]] = [
        {"id": "brand", "text": "no brand marks", "critical": True},
    ]
    prompt = {
        "shot": "01",
        "channel": "keyframe",
        "surfaces": ["image", "video"],
        "location": "alley",
        "prompt": "plain black high-tops, no logo",
    }
    client = _recorded([prompt], holds, [{"verdict": "pass", "findings": []}])
    clear = check_before_spend(holds, [prompt], client=client)
    assert clear["code"] == "CLEAR"
    added: list[dict[str, object]] = [
        *holds,
        {"id": "red-chest-light", "text": "no red light on the head or chest"},
    ]
    changed_holds = check_before_spend(added, [prompt], client=client)
    assert changed_holds["code"] == "JEV_UNREACHABLE"
    assert changed_holds["blocks_spend"] is True
    moved = dict(prompt)
    moved["shot"] = "02"
    moved["location"] = "street"
    changed_prompt = check_before_spend(holds, [moved], client=client)
    assert changed_prompt["code"] == "JEV_UNREACHABLE"
    other_channel = dict(prompt)
    other_channel["channel"] = "elevenlabs"
    other_channel["surfaces"] = ["audio"]
    changed_channel = check_before_spend(holds, [other_channel], client=client)
    assert changed_channel["code"] == "JEV_UNREACHABLE"


def test_malformed_explicit_hold_list_fails_closed() -> None:
    prompt = {
        "shot": "01",
        "channel": "keyframe",
        "surfaces": ["image"],
        "location": "plan",
        "prompt": "a figure waits",
    }
    locks = [{"id": "red", "negative": "no red light on the head or chest"}]
    for bad in ("no red light", {"id": "x"}, 3, None):
        found = hold_list({"hold_list": bad, "locks": locks})
        assert isinstance(found, str) and found.startswith("HOLD_LIST_INVALID")
        gate = check_before_spend(found, [prompt], override=True, override_source="flag")
        assert gate["code"] == "HOLD_LIST_INVALID"
        assert gate["blocks_spend"] is True
        assert gate["override_logged"] is False
    assert hold_list({"hold_list": []}) == []
    plan = _locked_plan()
    plan["hold_list"] = "no red light"
    code, data, _err = _run("video_runbook.py", plan, "--jev-override")
    assert code == 4
    assert data["code"] == "HOLD_LIST_INVALID"
    assert "ops" not in data
    assert "spend_estimate" not in data


def test_local_block_matches_frame_and_shot_aliases() -> None:
    plan = {
        "frames": [{
            "frame_id": "f1",
            "shot_id": "01",
            "duration_seconds": 4,
        }],
        "hold_list": [{
            "id": "block-f1",
            "blocked": True,
            "shot": "f1",
            "text": "shot f1 is held",
        }],
    }
    compiled = compiled_prompts(plan, "keyframe")
    holds = hold_list(plan)
    assert isinstance(compiled, list)
    assert isinstance(holds, list)
    assert compiled[0]["shot"] == "01"
    labels = compiled[0]["labels"]
    assert isinstance(labels, list)
    assert "f1" in labels and "01" in labels
    gate = check_before_spend(
        holds, compiled, client=_Down(), override=True, override_source="flag",
    )
    assert gate["code"] == "JEV_HOLD"
    assert gate["blocks_spend"] is True
    assert gate["override_logged"] is False
    assert "f1" in str(gate["message"])
    assert "does not bypass" in str(gate["message"])


class _ThenDown:
    def __init__(self, first: Mapping[str, object]) -> None:
        self._first = first
        self._calls = 0

    def judge(
        self, prompt: Mapping[str, object], holds: Sequence[Mapping[str, object]],
    ) -> Mapping[str, object]:
        self._calls += 1
        if self._calls == 1:
            return self._first
        raise JevUnreachable("connection reset")


def test_later_transport_failure_is_unreachable() -> None:
    holds = [{"id": "red-chest-light", "text": "no red light", "critical": True}]
    prompts = [
        {
            "shot": "01",
            "channel": "keyframe",
            "surfaces": ["image", "video"],
            "location": "aisle",
            "prompt": "first figure",
        },
        {
            "shot": "02",
            "channel": "keyframe",
            "surfaces": ["image", "video"],
            "location": "aisle",
            "prompt": "second figure",
        },
    ]
    blocked = check_before_spend(
        holds, prompts, client=_ThenDown({"verdict": "pass", "findings": []}),
    )
    assert blocked["code"] == "JEV_UNREACHABLE"
    assert blocked["blocks_spend"] is True
    assert "connection reset" in str(blocked["message"])
    logged: list[dict[str, object]] = []
    allowed = check_before_spend(
        holds, prompts,
        client=_ThenDown({"verdict": "pass", "findings": []}),
        override=True,
        override_source="flag",
        log=lambda record: logged.append(dict(record)),
    )
    assert allowed["code"] == "JEV_OVERRIDE"
    assert allowed["override_logged"] is True
    assert logged and logged[0]["shots_judged"] == ["01"]
    held = check_before_spend(
        holds, prompts,
        client=_ThenDown({
            "verdict": "fail",
            "findings": [{
                "code": "MISSING_LOCK",
                "hold_id": "red-chest-light",
                "message": "red chest LED lock is missing",
            }],
        }),
        override=True,
        override_source="flag",
    )
    assert held["code"] == "JEV_HOLD"
    assert held["blocks_spend"] is True
    assert held["override_logged"] is False
    assert "does not bypass" in str(held["message"])


def main() -> None:
    test_recorded_verdict_is_bound_to_holds_and_context()
    test_malformed_explicit_hold_list_fails_closed()
    test_local_block_matches_frame_and_shot_aliases()
    test_later_transport_failure_is_unreachable()
    print("jev pre-spend gate edge tests: PASS")


if __name__ == "__main__":
    main()
