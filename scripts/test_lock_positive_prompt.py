"""0.27.6: lock positives are compiled into prompts; canon drift compares critical."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kubrick.gates.canon_locks import canon_lock_drift  # noqa: E402
from kubrick.plan.lock_carriers import lock_table  # noqa: E402
from kubrick.plan.lock_positive_lines import lock_positive_lines  # noqa: E402
from kubrick.prompts.storyboard_prompts import shots_from_document  # noqa: E402


def test_lock_positive_lines_character_applicability():
    doc = {
        "locks": [
            {"character": "hero", "positive": "Brave hero"},
            {"character": "villain", "positive": "Dark lord"},
        ]
    }
    frame = {"cast": ["hero"]}
    assert lock_positive_lines(doc, frame) == ["Brave hero"]

    frame = {"cast": ["other"]}
    assert lock_positive_lines(doc, frame) == []

    frame = {}
    assert lock_positive_lines(doc, frame) == ["Brave hero", "Dark lord"]


def test_lock_positive_lines_no_character_always_applies():
    doc = {"locks": [{"positive": "Always here"}]}
    frame = {"cast": ["hero"]}
    assert lock_positive_lines(doc, frame) == ["Always here"]
    frame = {}
    assert lock_positive_lines(doc, frame) == ["Always here"]


def test_lock_positive_lines_skips_empty_positive():
    doc = {
        "locks": [
            {"positive": ""},
            {"positive": "   "},
            {"positive": "Valid"},
        ]
    }
    assert lock_positive_lines(doc, {}) == ["Valid"]


def test_lock_positive_lines_deduplicates():
    doc = {
        "locks": [
            {"positive": "Hello   world"},
            {"positive": "  hello world  "},
            {"positive": "HELLO WORLD"},
            {"positive": "Other"},
        ]
    }
    assert lock_positive_lines(doc, {}) == ["Hello world", "Other"]


def test_canon_drift_critical_mismatch(tmp_path):
    document = {
        "canon_locks": "canon.yaml",
        "locks": [
            {"id": "hero", "positive": "Bright", "critical": True},
        ],
    }

    def load(_p: Path):
        return {
            "locks": [
                {"id": "hero", "positive": "Bright", "critical": False},
            ]
        }

    findings = canon_lock_drift(document, tmp_path, load)
    assert len(findings) == 1
    assert findings[0]["code"] == "LOCK_CANON_DRIFT"
    assert findings[0]["field"] == "critical"


def test_canon_drift_identical(tmp_path):
    document = {
        "canon_locks": "canon.yaml",
        "locks": [
            {"id": "hero", "positive": "Bright", "critical": True},
        ],
    }

    def load(_p: Path):
        return {
            "locks": [
                {"id": "hero", "positive": "Bright", "critical": True},
            ]
        }

    assert canon_lock_drift(document, tmp_path, load) == []


def test_canon_drift_kind_only(tmp_path):
    document = {
        "canon_locks": "canon.yaml",
        "locks": [
            {"id": "hero", "positive": "Bright", "kind": "a"},
        ],
    }

    def load(_p: Path):
        return {
            "locks": [
                {"id": "hero", "positive": "Bright", "kind": "b"},
            ]
        }

    assert canon_lock_drift(document, tmp_path, load) == []


def _plan() -> dict[str, object]:
    return {
        "storyboard_id": "lamp-test",
        "locks": [
            {
                "id": "hero-badge", "kind": "prop", "critical": True, "character": "hero",
                "positive": "a small brass badge on the left lapel",
                "negative": "no badge on the right lapel",
            },
            {
                "id": "lamp", "kind": "light",
                "positive": "one warm desk lamp lights the room",
                "negative": "no overhead light",
            },
        ],
        "frames": [
            {"frame_id": "f1", "cast": ["hero"], "action": "hero reads",
             "node_states": {"room": "lit"}},
            {"frame_id": "f2", "cast": ["other"], "action": "other waits",
             "node_states": {"room": "lit"}},
        ],
    }


def test_compiled_prompts_carry_applicable_positives() -> None:
    shots = {str(s["shot_id"]): str(s["prompt"]) for s in shots_from_document(_plan())}
    assert "brass badge on the left lapel" in shots["f1"]
    assert "brass badge" not in shots["f2"]
    assert "one warm desk lamp lights the room" in shots["f1"]
    assert "one warm desk lamp lights the room" in shots["f2"]


def test_no_positive_not_in_prompt_without_drift() -> None:
    plan = _plan()
    frames = plan["frames"]
    assert isinstance(frames, list)
    rows = lock_table(plan, frames)
    assert rows
    assert all(row.get("code") != "LOCK_POSITIVE_NOT_IN_PROMPT" for row in rows)
    assert not [r for r in rows if r["shot"] == "f2" and r["lock"] == "hero-badge"]


def test_adapter_frame_prompt_is_the_one_checked() -> None:
    plan = _plan()
    raw = plan["frames"]
    assert isinstance(raw, list)
    frames = [dict(frame) for frame in raw]
    frames[0]["prompt"] = "hero reads; a prompt edited after compile"
    rows = lock_table(plan, frames)
    drifted = [r for r in rows if r.get("code") == "LOCK_POSITIVE_NOT_IN_PROMPT"]
    assert {(r["shot"], r["lock"]) for r in drifted} == {("f1", "hero-badge"), ("f1", "lamp")}


def test_scoped_out_lock_has_no_carrier_row_or_drift() -> None:
    plan = _plan()
    locks = plan["locks"]
    assert isinstance(locks, list)
    locks[1]["scope"] = {"shots": ["f1"]}
    shots = {
        str(s["shot_id"]): str(s["prompt"])
        for s in shots_from_document(plan)
    }
    lamp = locks[1]["positive"]
    assert lamp in shots["f1"]
    assert lamp not in shots["f2"]
    frames = plan["frames"]
    assert isinstance(frames, list)
    rows = lock_table(plan, frames)
    assert all(row.get("code") != "LOCK_POSITIVE_NOT_IN_PROMPT" for row in rows)
    assert not any(
        row.get("shot") == "f2" and row.get("lock") == "lamp" for row in rows
    )
    assert any(
        row.get("shot") == "f1" and row.get("lock") == "lamp" for row in rows
    )
