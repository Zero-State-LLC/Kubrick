"""0.27.14: lock negatives are compiled into prompts, the way 0.27.6 wrote positives."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kubrick.plan.lock_positive_lines import (  # noqa: E402
    lock_negative_lines,
    lock_positive_lines,
)
from kubrick.prompts.reference_lint import prompt_lines  # noqa: E402
from kubrick.prompts.storyboard_prompts import shots_from_document  # noqa: E402


def test_negative_lines_follow_the_cast() -> None:
    plan: Any = {
        "locks": [
            {"character": "hero", "negative": "no badge on the right lapel"},
            {"character": "villain", "negative": "no cape"},
        ]
    }
    frame: Any = {"cast": ["hero"]}
    assert lock_negative_lines(plan, frame) == ["no badge on the right lapel"]
    frame = {"cast": []}
    assert lock_negative_lines(plan, frame) == []
    frame = {"characters": ["villain"]}
    assert lock_negative_lines(plan, frame) == ["no cape"]
    frame = {}
    assert lock_negative_lines(plan, frame) == [
        "no badge on the right lapel",
        "no cape",
    ]
    frame = {"cast": ["hero"], "characters": ["villain"]}
    assert lock_negative_lines(plan, frame) == ["no badge on the right lapel"]


def test_negative_lines_skip_blank_and_dedupe() -> None:
    plan: Any = {
        "locks": [
            {"negative": ""},
            {"negative": "   "},
            {"negative": "No  overhead light"},
            {"negative": " no overhead LIGHT "},
            {"negative": "no smoke"},
            {"positive": "no negative here"},
        ]
    }
    assert lock_negative_lines(plan, {}) == ["No overhead light", "no smoke"]


def test_pov_skips_appearance_negatives_only() -> None:
    plan: Any = {
        "locks": [
            {"character": "hero", "kind": "wardrobe", "negative": "no hood up"},
            {
                "character": "hero",
                "kind": "light",
                "aspect": "appearance",
                "negative": "no glow on the collar",
            },
            {"character": "hero", "kind": "prop", "negative": "no second cup"},
        ]
    }
    frame: Any = {"characters": ["hero"], "view": "pov"}
    assert lock_negative_lines(plan, frame) == ["no second cup"]
    frame = {"characters": ["hero"]}
    assert lock_negative_lines(plan, frame) == [
        "no hood up",
        "no glow on the collar",
        "no second cup",
    ]


def test_compiled_prompt_carries_negatives_after_positives() -> None:
    plan: Any = {
        "storyboard_id": "lamp-test",
        "locks": [
            {
                "id": "hero-badge",
                "kind": "prop",
                "critical": True,
                "character": "hero",
                "positive": "a small brass badge on the left lapel",
                "negative": "no badge on the right lapel",
            },
            {
                "id": "lamp",
                "kind": "light",
                "positive": "one warm desk lamp lights the room",
                "negative": "no overhead light",
            },
        ],
        "frames": [
            {
                "frame_id": "f1",
                "cast": ["hero"],
                "action": "hero reads",
                "node_states": {"room": "lit"},
            },
            {
                "frame_id": "f2",
                "cast": [],
                "action": "the room waits",
                "node_states": {"room": "lit"},
            },
        ],
    }
    shots = shots_from_document(plan)
    assert isinstance(shots, list)
    prompts: dict[str, str] = {}
    for shot in shots:
        assert isinstance(shot, dict)
        shot_id = shot.get("shot_id")
        prompt = shot.get("prompt")
        assert isinstance(shot_id, str)
        assert isinstance(prompt, str)
        prompts[shot_id] = prompt

    f1 = prompts["f1"]
    badge_pos = "a small brass badge on the left lapel"
    badge_neg = "no badge on the right lapel"
    lamp_pos = "one warm desk lamp lights the room"
    lamp_neg = "no overhead light"

    assert badge_neg in f1
    assert lamp_neg in f1
    assert f1.index(badge_neg) > f1.index(badge_pos)
    assert f1.index(lamp_neg) > f1.index(lamp_pos)
    assert f1.index(badge_neg) > f1.index(lamp_pos)
    assert f1.index(lamp_neg) > f1.index(lamp_pos)
    assert f1.count(badge_neg) == 1
    assert f1.count(lamp_neg) == 1

    f2 = prompts["f2"]
    assert badge_neg not in f2
    assert badge_pos not in f2
    assert lamp_neg in f2
    assert f2.count(lamp_neg) == 1
    assert f2.count(badge_neg) == 0


def test_scoped_lock_lines_follow_scope_and_views() -> None:
    document = {
        "characters": {"myslef": {}},
        "locks": [
            {
                "id": "back-led",
                "character": "myslef",
                "positive": "a matte black back panel",
                "negative": "no light on head, hood, back or spine",
                "views": ["rear"],
                "scope": {"locations": ["basement"], "shots": ["07"]},
            }
        ],
    }
    base = {
        "frame_id": "frame-007",
        "shot_id": "07",
        "view": "rear",
        "location": "basement",
        "characters": ["myslef"],
    }
    pos = lock_positive_lines(document, base)
    neg = lock_negative_lines(document, base)
    text = " ".join(prompt_lines(document, base, []))
    assert pos == ["a matte black back panel"]
    assert neg == ["no light on head, hood, back or spine"]
    assert "a matte black back panel" in text
    assert "no light on head, hood, back or spine" in text

    variants = [
        {**base, "view": "front"},
        {**base, "shot_id": "08", "frame_id": "frame-008"},
        {**base, "location": "kitchen"},
        {**base, "view": "pov"},
    ]
    for frame in variants:
        assert lock_positive_lines(document, frame) == []
        assert lock_negative_lines(document, frame) == []
        joined = " ".join(prompt_lines(document, frame, []))
        assert "a matte black back panel" not in joined
        assert "no light on head, hood, back or spine" not in joined
