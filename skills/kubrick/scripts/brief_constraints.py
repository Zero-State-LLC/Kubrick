#!/usr/bin/env python3
"""Brief character locks and aspect ratio carried into provider packets.

``character_locks`` is an optional list of identity constraints. A
``production_constraints`` item prefixed ``character-lock:`` or
``identity-lock:`` is the same kind of lock. An ``aspect_ratio`` value, or
the first ``N:M`` token in ``production_constraints``, is the frame shape.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence

_CONSTRAINT_LOCK = re.compile(
    r"^(?:character-lock|identity-lock)\s*:\s*(.+)$",
    re.IGNORECASE,
)
_LOCK_PREFIX = re.compile(
    r"^(?:character-lock|identity-lock|identity)\s*:\s*",
    re.IGNORECASE,
)
_NO_PREFIX = re.compile(r"^(?:no|without)\s+\S", re.IGNORECASE)
_RATIO = re.compile(r"(?<!\d)(\d{1,2}:\d{1,2})(?!\d)")
_BLANK = {"", "none", "not_computable"}
_FRAME_KEYS = ("duration_seconds", "title", "scene", "sound", "speech_lines")
_CARRIED_KEYS = ("character_locks", "production_constraints", "aspect_ratio", "characters", "props")

BASE_NEGATIVES = (
    "no named esoterica",
    "no unexplained motif reset",
    "no continuity-breaking ownership change",
)


def _blank(value: object) -> bool:
    if value is None:
        return True
    return str(value).strip().casefold() in _BLANK


def string_list(value: object) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [] if _blank(text) else [text]
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    items: list[str] = []
    for item in value:
        if _blank(item):
            continue
        items.append(str(item).strip())
    return items


def _unique(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        key = item.casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(item)
    return ordered


def _strip_lock(text: str) -> str:
    return _LOCK_PREFIX.sub("", text.strip(), count=1).strip()


def negative_form(lock: str) -> str | None:
    """Return the negative wording of a lock, when the lock is a negation."""
    text = _strip_lock(lock)
    if _NO_PREFIX.match(text):
        return text
    return None


def collect_character_locks(source: Mapping[str, object]) -> list[str]:
    """Locks from ``character_locks`` and prefixed production constraints."""
    found: list[str] = []
    for item in string_list(source.get("character_locks")):
        found.append(_strip_lock(item))
    for item in string_list(source.get("production_constraints")):
        match = _CONSTRAINT_LOCK.match(item.strip())
        if match is None:
            continue
        found.append(_strip_lock(match.group(1)))
    return _unique(found)


def ratio_token(text: str) -> str | None:
    match = _RATIO.search(text)
    if match is None:
        return None
    return match.group(1)


def aspect_ratio_from(source: Mapping[str, object]) -> str | None:
    """First explicit ``N:M`` token on an aspect key or production constraint."""
    for key in ("aspectRatio", "aspect_ratio"):
        value = source.get(key)
        if isinstance(value, str):
            token = ratio_token(value)
            if token:
                return token
    for item in string_list(source.get("production_constraints")):
        token = ratio_token(item)
        if token:
            return token
    return None


def _load_mapping(text: str) -> dict[str, object]:
    stripped = text.strip()
    if not stripped:
        return {}
    if stripped[0] in "{[":
        try:
            loaded: object = json.loads(stripped)
        except json.JSONDecodeError:
            return {}
    else:
        try:
            import yaml
        except ImportError:
            return {}
        try:
            loaded = yaml.safe_load(stripped)
        except yaml.YAMLError:
            return {}
    if not isinstance(loaded, dict):
        return {}
    return {str(key): value for key, value in loaded.items()}


def constraints_from_texts(*texts: str | None) -> dict[str, object]:
    locks: list[str] = []
    constraints: list[str] = []
    aspect: str | None = None
    for text in texts:
        if text is None or not str(text).strip():
            continue
        mapping = _load_mapping(str(text))
        locks.extend(collect_character_locks(mapping))
        constraints.extend(string_list(mapping.get("production_constraints")))
        if aspect is None:
            aspect = aspect_ratio_from(mapping)
    payload: dict[str, object] = {}
    unique_locks = _unique(locks)
    if unique_locks:
        payload["character_locks"] = unique_locks
    unique_constraints = _unique(constraints)
    if unique_constraints:
        payload["production_constraints"] = unique_constraints
    if aspect:
        payload["aspect_ratio"] = aspect
    return payload


def carried_brief_fields(brief: Mapping[str, object]) -> dict[str, object]:
    """Non-empty brief fields the graph may carry into the adapter packet."""
    carried: dict[str, object] = {}
    for key in _CARRIED_KEYS:
        if key not in brief:
            continue
        value = brief.get(key)
        if value in (None, "", []):
            continue
        carried[key] = value
    if "aspect_ratio" not in carried:
        alias = brief.get("aspectRatio")
        if isinstance(alias, str) and alias.strip():
            carried["aspect_ratio"] = alias.strip()
    return carried


def copy_carried_fields(spec: Mapping[str, object]) -> dict[str, object]:
    return carried_brief_fields(spec)


def carried_shared(
    source: Mapping[str, object],
    base: Sequence[str] = BASE_NEGATIVES,
) -> dict[str, object]:
    """Shared-constraint additions: locks, ratio, and negative forms."""
    locks = collect_character_locks(source)
    forms = [form for form in (negative_form(lock) for lock in locks) if form is not None]
    extra: dict[str, object] = {"negative_constraints": _unique([*base, *forms])}
    if locks:
        extra["character_locks"] = locks
    ratio = aspect_ratio_from(source)
    if ratio:
        extra["aspect_ratio"] = ratio
    constraints = string_list(source.get("production_constraints"))
    if constraints:
        extra["production_constraints"] = constraints
    return extra


def attach_shot_locks(shot: dict[str, object], *texts: str | None) -> None:
    """Copy brief locks and aspect onto a video shot. No-op when absent."""
    payload = constraints_from_texts(*texts)
    locks = string_list(payload.get("character_locks"))
    if locks:
        shot["character_locks"] = locks
        existing = shot.get("negative_constraints")
        base = [str(item) for item in existing] if isinstance(existing, list) else []
        forms = [form for form in (negative_form(lock) for lock in locks) if form is not None]
        shot["negative_constraints"] = _unique([*base, *forms])
    ratio = payload.get("aspect_ratio")
    if isinstance(ratio, str) and ratio:
        shot["aspect_ratio"] = ratio


def _mapped_speech(item: Mapping[str, object]) -> str | None:
    raw = item.get("line")
    if raw is None:
        raw = item.get("text")
    if isinstance(raw, str) and not _blank(raw):
        return raw.strip()
    return None


def plain_speech_lines(raw: object) -> list[str]:
    """Spoken text. A ``{character, line}`` mapping contributes its line."""
    if isinstance(raw, str):
        return [] if _blank(raw) else [raw.strip()]
    if isinstance(raw, Mapping):
        spoken = _mapped_speech(raw)
        return [] if spoken is None else [spoken]
    if isinstance(raw, (bytes, bytearray)) or not isinstance(raw, Sequence):
        return []
    found: list[str] = []
    for item in raw:
        if isinstance(item, (str, Mapping)):
            found.extend(plain_speech_lines(item))
        elif not _blank(item):
            text = str(item).strip()
            if text:
                found.append(text)
    return found


def optional_frame_fields(spec: Mapping[str, object]) -> dict[str, object]:
    extra: dict[str, object] = {}
    for key in _FRAME_KEYS:
        if key not in spec:
            continue
        value = spec.get(key)
        if value in (None, ""):
            continue
        if key == "speech_lines" and isinstance(value, str) and value.strip():
            extra[key] = [value.strip()]
            continue
        extra[key] = value
    return extra


def frame_parameters(frame: Mapping[str, object]) -> dict[str, object]:
    params: dict[str, object] = {}
    raw = frame.get("provider_parameters")
    if isinstance(raw, Mapping):
        for key, value in raw.items():
            params[str(key)] = value
    for key, value in optional_frame_fields(frame).items():
        params.setdefault(key, value)
    speech = params.get("speech_lines")
    if speech is not None:
        params["speech_lines"] = plain_speech_lines(speech)
    return params


def packet_locks(packet: Mapping[str, object]) -> list[str]:
    shared = packet.get("shared_constraints")
    if not isinstance(shared, Mapping):
        return []
    return string_list(shared.get("character_locks"))
