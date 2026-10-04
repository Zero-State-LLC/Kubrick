"""Map an authored frame action into a shot contract. No placeholder."""
from __future__ import annotations

import re
from collections.abc import Mapping

_VERBS = frozenset({
    "blinks", "crosses", "drops", "grabs", "holds", "hops", "leans", "lifts",
    "looks", "opens", "press", "presses", "reaches", "runs", "sits", "skids",
    "springs", "stands", "stays", "steps", "turns", "types", "walks",
})
_PLACEHOLDER_SUBJECT = "evidenced subject"
_PLACEHOLDER_VERB = "changes"


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def authored_sentence(value: object) -> str:
    """The action words that must reach the compiled prompt."""
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, Mapping):
        return ""
    subject = _text(value.get("subject"))
    verb = _text(value.get("verb"))
    path = _text(value.get("path_or_change") or value.get("path") or value.get("magnitude"))
    if subject == _PLACEHOLDER_SUBJECT and verb == _PLACEHOLDER_VERB and not path:
        return ""
    if path and path not in {subject, verb}:
        return path
    parts = [part for part in (subject, verb, _text(value.get("object"))) if part]
    if subject == _PLACEHOLDER_SUBJECT and verb == _PLACEHOLDER_VERB:
        return ""
    return " ".join(parts)


def structured_action(value: object) -> dict[str, str]:
    """``subject``, ``verb``, ``object``, and ``path_or_change`` from an authored action."""
    sentence = authored_sentence(value)
    if not sentence:
        return {"subject": "", "verb": "", "object": "", "path_or_change": ""}
    if isinstance(value, Mapping):
        subject = _text(value.get("subject"))
        verb = _text(value.get("verb"))
        obj = _text(value.get("object"))
        if subject == _PLACEHOLDER_SUBJECT:
            subject = ""
        if verb == _PLACEHOLDER_VERB and not obj:
            verb = ""
        if subject or verb or obj:
            return {
                "subject": subject,
                "verb": verb,
                "object": obj,
                "path_or_change": sentence,
            }
    return _from_sentence(sentence)


def _from_sentence(sentence: str) -> dict[str, str]:
    words = sentence.split()
    index = next(
        (pos for pos, word in enumerate(words) if _stem(word) in _VERBS),
        None,
    )
    if index is None:
        return {"subject": sentence, "verb": "", "object": "", "path_or_change": sentence}
    verb = _stem(words[index])
    subject = " ".join(words[:index])
    obj = " ".join(words[index + 1:])
    return {
        "subject": subject,
        "verb": verb,
        "object": obj,
        "path_or_change": sentence,
    }


def _stem(word: str) -> str:
    return re.sub(r"[^a-z-]", "", word.casefold())
