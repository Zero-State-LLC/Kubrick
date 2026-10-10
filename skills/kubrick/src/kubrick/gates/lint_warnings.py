"""Non-blocking prompt guardrail warnings for the pre-spend gate result (0.27.15)."""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from kubrick.gates.hold_scope import prompt_hold_texts, scoped_lock_lines
from kubrick.gates.jev_holds import hold_list


def lint_warnings(
    document: Mapping[str, object],
    prompts: Sequence[Mapping[str, object]],
) -> list[dict[str, str]]:
    """Collect non-blocking guardrail findings for the compiled prompts."""
    from kubrick.gates.jev_gate import _frame_for
    from kubrick.plan.lock_positive_lines import lock_negative_lines
    from kubrick.prompts.prompt_guardrails import GUARDRAIL_CODES
    from kubrick.prompts.prompt_lint import BLOCKING, lint_text

    if not prompts:
        return []
    raw_holds = hold_list(document)
    found: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for prompt in prompts:
        text = prompt.get("prompt")
        if not isinstance(text, str):
            continue
        frame = _frame_for(document, prompt.get("shot"))
        declared = lock_negative_lines(document, frame) if frame else []
        locks: Sequence[str] = ()
        holds: Sequence[str] = ()
        if isinstance(raw_holds, list):
            chosen = scoped_lock_lines(raw_holds, prompt)
            if isinstance(chosen, str):
                continue
            locks = chosen
            texts = prompt_hold_texts(raw_holds, prompt)
            holds = texts if isinstance(texts, list) else []
        shot = str(prompt.get("shot") or "")
        for item in lint_text(
            text, holds=holds, frame=frame or None, locks=locks, declared=declared,
        ):
            code = item["code"]
            if code not in GUARDRAIL_CODES or code in BLOCKING:
                continue
            key = (code, shot)
            if key in seen:
                continue
            seen.add(key)
            found.append({
                "code": code,
                "message": item["message"],
                "suggestion": item.get("suggestion", ""),
                "shot": shot,
            })
    return found