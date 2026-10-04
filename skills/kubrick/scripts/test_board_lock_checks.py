#!/usr/bin/env python3
"""Atomic lock questions and per-check severity for the board image gate.

A scripted fake judge answers by question text. No model is loaded and no paid API is called.
"""
from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "evals" / "fixtures" / "board_images"
sys.path.insert(0, str(SCRIPTS))

import board_image_gate as gate  # noqa: E402
import board_pixels as pixels  # noqa: E402
import board_vision as vision  # noqa: E402
from io_safety import load_structured  # noqa: E402

from kubrick.gates import board_lock_checks as checks  # noqa: E402

PREFIX = "Answer only yes or no. Look at the character myslef in this image. "
ALLEY_LOCKS = [
    {"id": "red-chest-led", "character": "myslef",
     "positive": "the only light on the body is ONE small red LED pinpoint at the chest",
     "negative": "no light on the head, hood or temple, no light along the spine or on the back"},
    {"id": "lenses", "character": "myslef",
     "positive": "dark cracked lens on the figure's right (viewer's left)",
     "negative": "the lenses never glow, no human eyes, no long lens barrels"},
    {"id": "speaker-mouth", "character": "myslef",
     "positive": "a round steel mesh speaker grille", "negative": "no lip movement, no words"},
]


class FixedEmbedder:
    name = "fake-fixed"

    def embed(self, image: pixels.RGBImage) -> list[float]:
        return [1.0, 0.0]


class ScriptedJudge:
    """Answers from a table keyed by the question tail; anything else is ``default``."""

    name = "scripted-judge"

    def __init__(self, table: Mapping[str, str], default: str = "unknown") -> None:
        self.table = table
        self.default = default
        self.questions: list[str] = []

    def ask(self, image: pixels.RGBImage, image_sha256: str, question: str) -> str:
        self.questions.append(question)
        for tail, answer in self.table.items():
            if question.endswith(tail):
                return answer
        return self.default


class DownJudge:
    name = "down"

    def ask(self, image: pixels.RGBImage, image_sha256: str, question: str) -> str:
        raise vision.BackendUnavailable("proxy answered HTTP 502")


CLEAN = {
    "Does the character show any light on the head, hood or temple?": "no",
    "Does the character show any light along the spine or on the back?": "no",
    "Do the lenses glow?": "no",
    "Does the character show any human eyes?": "no",
    "Does the character show any long lens barrels?": "no",
    "Does the character show any lip movement?": "no",
    "Does the character show any words?": "no",
}
SIDES = {"id": "lens-sides", "question": (
    PREFIX + "Is the darker cracked lens on the left side of the image and the yellowed lens "
    "on the right side?"), "expect": "yes"}


def _plan(**extra: object) -> dict[str, Any]:
    raw = load_structured(str(FIXTURES / "plan.yaml"))
    assert isinstance(raw, dict)
    character = raw["characters"]["myslef"]
    character.pop("character_locks")
    character["ref_pack"]["views"] = character["ref_pack"]["views"][:1]
    raw["locks"] = [dict(row) for row in ALLEY_LOCKS]
    raw["frames"] = raw["frames"][:1]
    character.update(extra)
    return raw


def _check(document: Mapping[str, object], judge: object) -> dict[str, Any]:
    return gate.check_board_images(document, base_dir=FIXTURES, embedder=FixedEmbedder(),
                                   judge=judge)


def _lock_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = report["checks"]
    assert isinstance(rows, list)
    return [row for row in rows if row["check"] == "lock_detail"]


def test_each_compound_lock_becomes_direct_questions_with_expected_answers() -> None:
    plan = _plan()
    questions = gate.lock_questions(plan, "myslef", plan["characters"]["myslef"])
    asked = {item["question"].removeprefix(PREFIX): item["expect"] for item in questions}
    assert asked == CLEAN
    assert all("Is this statement true" not in item["question"] for item in questions)
    assert [item["lock_id"] for item in questions] == [
        "red-chest-led", "red-chest-led", "lenses", "lenses", "lenses",
        "speaker-mouth", "speaker-mouth",
    ]
    assert {item["severity"] for item in questions} == {"block"}


@pytest.mark.parametrize(("clause", "question", "expect"), [
    ("no nose", "Does the character show any nose?", "no"),
    ("not human skin", "Does the character show any human skin?", "no"),
    ("the grille never moves like lips", "Does the grille move like lips?", "no"),
    ("the hood never touches the head", "Does the hood touch the head?", "no"),
    ("the drone never flies", "Does the drone fly?", "no"),
    ("the character never has a nose", "Does the character have a nose?", "no"),
    ("the hood is never up", "Is the hood up?", "no"),
    ("the lenses are never lit", "Are the lenses lit?", "no"),
    ("silicon hands with no nails", "Does the character show silicon hands with no nails?", "yes"),
    ("the hood is down", "Is it true in this image that the hood is down?", "yes"),
])
def test_clause_wording(clause: str, question: str, expect: str) -> None:
    assert checks.clause_question(clause) == (question, expect)


def test_clause_split_keeps_lists_inside_one_clause() -> None:
    assert checks.split_clauses("no light on the head, hood or temple; no hat and no logo.") == [
        "no light on the head, hood or temple", "no hat", "no logo",
    ]
    assert checks.split_clauses("smooth dome head, grey and matte") == [
        "smooth dome head, grey and matte",
    ]


def test_clean_board_passes_every_atomic_question() -> None:
    judge = ScriptedJudge(CLEAN)
    report = _check(_plan(), judge)
    assert report["code"] == "BOARD_IMAGES_CLEAR"
    assert len(judge.questions) == 7
    assert {row["status"] for row in report["locks"]} == {"PASS"}
    assert [row["questions"] for row in report["locks"]] == [2, 3, 2]


def test_one_confirmed_fail_blocks_and_names_the_lock() -> None:
    judge = ScriptedJudge({**CLEAN, "Do the lenses glow?": "yes"})
    report = _check(_plan(), judge)
    assert report["blocks_spend"] is True
    assert report["code"] == "BOARD_LOCK_DETAIL_FAIL"
    verdicts = {row["lock_id"]: row["status"] for row in report["locks"]}
    assert verdicts == {"red-chest-led": "PASS", "lenses": "FAIL", "speaker-mouth": "PASS"}
    assert "lock 'lenses' answered yes" in str(report["message"])


def test_unverified_part_still_fails_closed() -> None:
    table = dict(CLEAN)
    del table["Does the character show any words?"]
    report = _check(_plan(), ScriptedJudge(table))
    assert report["code"] == "BOARD_LOCK_DETAIL_UNVERIFIED"
    assert {row["lock_id"]: row["status"] for row in report["locks"]}["speaker-mouth"] == (
        "UNVERIFIED")
    down = _check(_plan(), DownJudge())
    assert down["blocks_spend"] is True
    assert {row["status"] for row in _lock_rows(down)} == {"UNVERIFIED"}


def test_fail_outranks_unverified_in_one_lock() -> None:
    table = {**CLEAN, "Does the character show any light on the head, hood or temple?": "yes"}
    del table["Does the character show any light along the spine or on the back?"]
    report = _check(_plan(), ScriptedJudge(table))
    assert report["code"] == "BOARD_LOCK_DETAIL_FAIL"
    assert report["locks"][0]["status"] == "FAIL"


def test_lens_sides_is_warn_only_and_never_blocks() -> None:
    plan = _plan(board_checks=[SIDES])
    question = gate.lock_questions(plan, "myslef", plan["characters"]["myslef"])[-1]
    assert question["severity"] == "warn"
    wrong = _check(plan, ScriptedJudge({**CLEAN, "on the right side?": "no"}))
    assert wrong["code"] == "BOARD_IMAGES_CLEAR"
    assert wrong["blocks_spend"] is False
    row = _lock_rows(wrong)[-1]
    assert (row["status"], row["verdict"], row["code"]) == (
        "WARN", "FAIL", "BOARD_LOCK_DETAIL_WARN")
    warning = wrong["warnings"][-1]
    assert warning["code"] == "BOARD_LOCK_DETAIL_WARN"
    assert "warn only" in warning["message"]
    unknown = _check(plan, ScriptedJudge(CLEAN))
    assert unknown["blocks_spend"] is False
    assert _lock_rows(unknown)[-1]["verdict"] == "UNVERIFIED"
    assert unknown["locks"][-1]["status"] == "WARN"


def test_explicit_severity_and_lock_checks() -> None:
    forced = dict(SIDES, severity="block")
    plan = _plan(board_checks=[forced])
    plan["locks"][2]["checks"] = [
        {"question": PREFIX + "Is the speaker grille moving like lips?", "expect": "no"},
        {"question": PREFIX + "Is any text visible?", "expect": "no", "severity": "warn"},
    ]
    plan["locks"][0]["severity"] = "warn"
    questions = gate.lock_questions(plan, "myslef", plan["characters"]["myslef"])
    by_lock = [(item["lock_id"], item["severity"]) for item in questions]
    assert by_lock == [
        ("red-chest-led", "warn"), ("red-chest-led", "warn"),
        ("lenses", "block"), ("lenses", "block"), ("lenses", "block"),
        ("speaker-mouth", "block"), ("speaker-mouth", "warn"),
        ("lens-sides", "block"),
    ]
    report = _check(plan, ScriptedJudge({**CLEAN, "Is any text visible?": "no",
                                         "speaker grille moving like lips?": "no",
                                         "on the right side?": "no"}))
    assert report["code"] == "BOARD_LOCK_DETAIL_FAIL"
    assert {row["lock_id"]: row["status"] for row in report["locks"]}["lens-sides"] == "FAIL"


def test_lock_checks_inherit_the_lock_severity() -> None:
    plan = _plan()
    plan["locks"][2]["severity"] = "warn"
    plan["locks"][2]["checks"] = [
        {"question": PREFIX + "Is the speaker grille moving like lips?", "expect": "no"},
        {"question": PREFIX + "Is any text visible?", "expect": "no", "severity": "block"},
    ]
    questions = gate.lock_questions(plan, "myslef", plan["characters"]["myslef"])
    assert [item["severity"] for item in questions[-2:]] == ["warn", "block"]
    report = _check(plan, ScriptedJudge({**CLEAN, "Is any text visible?": "no",
                                         "speaker grille moving like lips?": "yes"}))
    assert report["blocks_spend"] is False
    assert report["locks"][-1]["status"] == "WARN"


@pytest.mark.parametrize("bad", [
    {"severity": "blok"},
    {"checks": [{"question": PREFIX + "Is any text visible?", "severity": "loud"}]},
    {"checks": [{"question": PREFIX + "Is any text visible?", "expect": "maybe"}]},
    {"checks": [{"question": "", "expect": "no"}]},
    {"checks": ["not a mapping"]},
])
def test_invalid_lock_config_fails_closed(bad: dict[str, object]) -> None:
    plan = _plan()
    plan["locks"][2].update(bad)
    report = _check(plan, ScriptedJudge({**CLEAN, "Is any text visible?": "no"}))
    assert report["blocks_spend"] is True
    assert report["code"] == "BOARD_GATE_CONFIG_INVALID"
    config = [row for row in report["checks"] if row["check"] == "lock_config"]
    assert config and all(row["lock_id"] == "speaker-mouth" for row in config)
    assert {row["lock_id"]: row["status"] for row in report["locks"]}["speaker-mouth"] == "FAIL"


def test_duplicate_questions_keep_the_stricter_severity_and_reject_conflicts() -> None:
    same = PREFIX + "Do the lenses glow?"
    plan = _plan(board_checks=[{"question": same, "expect": "no", "severity": "block"}])
    plan["locks"][1]["severity"] = "warn"
    questions = gate.lock_questions(plan, "myslef", plan["characters"]["myslef"])
    glow = [item for item in questions if item["question"] == same]
    assert [(item["lock_id"], item["severity"]) for item in glow] == [("lenses", "block")]
    plan["characters"]["myslef"]["board_checks"] = [{"question": same, "expect": "yes"}]
    conflict = _check(plan, ScriptedJudge(CLEAN))
    assert conflict["code"] == "BOARD_GATE_CONFIG_INVALID"
    assert "expects no for lock 'lenses' and yes" in str(conflict["message"])


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))


def test_yaml_bare_no_is_expect_no() -> None:
    """YAML reads a bare ``expect: no`` as False; it must mean no, not the default yes."""
    rows = [{"question": "Q one?", "expect": False}, {"question": "Q two?", "expect": True},
            {"question": "Q three?"}]
    found = checks.explicit_checks("lenses", rows)
    assert [c["expect"] for c in found] == ["no", "yes", "yes"]
