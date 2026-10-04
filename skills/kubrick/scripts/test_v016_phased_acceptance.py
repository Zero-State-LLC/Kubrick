#!/usr/bin/env python3
"""Phased acceptance tests matching the v0.16 implementation order.

1. Shared production engine
2. Design surface first
3. Script as first-class surface
4. Image + video on the same engine
5. Unified QA + receipt system
6. CLI / docs / regression smoke
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
sys.path.insert(0, str(ROOT / "scripts"))

from production_engine import (  # noqa: E402
    ProductionContext,
    ProductionRequest,
    ProductionSurface,
    ProductionValidator,
    build_surface,
    run_production,
    write_artifact_tree,
)

BRIEF = (
    "dramatic_problem: authority remains after exit\n"
    "desired_state_change: personal command becomes institutional pressure\n"
    "character_pressure: subordinate receives access\n"
    "format: storyboard\n"
    "geometry:\n  - empty command chair centered\n"
    "residue:\n  - cracked badge remains visible\n"
)


def run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PY, str(ROOT / "scripts/kubrick.py"), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def phase1_shared_engine() -> None:
    for name in ("ProductionSurface", "ProductionRequest", "ProductionResult",
                 "ProductionArtifact", "ProductionContext", "ProductionValidator",
                 "ProductionReceipt"):
        assert name in dir(__import__("production_engine"))
    req = ProductionRequest(surface="design", action="create", brief=BRIEF, project_id="p1")
    assert ProductionValidator.validate_request(req)["status"] == "VALID"
    result = run_production("design", "create", brief=BRIEF, project_id="p1")
    assert result.receipt.receipt_hash
    assert result.artifact.surface == "design"
    assert result.to_dict()["schema_version"] == "0.16.0"


def phase2_design_surface_first() -> None:
    design = build_surface("design")
    created = design.execute(
        ProductionRequest(surface="design", action="create", brief=BRIEF, project_id="p2")
    )
    assert created.status == "PROPOSED"
    assert created.document_markdown and "Dramatic engine" in created.document_markdown
    md = created.document_markdown
    ctx = ProductionContext(project_id="p2", design_revision=created.artifact.payload.get("revision"))

    improved = design.execute(
        ProductionRequest(
            surface="design",
            action="improve",
            input_text=md,
            evidence=BRIEF,
            project_id="p2",
            context=ctx,
        )
    )
    assert improved.status == "PROPOSED"
    assert improved.artifact.artifact_type == "design-revision-receipt"
    assert isinstance(improved.artifact.payload.get("diff"), list)

    for action in ("audit", "validate", "summarize", "expand", "reconcile"):
        kwargs = {"input_text": improved.document_markdown or md, "project_id": "p2"}
        if action in {"expand", "reconcile"}:
            kwargs["evidence"] = BRIEF if action == "expand" else (improved.document_markdown or md)
        out = design.execute(ProductionRequest(surface="design", action=action, **kwargs))
        assert out.receipt.receipt_id.startswith("receipt-"), action
        assert out.status in {"PROPOSED", "PASS", "NOT_COMPUTABLE"} or out.authority in {
            "PROPOSED",
            "OBSERVATION",
            "NOT_COMPUTABLE",
        }, (action, out.status, out.authority)


def phase3_script_first_class() -> None:
    design = run_production("design", "create", brief=BRIEF, project_id="p3")
    script = run_production(
        "script",
        "create",
        brief=BRIEF,
        design_text=design.document_markdown,
        format="fountain",
        project_id="p3",
    )
    assert script.status == "PROPOSED"
    assert "INT." in (script.document_markdown or "")
    assert script.to_dict().get("source_design_revision", "").startswith("r-") or (
        script.artifact.payload.get("source_design_revision", "").startswith("r-")
        or script.artifact.payload.get("source_design_revision") == "pending"
    )
    body = script.document_markdown or ""
    for action in ("diagnose", "continuity", "handoff", "rewrite", "compress", "scene-extract"):
        out = run_production("script", action, input_text=body, project_id="p3")
        assert out.receipt.receipt_hash, action
        assert out.artifact.surface == "script"


def phase4_image_and_video_same_engine() -> None:
    design = run_production("design", "create", brief=BRIEF, project_id="p4")
    image = run_production(
        "image",
        "prompt",
        brief=BRIEF,
        design_text=design.document_markdown,
        project_id="p4",
        provider="generic",
    )
    assert image.status == "PROPOSED"
    assert image.artifact.payload.get("packet", {}).get("frames")
    assert image.receipt.surface == "image"

    video = run_production(
        "video",
        "shot",
        brief=BRIEF,
        design_text=design.document_markdown,
        project_id="p4",
        duration=6.0,
    )
    assert video.status == "PROPOSED"
    shot = video.artifact.payload.get("shot") or {}
    for key in ("start_state", "action", "camera", "end_state", "continuity_invariants"):
        assert key in shot, key

    # Same engine class for both
    assert isinstance(build_surface("image"), ProductionSurface)
    assert isinstance(build_surface("video"), ProductionSurface)
    adapted = run_production(
        "image",
        "adapt",
        input_text=json.dumps(image.to_dict()),
        provider="flux",
        project_id="p4",
    )
    assert adapted.artifact.payload.get("preservation_report") or adapted.status == "NOT_COMPUTABLE"


def phase5_unified_qa_and_receipts() -> None:
    design = run_production("design", "create", brief=BRIEF, project_id="p5")
    script = run_production(
        "script",
        "create",
        brief=BRIEF,
        design_text=design.document_markdown,
        project_id="p5",
    )
    image = run_production("image", "prompt", brief=BRIEF, project_id="p5")
    video = run_production("video", "shot", brief=BRIEF, project_id="p5")

    for surface, payload in (
        ("design", {"input_text": design.document_markdown}),
        ("script", {"input_text": script.document_markdown}),
        ("image", {"input_text": json.dumps(image.to_dict()), "evidence": "authority chair badge doorway"}),
        ("video", {"input_text": json.dumps(video.to_dict()), "evidence": "identity persists end state residue motion"}),
    ):
        qa = run_production(surface, "qa", project_id="p5", **payload)
        assert qa.action == "qa"
        assert qa.receipt.receipt_hash
        assert "receipt" in qa.to_dict()

    with tempfile.TemporaryDirectory() as td:
        written = write_artifact_tree(design, td)
        assert Path(written["receipt"]).is_file()
        assert Path(written["artifact"]).is_file()
        assert Path(written["metadata"]).is_file()
        assert (Path(td) / "receipts").is_dir()
        meta = json.loads(Path(written["metadata"]).read_text(encoding="utf-8"))
        for key in ("timestamp", "surface", "version", "inputs", "outputs", "validation", "receipt_hash"):
            assert key in meta, key


def phase6_cli_docs_regression() -> None:
    assert (ROOT / "docs/ARCHITECTURE-v0.16.md").is_file()
    assert (ROOT / "docs/DELIVERABLES-v0.16.md").is_file()
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        design = out / "design.md"
        proc = run_cli(
            [
                "design",
                "create",
                "--brief",
                BRIEF,
                "--project-id",
                "p6",
                "--artifact-root",
                str(out),
                "--output",
                str(design),
            ]
        )
        assert proc.returncode == 0, (proc.stdout, proc.stderr)
        assert design.is_file()
        assert (out / "receipts").is_dir()
        proc = run_cli(["qa", "design", "--input", str(design), "--output", str(out / "qa.json")])
        assert proc.returncode in {0, 4}, (proc.stdout, proc.stderr)
        proc = run_cli(["receipts", "--root", str(out)])
        assert proc.returncode == 0, (proc.stdout, proc.stderr)
        data = json.loads(proc.stdout)
        assert data["status"] == "PASS"
        assert data["count"] >= 1


def main() -> None:
    phase1_shared_engine()
    print("phase1 shared engine: PASS")
    phase2_design_surface_first()
    print("phase2 design surface: PASS")
    phase3_script_first_class()
    print("phase3 script surface: PASS")
    phase4_image_and_video_same_engine()
    print("phase4 image+video: PASS")
    phase5_unified_qa_and_receipts()
    print("phase5 qa+receipts: PASS")
    phase6_cli_docs_regression()
    print("phase6 cli/docs/regression: PASS")
    print("v0.16 phased acceptance: PASS")


def test_v016_phased_acceptance() -> None:
    main()


if __name__ == "__main__":
    main()
