#!/usr/bin/env python3
"""Tests for issues #67 (capability caps, drift evidence) and #68 (compare_frame_state)."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import capability_caps  # noqa: E402
import drift_registry  # noqa: E402


def _run(storyboard: dict[str, object]) -> tuple[int, dict[str, object]]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "board.json"
        path.write_text(json.dumps(storyboard), encoding="utf-8")
        done = subprocess.run(
            [sys.executable, str(_HERE / "compare_frame_state.py"), "--storyboard", str(path)],
            capture_output=True, text=True, check=False,
        )
    return done.returncode, json.loads(done.stdout)


class CapsTest(unittest.TestCase):
    def test_model_limits(self) -> None:
        limits = capability_caps.model_limits("keyframe", {})
        self.assertEqual(limits["max_references"], 9)
        self.assertIs(limits["native_audio"], True)
        self.assertEqual(limits["model"], "seedance-2.5")

    def test_reference_cap(self) -> None:
        limits: dict[str, object] = {"max_references": 9, "model": "seedance-2.5"}
        ten: dict[str, object] = {"referenceImages": [f"r{i}" for i in range(10)], "shots": []}
        nine: dict[str, object] = {"referenceImages": [f"r{i}" for i in range(9)], "shots": []}
        error = capability_caps.reference_cap_error(ten, limits)
        self.assertIsNotNone(error)
        self.assertIn("REFERENCE_CAP_EXCEEDED", str(error))
        self.assertIsNone(capability_caps.reference_cap_error(nine, limits))
        self.assertIsNone(capability_caps.reference_cap_error(ten, {"model": "m"}))

    def test_native_audio(self) -> None:
        movie: dict[str, object] = {"shots": [
            {"title": "s1", "audio": {"speech": {"mode": "native", "lines": ["hi"]}}},
        ]}
        found = capability_caps.native_audio_warnings(movie, {"native_audio": False})
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["code"], "NATIVE_AUDIO_UNSUPPORTED")
        self.assertEqual(found[0]["shot"], "s1")
        self.assertEqual(capability_caps.native_audio_warnings(movie, {"native_audio": True}), [])

    def test_drift_evidence(self) -> None:
        entry: dict[str, object] = {
            "id": "x", "effect": "e",
            "evidence": "MYSLEF 2026-10-02", "observed_on": "2026-10-02",
        }
        self.assertEqual(drift_registry._warn(entry, "s1", None)["evidence"], "MYSLEF 2026-10-02")


class CompareTest(unittest.TestCase):
    def test_missing_frame_id(self) -> None:
        code, out = _run({"frames": [{"frame_id": "a"}, {}]})
        self.assertEqual(code, 4)
        self.assertEqual(out["status"], "NOT_COMPUTABLE")

    def test_convergence_lost(self) -> None:
        code, out = _run({"frames": [
            {"frame_id": "a", "convergence_sites": ["door"]}, {"frame_id": "b"},
        ]})
        self.assertEqual(code, 1)
        self.assertEqual(out["status"], "INVALID")
        errors = out["errors"]
        self.assertIsInstance(errors, list)
        assert isinstance(errors, list)
        self.assertTrue(any("lost convergence" in str(e) for e in errors))

    def test_clean(self) -> None:
        code, out = _run({"frames": [{"frame_id": "a"}, {"frame_id": "b"}]})
        self.assertEqual(code, 0)
        self.assertEqual(out["status"], "VALID")


if __name__ == "__main__":
    unittest.main()
