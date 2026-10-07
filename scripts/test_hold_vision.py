"""hold_vision (#93): per-hold verdicts on frames, fail closed, take_qc verdict."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kubrick.qc.board_pixels import RGBImage, encode_png  # noqa: E402
from kubrick.qc.board_vision import BackendUnavailable  # noqa: E402
from kubrick.qc.hold_vision import (  # noqa: E402
    Frame,
    frame_verdict,
    hold_verdict,
    judge_holds,
    main,
    markdown,
    parse_holds,
)
from kubrick.qc.take_qc import score_full  # noqa: E402

IMG = RGBImage(1, 1, b"\0\0\0")


class Table:
    name = "table"

    def __init__(self, answers: dict[tuple[str, str], str]) -> None:
        self.answers = answers

    def ask(self, image: RGBImage, image_sha256: str, question: str) -> str:
        key = (image_sha256, question)
        if key not in self.answers:
            raise BackendUnavailable("no answer")
        return self.answers[key]


HOLDS = parse_holds([
    {"hold_id": "hands", "question": "Silicon hands?", "expect": "yes"},
    {"hold_id": "glow", "question": "Lens glowing?", "expect": "no"},
])
FRAMES = [Frame("mid", 2.0, IMG, "a"), Frame("end", 4.0, IMG, "b")]


def test_parse_holds_rejects_bad_rows() -> None:
    for bad in ([], [{"hold_id": "x", "question": "q", "expect": "maybe"}],
                [{"hold_id": "x", "question": "q", "expect": "yes"}] * 2, "x"):
        with pytest.raises(ValueError):
            parse_holds(bad)
    parsed = parse_holds({"holds": [{"hold_id": "x", "question": "q", "expect": "YES"}]})
    assert parsed[0].expect == "yes"


def test_verdict_rules() -> None:
    assert frame_verdict("yes", "yes") == "pass"
    assert frame_verdict("no", "yes") == "fail"
    assert frame_verdict("unknown", "yes") == "unverified"
    assert hold_verdict(["pass", "pass"]) == "pass"
    assert hold_verdict(["fail", "fail"]) == "fail"
    assert hold_verdict(["pass", "fail"]) == "borderline"
    assert hold_verdict(["pass", "unverified"]) == "unverified"
    assert hold_verdict([]) == "unverified"


def test_fail_becomes_take_qc_defect() -> None:
    judge = Table({("a", "Silicon hands?"): "no", ("b", "Silicon hands?"): "No.",
                   ("a", "Lens glowing?"): "no", ("b", "Lens glowing?"): "yes"})
    report = judge_holds(HOLDS, FRAMES, judge)
    rows = {r["hold_id"]: r for r in report["holds"]}  # type: ignore[union-attr]
    assert rows["hands"]["verdict"] == "fail"
    assert (rows["hands"]["t_start"], rows["hands"]["t_end"]) == (2.0, 4.0)
    assert rows["glow"]["verdict"] == "borderline"
    assert report["authority"] == "PROPOSED"
    assert report["vlm"] == {"status": "fail",
                             "defects": [{"hold_id": "hands", "defect_code": "VLM_HOLD_FAIL"}]}
    assert "| hands | yes | fail |" in markdown(report)
    full = score_full({"duration_seconds": 4, "vlm": report["vlm"]})
    codes = {d.get("defect_code") for d in full.get("defects", []) if isinstance(d, dict)}
    assert "VLM_HOLD_FAIL" in codes


def test_backend_down_is_unverified_and_not_computable() -> None:
    report = judge_holds(HOLDS, FRAMES, Table({}))
    assert report["counts"] == {"pass": 0, "fail": 0, "borderline": 0, "unverified": 2}
    assert report["vlm"] == {"status": "not_computable"}


def test_all_pass() -> None:
    judge = Table({(s, q): a for s in "ab" for q, a in (("Silicon hands?", "yes"),
                                                        ("Lens glowing?", "no"))})
    assert judge_holds(HOLDS, FRAMES, judge)["vlm"] == {"status": "pass"}


def test_cli_with_recorded_answers(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from kubrick.qc.board_pixels import file_sha256

    frame = tmp_path / "f.png"
    frame.write_bytes(encode_png(RGBImage(2, 2, b"\x80" * 12)))
    sha = file_sha256(frame)
    holds = tmp_path / "holds.json"
    holds.write_text(json.dumps([{"hold_id": "hands", "question": "Silicon hands?",
                                  "expect": "yes"}]), encoding="utf-8")
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps({"answers": {sha: {"Silicon hands?": "yes"}}}), encoding="utf-8")
    out = tmp_path / "r.json"
    code = main(["--holds", str(holds), "--frame", f"end=4={frame}", "--answers", str(answers),
                 "--crop", "full", "--out", str(out)])
    assert code == 0
    assert json.loads(out.read_text(encoding="utf-8"))["vlm"] == {"status": "pass"}
    assert main(["--holds", str(holds), "--answers", str(answers)]) == 2
    capsys.readouterr()
