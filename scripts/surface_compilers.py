#!/usr/bin/env python3
"""Domain compilers for Kubrick first-class production surfaces (v0.15).

Deterministic, fail-closed, proposal-only. Emits readable design.md plus
structured packets for script/image/video without inventing unsupported detail.
"""
from __future__ import annotations

from typing import Any

from surface_common import (
    DESIGN_SECTIONS,
    REVISION_RE,
    SECTION_RE,
    parse_design_md,
    render_design_md,
    resolve_design_text,
)
from surface_design import (
    design_audit,
    design_create,
    design_improve,
    design_reconcile,
    design_update,
    design_validate,
)
from surface_design_extra import (
    design_drift,
    design_expand,
    design_qa,
    design_summarize,
)
from surface_image import (
    image_adapt,
    image_batch,
    image_camera_analysis,
    image_composition_analysis,
    image_generate,
    image_improve,
    image_lighting_analysis,
    image_negative,
    image_prompt,
    image_qa,
    image_reference,
    image_sequence,
    image_symbol_extract,
)
from surface_script import (
    script_adapt,
    script_continuity,
    script_create,
    script_diagnose,
    script_handoff,
    script_improve,
)
from surface_script_extra import (
    script_beat_validate,
    script_character_consistency,
    script_compress,
    script_dialog_validate,
    script_expand,
    script_genre_validate,
    script_qa,
    script_rewrite,
    script_scene_extract,
)
from surface_video import (
    _parse_video_adapt_input,
    _shot_dict_to_adapter_packet,
    video_adapt,
    video_animation,
    video_blocking,
    video_continuity_track,
    video_motion,
    video_prompt,
    video_qa,
    video_sequence,
    video_shot,
    video_timeline,
    video_transition,
)

__all__ = [
    "DESIGN_SECTIONS",
    "REVISION_RE",
    "SECTION_RE",
    "_parse_video_adapt_input",
    "_shot_dict_to_adapter_packet",
    "design_audit",
    "design_create",
    "design_drift",
    "design_expand",
    "design_improve",
    "design_qa",
    "design_reconcile",
    "design_summarize",
    "design_update",
    "design_validate",
    "image_adapt",
    "image_batch",
    "image_camera_analysis",
    "image_composition_analysis",
    "image_generate",
    "image_improve",
    "image_lighting_analysis",
    "image_negative",
    "image_prompt",
    "image_qa",
    "image_reference",
    "image_sequence",
    "image_symbol_extract",
    "parse_design_md",
    "render_design_md",
    "resolve_design_text",
    "script_adapt",
    "script_beat_validate",
    "script_character_consistency",
    "script_compress",
    "script_continuity",
    "script_create",
    "script_diagnose",
    "script_dialog_validate",
    "script_expand",
    "script_genre_validate",
    "script_handoff",
    "script_improve",
    "script_qa",
    "script_rewrite",
    "script_scene_extract",
    "video_adapt",
    "video_animation",
    "video_blocking",
    "video_continuity_track",
    "video_motion",
    "video_prompt",
    "video_qa",
    "video_sequence",
    "video_shot",
    "video_timeline",
    "video_transition",
    "COMPILERS",
    "compile_surface",
]


def _design_for_args(a: Any) -> str | None:
    return resolve_design_text(
        _read(a, "design"),
        _read(a, "input"),
        _read(a, "evidence"),
        auto_discover=True,
    )

COMPILERS: dict[tuple[str, str], Any] = {
    ("design", "create"): lambda a: design_create(a.brief, _read(a, "evidence"), a.project_id),
    ("design", "build"): lambda a: design_create(a.brief, _read(a, "evidence"), a.project_id),
    ("design", "improve"): lambda a: design_improve(_read(a, "input") or "", _read(a, "evidence"), a.project_id),
    ("design", "audit"): lambda a: design_audit(_read(a, "input") or "", _read(a, "evidence"), a.project_id),
    ("design", "reconcile"): lambda a: design_reconcile(_read(a, "input") or "", _read(a, "evidence"), a.project_id),
    ("design", "drift"): lambda a: design_drift(_read(a, "input") or "", _read(a, "evidence"), a.project_id),
    ("design", "update"): lambda a: design_update(_read(a, "input") or "", _read(a, "evidence"), a.project_id),
    ("design", "validate"): lambda a: design_validate(_read(a, "input") or "", a.project_id),
    ("script", "create"): lambda a: script_create(
        a.brief,
        _read(a, "evidence"),
        a.project_id,
        getattr(a, "format", "markdown"),
        design_text=_design_for_args(a),
    ),
    ("script", "improve"): lambda a: script_improve(_read(a, "input") or "", a.project_id),
    ("script", "diagnose"): lambda a: script_diagnose(_read(a, "input") or "", a.project_id),
    ("script", "adapt"): lambda a: script_adapt(_read(a, "input") or "", a.project_id),
    ("script", "continuity-check"): lambda a: script_continuity(_read(a, "input") or "", a.project_id),
    ("script", "handoff"): lambda a: script_handoff(_read(a, "input") or "", a.project_id),
    ("image", "prompt"): lambda a: image_prompt(
        a.brief,
        _read(a, "evidence"),
        _design_for_args(a) or _read(a, "input"),
        a.project_id,
        a.provider,
    ),
    ("image", "sequence"): lambda a: image_sequence(a.brief, _read(a, "evidence"), a.project_id, a.provider),
    ("image", "reference"): lambda a: image_reference(a.brief or _read(a, "input"), a.project_id, a.provider),
    ("image", "negative"): lambda a: image_negative(a.brief or _read(a, "input"), a.project_id),
    ("image", "adapt"): lambda a: image_adapt(_read(a, "input"), a.project_id, a.provider),
    ("image", "qa"): lambda a: image_qa(_read(a, "input"), _read(a, "evidence"), a.project_id),
    ("video", "shot"): lambda a: video_shot(
        a.brief,
        _read(a, "evidence"),
        a.project_id,
        getattr(a, "duration", 8.0),
        design_text=_design_for_args(a),
        input_text=_read(a, "input"),
    ),
    ("video", "prompt"): lambda a: video_prompt(
        a.brief,
        _read(a, "evidence"),
        a.project_id,
        getattr(a, "duration", 8.0),
        design_text=_design_for_args(a),
        provider=getattr(a, "provider", "generic"),
    ),
    ("video", "motion"): lambda a: video_motion(a.brief or _read(a, "input"), a.project_id),
    ("video", "sequence"): lambda a: video_sequence(
        a.brief, _read(a, "evidence"), a.project_id, design_text=_design_for_args(a)
    ),
    ("video", "adapt"): lambda a: video_adapt(_read(a, "input"), a.project_id, a.provider),
    ("video", "qa"): lambda a: video_qa(_read(a, "input"), _read(a, "evidence"), a.project_id),
    # --- v0.16 expansions (compose existing compilers; no parallel systems) ---
    ("design", "expand"): lambda a: design_expand(_read(a, "input") or "", _read(a, "evidence"), a.project_id),
    ("design", "summarize"): lambda a: design_summarize(_read(a, "input") or "", a.project_id),
    ("design", "qa"): lambda a: design_qa(_read(a, "input") or "", _read(a, "evidence"), a.project_id),
    ("script", "rewrite"): lambda a: script_rewrite(_read(a, "input") or "", a.project_id),
    ("script", "expand"): lambda a: script_expand(_read(a, "input") or "", a.project_id),
    ("script", "compress"): lambda a: script_compress(_read(a, "input") or "", a.project_id),
    ("script", "continuity"): lambda a: script_continuity(_read(a, "input") or "", a.project_id),
    ("script", "scene-extract"): lambda a: script_scene_extract(_read(a, "input") or "", a.project_id),
    ("script", "beat-validate"): lambda a: script_beat_validate(_read(a, "input") or "", a.project_id),
    ("script", "character-consistency"): lambda a: script_character_consistency(
        _read(a, "input") or "", a.project_id
    ),
    ("script", "dialog-validate"): lambda a: script_dialog_validate(_read(a, "input") or "", a.project_id),
    ("script", "genre-validate"): lambda a: script_genre_validate(
        _read(a, "input") or "", _read(a, "evidence"), a.project_id
    ),
    ("script", "qa"): lambda a: script_qa(_read(a, "input") or "", _read(a, "evidence"), a.project_id),
    ("image", "generate"): lambda a: image_generate(
        a.brief, _read(a, "evidence"), _design_for_args(a) or _read(a, "input"), a.project_id, a.provider
    ),
    ("image", "improve"): lambda a: image_improve(_read(a, "input") or "", a.project_id, a.provider),
    ("image", "composition"): lambda a: image_composition_analysis(_read(a, "input") or a.brief or "", a.project_id),
    ("image", "lighting"): lambda a: image_lighting_analysis(_read(a, "input") or a.brief or "", a.project_id),
    ("image", "camera"): lambda a: image_camera_analysis(_read(a, "input") or a.brief or "", a.project_id),
    ("image", "symbol-extract"): lambda a: image_symbol_extract(_read(a, "input") or a.brief or "", a.project_id),
    ("image", "batch"): lambda a: image_batch(
        a.brief, _read(a, "evidence"), a.project_id, a.provider
    ),
    ("video", "blocking"): lambda a: video_blocking(a.brief or _read(a, "input"), a.project_id),
    ("video", "transition"): lambda a: video_transition(
        a.brief, _read(a, "evidence"), a.project_id, design_text=_design_for_args(a)
    ),
    ("video", "animation"): lambda a: video_animation(a.brief or _read(a, "input"), a.project_id),
    ("video", "timeline"): lambda a: video_timeline(
        a.brief, _read(a, "evidence"), a.project_id, design_text=_design_for_args(a)
    ),
    ("video", "continuity"): lambda a: video_continuity_track(
        a.brief, _read(a, "evidence"), a.project_id, design_text=_design_for_args(a)
    ),
}

def _read(args: Any, name: str) -> str | None:
    # filled by production_surface before dispatch via setattr
    return getattr(args, f"_loaded_{name}", None)

def compile_surface(surface: str, action: str, args: Any) -> dict[str, Any]:
    key = (surface, action)
    if key not in COMPILERS:
        return {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": surface,
            "action": action,
            "diagnostic": {"code": "UNKNOWN_ACTION", "message": f"No domain compiler for {surface}:{action}"},
        }
    return COMPILERS[key](args)
