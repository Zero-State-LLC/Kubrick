#!/usr/bin/env python3
"""Model capability caps: reference count limits and native audio support. Issue #67."""
from __future__ import annotations

from collections.abc import Callable, Mapping

from continuity_locks import warning
from provider_capabilities import _ordered, _resolved_model, _text, normalize_provider


def model_limits(
    provider: str | None, document: Mapping[str, object] | None,
) -> dict[str, object]:
    name, blocks = _resolved_model(
        normalize_provider(provider), _text(document, "model"), None,
    )
    found: dict[str, object] = {"model": name}
    for block in _ordered(blocks, _text(document, "input_mode")):
        cap = block.get("max_references")
        if isinstance(cap, int) and not isinstance(cap, bool) and cap >= 0:
            found["max_references"] = cap
        audio = block.get("native_audio")
        if isinstance(audio, bool):
            found["native_audio"] = audio
    return found


def _unique(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    ordered: list[str] = []
    for item in value:
        if isinstance(item, str) and item not in ordered:
            ordered.append(item)
    return ordered


def _shots(movie: Mapping[str, object]) -> list[Mapping[str, object]]:
    raw = movie.get("shots")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, Mapping)]


def _shot_label(shot: Mapping[str, object], index: int) -> str:
    title = shot.get("title")
    return title if isinstance(title, str) and title.strip() else str(index)


def reference_cap_error(
    movie: Mapping[str, object], limits: Mapping[str, object],
) -> str | None:
    cap = limits.get("max_references")
    if not isinstance(cap, int) or isinstance(cap, bool):
        return None
    base = _unique(movie.get("referenceImages"))
    count, where = len(base), "movie"
    for index, shot in enumerate(_shots(movie), start=1):
        merged = _unique([*base, *_unique(shot.get("referenceImages"))])
        if len(merged) > count:
            count, where = len(merged), f"shot {_shot_label(shot, index)}"
    if count <= cap:
        return None
    model = limits.get("model") or "model"
    return (
        f"REFERENCE_CAP_EXCEEDED: {count} references exceed {model} "
        f"max_references {cap} on {where}"
    )


def native_audio_warnings(
    movie: Mapping[str, object], limits: Mapping[str, object],
) -> list[dict[str, str | None]]:
    if limits.get("native_audio") is not False:
        return []
    model = limits.get("model") or "model"
    found: list[dict[str, str | None]] = []
    for index, shot in enumerate(_shots(movie), start=1):
        audio = shot.get("audio")
        if isinstance(audio, Mapping) and "speech" in audio:
            label = _shot_label(shot, index)
            found.append(warning(
                "NATIVE_AUDIO_UNSUPPORTED",
                label,
                f"{label} requests speech but {model} has no native audio",
                "record dialogue separately and lay it in the edit",
            ))
    return found


def enforce(
    movie: dict[str, object],
    document: Mapping[str, object] | None,
    refuse: Callable[[str], dict[str, object]],
) -> dict[str, object]:
    limits = model_limits("keyframe", document)
    error = reference_cap_error(movie, limits)
    if error:
        payload = refuse(error)
        payload["code"] = "REFERENCE_CAP_EXCEEDED"
        return payload
    extra = native_audio_warnings(movie, limits)
    if extra:
        existing = movie.get("prep_warnings")
        current = list(existing) if isinstance(existing, list) else []
        movie["prep_warnings"] = [*current, *extra]
    return movie
