#!/usr/bin/env python3
"""Schema-validated known-drift registry. Issue #39.

Matching uses shot facts the planner already computes. An entry applies only
when its ``model`` equals the resolved model (document ``model``, else the
provider default). ``plain_top_motion`` delegates to ``drift_warnings`` so the
#30 text stays identical. Age is ``(as_of - observed_on).days > max_age``.
The default age is 180 days. Tests inject ``as_of``.
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path

from continuity_locks import frame_field, frame_id, warning
from provider_capabilities import (
    capabilities_for_document,
    configured_age,
    default_model,
    parse_iso_date,
    reference_date,
    require_calendar_date,
)

_ROOT = Path(__file__).resolve().parent.parent
_PATH = _ROOT / "assets" / "drift" / "known_drift.yaml"
_SCHEMA = _ROOT / "schemas" / "drift-registry.schema.json"
_CACHE: dict[str, object] | None = None


def join_mitigations(items: Sequence[str], failed: Sequence[str] = ()) -> str:
    """Join mitigations with a final ``or``. Append failed mitigations when set."""
    kept = [item.strip() for item in items if item.strip()]
    if not kept:
        text = ""
    elif len(kept) == 1:
        text = kept[0]
    else:
        text = ", ".join(kept[:-1]) + ", or " + kept[-1]
    failed_kept = [item.strip() for item in failed if item.strip()]
    if failed_kept:
        text = f"{text}; failed mitigations: {', '.join(failed_kept)}"
    return text


def load_registry(path: Path | None = None) -> dict[str, object]:
    """Validate the registry. An invalid file raises ValueError."""
    global _CACHE
    import jsonschema
    import yaml

    target = path or _PATH
    if path is None and _CACHE is not None:
        return _CACHE
    loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("drift registry must be an object")
    try:
        jsonschema.validate(loaded, schema)
    except jsonschema.ValidationError as exc:
        raise ValueError(f"drift registry schema invalid: {exc.message}") from exc
    _require_entries(loaded)
    record = {str(key): value for key, value in loaded.items()}
    if path is None:
        _CACHE = record
    return record


def _require_entries(loaded: Mapping[str, object]) -> None:
    raw = loaded.get("entries")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ValueError("drift registry entries must be a list")
    for item in raw:
        if not isinstance(item, Mapping):
            raise ValueError("drift entry must be an object")
        require_calendar_date(
            item.get("observed_on"), f"drift entry {item.get('id')} observed_on",
        )
        trigger = item.get("trigger")
        if not isinstance(trigger, Mapping):
            raise ValueError(f"drift entry {item.get('id')} trigger must be an object")
        if trigger.get("kind") == "missing_reference" and not _text(trigger.get("feature")):
            raise ValueError(f"drift entry {item.get('id')} missing_reference requires feature")


def _entries(path: Path | None) -> list[Mapping[str, object]]:
    raw = load_registry(path).get("entries")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    return [item for item in raw if isinstance(item, Mapping)]


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _strings(value: object) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _table(document: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    raw = document.get("characters")
    if not isinstance(raw, Mapping):
        return {}
    return {str(key): value for key, value in raw.items() if isinstance(value, Mapping)}


def _present(frame: Mapping[str, object]) -> list[str]:
    from reference_lint import screen_mode

    mode, present = screen_mode(frame)
    if mode == "absent":
        return []
    return present


def _resolved_model(
    document: Mapping[str, object],
    provider: str,
    model: str | None,
) -> str:
    if isinstance(model, str) and model.strip():
        return model.strip()
    named = _text(document.get("model"))
    if named:
        return named
    return default_model(provider) or ""


def _warn(
    entry: Mapping[str, object],
    shot: str,
    character: str | None,
) -> dict[str, str | None]:
    effect = str(entry.get("effect") or "")
    ident = str(entry.get("id") or "")
    if character:
        message = f"{character} on {shot} matches {ident} and can show {effect}"
    else:
        message = f"{shot} matches {ident}: {effect}"
    return warning(
        "KNOWN_DRIFT",
        shot,
        message,
        join_mitigations(
            _strings(entry.get("mitigations")), _strings(entry.get("failed_mitigations")),
        ),
        character=character,
    )


def _plain(
    entry: Mapping[str, object],
    document: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
    provider: str,
) -> list[dict[str, str | None]]:
    from continuity_locks import drift_warnings

    legacy = {
        "pattern": "plain top + motion",
        "effect": str(entry.get("effect") or "known wardrobe drift"),
        "providers": [provider],
    }
    return drift_warnings(document, frames, provider, [legacy])


def _owns_feature(document: Mapping[str, object], character: str, feature: str) -> bool:
    folded = feature.casefold()
    spec = _table(document).get(character)
    if spec is not None:
        for lock in _strings(spec.get("character_locks")):
            if folded in lock.casefold():
                return True
    raw = document.get("locks")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return False
    for item in raw:
        if not isinstance(item, Mapping) or str(item.get("character") or "") != character:
            continue
        for key in ("negative", "positive", "text"):
            value = item.get(key)
            if isinstance(value, str) and folded in value.casefold():
                return True
    return False


def _declared_paths(spec: Mapping[str, object]) -> set[str]:
    raw = spec.get("references")
    found: set[str] = set()
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return found
    for ref in raw:
        if not isinstance(ref, Mapping):
            continue
        for key in ("path", "mediaObjectId"):
            value = ref.get(key)
            if isinstance(value, str) and value.strip():
                found.add(value.strip())
    return found


def _frame_refs(frame: Mapping[str, object]) -> set[str]:
    return set(_strings(frame_field(frame, "reference_images")))


def _missing_reference(
    entry: Mapping[str, object],
    document: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
) -> list[dict[str, str | None]]:
    trigger = entry.get("trigger")
    feature = _text(trigger.get("feature") if isinstance(trigger, Mapping) else None)
    found: list[dict[str, str | None]] = []
    for index, frame in enumerate(frames, start=1):
        shot = frame_id(frame, index)
        listed = _frame_refs(frame)
        for character in _present(frame):
            spec = _table(document).get(character)
            if spec is None or not _owns_feature(document, character, feature):
                continue
            if _declared_paths(spec) & listed:
                continue
            found.append(_warn(entry, shot, character))
    return found


def _attached_character_ref(document: Mapping[str, object], frame: Mapping[str, object]) -> bool:
    from reference_lint import reference_attached

    for owner, spec in _table(document).items():
        raw = spec.get("references")
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            continue
        for ref in raw:
            if not isinstance(ref, Mapping):
                continue
            role = str(ref.get("role") or "character").strip().casefold()
            if role == "character" and reference_attached(frame, ref, owner):
                return True
    return False


def _bleed(
    entry: Mapping[str, object],
    document: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
) -> list[dict[str, str | None]]:
    trigger = entry.get("trigger")
    minimum = 2
    if isinstance(trigger, Mapping) and isinstance(trigger.get("min_characters"), int):
        minimum = int(trigger["min_characters"])
    found: list[dict[str, str | None]] = []
    for index, frame in enumerate(frames, start=1):
        present = _present(frame)
        if len(present) < minimum or not _attached_character_ref(document, frame):
            continue
        found.append(_warn(entry, frame_id(frame, index), None))
    return found


def _location(
    entry: Mapping[str, object],
    document: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
) -> list[dict[str, str | None]]:
    location = document.get("location")
    refs: object = None
    if isinstance(location, Mapping):
        refs = location.get("references")
    if not isinstance(refs, Sequence) or isinstance(refs, (str, bytes)) or not refs or not frames:
        return []
    return [_warn(entry, frame_id(frames[0], 1), None)]


def _chained(
    entry: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
) -> list[dict[str, str | None]]:
    from shot_plan import chain_source

    found: list[dict[str, str | None]] = []
    for index, frame in enumerate(frames, start=1):
        if chain_source(frame) is None:
            continue
        found.append(_warn(entry, frame_id(frame, index), None))
    return found


def _short(
    entry: Mapping[str, object],
    document: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
    provider: str,
) -> list[dict[str, str | None]]:
    from shot_plan import _duration, _threshold

    caps = capabilities_for_document(provider, document)
    if not caps.get("is_multi_shot_single_clip") or len(frames) < 2:
        return []
    limit = _threshold(provider, document)
    found: list[dict[str, str | None]] = []
    for index, frame in enumerate(frames, start=1):
        if _duration(frame, 8.0) > limit:
            continue
        found.append(_warn(entry, frame_id(frame, index), None))
    return found


def _match(
    entry: Mapping[str, object],
    document: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
    provider: str,
) -> list[dict[str, str | None]]:
    trigger = entry.get("trigger")
    kind = trigger.get("kind") if isinstance(trigger, Mapping) else None
    if kind == "plain_top_motion":
        return _plain(entry, document, frames, provider)
    if kind == "missing_reference":
        return _missing_reference(entry, document, frames)
    if kind == "character_reference_bleed":
        return _bleed(entry, document, frames)
    if kind == "location_reference":
        return _location(entry, document, frames)
    if kind == "chained_start":
        return _chained(entry, frames)
    if kind == "short_multi_shot":
        return _short(entry, document, frames, provider)
    return []


def _stale_warning(entry: Mapping[str, object], max_age: int) -> dict[str, str | None]:
    ident = str(entry.get("id") or "")
    observed = str(entry.get("observed_on") or "")
    return warning(
        "DRIFT_ENTRY_STALE",
        None,
        f"drift entry {ident} observed_on {observed} is older than {max_age} days",
        "re-check the entry against a current generation or retire it",
    )


def registry_warnings(
    document: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
    provider: str,
    *,
    as_of: date | None = None,
    max_age_days: int | None = None,
    model: str | None = None,
    path: Path | None = None,
) -> list[dict[str, str | None]]:
    """Known-drift warnings, then one stale warning per old entry that matched the model."""
    chosen = _resolved_model(document, provider, model)
    when = reference_date(as_of, document)
    max_age = configured_age(max_age_days, document, "drift_max_age_days")
    found: list[dict[str, str | None]] = []
    stale: list[dict[str, str | None]] = []
    for entry in _entries(path):
        if str(entry.get("model") or "") != chosen:
            continue
        found.extend(_match(entry, document, frames, provider))
        observed = parse_iso_date(entry.get("observed_on"))
        if observed is not None and (when - observed).days > max_age:
            stale.append(_stale_warning(entry, max_age))
    return [*found, *stale]
