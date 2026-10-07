"""Compiled prompt text for lock carriers. #133 review follow-up to issue #107."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

_COMPILING: list[bool] = []


def _folded(value: str) -> str:
    return " ".join(value.split()).casefold()


def positive_omitted(lock: Mapping[str, object] | None, prompt_text: str | None) -> bool:
    """The lock defines a positive line that the compiled prompt does not say (#133).

    ``prompt_text`` is None when the caller has no compiled prompt; then nothing is omitted.
    """
    if lock is None or prompt_text is None:
        return False
    positive = lock.get("positive")
    if not isinstance(positive, str) or not positive.strip():
        return False
    return _folded(positive) not in _folded(prompt_text)


def compiled_prompt_text(document: Mapping[str, object]) -> dict[str, str] | None:
    """Compiled prompt text per frame id. Lock positives are checked against it (#133).

    None while the prompt compiler itself asks for the lock table (no recursion).
    """
    if _COMPILING:
        return None
    if not isinstance(document.get("locks"), Sequence):
        return {}
    from kubrick.prompts.storyboard_prompts import shots_from_document

    _COMPILING.append(True)
    try:
        shots = shots_from_document(document)
    finally:
        _COMPILING.pop()
    found: dict[str, str] = {}
    for shot in shots:
        prompt = shot.get("prompt")
        if isinstance(prompt, str):
            found[str(shot.get("shot_id"))] = prompt
    return found
