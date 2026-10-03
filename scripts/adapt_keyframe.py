#!/usr/bin/env python3
"""Keyframe MCP create_movie adapter.

Shot duration is inclusive 3–60 seconds. A missing duration defaults to 4
seconds. A shorter planned beat is generated at the 3 second minimum and the
cut list trims it back. Above 60 seconds fails closed and is not clamped.
Speech is omitted when the shot has no dialogue.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from brief_constraints import aspect_ratio_from, packet_locks
from prompt_text import is_blank, join_clauses
from reference_lint import bound_positive

MIN_SECONDS = 3.0
MAX_SECONDS = 60.0
DEFAULT_SECONDS = 4.0
_PRESETS = {"draft", "standard", "high"}
_DURATION_KEYS = ("duration_seconds", "durationSeconds", "duration")


def _not_computable(message: str) -> dict[str, object]:
    return {
        "status": "NOT_COMPUTABLE",
        "code": "PROVIDER_CAPABILITY",
        "message": message,
        "errors": [message],
    }


def _total_seconds(shots: Sequence[Mapping[str, object]]) -> float:
    total = 0.0
    for shot in shots:
        value = shot.get("durationSeconds")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        total += float(value)
    return total


def _as_seconds(value: float) -> int | float:
    if float(value).is_integer():
        return int(value)
    return float(value)


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _duration(frame: Mapping[str, object], frame_id: str) -> tuple[float | None, str | None]:
    sources: list[Mapping[str, object]] = []
    params = frame.get("provider_parameters")
    if isinstance(params, Mapping):
        sources.append(params)
    sources.append(frame)
    for source in sources:
        for key in _DURATION_KEYS:
            if key not in source or source[key] in (None, ""):
                continue
            value = source[key]
            seconds = _as_float(value)
            if seconds is None:
                return None, (
                    f"keyframe shot {frame_id} duration {value!r} is not a number; "
                    "refusing to clamp or drop the shot"
                )
            return seconds, None
    return DEFAULT_SECONDS, None


def _range_error(frame_id: str, seconds: float) -> str | None:
    if MIN_SECONDS <= seconds <= MAX_SECONDS:
        return None
    shown = _as_seconds(seconds)
    return (
        f"keyframe shot {frame_id} duration {shown}s is outside the allowed 3–60 seconds; "
        "refusing to clamp or drop the shot"
    )


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


def _extend_lines(found: list[str], raw: object) -> None:
    if isinstance(raw, str) and not is_blank(raw):
        found.append(raw.strip())
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        found.extend(str(item).strip() for item in raw if not is_blank(item))


def _frame_sources(frame: Mapping[str, object]) -> list[Mapping[str, object]]:
    sources: list[Mapping[str, object]] = [frame]
    params = frame.get("provider_parameters")
    if isinstance(params, Mapping):
        sources.append(params)
    return sources


def _dialogue(frame: Mapping[str, object]) -> list[str]:
    found: list[str] = []
    for source in _frame_sources(frame):
        for key in ("dialogue", "lines", "speech_lines"):
            _extend_lines(found, source.get(key))
        speech = source.get("speech")
        if isinstance(speech, Mapping):
            _extend_lines(found, speech.get("lines"))
    return _unique(found)


def _sound(frame: Mapping[str, object]) -> str:
    for source in _frame_sources(frame):
        for key in ("sound", "audio_sound"):
            value = source.get(key)
            if isinstance(value, str) and not is_blank(value):
                return value.strip()
    return "no scored music; evidenced room presence only"


def _string_list(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [str(item).strip() for item in value if not is_blank(item)]


def _negatives(packet: Mapping[str, object]) -> list[str]:
    shared = packet.get("shared_constraints")
    if not isinstance(shared, Mapping):
        return []
    return _string_list(shared.get("negative_constraints"))


def _prompts(
    frame: Mapping[str, object],
    negatives: Sequence[str],
    locks: Sequence[str],
    packet: Mapping[str, object],
) -> tuple[str, str]:
    source = str(frame.get("prompt") or "").strip()
    image = bound_positive(source, [], negatives, locks, packet, frame)
    image = image or source or "evidenced frame"
    continuity = _string_list(frame.get("continuity_from_previous"))
    constraints = _string_list(frame.get("state_constraints"))
    if continuity or constraints:
        video = bound_positive(source, [*continuity, *constraints], negatives, locks, packet, frame)
    else:
        video = image
    return image, video or image


def _first_identity(packet: Mapping[str, object]) -> str:
    shared = packet.get("shared_constraints")
    if not isinstance(shared, Mapping):
        return ""
    items = _string_list(shared.get("visual_identity"))
    return items[0] if items else ""


def _scene(frame: Mapping[str, object], packet: Mapping[str, object]) -> str:
    for source in _frame_sources(frame):
        scene = source.get("scene")
        if isinstance(scene, str) and scene.strip():
            return scene.strip()
    identity = _first_identity(packet)
    return identity or "evidenced scene"


def _shot_title(frame: Mapping[str, object], frame_id: str) -> str:
    for source in _frame_sources(frame):
        title = source.get("title")
        if isinstance(title, str) and title.strip():
            return title.strip()
    return frame_id


def _preset_value(source: Mapping[str, object]) -> str | None:
    for key in ("qualityPreset", "quality_preset"):
        value = source.get(key)
        if isinstance(value, str) and value in _PRESETS:
            return value
    return None


def _preset(packet: Mapping[str, object]) -> str:
    found = _preset_value(packet)
    if found:
        return found
    params = packet.get("provider_parameters")
    if isinstance(params, Mapping):
        found = _preset_value(params)
        if found:
            return found
    frames = packet.get("frames")
    if isinstance(frames, Sequence) and not isinstance(frames, (str, bytes)):
        for frame in frames:
            if not isinstance(frame, Mapping):
                continue
            frame_params = frame.get("provider_parameters")
            if isinstance(frame_params, Mapping):
                found = _preset_value(frame_params)
                if found:
                    return found
    return "draft"


def _aspect_sources(packet: Mapping[str, object]) -> list[Mapping[str, object]]:
    sources: list[Mapping[str, object]] = []
    frames = packet.get("frames")
    if isinstance(frames, Sequence) and not isinstance(frames, (str, bytes)) and frames:
        first = frames[0]
        if isinstance(first, Mapping):
            sources.extend(_frame_sources(first))
    params = packet.get("provider_parameters")
    if isinstance(params, Mapping):
        sources.append(params)
    sources.append(packet)
    shared = packet.get("shared_constraints")
    if isinstance(shared, Mapping):
        sources.append(shared)
    return sources


def _aspect(packet: Mapping[str, object]) -> str:
    for source in _aspect_sources(packet):
        found = aspect_ratio_from(source)
        if found:
            return found
    return "16:9"


def _brief(packet: Mapping[str, object]) -> str:
    brief = packet.get("brief")
    if isinstance(brief, str) and brief.strip():
        return brief.strip()
    shared = packet.get("shared_constraints")
    if isinstance(shared, Mapping):
        text = join_clauses(_string_list(shared.get("visual_identity")))
        if text:
            return text
    return "continuity-locked scene"


def _text(value: object, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _references(packet: Mapping[str, object]) -> list[str]:
    raw = packet.get("referenceImages")
    if raw is None:
        raw = packet.get("reference_images")
    return _string_list(raw)


def _one_shot(
    frame: Mapping[str, object],
    packet: Mapping[str, object],
    negatives: Sequence[str],
    index: int,
) -> tuple[dict[str, object] | None, str | None]:
    frame_id = str(frame.get("frame_id") or f"frame-{index:03d}")
    seconds, error = _duration(frame, frame_id)
    if error or seconds is None:
        return None, error or f"keyframe shot {frame_id} duration is missing"
    range_error = _range_error(frame_id, seconds)
    if range_error:
        return None, range_error
    image, video = _prompts(frame, negatives, packet_locks(packet), packet)
    from audio_screen_locks import guide_sound
    audio: dict[str, object] = {"sound": guide_sound(_sound(frame), packet.get("audio_strategy"))}
    lines = _dialogue(frame)
    if lines:
        audio["speech"] = {"mode": "native", "lines": lines}
    shot: dict[str, object] = {
        "scene": _scene(frame, packet),
        "title": _shot_title(frame, frame_id),
        "imagePrompt": image,
        "videoPrompt": video,
        "durationSeconds": _as_seconds(seconds),
        "audio": audio,
    }
    return shot, None


def _mapped_frames(frames: object) -> list[Mapping[str, object]] | str:
    if not isinstance(frames, Sequence) or isinstance(frames, (str, bytes)) or not frames:
        return "no frames available for keyframe adaptation"
    mapped: list[Mapping[str, object]] = []
    for index, frame in enumerate(frames, start=1):
        if not isinstance(frame, Mapping):
            return f"keyframe shot {index} is not an object; refusing to drop the shot"
        mapped.append(frame)
    return mapped


def _keyframe_plan(
    packet: Mapping[str, object], frames: Sequence[Mapping[str, object]],
) -> tuple[Mapping[str, object], object, list[dict[str, str | None]], list[dict[str, object]],
           list[str]]:
    from planning_fields import document_from_packet
    from shot_plan import collect_prep, merged_warnings, padding_errors, shot_directives

    document = document_from_packet(packet)
    prep = collect_prep(document, frames, "keyframe", default_duration=DEFAULT_SECONDS)
    warnings = merged_warnings(packet, prep.warnings)
    directives = shot_directives(
        frames, "keyframe", _references(packet), default_duration=DEFAULT_SECONDS,
        document=document,
    )
    blocked = [*prep.errors, *padding_errors(frames, "keyframe", DEFAULT_SECONDS, document)]
    return document, prep, warnings, directives, blocked


def _sum_planned(directives: Sequence[Mapping[str, object]]) -> float:
    total = 0.0
    for item in directives:
        value = item.get("planned_seconds")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        total += float(value)
    return total


def _needs_cut(directives: Sequence[Mapping[str, object]]) -> bool:
    for item in directives:
        if item.get("chained"):
            return True
        if item.get("source_in") not in (0, 0.0, None):
            return True
        if item.get("source_out") != item.get("generated_seconds"):
            return True
    return False


def _plan_sections(
    directives: Sequence[Mapping[str, object]],
    warnings: Sequence[Mapping[str, object]],
    techniques: object,
    prompts: Sequence[str] | None = None,
    carriers: Sequence[Mapping[str, object]] | None = None,
) -> dict[str, object]:
    from shot_plan import cut_list, dropped_references

    sections: dict[str, object] = {
        "prep_warnings": list(warnings),
        "technique_suggestions": techniques,
        "plannedDurationSeconds": _as_seconds(_sum_planned(directives)),
    }
    if prompts is not None:
        sections["planned_prompts"] = list(prompts)
    if carriers:
        sections["lock_carriers"] = [dict(item) for item in carriers]
    if _needs_cut(directives):
        sections["cut_list"] = cut_list(directives)
    if any(item.get("chained") for item in directives):
        sections["dropped_references"] = dropped_references(directives)
    return sections


def _refuse(
    message: str,
    frames: Sequence[Mapping[str, object]],
    directives: Sequence[Mapping[str, object]],
    warnings: Sequence[Mapping[str, object]],
    techniques: object,
    errors: Sequence[str] | None = None,
) -> dict[str, object]:
    from shot_plan import attach_plan

    payload = _not_computable(message)
    if errors:
        payload["errors"] = [message, *[item for item in errors if item != message]]
    prompts = [str(frame.get("prompt") or "") for frame in frames]
    attach_plan(payload, **_plan_sections(directives, warnings, techniques, prompts))
    return payload


def _apply_directive(shot: dict[str, object], directive: Mapping[str, object]) -> None:
    if "startImage" in directive:
        shot["startImage"] = directive["startImage"]
    if "referenceImages" in directive:
        shot["referenceImages"] = directive["referenceImages"]


def _with_plan_duration(
    frame: Mapping[str, object], directive: Mapping[str, object], declared: float,
) -> Mapping[str, object]:
    """Keep an invalid declared duration visible. Replace only a real planned number."""
    from shot_plan import with_generated_duration

    generated = directive.get("generated_seconds")
    if not isinstance(generated, (int, float)) or float(generated) == declared:
        return frame
    return with_generated_duration(frame, float(generated))


def build_create_movie(packet: Mapping[str, object]) -> dict[str, object]:
    from continuity_locks import reference_block, strict_enabled
    from shot_plan import attach_plan

    mapped = _mapped_frames(packet.get("frames"))
    if isinstance(mapped, str):
        return _not_computable(mapped)
    document, prep, warnings, directives, blocked = _keyframe_plan(packet, mapped)
    techniques = getattr(prep, "techniques", [])
    from spend_plan import keyframe_extras, stamp_closed

    extra, budget_error = keyframe_extras(document, mapped, directives, _aspect(packet))
    if budget_error:
        return stamp_closed(
            _refuse(budget_error, mapped, directives, warnings, techniques), budget_error, extra,
        )
    if blocked:
        return stamp_closed(
            _refuse(blocked[0], mapped, directives, warnings, techniques, blocked),
            blocked[0], extra,
        )
    negatives = _negatives(packet)
    shots: list[dict[str, object]] = []
    for index, pair in enumerate(zip(mapped, directives), start=1):
        frame, directive = pair
        shot_id = str(directive.get("shot") or index)
        declared, error = _duration(frame, shot_id)
        if error:
            return _refuse(error, mapped, directives, warnings, techniques)
        prepared = _with_plan_duration(frame, directive, cast(float, declared))
        shot, error = _one_shot(prepared, packet, negatives, index)
        if error or shot is None:
            reason = error or f"keyframe shot {index} is not computable"
            return _refuse(reason, mapped, directives, warnings, techniques)
        _apply_directive(shot, directive)
        from start_frame_gate import stamp_asset

        stamp_asset(shot, prepared)
        shots.append(shot)
    graph_id = str(packet.get("source_graph_id") or "unknown")
    movie: dict[str, object] = {
        "title": _text(packet.get("title"), f"Kubrick {graph_id}"),
        "brief": _brief(packet),
        "aspectRatio": _aspect(packet),
        "targetDurationSeconds": _as_seconds(_total_seconds(shots)),
        "qualityPreset": _preset(packet),
        "style": _text(packet.get("style"), "continuity-locked photoreal"),
        "shots": shots,
    }
    if not any(item.get("chained") for item in directives):
        refs = _references(packet)
        if refs:
            movie["referenceImages"] = refs
    from lock_carriers import lock_table

    carriers = lock_table(document, mapped)
    attach_plan(
        movie, **_plan_sections(directives, warnings, techniques, carriers=carriers), **extra,
    )
    ref_errors = reference_block(warnings, strict_enabled(document))
    if ref_errors:
        movie["validation"] = {"status": "INVALID", "errors": ref_errors}
    return movie


def adapt_keyframe_packet(packet: Mapping[str, object]) -> dict[str, object]:
    validation = packet.get("validation")
    if isinstance(validation, Mapping) and validation.get("status") not in {None, "VALID"}:
        from shot_plan import attach_plan, warnings_in

        message = "neutral adapter packet is not VALID"
        payload = _not_computable(message)
        errors = validation.get("errors")
        if isinstance(errors, Sequence) and not isinstance(errors, (str, bytes)):
            payload["errors"] = [message, *[str(item) for item in errors]]
        attach_plan(
            payload,
            prep_warnings=warnings_in(packet),
            technique_suggestions=packet.get("technique_suggestions"),
        )
        return payload
    provider = packet.get("provider")
    if provider not in {"keyframe", "generic", None}:
        return _not_computable(f"packet provider {provider} is incompatible with keyframe adapter")
    return build_create_movie(packet)
