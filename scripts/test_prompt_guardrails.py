"""Tests for the deterministic prompt guardrails."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from kubrick.prompts.prompt_guardrails import (  # noqa: E402
    GUARDRAIL_BLOCKING,
    GUARDRAIL_CODES,
    guardrail_findings,
)


def _codes(text: str, frame=None) -> set[str]:
    """Return the set of guardrail codes found for a prompt."""
    return {finding["code"] for finding in guardrail_findings(text, frame)}


def test_end_card_space_positive_leave_clear() -> None:
    """Reserving clear room for a title is flagged."""
    assert "END_CARD_SPACE" in _codes("leave the lower third clear for the title")


def test_end_card_space_positive_empty_area_for_logo() -> None:
    """Reserving an empty area for a logo is flagged."""
    assert "END_CARD_SPACE" in _codes("empty space on the wall for the logo")


def test_end_card_space_negative_clean_wall() -> None:
    """A plain described wall is not an end card reservation."""
    assert guardrail_findings("A clean pale wall fills the upper half") == []


def test_prop_lettering_positive_mug() -> None:
    """A named mug without an unbranded lock is flagged."""
    assert "PROP_LETTERING_UNLOCKED" in _codes("a mug sits on the table")


def test_prop_lettering_positive_tablet() -> None:
    """A named tablet without an unbranded lock is flagged."""
    assert "PROP_LETTERING_UNLOCKED" in _codes("two tablets rest on the desk")


def test_prop_lettering_negative_unbranded() -> None:
    """An unbranded lock phrase clears the prop check."""
    assert "PROP_LETTERING_UNLOCKED" not in _codes("an unbranded plain mug on a wall shelf")


def test_ui_outside_screen_positive_banner() -> None:
    """A banner on a phone screen without containment is flagged."""
    assert "UI_OUTSIDE_SCREEN" in _codes("a phone screen shows a notification banner")


def test_ui_outside_screen_positive_popup() -> None:
    """A popup on a tablet display without containment is flagged."""
    assert "UI_OUTSIDE_SCREEN" in _codes("the tablet display shows a popup dialog")


def test_ui_outside_screen_negative_contained() -> None:
    """A containment phrase clears the UI check."""
    text = "a notification banner stays inside the screen of the phone"
    assert "UI_OUTSIDE_SCREEN" not in _codes(text)


def test_action_not_completed_positive_cast() -> None:
    """A cast with an action lacking a completion verb is flagged."""
    frame = {"characters": ["host"], "action": "the host waits in the doorway"}
    assert "ACTION_NOT_COMPLETED" in _codes("a person waits in the doorway", frame)


def test_action_not_completed_positive_empty_action() -> None:
    """A cast with an empty action is flagged."""
    frame = {"characters": ["hands"], "action": ""}
    assert "ACTION_NOT_COMPLETED" in _codes("hands in front of a wall", frame)


def test_action_not_completed_negative_completed() -> None:
    """A completed action verb clears the action check."""
    frame = {"characters": ["hands"], "action": "the hands set the box on the stack"}
    text = "one pair of hands sets an unbranded plain box on a stack"
    assert "ACTION_NOT_COMPLETED" not in _codes(text, frame)


def test_handwritten_text_positive_joined_token() -> None:
    """A hyphen joined token after the base form write is flagged."""
    assert "HANDWRITTEN_TEXT_IN_PROMPT" in _codes("hands write abc-def-ghi on tape")


def test_handwritten_text_positive_quoted() -> None:
    """A quoted string after a sign cue is flagged."""
    assert "HANDWRITTEN_TEXT_IN_PROMPT" in _codes('the sign says "OPEN" in the window')


def test_handwritten_text_negative_generic_note() -> None:
    """Writing without specific text is not flagged."""
    assert "HANDWRITTEN_TEXT_IN_PROMPT" not in _codes("hands write notes on a pad")


def test_clean_prompt_has_no_findings() -> None:
    """A locked, completed, text free shot yields no findings."""
    text = (
        "One pair of hands sets an unbranded plain cardboard box with no lettering "
        "on a stack in front of a pale wall."
    )
    frame = {"characters": ["hands"], "action": "the hands set the box on the stack"}
    assert guardrail_findings(text, frame) == []


def test_blocking_codes() -> None:
    """Only end card space and UI containment block a prompt."""
    assert GUARDRAIL_BLOCKING == {"END_CARD_SPACE", "UI_OUTSIDE_SCREEN"}
    assert set(GUARDRAIL_CODES) >= GUARDRAIL_BLOCKING
