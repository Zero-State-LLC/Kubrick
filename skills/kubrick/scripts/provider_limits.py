#!/usr/bin/env python3
"""Preflight Seedance and board limits before a packet can be submitted.

No provider is called. A duration, reference aspect, or missing board aspect
that Seedance or nano-banana would reject becomes NOT_COMPUTABLE here.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from provider_capabilities import (
    PROVIDER_CAPABILITIES,
    default_model,
    load_model_capabilities,
    normalize_provider,
)
from value_coerce import as_float, as_number


def model_limits(provider: str | None = "keyframe", model: str | None = None) -> dict[str, object]:
    """Declared limits for one model. Empty when the file has none."""
    loaded = load_model_capabilities()
    providers = loaded.get("providers")
    if not isinstance(providers, Mapping):
        return {}
    record = providers.get(normalize_provider(provider))
    if not isinstance(record, Mapping):
        return {}
    models = record.get("models")
    if not isinstance(models, Mapping):
        return {}
    chosen = model.strip() if isinstance(model, str) and model.strip() else default_model(provider)
    if not chosen:
        return {}
    spec = models.get(chosen)
    if not isinstance(spec, Mapping):
        return {}
    raw = spec.get("limits")
    if not isinstance(raw, Mapping):
        return {}
    return {str(key): value for key, value in raw.items()}

REF_ASPECT_MIN = 0.40
REF_ASPECT_MAX = 2.50
_SPLIT = "split the wide sheet into two tiles each with aspect at or below 2.50"


def _bounds() -> tuple[float, float, bool]:
    caps = PROVIDER_CAPABILITIES["keyframe"]
    minimum = as_float(caps["min_duration_seconds"]) or 4.0
    maximum = as_float(caps["max_duration_seconds"]) or 30.0
    integer = caps.get("duration_integer") is True
    limits = model_limits("keyframe")
    durations = limits.get("durations")
    if isinstance(durations, Mapping):
        parsed_min = as_float(durations.get("min"))
        parsed_max = as_float(durations.get("max"))
        if parsed_min is not None:
            minimum = parsed_min
        if parsed_max is not None:
            maximum = parsed_max
        if "integer" in durations:
            integer = durations.get("integer") is True
    return minimum, maximum, integer


def _shown(seconds: float) -> int | float:
    if float(seconds).is_integer():
        return int(seconds)
    return float(seconds)


def duration_refusal(seconds: float, frame_id: str) -> tuple[str, str] | None:
    """Return (code, message) when a declared duration cannot be submitted."""
    minimum, maximum, integer = _bounds()
    shown = _shown(seconds)
    if float(seconds) > maximum:
        return (
            "DURATION_OUT_OF_RANGE",
            (
                f"DURATION_OUT_OF_RANGE: keyframe shot {frame_id} duration {shown}s "
                f"is outside the allowed integer {_shown(minimum)}–{_shown(maximum)} seconds; "
                "refusing to clamp or drop the shot"
            ),
        )
    if integer and minimum <= float(seconds) <= maximum and not float(seconds).is_integer():
        return (
            "DURATION_NONINTEGER",
            (
                f"DURATION_NONINTEGER: keyframe shot {frame_id} duration {shown}s "
                "is not a whole second; Seedance accepts integer durations from "
                f"{_shown(minimum)} to {_shown(maximum)}; refusing to clamp or drop the shot"
            ),
        )
    return None


def ref_aspect_limits() -> tuple[float, float]:
    limits = model_limits("keyframe")
    raw = limits.get("ref_aspect")
    if (
        isinstance(raw, Sequence)
        and not isinstance(raw, (str, bytes))
        and len(raw) == 2
    ):
        low = as_float(raw[0])
        high = as_float(raw[1])
        if low is not None and high is not None and high >= low:
            return low, high
    return REF_ASPECT_MIN, REF_ASPECT_MAX


def reference_aspect_refusal(width: object, height: object) -> dict[str, object] | None:
    """Refuse a reference whose width/height is outside Seedance 0.40–2.50."""
    wide = as_number(width)
    tall = as_number(height)
    if wide is None or tall is None or tall <= 0 or wide <= 0:
        return {
            "code": "REF_ASPECT_OUT_OF_RANGE",
            "message": (
                "REF_ASPECT_OUT_OF_RANGE: reference width and height must be positive numbers"
            ),
            "suggestion": _SPLIT,
        }
    aspect = float(wide) / float(tall)
    low, high = ref_aspect_limits()
    if low <= aspect <= high:
        return None
    shown = round(aspect, 4)
    return {
        "code": "REF_ASPECT_OUT_OF_RANGE",
        "aspect": shown,
        "limit": [low, high],
        "width": wide,
        "height": tall,
        "message": (
            f"REF_ASPECT_OUT_OF_RANGE: reference {int(wide) if float(wide).is_integer() else wide}"
            f"x{int(tall) if float(tall).is_integer() else tall} has aspect {shown}, "
            f"outside {low}–{high}"
        ),
        "suggestion": _SPLIT,
    }


def _dimensioned(value: object) -> list[Mapping[str, object]]:
    if isinstance(value, Mapping) and ("width" in value or "height" in value):
        return [value]
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def packet_reference_refusals(packet: Mapping[str, object]) -> list[dict[str, object]]:
    """Dimensioned references on the packet or its frames. Path strings are skipped."""
    found: list[dict[str, object]] = []
    pools: list[object] = []
    for key in ("referenceImages", "reference_images", "reference_assets"):
        if key in packet:
            pools.append(packet.get(key))
    frames = packet.get("frames")
    if isinstance(frames, Sequence) and not isinstance(frames, (str, bytes)):
        for frame in frames:
            if not isinstance(frame, Mapping):
                continue
            for key in ("referenceImages", "reference_images", "reference_assets"):
                if key in frame:
                    pools.append(frame.get(key))
    for pool in pools:
        for item in _dimensioned(pool):
            refusal = reference_aspect_refusal(item.get("width"), item.get("height"))
            if refusal is not None:
                found.append(refusal)
    return found


def _explicit_aspect(packet: Mapping[str, object]) -> str:
    from brief_constraints import aspect_ratio_from

    sources: list[Mapping[str, object]] = [packet]
    shared = packet.get("shared_constraints")
    if isinstance(shared, Mapping):
        sources.append(shared)
    params = packet.get("provider_parameters")
    if isinstance(params, Mapping):
        sources.append(params)
    frames = packet.get("frames")
    if isinstance(frames, Sequence) and not isinstance(frames, (str, bytes)) and frames:
        first = frames[0]
        if isinstance(first, Mapping):
            sources.append(first)
            frame_params = first.get("provider_parameters")
            if isinstance(frame_params, Mapping):
                sources.append(frame_params)
    for source in sources:
        found = aspect_ratio_from(source)
        if found:
            return found
    return ""


def image_packet(packet: Mapping[str, object], kind: str = "board") -> dict[str, object]:
    """Board or still packet. Aspect is copied from the plan and never defaults to 16:9."""
    aspect = _explicit_aspect(packet)
    if not aspect:
        return {
            "status": "NOT_COMPUTABLE",
            "code": "BOARD_ASPECT_MISSING",
            "kind": kind,
            "message": (
                "BOARD_ASPECT_MISSING: board and still packets require aspectRatio; "
                "nano-banana-2 otherwise defaults to 16:9"
            ),
            "errors": ["BOARD_ASPECT_MISSING"],
        }
    prompt = ""
    frames = packet.get("frames")
    if isinstance(frames, Sequence) and not isinstance(frames, (str, bytes)) and frames:
        first = frames[0]
        if isinstance(first, Mapping) and isinstance(first.get("prompt"), str):
            prompt = first["prompt"].strip()
    return {
        "status": "PROPOSED",
        "kind": kind,
        "model": "nano-banana-2",
        "aspectRatio": aspect,
        "prompt": prompt,
    }


def billed_credits(seconds: float, rate: float) -> float:
    """Observed Seedance bill for 4/5/6 seconds; otherwise seconds times the rate."""
    limits = model_limits("keyframe")
    billing = limits.get("billing")
    if float(seconds).is_integer() and isinstance(billing, Mapping):
        key = str(int(seconds))
        price = billing.get(key)
        if isinstance(price, bool) or not isinstance(price, (int, float)):
            price = billing.get(int(seconds))
        if isinstance(price, (int, float)) and not isinstance(price, bool):
            return float(price)
    return float(seconds) * float(rate)
