#!/usr/bin/env python3
"""design.md drift, expand, summarize, and QA compilers.

Split from surface_compilers.py (#72); public names are re-exported there.
"""
from __future__ import annotations

import json
import re
from typing import Any

from surface_common import (
    DESIGN_SECTIONS,
    _base_meta,
    _design_revision,
    _is_placeholder_section,
    parse_design_md,
)
from surface_design import design_audit, design_improve


def design_drift(existing: str, against: str | None, project_id: str) -> dict[str, Any]:
    """Project-wide cross-surface drift report (design ↔ script/image/video)."""
    if not existing.strip():
        return {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": "design",
            "action": "drift",
            "diagnostic": {"code": "INSUFFICIENT_EVIDENCE", "message": "--input design.md is required"},
        }
    if not against or not against.strip():
        return {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": "design",
            "action": "drift",
            "diagnostic": {
                "code": "INSUFFICIENT_EVIDENCE",
                "message": "Provide --evidence (script/image/video artifact or directory dump)",
            },
        }

    sections = parse_design_md(existing)
    design_tokens = set(re.findall(r"[a-z0-9_]{4,}", existing.lower()))
    findings: list[dict[str, Any]] = []

    # Split concatenated multi-artifact evidence on a stable delimiter if present.
    chunks = re.split(r"\n---KUBRICK_ARTIFACT---\n", against)
    if len(chunks) == 1:
        chunks = [against]

    surfaces_seen: list[str] = []
    for idx, chunk in enumerate(chunks):
        text = chunk.strip()
        if not text:
            continue
        surface = "unknown"
        artifact_type = "raw"
        payload_text = text
        if text.startswith("{"):
            try:
                data = json.loads(text)
                surface = str(data.get("surface") or data.get("artifact_type") or "packet")
                artifact_type = str(data.get("artifact_type") or "json")
                payload_text = json.dumps(data.get("result") or data, ensure_ascii=False)
                if data.get("source_design_revision"):
                    design_rev = _design_revision(existing)
                    if design_rev and data["source_design_revision"] != design_rev:
                        findings.append(
                            {
                                "severity": "high",
                                "code": "REVISION_MISMATCH",
                                "collision": "CONTRADICTORY",
                                "surface": surface,
                                "message": (
                                    f"artifact design revision {data['source_design_revision']} "
                                    f"!= design {design_rev}"
                                ),
                            }
                        )
            except json.JSONDecodeError:
                surface = "text"
        elif text.lstrip().startswith("# Script") or "Dramatic intent" in text[:400]:
            surface = "script"
            artifact_type = "script-development-packet"
        elif "shot_id:" in text or "end_state:" in text:
            surface = "video"
            artifact_type = "shot-contract"
        elif text.lstrip().startswith("# Design"):
            surface = "design"
            artifact_type = "design-document"
        surfaces_seen.append(f"{surface}:{artifact_type}")

        against_tokens = set(re.findall(r"[a-z0-9_]{4,}", payload_text.lower()))
        overlap = len(design_tokens & against_tokens)
        ratio = overlap / max(1, len(design_tokens))
        if overlap < 3 or ratio < 0.02:
            findings.append(
                {
                    "severity": "high",
                    "code": "LOW_OVERLAP",
                    "collision": "CONTRADICTORY",
                    "surface": surface,
                    "message": f"low lexical overlap with design ({overlap} shared tokens)",
                    "chunk": idx,
                }
            )
        # Provider coupling leak from media into design space
        if re.search(r"\b(flux|midjourney|sd3|grok-imagine)\b", payload_text, re.I) and surface in {
            "image",
            "video",
            "packet",
        }:
            # provider syntax in media is fine; flag only if design also lacks negatives
            if not sections.get("negative-constraints", "").strip():
                findings.append(
                    {
                        "severity": "medium",
                        "code": "PROVIDER_WITHOUT_NEGATIVES",
                        "collision": "PROVIDER_SEMANTIC_DROP",
                        "surface": surface,
                        "message": "media references providers while design negatives are empty",
                    }
                )
        # Continuity keyword absence
        if surface in {"script", "video", "shot-contract", "image"} and not any(
            k in payload_text.lower() for k in ("identity", "residue", "ownership", "continuity")
        ):
            findings.append(
                {
                    "severity": "medium",
                    "code": "CONTINUITY_SILENCE",
                    "collision": "RESIDUE_ERASURE",
                    "surface": surface,
                    "message": "artifact lacks continuity vocabulary present in design contract",
                }
            )

    # Core design sections weak
    for sid in ("dramatic-engine", "continuity-invariants", "negative-constraints"):
        if _is_placeholder_section(sections.get(sid, "")):
            findings.append(
                {
                    "severity": "high",
                    "code": "WEAK_DESIGN_SECTION",
                    "collision": "CONTRADICTORY",
                    "surface": "design",
                    "message": f"design section `{sid}` is placeholder-only",
                }
            )

    high = [f for f in findings if f.get("severity") == "high"]
    meta = _base_meta("design", "drift", project_id, {"input": existing, "against": against})
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "surfaces_compared": surfaces_seen,
        "findings": findings,
        "finding_count": len(findings),
        "compatible": not high,
        "drift_status": "FAIL" if high else "PASS",
    }
    meta["artifact_type"] = "media-reconciliation-report"
    if high:
        meta["status"] = "PROPOSED"
        meta["authority"] = "OBSERVATION"
    return meta

def design_expand(existing: str, evidence: str | None, project_id: str) -> dict[str, Any]:
    """Expand placeholder/weak sections using evidence; preserve LOCKED text."""
    improved = design_improve(existing, evidence, project_id)
    if improved.get("status") == "NOT_COMPUTABLE":
        improved["action"] = "expand"
        return improved
    improved["action"] = "expand"
    sections = parse_design_md(improved["result"].get("document_markdown") or existing)
    roadmap: list[dict[str, str]] = []
    for sid, title in DESIGN_SECTIONS:
        body = sections.get(sid, "")
        if _is_placeholder_section(body) or "NOT_COMPUTABLE" in body:
            roadmap.append(
                {
                    "section": sid,
                    "title": title,
                    "priority": "high" if sid in {"dramatic-engine", "visual-grammar", "continuity-invariants"} else "medium",
                    "suggestion": f"Gather evidence for {title}; refuse invented specificity",
                }
            )
    score = max(0, 100 - len(roadmap) * 3)
    improved["result"]["implementation_roadmap"] = roadmap[:20]
    improved["result"]["quality_score"] = score
    improved["result"]["best_practice_suggestions"] = [
        "Keep normative claims authority-tagged",
        "Never promote PROPOSED to LOCKED without explicit approval",
        "Keep provider syntax out of design.md",
    ]
    improved["artifact_type"] = "design-revision-receipt"
    return improved

def design_summarize(existing: str, project_id: str) -> dict[str, Any]:
    if not existing.strip():
        return {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": "design",
            "action": "summarize",
            "diagnostic": {"code": "INSUFFICIENT_EVIDENCE", "message": "--input design.md is required"},
        }
    sections = parse_design_md(existing)
    filled = [sid for sid, body in sections.items() if body.strip() and not _is_placeholder_section(body)]
    weak = [sid for sid, _ in DESIGN_SECTIONS if sid not in filled]
    objective = sections.get("creative-objective") or sections.get("dramatic-engine") or ""
    summary_lines = [
        f"# Design summary — {project_id}",
        "",
        f"Revision: {_design_revision(existing) or 'unknown'}",
        f"Sections filled: {len(filled)} / {len(DESIGN_SECTIONS)}",
        "",
        "## Core objective",
        objective.strip() or "NOT_COMPUTABLE",
        "",
        "## Gaps",
        *[f"- {sid}" for sid in weak[:12]],
        "",
    ]
    meta = _base_meta("design", "summarize", project_id, {"input": existing})
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "filled_sections": filled,
        "gap_sections": weak,
        "document_markdown": "\n".join(summary_lines),
        "quality_score": max(0, int(100 * len(filled) / max(1, len(DESIGN_SECTIONS)))),
    }
    meta["artifact_type"] = "design-audit-report"
    return meta

def design_qa(existing: str, against: str | None, project_id: str) -> dict[str, Any]:
    audit = design_audit(existing, against, project_id)
    if audit.get("status") == "NOT_COMPUTABLE" and not audit.get("result"):
        audit["action"] = "qa"
        return audit
    findings = list((audit.get("result") or {}).get("findings") or [])
    if _is_placeholder_section(parse_design_md(existing).get("continuity-invariants", "")):
        findings.append(
            {
                "severity": "high",
                "code": "MISSING_CONTEXT",
                "message": "continuity invariants missing or placeholder",
            }
        )
    if re.search(r"\b(flux|midjourney|sd3)\b", existing, re.I):
        findings.append(
            {
                "severity": "medium",
                "code": "PROVIDER_INCOMPATIBILITY_RISK",
                "message": "provider-specific language in design contract",
            }
        )
    meta = _base_meta("design", "qa", project_id, {"input": existing, "against": against or ""})
    high = [f for f in findings if f.get("severity") == "high"]
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "qa_status": "FAIL" if high else "PASS",
        "findings": findings,
        "dimensions": {
            "missing_context": any(f.get("code") == "MISSING_CONTEXT" for f in findings),
            "inconsistency": any(f.get("code") in {"LOW_OVERLAP", "REVISION_MISMATCH"} for f in findings),
            "provider_coupling": any("PROVIDER" in str(f.get("code")) for f in findings),
        },
    }
    meta["artifact_type"] = "media-reconciliation-report"
    if high:
        meta["status"] = "NOT_COMPUTABLE"
        meta["authority"] = "NOT_COMPUTABLE"
    return meta
