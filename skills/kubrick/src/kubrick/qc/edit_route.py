#!/usr/bin/env python3
"""Retake router. Recommendations only. No provider call and no corpus write.

Issue #104, with #92 drift drafts and #108 left to the cue sheet. A human
approves before any corpus change. Drafts stay PROPOSED and unapplied.

#92: an ambiguous draft carries ``drift_entry``, a candidate known-drift entry
that validates against ``schemas/drift-registry.schema.json``, or
``missing_fields`` when the defect lacks what the entry needs. The report shape
is ``schemas/retake-route-report.schema.json``.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path

from kubrick.paths import SKILL_ROOT

_LABELS = {
    "LOCALIZED_MATERIAL": "mask_edit",
    "LOCALIZED_LIGHT": "mask_edit",
    "FRAMING": "reboard",
    "MOTION_INFEASIBLE": "replan",
    "IDENTITY": "reference_fix",
}
_FROM_DEFECT = {
    "material": "LOCALIZED_MATERIAL",
    "light_emitter": "LOCALIZED_LIGHT",
    "crop_line": "FRAMING",
    "head_ratio": "FRAMING",
    "edge_cut": "FRAMING",
    "push_drift": "MOTION_INFEASIBLE",
    "small_motion": "MOTION_INFEASIBLE",
    "open_copy": "IDENTITY",
    "ref_copy": "IDENTITY",
    "lens_side": "IDENTITY",
}
_PROVIDERS = {"aleph", "luma_modify", "wan_vace"}
_DEFAULT_PROVIDER = {"LOCALIZED_MATERIAL": "aleph", "LOCALIZED_LIGHT": "luma_modify"}
_DRIFT_SCHEMA = SKILL_ROOT / "schemas" / "drift-registry.schema.json"
REGISTRY = SKILL_ROOT / "assets" / "drift" / "known_drift.yaml"


def _drift_schema() -> dict[str, object]:
    loaded = json.loads(_DRIFT_SCHEMA.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("drift registry schema must be an object")
    return loaded


def trigger_kinds() -> frozenset[str]:
    """Trigger kinds the drift registry schema allows."""
    entries = _drift_schema()["properties"]["entries"]  # type: ignore[index]
    kinds = entries["items"]["properties"]["trigger"]["properties"]["kind"]["enum"]
    return frozenset(str(item) for item in kinds)


def _text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _rows(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _label(defect: Mapping[str, object]) -> str:
    named = _text(defect.get("label"))
    if named:
        return named
    return _FROM_DEFECT.get(_text(defect.get("defect_code")), "")


def _ambiguous(defect: Mapping[str, object], label: str) -> bool:
    jev = _text(defect.get("jev_label"))
    if jev and jev != label:
        return True
    labels = defect.get("labels")
    return isinstance(labels, Sequence) and not isinstance(labels, (str, bytes)) and len(labels) > 1


def _provider(defect: Mapping[str, object], label: str) -> str | None:
    chosen = _text(defect.get("provider")) or _DEFAULT_PROVIDER.get(label, "")
    if chosen in _PROVIDERS:
        return chosen
    return None


def _instruction(defect: Mapping[str, object], label: str) -> str:
    detail = _text(defect.get("detail"))
    if "nail" in detail.casefold():
        return "mask the faint nails; do not retake the shot"
    if label == "LOCALIZED_LIGHT":
        return "mask the localized emitter and keep it dark"
    if label == "LOCALIZED_MATERIAL":
        return "mask the localized material and keep the rest of the frame"
    if label == "FRAMING":
        return "re-board the shot before another video take"
    if label == "MOTION_INFEASIBLE":
        return "re-plan the move; do not spend a retake on the same action"
    return "fix the reference pack before another take"


def _first(*values: object) -> str:
    for value in values:
        text = value.isoformat() if isinstance(value, date) else _text(value)
        if text:
            return text
    return ""


def drift_entry(
    defect: Mapping[str, object],
    label: str,
    instruction: str,
    document: Mapping[str, object],
    kinds: frozenset[str],
) -> tuple[dict[str, object] | None, list[str]]:
    missing: list[str] = []
    shot = _text(defect.get("shot"))

    trigger_kind = _text(defect.get("trigger_kind"))
    if trigger_kind not in kinds:
        missing.append("trigger_kind")

    model = _first(defect.get("model"), document.get("model"))
    if not model:
        missing.append("model")

    effect = _text(defect.get("detail"))
    if not effect:
        missing.append("effect")

    observed_on = _first(defect.get("observed_on"), document.get("observed_on"))
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", observed_on):
        missing.append("observed_on")

    evidence = _text(defect.get("evidence"))
    if not evidence:
        if shot:
            jev = _text(defect.get("jev_label")) or "none"
            evidence = f"shot {shot}: QC label {label}, Jev label {jev}"
        else:
            missing.append("evidence")

    if missing:
        return None, sorted(missing)

    trigger: dict[str, object] = {"kind": trigger_kind}
    feature = _text(defect.get("feature"))
    if feature:
        trigger["feature"] = feature

    raw_slug = f"{shot or 'plan'}-{label}-{trigger_kind}".lower()
    slug = "draft-" + re.sub(r"[^a-z0-9]+", "-", raw_slug).strip("-")

    entry: dict[str, object] = {
        "id": slug,
        "model": model,
        "trigger": trigger,
        "effect": effect,
        "mitigations": [instruction],
        "failed_mitigations": [],
        "evidence": evidence,
        "observed_on": observed_on,
    }
    return entry, []


def _draft(
    defect: Mapping[str, object], label: str, document: Mapping[str, object],
) -> dict[str, object]:
    draft: dict[str, object] = {
        "code": "AMBIGUOUS_ROUTE",
        "shot": _text(defect.get("shot")) or None,
        "label": label or _text(defect.get("jev_label")),
        "status": "PROPOSED",
        "authority": "PROPOSED",
        "applied": False,
        "needs_human_approval": True,
    }
    entry, missing = drift_entry(
        defect, label, _instruction(defect, label), document, trigger_kinds(),
    )
    if entry is not None:
        draft["drift_entry"] = entry
    else:
        draft["missing_fields"] = missing
    return draft


def _one(
    defect: Mapping[str, object], document: Mapping[str, object],
) -> tuple[dict[str, object] | None, dict[str, object] | None, str]:
    label = _label(defect)
    if not label or label not in _LABELS:
        return None, None, f"unknown route label {label or 'missing'}"
    if _ambiguous(defect, label):
        return None, _draft(defect, label, document), ""
    action = _LABELS[label]
    route: dict[str, object] = {
        "shot": _text(defect.get("shot")) or None,
        "label": label,
        "action": action,
        "full_retake": False,
        "instruction": _instruction(defect, label),
    }
    if action == "mask_edit":
        provider = _provider(defect, label)
        if provider is None:
            return None, None, "mask provider must be aleph, luma_modify, or wan_vace"
        route["provider"] = provider
        route["mask"] = "sam2_track"
    return route, None, ""


def route(document: Mapping[str, object]) -> dict[str, object]:
    """Recommend a next step for each labelled defect. Nothing is submitted."""
    routes: list[dict[str, object]] = []
    drafts: list[dict[str, object]] = []
    errors: list[str] = []
    for defect in _rows(document.get("defects")):
        found, draft, error = _one(defect, document)
        if error:
            errors.append(error)
        if found is not None:
            routes.append(found)
        if draft is not None:
            drafts.append(draft)
    status = "NOT_COMPUTABLE" if errors else "PROPOSED"
    report: dict[str, object] = {
        "status": status,
        "authority": "PROPOSED" if status == "PROPOSED" else "NOT_COMPUTABLE",
        "routes": routes,
        "drift_drafts": drafts,
        "corpus_write": False,
    }
    if errors:
        report["errors"] = errors
    return report


def validate_drafts(drafts: Sequence[Mapping[str, object]]) -> list[str]:
    """Errors for drafts whose ``drift_entry`` is absent or fails the drift schema."""
    from kubrick.runtime.runtime_deps import require_module

    jsonschema = require_module("jsonschema")
    validate = getattr(jsonschema, "validate")
    failure = getattr(jsonschema, "ValidationError")
    schema = _drift_schema()
    errors: list[str] = []
    seen: set[str] = set()
    for index, draft in enumerate(drafts, start=1):
        entry = draft.get("drift_entry")
        if not isinstance(entry, Mapping):
            missing = draft.get("missing_fields")
            detail = ", ".join(str(item) for item in missing) if isinstance(missing, list) else ""
            errors.append(f"draft {index} has no drift_entry (missing: {detail or 'unknown'})")
            continue
        ident = str(entry.get("id") or "")
        if ident in seen:
            errors.append(f"draft {index} repeats drift id {ident}")
        seen.add(ident)
        try:
            validate({"version": "draft", "entries": [dict(entry)]}, schema)
        except failure as exc:
            errors.append(f"draft {index} fails the drift schema: {getattr(exc, 'message', exc)}")
    return errors


def apply_drafts(
    drafts: Sequence[Mapping[str, object]],
    *,
    out: Path | None = None,
    approved_by: str | None = None,
) -> dict[str, object]:
    """Approval step. Without ``approved_by`` nothing is written.

    With an approver and valid drafts, ``out`` (when given) receives a registry
    patch for review. The known-drift registry itself is never written here.
    """
    refused: dict[str, object] = {
        "status": "NOT_COMPUTABLE",
        "authority": "NOT_COMPUTABLE",
        "applied": False,
        "corpus_write": False,
    }
    approver = _text(approved_by)
    if not approver:
        return {**refused, "message": "human approval is required before a corpus write"}
    errors = validate_drafts(drafts)
    if not drafts:
        errors.append("no drafts to approve")
    if errors:
        return {**refused, "message": "drafts do not validate", "errors": errors}
    if out is not None and out.resolve() == REGISTRY.resolve():
        return {**refused, "message": "the known-drift registry is changed by a reviewed PR"}
    entries = [dict(draft["drift_entry"]) for draft in drafts]  # type: ignore[call-overload]
    patch: dict[str, object] = {"version": "draft", "entries": entries}
    if out is not None:
        out.write_text(json.dumps(patch, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "status": "APPROVED",
        "authority": "PROPOSED",
        "approved_by": approver,
        "applied": False,
        "corpus_write": False,
        "patch": patch,
        "patch_path": str(out) if out is not None else None,
    }
