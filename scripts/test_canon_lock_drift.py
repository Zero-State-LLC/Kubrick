#!/usr/bin/env python3
"""Plan lock text must match the canon lock file it names. Offline.

Generic cases use temp files. MYSLEF is only the test tenant.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from kubrick.gates.canon_locks import canon_block, canon_lock_drift  # noqa: E402
from kubrick.runtime.io_safety import load_structured  # noqa: E402

MYSLEF = ROOT / "examples" / "myslef-minder" / "storyboard-plan.yaml"
CANON = {"locks": [{"id": "badge", "positive": "one green badge light", "negative": "no glow"}]}


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _with_canon(tmp: str, plan: dict[str, object]) -> dict[str, object]:
    (Path(tmp) / "canon.json").write_text(json.dumps(CANON), encoding="utf-8")
    return dict(plan, canon_locks="canon.json")


def test_no_canon_reference_is_silent() -> None:
    assert canon_lock_drift({"locks": [{"id": "badge"}]}, ROOT, _load) == []


def test_matching_text_passes_and_whitespace_is_ignored() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        plan = _with_canon(tmp, {"locks": [
            {"id": "badge", "positive": "one  green badge light", "negative": "no glow"},
            {"id": "local-only", "negative": "no rain"},
        ]})
        assert canon_lock_drift(plan, Path(tmp), _load) == []


def test_same_id_different_text_fails() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        plan = _with_canon(tmp, {"locks": [
            {"id": "badge", "positive": "the badge light stays dark", "negative": "no glow"},
        ]})
        found = canon_lock_drift(plan, Path(tmp), _load)
        assert [(item["code"], item["field"]) for item in found] == [
            ("LOCK_CANON_DRIFT", "positive"),
        ]
        assert found[0]["canon_text"] == "one green badge light"
        lone = {"id": "badge", "positive": "one green badge light"}
        dropped = _with_canon(tmp, {"locks": [lone]})
        assert [item["field"] for item in canon_lock_drift(dropped, Path(tmp), _load)] == [
            "negative",
        ]


def test_canon_id_mapping_and_missing_or_bad_canon() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        mapped = _with_canon(tmp, {"locks": [{
            "id": "plan-badge", "canon_id": "badge",
            "positive": "one green badge light", "negative": "no glow",
        }]})
        assert canon_lock_drift(mapped, Path(tmp), _load) == []
        gone = _with_canon(tmp, {"locks": [{"id": "x", "canon_id": "nope"}]})
        assert canon_lock_drift(gone, Path(tmp), _load)[0]["code"] == "LOCK_CANON_MISSING"
        for bad in ({"canon_locks": ""}, {"canon_locks": "absent.json"}):
            assert canon_lock_drift(bad, Path(tmp), _load)[0]["code"] == "LOCK_CANON_UNREADABLE"


def test_myslef_tenant_matches_its_canon_and_drift_blocks_cues() -> None:
    plan = load_structured(MYSLEF)
    assert isinstance(plan, dict)
    assert canon_block(plan, MYSLEF) is None
    drifted = copy.deepcopy(plan)
    locks = drifted["locks"]
    assert isinstance(locks, list) and isinstance(locks[0], dict)
    locks[0]["positive"] = "the chest LED stays dark"
    blocked = canon_block(drifted, MYSLEF)
    assert blocked is not None and blocked.startswith("LOCK_CANON_DRIFT")
    with tempfile.TemporaryDirectory(dir=MYSLEF.parent) as tmp:
        inp = Path(tmp) / "plan.yaml"
        out = Path(tmp) / "out.json"
        inp.write_text(json.dumps(drifted), encoding="utf-8")
        cmd = [
            sys.executable, "scripts/video_cues.py", "--surface-action", "x",
            "--input", str(inp), "--provider", "keyframe", "--output", str(out),
        ]
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
        assert out.exists(), proc.stderr
        data = json.loads(out.read_text(encoding="utf-8"))
        assert proc.returncode != 0
        assert data["code"] == "LOCK_CANON_DRIFT"
        assert "elevenlabs_estimate" not in data
    source = (ROOT / "src" / "kubrick" / "gates" / "canon_locks.py").read_text(encoding="utf-8")
    assert "myslef" not in source.casefold()
