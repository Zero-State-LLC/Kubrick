#!/usr/bin/env python3
"""tools/board_calibration and evals/calibration/board-image-ep01: harness, manifest, wording.

A fake loopback judge answers by question. No network, no model, no EP-01 image.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
EP01 = ROOT / "evals" / "calibration" / "board-image-ep01"
FIXTURES = ROOT / "evals" / "fixtures" / "board_images"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from fake_vision_servers import ollama_judge, serve  # noqa: E402

from kubrick.gates.board_image_plan import lock_questions  # noqa: E402
from tools.board_calibration import gate_metrics, gate_run, judge_eval  # noqa: E402
from tools.board_calibration import manifest as mf  # noqa: E402

GRILLE = "Does the character show any light inside the mouth grille?"
LENS = "Is either of the character's round camera lenses glowing or emitting light?"


def test_ep01_manifest_is_the_labeled_set() -> None:
    man = mf.load(EP01 / "manifest.json")
    items = mf.gate_items(man)
    assert len(items) == 67
    assert sum(mf.defective(i) for i in items) == 7
    assert all(len(i["sha256"]) == 64 for i in man["items"])
    assert len({i["id"] for i in man["items"]}) == len(man["items"])
    assert set(man["roots"]) >= {i["path"].split("/")[0] for i in man["items"]}


def test_thumbnails_are_small_and_listed() -> None:
    thumbs = sorted((EP01 / "thumbnails").glob("*.jpg"))
    assert 1 <= len(thumbs) <= 10
    listed = (EP01 / "thumbnails" / "README.md").read_text(encoding="utf-8")
    for thumb in thumbs:
        assert thumb.stat().st_size < 20_000
        assert thumb.name in listed


def test_roots_resolve_with_overrides(monkeypatch: Any) -> None:
    man = {"roots": {"boards": "/a", "frames": "/b"}, "items": []}
    monkeypatch.setenv("KUBRICK_CALIB_ROOT_FRAMES", "/env")
    roots = mf.roots(man, ["boards=/cli"])
    assert roots == {"boards": "/cli", "frames": "/env"}
    assert mf.resolve("frames/x.png", roots) == "/env/x.png"


def test_v027_locks_ask_the_grille_and_the_long_lens_question() -> None:
    doc = yaml.safe_load((EP01 / "locks-v0.27.yaml").read_text(encoding="utf-8"))
    questions = {q["question"].split("image. ")[-1]: q for q in lock_questions(doc, "myslef", {})}
    assert questions[GRILLE]["lock_id"] == "red-chest-led"
    assert questions[GRILLE]["expect"] == "no"
    assert questions[LENS]["lock_id"] == "lenses" and questions[LENS]["expect"] == "no"
    assert "Do the lenses glow?" not in questions
    old = yaml.safe_load((EP01 / "locks-v0.26.yaml").read_text(encoding="utf-8"))
    assert GRILLE not in {q["question"].split("image. ")[-1]
                          for q in lock_questions(old, "myslef", {})}


def _tiny_manifest(tmp_path: Path) -> Path:
    images = tmp_path / "images"
    images.mkdir()
    shutil.copy(FIXTURES / "board-match.png", images / "grille-led.png")
    shutil.copy(FIXTURES / "board-match.png", images / "clean.png")
    man = {
        "character": "myslef", "roots": {"img": str(images)},
        "questions": {"lens_glow": {"question": "Answer only yes or no. " + LENS,
                                    "expect": "no"}},
        "board_checks": [],
        "items": [
            {"id": "img:grille-led.png", "path": "img/grille-led.png", "kind": "frame",
             "identity": "keep", "sha256": mf.sha256(str(images / "grille-led.png")),
             "truth": {"gate:red-chest-led": "no", "gate:lenses": "yes", "lens_glow": "no"}},
            {"id": "img:clean.png", "path": "img/clean.png", "kind": "board",
             "identity": "keep", "sha256": "0" * 64,
             "truth": {"gate:red-chest-led": "yes", "gate:lenses": "yes", "lens_glow": "no"},
             "pins": {"glow": "no"}},
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(man), encoding="utf-8")
    return path


def test_gate_run_blocks_a_red_light_inside_the_mouth_grille(tmp_path: Path,
                                                             capsys: Any) -> None:
    path = _tiny_manifest(tmp_path)
    out = tmp_path / "run.json"
    seen_grille: list[str] = []

    def answer(prompt: str) -> str:
        if prompt.endswith(GRILLE) and not seen_grille:
            seen_grille.append(prompt)
            return "yes"
        return "no"

    with serve(ollama_judge(answer)) as (url, _seen):
        argv = ["--manifest", str(path), "--locks", str(EP01 / "locks-v0.27.yaml"),
                "--url", url, "--workers", "1", "--out", str(out)]
        assert gate_run.main(argv) == 0
        # resume: a second run asks nothing new
        assert gate_run.main(argv) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    summary = gate_metrics.summarize(data)
    assert (summary["defective_blocked"], summary["defective"]) == (1, 1)
    assert (summary["clean_blocked"], summary["clean"]) == (0, 1)
    assert summary["per_question"][LENS] == {"n": 2, "ok": 2}
    assert "clean blocked: 0 of 1" in capsys.readouterr().out
    assert not (tmp_path / "run.json.tmp").exists()


def test_gate_run_verify_reports_changed_images(tmp_path: Path, capsys: Any) -> None:
    path = _tiny_manifest(tmp_path)
    argv = ["--manifest", str(path), "--locks", str(EP01 / "locks-v0.27.yaml"), "--verify",
            "--url", "http://127.0.0.1:9", "--out", str(tmp_path / "x.json")]
    assert gate_run.main(argv) == 1
    assert "changed img/clean.png" in capsys.readouterr().err


def test_unreachable_judge_blocks_everything(tmp_path: Path) -> None:
    path = _tiny_manifest(tmp_path)
    out = tmp_path / "run.json"
    argv = ["--manifest", str(path), "--locks", str(EP01 / "locks-v0.27.yaml"),
            "--url", "http://127.0.0.1:9", "--timeout", "2", "--out", str(out)]
    assert gate_run.main(argv) == 0
    summary = gate_metrics.summarize(json.loads(out.read_text(encoding="utf-8")))
    assert summary["clean_blocked"] == 1 and summary["unanswered"] == summary["calls"]


def test_judge_eval_scores_questions(tmp_path: Path, capsys: Any) -> None:
    path = _tiny_manifest(tmp_path)
    out = tmp_path / "judge.json"
    with serve(ollama_judge(lambda prompt: "no")) as (url, _seen):
        assert judge_eval.main(["--manifest", str(path), "--url", url, "--out",
                                str(out)]) == 0
    assert judge_eval.main(["--report", str(out)]) == 0
    text = capsys.readouterr().out
    assert "all 2 acc 1.00 unknown 0" in text


def test_metrics_report_on_saved_results() -> None:
    data = {"rows": [
        {"path": "a", "truth": {"gate:x": "no"}, "checks": [
            {"lock_id": "x", "question": "Look. image. Q1?", "expect": "no", "answer": "no",
             "status": "PASS"}], "locks": [{"lock_id": "x", "status": "PASS"}]},
        {"path": "b", "truth": {"gate:x": "yes"}, "checks": [
            {"lock_id": "x", "question": "Look. image. Q1?", "expect": "no", "answer": "yes",
             "status": "FAIL"}], "locks": [{"lock_id": "x", "status": "FAIL"}]},
    ]}
    summary = gate_metrics.summarize(data)
    assert summary["missed"] == ["a"]
    assert summary["clean_blocked_by_question"] == {"Q1?": 1}
    assert summary["per_lock"]["x"]["ok"] == 0
    assert "defective blocked: 0 of 1" in gate_metrics.report(summary)


def test_resume_refuses_a_different_configuration(tmp_path: Path) -> None:
    out = tmp_path / "run.json"
    first = mf.ResultFile(out, {"config": {"questions": ["a"]}})
    first.add({"path": "x", "answer": "yes"})
    assert mf.ResultFile(out, {"config": {"questions": ["a"]}}).done("x")
    try:
        mf.ResultFile(out, {"config": {"questions": ["b"]}})
    except SystemExit as exc:
        assert "different run configuration" in str(exc)
    else:
        raise AssertionError("resumed a run made with other questions")


def test_identity_verify_checks_the_references(tmp_path: Path, capsys: Any) -> None:
    from tools.board_calibration import identity

    path = _tiny_manifest(tmp_path)
    man = json.loads(path.read_text(encoding="utf-8"))
    man["items"] = man["items"][:1]
    man["refs"] = {"head_lock": ["img/ref.png"]}
    man["ref_sha256"] = {"img/ref.png": "0" * 64}
    path.write_text(json.dumps(man), encoding="utf-8")
    assert identity.main(["--manifest", str(path), "--verify", "--out",
                          str(tmp_path / "id.json")]) == 1
    assert "missing img/ref.png" in capsys.readouterr().err
