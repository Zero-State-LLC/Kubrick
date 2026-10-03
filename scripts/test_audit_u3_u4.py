#!/usr/bin/env python3
"""Tests for sequence adapt (#63) and take selection (#64)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from retime_plan import retime  # noqa: E402
from sequence_adapt import sequence_adapter_packet  # noqa: E402
from take_ledger import impact  # noqa: E402
from take_select import parse_take_overrides, select_take  # noqa: E402

_BOARD: dict[str, object] = {
    "frames": [{"frame_id": "a", "shot_id": "01"}, {"frame_id": "b", "shot_id": "02"}]
}


def _takes() -> list[dict[str, object]]:
    return [
        {"shot": "01", "take_id": "t1", "observed_end_state": {"props": {"x": "y"}}},
        {"shot": "01", "take_id": "t2", "observed_end_state": {"props": {"x": "y"}}},
    ]


class TakeSelectTests(unittest.TestCase):
    def test_parse(self) -> None:
        self.assertEqual(parse_take_overrides([" 01 = t2 "]), {"01": "t2"})
        self.assertEqual(parse_take_overrides(None), {})
        with self.assertRaises(ValueError):
            parse_take_overrides(["01"])
        with self.assertRaises(ValueError):
            parse_take_overrides(["01="])
        with self.assertRaises(ValueError):
            parse_take_overrides(["01=t1", "01=t2"])

    def test_select(self) -> None:
        one = {"take_id": "t1"}
        two = {"take_id": "t2"}
        self.assertIs(select_take([one, two], {"01"}, "01", {"01": "t2"})[0], two)
        miss = select_take([one, two], {"01"}, "01", {"01": "t9"})[1]
        self.assertEqual(miss and miss["code"], "TAKE_NOT_FOUND")
        both = [{"take_id": "t1", "selected": True}, {"take_id": "t2", "selected": True}]
        amb = select_take(both, {"01"}, "01", {})[1]
        self.assertEqual(amb and amb["code"], "TAKE_AMBIGUOUS")
        picked = {"take_id": "t2", "selected": True}
        self.assertIs(select_take([one, picked], {"01"}, "01", {})[0], picked)
        self.assertIs(select_take([one], {"01"}, "01", {})[0], one)

    def test_impact(self) -> None:
        result = impact(_BOARD, _takes(), "01")
        self.assertEqual(result["status"], "NOT_COMPUTABLE")
        self.assertEqual(result["code"], "TAKE_AMBIGUOUS")
        self.assertEqual(impact(_BOARD, _takes(), "01", {"01": "t2"})["status"], "PROPOSED")
        self.assertEqual(impact(_BOARD, _takes(), "01", {"01": "t9"})["code"], "TAKE_NOT_FOUND")

    def test_retime(self) -> None:
        doc: dict[str, object] = {
            "frames": [{"frame_id": "a", "shot_id": "01", "duration_seconds": 4}]
        }
        takes: list[dict[str, object]] = [
            {"shot": "01", "take_id": "t1", "trim": {"in": 0, "out": 4}},
            {"shot": "01", "take_id": "t2", "trim": {"in": 1, "out": 5}},
        ]
        result = retime(doc, "generic", takes, overrides={"01": "t2"})
        self.assertEqual(result["status"], "PROPOSED")
        generation = result["generation_plan"]
        edits = result["edit_plan"]
        assert isinstance(generation, list) and isinstance(edits, list)
        self.assertEqual(generation[0]["mode"], "reuse_take")
        self.assertEqual(edits[0]["in"], 1)
        for take in takes:
            take["selected"] = True
        closed = retime(doc, "generic", takes)
        self.assertEqual(closed["status"], "NOT_COMPUTABLE")
        self.assertEqual(closed["code"], "TAKE_AMBIGUOUS")

    def test_unknown_override_shot(self) -> None:
        doc: dict[str, object] = {
            "frames": [{"frame_id": "a", "shot_id": "01", "duration_seconds": 4}]
        }
        result = retime(doc, "generic", [], overrides={"99": "t9"})
        self.assertEqual(result["code"], "TAKE_NOT_FOUND")
        stray = impact(_BOARD, _takes(), "01", {"01": "t1", "99": "t9"})
        self.assertEqual(stray["status"], "NOT_COMPUTABLE")
        self.assertEqual(stray["code"], "TAKE_NOT_FOUND")

    def test_unusable_selected_take_refuses(self) -> None:
        doc: dict[str, object] = {
            "frames": [{"frame_id": "a", "shot_id": "01", "duration_seconds": 4}]
        }
        takes: list[dict[str, object]] = [
            {"shot": "01", "take_id": "t1", "trim": {"in": 0, "out": 4}},
            {"shot": "01", "take_id": "t2", "trim": {"in": 0, "out": 2}},
        ]
        result = retime(doc, "generic", takes, overrides={"01": "t2"})
        self.assertEqual(result["status"], "NOT_COMPUTABLE")
        self.assertEqual(result["code"], "TAKE_UNUSABLE")


class SequenceAdaptTests(unittest.TestCase):
    @staticmethod
    def _packet(shot: dict[str, object]) -> dict[str, object]:
        return {
            "frames": [{"frame_id": str(shot["frame_id"]), "prompt": "p"}],
            "shared_constraints": {"negative_constraints": shot.get("neg", [])},
        }

    def test_same_constraints_combine(self) -> None:
        shots: list[object] = [
            {"frame_id": "a", "neg": ["rain"]},
            {"frame_id": "b", "neg": ["rain"]},
        ]
        packet, _longest = sequence_adapter_packet(shots, self._packet)
        frames = packet["frames"]
        assert isinstance(frames, list)
        self.assertEqual([f["frame_id"] for f in frames], ["a", "b"])
        self.assertEqual(packet["shared_constraints"], {"negative_constraints": ["rain"]})

    def test_diverging_constraints_fail_closed(self) -> None:
        shots: list[object] = [{"frame_id": "a", "neg": ["rain"]}, {"frame_id": "b"}]
        with self.assertRaisesRegex(ValueError, "negative_constraints differ from shot a"):
            sequence_adapter_packet(shots, self._packet)


if __name__ == "__main__":
    unittest.main()
