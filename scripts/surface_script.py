#!/usr/bin/env python3
"""Script compilers: create, diagnose, continuity, improve, adapt, handoff.

Split from surface_compilers.py (#72); public names are re-exported there.
"""
from __future__ import annotations

import re
from typing import Any

from surface_common import (
    _attach_design_revision,
    _base_meta,
    _claim_bundle,
    _design_revision,
    _digest,
    _extract_brief_fields,
    _now,
)


def script_create(
    brief: str | None,
    evidence: str | None,
    project_id: str,
    fmt: str = "markdown",
    design_text: str | None = None,
) -> dict[str, Any]:
    fields = _extract_brief_fields(brief, evidence)
    if not fields["raw"] and not design_text:
        return {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": "script",
            "action": "create",
            "diagnostic": {"code": "INSUFFICIENT_EVIDENCE", "message": "Provide --brief, --evidence, or --input design.md"},
        }
    if not fields["raw"] and design_text:
        fields = _extract_brief_fields(design_text, None)
    revision = f"s-{_digest(fields)}"
    design_rev = _design_revision(design_text) or "pending"
    fmt_norm = (fmt or "markdown").lower().strip()
    if fmt_norm in {"fountain", "screenplay"}:
        body = "\n".join(
            [
                f"Title: {project_id}",
                "Credit: Kubrick PROPOSED package",
                f"Draft date: {_now()[:10]}",
                f"Contact: design-revision {design_rev}",
                "",
                f"= Script revision {revision}",
                "",
                "INT. INSTITUTIONAL INTERIOR - DAY",
                "",
                fields["dramatic_problem"] or "NOT_COMPUTABLE",
                "",
                (
                    f"Observable action: {fields['desired_state_change']}"
                    if fields["desired_state_change"]
                    else "NOT_COMPUTABLE — desired state change not evidenced"
                ),
                "",
                (
                    f"Character pressure: {fields['character_pressure']}"
                    if fields["character_pressure"]
                    else "NOT_COMPUTABLE — character pressure not evidenced"
                ),
                "",
                "NOTE: Dialogue is NOT_COMPUTABLE — no dialogue evidenced.",
                "",
            ]
        )
    elif fmt_norm in {"beat-sheet", "beats"}:
        body = "\n".join(
            [
                f"# Beat sheet — {project_id}",
                "",
                f"Design revision: {design_rev}",
                f"Script revision: {revision}",
                "",
                "1. Setup — " + (fields["dramatic_problem"] or "NOT_COMPUTABLE"),
                "2. Pressure — " + (fields["character_pressure"] or "NOT_COMPUTABLE"),
                "3. Turn — " + (fields["desired_state_change"] or "NOT_COMPUTABLE"),
                "4. Residue — "
                + (
                    "; ".join(fields.get("residue") or [])
                    or "NOT_COMPUTABLE — residue not evidenced"
                ),
                "",
            ]
        )
    else:
        body = "\n".join(
            [
                f"# Script package — {project_id}",
                "",
                f"Format: {fmt_norm}",
                f"Design revision link: {design_rev}",
                f"Script revision: {revision}",
                "",
                "## Dramatic intent",
                fields["dramatic_problem"] or "NOT_COMPUTABLE",
                "",
                "## Observable action",
                fields["desired_state_change"] or "NOT_COMPUTABLE",
                "",
                "## Character pressure",
                fields["character_pressure"] or "NOT_COMPUTABLE",
                "",
                "## Dialogue",
                "NOT_COMPUTABLE — no dialogue evidenced",
                "",
                "## Continuity requirements",
                "- Preserve identity, ownership, chronology, residue",
                "",
                "## Production implications",
                (
                    "\n".join(f"- {c}" for c in (fields.get("production_constraints") or [])[:4])
                    or "NOT_COMPUTABLE — awaiting production constraints"
                ),
                "",
            ]
        )
    meta = _base_meta("script", "create", project_id, fields)
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "script_revision": revision,
        "source_design_revision": design_rev,
        "format": fmt_norm,
        "document_markdown": body,
        "claims": _claim_bundle(fields),
        "continuity_requirements": [
            "preserve_identity",
            "preserve_ownership",
            "preserve_chronology",
            "preserve_residue",
        ],
    }
    meta["artifact_type"] = "script-development-packet"
    return _attach_design_revision(meta, design_text)

def script_diagnose(existing: str, project_id: str) -> dict[str, Any]:
    if not existing.strip():
        return {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": "script",
            "action": "diagnose",
            "diagnostic": {"code": "INSUFFICIENT_EVIDENCE", "message": "--input script is required"},
        }
    findings: list[dict[str, str]] = []
    lowered = existing.lower()
    if "because the symbol" in lowered or "represents" in lowered and "motif" in lowered:
        findings.append(
            {
                "severity": "high",
                "code": "SYMBOLIC_EXPLANATION",
                "message": "Symbolic explanation may be substituting for dramatic causality",
            }
        )
    if "NOT_COMPUTABLE" in existing and existing.count("NOT_COMPUTABLE") > 5:
        findings.append(
            {
                "severity": "medium",
                "code": "UNDER_SPECIFIED",
                "message": "Many NOT_COMPUTABLE fields — script needs more observable action",
            }
        )
    if len(existing.strip()) < 80:
        findings.append(
            {
                "severity": "high",
                "code": "TOO_SHORT",
                "message": "Script material is too thin for continuity-safe production",
            }
        )
    meta = _base_meta("script", "diagnose", project_id, {"input": existing})
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "findings": findings,
        "diagnostic_status": "FAIL" if any(f["severity"] == "high" for f in findings) else "PASS",
    }
    meta["artifact_type"] = "script-diagnostic-report"
    return meta

def script_continuity(existing: str, project_id: str) -> dict[str, Any]:
    if not existing.strip():
        return {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": "script",
            "action": "continuity-check",
            "diagnostic": {"code": "INSUFFICIENT_EVIDENCE", "message": "--input script is required"},
        }
    checks = {
        "identity_mentioned": bool(re.search(r"\b(character|identity|name)\b", existing, re.I)),
        "object_state_mentioned": bool(re.search(r"\b(object|prop|badge|door|chair)\b", existing, re.I)),
        "residue_mentioned": bool(re.search(r"\b(residue|remains|scar|crack)\b", existing, re.I)),
        "chronology_clear": bool(re.search(r"\b(then|after|before|continues)\b", existing, re.I)),
    }
    missing = [k for k, ok in checks.items() if not ok]
    meta = _base_meta("script", "continuity-check", project_id, {"input": existing})
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "checks": checks,
        "missing": missing,
        "continuity_status": "PASS" if len(missing) <= 2 else "FAIL",
    }
    meta["artifact_type"] = "script-continuity-report"
    if len(missing) > 2:
        meta["status"] = "NOT_COMPUTABLE"
        meta["authority"] = "NOT_COMPUTABLE"
        meta["not_computable"] = missing
    return meta

def script_improve(existing: str, project_id: str) -> dict[str, Any]:
    if not existing.strip():
        return {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": "script",
            "action": "improve",
            "diagnostic": {"code": "INSUFFICIENT_EVIDENCE", "message": "--input script is required"},
        }
    revision = f"s-{_digest(existing)}"
    improved = existing.rstrip() + "\n\n## Revision notes\n"
    improved += f"- [{revision}] Pressure, observable action, and continuity requirements restated without symbolic lecture.\n"
    if "Continuity requirements" not in existing:
        improved += "\n## Continuity requirements\n- Preserve identity, ownership, chronology, residue\n"
    meta = _base_meta("script", "improve", project_id, {"input": existing})
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "script_revision": revision,
        "document_markdown": improved,
        "source_script_revision": f"s-{_digest(existing[:200])}",
    }
    meta["artifact_type"] = "script-development-packet"
    return meta

def script_adapt(existing: str, project_id: str, fmt: str = "beat-sheet") -> dict[str, Any]:
    if not existing.strip():
        return {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": "script",
            "action": "adapt",
            "diagnostic": {"code": "INSUFFICIENT_EVIDENCE", "message": "--input script is required"},
        }
    lines = [ln.strip() for ln in existing.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    beats = lines[:12] or ["NOT_COMPUTABLE"]
    doc = "# Beat sheet\n\n" + "\n".join(f"{i+1}. {b}" for i, b in enumerate(beats)) + "\n"
    meta = _base_meta("script", "adapt", project_id, {"input": existing, "format": fmt})
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "format": fmt,
        "document_markdown": doc,
        "source_script_revision": f"s-{_digest(existing[:200])}",
    }
    meta["artifact_type"] = "script-development-packet"
    return meta

def script_handoff(existing: str, project_id: str) -> dict[str, Any]:
    if not existing.strip():
        return {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": "script",
            "action": "handoff",
            "diagnostic": {"code": "INSUFFICIENT_EVIDENCE", "message": "--input script is required"},
        }
    meta = _base_meta("script", "handoff", project_id, {"input": existing})
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "source_script_revision": f"s-{_digest(existing[:200])}",
        "handoff_targets": ["image", "video", "storyboard", "continuity-forge"],
        "locked_invariants": [
            "preserve_identity",
            "preserve_ownership",
            "preserve_chronology",
            "preserve_residue",
        ],
        "packet_preview": {
            "observable_action": next(
                (ln.strip() for ln in existing.splitlines() if ln.strip() and not ln.startswith("#")),
                "NOT_COMPUTABLE",
            )
        },
    }
    meta["artifact_type"] = "script-development-packet"
    return meta
