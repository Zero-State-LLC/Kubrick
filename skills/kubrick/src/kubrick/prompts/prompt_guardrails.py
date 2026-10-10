"""Deterministic prompt guardrails.

Five regex based checks that run in order over a shot prompt. Standard library
only: no model calls, no network, no third party imports.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

GUARDRAIL_CODES = (
    "END_CARD_SPACE",
    "PROP_LETTERING_UNLOCKED",
    "UI_OUTSIDE_SCREEN",
    "ACTION_NOT_COMPLETED",
    "HANDWRITTEN_TEXT_IN_PROMPT",
)

GUARDRAIL_BLOCKING = frozenset({"END_CARD_SPACE", "UI_OUTSIDE_SCREEN"})

_END_CARD_SPACE_RE = re.compile(
    r"(?ix)"
    r"(?:"
    r"(?:empty|blank|clear|open|negative|clean|spare)\s+(?:\w+\s+){0,3}?"
    r"(?:space|area|room|region|zone|section|part|gap|third|half|quarter)\b"
    r"(?:\s+\w+){0,4}?\s+for\b"
    r"|(?:space|area|room|region|zone|gap)\b(?:\s+\w+){0,4}?\s+for\b"
    r"(?:\s+\w+){0,3}?\s+(?:end\s*card|title|logo|caption|text|overlay|subtitle|lettering|credit)"
    r"|\bleave\b(?:\s+\w+){0,6}?\s(?:clear|blank|empty|open)\b"
    r"|\bend\s*card\s+(?:space|area|room)\b"
    r")"
)

_PROPS = (
    "smartphone|phone|tablet|laptop|marker|pencil|bottle|mug|cup|pen|box|bag|"
    "shoe|sneaker|cap|jacket|shirt|hoodie|label|package|carton|can"
)
_PROP_RE = re.compile(rf"\b(?:{_PROPS})s?\b", re.I)
_UNBRANDED_RE = re.compile(
    r"unbranded|no lettering|no letters|no printing|no printed|unlabell?ed|no logo|no brand",
    re.I,
)

_SCREEN_RE = re.compile(r"\b(?:phone|smartphone|tablet|laptop|monitor|screen|display)s?\b", re.I)
_UI_ELEMENT_RE = re.compile(
    r"\b(?:card|popup|pop-up|notification|banner|dialog|toast|overlay|button|"
    r"check mark|checkmark)s?\b",
    re.I,
)
_UI_CONTAINED_RE = re.compile(
    r"inside the screen|inside the phone screen|inside the display|within the screen|"
    r"within the display|within the screen edges|on the screen only|stays inside|stays within",
    re.I,
)

_COMPLETION_RE = re.compile(
    r"\b(?:set|place|put|lift|raise|lower|press|push|pull|tap|write|finish|cap|uncap|open|"
    r"close|hand|give|take|pick|drop|turn|slide|stick|tape|tear|hold|fold|wrap|stack|"
    r"click|sign|draw|point)(?:s|es|ed|d|ing)?\b",
    re.I,
)
_HANDS_RE = re.compile(r"\bhands?\b", re.I)

_HANDWRITING_CUE_RE = re.compile(
    r"\b(?:writes|write|written|handwritten|handwriting|reads|spelled|lettering|"
    r"label says|sign says)\b",
    re.I,
)
_QUOTED_TEXT_RE = re.compile(r'["\u201c\u201d][^"\u201c\u201d]{3,}["\u201c\u201d]')
_JOINED_TOKEN_RE = re.compile(r"\b(?:[A-Za-z]+[-_]){2,}[A-Za-z]+\b")


def _finding(code: str, message: str, suggestion: str = "") -> dict[str, str]:
    """Build one finding dict in the shared prompt lint shape."""
    return {"code": code, "message": f"{code}: {message}", "suggestion": suggestion}


def _check_end_card_space(text: str) -> dict[str, str] | None:
    """Flag prompts that reserve empty space for an end card, title or text."""
    if not _END_CARD_SPACE_RE.search(text):
        return None
    return _finding(
        "END_CARD_SPACE",
        "generators draw a literal blank panel",
        "describe the real background (wall, sky, table) and add end cards, titles "
        "and captions in post",
    )


def _check_prop_lettering(text: str) -> dict[str, str] | None:
    """Flag a named handheld prop that carries no unbranded lock phrase."""
    prop = _PROP_RE.search(text)
    if prop is None or _UNBRANDED_RE.search(text):
        return None
    return _finding(
        "PROP_LETTERING_UNLOCKED",
        f"the prop '{prop.group(0)}' is named without an unbranded lock phrase, so the "
        "generator may print lettering on it",
        "name the prop as unbranded with no printed lettering on it, or keep the "
        "printed surface out of frame",
    )


def _check_ui_outside_screen(text: str) -> dict[str, str] | None:
    """Flag a UI element named without a phrase that keeps it inside the screen."""
    if not _SCREEN_RE.search(text) or not _UI_ELEMENT_RE.search(text):
        return None
    if _UI_CONTAINED_RE.search(text):
        return None
    return _finding(
        "UI_OUTSIDE_SCREEN",
        "an on-screen UI element is named without a phrase that keeps it inside the device screen",
        "say the UI element stays inside the device screen edges and never extends "
        "past the frame of the device",
    )


def _check_action_not_completed(
    text: str, frame: Mapping[str, object] | None
) -> dict[str, str] | None:
    """Flag a cast or a pair of hands with no completed action verb to show."""
    data: Mapping[str, object] = frame or {}
    cast = data.get("characters") or data.get("cast") or []
    if isinstance(cast, str):
        cast = [cast] if cast.strip() else []
    has_hands = bool(_HANDS_RE.search(text))
    if not cast and not has_hands:
        return None

    action = data.get("action")
    if isinstance(action, Mapping):
        action = action.get("subject") or action.get("path_or_change") or ""
    if "action" not in data:
        if not has_hands:
            return None
        source = text
    else:
        source = action if isinstance(action, str) else ""

    if source.strip() and _COMPLETION_RE.search(source):
        return None
    return _finding(
        "ACTION_NOT_COMPLETED",
        "the shot shows people or hands but names no action verb the hands complete",
        "name the action as a verb the hands complete inside the shot "
        "(for example: sets the box on the stack, then caps the marker)",
    )


def _check_handwritten_text(text: str) -> dict[str, str] | None:
    """Flag prompts that ask the generator to render specific legible text."""
    for cue in _HANDWRITING_CUE_RE.finditer(text):
        window = text[cue.end() : cue.end() + 60]
        if _QUOTED_TEXT_RE.search(window) or _JOINED_TOKEN_RE.search(window):
            return _finding(
                "HANDWRITTEN_TEXT_IN_PROMPT",
                "the prompt asks the generator to render specific legible written text",
                "video models garble handwriting: render the exact text as a post overlay "
                "(for example ffmpeg drawtext) in a handwriting font that supports lowercase, "
                "or film a real insert",
            )
    return None


def guardrail_findings(
    text: str, frame: Mapping[str, object] | None = None
) -> list[dict[str, str]]:
    """Run the five guardrail checks in order and return the findings."""
    findings: list[dict[str, str]] = []
    for finding in (
        _check_end_card_space(text),
        _check_prop_lettering(text),
        _check_ui_outside_screen(text),
        _check_action_not_completed(text, frame),
        _check_handwritten_text(text),
    ):
        if finding is not None:
            findings.append(finding)
    return findings
