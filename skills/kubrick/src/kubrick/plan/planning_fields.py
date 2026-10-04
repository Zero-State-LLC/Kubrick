#!/usr/bin/env python3
"""Storyboard fields copied into symbolic state and adapter documents.

Issues #33–#38 add optional frame and root keys. The tuples live here so
``continuity_locks`` and ``shot_plan`` stay under 500 lines.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from kubrick.plan.brief_constraints import collect_character_locks, packet_locks

FRAME_KEYS = (
    "join",
    "opens_with",
    "prop_states",
    "characters",
    "wardrobe",
    "apply_techniques",
    "action",
    "reference_images",
    "cast",
    "start_frame",
    "counts",
    "shot_id",
    "screen_side",
    "axis_change",
    "light_states",
    "object_states",
    "keep",
    "camera",
    "cut",
    "framing",
    "end_framing",
    "continuity",
    "location_ref",
)
# Keys a plan, a storyboard frame, or an adapter frame may carry. Anything else
# warns UNKNOWN_FIELD instead of disappearing without a trace.
KNOWN_FRAME_KEYS = frozenset({
    *FRAME_KEYS,
    "frame_id",
    "ordinal",
    "node_states",
    "motif_ownership",
    "material_states",
    "residue",
    "residue_add",
    "convergence_sites",
    "required_mutations",
    "prohibited_resets",
    "allow_resets",
    "duration_seconds",
    "durationSeconds",
    "duration",
    "title",
    "scene",
    "sound",
    "audio_sound",
    "speech_lines",
    "dialogue",
    "lines",
    "speech",
    "negative_constraints",
    "prompt",
    "state_constraints",
    "continuity_from_previous",
    "provider_parameters",
    "qualityPreset",
    "quality_preset",
    "aspect_ratio",
    "aspectRatio",
    "board_measurements",
    "board_evidence",
    "ask",
    "video_prompt",
    "videoPrompt",
})
PREP_KEYS = (
    "audio_strategy",
    "budget_cap_credits",
    "model",
    "input_mode",
    "as_of",
    "drift_max_age_days",
    "capability_max_age_days",
)
ROOT_KEYS = (
    "props",
    "characters",
    "short_beat_threshold_seconds",
    "location",
    "counts",
    "locks",
    "keep",
    "delivery",
    *PREP_KEYS,
)


def planning_frame_fields(spec: Mapping[str, object]) -> dict[str, object]:
    found = {
        key: spec[key]
        for key in FRAME_KEYS
        if key != "camera" and key in spec and spec.get(key) is not None
    }
    from kubrick.prompts.film_grammar import carried_camera

    camera = carried_camera(spec.get("camera"))
    if camera:
        found["camera"] = camera
    return found


def planning_root_fields(plan: Mapping[str, object]) -> dict[str, object]:
    return {key: plan[key] for key in ROOT_KEYS if key in plan and plan.get(key) is not None}


def prep_fields(source: Mapping[str, object]) -> dict[str, object]:
    return {key: source[key] for key in PREP_KEYS if key in source and source.get(key) is not None}


def _copy_maps(source: Mapping[str, object], doc: dict[str, object], keys: Sequence[str]) -> None:
    for key in keys:
        if key not in doc and isinstance(source.get(key), Mapping):
            doc[key] = source[key]


def _copy_list(source: Mapping[str, object], doc: dict[str, object], key: str) -> None:
    value = source.get(key)
    if key in doc or isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return
    if value:
        doc[key] = list(value)


def document_from_packet(packet: Mapping[str, object]) -> dict[str, object]:
    doc: dict[str, object] = {}
    _copy_maps(packet, doc, ("characters", "props", "location", "counts"))
    _copy_list(packet, doc, "locks")
    _copy_list(packet, doc, "keep")
    locks = packet_locks(packet)
    if locks:
        doc["character_locks"] = locks
    if packet.get("strict") is True:
        doc["strict"] = True
    threshold = packet.get("short_beat_threshold_seconds")
    if isinstance(threshold, (int, float)) and not isinstance(threshold, bool):
        doc["short_beat_threshold_seconds"] = threshold
    doc.update(prep_fields(packet))
    return doc


def document_from_sources(
    graph: Mapping[str, object],
    storyboard: Mapping[str, object] | None,
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
    _copy_maps(graph, doc, ("characters", "props", "location", "counts"))
    _copy_list(graph, doc, "locks")
    if graph.get("strict") is True:
        doc["strict"] = True
    threshold = graph.get("short_beat_threshold_seconds")
    if "short_beat_threshold_seconds" not in doc and threshold is not None:
        doc["short_beat_threshold_seconds"] = threshold
    return doc
