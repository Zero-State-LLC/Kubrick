#!/usr/bin/env python3
"""Build per-frame prompts and shot contracts from a storyboard document."""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from brief_constraints import (
    attach_shot_locks,
    carried_shared,
    frame_parameters,
    string_list,
)
from prompt_text import (
    is_blank,
    node_labels,
    node_state_constraints,
    render_frame_prompt,
)

_VIDEO_NEGATIVES = ["named occult labels", "geometry reset", "residue erasure"]
_DURATION_KEYS = ("duration_seconds", "durationSeconds", "duration")


def parse_document(text: str) -> object:
    stripped = text.strip()
    if not stripped:
        return None
    if stripped[0] in "{[":
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return None
    try:
        import yaml
    except ImportError:
        return None
    try:
        return yaml.safe_load(stripped)
    except yaml.YAMLError:
        return None


def is_storyboard(data: object) -> bool:
    if not isinstance(data, Mapping):
        return False
    frames = data.get("frames")
    if not isinstance(frames, Sequence) or isinstance(frames, (str, bytes)) or not frames:
        return False
    if not all(isinstance(frame, Mapping) for frame in frames):
        return False
    has_states = any("node_states" in frame for frame in frames)
    has_prompt = any("prompt" in frame for frame in frames)
    return has_states and not has_prompt


def labels_from_document(data: Mapping[str, object]) -> dict[str, str]:
    labels: dict[str, str] = {}
    raw_labels = data.get("node_labels")
    if isinstance(raw_labels, Mapping):
        for key, value in raw_labels.items():
            if not is_blank(value):
                labels[str(key)] = str(value).strip()
    nodes = data.get("nodes")
    if isinstance(nodes, Sequence) and not isinstance(nodes, (str, bytes)):
        mappings = [node for node in nodes if isinstance(node, Mapping)]
        for key, value in node_labels(mappings).items():
            labels.setdefault(key, value)
    forms = data.get("observed_forms")
    if forms is None:
        forms = data.get("observable_evidence")
    if isinstance(forms, Sequence) and not isinstance(forms, (str, bytes)):
        _add_forms(labels, forms)
    return labels


def _add_forms(labels: dict[str, str], forms: Sequence[object]) -> None:
    for index, form in enumerate(forms, start=1):
        if isinstance(form, Mapping):
            node_id = str(form.get("id") or f"observed_{index}")
            text = form.get("observed_form") or form.get("form")
            if not is_blank(text):
                labels.setdefault(node_id, str(text).strip())
        elif not is_blank(form):
            labels.setdefault(f"observed_{index}", str(form).strip())


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _frame_duration(frame: Mapping[str, object], default: float) -> float:
    sources: list[Mapping[str, object]] = []
    params = frame.get("provider_parameters")
    if isinstance(params, Mapping):
        sources.append(params)
    sources.append(frame)
    for source in sources:
        for key in _DURATION_KEYS:
            if key not in source or source[key] in (None, ""):
                continue
            parsed = _as_float(source[key])
            return default if parsed is None else parsed
    return default


def _negatives(frame: Mapping[str, object]) -> list[str]:
    raw = frame.get("negative_constraints")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or not raw:
        return list(_VIDEO_NEGATIVES)
    return [str(item) for item in raw if not is_blank(item)]


def _residue(frame: Mapping[str, object]) -> list[str]:
    raw = frame.get("residue")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or not raw:
        raw = frame.get("residue_add")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    return [str(item) for item in raw if not is_blank(item)][:3]


def _end_summary(frame: Mapping[str, object], prompt: str) -> str:
    mutations = frame.get("required_mutations")
    if isinstance(mutations, Sequence) and not isinstance(mutations, (str, bytes)):
        for item in mutations:
            if not is_blank(item):
                return str(item).strip()
    if prompt.strip():
        return prompt.strip()
    return "evidenced frame state"


def _shared_identity(data: Mapping[str, object]) -> list[str]:
    surface = data.get("surface_output")
    if not isinstance(surface, Mapping):
        return []
    shared: list[str] = []
    for key in ("geometry", "light", "material"):
        values = surface.get(key) or []
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
            shared.extend(str(item) for item in values if not is_blank(item))
    return shared


def _provider_parameters(frame: Mapping[str, object]) -> dict[str, object]:
    return frame_parameters(frame)


def shots_from_document(
    data: Mapping[str, object],
    duration: float = 8.0,
) -> list[dict[str, object]]:
    labels = labels_from_document(data)
    frames = data.get("frames")
    shots: list[dict[str, object]] = []
    if not isinstance(frames, Sequence) or isinstance(frames, (str, bytes)):
        return shots
    source_id = str(data.get("graph_id") or data.get("storyboard_id") or "storyboard")
    for index, frame in enumerate(frames):
        if not isinstance(frame, Mapping):
            continue
        prompt = render_frame_prompt([], frame, labels) or "evidenced frame state"
        summary = _end_summary(frame, prompt)
        shot_id = str(frame.get("frame_id") or f"frame-{index + 1:03d}")
        shots.append(
            {
                "shot_id": shot_id,
                "source_state_id": source_id,
                "duration_seconds": _frame_duration(frame, duration),
                "prompt": prompt,
                "start_state": {"summary": summary, "observable": prompt},
                "action": {
                    "subject": "evidenced subject",
                    "verb": "changes",
                    "path_or_change": summary,
                },
                "camera": {"framing": "evidenced framing", "movement": "static unless evidenced"},
                "end_state": {"summary": summary, "residue": _residue(frame)},
                "continuity_invariants": ["preserve_identity", "preserve_residue"],
                "negative_constraints": _negatives(frame),
            }
        )
    _apply_document_locks(data, shots)
    return shots


def _apply_document_locks(data: Mapping[str, object], shots: list[dict[str, object]]) -> None:
    if not shots:
        return
    text = _document_text(data)
    if text is None:
        return
    for shot in shots:
        attach_shot_locks(shot, text)


def _document_text(data: Mapping[str, object]) -> str | None:
    locks = string_list(data.get("character_locks"))
    constraints = string_list(data.get("production_constraints"))
    aspect = data.get("aspect_ratio") or data.get("aspectRatio")
    if not locks and not constraints and not isinstance(aspect, str):
        return None
    payload: dict[str, object] = {}
    if locks:
        payload["character_locks"] = locks
    if constraints:
        payload["production_constraints"] = constraints
    if isinstance(aspect, str) and aspect.strip():
        payload["aspect_ratio"] = aspect.strip()
    return json.dumps(payload)


def shots_from_text(text: str | None, duration: float = 8.0) -> list[dict[str, object]] | None:
    if text is None or not str(text).strip():
        return None
    data = parse_document(str(text))
    if not is_storyboard(data) or not isinstance(data, Mapping):
        return None
    return shots_from_document(data, duration)


def adapter_packet_from_document(
    data: Mapping[str, object],
    provider: str = "generic",
) -> dict[str, object]:
    labels = labels_from_document(data)
    shared = _shared_identity(data)
    frames_out: list[dict[str, object]] = []
    raw_frames = data.get("frames")
    if isinstance(raw_frames, Sequence) and not isinstance(raw_frames, (str, bytes)):
        for index, frame in enumerate(raw_frames):
            if not isinstance(frame, Mapping):
                continue
            prompt = render_frame_prompt(shared, frame, labels) or "evidenced frame state"
            frames_out.append(
                {
                    "frame_id": str(frame.get("frame_id") or f"frame-{index + 1:03d}"),
                    "prompt": prompt,
                    "state_constraints": node_state_constraints(frame, labels),
                    "continuity_from_previous": [],
                    "provider_parameters": _provider_parameters(frame),
                }
            )
    graph_id = str(data.get("graph_id") or data.get("storyboard_id") or "storyboard")
    errors = [] if frames_out else ["no frames available for adaptation"]
    packet: dict[str, object] = {
        "schema_version": "1.0.0",
        "adapter_id": f"kubrick-{provider}-adapter-v1",
        "provider": provider,
        "source_graph_id": graph_id,
        "mode": "storyboard",
        "title": data.get("title"),
        "brief": data.get("brief"),
        "style": data.get("style"),
        "shared_constraints": {
            "visual_identity": shared,
            "continuity_rules": [
                "preserve graph identity",
                "preserve residue",
                "preserve ownership until explicitly changed",
            ],
            "prohibited_resets": [],
        },
        "frames": frames_out,
        "private_state_policy": {
            "graph_mutation_allowed": False,
            "pattern_links_exposed": False,
            "lexicon_links_exposed": False,
        },
        "validation": {
            "status": "VALID" if frames_out else "INVALID",
            "errors": errors,
            "warnings": [],
        },
    }
    constraints = packet["shared_constraints"]
    if isinstance(constraints, dict):
        constraints.update(carried_shared(data))
    return packet
