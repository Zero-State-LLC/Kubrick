#!/usr/bin/env python3
"""Regression: image/video surface adapt must emit provider preservation reports."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
BRIEF = ROOT / "examples/authority-transfer-storyboard/brief.yaml"
sys.path.insert(0, str(ROOT / "scripts"))

from provider_capabilities import capabilities_for, check_video_adapt  # noqa: E402


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PY, str(ROOT / "scripts/kubrick.py"), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def test_image_adapt_preservation() -> None:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        image = out / "image.json"
        adapted_image = out / "image-adapted.json"

        proc = run(
            [
                "do", "image", "--action", "prompt",
                "--brief", str(BRIEF),
                "--provider", "generic",
                "--output", str(image),
            ]
        )
        assert proc.returncode == 0, (proc.stdout, proc.stderr)

        proc = run(
            [
                "do", "image", "--action", "adapt",
                "--input", str(image),
                "--provider", "flux",
                "--output", str(adapted_image),
            ]
        )
        assert proc.returncode == 0, (proc.stdout, proc.stderr)
        data = json.loads(adapted_image.read_text(encoding="utf-8"))
        assert data["action"] == "adapt"
        report = data["result"]["preservation_report"]
        assert isinstance(report, dict)
        assert report.get("critical_invariants_preserved") is True or report.get("status") == "VALID"
        assert data["result"]["capabilities"]["image"] is True


def test_video_adapt_fail_closed_on_image_only_provider() -> None:
    """Flux is image-only, so video adapt must NOT_COMPUTABLE."""
    assert check_video_adapt("flux") is not None
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        shot = out / "shot.yaml"
        adapted = out / "video-adapted.json"
        proc = run(
            [
                "do", "video", "--action", "shot",
                "--brief", str(BRIEF),
                "--output", str(shot),
            ]
        )
        assert proc.returncode == 0, (proc.stdout, proc.stderr)
        proc = run(
            [
                "do", "video", "--action", "adapt",
                "--input", str(shot),
                "--provider", "flux",
                "--output", str(adapted),
            ]
        )
        assert proc.returncode == 4, (proc.stdout, proc.stderr)
        data = json.loads(adapted.read_text(encoding="utf-8"))
        assert data["status"] == "NOT_COMPUTABLE"
        assert data["diagnostic"]["code"] == "PROVIDER_CAPABILITY"


def test_video_adapt_preservation_on_capable_provider() -> None:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        shot = out / "shot.yaml"
        adapted = out / "video-adapted.json"
        proc = run(
            [
                "do", "video", "--action", "shot",
                "--brief", str(BRIEF),
                "--output", str(shot),
            ]
        )
        assert proc.returncode == 0, (proc.stdout, proc.stderr)
        proc = run(
            [
                "do", "video", "--action", "adapt",
                "--input", str(shot),
                "--provider", "grok-imagine",
                "--output", str(adapted),
            ]
        )
        assert proc.returncode == 0, (proc.stdout, proc.stderr)
        data = json.loads(adapted.read_text(encoding="utf-8"))
        report = data["result"]["preservation_report"]
        assert report.get("critical_invariants_preserved") is True or report.get("status") == "VALID"
        assert data["result"]["capabilities"]["video"] is True


def test_video_prompt_emits_packet() -> None:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "video-prompt.json"
        proc = run(
            [
                "do", "video", "--action", "prompt",
                "--brief", str(BRIEF),
                "--provider", "generic",
                "--output", str(out),
            ]
        )
        assert proc.returncode == 0, (proc.stdout, proc.stderr)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["artifact_type"] == "video-prompt-packet"
        assert data["result"]["packet"]["frames"]
        assert data["result"]["capabilities"] == capabilities_for("generic")


def test_adapt_fail_closed_without_packet() -> None:
    proc = run(["do", "image", "--action", "adapt", "--provider", "flux"])
    assert proc.returncode == 4


def main() -> None:
    test_image_adapt_preservation()
    test_video_adapt_fail_closed_on_image_only_provider()
    test_video_adapt_preservation_on_capable_provider()
    test_video_prompt_emits_packet()
    test_adapt_fail_closed_without_packet()
    print("surface adapt preservation: PASS")


if __name__ == "__main__":
    main()
