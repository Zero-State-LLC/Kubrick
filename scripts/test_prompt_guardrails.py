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


def _regression_codes(text: str, frame: dict | None = None) -> set[str]:
    return {f["code"] for f in guardrail_findings(text, frame)}


def test_regression_end_card_space_absent_for_open_area() -> None:
    """Space described as usable area is not treated as reserved."""
    assert "END_CARD_SPACE" not in _regression_codes("an open area for the dancer to cross")


def test_regression_end_card_space_absent_for_empty_room() -> None:
    """Empty room phrasing is not treated as reserved space."""
    assert "END_CARD_SPACE" not in _regression_codes("empty room for the family to gather")


def test_regression_end_card_space_present_for_clear_top_third() -> None:
    """Cleared top third for a title is flagged."""
    assert "END_CARD_SPACE" in _regression_codes("leave the top third clear for the title")


def test_regression_end_card_space_present_for_blank_logo_area() -> None:
    """Blank area for a logo is flagged."""
    assert "END_CARD_SPACE" in _regression_codes("blank area for a logo")


def test_regression_ui_outside_screen_absent_for_phone_beside_card() -> None:
    """A phone beside a card is not a UI-on-screen violation."""
    assert "UI_OUTSIDE_SCREEN" not in _regression_codes("a phone lies beside a birthday card")


def test_regression_ui_outside_screen_absent_for_physical_button() -> None:
    """A physical button on a phone is not a UI-on-screen violation."""
    assert "UI_OUTSIDE_SCREEN" not in _regression_codes("a phone with a physical red button")


def test_regression_ui_outside_screen_absent_for_card_inside_screen() -> None:
    """A card staying inside the screen is not a violation."""
    assert "UI_OUTSIDE_SCREEN" not in _regression_codes(
        "a card pops up and stays inside the phone screen"
    )


def test_regression_ui_outside_screen_present_for_card_on_screen() -> None:
    """A card shown on the phone screen is flagged."""
    assert "UI_OUTSIDE_SCREEN" in _regression_codes(
        "the phone screen shows a white card that pops up"
    )


def test_regression_ui_outside_screen_present_for_tablet_notification() -> None:
    """A notification on a tablet is flagged."""
    assert "UI_OUTSIDE_SCREEN" in _regression_codes("a notification appears on the tablet")


def test_regression_action_not_completed_absent_for_completed_action() -> None:
    """An action whose path describes completion is not flagged."""
    frame = {
        "characters": ["hero"],
        "action": {
            "subject": "hero",
            "verb": "sets",
            "path_or_change": "hero sets the box down",
        },
    }
    assert "ACTION_NOT_COMPLETED" not in _regression_codes("hero sets the box down", frame)


def test_regression_handwritten_text_present_for_written_word() -> None:
    """Explicit writing of a word is flagged."""
    assert "HANDWRITTEN_TEXT_IN_PROMPT" in _regression_codes("hands write OPEN on tape")


def test_regression_handwritten_text_present_for_spoken_label() -> None:
    """A label stating text is flagged."""
    assert "HANDWRITTEN_TEXT_IN_PROMPT" in _regression_codes("the label says SALE")


def test_regression_handwritten_text_absent_for_unspecified_line() -> None:
    """Writing an unspecified line is not flagged."""
    assert "HANDWRITTEN_TEXT_IN_PROMPT" not in _regression_codes(
        "the hand writes a short line along the tape"
    )


def test_regression_handwritten_text_absent_for_illegible_sign() -> None:
    """A sign with no legible text is not flagged."""
    assert "HANDWRITTEN_TEXT_IN_PROMPT" not in _regression_codes("a sign says nothing legible")


def test_regression_prop_lettering_unlocked_present_with_mug() -> None:
    """Unbranded phone beside a mug is flagged and names the mug."""
    findings = guardrail_findings("an unbranded phone beside a mug")
    codes = {f["code"] for f in findings}
    assert "PROP_LETTERING_UNLOCKED" in codes
    assert any(
        "mug" in f.get("message", "") for f in findings if f["code"] == "PROP_LETTERING_UNLOCKED"
    )


def test_regression_prop_lettering_unlocked_absent_for_no_lettering() -> None:
    """A phone stated to have no lettering is not flagged."""
    assert "PROP_LETTERING_UNLOCKED" not in _regression_codes(
        "an unbranded phone with no lettering"
    )


def test_regression_prop_lettering_unlocked_absent_for_plain_mug() -> None:
    """A plainly described mug is not flagged."""
    assert "PROP_LETTERING_UNLOCKED" not in _regression_codes("a plain mug, unbranded, no printing")
