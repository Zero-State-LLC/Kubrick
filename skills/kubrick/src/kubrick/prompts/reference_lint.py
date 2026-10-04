#!/usr/bin/env python3
"""Reference scope, location locks, counts, and cast. Issues #33 and #34.

``scope`` without ``applies_to`` is author metadata. A reference is scoped only
when ``applies_to`` names exactly one id who is on screen. ``cast`` is read
only when the frame has that key. ``characters: []`` alone does not drop
identity lines.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from kubrick.gates.hold_scope import frame_view, view_clauses
from kubrick.plan.brief_constraints import negative_form, string_list
from kubrick.plan.continuity_locks import frame_field, frame_id, wardrobe_lines, warning
from kubrick.prompts.prompt_text import positive_prompt

_COUNT_WORDS = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
)
_WORD_INDEX = {word: index for index, word in enumerate(_COUNT_WORDS)}
_NO_LOCK = re.compile(r"^(?:no|without)\s+(?:a\s+|an\s+|the\s+)?(.+)$", re.IGNORECASE)
_COUNT_X = re.compile(r"^(.+?)\s+x\s*(\d+)$", re.IGNORECASE)
_COUNT_LEAD = re.compile(
    r"^(\d+|zero|one|two|three|four|five|six|seven|eight|nine|ten)\s+(.+)$",
    re.IGNORECASE,
)
_BLEED = (
    "scope the reference with applies_to naming one on-screen character, "
    "or drop it from this frame"
)
_LOCATION = "edit the location reference, drop the lock, or accept the drift"


def _norm(text: str) -> str:
    return " ".join(text.casefold().split())


def _table(document: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    raw = document.get("characters")
    if not isinstance(raw, Mapping):
        return {}
    return {str(key): value for key, value in raw.items() if isinstance(value, Mapping)}


def screen_mode(frame: Mapping[str, object]) -> tuple[str, list[str]]:
    """``cast`` when that key is present, else ``characters``, else ``absent``."""
    cast = frame_field(frame, "cast")
    if isinstance(cast, Sequence) and not isinstance(cast, (str, bytes)):
        return "cast", [str(item).strip() for item in cast if str(item).strip()]
    characters = frame_field(frame, "characters")
    if isinstance(characters, Sequence) and not isinstance(characters, (str, bytes)):
        return "characters", [str(item).strip() for item in characters if str(item).strip()]
    return "absent", []


def _owners(document: Mapping[str, object]) -> dict[str, set[str]]:
    owned: dict[str, set[str]] = {}
    for name, spec in _table(document).items():
        for lock in string_list(spec.get("character_locks")):
            owned.setdefault(_norm(lock), set()).add(name)
    return owned


def _kept_locks(
    document: Mapping[str, object],
    cleaned: Sequence[str],
    present: Sequence[str],
) -> list[str]:
    owned = _owners(document)
    kept: list[str] = []
    for lock in cleaned:
        owners = owned.get(_norm(lock), set())
        if not owners or owners & set(present):
            kept.append(lock)
    return kept


def frame_locks(
    document: Mapping[str, object],
    frame: Mapping[str, object],
    locks: Sequence[object],
) -> list[str]:
    """Identity locks for this frame.

    ``cast: []`` drops them. ``characters: []`` does not, because an absent
    cast list is the only explicit empty frame.
    """
    mode, present = screen_mode(frame)
    cleaned = [str(item).strip() for item in locks if str(item).strip()]
    if mode != "cast":
        if mode == "characters" and present:
            return _kept_locks(document, cleaned, present)
        return cleaned
    if not present:
        return []
    return _kept_locks(document, cleaned, present)


def _form(text: str) -> str:
    formed = negative_form(text)
    return _norm(formed if formed is not None else text)


def identity_inputs(
    document: Mapping[str, object],
    frame: Mapping[str, object],
    locks: Sequence[object],
    negatives: Sequence[object],
) -> tuple[list[str], list[str]]:
    """Locks and negatives after the cast filter. Absent cast keeps both."""
    kept = frame_locks(document, frame, locks)
    mode, _present = screen_mode(frame)
    if mode == "absent":
        return kept, [str(item) for item in negatives]
    kept_forms = {_form(item) for item in kept}
    all_forms = {_form(str(item)) for item in locks}
    filtered: list[str] = []
    for item in negatives:
        text = str(item)
        if _form(text) in all_forms and _form(text) not in kept_forms:
            continue
        filtered.append(text)
    return kept, filtered


def bound_positive(
    source: str,
    extras: Sequence[object],
    negatives: Sequence[object],
    locks: Sequence[object],
    document: Mapping[str, object],
    frame: Mapping[str, object],
) -> str:
    kept_locks, kept_negatives = identity_inputs(document, frame, locks, negatives)
    return positive_prompt(source, extras, kept_negatives, kept_locks)


def count_phrase(name: str, count: int) -> str:
    word = _COUNT_WORDS[count] if 0 <= count <= 10 else str(count)
    label = name if count == 1 or name.endswith("s") else f"{name}s"
    return f"exactly {word} {label}"


def _int_map(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    found: dict[str, int] = {}
    for key, raw in value.items():
        if isinstance(raw, bool) or not isinstance(raw, int):
            continue
        found[str(key)] = raw
    return found


def merged_counts(document: Mapping[str, object], frame: Mapping[str, object]) -> dict[str, int]:
    counts = _int_map(document.get("counts"))
    counts.update(_int_map(frame_field(frame, "counts")))
    return counts


def _count_lines(document: Mapping[str, object], frame: Mapping[str, object]) -> list[str]:
    return [count_phrase(name, count) for name, count in merged_counts(document, frame).items()]


def _ref_id(ref: Mapping[str, object]) -> str:
    for key in ("path", "mediaObjectId"):
        value = ref.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "reference"


def _ref_ids(ref: Mapping[str, object]) -> set[str]:
    found: set[str] = set()
    for key in ("path", "mediaObjectId"):
        value = ref.get(key)
        if isinstance(value, str) and value.strip():
            found.add(value.strip())
    return found


def reference_attached(
    frame: Mapping[str, object],
    ref: Mapping[str, object],
    owner: str,
) -> bool:
    """Listed on the frame, or implicit when the frame names no references."""
    images = frame_field(frame, "reference_images")
    if isinstance(images, Sequence) and not isinstance(images, (str, bytes)):
        names = {str(item).strip() for item in images if str(item).strip()}
        if names:
            return bool(_ref_ids(ref) & names)
    _mode, present = screen_mode(frame)
    return owner in present


def _character_refs(spec: Mapping[str, object]) -> list[Mapping[str, object]]:
    raw = spec.get("references")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    refs: list[Mapping[str, object]] = []
    for ref in raw:
        if not isinstance(ref, Mapping):
            continue
        role = str(ref.get("role") or "character").strip().casefold()
        if role == "character":
            refs.append(ref)
    return refs


def _scoped_to_one(ref: Mapping[str, object], present: Sequence[str]) -> str | None:
    applies = string_list(ref.get("applies_to"))
    if len(applies) == 1 and applies[0] in present:
        return applies[0]
    return None


def _other_text(others: Sequence[str]) -> str:
    if not others:
        return "anyone else"
    return " or ".join(f"the {name}" for name in others)


def _binding_lines(document: Mapping[str, object], frame: Mapping[str, object]) -> list[str]:
    _mode, present = screen_mode(frame)
    lines: list[str] = []
    for owner, spec in _table(document).items():
        for ref in _character_refs(spec):
            if not reference_attached(frame, ref, owner):
                continue
            target = _scoped_to_one(ref, present)
            if target is None:
                continue
            others = [name for name in present if name != target]
            lines.append(
                f"reference {_ref_id(ref)} defines {target} only; ignore its background; "
                f"it does not apply to {_other_text(others)}"
            )
    return lines


def _bleed_one(
    frame: Mapping[str, object],
    shot: str,
    owner: str,
    ref: Mapping[str, object],
    present: Sequence[str],
) -> dict[str, str | None] | None:
    if len(present) < 2 or not reference_attached(frame, ref, owner):
        return None
    if _scoped_to_one(ref, present) is not None:
        return None
    names = ", ".join(present)
    return warning(
        "REFERENCE_BLEED_RISK",
        shot,
        f"frame {shot} reference {_ref_id(ref)} can bleed onto {names}",
        _BLEED,
    )


def bleed_warnings(
    document: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
) -> list[dict[str, str | None]]:
    found: list[dict[str, str | None]] = []
    for index, frame in enumerate(frames, start=1):
        _mode, present = screen_mode(frame)
        shot = frame_id(frame, index)
        for owner, spec in _table(document).items():
            for ref in _character_refs(spec):
                item = _bleed_one(frame, shot, owner, ref, present)
                if item is not None:
                    found.append(item)
    return found


def declares_feature(declares: Sequence[str], feature: str) -> bool:
    folded = feature.casefold().strip()
    for item in declares:
        words = item.casefold().replace("-", " ").split()
        if folded == item.casefold().strip() or folded in words:
            return True
    return False


def _count_declare(text: str) -> tuple[str, int] | None:
    match = _COUNT_X.match(text.strip())
    if match is not None:
        return match.group(1).strip(), int(match.group(2))
    lead = _COUNT_LEAD.match(text.strip())
    if lead is None:
        return None
    raw_count = lead.group(1).casefold()
    count = _WORD_INDEX[raw_count] if raw_count in _WORD_INDEX else int(raw_count)
    return lead.group(2).strip(), count


def _count_key(name: str, counts: Mapping[str, int]) -> str | None:
    folded = {key.casefold(): key for key in counts}
    token = name.casefold()
    if token in folded:
        return folded[token]
    if token.endswith("s") and token[:-1] in folded:
        return folded[token[:-1]]
    return None


def _location_refs(location: Mapping[str, object]) -> list[Mapping[str, object]]:
    raw = location.get("references")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    return [item for item in raw if isinstance(item, Mapping)]


def _feature_hit(declare: str, locks: Sequence[str]) -> str | None:
    for lock in locks:
        match = _NO_LOCK.match(lock.strip())
        if match is not None and _norm(match.group(1)) == _norm(declare):
            return lock
    return None


def _contradiction(
    ident: str,
    declare: str,
    locks: Sequence[str],
    counts: Mapping[str, int],
) -> dict[str, str | None] | None:
    parsed = _count_declare(declare)
    if parsed is not None:
        folded_key = _count_key(parsed[0], counts)
        if folded_key is not None and counts[folded_key] != parsed[1]:
            return warning(
                "LOCATION_REFERENCE_CONTRADICTION",
                None,
                (
                    f"location reference {ident} declares '{declare}' "
                    f"against counts {folded_key}: {counts[folded_key]}"
                ),
                _LOCATION,
            )
        if folded_key is not None:
            return None
    hit = _feature_hit(declare, locks)
    if hit is None:
        return None
    return warning(
        "LOCATION_REFERENCE_CONTRADICTION",
        None,
        f"location reference {ident} declares '{declare}' against lock '{hit}'",
        _LOCATION,
    )


def location_warnings(document: Mapping[str, object]) -> list[dict[str, str | None]]:
    location = document.get("location")
    if not isinstance(location, Mapping):
        return []
    locks = string_list(location.get("locks"))
    counts = _int_map(document.get("counts"))
    found: list[dict[str, str | None]] = []
    for ref in _location_refs(location):
        ident = _ref_id(ref)
        for declare in string_list(ref.get("declares")):
            item = _contradiction(ident, declare, locks, counts)
            if item is not None:
                found.append(item)
    return found


def wardrobe_lines_for(document: Mapping[str, object], frame: Mapping[str, object]) -> list[str]:
    mode, present = screen_mode(frame)
    if mode == "cast" and not present:
        return []
    if mode != "cast":
        return wardrobe_lines(document, frame)
    limited = dict(frame)
    limited["characters"] = present
    return wardrobe_lines(document, limited)


def prompt_lines(
    document: Mapping[str, object],
    frame: Mapping[str, object],
    prop_lines: Sequence[str],
) -> list[str]:
    """Lock lines prepended to one frame. Empty cast drops wardrobe.

    A POV frame does not take wardrobe or asymmetry lines.
    """
    mode, present = screen_mode(frame)
    pov = frame_view(frame) == "pov"
    lines: list[str] = []
    if mode == "cast" and not present:
        lines.append("nobody is in frame")
    elif not pov:
        lines.extend(wardrobe_lines_for(document, frame))
    lines.extend(prop_lines)
    lines.extend(_count_lines(document, frame))
    lines.extend(_binding_lines(document, frame))
    if not pov:
        from kubrick.prompts.audio_screen_locks import asymmetry_lines

        lines.extend(asymmetry_lines(document, frame))
    lines.extend(view_clauses(document, frame))
    return lines


def extra_warnings(
    document: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
    provider: str,
) -> list[dict[str, str | None]]:
    """Bleed, location, start-frame, and negative-only warnings."""
    from kubrick.gates.start_frame_gate import start_warnings
    from kubrick.plan.lock_carriers import negative_only_warnings

    return [
        *bleed_warnings(document, frames),
        *location_warnings(document),
        *start_warnings(frames, provider),
        *negative_only_warnings(document, frames, provider),
    ]
