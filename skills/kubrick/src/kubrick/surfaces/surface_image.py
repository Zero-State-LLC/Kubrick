#!/usr/bin/env python3
"""Image compilers: prompt, sequence, reference, negative, QA, adapt, and analysis.

Split from surface_compilers.py (#72); public names are re-exported there.
"""
from __future__ import annotations

import json
import re
from typing import Any

from kubrick.surfaces.surface_common import (
    _attach_design_revision,
    _base_meta,
    _claim_bundle,
    _digest,
    _extract_brief_fields,
)


def _neutral_frame_from_text(text: str, provider: str) -> dict[str, Any]:
    fields = _extract_brief_fields(text, None)
    parts = [fields["dramatic_problem"] or text.strip().splitlines()[0][:280]]
    for item in (fields.get("geometry") or [])[:2]:
        parts.append(item)
    for item in (fields.get("cinematic_channel") or [])[:1]:
        parts.append(item)
    for item in (fields.get("residue") or [])[:1]:
        parts.append(f"residue: {item}")
    prompt = "; ".join(p for p in parts if p)
    negatives = [
        "named occult labels",
        "unsupported location changes",
        "identity reset",
        "residue erasure",
    ]
    constraints = [
        c
        for c in (
            fields["desired_state_change"],
            fields["character_pressure"],
            *(fields.get("observable_evidence") or [])[:2],
        )
        if c
    ]
    return {
        "frame_id": f"frame-{_digest(prompt)}",
        "prompt": prompt,
        "state_constraints": constraints,
        "continuity_from_previous": [],
        "negative_constraints": negatives,
        "claims": _claim_bundle(fields),
        "provider": provider,
        "provider_syntax_only": True,
    }

def image_prompt(brief: str | None, evidence: str | None, design: str | None, project_id: str, provider: str) -> dict[str, Any]:
    text = "\n".join(x for x in (brief, evidence, design) if x).strip()
    if not text:
        return {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": "image",
            "action": "prompt",
            "diagnostic": {"code": "INSUFFICIENT_EVIDENCE", "message": "Provide --brief, --evidence, or --input"},
        }
    frame = _neutral_frame_from_text(text, provider)
    meta = _base_meta("image", "prompt", project_id, {"text": text, "provider": provider})
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "packet": {
            "provider": provider,
            "frames": [frame],
            "shared_constraints": {
                "negative_constraints": frame["negative_constraints"],
                "visual_identity": [],
            },
            "locked_invariants": list(meta["shared_invariants"].keys()),
            "required_elements": frame["state_constraints"],
            "forbidden_changes": frame["negative_constraints"],
        },
    }
    meta["artifact_type"] = "image-prompt-packet"
    return _attach_design_revision(meta, design)

def image_sequence(brief: str | None, evidence: str | None, project_id: str, provider: str) -> dict[str, Any]:
    base = image_prompt(brief, evidence, None, project_id, provider)
    if base.get("status") == "NOT_COMPUTABLE":
        base["action"] = "sequence"
        return base
    frame = base["result"]["packet"]["frames"][0]
    f2 = dict(frame)
    f2["frame_id"] = f"frame-{_digest(frame['prompt'] + '|2')}"
    f2["continuity_from_previous"] = ["preserve identity", "preserve residue", "preserve geometry"]
    f2["prompt"] = frame["prompt"] + "; state advanced without identity reset"
    base["action"] = "sequence"
    base["artifact_type"] = "image-sequence-packet"
    base["result"]["packet"]["frames"] = [frame, f2]
    return base

def image_reference(brief: str | None, project_id: str, provider: str) -> dict[str, Any]:
    packet = image_prompt(brief, None, None, project_id, provider)
    if packet.get("status") == "NOT_COMPUTABLE":
        packet["action"] = "reference"
        return packet
    packet["action"] = "reference"
    packet["artifact_type"] = "visual-reference-packet"
    packet["result"]["reference_type"] = "character-environment-prop"
    return packet

def image_negative(brief: str | None, project_id: str) -> dict[str, Any]:
    text = (brief or "").strip() or "generic failure modes"
    meta = _base_meta("image", "negative", project_id, {"brief": text})
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "negative_constraints": [
            "named occult labels",
            "identity reset",
            "ownership swap without causal transfer",
            "geometry reset",
            "residue erasure",
            "unsupported location jump",
        ],
    }
    meta["artifact_type"] = "image-prompt-packet"
    return meta

def image_qa(expected: str | None, observation: str | None, project_id: str) -> dict[str, Any]:
    if not expected or not observation:
        return {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": "image",
            "action": "qa",
            "diagnostic": {
                "code": "INSUFFICIENT_EVIDENCE",
                "message": "Provide --input expected packet text and --evidence observation text",
            },
        }
    exp_tokens = set(re.findall(r"[a-z0-9_]{4,}", expected.lower()))
    obs_tokens = set(re.findall(r"[a-z0-9_]{4,}", observation.lower()))
    overlap = len(exp_tokens & obs_tokens) / max(1, len(exp_tokens))
    meta = _base_meta("image", "qa", project_id, {"expected": expected, "observation": observation})
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "overlap_ratio": round(overlap, 4),
        "qa_status": "PASS" if overlap >= 0.2 else "FAIL",
        "dimensions": {
            "identity": overlap >= 0.2,
            "geometry": overlap >= 0.15,
            "residue": "residue" in observation.lower() or overlap >= 0.25,
        },
    }
    meta["artifact_type"] = "media-reconciliation-report"
    if overlap < 0.2:
        meta["status"] = "NOT_COMPUTABLE"
        meta["authority"] = "NOT_COMPUTABLE"
    return meta

def _load_packet_document(text: str) -> Any:
    if text.startswith("{"):
        return json.loads(text)
    from kubrick.runtime.runtime_deps import yaml_load

    return yaml_load(text) or {}

def _parse_surface_or_adapter_packet(packet_text: str) -> dict[str, Any]:
    text = packet_text.strip()
    data: Any = _load_packet_document(text)
    if not isinstance(data, dict):
        raise ValueError("packet root must be an object")
    # Unwrap surface receipt → packet
    if "result" in data and isinstance(data["result"], dict) and "packet" in data["result"]:
        packet = dict(data["result"]["packet"])
        packet.setdefault("source_graph_id", data.get("source_state_id") or data.get("artifact_id") or "surface")
        return packet
    if "frames" in data:
        data.setdefault("source_graph_id", data.get("source_graph_id") or "surface")
        return data
    raise ValueError("packet must include frames or result.packet")

def _to_adapter_packet(packet: dict[str, Any]) -> dict[str, Any]:
    frames = []
    for frame in packet.get("frames") or []:
        frames.append(
            {
                "frame_id": frame.get("frame_id"),
                "prompt": frame.get("prompt", ""),
                "state_constraints": list(frame.get("state_constraints") or []),
                "continuity_from_previous": list(frame.get("continuity_from_previous") or []),
            }
        )
    shared = packet.get("shared_constraints") or {}
    if "negative_constraints" not in shared and packet.get("negative_constraints"):
        shared = {**shared, "negative_constraints": packet.get("negative_constraints")}
    return {
        "source_graph_id": packet.get("source_graph_id") or "surface",
        "provider": "generic",
        "frames": frames,
        "shared_constraints": shared,
        "validation": {"status": "VALID", "errors": []},
        "private_state_policy": {
            "graph_mutation_allowed": False,
            "pattern_links_exposed": False,
            "lexicon_links_exposed": False,
        },
    }

def image_adapt(packet_text: str | None, project_id: str, provider: str) -> dict[str, Any]:
    if not packet_text:
        return {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": "image",
            "action": "adapt",
            "diagnostic": {"code": "INSUFFICIENT_EVIDENCE", "message": "--input packet is required"},
        }
    from kubrick.providers.provider_capabilities import (
        capabilities_for,
        check_image_adapt,
        normalize_provider,
    )

    cap_err = check_image_adapt(provider)
    if cap_err:
        return {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": "image",
            "action": "adapt",
            "diagnostic": cap_err,
            "result": {
                "implementation_state": "DOMAIN",
                "provider": normalize_provider(provider),
                "capabilities": cap_err.get("capabilities"),
            },
            "artifact_type": "image-prompt-packet",
        }
    meta = _base_meta("image", "adapt", project_id, {"packet": packet_text, "provider": provider})
    try:
        packet = _parse_surface_or_adapter_packet(packet_text)
        adapter_packet = _to_adapter_packet(packet)
        from kubrick.adapters.adapt_provider import (
            adapt,  # local import avoids circular startup cost
        )

        adapted = adapt(adapter_packet, provider)
        report = adapted.get("preservation_report") or adapted.get("validation") or {}
        status = "VALID"
        if isinstance(report, dict):
            status = report.get("status") or adapted.get("validation", {}).get("status") or "VALID"
        meta["result"] = {
            "implementation_state": "DOMAIN",
            "provider": normalize_provider(provider),
            "capabilities": capabilities_for(provider),
            "adapted_packet": adapted,
            "preservation_report": report
            if isinstance(report, dict)
            else {"status": status},
        }
        if status != "VALID":
            meta["status"] = "NOT_COMPUTABLE"
            meta["authority"] = "NOT_COMPUTABLE"
            meta["not_computable"] = ["provider_semantic_preservation"]
    except Exception as exc:  # noqa: BLE001 — surface must fail closed, not crash
        meta["status"] = "NOT_COMPUTABLE"
        meta["authority"] = "NOT_COMPUTABLE"
        meta["diagnostic"] = {"code": "ADAPTER_NOT_COMPUTABLE", "message": str(exc)}
        meta["result"] = {
            "implementation_state": "DOMAIN",
            "provider": normalize_provider(provider),
            "capabilities": capabilities_for(provider),
        }
    meta["artifact_type"] = "image-prompt-packet"
    return meta

def image_generate(
    brief: str | None, evidence: str | None, design: str | None, project_id: str, provider: str
) -> dict[str, Any]:
    packet = image_prompt(brief, evidence, design, project_id, provider)
    packet["action"] = "generate"
    return packet

def image_improve(packet_text: str, project_id: str, provider: str) -> dict[str, Any]:
    if not packet_text.strip():
        return {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": "image",
            "action": "improve",
            "diagnostic": {"code": "INSUFFICIENT_EVIDENCE", "message": "--input packet is required"},
        }
    base = image_prompt(packet_text, None, None, project_id, provider)
    if base.get("status") == "NOT_COMPUTABLE":
        base["action"] = "improve"
        return base
    frame = base["result"]["packet"]["frames"][0]
    frame["prompt"] = frame["prompt"] + "; reinforce identity lock and residue visibility"
    frame["negative_constraints"] = list(
        dict.fromkeys(list(frame.get("negative_constraints") or []) + ["identity reset", "geometry reset"])
    )
    base["action"] = "improve"
    base["result"]["improvement"] = "strengthened identity/residue constraints"
    return base

def _image_analysis(kind: str, text: str, project_id: str) -> dict[str, Any]:
    if not text.strip():
        return {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": "image",
            "action": kind,
            "diagnostic": {"code": "INSUFFICIENT_EVIDENCE", "message": "Provide --input or --brief"},
        }
    fields = _extract_brief_fields(text, None)
    meta = _base_meta("image", kind, project_id, {"text": text})
    observations = {
        "composition": list(fields.get("geometry") or [])[:4] or ["NOT_COMPUTABLE — composition not evidenced"],
        "lighting": ["NOT_COMPUTABLE — lighting not evidenced"]
        if "light" not in text.lower() and "color" not in text.lower()
        else ["lighting cues evidenced in brief"],
        "camera": list(fields.get("cinematic_channel") or [])[:3]
        or ["NOT_COMPUTABLE — camera language not evidenced"],
        "symbol-extract": list(fields.get("observable_evidence") or [])[:6]
        or ["NOT_COMPUTABLE — symbols not evidenced"],
    }
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "analysis": observations.get(kind, observations["composition"]),
        "claims": _claim_bundle(fields),
    }
    meta["artifact_type"] = "visual-reference-packet"
    return meta

def image_composition_analysis(text: str, project_id: str) -> dict[str, Any]:
    return _image_analysis("composition", text, project_id)

def image_lighting_analysis(text: str, project_id: str) -> dict[str, Any]:
    return _image_analysis("lighting", text, project_id)

def image_camera_analysis(text: str, project_id: str) -> dict[str, Any]:
    return _image_analysis("camera", text, project_id)

def image_symbol_extract(text: str, project_id: str) -> dict[str, Any]:
    return _image_analysis("symbol-extract", text, project_id)

def image_batch(brief: str | None, evidence: str | None, project_id: str, provider: str) -> dict[str, Any]:
    seq = image_sequence(brief, evidence, project_id, provider)
    if seq.get("status") == "NOT_COMPUTABLE":
        seq["action"] = "batch"
        return seq
    seq["action"] = "batch"
    seq["artifact_type"] = "image-sequence-packet"
    seq["result"]["batch"] = True
    return seq
