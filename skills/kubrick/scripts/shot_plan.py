#!/usr/bin/env python3
"""Shot prep for short beats, joins, hold, and techniques. Issues #25–#27 and #31."""
from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from brief_constraints import collect_character_locks, frame_parameters, packet_locks
from continuity_locks import (
    frame_field,
    frame_id,
    planning_frame_fields,
    planning_root_fields,
    prop_assignments,
    reference_warnings,
    render_with_locks,
    wardrobe_lines,
    warning,
)

_ROOT = Path(__file__).resolve().parent.parent
_TECHNIQUE_PATH = _ROOT / "assets" / "techniques" / "techniques.yaml"
_TECHNIQUE_SCHEMA = _ROOT / "schemas" / "techniques.schema.json"
_EXIT_PHRASES = ("walks out", "walk out", "leaves frame", "leave frame")
_EXIT_WORDS = {"exit", "exits", "walks out", "leaves frame"}
_PROVIDER_CODES = {"SHORT_BEAT", "KNOWN_DRIFT"}
Render = Callable[[Mapping[str, object]], str]

@dataclass(frozen=True)
class Prep:
    warnings: list[dict[str, str | None]]
    errors: list[str]
    locks: dict[str, list[str]]
    opted: dict[str, list[str]]
    techniques: list[dict[str, object]]
def _capabilities(provider: str) -> Mapping[str, object]:
    from provider_capabilities import capabilities_for
    caps = capabilities_for(provider)
    return caps if isinstance(caps, Mapping) else {}
def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except ValueError:
        return None
def _seconds_text(value: float) -> str:
    rounded = round(float(value), 4)
    return str(int(rounded)) if float(rounded).is_integer() else str(rounded)
def _string_list(value: object) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
def _duration(frame: Mapping[str, object], default: float) -> float:
    for key in ("duration_seconds", "durationSeconds", "duration"):
        parsed = _as_float(frame_field(frame, key))
        if parsed is not None:
            return parsed
    return default
def _threshold(provider: str, document: Mapping[str, object] | None) -> float:
    if document is not None:
        override = _as_float(document.get("short_beat_threshold_seconds"))
        if override is not None:
            return override
    parsed = _as_float(_capabilities(provider).get("short_beat_threshold_seconds"))
    return 2.0 if parsed is None else parsed

def short_beat_warnings(
    frames: Sequence[Mapping[str, object]],
    provider: str,
    *,
    document: Mapping[str, object] | None = None,
    default_duration: float = 8.0,
) -> list[dict[str, str | None]]:
    caps = _capabilities(provider)
    if not caps.get("is_multi_shot_single_clip") or len(frames) < 2:
        return []
    limit = _threshold(provider, document)
    minimum = _as_float(caps.get("min_duration_seconds"))
    floor = _seconds_text(minimum) if minimum is not None else "the provider minimum"
    found: list[dict[str, str | None]] = []
    for index, frame in enumerate(frames, start=1):
        duration = _duration(frame, default_duration)
        if duration > limit:
            continue
        shot, shown = frame_id(frame, index), _seconds_text(duration)
        found.append(warning(
            "SHORT_BEAT", shot,
            (
                f"shot {shot} is {shown}s, at or below the {_seconds_text(limit)}s "
                "short-beat threshold; a multi-shot single clip absorbs a beat this short"
            ),
            (
                f"generate {shot} as its own separate clip at the provider minimum "
                f"of {floor}s, then trim"
            ),
        ))
    return found

def chain_source(frame: Mapping[str, object]) -> str | None:
    raw = frame_field(frame, "join")
    if isinstance(raw, Mapping):
        source = raw.get("chain_from")
        if isinstance(source, str) and source.strip():
            return source.strip()
    return None
def _at_seconds(raw: Mapping[str, object]) -> tuple[float | None, str | None]:
    if "at_seconds" not in raw or raw.get("at_seconds") is None:
        return None, None
    parsed = _as_float(raw.get("at_seconds"))
    return (parsed, None) if parsed is not None else (None, "at_seconds is not a number")
def _join_errors(
    frame: Mapping[str, object], shot: str, index: int, position: Mapping[str, int],
) -> list[str]:
    raw = frame_field(frame, "join")
    if raw is None or raw == "cut":
        return []
    if not isinstance(raw, Mapping) or "chain_from" not in raw:
        return [f"shot {shot} join must be cut or chain_from"]
    _at, at_error = _at_seconds(raw)
    if at_error:
        return [f"shot {shot} {at_error}"]
    source = chain_source(frame)
    if source is None:
        return [f"shot {shot} chain_from is missing"]
    if source not in position:
        return [f"shot {shot} chain_from {source} is an unknown frame"]
    if source == shot:
        return [f"shot {shot} chain_from names the same frame"]
    if position[source] > index:
        return [f"shot {shot} chain_from {source} names a later frame"]
    return []
def validate_joins(frames: Sequence[Mapping[str, object]]) -> list[str]:
    ids = [frame_id(frame, index) for index, frame in enumerate(frames, start=1)]
    position = {shot: index for index, shot in enumerate(ids)}
    errors: list[str] = []
    for index, frame in enumerate(frames):
        errors.extend(_join_errors(frame, ids[index], index, position))
    return errors
def _leading_action(frame: Mapping[str, object]) -> str:
    for key in ("action", "prompt"):
        value = frame_field(frame, key)
        if isinstance(value, str) and value.strip():
            return value.split(";", 1)[0]
    return ""
def opens_with_exit(frame: Mapping[str, object]) -> bool:
    declared = frame_field(frame, "opens_with")
    if isinstance(declared, str) and declared.strip().casefold() in _EXIT_WORDS:
        return True
    folded = _leading_action(frame).casefold()
    if re.search(r"\bexits\b", folded):
        return True
    return any(phrase in folded for phrase in _EXIT_PHRASES)
def _positive_bound(provider: str, key: str) -> float:
    parsed = _as_float(_capabilities(provider).get(key))
    if parsed is None or parsed <= 0:
        return 0.0
    return parsed
def generation_seconds(
    planned: float, *, chained: bool, exit_open: bool, provider: str,
) -> tuple[float, float]:
    """Generated length is the padded plan, raised to the provider minimum."""
    hold = _positive_bound(
        provider, "start_frame_hold_seconds") if chained and not exit_open else 0.0
    floor = _positive_bound(provider, "min_duration_seconds")
    return round(max(planned + hold, floor), 4), hold
def padding_error(shot: str, generated: float, provider: str, *, hold: float) -> str | None:
    if hold <= 0:
        return None
    maximum = _as_float(_capabilities(provider).get("max_duration_seconds"))
    if maximum is None or maximum <= 0 or generated <= maximum:
        return None
    return (
        f"shot {shot} padded duration {_seconds_text(generated)}s exceeds "
        f"{provider} maximum {_seconds_text(maximum)}s; refusing to clamp or drop the shot"
    )
def padding_errors(
    frames: Sequence[Mapping[str, object]], provider: str, default_duration: float,
) -> list[str]:
    errors: list[str] = []
    for index, frame in enumerate(frames, start=1):
        planned = _duration(frame, default_duration)
        generated, hold = generation_seconds(
            planned, chained=chain_source(frame) is not None,
            exit_open=opens_with_exit(frame), provider=provider,
        )
        message = padding_error(frame_id(frame, index), generated, provider, hold=hold)
        if message:
            errors.append(message)
    return errors
def frame_references(frame: Mapping[str, object]) -> list[str]:
    for key in ("reference_images", "referenceImages"):
        found = _string_list(frame_field(frame, key))
        if found:
            return found
    return []

def load_techniques(path: Path | None = None) -> dict[str, object]:
    import json

    import jsonschema
    import yaml
    loaded = yaml.safe_load((path or _TECHNIQUE_PATH).read_text(encoding="utf-8"))
    schema = json.loads(_TECHNIQUE_SCHEMA.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("technique library must be an object")
    jsonschema.validate(loaded, schema)
    return loaded
def _library() -> list[Mapping[str, object]]:
    raw = load_techniques().get("techniques")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    return [item for item in raw if isinstance(item, Mapping)]
def _names(frame: Mapping[str, object]) -> list[str] | None:
    raw = frame_field(frame, "characters")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return None
    return [str(item).strip() for item in raw if str(item).strip()]
def _removes_character(frame: Mapping[str, object], frames: Sequence[Mapping[str, object]]) -> bool:
    source = chain_source(frame)
    current = _names(frame)
    if source is None or current is None:
        return False
    prior = next(
        (item for i, item in enumerate(frames, start=1) if frame_id(item, i) == source),
        None,
    )
    before = _names(prior) if isinstance(prior, Mapping) else None
    if not before:
        return False
    return len(current) < len(before) or bool(set(before) - set(current))
def _verb(text: str, verbs: Sequence[object]) -> bool:
    folded = text.casefold()
    for verb in verbs:
        token = str(verb).casefold().strip()
        if token and re.search(rf"\b{re.escape(token)}\b", folded):
            return True
    return False
def _blob(frame: Mapping[str, object]) -> str:
    return " ".join(
        value for key in ("action", "prompt")
        if isinstance(value := frame_field(frame, key), str)
    )
def _technique_matches(
    technique: Mapping[str, object], frame: Mapping[str, object],
    frames: Sequence[Mapping[str, object]], provider: str,
) -> bool:
    providers = technique.get("providers")
    if isinstance(providers, Sequence) and not isinstance(providers, (str, bytes)):
        if provider not in {str(item) for item in providers}:
            return False
    triggers = technique.get("triggers")
    if not isinstance(triggers, Mapping):
        return False
    if "chained" in triggers and bool(triggers.get("chained")) != (chain_source(frame) is not None):
        return False
    if triggers.get("fewer_characters_than_start") and not _removes_character(frame, frames):
        return False
    verbs = triggers.get("motion_verbs")
    if isinstance(verbs, Sequence) and not isinstance(verbs, (str, bytes)) and verbs:
        return _verb(_blob(frame), verbs)
    return True
def match_techniques(
    frames: Sequence[Mapping[str, object]], provider: str,
) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for index, frame in enumerate(frames, start=1):
        shot = frame_id(frame, index)
        opted = set(_string_list(frame_field(frame, "apply_techniques")))
        for technique in _library():
            if not _technique_matches(technique, frame, frames, provider):
                continue
            tech_id = str(technique.get("id") or "")
            found.append({
                "id": tech_id, "shot": shot, "intent": str(technique.get("intent") or ""),
                "prompt_template": str(technique.get("prompt_template") or ""),
                "trim_guidance": str(technique.get("trim_guidance") or ""),
                "evidence": str(technique.get("evidence") or ""), "applied": tech_id in opted,
            })
    return found
def opted_clauses(
    suggestions: Sequence[Mapping[str, object]], shot: str, wanted: Sequence[str],
) -> list[str]:
    needed = set(wanted)
    clauses: list[str] = []
    for item in suggestions:
        template = str(item.get("prompt_template") or "").strip()
        same = str(item.get("shot") or "") == shot and item.get("applied") is True
        if same and str(item.get("id") or "") in needed and template and template not in clauses:
            clauses.append(template)
    return clauses
def collect_prep(
    document: Mapping[str, object], frames: Sequence[Mapping[str, object]], provider: str,
    *, extra_locks: Sequence[str] = (), default_duration: float = 8.0,
) -> Prep:
    merged = dict(document)
    locks = _string_list(document.get("character_locks"))
    locks.extend(str(item) for item in extra_locks if str(item).strip())
    if locks:
        merged["character_locks"] = list(dict.fromkeys(locks))
    prop_lines, prop_errors = prop_assignments(merged, frames)
    techniques = match_techniques(frames, provider)
    lock_map: dict[str, list[str]] = {}
    opted: dict[str, list[str]] = {}
    for index, frame in enumerate(frames, start=1):
        shot = frame_id(frame, index)
        lock_map[shot] = [*wardrobe_lines(merged, frame), *prop_lines.get(shot, [])]
        wanted = _string_list(frame_field(frame, "apply_techniques"))
        opted[shot] = opted_clauses(techniques, shot, wanted)
    from continuity_locks import drift_warnings
    raw_drift = _capabilities(provider).get("known_drift")
    entries: list[Mapping[str, object]] = []
    if isinstance(raw_drift, Sequence) and not isinstance(raw_drift, (str, bytes)):
        entries = [item for item in raw_drift if isinstance(item, Mapping)]
    warnings = [
        *short_beat_warnings(frames, provider, document=merged, default_duration=default_duration),
        *drift_warnings(merged, frames, provider, entries),
        *reference_warnings(merged),
    ]
    return Prep(warnings, [*validate_joins(frames), *prop_errors], lock_map, opted, techniques)
def enrich_prompts(
    document: Mapping[str, object], frames: Sequence[Mapping[str, object]], provider: str,
    render: Render, *, extra_locks: Sequence[str] = (), default_duration: float = 8.0,
) -> tuple[list[str], Prep]:
    prep = collect_prep(
        document, frames, provider, extra_locks=extra_locks, default_duration=default_duration,
    )
    prompts = [
        render_with_locks(
            str(render(frame) or ""),
            prep.locks.get(frame_id(frame, index), []),
            prep.opted.get(frame_id(frame, index), []),
        )
        for index, frame in enumerate(frames, start=1)
    ]
    return prompts, prep

def exclusivity_reason(provider: str, shot: str) -> str | None:
    caps = _capabilities(provider)
    groups = caps.get("exclusive_inputs")
    notes = caps.get("exclusivity_notes")
    if not isinstance(groups, Sequence) or isinstance(groups, (str, bytes)):
        return None
    if not isinstance(notes, Mapping):
        return None
    paired = any(
        isinstance(group, Sequence) and not isinstance(group, (str, bytes))
        and {"startImage", "referenceImages"} <= {str(item) for item in group}
        for group in groups
    )
    template = notes.get("startImage|referenceImages")
    if not paired or not isinstance(template, str) or not template.strip():
        return None
    return template.format(shot=shot)
def _one_directive(
    frame: Mapping[str, object], index: int, provider: str, movie_refs: Sequence[str],
    chained_any: bool, default_duration: float,
) -> dict[str, object]:
    shot, source = frame_id(frame, index), chain_source(frame)
    planned = _duration(frame, default_duration)
    generated, hold = generation_seconds(
        planned, chained=source is not None, exit_open=opens_with_exit(frame), provider=provider,
    )
    own = frame_references(frame)
    directive: dict[str, object] = {
        "shot": shot,
        "planned_seconds": planned,
        "generated_seconds": generated,
        "hold_seconds": hold,
        "source_in": hold,
        "source_out": round(hold + planned, 4),
        "chained": source is not None,
    }
    if source is None:
        if own or (chained_any and (own or list(movie_refs))):
            directive["referenceImages"] = own or list(movie_refs)
        return directive
    image: dict[str, object] = {"sourceFrame": source}
    raw = frame_field(frame, "join")
    if isinstance(raw, Mapping):
        at, _error = _at_seconds(raw)
        if at is not None:
            image["atSeconds"] = at
    directive["startImage"] = image
    directive["dropped_references"] = own or list(movie_refs)
    reason = exclusivity_reason(provider, shot)
    if reason:
        directive["reason"] = reason
    return directive
def shot_directives(
    frames: Sequence[Mapping[str, object]], provider: str, movie_refs: Sequence[str], *,
    default_duration: float = 8.0,
) -> list[dict[str, object]]:
    chained_any = any(chain_source(frame) is not None for frame in frames)
    return [
        _one_directive(frame, index, provider, movie_refs, chained_any, default_duration)
        for index, frame in enumerate(frames, start=1)
    ]
def cut_list(directives: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    keys = ("shot", "source_in", "source_out", "planned_seconds", "generated_seconds")
    return [{key: item.get(key) for key in keys} for item in directives]
def dropped_references(directives: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    dropped: list[dict[str, object]] = []
    for item in directives:
        if "dropped_references" not in item:
            continue
        dropped.append({
            "shot": item.get("shot"),
            "references": _string_list(item.get("dropped_references")),
            "reason": str(item.get("reason") or ""),
        })
    return dropped

def with_generated_duration(frame: Mapping[str, object], generated: float) -> dict[str, object]:
    prepared = dict(frame)
    params = frame.get("provider_parameters")
    copied = dict(params) if isinstance(params, Mapping) else {}
    copied["duration_seconds"] = generated
    prepared["provider_parameters"] = copied
    return prepared
def attach_plan(payload: dict[str, object], **sections: object) -> None:
    for key, value in sections.items():
        if value not in (None, [], {}):
            payload[key] = value
def prompted_parameters(frame: Mapping[str, object]) -> dict[str, object]:
    merged = frame_parameters(frame)
    for key, value in planning_frame_fields(frame).items():
        merged.setdefault(key, value)
    return merged
def dedupe_warnings(items: Sequence[Mapping[str, object]]) -> list[dict[str, str | None]]:
    seen: set[tuple[str, str, str]] = set()
    ordered: list[dict[str, str | None]] = []
    for item in items:
        code = str(item.get("code") or "")
        raw_shot = item.get("shot")
        shot = None if raw_shot is None else str(raw_shot)
        message = str(item.get("message") or "")
        key = (code, shot or "", message)
        if not code or key in seen:
            continue
        seen.add(key)
        raw_character = item.get("character")
        character = raw_character if isinstance(raw_character, str) else None
        ordered.append(warning(
            code, shot, message, str(item.get("recommendation") or ""), character=character,
        ))
    return ordered
def warnings_in(data: object) -> list[dict[str, str | None]]:
    if not isinstance(data, Mapping):
        return []
    raw = data.get("prep_warnings")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    return dedupe_warnings([item for item in raw if isinstance(item, Mapping)])
def merged_warnings(
    packet: Mapping[str, object], fresh: Sequence[Mapping[str, object]],
) -> list[dict[str, str | None]]:
    kept = [item for item in warnings_in(packet) if item.get("code") not in _PROVIDER_CODES]
    return dedupe_warnings([*kept, *fresh])
def _copy_maps(source: Mapping[str, object], doc: dict[str, object], keys: Sequence[str]) -> None:
    for key in keys:
        if key not in doc and isinstance(source.get(key), Mapping):
            doc[key] = source[key]

def document_from_packet(packet: Mapping[str, object]) -> dict[str, object]:
    doc: dict[str, object] = {}
    _copy_maps(packet, doc, ("characters", "props"))
    locks = packet_locks(packet)
    if locks:
        doc["character_locks"] = locks
    if packet.get("strict") is True:
        doc["strict"] = True
    threshold = packet.get("short_beat_threshold_seconds")
    if isinstance(threshold, (int, float)) and not isinstance(threshold, bool):
        doc["short_beat_threshold_seconds"] = threshold
    return doc
def document_from_sources(
    graph: Mapping[str, object], storyboard: Mapping[str, object] | None,
) -> dict[str, object]:
    doc: dict[str, object] = {}
    locks = collect_character_locks(graph)
    if isinstance(storyboard, Mapping):
        doc.update(planning_root_fields(storyboard))
        if storyboard.get("strict") is True:
            doc["strict"] = True
        locks.extend(collect_character_locks(storyboard))
    if locks:
        doc["character_locks"] = list(dict.fromkeys(locks))
    _copy_maps(graph, doc, ("characters", "props"))
    if graph.get("strict") is True:
        doc["strict"] = True
    threshold = graph.get("short_beat_threshold_seconds")
    if "short_beat_threshold_seconds" not in doc and threshold is not None:
        doc["short_beat_threshold_seconds"] = threshold
    return doc
