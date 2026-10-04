#!/usr/bin/env python3
"""Board image gate. Tiny fixture PNGs, a mocked embedder, and recorded or fake judges.

No model is loaded and no paid API is called.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "evals" / "fixtures" / "board_images"
MYSLEF = ROOT / "examples" / "myslef-minder" / "storyboard-plan.yaml"
sys.path.insert(0, str(SCRIPTS))

import board_image_gate as gate  # noqa: E402
import board_pixels as pixels  # noqa: E402
import board_vision as vision  # noqa: E402
from io_safety import load_structured  # noqa: E402

_ENV = (
    "KUBRICK_JEV_URL",
    "KUBRICK_JEV_VERDICTS",
    "KUBRICK_JEV_OVERRIDE",
    "KUBRICK_BOARD_IMAGE_OPT_OUT",
    "KUBRICK_BOARD_JUDGE_ANSWERS",
    "KUBRICK_BOARD_VLM_URL",
    "KUBRICK_BOARD_VLM_MODEL",
)
_UNVERIFIED = {"BOARD_IDENTITY_UNVERIFIED", "BOARD_LOCK_DETAIL_UNVERIFIED"}


class HistogramEmbedder:
    """Stand-in for DINOv2: a color histogram that ignores the crop background."""

    name = "fake-histogram"

    def __init__(self) -> None:
        self.calls = 0

    def embed(self, image: pixels.RGBImage) -> list[float]:
        self.calls += 1
        background = image.pixel(0, 0)
        bins = [0.0] * 64
        data = image.pixels
        for offset in range(0, len(data), 3):
            red, green, blue = data[offset], data[offset + 1], data[offset + 2]
            if max(abs(red - background[0]), abs(green - background[1]),
                   abs(blue - background[2])) <= 40:
                continue
            bins[(red // 64) * 16 + (green // 64) * 4 + blue // 64] += 1.0
        bins[0] += 1e-6
        return bins


class FixedEmbedder:
    """Board crops embed to ``board``; every reference embeds to ``ref``."""

    name = "fake-fixed"

    def __init__(self, board: list[float], ref: list[float]) -> None:
        self.vectors = [board, ref]
        self.calls = 0

    def embed(self, image: pixels.RGBImage) -> list[float]:
        vector = self.vectors[0] if self.calls == 0 else self.vectors[1]
        self.calls += 1
        return vector


class FakeJudge:
    name = "fake-judge"

    def __init__(self, answer: str = "yes") -> None:
        self.answer = answer
        self.questions: list[str] = []

    def ask(self, image: pixels.RGBImage, image_sha256: str, question: str) -> str:
        self.questions.append(question)
        return self.answer


class NoEmbedder:
    name = "none"

    def embed(self, image: pixels.RGBImage) -> list[float]:
        raise vision.BackendUnavailable("DINOv2 needs torch (test stub)")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _ENV:
        monkeypatch.delenv(key, raising=False)


def _fixture_plan() -> dict[str, object]:
    raw = load_structured(str(FIXTURES / "plan.yaml"))
    assert isinstance(raw, dict)
    return raw


def _map(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value


def _rows(value: object) -> list[dict[str, object]]:
    assert isinstance(value, list)
    return [_map(item) for item in value]


def _codes(report: Mapping[str, object]) -> set[str]:
    return {str(row.get("code")) for row in _rows(report["checks"]) if row.get("code")}


# ----------------------------------------------------------------- gate ---

def _check(document: Mapping[str, object], **kwargs: object) -> dict[str, object]:
    options: dict[str, object] = {"base_dir": FIXTURES}
    options.update(kwargs)
    return gate.check_board_images(document, **options)


def test_matching_board_passes_identity_and_locks() -> None:
    report = _check(
        _fixture_plan(),
        shots={"01"},
        embedder=HistogramEmbedder(),
        answers_path=str(FIXTURES / "judge-answers.json"),
    )
    assert report["code"] == "BOARD_IMAGES_CLEAR"
    assert report["blocks_spend"] is False
    assert report["checked_before_spend"] is True
    assert report["default_on"] is True
    assert report["policy"] == "fail_closed"
    identity = [row for row in _rows(report["checks"]) if row["check"] == "identity"]
    assert identity[0]["status"] == "PASS"
    assert identity[0]["threshold"] == 0.7
    assert identity[0]["crop"] == "border_contrast"
    locks = [row for row in _rows(report["checks"]) if row["check"] == "lock_detail"]
    assert [row["status"] for row in locks] == ["PASS", "PASS"]
    assert _map(report["backends"])["judge"] == "recorded"


def test_mismatched_board_blocks_with_identity_and_lock_codes() -> None:
    report = _check(
        _fixture_plan(),
        embedder=HistogramEmbedder(),
        answers_path=str(FIXTURES / "judge-answers.json"),
    )
    assert report["status"] == "BLOCKED"
    assert report["blocks_spend"] is True
    assert report["code"] == "BOARD_IDENTITY_MISMATCH"
    assert {"BOARD_IDENTITY_MISMATCH", "BOARD_LOCK_DETAIL_FAIL"} <= _codes(report)
    message = str(report["message"])
    assert "shot 02" in message and "regenerate the board" in message
    assert "--board-image-opt-out" in message
    assert "regenerate the board" in str(report["recommendation"])
    passing = [row for row in _rows(report["checks"]) if row["shot"] == "01"]
    assert all(row["status"] == "PASS" for row in passing)
    identity = next(row for row in _rows(report["checks"])
                    if row["shot"] == "02" and row["check"] == "identity")
    if identity["crop"] != "plan_box":
        assert "board_subject_boxes" in str(identity["detail"])
    assert gate.crop_hint("plan_box") is None
    assert "head box" in str(gate.crop_hint("border_contrast"))


def test_missing_models_fail_closed_as_unverified(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gate, "resolve_embedder", lambda: NoEmbedder())
    report = _check(_fixture_plan(), shots={"01"})
    assert report["blocks_spend"] is True
    assert report["code"] == "BOARD_IDENTITY_UNVERIFIED"
    assert _codes(report) == _UNVERIFIED
    assert "KUBRICK_BOARD_VLM_URL" in str(report["message"])
    backends = _map(report["backends"])
    assert backends["judge"] == "local-vlm:" + vision.DEFAULT_VLM_MODEL


def test_judge_unknown_answer_is_unverified_and_blocks() -> None:
    report = _check(_fixture_plan(), shots={"01"}, embedder=HistogramEmbedder(),
                    judge=FakeJudge("unknown"))
    assert report["code"] == "BOARD_LOCK_DETAIL_UNVERIFIED"
    assert report["blocks_spend"] is True


def test_unresolvable_answers_file_is_unverified(tmp_path: Path) -> None:
    report = _check(_fixture_plan(), shots={"01"}, embedder=HistogramEmbedder(),
                    answers_path=str(tmp_path / "missing.json"))
    assert report["code"] == "BOARD_LOCK_DETAIL_UNVERIFIED"
    assert "cannot load" in str(_map(report["backends"])["judge_error"])


def test_threshold_precedence_and_validation() -> None:
    plan = _fixture_plan()
    close = FixedEmbedder([1.0, 0.0], [0.8, 0.6])
    report = _check(plan, shots={"01"}, embedder=close, judge=FakeJudge())
    assert report["code"] == "BOARD_IMAGES_CLEAR"
    strict = _check(plan, shots={"01"}, embedder=FixedEmbedder([1.0, 0.0], [0.8, 0.6]),
                    judge=FakeJudge(), identity_threshold=0.9)
    assert strict["code"] == "BOARD_IDENTITY_MISMATCH"
    row = next(item for item in _rows(strict["checks"]) if item["check"] == "identity")
    assert row["score"] == pytest.approx(0.8)
    assert row["threshold"] == 0.9
    character = _map(_map(plan["characters"])["myslef"])
    _map(character["ref_pack"])["identity_threshold"] = 0.85
    per_char = _check(plan, shots={"01"}, embedder=FixedEmbedder([1.0, 0.0], [0.8, 0.6]),
                      judge=FakeJudge())
    assert per_char["code"] == "BOARD_IDENTITY_MISMATCH"
    invalid = _check(plan, shots={"01"}, embedder=HistogramEmbedder(), judge=FakeJudge(),
                     identity_threshold=0.0)
    assert invalid["code"] == "BOARD_GATE_CONFIG_INVALID"
    plan["board_image_gate"] = {"identity_threshold": "high"}
    del _map(character["ref_pack"])["identity_threshold"]
    bad_plan = _check(plan, shots={"01"}, embedder=HistogramEmbedder(), judge=FakeJudge())
    assert bad_plan["code"] == "BOARD_GATE_CONFIG_INVALID"
    assert gate.DEFAULT_IDENTITY_THRESHOLD == 0.50


def test_opt_out_needs_a_reason_and_is_logged(monkeypatch: pytest.MonkeyPatch) -> None:
    logged: list[Mapping[str, object]] = []
    skipped = _check(_fixture_plan(), opt_out=True, opt_out_reason="EP-01 calibration run",
                     opt_out_source="flag", shots={"02"}, log=logged.append)
    assert skipped["code"] == "BOARD_IMAGE_OPT_OUT"
    assert skipped["blocks_spend"] is False
    assert skipped["opt_out_reason"] == "EP-01 calibration run"
    assert logged == [{
        "event": "BOARD_IMAGE_OPT_OUT", "source": "flag",
        "reason": "EP-01 calibration run", "shots": ["02"],
    }]
    blank = _check(_fixture_plan(), opt_out=True, opt_out_reason="")
    assert blank["code"] == "BOARD_OPT_OUT_REASON_MISSING"
    assert blank["blocks_spend"] is True
    assert gate.opt_out_requested("  why ") == (True, "why", "flag")
    assert gate.opt_out_requested(None) == (False, "", "")
    monkeypatch.setenv("KUBRICK_BOARD_IMAGE_OPT_OUT", "fixture replay")
    assert gate.opt_out_requested(None) == (True, "fixture replay", "env")
    sink = io.StringIO()
    gate.log_opt_out({"reason": "r"}, sink)
    assert sink.getvalue().startswith("BOARD_IMAGE_OPT_OUT {")


def test_cut_rules_block_a_reused_board_and_a_hidden_identity() -> None:
    plan = _fixture_plan()
    frames = _rows(plan["frames"])
    frames[1]["board_image"] = "board-match.png"
    reused = _check(plan, embedder=HistogramEmbedder(), judge=FakeJudge())
    assert reused["code"] == "BOARD_REUSED_ON_CUT"
    frames[1]["join"] = {"chain_from": "frame-001"}
    chained = _check(plan, embedder=HistogramEmbedder(), judge=FakeJudge())
    assert chained["code"] == "BOARD_IMAGES_CLEAR"
    frames[1]["cut"] = "cut-on-sound, thirty-degree"
    angled = _check(plan, embedder=HistogramEmbedder(), judge=FakeJudge())
    assert angled["code"] == "BOARD_REUSED_ON_CUT"
    del frames[1]["cut"]
    frames[0]["board_view"] = "back"
    frames[0]["reveals_identity"] = True
    hidden = _check(plan, shots={"01"}, embedder=HistogramEmbedder(), judge=FakeJudge())
    assert hidden["code"] == "START_FRAME_HIDES_IDENTITY"


def test_board_sources_missing_unreadable_and_not_local(tmp_path: Path) -> None:
    plan = _fixture_plan()
    frames = _rows(plan["frames"])
    frames[0]["board_image"] = "nope.png"
    missing = _check(plan, shots={"01"}, embedder=HistogramEmbedder(), judge=FakeJudge())
    assert missing["code"] == "BOARD_IMAGE_MISSING"
    junk = tmp_path / "junk.png"
    junk.write_bytes(b"\x89PNG\r\n\x1a\nbroken")
    frames[0]["board_image"] = str(junk)
    unreadable = _check(plan, shots={"01"}, embedder=HistogramEmbedder(), judge=FakeJudge())
    assert unreadable["code"] == "BOARD_IMAGE_UNREADABLE"
    del frames[0]["board_image"]
    frames[0]["start_frame"] = {"asset": "keyframe-asset-123", "verified": True}
    remote = _check(plan, shots={"01"}, embedder=HistogramEmbedder(), judge=FakeJudge())
    assert remote["code"] == "NO_BOARD_IMAGES"
    assert remote["blocks_spend"] is False
    assert _rows(remote["warnings"])[0]["code"] == "BOARD_IMAGE_NOT_LOCAL"
    frames[0]["start_frame"] = {"asset": "board-match.png"}
    local_asset = _check(plan, shots={"01"}, embedder=HistogramEmbedder(), judge=FakeJudge())
    assert local_asset["code"] == "BOARD_IMAGES_CLEAR"


def test_identity_needs_reference_views() -> None:
    plan = _fixture_plan()
    character = _map(_map(plan["characters"])["myslef"])
    views = _rows(_map(character["ref_pack"])["views"])
    for view in views:
        view["path"] = "gone.png"
    unreadable = _check(plan, shots={"01"}, embedder=HistogramEmbedder(), judge=FakeJudge())
    assert unreadable["code"] == "BOARD_IDENTITY_UNVERIFIED"
    assert "no reference view could be read" in str(unreadable["message"])
    del character["ref_pack"]
    none = _check(plan, shots={"01"}, embedder=HistogramEmbedder(), judge=FakeJudge())
    assert none["code"] == "BOARD_IDENTITY_UNVERIFIED"
    assert "no approved ref_pack identity views" in str(none["message"])


def test_lock_questions_cover_every_lock_source() -> None:
    document: dict[str, object] = {
        "locks": [
            {"id": "red-chest-light", "character": "myslef", "negative": "no red chest light"},
            {"id": "other", "character": "minder", "negative": "no hat"},
        ],
    }
    spec: dict[str, object] = {
        "character_locks": ["no nose", "No Nose"],
        "locks": [{"id": "dome", "positive": "smooth dome head"}],
        "board_checks": [
            {"id": "nails", "question": "Do the hands show fingernails?", "expect": "no"},
            {"question": "Bad expectation?", "expect": "maybe"},
        ],
    }
    questions = gate.lock_questions(document, "myslef", spec)
    assert [item["lock_id"] for item in questions] == [
        "no nose", "dome", "red-chest-light", "nails",
    ]
    assert questions[-1]["expect"] == "no"
    assert "no hat" not in json.dumps(questions)


def test_characters_off_screen_and_multi_character_boards() -> None:
    plan = _fixture_plan()
    frames = _rows(plan["frames"])
    frames[0]["characters"] = []
    unnamed = _check(plan, shots={"01"}, embedder=HistogramEmbedder(), judge=FakeJudge())
    assert "identity" in [row["check"] for row in _rows(unnamed["checks"])]
    frames[0]["cast"] = []
    empty = _check(plan, shots={"01"}, embedder=HistogramEmbedder(), judge=FakeJudge())
    assert empty["code"] == "BOARD_IMAGES_CLEAR"
    assert [row["check"] for row in _rows(empty["checks"])] == ["image"]
    del frames[0]["cast"]
    characters = _map(plan["characters"])
    characters["twin"] = characters["myslef"]
    frames[0]["characters"] = ["myslef", "twin"]
    frames[0]["board_subject_boxes"] = {"twin": [0.0, 0.0, 1.0, 1.0]}
    multi = _check(plan, shots={"01"}, embedder=HistogramEmbedder(), judge=FakeJudge())
    crops = {row["character"]: row["crop"] for row in _rows(multi["checks"])
             if row["check"] == "identity"}
    assert crops == {"myslef": "full_frame", "twin": "plan_box"}


def test_attach_board_gate_appends_to_payload_and_ledger(tmp_path: Path) -> None:
    report = _check(_fixture_plan(), shots={"01"}, embedder=HistogramEmbedder(),
                    judge=FakeJudge())
    payload: dict[str, object] = {"run_ledger": [{"kind": "jev_gate"}]}
    ledger = tmp_path / "ledger.json"
    assert gate.attach_board_gate(payload, report, str(ledger)) is None
    assert [row["kind"] for row in _rows(payload["run_ledger"])] == [
        "jev_gate", "board_image_gate",
    ]
    stored = json.loads(ledger.read_text(encoding="utf-8"))
    assert stored["entries"][0]["kind"] == "board_image_gate"
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("[1, 2]", encoding="utf-8")
    error = gate.attach_board_gate({}, report, str(corrupt))
    assert error is not None and error.startswith("LEDGER_INVALID")


# ------------------------------------------------------------ commands ---

def _env() -> dict[str, str]:
    env = os.environ.copy()
    for key in _ENV:
        env.pop(key, None)
    return env


def test_standalone_command_blocks_by_default_and_honors_opt_out() -> None:
    base = [sys.executable, str(SCRIPTS / "board_image_gate.py"),
            "--input", str(FIXTURES / "plan.yaml"), "--shot", "02",
            "--board-judge-answers", str(FIXTURES / "judge-answers.json")]
    blocked = subprocess.run(base, capture_output=True, text=True, check=False, env=_env(),
                             cwd=ROOT)
    assert blocked.returncode == 4, blocked.stderr
    data = json.loads(blocked.stdout)
    assert data["blocks_spend"] is True
    assert "BOARD_LOCK_DETAIL_FAIL" in _codes(data)
    skipped = subprocess.run([*base, "--board-image-opt-out", "manual review of shot 02"],
                             capture_output=True, text=True, check=False, env=_env(), cwd=ROOT)
    assert skipped.returncode == 0
    assert json.loads(skipped.stdout)["code"] == "BOARD_IMAGE_OPT_OUT"
    assert "BOARD_IMAGE_OPT_OUT" in skipped.stderr
    bad = subprocess.run([sys.executable, str(SCRIPTS / "board_image_gate.py"),
                          "--input", str(FIXTURES / "missing.yaml")],
                         capture_output=True, text=True, check=False, env=_env(), cwd=ROOT)
    assert bad.returncode == 2


def _myslef_with_board() -> dict[str, object]:
    raw = load_structured(str(MYSLEF))
    assert isinstance(raw, dict)
    raw["hold_list"] = []
    character = _map(_map(raw["characters"])["myslef"])
    character["ref_pack"] = {
        "asset_hash": "sha256:board-fixture-myslef",
        "views": [
            {"path": str(FIXTURES / "myslef-front.png"), "ref_role": "identity",
             "asset_hash": "sha256:front"},
            {"path": str(FIXTURES / "myslef-three-quarter.png"), "ref_role": "identity",
             "asset_hash": "sha256:three-quarter"},
        ],
    }
    frames = _rows(raw["frames"])
    shot_05 = next(frame for frame in frames if frame.get("shot_id") == "05")
    shot_05["board_image"] = str(FIXTURES / "board-match.png")
    return raw


def _runbook(plan: Mapping[str, object], *extra: str) -> tuple[int, dict[str, object], str]:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "plan.json"
        out = Path(tmp) / "out.json"
        source.write_text(json.dumps(plan), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "video_runbook.py"), "--input", str(source),
             "--provider", "keyframe", "--output", str(out), *extra],
            cwd=ROOT, capture_output=True, text=True, check=False, env=_env(),
        )
        data = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return proc.returncode, data, proc.stderr


def test_runbook_runs_the_board_gate_by_default_before_spend() -> None:
    plan = _myslef_with_board()
    code, data, _err = _runbook(plan)
    assert code == 4
    assert data["code"] in _UNVERIFIED | {"BOARD_IDENTITY_MISMATCH"}
    assert "ops" not in data
    assert "spend_estimate" not in data
    assert _map(data["board_image_gate"])["checked_before_spend"] is True
    assert [row["kind"] for row in _rows(data["run_ledger"])] == ["jev_gate", "board_image_gate"]
    code, data, err = _runbook(plan, "--board-image-opt-out", "fixture plan, no local models")
    assert code == 0, data
    assert data["status"] == "PROPOSED"
    assert "ops" in data
    assert _map(data["board_image_gate"])["code"] == "BOARD_IMAGE_OPT_OUT"
    assert "BOARD_IMAGE_OPT_OUT" in err
    code, data, _err = _runbook(plan, "--board-image-opt-out", "  ")
    assert code == 4
    assert data["code"] == "BOARD_OPT_OUT_REASON_MISSING"


def test_example_plan_without_board_images_is_unchanged() -> None:
    raw = load_structured(str(MYSLEF))
    assert isinstance(raw, dict)
    raw["hold_list"] = []
    code, data, _err = _runbook(raw)
    assert code == 0, data
    board = _map(data["board_image_gate"])
    assert board["code"] == "NO_BOARD_IMAGES"
    assert any(row["code"] == "BOARD_IMAGE_NOT_LOCAL" for row in _rows(board["warnings"]))


def test_runbook_in_process_with_mocked_backends() -> None:
    from retime_plan import retime
    from video_runbook import runbook

    document = _myslef_with_board()
    plan = retime(document, "keyframe", None)
    assert plan["status"] == "PROPOSED"
    clear = runbook(document, plan, "keyframe", None,
                    board_backends={"embedder": HistogramEmbedder(), "judge": FakeJudge()})
    assert clear["status"] == "PROPOSED"
    assert _map(clear["board_image_gate"])["code"] == "BOARD_IMAGES_CLEAR"
    frames = _rows(document["frames"])
    shot_05 = next(frame for frame in frames if frame.get("shot_id") == "05")
    shot_05["board_image"] = str(FIXTURES / "board-mismatch.png")
    blocked = runbook(document, plan, "keyframe", None,
                      board_backends={"embedder": HistogramEmbedder(), "judge": FakeJudge("no")})
    assert blocked["code"] == "BOARD_IDENTITY_MISMATCH"
    assert "ops" not in blocked
    assert "regenerate the board" in str(blocked["message"])


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
