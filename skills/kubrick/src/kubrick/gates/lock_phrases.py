"""Critical lock lines that a picture prompt must still contain. Issue #107."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from kubrick.gates.jev_client import prompt_sha256


def _lock_phrases(hold: Mapping[str, object]) -> list[str]:
    """Critical present locks: every negative and positive line must appear."""
    if hold.get("critical") is not True or hold.get("blocked") is True:
        return []
    if hold.get("requirement") not in (None, "present"):
        return []
    lines: list[str] = []
    for key in ("negative", "positive"):
        value = hold.get(key)
        if isinstance(value, str) and value.strip():
            lines.append(" ".join(value.split()))
    return lines


def _scope_applies(hold: Mapping[str, object], prompt: Mapping[str, object]) -> bool:
    scope = hold.get("scope")
    location = prompt.get("location")
    if not isinstance(scope, str) or not scope.strip():
        return True
    if not isinstance(location, str) or not location.strip():
        return True
    return scope.strip() == location.strip()


def _cast_applies(hold: Mapping[str, object], prompt: Mapping[str, object]) -> bool:
    """A character lock skips a prompt whose cast list leaves that character out."""
    character = hold.get("character")
    cast = prompt.get("characters")
    if not isinstance(character, str) or not character.strip():
        return True
    if not isinstance(cast, Sequence) or isinstance(cast, (str, bytes)):
        return True
    names = {str(name).strip().casefold() for name in cast}
    return character.strip().casefold() in names


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
        for phrase in _lock_phrases(hold):
            phrases.append((hold, phrase))
    checks: list[dict[str, object]] = []
    for prompt in prompts:
        if not _visual_prompt(prompt):
            continue
        raw = prompt.get("prompt")
        body = " ".join(raw.split()) if isinstance(raw, str) else ""
        folded = body.casefold()
        for hold, phrase in phrases:
            if not _scope_applies(hold, prompt) or not _cast_applies(hold, prompt):
                continue
            if phrase.casefold() in folded:
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
