#!/usr/bin/env python3
"""Provider capability declarations for Kubrick image/video surfaces.

Adapters may change syntax only. When a request exceeds a provider's declared
capability, compilers fail closed with NOT_COMPUTABLE rather than inventing
unsupported temporal or dialogue behavior.

Model overlays (#42) merge onto these defaults. Only keys already present on
the provider are overwritten. ``max_references`` and ``native_audio`` stay on
the model block and are not copied into the returned map. Observed blocks win
over vendor claims. ``negative_prompt_effective`` is the same field #35 reads.
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from pathlib import Path

from continuity_locks import warning
from value_coerce import as_number as _number

_ROOT = Path(__file__).resolve().parent.parent
_MODEL_PATH = _ROOT / "assets" / "models" / "capabilities.yaml"
_MODEL_SCHEMA = _ROOT / "schemas" / "model-capabilities.schema.json"
_CACHE: dict[str, object] | None = None
_SKIP = {"source", "verified_on", "input_mode", "max_references", "native_audio"}
_DEFAULT_AGE = 180

# Declared capabilities — keep conservative; unknown providers inherit generic.
PROVIDER_CAPABILITIES: dict[str, dict[str, object]] = {
    "generic": {
        "image": True,
        "video": True,
        "max_duration_seconds": 16.0,
        "camera_motion": True,
        "dialogue_audio": False,
        "multi_shot": True,
        "physics_hints": True,
        "identity_lock": True,
        "negative_prompt_effective": True,
    },
    "flux": {
        "image": True,
        "video": False,
        "max_duration_seconds": 0.0,
        "camera_motion": False,
        "dialogue_audio": False,
        "multi_shot": False,
        "physics_hints": False,
        "identity_lock": True,
        "negative_prompt_effective": True,
    },
    "sd3": {
        "image": True,
        "video": False,
        "max_duration_seconds": 0.0,
        "camera_motion": False,
        "dialogue_audio": False,
        "multi_shot": False,
        "physics_hints": False,
        "identity_lock": True,
        "negative_prompt_effective": True,
    },
    "midjourney": {
        "image": True,
        "video": False,
        "max_duration_seconds": 0.0,
        "camera_motion": False,
        "dialogue_audio": False,
        "multi_shot": False,
        "physics_hints": False,
        "identity_lock": True,
        "negative_prompt_effective": True,
    },
    "grok-imagine": {
        "image": True,
        "video": True,
        "max_duration_seconds": 8.0,
        "camera_motion": True,
        "dialogue_audio": False,
        "multi_shot": False,
        "physics_hints": True,
        "identity_lock": True,
        "negative_prompt_effective": True,
    },
    "keyframe": {
        "image": True,
        "video": True,
        "min_duration_seconds": 4.0,
        "max_duration_seconds": 30.0,
        "duration_integer": True,
        "camera_motion": True,
        "dialogue_audio": True,
        "multi_shot": True,
        "physics_hints": True,
        "identity_lock": True,
        "is_multi_shot_single_clip": True,
        "short_beat_threshold_seconds": 2.0,
        "start_frame_hold_seconds": 1.6,
        "exclusive_inputs": [["startImage", "referenceImages"]],
        "exclusivity_notes": {
            "startImage|referenceImages": (
                "Seedance 2.5: startImage and referenceImages are mutually exclusive; "
                "references dropped on shot {shot}"
            ),
        },
        "negative_prompt_effective": False,
    },
}


def normalize_provider(provider: str | None) -> str:
    name = (provider or "generic").strip().lower() or "generic"
    return name


def _base(provider: str | None) -> dict[str, object]:
    name = normalize_provider(provider)
    if name in PROVIDER_CAPABILITIES:
        return dict(PROVIDER_CAPABILITIES[name])
    return {
        "image": True,
        "video": False,
        "max_duration_seconds": 0.0,
        "camera_motion": False,
        "dialogue_audio": False,
        "multi_shot": False,
        "physics_hints": False,
        "identity_lock": True,
        "negative_prompt_effective": False,
        "unknown_provider": True,
    }


def parse_iso_date(value: object) -> date | None:
    """Calendar date from an ISO string or a YAML date. Invalid values are None."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def require_calendar_date(value: object, label: str) -> date:
    parsed = parse_iso_date(value)
    if parsed is None:
        raise ValueError(f"{label} {value} is not a calendar date")
    return parsed


def _require_dates(loaded: Mapping[str, object]) -> None:
    providers = loaded.get("providers")
    if not isinstance(providers, Mapping):
        return
    for name, record in providers.items():
        if isinstance(record, Mapping):
            _require_record_dates(str(name), record)


def _require_record_dates(provider: str, record: Mapping[str, object]) -> None:
    pricing = record.get("pricing")
    if isinstance(pricing, Mapping):
        require_calendar_date(pricing.get("observed_on"), f"pricing for {provider} observed_on")
    models = record.get("models")
    if not isinstance(models, Mapping):
        return
    for model, spec in models.items():
        blocks = spec.get("blocks") if isinstance(spec, Mapping) else None
        if not isinstance(blocks, Sequence) or isinstance(blocks, (str, bytes)):
            continue
        label = f"capability block for {model} verified_on"
        for block in blocks:
            if isinstance(block, Mapping):
                require_calendar_date(block.get("verified_on"), label)


def reference_date(explicit: date | None, document: Mapping[str, object] | None) -> date:
    """Injected date, else document ``as_of``, else today. Tests pass ``explicit``."""
    if explicit is not None:
        return explicit
    if document is not None:
        parsed = parse_iso_date(document.get("as_of"))
        if parsed is not None:
            return parsed
    return date.today()


def configured_age(
    explicit: int | None,
    document: Mapping[str, object] | None,
    key: str,
    default: int = _DEFAULT_AGE,
) -> int:
    if explicit is not None:
        return explicit
    if document is not None:
        raw = document.get(key)
        if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0:
            return raw
    return default


def _text(source: Mapping[str, object] | None, key: str) -> str | None:
    if source is None:
        return None
    value = source.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def load_model_capabilities(path: Path | None = None) -> dict[str, object]:
    """Validate the model file. A schema failure or impossible date raises ValueError."""
    global _CACHE
    import jsonschema
    import yaml

    target = path or _MODEL_PATH
    if path is None and _CACHE is not None:
        return _CACHE
    loaded = yaml.safe_load(target.read_text(encoding="utf-8"))
    schema = json.loads(_MODEL_SCHEMA.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("model capabilities must be an object")
    try:
        jsonschema.validate(loaded, schema)
    except jsonschema.ValidationError as exc:
        raise ValueError(f"model capabilities schema invalid: {exc.message}") from exc
    _require_dates(loaded)
    record = {str(key): value for key, value in loaded.items()}
    if path is None:
        _CACHE = record
    return record


def _provider_record(provider: str | None, path: Path | None = None) -> Mapping[str, object] | None:
    try:
        loaded = load_model_capabilities(path)
    except ImportError:
        # Stdlib profile has no validator. An explicit file still fails closed.
        if path is not None:
            raise
        return None
    providers = loaded.get("providers")
    if not isinstance(providers, Mapping):
        return None
    record = providers.get(normalize_provider(provider))
    if not isinstance(record, Mapping):
        return None
    return record


def default_model(provider: str | None, path: Path | None = None) -> str | None:
    record = _provider_record(provider, path)
    if record is None:
        return None
    return _text(record, "default_model")


def pricing_for(provider: str | None, path: Path | None = None) -> dict[str, object] | None:
    record = _provider_record(provider, path)
    if record is None:
        return None
    pricing = record.get("pricing")
    if not isinstance(pricing, Mapping):
        return None
    return {str(key): value for key, value in pricing.items()}


def model_blocks(
    provider: str | None,
    model: str,
    path: Path | None = None,
) -> list[dict[str, object]]:
    record = _provider_record(provider, path)
    if record is None:
        return []
    models = record.get("models")
    if not isinstance(models, Mapping):
        return []
    spec = models.get(model)
    if not isinstance(spec, Mapping):
        return []
    raw = spec.get("blocks")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    found: list[dict[str, object]] = []
    for item in raw:
        if isinstance(item, Mapping):
            found.append({str(key): value for key, value in item.items()})
    return found


def _ordered(
    blocks: Sequence[Mapping[str, object]], mode: str | None,
) -> list[Mapping[str, object]]:
    plain = [item for item in blocks if not _text(item, "input_mode")]
    modal = [item for item in blocks if mode and _text(item, "input_mode") == mode]
    ordered: list[Mapping[str, object]] = []
    for group in (plain, modal):
        ordered.extend(item for item in group if item.get("source") == "vendor_claim")
        ordered.extend(item for item in group if item.get("source") == "observed")
    return ordered


def _apply(base: dict[str, object], block: Mapping[str, object]) -> None:
    for key, value in block.items():
        if key in _SKIP or key not in base:
            continue
        base[key] = value


def _resolved_model(
    provider: str,
    model: str | None,
    path: Path | None,
) -> tuple[str | None, list[dict[str, object]]]:
    named = model.strip() if isinstance(model, str) and model.strip() else None
    name = named or default_model(provider, path)
    if not name:
        return None, []
    blocks = model_blocks(provider, name, path)
    return name, blocks


def provider_capabilities(
    provider: str | None,
    model: str | None = None,
    *,
    input_mode: str | None = None,
    path: Path | None = None,
) -> dict[str, object]:
    """Provider defaults with the model overlay merged. Observed values win."""
    base = _base(provider)
    name = normalize_provider(provider)
    _model, blocks = _resolved_model(name, model, path)
    mode = input_mode.strip() if isinstance(input_mode, str) and input_mode.strip() else None
    for block in _ordered(blocks, mode):
        _apply(base, block)
    return base


def capabilities_for(
    provider: str | None,
    model: str | None = None,
    *,
    input_mode: str | None = None,
) -> dict[str, object]:
    return provider_capabilities(provider, model, input_mode=input_mode)


def capabilities_for_document(
    provider: str | None,
    document: Mapping[str, object] | None,
) -> dict[str, object]:
    return provider_capabilities(
        provider,
        _text(document, "model"),
        input_mode=_text(document, "input_mode"),
    )


def _stale(block: Mapping[str, object], as_of: date, max_age: int) -> bool:
    verified = parse_iso_date(block.get("verified_on"))
    if verified is None:
        return False
    return (as_of - verified).days > max_age


def capability_warnings(
    provider: str,
    document: Mapping[str, object] | None = None,
    *,
    as_of: date | None = None,
    max_age_days: int | None = None,
    path: Path | None = None,
) -> list[dict[str, str | None]]:
    """One ``CAPABILITY_STALE`` warning per applied block older than the age."""
    name = normalize_provider(provider)
    model, blocks = _resolved_model(name, _text(document, "model"), path)
    if not model:
        return []
    when = reference_date(as_of, document)
    age = configured_age(max_age_days, document, "capability_max_age_days")
    mode = _text(document, "input_mode")
    found: list[dict[str, str | None]] = []
    for block in _ordered(blocks, mode):
        if not _stale(block, when, age):
            continue
        verified = str(block.get("verified_on") or "")
        found.append(warning(
            "CAPABILITY_STALE",
            None,
            (
                f"capability block for {model} verified_on {verified} "
                f"is older than {age} days"
            ),
            "re-check the capability against a current generation",
        ))
    return found


def check_image_adapt(provider: str | None) -> dict[str, object] | None:
    caps = capabilities_for(provider)
    if not caps.get("image"):
        return {
            "code": "PROVIDER_CAPABILITY",
            "message": (
                f"provider `{normalize_provider(provider)}` does not support image adaptation"
            ),
            "capabilities": caps,
        }
    return None


def check_video_adapt(
    provider: str | None, *, duration: float | None = None,
) -> dict[str, object] | None:
    caps = capabilities_for(provider)
    name = normalize_provider(provider)
    if not caps.get("video"):
        return {
            "code": "PROVIDER_CAPABILITY",
            "message": f"provider `{name}` does not support video adaptation",
            "capabilities": caps,
        }
    if duration is not None and "min_duration_seconds" in caps:
        min_dur = _number(caps.get("min_duration_seconds"))
        if min_dur is not None and float(duration) < min_dur:
            return {
                "code": "PROVIDER_CAPABILITY",
                "message": f"requested duration {duration}s is below `{name}` minimum {min_dur}s",
                "capabilities": caps,
            }
    if duration is not None:
        max_dur = _number(caps.get("max_duration_seconds")) or 0.0
        if max_dur > 0 and float(duration) > max_dur:
            return {
                "code": "PROVIDER_CAPABILITY",
                "message": (
                    f"requested duration {duration}s exceeds `{name}` max "
                    f"{max_dur}s"
                ),
                "capabilities": caps,
            }
    return None


def check_video_shot(
    provider: str | None, *, duration: float, wants_camera_motion: bool = False,
) -> dict[str, object] | None:
    """Optional advisory when compiling shots toward a known provider."""
    if not provider or normalize_provider(provider) == "generic":
        return None
    caps = capabilities_for(provider)
    name = normalize_provider(provider)
    if not caps.get("video"):
        return {
            "code": "PROVIDER_CAPABILITY",
            "message": (
                f"provider `{name}` cannot execute video shots; keep packet provider-neutral"
            ),
            "capabilities": caps,
        }
    minimum = _number(caps.get("min_duration_seconds"))
    if minimum is not None and float(duration) < minimum:
        return {
            "code": "PROVIDER_CAPABILITY",
            "message": (
                f"shot duration {duration}s is below `{name}` minimum {minimum}s"
            ),
            "capabilities": caps,
        }
    max_dur = _number(caps.get("max_duration_seconds")) or 0.0
    if max_dur > 0 and float(duration) > max_dur:
        return {
            "code": "PROVIDER_CAPABILITY",
            "message": f"shot duration {duration}s exceeds `{name}` max {max_dur}s",
            "capabilities": caps,
        }
    if wants_camera_motion and not caps.get("camera_motion"):
        return {
            "code": "PROVIDER_CAPABILITY",
            "message": f"provider `{name}` does not declare camera motion support",
            "capabilities": caps,
        }
    return None
