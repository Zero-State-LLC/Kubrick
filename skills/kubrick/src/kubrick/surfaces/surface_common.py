#!/usr/bin/env python3
"""Shared design.md parsing, claims, and envelope metadata for surface compilers.

Split from surface_compilers.py (#72); public names are re-exported there.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from kubrick.paths import SKILL_ROOT
from kubrick.runtime.provenance import provenance_bucket

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
        import yaml

        loaded = yaml.safe_load(blob)
        if isinstance(loaded, dict):
            parsed = loaded
    # Fall back to line parsing if YAML parsing fails.
    except Exception:
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
    # Single-line NOT_COMPUTABLE awaiting evidence: replaceable when brief arrives.
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

    from kubrick.runtime.version_surfaces import product_version

    return product_version(SKILL_ROOT)

def render_design_md(
    sections: dict[str, str],
    *,
    project_id: str,
    revision: str,
    authority: str = "PROPOSED",
) -> str:
    lines = [
        f"# Design: {project_id}",
        "",
        f"> Authority: `{authority}` · Revision: `{revision}` · Generated by Kubrick v{_product_version()}",
        "> Local outputs remain PROPOSED until explicitly promoted.",
        "",
    ]
    for sid, title in DESIGN_SECTIONS:
        body = (sections.get(sid) or "").strip()
        if not body:
            body = _claim("NOT_COMPUTABLE: insufficient evidence for this section", "NOT_COMPUTABLE")
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
