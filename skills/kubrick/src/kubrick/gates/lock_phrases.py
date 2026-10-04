"""Critical lock lines that a picture prompt must still contain. Issue #107."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from kubrick.gates.jev_client import prompt_sha256


def _lock_phrase(hold: Mapping[str, object]) -> str | None:
    """Critical present locks carry a negative or positive line that must appear."""
    if hold.get("critical") is not True or hold.get("blocked") is True:
        return None
    if hold.get("requirement") not in (None, "present"):
        return None
    for key in ("negative", "positive"):
        value = hold.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())
    return None


def _scope_applies(hold: Mapping[str, object], prompt: Mapping[str, object]) -> bool:
    scope = hold.get("scope")
    location = prompt.get("location")
    if not isinstance(scope, str) or not scope.strip():
        return True
    if not isinstance(location, str) or not location.strip():
        return True
    return scope.strip() == location.strip()


def _visual_prompt(prompt: Mapping[str, object]) -> bool:
    """Picture prompts carry light locks. Spoken cues do not."""
    surfaces = prompt.get("surfaces")
    if isinstance(surfaces, Sequence) and not isinstance(surfaces, (str, bytes)):
        names = {str(item) for item in surfaces if str(item).strip()}
        if names and names.isdisjoint({"image", "video"}):
            return False
    return prompt.get("channel") != "elevenlabs"


def missing_lock_phrases(
    prompts: Sequence[Mapping[str, object]], holds: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """A recorded pass cannot bless a picture prompt that drops a critical lock line."""
    phrases: list[tuple[Mapping[str, object], str]] = []
    for hold in holds:
        phrase = _lock_phrase(hold)
        if phrase is not None:
            phrases.append((hold, phrase))
    checks: list[dict[str, object]] = []
    for prompt in prompts:
        if not _visual_prompt(prompt):
            continue
        raw = prompt.get("prompt")
        body = " ".join(raw.split()) if isinstance(raw, str) else ""
        folded = body.casefold()
        for hold, phrase in phrases:
            if not _scope_applies(hold, prompt) or phrase.casefold() in folded:
                continue
            shot = prompt.get("shot")
            checks.append({
                "shot": shot.strip() if isinstance(shot, str) else shot,
                "channel": prompt.get("channel"),
                "prompt_sha256": prompt_sha256(body),
                "verdict": "fail",
                "findings": [{
                    "code": "MISSING_LOCK",
                    "hold_id": str(hold.get("id") or ""),
                    "message": f"{phrase} is missing from the prompt",
                }],
            })
    return checks
