#!/usr/bin/env python3
"""Prop, wardrobe, and reference locks. Issues #28, #29, and #30."""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from contextvars import ContextVar, Token

from kubrick.gates.hold_scope import frame_place, prop_in_place
from kubrick.plan.brief_constraints import collect_character_locks, string_list
from kubrick.prompts.prompt_text import character_lock_feature, join_clauses

_STRICT: ContextVar[bool] = ContextVar("kubrick_prep_strict", default=False)
REFERENCE_CODE = "REFERENCE_LOCK_CONTRADICTION"
_BLOCKING_CODES = frozenset({
    REFERENCE_CODE,
    "LOCATION_REFERENCE_CONTRADICTION",
    "START_FRAME_MISSING",
})
_ARROW = "->"
_MOTION = (
    "stand", "stands", "standing", "jump", "jumps", "jumping", "spring", "springs",
    "springing", "run", "runs", "running", "turn", "turns", "turning",
)
_PLAIN_LOGO = re.compile(r"\b(?:no|without)\s+(?:a\s+)?logo\b", re.IGNORECASE)
_LOGO = re.compile(r"\blogo\b", re.IGNORECASE)
_DRIFT_RECOMMENDATION = (
    "use a start frame that already shows the plain top in the moving pose, "
    "retouch after generation, or accept the drift"
)
_REFERENCE_RECOMMENDATION = "edit the reference, drop the lock, or accept the drift"


def set_strict(enabled: bool) -> None:
    _STRICT.set(enabled)


def bind_strict(enabled: bool) -> Token[bool]:
    return _STRICT.set(enabled)


def unbind_strict(token: Token[bool]) -> None:
    _STRICT.reset(token)


def strict_enabled(source: Mapping[str, object] | None = None) -> bool:
    if _STRICT.get():
        return True
    return isinstance(source, Mapping) and source.get("strict") is True


def warning(
    code: str,
    shot: str | None,
    message: str,
    recommendation: str,
    *,
    character: str | None = None,
) -> dict[str, str | None]:
    found: dict[str, str | None] = {
        "code": code,
        "shot": shot,
        "message": message,
        "recommendation": recommendation,
    }
    if character is not None:
        found["character"] = character
    return found


def frame_id(frame: Mapping[str, object], index: int) -> str:
    raw = frame.get("frame_id")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return f"frame-{index:03d}"


def frame_field(frame: Mapping[str, object], key: str) -> object:
    if key in frame and frame.get(key) is not None:
        return frame.get(key)
    params = frame.get("provider_parameters")
    if isinstance(params, Mapping) and params.get(key) is not None:
        return params.get(key)
    return None


def resolve_state(states: Mapping[str, str], token: str) -> str | None:
    """Public alias for the #28 state resolver."""
    return _resolve_state(states, token)


def _norm(text: str) -> str:
    return " ".join(text.casefold().split())


def _introduces(added: str, pending: str) -> bool:
    left, right = _norm(added), _norm(pending)
    return bool(left and right and (left in right or right in left))


def introduced_residue(
    prior: Sequence[str],
    added: Sequence[object],
    pending: Sequence[str],
) -> tuple[list[str], list[str]]:
    """Carry residue forward. Brief residue starts at the introducing frame."""
    fresh = [str(item).strip() for item in added if str(item).strip()]
    kept: list[str] = []
    still: list[str] = []
    for item in pending:
        text = str(item).strip()
        if not text:
            continue
        if any(_introduces(piece, text) for piece in fresh):
            kept.append(text)
        else:
            still.append(text)
    return list(dict.fromkeys([*prior, *fresh, *kept])), still


def _character_table(document: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    raw = document.get("characters")
    if not isinstance(raw, Mapping):
        return {}
    return {str(key): value for key, value in raw.items() if isinstance(value, Mapping)}


def _present(frame: Mapping[str, object]) -> list[str] | None:
    raw = frame_field(frame, "characters")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return None
    return [str(item).strip() for item in raw if str(item).strip()]


def _wardrobe_text(
    table: Mapping[str, Mapping[str, object]],
    frame: Mapping[str, object],
    character: str,
    present: Sequence[str],
) -> str | None:
    override = frame_field(frame, "wardrobe")
    if isinstance(override, str) and override.strip() and len(present) == 1:
        return override.strip()
    if isinstance(override, Mapping):
        value = override.get(character)
        if isinstance(value, str) and value.strip():
            return value.strip()
    spec = table.get(character)
    if spec is None:
        return None
    base = spec.get("wardrobe")
    if isinstance(base, str) and base.strip():
        return base.strip()
    return None


def wardrobe_lines(document: Mapping[str, object], frame: Mapping[str, object]) -> list[str]:
    present = _present(frame)
    if not present:
        return []
    table = _character_table(document)
    lines: list[str] = []
    for character in present:
        text = _wardrobe_text(table, frame, character, present)
        if text is not None:
            lines.append(f"WARDROBE LOCK: {character} wears {text}")
    return lines


def _prop_registry(document: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    raw = document.get("props")
    if not isinstance(raw, Mapping):
        return {}
    return {
        str(key): value
        for key, value in raw.items()
        if isinstance(value, Mapping) and isinstance(value.get("states"), Mapping)
    }


def _state_map(prop: Mapping[str, object]) -> dict[str, str]:
    raw = prop.get("states")
    if not isinstance(raw, Mapping):
        return {}
    return {str(key): str(value) for key, value in raw.items()}


def _resolve_state(states: Mapping[str, str], token: str) -> str | None:
    text = token.strip()
    if text in states:
        return text
    folded = text.casefold()
    by_text = [key for key, desc in states.items() if desc.casefold() == folded]
    if len(by_text) == 1:
        return by_text[0]
    contained = [
        key for key, desc in states.items() if len(folded) >= 4 and folded in desc.casefold()
    ]
    if len(contained) == 1:
        return contained[0]
    return None


def _split_declaration(value: str) -> tuple[str, str] | None:
    text = value.strip()
    if not text:
        return None
    if _ARROW not in text:
        return text, text
    start, end = text.split(_ARROW, 1)
    if not start.strip() or not end.strip() or _ARROW in end:
        return None
    return start.strip(), end.strip()


def _edges(prop: Mapping[str, object]) -> set[tuple[str, str]] | None:
    raw = prop.get("transitions")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return None
    edges: set[tuple[str, str]] = set()
    for item in raw:
        if isinstance(item, Mapping):
            edges.add((str(item.get("from") or "").strip(), str(item.get("to") or "").strip()))
    return edges


def _reachable(
    order: Sequence[str],
    edges: set[tuple[str, str]] | None,
    start: str,
    end: str,
) -> bool:
    if start == end:
        return True
    if edges is not None:
        return (start, end) in edges
    return start in order and end in order and order.index(end) >= order.index(start)


def _lock_text(prop_id: str, states: Mapping[str, str], start: str, end: str) -> str:
    label = prop_id.replace("_", " ").upper()
    if start == end:
        return f"{label} LOCK: {states.get(end, end)}"
    return f"{label} LOCK: {states.get(start, start)}; then {states.get(end, end)}"


def _prop_error(prop_id: str, earlier: str, later: str, detail: str) -> str:
    return f"prop {prop_id} on {earlier} and {later} is not reachable: {detail}"


def _assign_declared(
    prop_id: str,
    states: Mapping[str, str],
    order: Sequence[str],
    edges: set[tuple[str, str]] | None,
    declared: str,
    shot: str,
    previous: str | None,
    prior_end: str | None,
) -> tuple[str, str] | str:
    parsed = _split_declaration(declared)
    earlier = previous or shot
    if parsed is None:
        return _prop_error(prop_id, earlier, shot, f"declaration {declared!r} is invalid")
    start, end = _resolve_state(states, parsed[0]), _resolve_state(states, parsed[1])
    if start is None or end is None:
        missing = parsed[0] if start is None else parsed[1]
        return _prop_error(prop_id, earlier, shot, f"unknown state {missing}")
    # Equality is required only for an omitted prop (it carries forward). A declared
    # start may advance when that jump is reachable in state order or transitions.
    if (
        prior_end is not None
        and start != prior_end
        and not _reachable(order, edges, prior_end, start)
    ):
        detail = f"start {start} does not continue end {prior_end}"
        return _prop_error(prop_id, earlier, shot, detail)
    if not _reachable(order, edges, start, end):
        return _prop_error(prop_id, earlier, shot, f"{start} cannot move to {end}")
    return start, end


def _one_prop(
    prop_id: str,
    prop: Mapping[str, object],
    raw: object,
    shot: str,
    carried: dict[str, str],
    previous: dict[str, str],
) -> tuple[str, str] | str | None:
    states = _state_map(prop)
    if isinstance(raw, str):
        return _assign_declared(
            prop_id, states, list(states), _edges(prop), raw, shot,
            previous.get(prop_id), carried.get(prop_id),
        )
    if prop_id in carried:
        end = carried[prop_id]
        return end, end
    return None


def prop_assignments(
    document: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
) -> tuple[dict[str, list[str]], list[str]]:
    """Lock lines per frame, plus fail-closed reachability errors."""
    registry = _prop_registry(document)
    lines: dict[str, list[str]] = {}
    errors: list[str] = []
    carried: dict[str, str] = {}
    previous: dict[str, str] = {}
    prior_place: str | None = None
    if not registry:
        return lines, errors
    for index, frame in enumerate(frames, start=1):
        shot = frame_id(frame, index)
        place = frame_place(frame)
        if place and prior_place and place != prior_place:
            carried.clear()
            previous.clear()
        if place:
            prior_place = place
        declared = frame_field(frame, "prop_states")
        mapping = declared if isinstance(declared, Mapping) else {}
        shot_lines: list[str] = []
        for prop_id, prop in registry.items():
            if not prop_in_place(prop, place):
                continue
            assigned = _one_prop(prop_id, prop, mapping.get(prop_id), shot, carried, previous)
            if assigned is None:
                continue
            if isinstance(assigned, str):
                errors.append(assigned)
                continue
            start, end = assigned
            carried[prop_id] = end
            previous[prop_id] = shot
            shot_lines.append(_lock_text(prop_id, _state_map(prop), start, end))
        lines[shot] = shot_lines
    return lines, errors


def _action_text(frame: Mapping[str, object]) -> str:
    parts: list[str] = []
    for key in ("action", "prompt"):
        value = frame_field(frame, key)
        if isinstance(value, str) and value.strip():
            parts.append(value)
    nodes = frame.get("node_states")
    if isinstance(nodes, Mapping):
        parts.extend(str(value) for value in nodes.values() if str(value).strip())
    return " ".join(parts)


def _has_motion(text: str) -> bool:
    folded = text.casefold()
    return any(re.search(rf"\b{re.escape(verb)}\b", folded) for verb in _MOTION)


def is_plain_top(wardrobe: str) -> bool:
    text = wardrobe.casefold()
    if "plain" not in text and "solid" not in text:
        return False
    return not (_LOGO.search(text) and not _PLAIN_LOGO.search(text))


def _drift_for(
    entries: Sequence[Mapping[str, object]],
    provider: str,
    shot: str,
    character: str,
) -> list[dict[str, str | None]]:
    found: list[dict[str, str | None]] = []
    for entry in entries:
        providers = entry.get("providers")
        if isinstance(providers, Sequence) and not isinstance(providers, (str, bytes)):
            allowed = {str(item).casefold() for item in providers}
            if allowed and provider not in allowed:
                continue
        pattern = str(entry.get("pattern") or "plain top + motion")
        effect = str(entry.get("effect") or "known wardrobe drift")
        found.append(
            warning(
                "KNOWN_DRIFT",
                shot,
                f"{character} on {shot} matches {pattern} and can show {effect}",
                _DRIFT_RECOMMENDATION,
            )
        )
    return found


def drift_warnings(
    document: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
    provider: str,
    entries: Sequence[Mapping[str, object]],
) -> list[dict[str, str | None]]:
    found: list[dict[str, str | None]] = []
    table = _character_table(document)
    name = provider.strip().casefold()
    for index, frame in enumerate(frames, start=1):
        present = _present(frame) or []
        if not present or not _has_motion(_action_text(frame)):
            continue
        shot = frame_id(frame, index)
        for character in present:
            text = _wardrobe_text(table, frame, character, present)
            if text is not None and is_plain_top(text):
                found.extend(_drift_for(entries, name, shot, character))
    return found


def _declared(declares: Sequence[str], feature: str) -> bool:
    for item in declares:
        words = item.casefold().replace("-", " ").split()
        if feature == item.casefold().strip() or feature in words:
            return True
    return False


def _reference_id(ref: Mapping[str, object]) -> str:
    for key in ("path", "mediaObjectId"):
        value = ref.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "reference"


def _locks_for(
    document: Mapping[str, object],
    spec: Mapping[str, object],
    extra: Sequence[str],
) -> list[str]:
    own = string_list(spec.get("character_locks"))
    shared = collect_character_locks(document)
    return list(dict.fromkeys([*own, *shared, *extra]))


def _reference_hits(
    character: str,
    ref: Mapping[str, object],
    locks: Sequence[str],
) -> list[dict[str, str | None]]:
    role = str(ref.get("role") or "character").strip().casefold()
    if role != "character":
        return []
    declares = string_list(ref.get("declares"))
    if not declares:
        return []
    ident = _reference_id(ref)
    found: list[dict[str, str | None]] = []
    for lock in locks:
        feature = character_lock_feature(lock, from_lock=True)
        if feature is None or not _declared(declares, feature):
            continue
        found.append(
            warning(
                REFERENCE_CODE,
                None,
                f"character lock '{lock}' contradicts reference {ident} which declares {feature}",
                _REFERENCE_RECOMMENDATION,
                character=character,
            )
        )
    return found


def reference_warnings(
    document: Mapping[str, object],
    extra_locks: Sequence[str] = (),
) -> list[dict[str, str | None]]:
    found: list[dict[str, str | None]] = []
    for name, spec in _character_table(document).items():
        raw_refs = spec.get("references")
        if not isinstance(raw_refs, Sequence) or isinstance(raw_refs, (str, bytes)):
            continue
        locks = _locks_for(document, spec, extra_locks)
        for ref in raw_refs:
            if isinstance(ref, Mapping):
                found.extend(_reference_hits(name, ref, locks))
    return found


def reference_block(warnings: Sequence[Mapping[str, object]], enabled: bool) -> list[str]:
    if not enabled:
        return []
    messages: list[str] = []
    for item in warnings:
        if item.get("code") not in _BLOCKING_CODES:
            continue
        message = str(item.get("message") or "")
        if message and message not in messages:
            messages.append(message)
    return messages


def render_with_locks(base: str, lock_lines: Sequence[str], opted: Sequence[str]) -> str:
    return join_clauses([*lock_lines, *opted, base])
