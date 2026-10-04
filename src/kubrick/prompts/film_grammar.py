#!/usr/bin/env python3
"""Expand camera and cut terms, and warn on unknown or conflicting film grammar."""
from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from kubrick.paths import SKILL_ROOT
from kubrick.plan.continuity_locks import frame_field, frame_id, warning
from kubrick.plan.planning_fields import KNOWN_FRAME_KEYS
from kubrick.runtime.value_coerce import as_float

_ROOT = SKILL_ROOT
_PATH = _ROOT / "assets" / "grammar" / "film_grammar.yaml"
_SCHEMA = _ROOT / "schemas" / "film-grammar.schema.json"
_SPLIT = re.compile(r"\s*(?:,|;|\+|\band\b)\s*")
_NEGATION = re.compile(r"\b(?:no|not|non|never|without|avoid|dont)\b")
_FIELD_ID_PART = {"focus": "focus"}  # camera.focus may only resolve focus entries
_CHAIN_CONFLICT = "chain_from_start_frame"
CAMERA_KEYS = ("size", "angle", "lens_mm", "move", "focus")
_TEXT_FIELDS = (
    ("size", "shot_size", "framing"),
    ("angle", "angle", "framing"),
    ("move", "move", "movement"),
    ("focus", "move", "movement"),
)
_DEFAULT_CAMERA = {
    "framing": "evidenced framing",
    "movement": "static unless evidenced",
}
WarningRow = dict[str, str | None]


@dataclass(frozen=True)
class Library:
    document: dict[str, object]
    entries: tuple[Mapping[str, object], ...]
    index: Mapping[tuple[str, str], Mapping[str, object]]


@dataclass(frozen=True)
class Resolved:
    """Prompt phrases and warnings for one frame's camera and cut."""

    framing: tuple[str, ...]
    movement: tuple[str, ...]
    cuts: tuple[str, ...]
    warnings: tuple[WarningRow, ...]


_CACHE: Library | None = None


def _norm(text: str) -> str:
    cleaned = text.casefold().replace("_", " ").replace("-", " ")
    cleaned = cleaned.replace("'", "").replace("’", "")
    return " ".join(cleaned.split())


def _validate_schema(loaded: object, schema: object) -> None:
    from kubrick.runtime.runtime_deps import require_module

    module = require_module("jsonschema")
    try:
        getattr(module, "validate")(loaded, schema)
    except Exception as exc:
        if exc.__class__.__name__ != "ValidationError":
            raise
        detail = getattr(exc, "message", None)
        text = detail if isinstance(detail, str) and detail else str(exc)
        raise ValueError(f"film grammar schema invalid: {text}") from exc


def _entry_list(loaded: Mapping[str, object]) -> list[Mapping[str, object]]:
    raw = loaded.get("entries")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ValueError("film grammar entries must be a list")
    entries: list[Mapping[str, object]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise ValueError("film grammar entry must be an object")
        entries.append(item)
    return entries


def _require_unique(entries: Sequence[Mapping[str, object]]) -> None:
    seen: set[str] = set()
    for entry in entries:
        ident = entry.get("id")
        if not isinstance(ident, str) or not ident.strip():
            raise ValueError("film grammar entry is missing an id")
        key = ident.strip()
        if key in seen:
            raise ValueError(f"duplicate film grammar id {key}")
        seen.add(key)


def _alias_names(entry: Mapping[str, object]) -> list[str]:
    names = [str(entry.get("id") or "")]
    raw = entry.get("aliases")
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        names.extend(str(item) for item in raw)
    return [name for name in names if name.strip()]


def _build_index(
    entries: Sequence[Mapping[str, object]],
) -> dict[tuple[str, str], Mapping[str, object]]:
    index: dict[tuple[str, str], Mapping[str, object]] = {}
    for entry in entries:
        category = str(entry.get("category") or "")
        ident = str(entry.get("id") or "")
        for name in _alias_names(entry):
            key = (category, _norm(name))
            prior = index.get(key)
            if prior is not None and str(prior.get("id") or "") != ident:
                raise ValueError(
                    f"film grammar alias {name!r} is used by {prior.get('id')} and {ident}"
                )
            index[key] = entry
    return index


def _band_bounds(entry: Mapping[str, object]) -> tuple[float, float] | None:
    low = entry.get("lens_mm_min")
    if isinstance(low, bool) or not isinstance(low, (int, float)):
        return None
    high = entry.get("lens_mm_max")
    if high is None:
        return float(low), float("inf")
    if isinstance(high, bool) or not isinstance(high, (int, float)):
        raise ValueError(f"lens band {entry.get('id')} has a non-numeric lens_mm_max")
    upper = float(high)
    if upper < float(low):
        raise ValueError(f"lens band {entry.get('id')} ends before it starts")
    return float(low), upper


def _check_bands(entries: Sequence[Mapping[str, object]]) -> None:
    ranges: list[tuple[float, float, str]] = []
    for entry in entries:
        if str(entry.get("category") or "") != "lens_band":
            continue
        bounds = _band_bounds(entry)
        if bounds is None:
            continue
        ranges.append((bounds[0], bounds[1], str(entry.get("id") or "")))
    ranges.sort()
    for earlier, later in zip(ranges, ranges[1:]):
        if later[0] <= earlier[1]:
            raise ValueError(f"lens bands {earlier[2]} and {later[2]} overlap")


def load_grammar(path: Path | None = None) -> Library:
    """Validate the registry. An invalid file raises ValueError."""
    global _CACHE
    if path is None and _CACHE is not None:
        return _CACHE
    from kubrick.runtime.runtime_deps import yaml_load

    target = path or _PATH
    loaded = yaml_load(target.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("film grammar must be an object")
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    _validate_schema(loaded, schema)
    entries = _entry_list(loaded)
    _require_unique(entries)
    library = Library(
        document={str(key): value for key, value in loaded.items()},
        entries=tuple(entries),
        index=_build_index(entries),
    )
    _check_bands(library.entries)
    if path is None:
        _CACHE = library
    return library


def _text_value(value: object) -> str | list[str] | None:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, list):
        items = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        if items and len(items) == len(value):
            return items
    return None


def _lens_number(value: object) -> int | float | None:
    parsed = as_float(value)
    if parsed is None or parsed <= 0:
        return None
    return int(parsed) if float(parsed).is_integer() else float(parsed)


def carried_camera(value: object) -> dict[str, object] | None:
    """Camera object safe for the storyboard schema. Unknown subkeys are omitted."""
    if not isinstance(value, Mapping):
        return None
    kept: dict[str, object] = {}
    for key in ("size", "angle", "move", "focus"):
        if key not in value or value.get(key) is None:
            continue
        text = _text_value(value.get(key))
        if text is not None:
            kept[key] = text
    if "lens_mm" in value and value.get("lens_mm") is not None:
        millimetres = _lens_number(value.get("lens_mm"))
        if millimetres is not None:
            kept["lens_mm"] = millimetres
    return kept or None


def _mappings(frames: object) -> list[Mapping[str, object]]:
    if not isinstance(frames, Sequence) or isinstance(frames, (str, bytes)):
        return []
    return [frame for frame in frames if isinstance(frame, Mapping)]


def _parts(value: object) -> list[str] | None:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        return [part.strip() for part in _SPLIT.split(text) if part.strip()]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        parts: list[str] = []
        for item in value:
            if not isinstance(item, str):
                return None
            if item.strip():
                parts.append(item.strip())
        return parts
    return None


def _match(
    text: str,
    category: str,
    index: Mapping[tuple[str, str], Mapping[str, object]],
    field: str = "",
) -> Mapping[str, object] | None:
    norm = _norm(text)
    if _NEGATION.search(norm):
        return None  # "no push-in" must not resolve to push-in
    part = _FIELD_ID_PART.get(field, "")
    exact = index.get((category, norm))
    if exact is not None and part in str(exact.get("id", "")):
        return exact
    best: Mapping[str, object] | None = None
    best_len = 0
    padded = f" {norm} "
    for (cat, alias), entry in index.items():
        if cat != category or not alias or len(alias) <= best_len:
            continue
        if part not in str(entry.get("id", "")):
            continue
        if f" {alias} " in padded:
            best = entry
            best_len = len(alias)
    return best


def _term_warning(shot: str, field: str, value: object) -> WarningRow:
    negated = "negated " if _NEGATION.search(_norm(str(value))) else ""
    return warning(
        "UNKNOWN_GRAMMAR_TERM",
        shot,
        f"unknown {negated}{field} term {str(value).strip()!r}",
        "use an id from assets/grammar/film_grammar.yaml; omit a move instead of negating it",
    )


def _phrases_for(
    value: object,
    category: str,
    library: Library,
    shot: str,
    field: str,
) -> tuple[list[str], list[Mapping[str, object]], list[WarningRow]]:
    parts = _parts(value)
    if parts is None:
        return [], [], [_term_warning(shot, field, value)]
    phrases: list[str] = []
    matched: list[Mapping[str, object]] = []
    warns: list[WarningRow] = []
    for part in parts:
        entry = _match(part, category, library.index, field)
        if entry is None:
            warns.append(_term_warning(shot, field, part))
            continue
        phrase = str(entry.get("prompt_phrase") or "").strip()
        if phrase and phrase not in phrases:
            phrases.append(phrase)
        matched.append(entry)
    return phrases, matched, warns


def _band_for(millimetres: float, library: Library) -> Mapping[str, object] | None:
    found = [
        entry for entry in library.entries
        if str(entry.get("category") or "") == "lens_band"
        and (bounds := _band_bounds(entry)) is not None and bounds[0] <= millimetres <= bounds[1]
    ]
    return found[0] if len(found) == 1 else None


def _lens_clauses(
    value: object, library: Library, shot: str,
) -> tuple[list[str], list[WarningRow]]:
    millimetres = _lens_number(value)
    if millimetres is None:
        return [], [warning(
            "UNKNOWN_GRAMMAR_TERM",
            shot,
            f"lens_mm {value!r} is not a focal length",
            "set lens_mm to a number of millimetres",
        )]
    shown = str(int(millimetres)) if float(millimetres).is_integer() else str(millimetres)
    phrases = [f"{shown} mm lens"]
    band = _band_for(float(millimetres), library)
    if band is None:
        return phrases, [warning(
            "LENS_BAND_UNMAPPED",
            shot,
            f"lens {shown} mm does not fall in a known lens band",
            "choose a focal length inside a declared lens band",
        )]
    phrase = str(band.get("prompt_phrase") or "").strip()
    if phrase:
        phrases.append(phrase)
    return phrases, []

def _chains(frame: Mapping[str, object]) -> bool:
    raw = frame_field(frame, "join")
    if not isinstance(raw, Mapping):
        return False
    source = raw.get("chain_from")
    return isinstance(source, str) and bool(source.strip())

def _conflict_ids(entries: Sequence[Mapping[str, object]]) -> list[str]:
    names: list[str] = []
    for entry in entries:
        raw = entry.get("conflicts")
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            continue
        if _CHAIN_CONFLICT not in {str(item) for item in raw}:
            continue
        ident = str(entry.get("id") or "move")
        if ident not in names:
            names.append(ident)
    return names


_MOVE_MODIFIERS = frozenset({"handheld", "stabilised-float"})


def _chain_warning(
    frame: Mapping[str, object],
    entries: Sequence[Mapping[str, object]],
    shot: str,
) -> WarningRow | None:
    primary = [entry for entry in entries if str(entry.get("id") or "") not in _MOVE_MODIFIERS]
    if len(primary) > 1:
        listed = ", ".join(str(entry.get("id") or "move") for entry in primary)
        return warning(
            "MOVE_CHAIN_CONFLICT", shot,
            f"{listed} on {shot} names more than one primary camera move",
            "keep one camera move",
        )
    if not _chains(frame):
        return None
    names = _conflict_ids(entries)
    if not names:
        return None
    listed = ", ".join(names)
    return warning(
        "MOVE_CHAIN_CONFLICT",
        shot,
        f"{listed} on {shot} chains from a start frame; a snap or whip cannot ride that chain",
        "cut to the new angle, or remove the snap or whip move",
    )


def _resolve(frame: Mapping[str, object], shot: str) -> Resolved:
    library = load_grammar()
    framing: list[str] = []
    movement: list[str] = []
    cuts: list[str] = []
    warns: list[WarningRow] = []
    camera = frame_field(frame, "camera")
    if isinstance(camera, Mapping):
        move_entries: list[Mapping[str, object]] = []
        for field, category, bucket_name in _TEXT_FIELDS:
            if field not in camera or camera.get(field) is None:
                continue
            phrases, matched, field_warns = _phrases_for(
                camera.get(field), category, library, shot, field,
            )
            warns.extend(field_warns)
            if bucket_name == "framing":
                framing.extend(phrases)
            else:
                movement.extend(phrases)
            if field == "move":
                move_entries = matched
        if "lens_mm" in camera and camera.get("lens_mm") is not None:
            lens_phrases, lens_warns = _lens_clauses(camera.get("lens_mm"), library, shot)
            framing.extend(lens_phrases)
            warns.extend(lens_warns)
        chain = _chain_warning(frame, move_entries, shot)
        if chain is not None:
            warns.append(chain)
    cut = frame_field(frame, "cut")
    if cut is not None:
        phrases, _matched, field_warns = _phrases_for(cut, "edit", library, shot, "cut")
        cuts.extend(phrases)
        warns.extend(field_warns)
    return Resolved(tuple(framing), tuple(movement), tuple(cuts), tuple(warns))


def _has_direction(frame: Mapping[str, object]) -> bool:
    return frame_field(frame, "camera") is not None or frame_field(frame, "cut") is not None


def _unknown_rows(frame: Mapping[str, object], shot: str) -> list[WarningRow]:
    found = [
        warning(
            "UNKNOWN_FIELD", shot, f"unknown frame field {str(key)!r} was not copied",
            "remove the field or add it to the storyboard frame schema",
        )
        for key in frame if str(key) not in KNOWN_FRAME_KEYS
    ]
    camera = frame_field(frame, "camera")
    if camera is None:
        return found
    if not isinstance(camera, Mapping):
        found.append(warning(
            "UNKNOWN_FIELD", shot, "camera must be an object",
            "set camera to size, angle, lens_mm, move, and focus",
        ))
        return found
    found.extend(
        warning(
            "UNKNOWN_FIELD", shot, f"unknown camera field {str(key)!r} was not copied",
            "use size, angle, lens_mm, move, or focus",
        )
        for key in camera if str(key) not in CAMERA_KEYS
    )
    return found


def frame_prep_warnings(frames: object) -> list[WarningRow]:
    """Structured warnings for unknown keys, unknown terms, and chain conflicts."""
    found: list[WarningRow] = []
    directed: list[tuple[str, Mapping[str, object]]] = []
    for index, frame in enumerate(_mappings(frames), start=1):
        shot = frame_id(frame, index)
        found.extend(_unknown_rows(frame, shot))
        if _has_direction(frame):
            directed.append((shot, frame))
    for shot, frame in directed:
        found.extend(_resolve(frame, shot).warnings)
    return found


def storyboard_warning_lines(frames: object) -> list[str]:
    """String warnings for storyboard validation.warnings."""
    return [
        f"{item.get('code') or 'WARNING'}: {item.get('message') or ''}"
        for item in frame_prep_warnings(frames)
    ]


def direction_clauses(frame: Mapping[str, object]) -> list[str]:
    """Prompt phrases for known camera and cut terms. Empty when neither is set."""
    if not _has_direction(frame):
        return []
    raw = frame.get("frame_id")
    shot = raw.strip() if isinstance(raw, str) and raw.strip() else "frame"
    resolved = _resolve(frame, shot)
    return [*resolved.framing, *resolved.movement, *resolved.cuts]


def shot_camera(frame: Mapping[str, object]) -> dict[str, str]:
    """Shot-contract camera. Frames without camera keep the evidenced defaults."""
    if frame_field(frame, "camera") is None:
        return dict(_DEFAULT_CAMERA)
    raw = frame.get("frame_id")
    shot = raw.strip() if isinstance(raw, str) and raw.strip() else "frame"
    resolved = _resolve(frame, shot)
    framing = "; ".join(resolved.framing) or _DEFAULT_CAMERA["framing"]
    movement = "; ".join(resolved.movement) or _DEFAULT_CAMERA["movement"]
    return {"framing": framing, "movement": movement}
