#!/usr/bin/env python3
"""Frame action reaches compiled prompts, and deterministic lint runs before Jev."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from jev_gate import gate_prompts  # noqa: E402
from prompt_lint import (  # noqa: E402
    emit_board_prompt,
    lint_text,
    missing_board_locks,
    review_prompt,
)
from storyboard_prompts import shots_from_document  # noqa: E402

EXAMPLE = ROOT / "examples/myslef-minder/storyboard-plan.yaml"
ACTIONS = ROOT / "evals/fixtures/myslef/ep01-actions.yaml"
_PLACEHOLDER_SUBJECT = "evidenced subject"
_PLACEHOLDER_VERB = "changes"


def _load(path: Path) -> dict[str, object]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _shots(document: dict[str, object]) -> list[dict[str, object]]:
    shots = shots_from_document(document)
    narrowed: list[dict[str, object]] = []
    for shot in shots:
        assert isinstance(shot, dict)
        narrowed.append(shot)
    return narrowed


def _action(shot: dict[str, object]) -> dict[str, object]:
    raw = shot.get("action")
    assert isinstance(raw, dict)
    return raw


def _prompt(shot: dict[str, object]) -> str:
    text = shot.get("prompt")
    assert isinstance(text, str)
    return text


def _codes(findings: list[dict[str, str]]) -> set[str]:
    return {item["code"] for item in findings}


def test_twelve_myslef_actions_reach_compiled_prompts() -> None:
    shots = _shots(_load(ACTIONS))
    assert len(shots) == 12
    for shot in shots:
        sentence = str(_action(shot).get("path_or_change") or "")
        assert sentence
        assert sentence in _prompt(shot)
        assert _action(shot).get("subject") != _PLACEHOLDER_SUBJECT
        assert _action(shot).get("verb") != _PLACEHOLDER_VERB
    example = _shots(_load(EXAMPLE))
    authored = [str(_action(shot).get("path_or_change") or "") for shot in example]
    assert authored[:4] == [
        "the minder sits typing at the bench",
        "the minder springs up and the chair skids",
        "myslef stays seated at the rack",
        "the minder walks out of frame right",
    ]
    for shot, sentence in zip(example, authored, strict=True):
        assert sentence in _prompt(shot)


def test_contradictions_block_before_jev() -> None:
    class _Boom:
        def judge(self, prompt: object, holds: object) -> dict[str, object]:
            raise AssertionError("Jev was called")

    neon = gate_prompts(
        {"frames": [{"frame_id": "f01"}], "hold_list": []},
        [{"shot": "f01", "prompt": "a neon sign glows and no neon", "labels": ["f01"]}],
        client=_Boom(),
    )
    assert neon.get("code") == "POSITIVE_NEGATIVE_CONFLICT"
    assert neon.get("blocks_spend") is True
    head = gate_prompts(
        {
            "frames": [{"frame_id": "f02"}],
            "hold_list": [{"id": "head-size", "text": "head-size ratio, not oversized"}],
        },
        [{"shot": "f02", "prompt": "a big bulbous head fills the frame", "labels": ["f02"]}],
        client=_Boom(),
    )
    assert head.get("code") == "HOLD_CONTRADICTION"
    assert head.get("blocks_spend") is True


def test_brand_weak_negation_and_meta_word() -> None:
    rewritten, findings = review_prompt(
        "black-and-red high-tops and sweatpants with no tears",
    )
    assert "black-and-red high-tops" not in rewritten
    assert "unbranded canvas high-tops" in rewritten
    assert "smooth intact fabric at the knees" in rewritten
    assert "no tears" not in rewritten
    assert {"BRAND_TERM", "WEAK_NEGATION"} <= _codes(findings)
    meta, meta_findings = review_prompt("the on-screen text reads gibberish and no real words")
    assert "META_WORD" in _codes(meta_findings)
    assert "gibberish" in meta
    frame: dict[str, object] = {
        "frame_id": "f01",
        "action": "she wears black-and-red high-tops",
        "node_states": {"observed_1": "present"},
    }
    document: dict[str, object] = {
        "brand_safe_aliases": {"black-and-red high-tops": "plain canvas shoes"},
        "frames": [frame],
        "node_labels": {"observed_1": "figure"},
    }
    prompt = _prompt(_shots(document)[0])
    assert "plain canvas shoes" in prompt
    assert "black-and-red high-tops" not in prompt


def test_missing_board_lock_blocks_before_jev() -> None:
    class _Boom:
        def judge(self, prompt: object, holds: object) -> dict[str, object]:
            raise AssertionError("Jev was called")

    class _Pass:
        def __init__(self) -> None:
            self.called = False

        def judge(self, prompt: object, holds: object) -> dict[str, object]:
            self.called = True
            return {"verdict": "pass", "findings": []}

    document: dict[str, object] = {
        "frames": [{"frame_id": "f01", "location": "alley"}],
        "hold_list": [{
            "id": "hands",
            "text": "silicon hands",
            "scope": {"locations": ["alley"], "shots": ["f01"]},
        }],
    }
    bare = [{
        "shot": "f01",
        "prompt": "hands press the grille",
        "location": "alley",
        "labels": ["f01"],
    }]
    blocked = gate_prompts(document, bare, client=_Boom())
    assert blocked.get("code") == "LOCK_MISSING_IN_BOARD"
    assert blocked.get("blocks_spend") is True
    assert blocked.get("authority") == "NOT_COMPUTABLE"
    direct = lint_text("hands press the grille", locks=["silicon hands"])
    assert "LOCK_MISSING_IN_BOARD" in _codes(direct)
    assert direct[0]["suggestion"] == emit_board_prompt("hands press the grille", ["silicon hands"])
    stated = [{
        "shot": "f01",
        "prompt": "silicon hands press the grille",
        "location": "alley",
        "labels": ["f01"],
    }]
    client = _Pass()
    cleared = gate_prompts(document, stated, client=client)
    assert cleared.get("code") == "CLEAR"
    assert cleared.get("blocks_spend") is False
    assert client.called is True


def test_board_lock_and_infeasible_motion() -> None:
    locks = ["silicon hands"]
    bare = "hands press the grille"
    missing = missing_board_locks(bare, locks)
    assert [item["code"] for item in missing] == ["LOCK_MISSING_IN_BOARD"]
    emitted = emit_board_prompt(bare, locks)
    assert "silicon hands" in emitted
    assert missing_board_locks(emitted, locks) == []
    frame = {
        "frame_id": "f09",
        "action": "debris hops across the lower alley",
        "provider_parameters": {"resolution": "480p"},
    }
    debris = lint_text("debris hops across the lower alley", frame=frame)
    assert "SMALL_FG_MOTION_LOW_RES" in _codes(debris)
    suggestion = " ".join(item["suggestion"] for item in debris)
    assert "insert" in suggestion
    assert "720p" in suggestion
    assert "sound" in suggestion
    fast = lint_text("the lamp blinks", duration=0.4)
    assert "SUBSECOND_TIMING_IGNORED" in _codes(fast)
    held = lint_text(
        "the minder springs up",
        frame={"frame_id": "f02", "join": {"chain_from": "f01"}},
    )
    assert "START_HOLD_1_6S" in _codes(held)
    clear = lint_text("debris hops across the lower alley", resolution="720p")
    assert "SMALL_FG_MOTION_LOW_RES" not in _codes(clear)


def main() -> None:
    test_twelve_myslef_actions_reach_compiled_prompts()
    test_contradictions_block_before_jev()
    test_brand_weak_negation_and_meta_word()
    test_missing_board_lock_blocks_before_jev()
    test_board_lock_and_infeasible_motion()
    print("prompt lint tests: PASS")


if __name__ == "__main__":
    main()
