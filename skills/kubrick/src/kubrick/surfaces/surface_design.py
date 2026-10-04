#!/usr/bin/env python3
"""design.md lifecycle compilers: create, improve, audit, reconcile, validate, update.

Split from surface_compilers.py (#72); public names are re-exported there.
"""
from __future__ import annotations

import re
from typing import Any

from kubrick.surfaces.surface_common import (
    DESIGN_SECTIONS,
    _base_meta,
    _claim,
    _claims_from_list,
    _design_revision,
    _digest,
    _extract_brief_fields,
    _is_placeholder_section,
    _now,
    parse_design_md,
    render_design_md,
)


def design_create(brief: str | None, evidence: str | None, project_id: str) -> dict[str, Any]:
    fields = _extract_brief_fields(brief, evidence)
    if not fields["raw"]:
        return {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": "design",
            "action": "create",
            "diagnostic": {
                "code": "INSUFFICIENT_EVIDENCE",
                "message": "Provide --brief or --evidence to create design.md",
            },
        }
    revision = f"r-{_digest(fields)}"
    sections = {sid: "" for sid, _ in DESIGN_SECTIONS}
    sections["document-status"] = "\n".join(
        [
            _claim(f"Project `{project_id}` design contract", "PROPOSED"),
            _claim("Not canonical until human or Forge promotion", "PROPOSED"),
        ]
    )
    sections["project-identity"] = "\n".join(
        [
            _claim(f"Format: {fields['format'] or 'unspecified'}", "OBSERVED" if fields["format"] != "unspecified" else "PROPOSED"),
            _claim(f"Project id: {project_id}", "PROPOSED"),
        ]
    )
    sections["creative-objective"] = _claim(fields["dramatic_problem"], "OBSERVED")
    sections["dramatic-engine"] = "\n".join(
        [
            _claim(fields["dramatic_problem"], "OBSERVED"),
            _claim(
                fields["desired_state_change"] or "NOT_COMPUTABLE — desired state change not evidenced",
                "OBSERVED" if fields["desired_state_change"] else "NOT_COMPUTABLE",
            ),
            _claim(
                fields["character_pressure"] or "NOT_COMPUTABLE — character pressure not evidenced",
                "OBSERVED" if fields["character_pressure"] else "NOT_COMPUTABLE",
            ),
        ]
    )
    if fields.get("character_pressure"):
        sections["audience-experience"] = _claim(
            f"Audience tracks pressure: {fields['character_pressure']}",
            "OBSERVED",
        )
        sections["character-architecture"] = _claim(fields["character_pressure"], "OBSERVED")
    if fields.get("geometry") or fields.get("cinematic_channel"):
        sections["visual-grammar"] = _claims_from_list(
            list(fields.get("geometry") or []) + list(fields.get("cinematic_channel") or [])
        ) or _claim("NOT_COMPUTABLE — visual grammar not evidenced", "NOT_COMPUTABLE")
        sections["composition-camera"] = _claims_from_list(list(fields.get("cinematic_channel") or [])) or _claim(
            "NOT_COMPUTABLE — camera language not evidenced",
            "NOT_COMPUTABLE",
        )
    if fields.get("observable_evidence") or fields.get("residue"):
        sections["material-continuity"] = _claims_from_list(
            list(fields.get("observable_evidence") or []) + list(fields.get("residue") or [])
        )
    if fields.get("production_constraints") or fields.get("geometry"):
        sections["environment-production"] = _claims_from_list(
            list(fields.get("production_constraints") or []) + list(fields.get("geometry") or [])
        )
    if fields.get("causal_actions") or fields.get("convergence_effect"):
        motion_bits = list(fields.get("causal_actions") or [])
        if fields.get("convergence_effect"):
            motion_bits.append(str(fields["convergence_effect"]))
        sections["motion-behavior"] = _claims_from_list(motion_bits)
    if fields.get("production_constraints"):
        sections["image-rules"] = _claims_from_list(
            list(fields["production_constraints"]),
            "PROPOSED",
        )
        sections["video-rules"] = _claims_from_list(
            list(fields["production_constraints"])
            + (["end state must be observable"] if fields.get("desired_state_change") else []),
            "PROPOSED",
        )
    sections["continuity-invariants"] = "\n".join(
        [
            _claim("Preserve identity, ownership, chronology, geometry, material state, residue", "PROPOSED"),
            *([_claim(item, "OBSERVED") for item in (fields.get("residue") or [])[:3]]),
        ]
    )
    sections["negative-constraints"] = "\n".join(
        [
            _claim("No named esoterica in audience-facing prompts unless explicitly requested", "PROPOSED"),
            _claim("Do not invent unsupported production detail", "PROPOSED"),
        ]
    )
    open_q = []
    if not fields.get("geometry"):
        open_q.append("visual grammar / geometry not fully evidenced")
    if not fields.get("desired_state_change"):
        open_q.append("desired state change missing")
    sections["open-questions"] = (
        _claims_from_list(open_q, "NOT_COMPUTABLE")
        if open_q
        else _claim("No blocking open questions from brief seed", "PROPOSED")
    )
    sections["provenance-map"] = _claim("Seeded from brief/evidence strings supplied to design create", "OBSERVED")
    sections["revision-history"] = _claim(f"{revision} created at {_now()}", "PROPOSED")

    markdown = render_design_md(sections, project_id=project_id, revision=revision)
    meta = _base_meta("design", "create", project_id, fields)
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "revision": revision,
        "document_markdown": markdown,
        "sections_present": sorted(sid for sid, body in sections.items() if body.strip()),
    }
    meta["artifact_type"] = "design-document"
    return meta

def design_improve(existing: str, evidence: str | None, project_id: str) -> dict[str, Any]:
    if not existing.strip():
        return {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": "design",
            "action": "improve",
            "diagnostic": {"code": "INSUFFICIENT_EVIDENCE", "message": "--input design.md is required"},
        }
    sections = parse_design_md(existing)
    preserved = {sid: body for sid, body in sections.items() if body.strip()}
    fields = _extract_brief_fields(None, evidence)
    diffs: list[dict[str, str]] = []

    # Fill empty / placeholder sections from evidenced brief YAML; never wipe LOCKED/OBSERVED text.
    def _needs_fill(sid: str) -> bool:
        return _is_placeholder_section(sections.get(sid, ""))

    fill_plan: list[tuple[str, str, str]] = []  # sid, body, reason
    if _needs_fill("dramatic-engine") and fields["dramatic_problem"]:
        fill_plan.append(
            (
                "dramatic-engine",
                "\n".join(
                    [
                        _claim(fields["dramatic_problem"], "OBSERVED"),
                        _claim(
                            fields["desired_state_change"] or "NOT_COMPUTABLE — desired state change not evidenced",
                            "OBSERVED" if fields["desired_state_change"] else "NOT_COMPUTABLE",
                        ),
                        _claim(
                            fields["character_pressure"] or "NOT_COMPUTABLE — character pressure not evidenced",
                            "OBSERVED" if fields["character_pressure"] else "NOT_COMPUTABLE",
                        ),
                    ]
                ),
                "seeded dramatic engine from brief evidence",
            )
        )
    if _needs_fill("audience-experience") and fields.get("character_pressure"):
        fill_plan.append(
            (
                "audience-experience",
                _claim(f"Audience tracks pressure: {fields['character_pressure']}", "OBSERVED"),
                "character pressure evidenced",
            )
        )
    if _needs_fill("character-architecture") and fields.get("character_pressure"):
        fill_plan.append(
            (
                "character-architecture",
                _claim(fields["character_pressure"], "OBSERVED"),
                "character pressure evidenced",
            )
        )
    visual_bits = list(fields.get("geometry") or []) + list(fields.get("cinematic_channel") or [])
    if _needs_fill("visual-grammar"):
        if visual_bits:
            fill_plan.append(
                ("visual-grammar", _claims_from_list(visual_bits), "geometry/cinematic channel evidenced")
            )
        elif not sections.get("visual-grammar", "").strip():
            fill_plan.append(
                (
                    "visual-grammar",
                    _claim(
                        "NOT_COMPUTABLE — visual grammar not evidenced; refuse invented shot language",
                        "NOT_COMPUTABLE",
                    ),
                    "missing production-critical section",
                )
            )
    if _needs_fill("composition-camera") and fields.get("cinematic_channel"):
        fill_plan.append(
            (
                "composition-camera",
                _claims_from_list(list(fields["cinematic_channel"])),
                "cinematic channel evidenced",
            )
        )
    if _needs_fill("material-continuity") and (
        fields.get("observable_evidence") or fields.get("residue")
    ):
        fill_plan.append(
            (
                "material-continuity",
                _claims_from_list(
                    list(fields.get("observable_evidence") or []) + list(fields.get("residue") or [])
                ),
                "observable evidence / residue present",
            )
        )
    if _needs_fill("environment-production") and (
        fields.get("production_constraints") or fields.get("geometry")
    ):
        fill_plan.append(
            (
                "environment-production",
                _claims_from_list(
                    list(fields.get("production_constraints") or []) + list(fields.get("geometry") or [])
                ),
                "production constraints / geometry evidenced",
            )
        )
    if _needs_fill("motion-behavior") and (
        fields.get("causal_actions") or fields.get("convergence_effect")
    ):
        motion_bits = list(fields.get("causal_actions") or [])
        if fields.get("convergence_effect"):
            motion_bits.append(str(fields["convergence_effect"]))
        fill_plan.append(
            ("motion-behavior", _claims_from_list(motion_bits), "causal actions evidenced")
        )
    if _needs_fill("image-rules") and fields.get("production_constraints"):
        fill_plan.append(
            (
                "image-rules",
                _claims_from_list(list(fields["production_constraints"]), "PROPOSED"),
                "production constraints evidenced",
            )
        )
    if _needs_fill("video-rules") and (
        fields.get("production_constraints") or fields.get("desired_state_change")
    ):
        bits = list(fields.get("production_constraints") or [])
        if fields.get("desired_state_change"):
            bits.append(f"end state must realize: {fields['desired_state_change']}")
        fill_plan.append(
            ("video-rules", _claims_from_list(bits, "PROPOSED"), "video constraints evidenced")
        )
    if _needs_fill("continuity-invariants"):
        fill_plan.append(
            (
                "continuity-invariants",
                "\n".join(
                    [
                        _claim(
                            "Preserve identity, ownership, chronology, geometry, material state, residue",
                            "PROPOSED",
                        ),
                        *([_claim(item, "OBSERVED") for item in (fields.get("residue") or [])[:3]]),
                    ]
                ),
                "missing production-critical section",
            )
        )
    if _needs_fill("negative-constraints"):
        fill_plan.append(
            (
                "negative-constraints",
                _claim(
                    "No named esoterica in audience-facing prompts unless explicitly requested",
                    "PROPOSED",
                ),
                "missing production-critical section",
            )
        )
    if _needs_fill("open-questions") and not sections.get("open-questions", "").strip():
        fill_plan.append(
            ("open-questions", _claim("Awaiting evidence", "NOT_COMPUTABLE"), "missing production-critical section")
        )

    for sid, new_body, reason in fill_plan:
        if not _needs_fill(sid):
            continue
        # Never overwrite LOCKED claims even if somehow marked placeholder.
        if "[LOCKED]" in sections.get(sid, ""):
            continue
        change = "filled_empty" if not sections.get(sid, "").strip() else "replaced_placeholder"
        sections[sid] = new_body
        diffs.append({"section": sid, "change": change, "reason": reason})

    # Append evidence note without rewriting preserved sections.
    if fields["raw"]:
        note = _claim(f"Additional evidence considered: {fields['raw'][:280]}", "OBSERVED")
        prev = sections.get("provenance-map", "").rstrip()
        if note not in prev:
            sections["provenance-map"] = (prev + "\n" + note).strip()
            diffs.append({"section": "provenance-map", "change": "appended", "reason": "new evidence"})

    revision = f"r-{_digest({'preserved': sorted(preserved), 'diffs': diffs})}"
    history = sections.get("revision-history", "").rstrip()
    history_line = _claim(f"{revision} improve at {_now()} ({len(diffs)} bounded edits)", "PROPOSED")
    sections["revision-history"] = (history + "\n" + history_line).strip()
    markdown = render_design_md(sections, project_id=project_id, revision=revision)
    meta = _base_meta("design", "improve", project_id, {"input": existing, "evidence": evidence or ""})
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "revision": revision,
        "parent_revision": _design_revision(existing),
        "document_markdown": markdown,
        "diff": diffs,
        "preserved_section_count": len(preserved),
        "invariant_impact": {
            "sections_filled": [
                d["section"]
                for d in diffs
                if d.get("change") in {"filled_empty", "replaced_placeholder"}
            ],
            "authority_promotions": [],
        },
    }
    meta["artifact_type"] = "design-revision-receipt"
    return meta

def design_audit(existing: str, against: str | None, project_id: str) -> dict[str, Any]:
    if not existing.strip():
        return {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": "design",
            "action": "audit",
            "diagnostic": {"code": "INSUFFICIENT_EVIDENCE", "message": "--input design.md is required"},
        }
    sections = parse_design_md(existing)
    findings: list[dict[str, str]] = []
    for sid, title in DESIGN_SECTIONS:
        body = sections.get(sid, "").strip()
        if not body or "NOT_COMPUTABLE" in body and body.count("\n") == 0:
            if sid in {
                "dramatic-engine",
                "visual-grammar",
                "continuity-invariants",
                "image-rules",
                "video-rules",
            }:
                findings.append(
                    {
                        "severity": "high",
                        "section": sid,
                        "code": "MISSING_OR_WEAK",
                        "message": f"{title} lacks enforceable content",
                    }
                )
        if body and re.search(r"\b(flux|midjourney|sd3|grok)\b", body, re.I):
            findings.append(
                {
                    "severity": "medium",
                    "section": sid,
                    "code": "PROVIDER_COUPLING",
                    "message": "Provider-specific language found in design contract",
                }
            )
    if against:
        # Simple lexical overlap check for reconcile-lite during audit
        design_tokens = set(re.findall(r"[a-z0-9_]{4,}", existing.lower()))
        against_tokens = set(re.findall(r"[a-z0-9_]{4,}", against.lower()))
        overlap = len(design_tokens & against_tokens)
        if overlap < 3:
            findings.append(
                {
                    "severity": "high",
                    "section": "reconcile",
                    "code": "LOW_OVERLAP",
                    "message": "Against-material shares little vocabulary with design.md",
                }
            )
    status = "PASS" if not any(f["severity"] == "high" for f in findings) else "FAIL"
    meta = _base_meta("design", "audit", project_id, {"input": existing, "against": against or ""})
    meta["status"] = status if status == "PASS" else "PROPOSED"
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "audit_status": status,
        "findings": findings,
        "finding_count": len(findings),
    }
    meta["artifact_type"] = "design-audit-report"
    if status == "FAIL":
        meta["authority"] = "OBSERVATION"
    return meta

def design_reconcile(existing: str, against: str | None, project_id: str) -> dict[str, Any]:
    audit = design_audit(existing, against, project_id)
    if audit.get("status") == "NOT_COMPUTABLE":
        audit["action"] = "reconcile"
        return audit
    meta = _base_meta("design", "reconcile", project_id, {"input": existing, "against": against or ""})
    findings = audit.get("result", {}).get("findings", [])
    drift = [f for f in findings if f.get("code") in {"LOW_OVERLAP", "PROVIDER_COUPLING", "MISSING_OR_WEAK"}]
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "drift": drift,
        "compatible": not any(f.get("severity") == "high" for f in drift),
        "audit": audit.get("result"),
    }
    meta["artifact_type"] = "media-reconciliation-report"
    if not against:
        meta["status"] = "NOT_COMPUTABLE"
        meta["authority"] = "NOT_COMPUTABLE"
        meta["not_computable"] = ["against material missing"]
        meta["diagnostic"] = {
            "code": "INSUFFICIENT_EVIDENCE",
            "message": "Provide --evidence (against script/prompt material) for reconcile",
        }
    return meta

def design_validate(existing: str, project_id: str) -> dict[str, Any]:
    if not existing.strip():
        return {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": "design",
            "action": "validate",
            "diagnostic": {"code": "INSUFFICIENT_EVIDENCE", "message": "--input design.md is required"},
        }
    sections = parse_design_md(existing)
    missing = [sid for sid, _ in DESIGN_SECTIONS if not sections.get(sid, "").strip()]
    # Structural validity: must have dramatic engine or creative objective with non-placeholder text
    core_ok = any(
        sections.get(sid, "") and "NOT_COMPUTABLE" not in sections.get(sid, "").split("\n")[0]
        for sid in ("dramatic-engine", "creative-objective")
    )
    meta = _base_meta("design", "validate", project_id, {"input": existing})
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "missing_sections": missing,
        "core_objective_present": core_ok,
        "section_count": len(DESIGN_SECTIONS) - len(missing),
        "valid": core_ok,
    }
    meta["artifact_type"] = "design-audit-report"
    if not core_ok:
        meta["status"] = "NOT_COMPUTABLE"
        meta["authority"] = "NOT_COMPUTABLE"
        meta["not_computable"] = ["core dramatic/creative objective"]
    return meta

def design_update(existing: str, evidence: str | None, project_id: str) -> dict[str, Any]:
    # Bounded update == improve + explicit receipt alias
    improved = design_improve(existing, evidence, project_id)
    if improved.get("status") == "NOT_COMPUTABLE":
        improved["action"] = "update"
        return improved
    improved["action"] = "update"
    improved["artifact_type"] = "design-revision-receipt"
    improved["result"]["update_mode"] = "bounded"
    return improved
