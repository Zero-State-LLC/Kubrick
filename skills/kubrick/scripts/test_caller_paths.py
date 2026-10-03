#!/usr/bin/env python3
"""Caller-cwd path flags and ledger --action dispatch (#82)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from caller_paths import rewrite  # noqa: E402

PY = sys.executable
KUBRICK = ROOT / "scripts" / "kubrick.py"


def _run(
    argv: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.pop("KUBRICK_PROJECT_DIR", None)
    merged.pop("KUBRICK_CALLER_CWD", None)
    if env:
        merged.update(env)
    return subprocess.run(
        [PY, str(KUBRICK), *argv],
        cwd=cwd,
        env=merged,
        text=True,
        capture_output=True,
    )


def test_rewrite_relative_path_flags() -> None:
    root = Path("/tmp/caller-example")
    argv = rewrite(
        [
            "--input",
            "myslef-real.yaml",
            "--output=out/clip.json",
            "--provider",
            "generic",
            "--takes",
            "takes.yaml",
            "--answers",
            "-",
            "--out",
            "/tmp/abs-out",
            "--storyboard-plan",
            "plan.yaml",
            "--ledger",
            "ledgers/a.yaml",
            "--brief",
            "examples/brief.yaml",
        ],
        str(root),
    )
    assert argv[1] == str((root / "myslef-real.yaml").resolve())
    assert argv[2] == f"--output={root.resolve() / 'out' / 'clip.json'}"
    assert argv[3:5] == ["--provider", "generic"]
    assert argv[6] == str((root / "takes.yaml").resolve())
    assert argv[7:9] == ["--answers", "-"]
    assert argv[10] == "/tmp/abs-out"
    assert argv[12] == str((root / "plan.yaml").resolve())
    assert argv[14] == str((root / "ledgers" / "a.yaml").resolve())
    assert argv[16] == str((root / "examples" / "brief.yaml").resolve())


def test_rewrite_leaves_prose_and_labels() -> None:
    root = "/tmp/caller-example"
    brief = "cracked badge in an empty command chair"
    prose = "dramatic_problem: fog rolls in"
    argv = rewrite(
        ["--brief", brief, "--brief", prose, "--evidence", "manual_record", "--input", "reel.yaml"],
        root,
    )
    assert argv[1] == brief
    assert argv[3] == prose
    assert argv[5] == "manual_record"
    assert argv[7].endswith("/reel.yaml")


def test_inline_brief_with_slash_or_suffix_stays_prose() -> None:
    root = "/tmp/caller-example"
    briefs = ["day/night transition", "Create README.md", "a ./hidden door at dusk"]
    argv = rewrite([token for brief in briefs for token in ("--brief", brief)], root)
    assert argv[1::2] == briefs


def test_rewrite_stops_at_double_dash() -> None:
    argv = rewrite(["--input", "a.yaml", "--", "--output", "b.yaml"], "/tmp/caller-example")
    assert argv[0:2] == ["--input", str(Path("/tmp/caller-example/a.yaml").resolve())]
    assert argv[2:] == ["--", "--output", "b.yaml"]


def test_relative_input_resolves_against_caller_cwd() -> None:
    with tempfile.TemporaryDirectory() as raw:
        caller = Path(raw)
        proc = _run(
            ["video", "--action", "adapt", "--input", "myslef-real.yaml"],
            caller,
        )
        blob = proc.stdout + proc.stderr
        missing = str((caller / "myslef-real.yaml").resolve())
        repo_copy = str((ROOT / "myslef-real.yaml").resolve())
        assert proc.returncode == 4, blob
        payload = json.loads(proc.stdout)
        assert payload["status"] == "NOT_COMPUTABLE"
        assert payload["diagnostic"]["code"] == "INSUFFICIENT_EVIDENCE"
        assert missing in payload["diagnostic"]["message"]
        assert repo_copy not in blob


def test_caller_cwd_env_wins_over_process_cwd() -> None:
    caller_tmp = tempfile.TemporaryDirectory()
    elsewhere_tmp = tempfile.TemporaryDirectory()
    with caller_tmp, elsewhere_tmp:
        caller = Path(caller_tmp.name)
        elsewhere = Path(elsewhere_tmp.name)
        env = {"KUBRICK_CALLER_CWD": str(caller)}
        proc = _run(
            ["video", "--action", "adapt", "--input=clip.yaml"],
            elsewhere,
            env,
        )
        blob = proc.stdout + proc.stderr
        assert str((caller / "clip.yaml").resolve()) in blob
        assert str((elsewhere / "clip.yaml").resolve()) not in blob
        assert str((ROOT / "clip.yaml").resolve()) not in blob


def test_existing_relative_input_is_opened() -> None:
    with tempfile.TemporaryDirectory() as raw:
        caller = Path(raw)
        (caller / "myslef-real.yaml").write_text("title: reel\n", encoding="utf-8")
        proc = _run(
            ["video", "--action", "adapt", "--input", "myslef-real.yaml"],
            caller,
        )
        blob = proc.stdout + proc.stderr
        assert "input not found" not in blob
        assert str((ROOT / "myslef-real.yaml").resolve()) not in blob


def test_ledger_action_flag_writes_relative_out() -> None:
    stray = ROOT / "ledger.yaml"
    try:
        with tempfile.TemporaryDirectory() as raw:
            caller = Path(raw)
            proc = _run(
                ["do", "ledger", "--action", "init", "--project-id", "p", "--out", "ledger.yaml"],
                caller,
            )
            blob = proc.stdout + proc.stderr
            assert proc.returncode == 0, blob
            assert "missing subcommand" not in blob
            written = (caller / "ledger.yaml").read_text(encoding="utf-8")
            assert "project_id: p" in written
            assert not stray.exists()
    finally:
        if stray.exists():
            stray.unlink()


def test_inline_brief_and_relative_output_stay_with_caller() -> None:
    stray = ROOT / "image.json"
    phrase = "cracked badge in an empty command chair"
    try:
        with tempfile.TemporaryDirectory() as raw:
            caller = Path(raw)
            proc = _run(
                [
                    "do",
                    "image",
                    "--action",
                    "prompt",
                    "--brief",
                    phrase,
                    "--output",
                    "image.json",
                ],
                caller,
            )
            blob = proc.stdout + proc.stderr
            assert proc.returncode == 0, blob
            text = (caller / "image.json").read_text(encoding="utf-8")
            assert phrase in text
            assert not stray.exists()
    finally:
        if stray.exists():
            stray.unlink()


def main() -> None:
    test_rewrite_relative_path_flags()
    test_rewrite_leaves_prose_and_labels()
    test_inline_brief_with_slash_or_suffix_stays_prose()
    test_rewrite_stops_at_double_dash()
    test_relative_input_resolves_against_caller_cwd()
    test_caller_cwd_env_wins_over_process_cwd()
    test_existing_relative_input_is_opened()
    test_ledger_action_flag_writes_relative_out()
    test_inline_brief_and_relative_output_stay_with_caller()
    print("caller paths and ledger --action: PASS")


if __name__ == "__main__":
    main()
