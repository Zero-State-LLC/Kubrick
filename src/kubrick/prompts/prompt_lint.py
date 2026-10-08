"""Deterministic prompt lint. No model calls.

Brand phrases and weak negations are rewritten. Contradictions, meta words,
missing board locks, and infeasible motion block before Jev.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

_DEFAULT_ALIASES = {
    "black-and-red high-tops": "unbranded canvas high-tops",
    "nike swoosh": "plain canvas with no logo",
}
_NEGATED = re.compile(r"\bno\s+([a-z0-9][\w-]*)", re.IGNORECASE)
_BULBOUS = re.compile(r"\b(?:big\s+)?bulbous\s+head\b|\boversized\s+head\b", re.IGNORECASE)
_HEAD_HOLD = re.compile(
    r"head(?:[\w-]|\s){0,24}(?:size|ratio|proportion)|not oversized|head-size",
    re.IGNORECASE,
)
_META = re.compile(r"\bgibberish\b|\bno real words\b", re.IGNORECASE)
_TEARS = re.compile(r"\bno tears\b", re.IGNORECASE)
_PANTS = re.compile(r"\bsweatpants\b", re.IGNORECASE)
_FABRIC = "smooth intact fabric at the knees"
_SMALL = re.compile(r"\bdebris\b|\bsmall foreground\b|\bforeground debris\b", re.IGNORECASE)
_SUBSECOND = re.compile(
    r"\bsub-?second\b|\bhalf a second\b|\b0\.\d+\s*s(?:econds)?\b",
    re.IGNORECASE,
)
_LOW_RES = re.compile(r"\b480p\b|\b480\b", re.IGNORECASE)
_HOLD_MARK = re.compile(r"\b1\.6\s*s(?:econds)?\b", re.IGNORECASE)

BLOCKING = frozenset({
    "POSITIVE_NEGATIVE_CONFLICT",
    "HOLD_CONTRADICTION",
    "META_WORD",
    "LOCK_MISSING_IN_BOARD",
    "SMALL_FG_MOTION_LOW_RES",
    "SUBSECOND_TIMING_IGNORED",
})


def _finding(code: str, message: str, suggestion: str = "") -> dict[str, str]:
    return {"code": code, "message": f"{code}: {message}", "suggestion": suggestion}


def brand_aliases(document: Mapping[str, object] | None) -> dict[str, str]:
    """Brief aliases override the built-in unbranded canvas pair."""
    found = dict(_DEFAULT_ALIASES)
    if not isinstance(document, Mapping):
        return found
    raw = document.get("brand_safe_aliases")
    if not isinstance(raw, Mapping):
        return found
    for key, value in raw.items():
        if isinstance(key, str) and isinstance(value, str) and key.strip() and value.strip():
            found[key.strip()] = value.strip()
    return found


def rewrite_surface(
    text: str, aliases: Mapping[str, str] | None = None,
) -> tuple[str, list[dict[str, str]]]:
    """Rewrite brand terms and the sweatpants negation. Other lint is not applied."""
    table = dict(_DEFAULT_ALIASES)
    if isinstance(aliases, Mapping):
        for key, value in aliases.items():
            if isinstance(key, str) and isinstance(value, str) and key.strip() and value.strip():
                table[key.strip()] = value.strip()
    rewritten = text
    findings: list[dict[str, str]] = []
    for phrase in sorted(table, key=len, reverse=True):
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        if pattern.search(rewritten) is None:
            continue
        replacement = table[phrase]
        rewritten = pattern.sub(replacement, rewritten)
        findings.append(_finding(
            "BRAND_TERM",
            f"{phrase} rewritten to {replacement}",
            replacement,
        ))
    if _TEARS.search(rewritten) and _PANTS.search(rewritten):
        rewritten = _TEARS.sub(_FABRIC, rewritten)
        findings.append(_finding(
            "WEAK_NEGATION",
            "no tears on sweatpants rewritten to the intact-fabric line",
            _FABRIC,
        ))
    return rewritten, findings


def lint_text(
    text: str,
    *,
    holds: Sequence[str] = (),
    frame: Mapping[str, object] | None = None,
    resolution: object = None,
    duration: object = None,
    chained: bool = False,
    locks: Sequence[str] = (),
    declared: Sequence[str] = (),
) -> list[dict[str, str]]:
    """Findings for one prompt. Rewrites are not applied here.

    ``declared`` adds plan lock lines (0.27.14) to the hold texts whose own negative
    wording is not read as a conflict.
    """
    findings: list[dict[str, str]] = []
    findings.extend(_conflicts(text, [*holds, *declared]))
    findings.extend(_hold_conflicts(text, holds))
    if _META.search(text):
        findings.append(_finding(
            "META_WORD",
            "gibberish or no-real-words would be printed as on-screen text",
            "describe unreadable marks without naming the word",
        ))
    findings.extend(_motion(text, frame, resolution, duration, chained))
    findings.extend(_missing_board(text, locks))
    return findings
def review_prompt(
    text: str,
    *,
    holds: Sequence[str] = (),
    aliases: Mapping[str, str] | None = None,
    frame: Mapping[str, object] | None = None,
    resolution: object = None,
    duration: object = None,
    chained: bool = False,
    locks: Sequence[str] = (),
) -> tuple[str, list[dict[str, str]]]:
    """Rewrite, then lint the text that would be sent."""
    rewritten, rewrites = rewrite_surface(text, aliases)
    return rewritten, [
        *rewrites,
        *lint_text(
            rewritten, holds=holds, frame=frame, resolution=resolution,
            duration=duration, chained=chained, locks=locks,
        ),
    ]


def _missing_board(text: str, locks: Sequence[str]) -> list[dict[str, str]]:
    """Run the board-lock helpers. A missing lock blocks; the suggestion is the repair."""
    named = [item.strip() for item in locks if isinstance(item, str) and item.strip()]
    if not named:
        return []
    missing = missing_board_locks(text, named)
    if not missing:
        return []
    repaired = emit_board_prompt(text, named)
    for item in missing:
        item["suggestion"] = repaired
    return missing


def missing_board_locks(prompt: str, locks: Sequence[str]) -> list[dict[str, str]]:
    """A scoped material or character lock that the board prompt does not state."""
    folded = prompt.casefold()
    findings: list[dict[str, str]] = []
    for lock in locks:
        text = lock.strip()
        if text and text.casefold() not in folded:
            findings.append(_finding(
                "LOCK_MISSING_IN_BOARD",
                f"board prompt omits scoped lock {text}",
                text,
            ))
    return findings


def emit_board_prompt(prompt: str, locks: Sequence[str]) -> str:
    """Append each missing scoped lock so the emitted board states it."""
    text = prompt.strip()
    for lock in locks:
        clause = lock.strip()
        if not clause or clause.casefold() in text.casefold():
            continue
        text = f"{text}; {clause}" if text else clause
    return text


def _conflicts(
    text: str,
    declared: Sequence[str] = (),
) -> list[dict[str, str]]:
    """Return positive-negative conflicts after masking declared negatives.

    A plan's own declared negative line is not a conflict with the rest of
    the prompt (0.27.14).
    """
    negative_lines: list[str] = []
    for line in declared:
        if not isinstance(line, str) or not line.strip():
            continue
        if _NEGATED.search(line) is None:
            continue
        negative_lines.append(line)

    masked = text
    for line in sorted(negative_lines, key=len, reverse=True):
        words = r"\s+".join(re.escape(word) for word in line.split())
        pattern = rf"(?<!\w){words}(?!\w)"
        masked = re.sub(pattern, " ", masked, flags=re.IGNORECASE)

    negated = {word.casefold() for word in _NEGATED.findall(masked)}
    if not negated:
        return []
    outside = _NEGATED.sub(" ", masked).casefold()
    findings: list[dict[str, str]] = []
    for word in sorted(negated):
        if re.search(rf"\b{re.escape(word)}\b", outside):
            findings.append(_finding(
                "POSITIVE_NEGATIVE_CONFLICT",
                f"prompt names {word} and also says no {word}",
                f"keep one statement about {word}",
            ))
    return findings

def _hold_conflicts(text: str, holds: Sequence[str]) -> list[dict[str, str]]:
    blob = " ".join(holds)
    if _BULBOUS.search(text) and _HEAD_HOLD.search(blob):
        return [_finding(
            "HOLD_CONTRADICTION",
            "big bulbous head contradicts the head-size hold",
            "state the numeric head ratio and drop the size adjective",
        )]
    return []


def _motion(
    text: str,
    frame: Mapping[str, object] | None,
    resolution: object,
    duration: object,
    chained: bool,
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    blob = " ".join(part for part in (text, _resolution_blob(frame), _as_text(resolution)) if part)
    if _SMALL.search(text) and _low_res(blob, frame, resolution):
        findings.append(_finding(
            "SMALL_FG_MOTION_LOW_RES",
            "small foreground motion at 480p does not render",
            _registry_suggestion(
                "small_fg_motion",
                "move the beat to an insert shot, render at 720p, or carry it as sound",
            ),
        ))
    seconds = _duration_value(duration, frame)
    if (seconds is not None and 0 < seconds < 1) or _SUBSECOND.search(text):
        findings.append(_finding(
            "SUBSECOND_TIMING_IGNORED",
            "a sub-second beat is dropped by the generator",
            _registry_suggestion(
                "subsecond_timing",
                "plan the beat in whole seconds or move the timing into the cut",
            ),
        ))
    if chained or _HOLD_MARK.search(text) or _frame_chained(frame):
        findings.append(_finding(
            "START_HOLD_1_6S",
            "a chained start holds about 1.6 seconds before the action",
            _registry_suggestion("start_hold", "trim the hold in the cut list"),
        ))
    return findings


def _registry_suggestion(kind: str, fallback: str) -> str:
    from kubrick.qc.drift_registry import join_mitigations, load_registry

    raw = load_registry().get("entries")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return fallback
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        trigger = item.get("trigger")
        if not isinstance(trigger, Mapping) or trigger.get("kind") != kind:
            continue
        mitigations = item.get("mitigations")
        if isinstance(mitigations, Sequence) and not isinstance(mitigations, (str, bytes)):
            text = join_mitigations([str(entry) for entry in mitigations])
            if text:
                return text
    return fallback


def _resolution_blob(frame: Mapping[str, object] | None) -> str:
    if not isinstance(frame, Mapping):
        return ""
    parts: list[str] = []
    for source in _sources(frame):
        for key in ("resolution", "quality", "height"):
            value = source.get(key)
            if value is not None:
                parts.append(str(value))
    return " ".join(parts)


def _sources(frame: Mapping[str, object]) -> list[Mapping[str, object]]:
    sources = [frame]
    params = frame.get("provider_parameters")
    if isinstance(params, Mapping):
        sources.append(params)
    return sources


def _low_res(blob: str, frame: Mapping[str, object] | None, resolution: object) -> bool:
    if _LOW_RES.search(blob) or _LOW_RES.search(_as_text(resolution)):
        return True
    if not isinstance(frame, Mapping):
        return False
    for source in _sources(frame):
        height = source.get("height")
        if isinstance(height, bool) or not isinstance(height, (int, float)):
            continue
        if 0 < float(height) <= 480:
            return True
    return False


def _duration_value(duration: object, frame: Mapping[str, object] | None) -> float | None:
    from kubrick.runtime.value_coerce import as_float

    parsed = as_float(duration)
    if parsed is not None:
        return parsed
    if not isinstance(frame, Mapping):
        return None
    for source in _sources(frame):
        for key in ("duration_seconds", "durationSeconds", "duration"):
            found = as_float(source.get(key))
            if found is not None:
                return found
    return None


def _frame_chained(frame: Mapping[str, object] | None) -> bool:
    if not isinstance(frame, Mapping):
        return False
    from kubrick.plan.shot_plan import chain_source

    return chain_source(frame) is not None


def _as_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""
