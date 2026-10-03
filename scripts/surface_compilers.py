#!/usr/bin/env python3
"""Domain compilers for Kubrick first-class production surfaces (v0.15).

Deterministic, fail-closed, proposal-only. Emits readable design.md plus
structured packets for script/image/video without inventing unsupported detail.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from provenance import provenance_bucket

DESIGN_SECTIONS: list[tuple[str, str]] = [
    ("document-status", "Document status and authority"),
    ("project-identity", "Project identity and format"),
    ("creative-objective", "Creative objective"),
    ("audience-experience", "Audience experience"),
    ("dramatic-engine", "Dramatic engine"),
    ("world-rules", "World rules and boundaries"),
    ("character-architecture", "Character identity and pressure architecture"),
    ("visual-grammar", "Visual grammar"),
    ("composition-camera", "Composition and camera language"),
    ("lighting-color", "Lighting and color logic"),
    ("environment-production", "Environment and production design"),
    ("material-continuity", "Character, costume, prop, and material continuity"),
    ("motif-lifecycle", "Motif lifecycle and convergence limits"),
    ("motion-behavior", "Motion and physical behavior"),
    ("editing-rhythm", "Editing, rhythm, and transition logic"),
    ("sound-dialogue", "Dialogue, voice, sound, and music logic"),
    ("image-rules", "Image-generation rules"),
    ("video-rules", "Video-generation rules"),
    ("negative-constraints", "Provider-independent negative constraints"),
    ("safety-constraints", "Accessibility, cultural, legal, and safety constraints"),
    ("continuity-invariants", "Continuity invariants and locked facts"),
    ("production-handoff", "Production handoff requirements"),
    ("open-questions", "Open questions and NOT_COMPUTABLE fields"),
    ("provenance-map", "Provenance map"),
    ("revision-history", "Revision history and decision log"),
]

SECTION_RE = re.compile(
    r"^##\s+(?P<title>.+?)\s*$",
    re.MULTILINE,
)
REVISION_RE = re.compile(r"Revision:\s*`([^`]+)`")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _design_revision(design_text: str | None) -> str | None:
    if not design_text:
        return None
    match = REVISION_RE.search(design_text)
    if match:
        return match.group(1)
    # Fallback stable digest of design body for linkage when header missing.
    return f"r-{_digest(design_text[:2000])}"


def _attach_design_revision(meta: dict[str, Any], design_text: str | None) -> dict[str, Any]:
    rev = _design_revision(design_text)
    if rev:
        meta["source_design_revision"] = rev
        result = meta.setdefault("result", {})
        if isinstance(result, dict):
            result["source_design_revision"] = rev
    return meta


def _claim(text: str, label: str = "PROPOSED") -> str:
    return f"- [{label}] {text}"


def _authority_tag(text: str, authority: str = "OBSERVED") -> dict[str, str]:
    return {"text": text, "authority": authority}


def _claim_bundle(fields: dict[str, Any]) -> dict[str, Any]:
    """Structured claim map for criteria #9 (authority-tagged production claims)."""
    claims: dict[str, Any] = {}
    if fields.get("dramatic_problem"):
        claims["dramatic_problem"] = _authority_tag(fields["dramatic_problem"], "OBSERVED")
    if fields.get("desired_state_change"):
        claims["desired_state_change"] = _authority_tag(fields["desired_state_change"], "OBSERVED")
    else:
        claims["desired_state_change"] = _authority_tag("not evidenced", "NOT_COMPUTABLE")
    if fields.get("character_pressure"):
        claims["character_pressure"] = _authority_tag(fields["character_pressure"], "OBSERVED")
    for key in ("geometry", "residue", "observable_evidence", "production_constraints"):
        items = list(fields.get(key) or [])
        if items:
            claims[key] = [_authority_tag(item, "OBSERVED") for item in items[:6]]
    claims["invariants"] = [
        _authority_tag("preserve_identity", "PROPOSED"),
        _authority_tag("preserve_ownership", "PROPOSED"),
        _authority_tag("preserve_residue", "PROPOSED"),
    ]
    return claims


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif isinstance(item, dict):
                # relation / transformation rows
                for key in ("transformation", "relation", "summary", "text"):
                    if isinstance(item.get(key), str) and item[key].strip():
                        out.append(item[key].strip())
                        break
        return out
    return [str(value)]


def _extract_brief_fields(brief: str | None, evidence: str | None) -> dict[str, Any]:
    blob = "\n".join(x for x in (brief, evidence) if x).strip()
    fields: dict[str, Any] = {
        "dramatic_problem": "",
        "desired_state_change": "",
        "character_pressure": "",
        "format": "unspecified",
        "observable_evidence": [],
        "geometry": [],
        "residue": [],
        "production_constraints": [],
        "causal_actions": [],
        "convergence_effect": "",
        "cinematic_channel": [],
        "raw": blob,
    }
    if not blob:
        return fields

    parsed: dict[str, Any] | None = None
    try:
        import yaml  # type: ignore[import-untyped]

        loaded = yaml.safe_load(blob)
        if isinstance(loaded, dict):
            parsed = loaded
    except Exception:  # noqa: BLE001 — fall back to line parsing
        parsed = None

    if parsed is not None:
        for key in ("dramatic_problem", "desired_state_change", "character_pressure", "format", "convergence_effect"):
            val = parsed.get(key)
            if isinstance(val, str) and val.strip():
                fields[key] = val.strip()
        for key in ("observable_evidence", "geometry", "residue", "production_constraints", "causal_actions"):
            fields[key] = _as_str_list(parsed.get(key))
        channels = parsed.get("symbolic_channels")
        if isinstance(channels, dict):
            fields["cinematic_channel"] = _as_str_list(channels.get("cinematic"))
        relations = parsed.get("relations")
        if isinstance(relations, list):
            fields["causal_actions"] = list(
                dict.fromkeys(fields["causal_actions"] + _as_str_list(relations))
            )
    else:
        for key in ("dramatic_problem", "desired_state_change", "character_pressure", "format"):
            match = re.search(rf"^{key}\s*:\s*(.+)$", blob, re.MULTILINE)
            if match:
                fields[key] = match.group(1).strip().strip("\"'")

    if not fields["dramatic_problem"]:
        for line in blob.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and ":" not in line[:40]:
                fields["dramatic_problem"] = line
                break
        if not fields["dramatic_problem"]:
            fields["dramatic_problem"] = blob.splitlines()[0].strip()[:240]
    return fields


def _claims_from_list(items: list[str], label: str = "OBSERVED", limit: int = 6) -> str:
    lines = [_claim(item, label) for item in items[:limit] if item.strip()]
    return "\n".join(lines)


def _is_placeholder_section(body: str) -> bool:
    """True when section is empty or only a generic NOT_COMPUTABLE stub."""
    text = (body or "").strip()
    if not text:
        return True
    if "insufficient evidence for this section" in text.lower():
        return True
    # Single-line NOT_COMPUTABLE awaiting evidence — replaceable when brief arrives.
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) == 1 and "NOT_COMPUTABLE" in lines[0] and "Awaiting evidence" in lines[0]:
        return True
    return False


def resolve_design_text(
    explicit: str | None = None,
    input_text: str | None = None,
    evidence_text: str | None = None,
    *,
    auto_discover: bool = True,
) -> str | None:
    """Resolve design.md text from explicit flag, input/evidence, or project files."""
    if explicit and explicit.strip():
        return explicit
    for candidate in (input_text, evidence_text):
        if not candidate:
            continue
        head = candidate.lstrip()[:400]
        if head.startswith("# Design") or "Revision:" in head or "## Dramatic engine" in candidate:
            return candidate
    if not auto_discover:
        return None
    import os
    from pathlib import Path

    roots: list[Path] = []
    project_dir = os.environ.get("KUBRICK_PROJECT_DIR")
    if project_dir:
        roots.append(Path(project_dir))
    roots.append(Path.cwd())
    seen: set[Path] = set()
    for root in roots:
        root = root.resolve()
        if root in seen:
            continue
        seen.add(root)
        for rel in ("design.md", "out/design.md", "docs/design.md"):
            path = root / rel
            if path.is_file():
                try:
                    return path.read_text(encoding="utf-8")
                except OSError:
                    continue
    return None


def parse_design_md(text: str) -> dict[str, str]:
    """Parse a design.md into section_id -> body (best-effort, stable IDs)."""
    titles = {title.lower(): sid for sid, title in DESIGN_SECTIONS}
    sections: dict[str, str] = {sid: "" for sid, _ in DESIGN_SECTIONS}
    if text.strip() and not SECTION_RE.search(text):
        sections["creative-objective"] = text.strip()
        return sections
    # re.split with one group returns [pre, title, body, title, body...]
    tokens = SECTION_RE.split(text)
    if len(tokens) <= 1:
        return sections
    i = 1
    while i + 1 < len(tokens):
        title = tokens[i].strip()
        body = tokens[i + 1].strip()
        sid = titles.get(title.lower())
        if sid is None:
            # fuzzy: match by keyword
            lowered = title.lower()
            for candidate_sid, candidate_title in DESIGN_SECTIONS:
                if candidate_title.lower() in lowered or lowered in candidate_title.lower():
                    sid = candidate_sid
                    break
            if sid is None:
                sid = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")[:48] or "custom"
        sections[sid] = body
        i += 2
    return sections


def _product_version() -> str:
    from pathlib import Path

    from version_surfaces import product_version

    return product_version(Path(__file__).resolve().parent.parent)


def render_design_md(
    sections: dict[str, str],
    *,
    project_id: str,
    revision: str,
    authority: str = "PROPOSED",
) -> str:
    lines = [
        f"# Design — {project_id}",
        "",
        f"> Authority: `{authority}` · Revision: `{revision}` · Generated by Kubrick v{_product_version()}",
        "> Local outputs remain PROPOSED until explicitly promoted.",
        "",
    ]
    for sid, title in DESIGN_SECTIONS:
        body = (sections.get(sid) or "").strip()
        if not body:
            body = _claim("NOT_COMPUTABLE — insufficient evidence for this section", "NOT_COMPUTABLE")
        lines.extend([f"## {title}", "", body, ""])
    return "\n".join(lines).rstrip() + "\n"


def _base_meta(surface: str, action: str, project_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
    artifact_id = f"kubrick-{surface}-{action}-{_digest(inputs)}"
    return {
        "schema_version": "0.16.0",
        "artifact_id": artifact_id,
        "artifact_type": f"{surface}-{action}",
        "surface": surface,
        "action": action,
        "project_id": project_id,
        "source_state_id": f"state-{_digest({'project_id': project_id, **inputs})}",
        "authority": "PROPOSED",
        "status": "PROPOSED",
        "generated_at": _now(),
        "provenance": provenance_bucket(
            observed=[k for k, v in inputs.items() if v],
        ),
        "shared_invariants": {
            "preserve_identity": True,
            "preserve_locked_facts": True,
            "preserve_ownership": True,
            "preserve_chronology": True,
            "preserve_geometry": True,
            "preserve_material_state": True,
            "preserve_residue": True,
        },
        "not_computable": [],
    }


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
    from runtime_deps import yaml_load

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
    from provider_capabilities import capabilities_for, check_image_adapt, normalize_provider

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
        from adapt_provider import adapt  # local import avoids circular startup cost

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


def _shot_dict_to_adapter_packet(shot: dict[str, Any], provider: str = "generic") -> dict[str, Any]:
    from video_packet_bridge import shot_dict_to_adapter_packet

    return shot_dict_to_adapter_packet(shot, provider, _digest)


def _sequence_shot_name(shot: object, index: int) -> str:
    if isinstance(shot, dict):
        for key in ("shot_id", "frame_id", "id"):
            raw = shot.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    return f"index-{index}"


def _sequence_packet(data: dict[str, Any]) -> tuple[dict[str, Any], float | None] | None:
    result = data.get("result")
    if not isinstance(result, dict):
        return None
    shots = result.get("shots")
    if not isinstance(shots, list) or not shots:
        return None
    if len(shots) > 1:
        dropped = ", ".join(
            _sequence_shot_name(shot, index) for index, shot in enumerate(shots[1:], start=1)
        )
        raise ValueError(f"sequence adapt cannot keep every shot; dropped: {dropped}")
    shot = shots[0]
    if not isinstance(shot, dict):
        raise ValueError("sequence shot must be an object")
    return _shot_dict_to_adapter_packet(shot), shot.get("duration_seconds")


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


def script_rewrite(existing: str, project_id: str) -> dict[str, Any]:
    improved = script_improve(existing, project_id)
    improved["action"] = "rewrite"
    if improved.get("result"):
        improved["result"]["rewrite_mode"] = "causality-pressure-legibility"
    return improved


def script_expand(existing: str, project_id: str) -> dict[str, Any]:
    if not existing.strip():
        return {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": "script",
            "action": "expand",
            "diagnostic": {"code": "INSUFFICIENT_EVIDENCE", "message": "--input script is required"},
        }
    body = existing.rstrip() + "\n\n## Expanded beats\n"
    body += "- [PROPOSED] Hold on institutional geometry before the transfer\n"
    body += "- [PROPOSED] Make the ownership change observable without explanation\n"
    body += "- [NOT_COMPUTABLE] Dialogue expansion requires evidenced speech\n"
    meta = _base_meta("script", "expand", project_id, {"input": existing})
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "document_markdown": body,
        "script_revision": f"s-{_digest(body)}",
    }
    meta["artifact_type"] = "script-development-packet"
    return meta


def script_compress(existing: str, project_id: str) -> dict[str, Any]:
    if not existing.strip():
        return {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": "script",
            "action": "compress",
            "diagnostic": {"code": "INSUFFICIENT_EVIDENCE", "message": "--input script is required"},
        }
    lines = [ln for ln in existing.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    keep = lines[:12]
    body = "\n".join(
        [
            f"# Compressed script — {project_id}",
            "",
            *keep,
            "",
            "NOTE: Compression preserves observable action lines; dialogue may be omitted.",
            "",
        ]
    )
    meta = _base_meta("script", "compress", project_id, {"input": existing})
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "document_markdown": body,
        "script_revision": f"s-{_digest(body)}",
    }
    meta["artifact_type"] = "script-development-packet"
    return meta


def script_scene_extract(existing: str, project_id: str) -> dict[str, Any]:
    if not existing.strip():
        return {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": "script",
            "action": "scene-extract",
            "diagnostic": {"code": "INSUFFICIENT_EVIDENCE", "message": "--input script is required"},
        }
    scenes = []
    current: list[str] = []
    for line in existing.splitlines():
        if re.match(r"^(INT\.|EXT\.|##\s+Scene)", line, re.I):
            if current:
                scenes.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        scenes.append("\n".join(current).strip())
    if not scenes:
        scenes = [existing.strip()[:800]]
    meta = _base_meta("script", "scene-extract", project_id, {"input": existing})
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "scenes": [{"scene_id": f"scene-{i+1}", "text": s[:2000]} for i, s in enumerate(scenes[:20])],
        "scene_count": min(len(scenes), 20),
    }
    meta["artifact_type"] = "script-development-packet"
    return meta


def script_beat_validate(existing: str, project_id: str) -> dict[str, Any]:
    diag = script_diagnose(existing, project_id)
    findings = list((diag.get("result") or {}).get("findings") or [])
    if existing and not re.search(r"\b(because|then|after|before|when)\b", existing, re.I):
        findings.append(
            {
                "severity": "medium",
                "code": "WEAK_BEAT_CAUSALITY",
                "message": "Beats may lack explicit causal connectors",
            }
        )
    meta = _base_meta("script", "beat-validate", project_id, {"input": existing})
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "findings": findings,
        "qa_status": "FAIL" if any(f.get("severity") == "high" for f in findings) else "PASS",
    }
    meta["artifact_type"] = "script-diagnostic-report"
    return meta


def script_character_consistency(existing: str, project_id: str) -> dict[str, Any]:
    if not existing.strip():
        return {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": "script",
            "action": "character-consistency",
            "diagnostic": {"code": "INSUFFICIENT_EVIDENCE", "message": "--input script is required"},
        }
    names = sorted(set(re.findall(r"\b([A-Z][A-Z' -]{2,})\b", existing)))
    findings = []
    if not names:
        findings.append(
            {
                "severity": "medium",
                "code": "NO_CHARACTER_TOKENS",
                "message": "No uppercase character name tokens detected",
            }
        )
    meta = _base_meta("script", "character-consistency", project_id, {"input": existing})
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "character_tokens": names[:30],
        "findings": findings,
        "qa_status": "PASS" if not findings else "FAIL",
    }
    meta["artifact_type"] = "script-continuity-report"
    return meta


def script_dialog_validate(existing: str, project_id: str) -> dict[str, Any]:
    if not existing.strip():
        return {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": "script",
            "action": "dialog-validate",
            "diagnostic": {"code": "INSUFFICIENT_EVIDENCE", "message": "--input script is required"},
        }
    findings = []
    if "NOT_COMPUTABLE — no dialogue" in existing or "Dialogue" in existing and "NOT_COMPUTABLE" in existing:
        findings.append(
            {
                "severity": "low",
                "code": "DIALOGUE_ABSENT",
                "message": "Dialogue not evidenced — valid fail-closed state",
            }
        )
    if re.search(r"\b(as you know|let me explain)\b", existing, re.I):
        findings.append(
            {
                "severity": "high",
                "code": "EXPOSITION_DIALOGUE",
                "message": "Possible exposition-as-dialogue",
            }
        )
    meta = _base_meta("script", "dialog-validate", project_id, {"input": existing})
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "findings": findings,
        "qa_status": "FAIL" if any(f.get("severity") == "high" for f in findings) else "PASS",
    }
    meta["artifact_type"] = "script-diagnostic-report"
    return meta


def script_genre_validate(existing: str, evidence: str | None, project_id: str) -> dict[str, Any]:
    if not existing.strip():
        return {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": "script",
            "action": "genre-validate",
            "diagnostic": {"code": "INSUFFICIENT_EVIDENCE", "message": "--input script is required"},
        }
    blob = f"{existing}\n{evidence or ''}".lower()
    genre = "institutional-drama" if "authority" in blob or "badge" in blob else "unspecified"
    meta = _base_meta("script", "genre-validate", project_id, {"input": existing})
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "inferred_genre": genre,
        "qa_status": "PASS" if genre != "unspecified" else "FAIL",
        "findings": []
        if genre != "unspecified"
        else [{"severity": "medium", "code": "GENRE_UNSPECIFIED", "message": "Genre not evidenced"}],
    }
    meta["artifact_type"] = "script-diagnostic-report"
    return meta


def script_qa(existing: str, against: str | None, project_id: str) -> dict[str, Any]:
    diag = script_diagnose(existing, project_id)
    cont = script_continuity(existing, project_id)
    findings = list((diag.get("result") or {}).get("findings") or [])
    if cont.get("status") == "NOT_COMPUTABLE":
        findings.append({"severity": "high", "code": "CONTINUITY_FAIL", "message": "continuity check failed"})
    meta = _base_meta("script", "qa", project_id, {"input": existing, "against": against or ""})
    high = [f for f in findings if f.get("severity") == "high"]
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "qa_status": "FAIL" if high else "PASS",
        "findings": findings,
        "continuity": cont.get("result"),
        "dimensions": {
            "missing_context": len(existing.strip()) < 80,
            "broken_continuity": cont.get("status") == "NOT_COMPUTABLE",
            "weak_prompts": False,
            "duplicate_information": existing.count("\n\n") > 40,
        },
    }
    meta["artifact_type"] = "media-reconciliation-report"
    if high:
        meta["status"] = "NOT_COMPUTABLE"
        meta["authority"] = "NOT_COMPUTABLE"
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
