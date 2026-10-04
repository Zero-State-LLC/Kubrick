#!/usr/bin/env python3
"""Retake router. Recommendations only. No provider call and no corpus write.

Issue #104, with #92 drift drafts and #108 left to the cue sheet. A human
approves before any corpus change. Drafts stay PROPOSED and unapplied.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

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


def _draft(defect: Mapping[str, object], label: str) -> dict[str, object]:
    return {
        "code": "AMBIGUOUS_ROUTE",
        "shot": _text(defect.get("shot")) or None,
        "label": label or _text(defect.get("jev_label")),
        "status": "PROPOSED",
        "authority": "PROPOSED",
        "applied": False,
        "needs_human_approval": True,
    }


def _one(
    defect: Mapping[str, object],
) -> tuple[dict[str, object] | None, dict[str, object] | None, str]:
    label = _label(defect)
    if not label or label not in _LABELS:
        return None, None, f"unknown route label {label or 'missing'}"
    if _ambiguous(defect, label):
        return None, _draft(defect, label), ""
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
        found, draft, error = _one(defect)
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


def apply_drafts(
    drafts: Sequence[Mapping[str, object]],
    *,
    out: Path | None = None,
) -> dict[str, object]:
    """Refuse the corpus write. ``out`` is not created and not modified."""
    del drafts, out
    return {
        "status": "NOT_COMPUTABLE",
        "authority": "NOT_COMPUTABLE",
        "applied": False,
        "corpus_write": False,
        "message": "human approval is required before a corpus write",
    }
