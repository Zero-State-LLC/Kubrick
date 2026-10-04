#!/usr/bin/env python3
"""Cinematic project state helper for cross-surface continuity (v0.16).

Builds a provider-neutral shared state snapshot from design.md / script /
brief evidence. Used by production surfaces and golden fixtures — does not
replace Continuity Forge authority.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from kubrick.runtime.provenance import provenance_bucket

SCHEMA_VERSION = "0.16.0"
REVISION_RE = re.compile(r"Revision:\s*`([^`]+)`")


def _digest(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _revision_from_text(text: str | None, prefix: str) -> str | None:
    if not text:
        return None
    match = REVISION_RE.search(text)
    if match:
        return match.group(1)
    return f"{prefix}-{_digest(text[:2000])}"


def build_cinematic_project_state(
    *,
    project_id: str,
    design_text: str | None = None,
    script_text: str | None = None,
    brief: str | None = None,
) -> dict[str, Any]:
    """Compile a cinematic-project-state artifact from available evidence."""
    design_rev = _revision_from_text(design_text, "r")
    script_rev = _revision_from_text(script_text, "s")
    blob = "\n".join(x for x in (brief, design_text, script_text) if x)
    dramatic = ""
    for line in blob.splitlines():
        if line.strip().startswith("dramatic_problem:"):
            dramatic = line.split(":", 1)[1].strip()
            break
    if not dramatic:
        for line in blob.splitlines():
            if line.strip() and not line.strip().startswith("#"):
                dramatic = line.strip()[:240]
                break

    geometry = re.findall(r"(?m)^(?:\s*-\s*)(.+)$", brief or "")
    state = {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "source_design_revision": design_rev,
        "source_script_revision": script_rev,
        "source_state_id": f"state-{_digest({'project_id': project_id, 'design': design_rev, 'script': script_rev})}",
        "locked_invariants": {
            "preserve_identity": True,
            "preserve_locked_facts": True,
            "preserve_ownership": True,
            "preserve_chronology": True,
            "preserve_geometry": True,
            "preserve_material_state": True,
            "preserve_residue": True,
        },
        "dramatic_pressure": dramatic or "NOT_COMPUTABLE",
        "visual_grammar": geometry[:8],
        "provider_independent_negatives": [
            "named occult labels",
            "identity reset",
            "geometry reset",
            "residue erasure",
        ],
        "not_computable": [] if dramatic else ["dramatic_pressure"],
        "authority": "PROPOSED",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provenance": provenance_bucket(
            observed=[k for k, v in {"brief": brief, "design": design_text, "script": script_text}.items() if v]
        ),
    }
    return state


def validate_cinematic_project_state(state: dict[str, Any]) -> dict[str, Any]:
    """Lightweight required-key validation (full JSON Schema remains in schemas/)."""
    required = ("project_id", "schema_version", "locked_invariants")
    missing = [k for k in required if k not in state]
    return {
        "status": "VALID" if not missing else "INVALID",
        "errors": [f"missing {k}" for k in missing],
    }
