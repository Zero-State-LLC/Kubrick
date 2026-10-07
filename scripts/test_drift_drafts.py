"""#92: retake drift drafts validate against the drift schema, with an approval step."""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import date
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kubrick.qc.edit_route import (  # noqa: E402
    REGISTRY,
    apply_drafts,
    route,
    trigger_kinds,
    validate_drafts,
)

REPORT = json.loads((ROOT / "schemas/retake-route-report.schema.json").read_text("utf-8"))
DRIFT = json.loads((ROOT / "schemas/drift-registry.schema.json").read_text("utf-8"))


def _defect(**extra: object) -> dict[str, object]:
    base: dict[str, object] = {
        "shot": "07",
        "label": "FRAMING",
        "jev_label": "IDENTITY",
        "trigger_kind": "close_framing",
        "detail": "the head grows past the crop line on a close push",
        "feature": "head size",
    }
    base.update(extra)
    return base


def _drafts(report: dict[str, object]) -> list[dict[str, object]]:
    rows = report["drift_drafts"]
    assert isinstance(rows, list)
    return [row for row in rows if isinstance(row, dict)]


def test_report_matches_the_classifier_schema() -> None:
    report = route({
        "model": "generic-video-1",
        "observed_on": "2026-10-07",
        "defects": [_defect(), {"shot": "02", "defect_code": "edge_cut"}],
    })
    jsonschema.validate(report, REPORT)
    routes = report["routes"]
    assert isinstance(routes, list) and len(routes) == 1


def test_draft_entry_validates_against_the_drift_schema() -> None:
    report = route({
        "model": "generic-video-1", "observed_on": date(2026, 10, 7), "defects": [_defect()],
    })
    (draft,) = _drafts(report)
    entry = draft["drift_entry"]
    assert isinstance(entry, dict)
    jsonschema.validate({"version": "1", "entries": [entry]}, DRIFT)
    assert entry["id"] == "draft-07-framing-close-framing"
    assert entry["trigger"] == {"kind": "close_framing", "feature": "head size"}
    assert entry["observed_on"] == "2026-10-07"
    assert entry["evidence"] == "shot 07: QC label FRAMING, Jev label IDENTITY"
    assert validate_drafts([draft]) == []
    assert "close_framing" in trigger_kinds()


def test_missing_inputs_are_named_and_never_guessed() -> None:
    report = route({"defects": [_defect(trigger_kind="framing_drift", detail="")]})
    (draft,) = _drafts(report)
    assert "drift_entry" not in draft
    assert draft["missing_fields"] == ["effect", "model", "observed_on", "trigger_kind"]
    jsonschema.validate(report, REPORT)
    errors = validate_drafts([draft])
    assert len(errors) == 1 and "trigger_kind" in errors[0]


def test_approval_step() -> None:
    report = route({
        "model": "generic-video-1", "observed_on": "2026-10-07", "defects": [_defect()],
    })
    drafts = _drafts(report)
    with tempfile.TemporaryDirectory() as directory:
        out = Path(directory) / "patch.json"
        refused = apply_drafts(drafts, out=out)
        assert refused["status"] == "NOT_COMPUTABLE" and not out.exists()
        approved = apply_drafts(drafts, out=out, approved_by="reviewer")
        assert approved["status"] == "APPROVED"
        assert approved["applied"] is False and approved["corpus_write"] is False
        patch = json.loads(out.read_text("utf-8"))
        jsonschema.validate(patch, DRIFT)
        assert patch["entries"][0]["id"] == "draft-07-framing-close-framing"
    before = REGISTRY.read_bytes()
    blocked = apply_drafts(drafts, out=REGISTRY, approved_by="reviewer")
    assert blocked["status"] == "NOT_COMPUTABLE"
    assert REGISTRY.read_bytes() == before
    bad = route({"defects": [_defect()]})
    invalid = apply_drafts(_drafts(bad), approved_by="reviewer")
    assert invalid["status"] == "NOT_COMPUTABLE" and invalid["errors"]
    assert apply_drafts([], approved_by="reviewer")["status"] == "NOT_COMPUTABLE"
