#!/usr/bin/env python3
"""Acceptance tests for cross-surface design↔script↔image↔video flow."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
BRIEF = ROOT / "examples/authority-transfer-storyboard/brief.yaml"


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PY, str(ROOT / "scripts/kubrick.py"), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def test_end_to_end_surfaces() -> None:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        design = out / "design.md"
        improved = out / "design-improved.md"
        script = out / "script.md"
        image = out / "image.json"
        shot = out / "shot.json"
        reconcile = out / "reconcile.json"

        steps = [
            (
                [
                    "do", "design", "--action", "create",
                    "--brief", str(BRIEF),
                    "--project-id", "authority-transfer",
                    "--output", str(design),
                ],
                0,
            ),
            (
                [
                    "do", "design", "--action", "improve",
                    "--input", str(design),
                    "--evidence", str(BRIEF),
                    "--output", str(improved),
                ],
                0,
            ),
            (
                [
                    "do", "script", "--action", "create",
                    "--brief", str(BRIEF),
                    "--input", str(improved),
                    "--output", str(script),
                ],
                0,
            ),
            (
                [
                    "do", "image", "--action", "prompt",
                    "--brief", str(BRIEF),
                    "--input", str(improved),
                    "--provider", "generic",
                    "--output", str(image),
                ],
                0,
            ),
            (
                [
                    "do", "video", "--action", "shot",
                    "--brief", str(BRIEF),
                    "--input", str(improved),
                    "--output", str(shot),
                ],
                0,
            ),
            (
                [
                    "do", "design", "--action", "reconcile",
                    "--input", str(improved),
                    "--evidence", str(script),
                    "--output", str(reconcile),
                ],
                0,
            ),
        ]
        for argv, code in steps:
            proc = run(argv)
            assert proc.returncode == code, (argv, proc.returncode, proc.stdout, proc.stderr)

        text = improved.read_text(encoding="utf-8")
        assert "Dramatic engine" in text
        assert "authority remains active" in text
        # improve preserved/created content rather than wiping
        assert "Revision history" in text or "revision" in text.lower()

        script_text = script.read_text(encoding="utf-8")
        assert "Dramatic intent" in script_text
        assert "Script revision:" in script_text
        assert "Design revision link: r-" in script_text

        image_data = json.loads(image.read_text(encoding="utf-8"))
        assert image_data["artifact_type"] == "image-prompt-packet"
        assert image_data["result"]["packet"]["frames"]
        assert image_data["shared_invariants"]["preserve_identity"] is True
        assert image_data.get("source_design_revision", "").startswith("r-")

        # JSON output is the full artifact envelope; schema expects the inner shot.
        shot_envelope = json.loads(shot.read_text(encoding="utf-8"))
        shot_obj = shot_envelope.get("result", {}).get("shot") or shot_envelope
        for key in (
            "shot_id",
            "start_state",
            "end_state",
            "camera",
            "continuity_invariants",
            "source_design_revision",
        ):
            assert key in shot_obj, key
        shot_contract = out / "shot-contract.json"
        shot_contract.write_text(
            json.dumps(shot_obj, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        recon = json.loads(reconcile.read_text(encoding="utf-8"))
        assert recon["artifact_type"] == "media-reconciliation-report"
        assert "result" in recon

        design_receipt = improved.with_name(improved.stem + ".receipt.json")
        assert design_receipt.is_file()
        receipt_data = json.loads(design_receipt.read_text(encoding="utf-8"))
        assert receipt_data["artifact_type"] == "design-revision-receipt"
        assert isinstance(receipt_data["result"].get("diff"), list)

        # Provider adapt + artifact schema validation need the validation profile.
        try:
            import jsonschema  # noqa: F401
            import yaml  # noqa: F401
        except ImportError:
            print("skip adapt/schema checks (validation profile not installed)")
            return

        adapted = out / "image-adapted.json"
        proc = run(
            [
                "do", "image", "--action", "adapt",
                "--input", str(image),
                "--provider", "flux",
                "--output", str(adapted),
            ]
        )
        assert proc.returncode == 0, (proc.stdout, proc.stderr)
        adapted_data = json.loads(adapted.read_text(encoding="utf-8"))
        report = adapted_data["result"]["preservation_report"]
        assert (
            report.get("critical_invariants_preserved") is True
            or report.get("status") == "VALID"
        )

        for artifact, schema in (
            (design_receipt, "schemas/design-revision-receipt.schema.json"),
            (image, "schemas/image-prompt-packet.schema.json"),
            (shot_contract, "schemas/shot-contract.schema.json"),
        ):
            v = subprocess.run(
                [
                    PY,
                    str(ROOT / "scripts/validate_artifact.py"),
                    "--artifact",
                    str(artifact),
                    "--schema",
                    str(ROOT / schema),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            assert v.returncode == 0, (schema, v.stdout, v.stderr)


def test_video_sequence_fail_closed_without_end_state() -> None:
    proc = run(
        [
            "do", "video", "--action", "shot",
            "--brief", "dramatic_problem: fog rolls in",
            "--output", "/tmp/should-not-matter.json",
        ]
    )
    # May write NOT_COMPUTABLE JSON and exit 4
    assert proc.returncode == 4


def test_help_lists_four_surfaces() -> None:
    proc = run(["--help"])
    assert proc.returncode == 0
    for intent in ("design", "script", "image", "video"):
        assert intent in proc.stdout


def main() -> None:
    test_help_lists_four_surfaces()
    test_end_to_end_surfaces()
    test_video_sequence_fail_closed_without_end_state()
    print("cross-surface acceptance: PASS")


if __name__ == "__main__":
    main()
