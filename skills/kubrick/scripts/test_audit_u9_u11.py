"""Audit tests for issues #69-#71 (runbook, cut-qa, cues)."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

P: dict[str, object] = {
    "frames": [
        {
            "frame_id": "f1",
            "shot_id": "01",
            "duration_seconds": 4,
            "speech_lines": ["minder: Hi there"],
        },
        {
            "frame_id": "f2",
            "shot_id": "02",
            "duration_seconds": 4,
            "start_frame": {
                "asset": "starts/02.png",
                "at_seconds": 0.0,
                "source_take": "t",
                "verified": True,
            },
        },
    ],
    "characters": {
        "minder": {"voice": {"speaks": True, "library_id": "lib-1"}},
        "myslef": {"voice": {"speaks": False}},
    },
}


def _rows(value: object) -> list[dict[str, object]]:
    assert isinstance(value, list)
    rows: list[dict[str, object]] = []
    for item in value:
        assert isinstance(item, dict)
        rows.append(item)
    return rows


def _map(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value


def _num(value: object) -> float:
    assert isinstance(value, (int, float))
    return float(value)


class AuditU9U11(unittest.TestCase):
    def run_script(
        self, name: str, plan: dict[str, object], *extra: str
    ) -> tuple[int, dict[str, object]]:
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "plan.json"
            out = Path(tmp) / "out.json"
            inp.write_text(json.dumps(plan), encoding="utf-8")
            cmd = [
                sys.executable, f"scripts/{name}.py", "--surface-action", "x",
                "--input", str(inp), "--provider", "keyframe", "--output", str(out), *extra,
            ]
            proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
            self.assertTrue(out.exists(), proc.stderr)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertIsInstance(data, dict)
            return proc.returncode, data

    def test_runbook(self) -> None:
        code, data = self.run_script("video_runbook", P)
        self.assertEqual(code, 0)
        ops = _rows(data["ops"])
        self.assertEqual(ops[0]["op"], "regenerate")
        self.assertEqual(ops[0]["credits_label"], "INFERRED")
        self.assertTrue(any(o["op"] == "wait" and o["max_wait_seconds"] == 45 for o in ops))
        rejoin = [o for o in ops if o["op"] == "rejoin"]
        self.assertEqual(len(rejoin), 1)
        self.assertEqual(rejoin[0]["credits"], 0)

    def test_runbook_retake(self) -> None:
        plan = copy.deepcopy(P)
        frames = plan["frames"]
        assert isinstance(frames, list)
        frames[1]["join"] = {"chain_from": "01"}
        code, data = self.run_script("video_runbook", plan, "--retake", "02")
        self.assertEqual(code, 0)
        ops = _rows(data["ops"])
        regen = [o for o in ops if o["op"] == "regenerate"]
        self.assertEqual(len(regen), 1)
        self.assertEqual(regen[0]["shot"], "02")
        self.assertTrue(any(o["op"] == "reuse" and o["shot"] == "01" for o in ops))

    def test_runbook_retake_shared_clip(self) -> None:
        code, data = self.run_script("video_runbook", P, "--retake", "02")
        self.assertEqual(code, 0)
        regen = [o for o in _rows(data["ops"]) if o["op"] == "regenerate"]
        self.assertEqual(len(regen), 1)
        self.assertEqual(regen[0]["shots"], ["01", "02"])

    def test_runbook_retake_regenerates_reused_take(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            takes = Path(tmp) / "takes.json"
            takes.write_text(
                json.dumps([{"shot": "01", "take_id": "t1", "trim": {"in": 0, "out": 4}}]),
                encoding="utf-8",
            )
            _, kept = self.run_script("video_runbook", P, "--takes", str(takes))
            kept_ops = _rows(kept["ops"])
            self.assertTrue(any(o["op"] == "reuse" and o["shot"] == "01" for o in kept_ops))
            code, data = self.run_script(
                "video_runbook", P, "--takes", str(takes), "--retake", "01"
            )
        self.assertEqual(code, 0)
        ops = _rows(data["ops"])
        self.assertFalse(any(o["op"] == "reuse" and o["shot"] == "01" for o in ops))
        regen = [o for o in ops if o["op"] == "regenerate"]
        self.assertTrue(any(o.get("shot") == "01" or "01" in str(o.get("shots")) for o in regen))

    def test_runbook_unknown_retake(self) -> None:
        code, data = self.run_script("video_runbook", P, "--retake", "99")
        self.assertEqual(code, 4)
        self.assertEqual(data["code"], "RETAKE_UNKNOWN")

    def test_runbook_budget(self) -> None:
        plan = copy.deepcopy(P)
        plan["budget_cap_credits"] = 1
        code, data = self.run_script("video_runbook", plan)
        self.assertEqual(code, 4)
        self.assertEqual(data["code"], "BUDGET_CAP_EXCEEDED")

    def test_cut_qa(self) -> None:
        code, data = self.run_script("video_cut_qa", P)
        self.assertEqual(code, 0)
        self.assertFalse(data["executes"])
        cuts = _rows(data["expected_cuts"])
        self.assertEqual(len(cuts), 1)
        _, rb = self.run_script("video_runbook", P)
        edits = _rows(_rows(rb["ops"])[-2]["edit_plan"])
        first = _num(edits[0]["out"]) - _num(edits[0]["in"])
        self.assertAlmostEqual(_num(cuts[0]["at_seconds"]), round(first, 4))
        mae = [c for c in _rows(data["commands"]) if c["kind"] == "start_frame_mae"]
        self.assertEqual(len(mae), 1)
        self.assertIn("starts/02.png", str(mae[0]["command"]))

    def test_cues(self) -> None:
        code, data = self.run_script("video_cues", P)
        self.assertEqual(code, 0)
        cues = _rows(data["cues"])
        self.assertEqual(len(cues), 1)
        self.assertEqual(cues[0]["speaker"], "minder")
        self.assertEqual(cues[0]["voice"], "lib-1")
        variants = _rows(data["mix_variants"])
        self.assertEqual(len(variants), 2)
        for v in variants:
            self.assertEqual(v["integrated_lufs"], -14)
            self.assertEqual(v["true_peak_dbtp"], -1)
        self.assertEqual(_map(data["elevenlabs_estimate"])["total_credits"], len("Hi there"))
        sfx = _map(data["sfx_estimate"])
        self.assertEqual(sfx["line"], "sfx 0")
        self.assertEqual(sfx["credits"], 0)
        self.assertEqual(sfx["source"], "fixture")

    def test_cues_voice_lock(self) -> None:
        plan = copy.deepcopy(P)
        frames = plan["frames"]
        assert isinstance(frames, list)
        frames[1]["speech_lines"] = ["myslef: I should not talk"]
        code, data = self.run_script("video_cues", plan)
        self.assertEqual(code, 4)

    def test_cues_name_clone_lock(self) -> None:
        plan = copy.deepcopy(P)
        chars = _map(plan["characters"])
        chars["minder"] = {"voice": {"speaks": True, "name": "danny", "never_clone_of": ["Danny"]}}
        code, data = self.run_script("video_cues", plan)
        self.assertEqual(code, 4)
        self.assertEqual(data["code"], "VOICE_LOCK_VIOLATION")
        self.assertEqual(data["code"], "VOICE_LOCK_VIOLATION")

    def test_cues_cap(self) -> None:
        plan = copy.deepcopy(P)
        plan["elevenlabs"] = {"cap_credits": 1}
        code, data = self.run_script("video_cues", plan)
        self.assertEqual(code, 4)
        self.assertEqual(data["code"], "ELEVENLABS_CAP_EXCEEDED")


if __name__ == "__main__":
    unittest.main()
