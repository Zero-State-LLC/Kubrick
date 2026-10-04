#!/usr/bin/env python3
"""Retake router and fixture SFX. No provider call and no corpus write."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from edit_route import apply_drafts, route  # noqa: E402
from structured_io import load_mapping  # noqa: E402
from video_cues import sfx_estimate  # noqa: E402

FIXTURE = ROOT / "evals" / "fixtures" / "ep01" / "retake_routes.yaml"
EXPECT = {
    "shot-10-nails": ("mask_edit", "aleph"),
    "v07-light": ("mask_edit", "luma_modify"),
    "b11-crop": ("reboard", None),
    "v09-push": ("replan", None),
    "lens-flip": ("reference_fix", None),
    "v13-open": ("reference_fix", None),
}


def _cases() -> dict[str, dict[str, object]]:
    document = load_mapping(FIXTURE)
    rows = document.get("cases")
    assert isinstance(rows, list)
    return {str(item["id"]): item for item in rows if isinstance(item, dict)}


def test_six_labelled_failures_and_faint_nails_are_a_mask() -> None:
    cases = _cases()
    assert len(EXPECT) == 6
    for case_id, (action, provider) in EXPECT.items():
        report = route(cases[case_id])
        assert report["status"] == "PROPOSED", case_id
        assert report["corpus_write"] is False
        routes = report["routes"]
        assert isinstance(routes, list) and len(routes) == 1
        found = routes[0]
        assert isinstance(found, dict)
        assert found["action"] == action
        assert found["full_retake"] is False
        if provider:
            assert found["provider"] == provider
            assert found["mask"] == "sam2_track"
    nails = route(cases["shot-10-nails"])["routes"]
    assert isinstance(nails, list)
    instruction = str(nails[0]["instruction"])
    assert "faint nails" in instruction and "do not retake" in instruction


def test_ambiguous_jev_label_drafts_an_unapplied_drift_entry() -> None:
    report = route({
        "defects": [{
            "shot": "10",
            "label": "FRAMING",
            "jev_label": "IDENTITY",
        }],
    })
    assert report["routes"] == []
    drafts = report["drift_drafts"]
    assert isinstance(drafts, list) and len(drafts) == 1
    draft = drafts[0]
    assert isinstance(draft, dict)
    assert draft["applied"] is False
    assert draft["needs_human_approval"] is True
    assert draft["authority"] == "PROPOSED"
    assert draft["code"] == "AMBIGUOUS_ROUTE"
    with tempfile.TemporaryDirectory() as directory:
        out = Path(directory) / "corpus"
        refused = apply_drafts(drafts, out=out)
        assert refused["status"] == "NOT_COMPUTABLE"
        assert refused["applied"] is False
        assert refused["corpus_write"] is False
        assert not out.exists()
    unknown = route({"defects": [{"label": "SPEND"}]})
    assert unknown["status"] == "NOT_COMPUTABLE"


def test_sfx_estimate_is_a_fixture_and_zero_when_absent() -> None:
    quiet = sfx_estimate({})
    assert quiet == {"status": "PROPOSED", "credits": 0, "line": "sfx 0", "source": "fixture"}
    stated = sfx_estimate({"sfx": {"credits": 2}})
    assert stated["line"] == "sfx 2"
    assert stated["source"] == "fixture"
    assert sfx_estimate({"sfx": {"credits": -1}})["status"] == "NOT_COMPUTABLE"
    source = (ROOT / "src" / "kubrick" / "qc" / "edit_route.py").read_text(encoding="utf-8")
    assert "requests" not in source
