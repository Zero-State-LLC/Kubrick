#!/usr/bin/env python3
"""Video compilers: prompt, adapt, QA, shot, motion, sequence, and timeline helpers.

Split from surface_compilers.py (#72); public names are re-exported there.
"""
from __future__ import annotations

import re
from typing import Any

from sequence_adapt import sequence_adapter_packet
from surface_common import (
    _attach_design_revision,
    _base_meta,
    _claim_bundle,
    _design_revision,
    _digest,
    _extract_brief_fields,
)
from surface_image import (
    _load_packet_document,
    _parse_surface_or_adapter_packet,
    _to_adapter_packet,
)


def _shot_dict_to_adapter_packet(shot: dict[str, Any], provider: str = "generic") -> dict[str, Any]:
    from video_packet_bridge import shot_dict_to_adapter_packet

    return shot_dict_to_adapter_packet(shot, provider, _digest)


def _sequence_packet(data: dict[str, Any]) -> tuple[dict[str, Any], float | None] | None:
    result = data.get("result")
    if not isinstance(result, dict):
        return None
    shots = result.get("shots")
    if not isinstance(shots, list) or not shots:
        return None
    return sequence_adapter_packet(shots, _shot_dict_to_adapter_packet)

def _parse_video_adapt_input(packet_text: str) -> tuple[dict[str, Any], float | None]:
    """Return adapter packet + optional duration from surface/shot/adapter input."""
    text = packet_text.strip()
    data: Any = _load_packet_document(text)
    if not isinstance(data, dict):
        raise ValueError("packet root must be an object")

    from storyboard_prompts import adapter_packet_from_document, is_storyboard

    if is_storyboard(data):
        return adapter_packet_from_document(data), None

    duration = None
    # Surface video receipt with result.shot
    if isinstance(data.get("result"), dict) and "shot" in data["result"]:
        shot = data["result"]["shot"]
        duration = shot.get("duration_seconds")
        return _shot_dict_to_adapter_packet(shot), duration
    # Raw shot contract
    if "shot_id" in data and ("start_state" in data or "end_state" in data):
        duration = data.get("duration_seconds")
        return _shot_dict_to_adapter_packet(data), duration
    sequenced = _sequence_packet(data)
    if sequenced is not None:
        return sequenced
    # Image-style packet with frames
    packet = _parse_surface_or_adapter_packet(packet_text)
    return _to_adapter_packet(packet), duration

def video_prompt(
    brief: str | None,
    evidence: str | None,
    project_id: str,
    duration: float = 8.0,
    design_text: str | None = None,
    provider: str = "generic",
) -> dict[str, Any]:
    """Compile a neutral video prompt packet from brief (+ optional design)."""
    shot_meta = video_shot(brief, evidence, project_id, duration=duration, design_text=design_text)
    if shot_meta.get("status") == "NOT_COMPUTABLE":
        shot_meta["action"] = "prompt"
        shot_meta["artifact_type"] = "video-prompt-packet"
        return shot_meta
    from provider_capabilities import capabilities_for, check_video_shot, normalize_provider

    shot = shot_meta["result"]["shot"]
    cap_warn = check_video_shot(provider, duration=float(duration))
    adapter = _shot_dict_to_adapter_packet(shot, provider=normalize_provider(provider))
    meta = _base_meta(
        "video",
        "prompt",
        project_id,
        {"brief": brief or "", "evidence": evidence or "", "provider": provider},
    )
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "provider": normalize_provider(provider),
        "capabilities": capabilities_for(provider),
        "shot": shot,
        "packet": adapter,
        "claims": shot.get("claims") or {},
    }
    if cap_warn:
        meta["result"]["capability_advisory"] = cap_warn
        # Keep provider-neutral packet; do not hard-fail prompt compile for advisory.
    meta["artifact_type"] = "video-prompt-packet"
    return _attach_design_revision(meta, design_text)

def video_adapt(packet_text: str | None, project_id: str, provider: str) -> dict[str, Any]:
    from video_packet_bridge import compile_video_adapt

    return compile_video_adapt(
        packet_text,
        project_id,
        provider,
        base_meta=_base_meta,
        digest=_digest,
        parse_input=_parse_video_adapt_input,
    )

def video_qa(expected: str | None, observation: str | None, project_id: str) -> dict[str, Any]:
    if not expected or not observation:
        return {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": "video",
            "action": "qa",
            "diagnostic": {
                "code": "INSUFFICIENT_EVIDENCE",
                "message": "Provide --input expected packet text and --evidence observation text",
            },
        }
    exp_tokens = set(re.findall(r"[a-z0-9_]{4,}", expected.lower()))
    obs_tokens = set(re.findall(r"[a-z0-9_]{4,}", observation.lower()))
    overlap = len(exp_tokens & obs_tokens) / max(1, len(exp_tokens))
    obs = observation.lower()
    dimensions = {
        "identity": overlap >= 0.2 or "identity" in obs,
        "geometry": overlap >= 0.15 or "geometry" in obs or "door" in obs,
        "residue": "residue" in obs or "crack" in obs or overlap >= 0.25,
        "motion": any(k in obs for k in ("move", "transfer", "walk", "hand", "motion")) or overlap >= 0.2,
        "timing": any(k in obs for k in ("second", "duration", "beat", "pause", "hold")) or overlap >= 0.3,
        "camera": any(k in obs for k in ("camera", "framing", "pan", "track", "static")) or overlap >= 0.25,
        "physics": any(k in obs for k in ("physics", "fall", "weight", "impact", "gravity")) or overlap >= 0.3,
        "identity_persistence": "same" in obs or "persist" in obs or "identity" in obs or overlap >= 0.25,
        "end_state": "end" in obs or "after" in obs or "final" in obs or overlap >= 0.25,
    }
    critical = ("identity", "end_state", "identity_persistence")
    critical_ok = all(dimensions[k] for k in critical)
    meta = _base_meta("video", "qa", project_id, {"expected": expected, "observation": observation})
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "overlap_ratio": round(overlap, 4),
        "qa_status": "PASS" if critical_ok and overlap >= 0.15 else "FAIL",
        "dimensions": dimensions,
    }
    meta["artifact_type"] = "media-reconciliation-report"
    if not critical_ok or overlap < 0.15:
        meta["status"] = "NOT_COMPUTABLE"
        meta["authority"] = "NOT_COMPUTABLE"
        meta["not_computable"] = [k for k in critical if not dimensions[k]]
    return meta

def video_shot(
    brief: str | None,
    evidence: str | None,
    project_id: str,
    duration: float = 8.0,
    design_text: str | None = None,
    input_text: str | None = None,
) -> dict[str, Any]:
    from video_packet_bridge import compile_video_shot

    return compile_video_shot(
        brief,
        evidence,
        project_id,
        duration,
        design_text,
        input_text,
        extract_fields=_extract_brief_fields,
        design_revision=_design_revision,
        claim_bundle=_claim_bundle,
        digest=_digest,
        base_meta=_base_meta,
        attach=_attach_design_revision,
    )

def video_motion(brief: str | None, project_id: str) -> dict[str, Any]:
    fields = _extract_brief_fields(brief, None)
    if not fields["raw"]:
        return {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": "video",
            "action": "motion",
            "diagnostic": {"code": "INSUFFICIENT_EVIDENCE", "message": "Provide --brief"},
        }
    meta = _base_meta("video", "motion", project_id, fields)
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "motion_contract": {
            "blocking": fields["dramatic_problem"],
            "object_motion": fields["desired_state_change"] or "NOT_COMPUTABLE",
            "camera_motion": "static unless evidenced",
            "physical_behavior": [],
            "forbidden_motion": ["teleportation", "identity swap", "residue erasure"],
            "rhythm": "NOT_COMPUTABLE",
        },
    }
    meta["artifact_type"] = "motion-contract"
    return meta

def video_sequence(
    brief: str | None,
    evidence: str | None,
    project_id: str,
    design_text: str | None = None,
) -> dict[str, Any]:
    shot_a = video_shot(brief, evidence, project_id, duration=4.0, design_text=design_text)
    if shot_a.get("status") == "NOT_COMPUTABLE":
        shot_a["action"] = "sequence"
        return shot_a
    shot1 = shot_a["result"]["shot"]
    # Second shot must start from shot1 end_state
    shot2 = dict(shot1)
    shot2["shot_id"] = f"shot-{_digest(shot1['shot_id'] + '|2')}"
    shot2["start_state"] = dict(shot1["end_state"])
    shot2["end_state"] = {
        "summary": (shot1["end_state"].get("summary") or "") + " with visible residue retained",
        "residue": list((shot1.get("end_state") or {}).get("residue") or []),
    }
    # Compatibility proof
    compatible = shot2["start_state"].get("summary") == shot1["end_state"].get("summary")
    if not compatible:
        return {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": "video",
            "action": "sequence",
            "diagnostic": {
                "code": "INCOMPATIBLE_TRANSITION",
                "message": "shot end_state/start_state mismatch",
            },
        }
    meta = _base_meta("video", "sequence", project_id, {"brief": brief or "", "evidence": evidence or ""})
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "shots": [shot1, shot2],
        "transitions": [
            {
                "from": shot1["shot_id"],
                "to": shot2["shot_id"],
                "compatible": True,
            }
        ],
        "claims": shot1.get("claims") or {},
    }
    meta["artifact_type"] = "video-sequence-packet"
    return _attach_design_revision(meta, design_text)

def video_blocking(brief: str | None, project_id: str) -> dict[str, Any]:
    motion = video_motion(brief, project_id)
    motion["action"] = "blocking"
    if motion.get("result"):
        motion["result"]["blocking_mode"] = "spatial"
    return motion

def video_transition(
    brief: str | None, evidence: str | None, project_id: str, design_text: str | None = None
) -> dict[str, Any]:
    seq = video_sequence(brief, evidence, project_id, design_text=design_text)
    if seq.get("status") == "NOT_COMPUTABLE":
        seq["action"] = "transition"
        return seq
    seq["action"] = "transition"
    transitions = seq["result"].get("transitions") or []
    for t in transitions:
        t["type"] = "cut" if t.get("compatible") else "NOT_COMPUTABLE"
    return seq

def video_animation(brief: str | None, project_id: str) -> dict[str, Any]:
    motion = video_motion(brief, project_id)
    if motion.get("status") == "NOT_COMPUTABLE":
        motion["action"] = "animation"
        return motion
    motion["action"] = "animation"
    motion["result"]["animation_prompt"] = {
        "subject_motion": (motion["result"].get("motion_contract") or {}).get("object_motion"),
        "camera_motion": (motion["result"].get("motion_contract") or {}).get("camera_motion"),
        "forbidden": (motion["result"].get("motion_contract") or {}).get("forbidden_motion"),
    }
    return motion

def video_timeline(
    brief: str | None, evidence: str | None, project_id: str, design_text: str | None = None
) -> dict[str, Any]:
    seq = video_sequence(brief, evidence, project_id, design_text=design_text)
    if seq.get("status") == "NOT_COMPUTABLE":
        seq["action"] = "timeline"
        return seq
    shots = seq["result"].get("shots") or []
    cursor = 0.0
    timeline = []
    for shot in shots:
        dur = float(shot.get("duration_seconds") or 4.0)
        timeline.append(
            {
                "shot_id": shot.get("shot_id"),
                "start_seconds": cursor,
                "end_seconds": cursor + dur,
                "end_state": shot.get("end_state"),
            }
        )
        cursor += dur
    seq["action"] = "timeline"
    seq["result"]["timeline"] = timeline
    seq["result"]["total_duration_seconds"] = cursor
    seq["artifact_type"] = "video-sequence-packet"
    return seq

def video_continuity_track(
    brief: str | None, evidence: str | None, project_id: str, design_text: str | None = None
) -> dict[str, Any]:
    seq = video_sequence(brief, evidence, project_id, design_text=design_text)
    if seq.get("status") == "NOT_COMPUTABLE":
        seq["action"] = "continuity"
        return seq
    seq["action"] = "continuity"
    seq["result"]["continuity_tracking"] = {
        "compatible_transitions": all(t.get("compatible") for t in seq["result"].get("transitions") or []),
        "shared_invariants": ["preserve_identity", "preserve_residue", "preserve_geometry"],
    }
    return seq
