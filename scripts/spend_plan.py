#!/usr/bin/env python3
"""Inferred spend, the execution checklist, and multi-shot prompt text.

Issues #40 and #41. Pricing is provider data labelled INFERRED. The estimate
uses generated seconds from the cut list, or from a retime plan when each
``clip_id`` is counted once. ``image_rate`` is recorded and not added. A
missing price is ``NOT_COMPUTABLE``, never 0. No provider is called.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from continuity_locks import frame_field, warning
from prompt_text import character_lock_clauses
from provider_capabilities import capabilities_for_document, pricing_for

CHECKLIST = (
    "on -32602 or 'Job not found', check get_movie includeCredits before any retry",
    "wait on processingJobId, not generationJobIds",
)
_LABEL = "INFERRED"


def whole_number(value: float) -> int | float:
    rounded = round(float(value), 4)
    if float(rounded).is_integer():
        return int(rounded)
    return float(rounded)


def _shot_rows(rows: Sequence[Mapping[str, object]]) -> list[tuple[str, float]]:
    """Generated seconds. Each shared ``clip_id`` counts once."""
    seen: set[str] = set()
    found: list[tuple[str, float]] = []
    for item in rows:
        seconds = item.get("generated_seconds")
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
            continue
        clip = item.get("clip_id")
        if isinstance(clip, str) and clip.strip():
            if clip in seen:
                continue
            seen.add(clip)
        shot = item.get("shot")
        label = shot.strip() if isinstance(shot, str) and shot.strip() else "shot"
        found.append((label, float(seconds)))
    return found


def spend_estimate(
    provider: str,
    rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Per-shot and total credits. Missing pricing is NOT_COMPUTABLE, not 0."""
    pricing = pricing_for(provider)
    rate = None if pricing is None else pricing.get("rate")
    if pricing is None or isinstance(rate, bool) or not isinstance(rate, (int, float)):
        return {
            "label": _LABEL,
            "status": "NOT_COMPUTABLE",
            "unit": None,
            "resolution": None,
            "rate": None,
            "shots": [],
            "total_credits": None,
        }
    shots: list[dict[str, object]] = []
    total = 0.0
    for label, seconds in _shot_rows(rows):
        from provider_limits import billed_credits

        credits = billed_credits(seconds, float(rate))
        total += credits
        shots.append({
            "shot": label,
            "generated_seconds": whole_number(seconds),
            "credits": whole_number(credits),
        })
    resolution = pricing.get("resolution")
    unit = pricing.get("unit")
    return {
        "label": _LABEL,
        "status": _LABEL,
        "unit": unit if isinstance(unit, str) else None,
        "resolution": resolution if isinstance(resolution, str) else None,
        "rate": whole_number(float(rate)),
        "shots": shots,
        "total_credits": whole_number(total),
    }


def budget_error(estimate: Mapping[str, object], cap: object) -> str | None:
    """Fail closed when a numeric cap is set and the estimate is missing or over it."""
    if isinstance(cap, bool) or not isinstance(cap, (int, float)):
        return None
    cap_text = whole_number(float(cap))
    unverifiable = (
        f"BUDGET_CAP_UNVERIFIABLE budget_cap_credits {cap_text} "
        "is set but the spend estimate is not computable"
    )
    if estimate.get("status") != _LABEL:
        return unverifiable
    total = estimate.get("total_credits")
    if isinstance(total, bool) or not isinstance(total, (int, float)):
        return unverifiable
    if float(total) > float(cap):
        return (
            f"BUDGET_CAP_EXCEEDED estimate {whole_number(float(total))} credits "
            f"is above budget_cap_credits {cap_text}"
        )
    return None


def attach_spend(
    result: dict[str, object], provider: str, rows: Sequence[Mapping[str, object]],
) -> None:
    """Attach the estimate and the checklist. Does not add ``multi_shot_prompt``."""
    result["spend_estimate"] = spend_estimate(provider, rows)
    result["execution_checklist"] = list(CHECKLIST)


def shot_count_warning(
    count: int,
    provider: str,
    document: Mapping[str, object] | None = None,
) -> dict[str, str | None] | None:
    """Warn when a multi-shot single clip has more than 5 shots. 5 does not warn."""
    caps = capabilities_for_document(provider, document)
    if not caps.get("is_multi_shot_single_clip") or count <= 5:
        return None
    return warning(
        "SHOT_COUNT_HIGH",
        None,
        f"{count} shots in one clip is above 5",
        "split the clip so each generation has at most 5 shots",
    )


def _identity_pool(document: Mapping[str, object]) -> list[str]:
    locks: list[str] = []
    locks.extend(str(item) for item in _as_list(document.get("character_locks")))
    raw = document.get("characters")
    if isinstance(raw, Mapping):
        for spec in raw.values():
            if isinstance(spec, Mapping):
                locks.extend(str(item) for item in _as_list(spec.get("character_locks")))
    return character_lock_clauses(locks, from_lock=True)


def _as_list(value: object) -> list[object]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return list(value)
    return []


def _is_wardrobe(clause: str) -> bool:
    return clause.startswith("WARDROBE LOCK:")


def _is_prop(clause: str) -> bool:
    return " LOCK:" in clause and not _is_wardrobe(clause)


def _is_identity(clause: str, known: set[str]) -> bool:
    return clause.casefold() in known or "never swap sides" in clause.casefold()


def _lock_line(clause: str, known: set[str]) -> bool:
    return _is_wardrobe(clause) or _is_prop(clause) or _is_identity(clause, known)


def _continuity(
    frames: Sequence[Mapping[str, object]], document: Mapping[str, object],
) -> list[str]:
    """Wardrobe, prop, and identity lines once. Built from planner lines, not a semicolon split."""
    from continuity_locks import frame_id, prop_assignments
    from reference_lint import prompt_lines

    known = {item.casefold() for item in _identity_pool(document)}
    assigned, _prop_errors = prop_assignments(document, frames)
    ordered: list[str] = []
    for index, frame in enumerate(frames, start=1):
        shot = frame_id(frame, index)
        props = assigned.get(shot, []) if isinstance(assigned, Mapping) else []
        for clause in prompt_lines(document, frame, props):
            if _lock_line(clause, known) and clause not in ordered:
                ordered.append(clause)
    for clause in _identity_pool(document):
        if clause not in ordered:
            ordered.append(clause)
    return ordered


def _lighting(frames: Sequence[Mapping[str, object]]) -> str:
    seen: list[str] = []
    for frame in frames:
        states = frame_field(frame, "light_states")
        if not isinstance(states, Mapping):
            continue
        for value in states.values():
            text = str(value).strip()
            if text and text not in seen:
                seen.append(text)
    return "; ".join(seen) if seen else "unspecified"


def _ending(frame: Mapping[str, object]) -> str:
    parts: list[str] = []
    action = frame_field(frame, "action")
    if isinstance(action, str) and action.strip():
        parts.append(action.strip())
    states = frame_field(frame, "object_states")
    if isinstance(states, Mapping):
        for value in states.values():
            text = str(value).strip()
            if text and text not in parts:
                parts.append(text)
    return "; ".join(parts) if parts else "unspecified"


def multi_shot_prompt(
    provider: str,
    frames: Sequence[Mapping[str, object]],
    directives: Sequence[Mapping[str, object]],
    document: Mapping[str, object],
    aspect: str,
) -> str | None:
    """Header, labelled shots, one continuity block, and an ending state."""
    caps = capabilities_for_document(provider, document)
    if not caps.get("is_multi_shot_single_clip") or not frames:
        return None
    rows = _shot_rows(directives)
    total = whole_number(sum(seconds for _label, seconds in rows))
    ratio = aspect.strip() or "unspecified"
    lines = [
        f"{len(frames)} shots, {total}s generated, aspect {ratio}, lighting: {_lighting(frames)}",
    ]
    prompts = [str(frame.get("prompt") or "") for frame in frames]
    for index, prompt in enumerate(prompts, start=1):
        seconds = rows[index - 1][1] if index - 1 < len(rows) else 0.0
        lines.append(f"Shot {index} ({whole_number(seconds)}s): {prompt}")
    lines.append("Continuity:")
    lines.extend(_continuity(frames, document))
    last = frames[-1]
    lines.append(f"Ending state: {_ending(last)}")
    return "\n".join(lines)


def stamp_closed(
    payload: dict[str, object],
    message: str,
    extra: Mapping[str, object],
) -> dict[str, object]:
    """Set the fail-closed code. Budget refusals also carry the estimate."""
    if message.startswith("BUDGET_CAP_EXCEEDED") or message.startswith("BUDGET_CAP_UNVERIFIABLE"):
        payload["code"] = message.split()[0]
        payload.update(dict(extra))
    elif message.startswith("VOICE_LOCK_VIOLATION"):
        payload["code"] = "VOICE_LOCK_VIOLATION"
    return payload


def keyframe_extras(
    document: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
    directives: Sequence[Mapping[str, object]],
    aspect: str,
) -> tuple[dict[str, object], str | None]:
    """Spend, checklist, and multi-shot text. The error is set when the cap fails."""
    estimate = spend_estimate("keyframe", directives)
    extra: dict[str, object] = {
        "spend_estimate": estimate,
        "execution_checklist": list(CHECKLIST),
    }
    prompt = multi_shot_prompt("keyframe", frames, directives, document, aspect)
    if prompt:
        extra["multi_shot_prompt"] = prompt
    return extra, budget_error(estimate, document.get("budget_cap_credits"))
