#!/usr/bin/env python3
"""Write the canonical production artifact tree.

Split from ``production_engine.py`` so that module stays under the 500-line
gate. The engine re-exports ``write_artifact_tree``; call sites do not change.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from production_engine import ProductionResult


def _dump(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def write_artifact_tree(
    result: ProductionResult,
    root: str | Path,
    *,
    write_document: bool = True,
) -> dict[str, str]:
    """Write canonical artifact layout under root (receipts/, artifacts/, qa/, …)."""
    root_path = Path(root)
    paths = {
        "receipts": root_path / "receipts",
        "artifacts": root_path / "artifacts",
        "reports": root_path / "reports",
        "validation": root_path / "validation",
        "qa": root_path / "qa",
        "timeline": root_path / "timeline",
        "references": root_path / "references",
        "metadata": root_path / "metadata",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)

    written: dict[str, str] = {}
    envelope = result.to_dict()
    receipt_id = result.receipt.receipt_id
    artifact_id = result.artifact.artifact_id

    receipt_path = paths["receipts"] / f"{receipt_id}.json"
    receipt_path.write_text(_dump(result.receipt.to_dict()), encoding="utf-8")
    written["receipt"] = str(receipt_path)

    artifact_path = paths["artifacts"] / f"{artifact_id}.json"
    artifact_path.write_text(_dump(envelope), encoding="utf-8")
    written["artifact"] = str(artifact_path)

    validation_path = paths["validation"] / f"{receipt_id}.validation.json"
    validation_path.write_text(_dump(result.receipt.validation), encoding="utf-8")
    written["validation"] = str(validation_path)

    meta_path = paths["metadata"] / f"{receipt_id}.meta.json"
    # Receipts are stamped with the engine schema version when they are built.
    meta_path.write_text(
        _dump(
            {
                "timestamp": result.receipt.timestamp,
                "surface": result.surface,
                "version": result.receipt.schema_version,
                "inputs": result.receipt.inputs,
                "outputs": result.receipt.outputs,
                "warnings": result.receipt.warnings,
                "validation": result.receipt.validation,
                "receipt_hash": result.receipt.receipt_hash,
            }
        ),
        encoding="utf-8",
    )
    written["metadata"] = str(meta_path)

    if result.action == "qa":
        qa_path = paths["qa"] / f"{artifact_id}.qa.json"
        qa_path.write_text(_dump(envelope), encoding="utf-8")
        written["qa"] = str(qa_path)

    timeline_actions = {"shot", "sequence", "timeline"}
    if result.surface == "video" and result.action in timeline_actions:
        timeline_path = paths["timeline"] / f"{artifact_id}.json"
        timeline_path.write_text(_dump(result.artifact.payload), encoding="utf-8")
        written["timeline"] = str(timeline_path)

    if write_document and result.document_markdown:
        doc_path = paths["artifacts"] / f"{artifact_id}.md"
        doc_path.write_text(result.document_markdown, encoding="utf-8")
        written["document"] = str(doc_path)

    return written
