#!/usr/bin/env python3
"""Script compilers: rewrite, expand, compress, scene extraction, and validators.

Split from surface_compilers.py (#72); public names are re-exported there.
"""
from __future__ import annotations

import re
from typing import Any

from surface_common import _base_meta, _digest
from surface_script import script_continuity, script_diagnose, script_improve


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
