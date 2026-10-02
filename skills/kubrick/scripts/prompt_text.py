#!/usr/bin/env python3
"""Deterministic prompt text for provider packets.

General negatives stay out of positive prompt text. Character-lock negatives
are restated as positive identity constraints. Clause de-duplication does not
rewrite an already stored source prompt: callers dedupe when they build the
stored prompt, and ``append_unique`` only appends unseen clauses.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

_BLANK = {"", "none", "not_computable"}
_OBSERVED_ID = re.compile(r"^observed_\d+$")
_LOCK_PREFIX = re.compile(
    r"^(?:character-lock|identity-lock|identity)\s*:\s*",
    re.IGNORECASE,
)
_NO_PREFIX = re.compile(r"^(?:no|without)\s+(.+)$", re.IGNORECASE)
_CLAUSE_SPLIT = re.compile(r"\s*;\s*")

FIELD_LABELS = {"motif_ownership": "motif ownership"}

# What is present, then an explicit absence tied to the locked character.
_FEATURES: dict[str, tuple[str, str]] = {
    "nose": (
        "smooth featureless skin where a nose would be",
        "the locked character's face has no nose",
    ),
    "eye": (
        "smooth uninterrupted skin where an eye would be",
        "the locked character's face has no eye",
    ),
    "eyes": (
        "smooth uninterrupted skin where eyes would be",
        "the locked character's face has no eyes",
    ),
    "mouth": (
        "smooth uninterrupted skin where a mouth would be",
        "the locked character's face has no mouth",
    ),
    "ear": (
        "smooth uninterrupted skin where an ear would be",
        "the locked character's head has no ear",
    ),
    "ears": (
        "smooth uninterrupted skin where ears would be",
        "the locked character's head has no ears",
    ),
    "hair": (
        "a hairless scalp",
        "the locked character has no hair",
    ),
    "lip": (
        "smooth skin where a lip would be",
        "the locked character's face has no lip",
    ),
    "lips": (
        "smooth skin where lips would be",
        "the locked character's face has no lips",
    ),
    "teeth": (
        "a closed featureless mouth line",
        "the locked character's face has no teeth",
    ),
    "eyebrow": (
        "smooth skin where an eyebrow would be",
        "the locked character's face has no eyebrow",
    ),
    "eyebrows": (
        "smooth skin where eyebrows would be",
        "the locked character's face has no eyebrows",
    ),
}

_STATE_FIELDS = (
    "node_states",
    "motif_ownership",
    "object_states",
    "light_states",
    "material_states",
)
_CONTINUITY_FIELDS = (
    "motif_ownership",
    "object_states",
    "light_states",
    "material_states",
)


def field_label(field: str) -> str:
    """Human label for a frame field. Never strips a trailing letter."""
    if field in FIELD_LABELS:
        return FIELD_LABELS[field]
    if field.endswith("_states"):
        stem = field[: -len("_states")].replace("_", " ")
        return f"{stem} state"
    return field.replace("_", " ")


def is_blank(value: object) -> bool:
    if value is None:
        return True
    return str(value).strip().casefold() in _BLANK


def split_clauses(text: str) -> list[str]:
    return [part.strip() for part in _CLAUSE_SPLIT.split(text) if part.strip()]


def dedupe_clauses(clauses: Sequence[object]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for clause in clauses:
        for part in split_clauses(str(clause)):
            key = part.casefold()
            if key in seen:
                continue
            seen.add(key)
            ordered.append(part)
    return ordered


def join_clauses(clauses: Sequence[object]) -> str:
    return "; ".join(dedupe_clauses(clauses))


def append_unique(base: str, extras: Sequence[object]) -> str:
    """Keep ``base`` intact and append clauses that are not already present."""
    text = base.strip()
    seen = {part.casefold() for part in split_clauses(text)}
    added: list[str] = []
    for clause in extras:
        for part in split_clauses(str(clause)):
            key = part.casefold()
            if key in seen:
                continue
            seen.add(key)
            added.append(part)
    if not added:
        return text
    if not text:
        return "; ".join(added)
    return f"{text}; " + "; ".join(added)


def node_labels(nodes: Sequence[Mapping[str, object]]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for node in nodes:
        node_id = node.get("id")
        form = node.get("observed_form")
        if node_id is None or is_blank(form):
            continue
        labels[str(node_id)] = str(form).strip()
    return labels


def render_name(key: object, labels: Mapping[str, str]) -> str | None:
    """Render a state key. Unlabeled ``observed_N`` ids are omitted."""
    name = str(key).strip()
    if not name or is_blank(name):
        return None
    if name in labels:
        return labels[name]
    if _OBSERVED_ID.match(name):
        return None
    return name


def mapping_clauses(
    field: str,
    mapping: Mapping[object, object],
    labels: Mapping[str, str],
) -> list[str]:
    label = field_label(field)
    clauses: list[str] = []
    for key in sorted(mapping, key=str):
        value = mapping[key]
        if is_blank(value):
            continue
        rendered = render_name(key, labels)
        if rendered is None:
            continue
        clauses.append(f"{label} {rendered}: {value}")
    return clauses


def _string_items(value: object, prefix: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [f"{prefix}{item}" for item in value if not is_blank(item)]


def frame_state_clauses(frame: Mapping[str, object], labels: Mapping[str, str]) -> list[str]:
    clauses: list[str] = []
    for field in _STATE_FIELDS:
        raw = frame.get(field) or {}
        if isinstance(raw, Mapping):
            clauses.extend(mapping_clauses(field, raw, labels))
    clauses.extend(_string_items(frame.get("residue"), "residue persists: "))
    clauses.extend(_string_items(frame.get("residue_add"), "residue persists: "))
    clauses.extend(_string_items(frame.get("required_mutations"), "required mutation: "))
    clauses.extend(
        _string_items(frame.get("convergence_sites"), "convergence remains observable at ")
    )
    return dedupe_clauses(clauses)


def render_frame_prompt(
    shared: Sequence[object],
    frame: Mapping[str, object],
    labels: Mapping[str, str],
) -> str:
    return join_clauses([*shared, *frame_state_clauses(frame, labels)])


def continuity_clauses(
    graph_id: str,
    previous: Mapping[str, object],
    labels: Mapping[str, str],
) -> list[str]:
    clauses = [f"preserve graph identity {graph_id}"]
    for field in _CONTINUITY_FIELDS:
        raw = previous.get(field) or {}
        if not isinstance(raw, Mapping):
            continue
        label = field_label(field)
        for key in sorted(raw, key=str):
            value = raw[key]
            if is_blank(value):
                continue
            rendered = render_name(key, labels)
            if rendered is None:
                continue
            clauses.append(f"preserve prior {label} {rendered}: {value}")
    clauses.extend(_string_items(previous.get("residue"), "do not remove residue: "))
    return clauses


def node_state_constraints(frame: Mapping[str, object], labels: Mapping[str, str]) -> list[str]:
    raw = frame.get("node_states") or {}
    if not isinstance(raw, Mapping):
        return []
    clauses: list[str] = []
    for key in sorted(raw, key=str):
        value = raw[key]
        if is_blank(value):
            continue
        rendered = render_name(key, labels)
        if rendered is None:
            continue
        clauses.append(f"node state {rendered}: {value}")
    return clauses


def character_lock_positive(
    negative: str,
    *,
    from_lock: bool = False,
) -> tuple[str, str] | str | None:
    """Positive wording for one lock.

    Lexicon features keep their fixed pair. An explicit character-lock prefix,
    or an item that came from ``character_locks``, still produces a positive
    constraint when the feature is outside that lexicon. The generic form uses
    only the named feature and does not invent anatomy. A lock that is not a
    negation is copied as written. An unprefixed general negative that is not
    a lexicon hit stays negative-only.
    """
    raw = negative.strip()
    text = _LOCK_PREFIX.sub("", raw, count=1)
    explicit = from_lock or text != raw
    match = _NO_PREFIX.match(text)
    if match is None:
        if explicit and text and not is_blank(text):
            return text
        return None
    rest = match.group(1).strip()
    key = rest.casefold()
    if key in _FEATURES:
        return _FEATURES[key]
    first = key.split(" ", 1)[0]
    if first in _FEATURES:
        return _FEATURES[first]
    if not explicit:
        return None
    feature = rest.casefold()
    return (
        f"the locked character has no {feature}; "
        f"the {feature} stays absent in every frame"
    )


def _lock_parts(found: tuple[str, str] | str) -> list[str]:
    if isinstance(found, str):
        return [found]
    return [found[0], found[1]]


def character_lock_clauses(
    negatives: Sequence[object],
    *,
    from_lock: bool = False,
) -> list[str]:
    clauses: list[str] = []
    for negative in negatives:
        found = character_lock_positive(str(negative), from_lock=from_lock)
        if found is None:
            continue
        clauses.extend(_lock_parts(found))
    return dedupe_clauses(clauses)


def positive_prompt(
    source: str,
    extras: Sequence[object],
    negatives: Sequence[object],
    locks: Sequence[object] = (),
) -> str:
    """Positive prompt. General negatives are not copied into the text."""
    clauses = character_lock_clauses(negatives)
    if locks:
        clauses = dedupe_clauses([*clauses, *character_lock_clauses(locks, from_lock=True)])
    return append_unique(append_unique(source, extras), clauses)
