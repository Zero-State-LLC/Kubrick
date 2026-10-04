#!/usr/bin/env python3
"""Full take QC. Fixture verdicts only. ffmpeg runs only through an injected runner."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from structured_io import load_mapping  # noqa: E402
from take_qc import score_full  # noqa: E402

FIXTURE = ROOT / "evals" / "fixtures" / "ep01" / "take_qc_cases.yaml"


def _case(case_id: str) -> dict[str, object]:
    document = load_mapping(FIXTURE)
    rows = document.get("cases")
    assert isinstance(rows, list)
    found = next(item for item in rows if isinstance(item, dict) and item.get("id") == case_id)
    assert isinstance(found, dict)
    return found


def _codes(report: dict[str, object]) -> list[str]:
    defects = report["defects"]
    assert isinstance(defects, list)
    return [str(item["defect_code"]) for item in defects if isinstance(item, dict)]


def test_core_cases_keep_their_defects() -> None:
    clean = score_full(_case("v09-t2"))
    assert clean["status"] == "PROPOSED"
    assert _codes(clean) == []
    failed = score_full(_case("v09-t1"))
    assert _codes(failed) == ["push_drift"]
    ffmpeg = failed["ffmpeg"]
    assert isinstance(ffmpeg, dict) and ffmpeg["opted_in"] is False and ffmpeg["executed"] is False


def test_vlm_fixture_and_a_live_call_is_not_computable() -> None:
    document = _case("v09-t2")
    document["vlm"] = {
        "status": "fail",
        "defects": [{"defect_code": "wardrobe_drift", "hold_id": "vlm"}],
    }
    report = score_full(document)
    assert report["status"] == "PROPOSED"
    assert _codes(report) == ["wardrobe_drift"]
    live = dict(document)
    live["vlm"] = {"status": "fail", "live": True, "provider": "paid"}
    blocked = score_full(live)
    assert blocked["status"] == "NOT_COMPUTABLE"
    assert "VLM calls are not run" in str(blocked["message"])
    assert "wardrobe_drift" not in _codes(blocked)


def test_identity_similarity_and_timestamps() -> None:
    weak = _case("v09-t2")
    weak["identity"] = {"similarity": 0.50, "threshold": 0.85}
    assert "identity" in _codes(score_full(weak))
    strong = _case("v09-t2")
    strong["identity"] = {"similarity": 0.90}
    assert score_full(strong)["defects"] == []
    gap = _case("v09-t2")
    gap["timestamps"] = [0.0, 4.0]
    assert "timestamp_gap" in _codes(score_full(gap))
    covered = _case("v09-t2")
    samples = score_full(covered)["samples"]
    assert isinstance(samples, list)
    covered["timestamps"] = list(samples)
    assert score_full(covered)["defects"] == []
    late = _case("v09-t2")
    late["timestamps"] = [*samples, 9.0]
    outside = score_full(late)
    assert outside["status"] == "NOT_COMPUTABLE"
    assert outside["defects"] == []


def test_ffmpeg_runs_only_when_opted_in_with_a_runner() -> None:
    seen: list[int] = []

    def _runner(commands: object) -> dict[str, object]:
        assert isinstance(commands, list) and commands
        seen.append(len(commands))
        return {"status": "PROPOSED", "defects": [{"defect_code": "mae"}]}

    document = _case("v09-t2")
    assert score_full(document, runner=_runner)["ffmpeg"] == {
        "opted_in": False, "executed": False,
    }
    assert seen == []
    document["ffmpeg"] = True
    missing = score_full(document)
    assert missing["status"] == "NOT_COMPUTABLE"
    assert "no runner is configured" in str(missing["message"])
    assert seen == []
    ran = score_full(document, runner=_runner)
    assert len(seen) == 1 and seen[0] > 0
    assert "mae" in _codes(ran)
    ffmpeg = ran["ffmpeg"]
    assert isinstance(ffmpeg, dict) and ffmpeg["executed"] is True
    source = (ROOT / "src" / "kubrick" / "qc" / "take_qc.py").read_text(encoding="utf-8")
    imported = [
        line.strip() for line in source.splitlines()
        if line.strip().startswith(("import subprocess", "from subprocess"))
    ]
    assert imported == []
