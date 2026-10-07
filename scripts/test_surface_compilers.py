#!/usr/bin/env python3
"""Deterministic tests for v0.15 production-surface domain compilers."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
PY = sys.executable

import surface_compilers as sc  # noqa: E402


def test_design_create_and_improve_preserves_sections() -> None:
    created = sc.design_create(
        "dramatic_problem: authority remains after exit\ndesired_state_change: command becomes institutional\ncharacter_pressure: subordinate receives access\nformat: storyboard",
        None,
        "authority-transfer",
    )
    assert created["status"] == "PROPOSED"
    md = created["result"]["document_markdown"]
    assert "Dramatic engine" in md
    assert "authority remains after exit" in md

    # Inject a custom locked-looking section body and ensure improve keeps it
    sections = sc.parse_design_md(md)
    sections["visual-grammar"] = "- [LOCKED] one-point empty center framing"
    custom = sc.render_design_md(sections, project_id="authority-transfer", revision="r-test")
    improved = sc.design_improve(custom, "extra evidence about doorway access", "authority-transfer")
    assert improved["status"] == "PROPOSED"
    assert "one-point empty center framing" in improved["result"]["document_markdown"]
    assert improved["result"]["preserved_section_count"] >= 1


def test_video_sequence_transition_compatible() -> None:
    seq = sc.video_sequence(
        "dramatic_problem: badge changes hands\ndesired_state_change: access transfers to subordinate",
        None,
        "authority-transfer",
    )
    assert seq["status"] == "PROPOSED"
    assert len(seq["result"]["shots"]) == 2
    assert seq["result"]["transitions"][0]["compatible"] is True


def test_video_shot_fails_without_end_state() -> None:
    shot = sc.video_shot("dramatic_problem: something happens", None, "p")
    assert shot["status"] == "NOT_COMPUTABLE"


def test_cli_design_create_writes_markdown() -> None:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "design.md"
        proc = subprocess.run(
            [
                PY,
                str(ROOT / "scripts/kubrick.py"),
                "do",
                "design",
                "--action",
                "create",
                "--brief",
                "dramatic_problem: empty chair holds power\ndesired_state_change: access moves through a cracked badge\ncharacter_pressure: outsider waits at doorway",
                "--project-id",
                "demo",
                "--output",
                str(out),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        assert proc.returncode == 0, proc.stderr
        assert out.is_file()
        text = out.read_text(encoding="utf-8")
        assert text.startswith("# Design: demo")
        assert "empty chair holds power" in text
        receipt = out.with_name("design.receipt.json")
        assert receipt.is_file()
        data = json.loads(receipt.read_text(encoding="utf-8"))
        assert data["artifact_type"] == "design-document"


def test_cli_image_and_script() -> None:
    with tempfile.TemporaryDirectory() as td:
        img = Path(td) / "image.json"
        script = Path(td) / "script.md"
        proc = subprocess.run(
            [
                PY,
                str(ROOT / "scripts/kubrick.py"),
                "do",
                "image",
                "--action",
                "prompt",
                "--brief",
                "cracked badge in an empty command chair",
                "--output",
                str(img),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        assert proc.returncode == 0, proc.stderr
        packet = json.loads(img.read_text(encoding="utf-8"))
        assert packet["artifact_type"] == "image-prompt-packet"
        assert packet["result"]["packet"]["frames"]

        proc = subprocess.run(
            [
                PY,
                str(ROOT / "scripts/kubrick.py"),
                "do",
                "script",
                "--action",
                "create",
                "--brief",
                "dramatic_problem: authority persists\ndesired_state_change: badge transfer\ncharacter_pressure: fear of the empty chair",
                "--output",
                str(script),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        assert proc.returncode == 0, proc.stderr
        assert "Dramatic intent" in script.read_text(encoding="utf-8")


def _has_yaml() -> bool:
    try:
        import yaml  # noqa: F401
    except ImportError:
        return False
    return True


def test_yaml_brief_enriches_design_and_improve() -> None:
    # List / nested YAML fields need PyYAML; stdlib CI falls back to line parsing only.
    if not _has_yaml():
        print("skip test_yaml_brief_enriches_design_and_improve (PyYAML not installed)")
        return
    brief = (ROOT / "examples/authority-transfer-storyboard/brief.yaml").read_text(encoding="utf-8")
    created = sc.design_create(brief, None, "authority-transfer")
    md = created["result"]["document_markdown"]
    assert "empty command chair" in md or "repeated work cells" in md
    assert "Visual grammar" in md
    # Start from thin design and improve with full YAML evidence
    thin = sc.design_create(
        "dramatic_problem: authority remains\ndesired_state_change: badge transfers\ncharacter_pressure: subordinate waits",
        None,
        "authority-transfer",
    )
    # Clear visual-grammar to force fill from evidence
    sections = sc.parse_design_md(thin["result"]["document_markdown"])
    sections["visual-grammar"] = ""
    sections["material-continuity"] = ""
    thin_md = sc.render_design_md(sections, project_id="authority-transfer", revision="r-thin")
    improved = sc.design_improve(thin_md, brief, "authority-transfer")
    assert improved["artifact_type"] == "design-revision-receipt"
    assert improved["result"].get("parent_revision")
    filled = {
        d["section"]
        for d in improved["result"]["diff"]
        if d["change"] in {"filled_empty", "replaced_placeholder"}
    }
    assert "visual-grammar" in filled or "material-continuity" in filled
    body = improved["result"]["document_markdown"]
    assert "cracked" in body.lower() or "badge" in body.lower()
    # LOCKED visual grammar must survive improve even when YAML evidence exists
    sections = sc.parse_design_md(body)
    sections["visual-grammar"] = "- [LOCKED] one-point empty center framing"
    locked_md = sc.render_design_md(sections, project_id="authority-transfer", revision="r-locked")
    locked_improved = sc.design_improve(locked_md, brief, "authority-transfer")
    assert "one-point empty center framing" in locked_improved["result"]["document_markdown"]


def test_video_shot_embeds_design_revision() -> None:
    design = sc.design_create(
        "dramatic_problem: authority remains\ndesired_state_change: access transfers\ncharacter_pressure: subordinate waits",
        None,
        "p",
    )
    design_md = design["result"]["document_markdown"]
    shot = sc.video_shot(
        "dramatic_problem: authority remains\ndesired_state_change: access transfers",
        None,
        "p",
        design_text=design_md,
    )
    assert shot["status"] == "PROPOSED"
    assert shot["result"]["shot"]["source_design_revision"].startswith("r-")
    assert shot.get("source_design_revision", "").startswith("r-")


def test_resolve_design_auto_discover(monkeypatch=None) -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        design = root / "design.md"
        design.write_text("# Design: demo\n\nRevision: `r-abc123`\n\n## Creative objective\n- hi\n", encoding="utf-8")
        import os

        old = os.environ.get("KUBRICK_PROJECT_DIR")
        os.environ["KUBRICK_PROJECT_DIR"] = str(root)
        try:
            found = sc.resolve_design_text(None, None, None, auto_discover=True)
            assert found is not None
            assert "r-abc123" in found
        finally:
            if old is None:
                os.environ.pop("KUBRICK_PROJECT_DIR", None)
            else:
                os.environ["KUBRICK_PROJECT_DIR"] = old


def test_fountain_script_and_claims() -> None:
    brief = (ROOT / "examples/authority-transfer-storyboard/brief.yaml").read_text(encoding="utf-8")
    packet = sc.script_create(brief, None, "authority-transfer", fmt="fountain")
    assert packet["status"] == "PROPOSED"
    body = packet["result"]["document_markdown"]
    assert "INT." in body
    assert packet["result"]["format"] == "fountain"
    claims = packet["result"]["claims"]
    assert claims["dramatic_problem"]["authority"] == "OBSERVED"
    assert claims["desired_state_change"]["authority"] == "OBSERVED"


def test_design_drift_directory_compatible() -> None:
    brief = (ROOT / "examples/authority-transfer-storyboard/brief.yaml").read_text(encoding="utf-8")
    design = sc.design_create(brief, None, "authority-transfer")
    design_md = design["result"]["document_markdown"]
    script = sc.script_create(brief, None, "authority-transfer", design_text=design_md)
    image = sc.image_prompt(brief, None, design_md, "authority-transfer", "generic")
    against = "\n---KUBRICK_ARTIFACT---\n".join(
        [
            script["result"]["document_markdown"],
            json.dumps(image),
        ]
    )
    drift = sc.design_drift(design_md, against, "authority-transfer")
    assert drift["artifact_type"] == "media-reconciliation-report"
    assert "result" in drift
    assert drift["result"]["finding_count"] >= 0
    assert isinstance(drift["result"]["surfaces_compared"], list)


def test_image_frame_carries_claims() -> None:
    brief = (ROOT / "examples/authority-transfer-storyboard/brief.yaml").read_text(encoding="utf-8")
    image = sc.image_prompt(brief, None, None, "authority-transfer", "generic")
    frame = image["result"]["packet"]["frames"][0]
    assert "claims" in frame
    assert frame["claims"]["dramatic_problem"]["authority"] == "OBSERVED"


def test_video_qa_dimensions() -> None:
    qa = sc.video_qa(
        "shot end_state access transfers identity residue",
        "identity persists; badge transfers; end state shows residue; camera static; motion of hand",
        "p",
    )
    assert qa["result"]["dimensions"]["motion"] is True
    assert qa["result"]["dimensions"]["identity_persistence"] is True
    assert qa["result"]["dimensions"]["end_state"] is True


def test_provider_capability_helpers() -> None:
    from provider_capabilities import check_video_adapt, check_image_adapt, capabilities_for

    assert check_image_adapt("flux") is None
    assert check_video_adapt("flux") is not None
    assert capabilities_for("grok-imagine")["video"] is True
    assert check_video_adapt("grok-imagine", duration=20) is not None


def main() -> None:
    test_design_create_and_improve_preserves_sections()
    test_yaml_brief_enriches_design_and_improve()
    test_fountain_script_and_claims()
    test_design_drift_directory_compatible()
    test_image_frame_carries_claims()
    test_video_shot_embeds_design_revision()
    test_video_qa_dimensions()
    test_provider_capability_helpers()
    test_resolve_design_auto_discover()
    test_video_sequence_transition_compatible()
    test_video_shot_fails_without_end_state()
    test_cli_design_create_writes_markdown()
    test_cli_image_and_script()
    print("surface compiler tests: PASS")


if __name__ == "__main__":
    main()
