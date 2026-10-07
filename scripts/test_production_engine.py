#!/usr/bin/env python3
"""Unit tests for the v0.16 canonical production engine."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from production_engine import (  # noqa: E402
    ProductionEngine,
    ProductionRequest,
    ProductionSurface,
    ProductionValidator,
    write_artifact_tree,
)
from surface_compilers import COMPILERS  # noqa: E402


def test_engine_design_create_receipt() -> None:
    surface = ProductionSurface(
        "design",
        {a: fn for (s, a), fn in COMPILERS.items() if s == "design"},
    )
    req = ProductionRequest(
        surface="design",
        action="create",
        brief="dramatic_problem: authority remains\ndesired_state_change: badge transfers\ncharacter_pressure: subordinate waits",
        project_id="engine-demo",
    )
    result = surface.execute(req)
    assert result.status == "PROPOSED"
    assert result.receipt.receipt_hash
    assert result.document_markdown and "Design: engine-demo" in result.document_markdown
    envelope = result.to_dict()
    assert envelope["schema_version"] == "0.16.0"
    assert envelope["receipt"]["receipt_id"].startswith("receipt-")


def test_validator_rejects_bad_request() -> None:
    bad = ProductionValidator.validate_request
    # Construct via engine unknown action path
    surface = ProductionSurface("image", {})
    req = ProductionRequest(surface="image", action="nope")
    result = surface.execute(req)
    assert result.status == "NOT_COMPUTABLE"
    assert result.diagnostic and result.diagnostic["code"] == "UNKNOWN_ACTION"


def test_artifact_tree_layout() -> None:
    surface = ProductionSurface(
        "design",
        {a: fn for (s, a), fn in COMPILERS.items() if s == "design"},
    )
    req = ProductionRequest(
        surface="design",
        action="summarize",
        input_text="# Design: x\n\nRevision: `r-test`\n\n## Creative objective\n- [OBSERVED] hi\n",
        project_id="x",
    )
    result = surface.execute(req)
    with tempfile.TemporaryDirectory() as td:
        written = write_artifact_tree(result, td)
        assert Path(written["receipt"]).is_file()
        assert Path(written["artifact"]).is_file()
        assert Path(written["metadata"]).is_file()
        assert (Path(td) / "receipts").is_dir()
        assert (Path(td) / "artifacts").is_dir()


def test_shared_qa_actions_registered() -> None:
    for surface in ("design", "script", "image", "video"):
        assert (surface, "qa") in COMPILERS


def main() -> None:
    test_engine_design_create_receipt()
    test_validator_rejects_bad_request()
    test_artifact_tree_layout()
    test_shared_qa_actions_registered()
    print("production engine tests: PASS")


if __name__ == "__main__":
    main()
