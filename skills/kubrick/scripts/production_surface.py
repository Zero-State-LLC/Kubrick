#!/usr/bin/env python3
"""Shared deterministic runtime for Kubrick first-class production surfaces.

v0.16 routes every design/script/image/video action through the canonical
ProductionEngine lifecycle while preserving the public CLI contract.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from continuity_locks import bind_strict, unbind_strict  # noqa: E402
from io_safety import PathSafetyError, resolve_bounded_path, write_text_bounded  # noqa: E402
from production_engine import (  # noqa: E402
    ProductionRequest,
    build_surface,
    write_artifact_tree,
)

VALID_SURFACES = {"design", "script", "image", "video"}


def _is_directory_output(out: Path, output: str) -> bool:
    return (out.exists() and out.is_dir()) or output.endswith("/")


def _load_optional(path: str | None) -> str | None:
    if not path:
        return None
    resolved = resolve_bounded_path(path, for_write=False)
    if resolved.is_dir():
        chunks: list[str] = []
        for child in sorted(resolved.iterdir()):
            if not child.is_file():
                continue
            allowed = {".md", ".markdown", ".fountain", ".json", ".yaml", ".yml", ".txt"}
            if child.suffix.lower() not in allowed:
                continue
            chunks.append(child.read_text(encoding="utf-8"))
        if not chunks:
            raise FileNotFoundError(f"evidence directory has no readable artifacts: {resolved}")
        return "\n---KUBRICK_ARTIFACT---\n".join(chunks)
    if not resolved.is_file():
        raise FileNotFoundError(f"input not found: {resolved}")
    return resolved.read_text(encoding="utf-8")


def _write_artifact(artifact: dict[str, Any], output: str | None) -> None:
    """Write markdown document when present; always emit JSON receipt/packet."""
    markdown = None
    result = artifact.get("result") or {}
    if isinstance(result, dict):
        markdown = result.get("document_markdown")

    if output:
        out = resolve_bounded_path(output, for_write=True)
        # Directory output → canonical artifact tree
        if _is_directory_output(out, output):
            out.mkdir(parents=True, exist_ok=True)
            # Rebuild result object for tree writer via engine envelope already present
            payload = json.dumps(artifact, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
            write_text_bounded(out / "latest.json", payload)
            if markdown:
                write_text_bounded(out / "document.md", markdown)
            if artifact.get("receipt"):
                receipt_json = (
                    json.dumps(artifact["receipt"], indent=2, sort_keys=True, ensure_ascii=False)
                    + "\n"
                )
                write_text_bounded(out / "receipt.json", receipt_json)
            return
        if markdown and out.suffix.lower() in {".md", ".markdown", ".fountain"}:
            write_text_bounded(out, markdown)
            side = out.with_name(out.stem + ".receipt.json")
            receipt = dict(artifact)
            if isinstance(receipt.get("result"), dict):
                receipt["result"] = {
                    k: v for k, v in receipt["result"].items() if k != "document_markdown"
                }
                receipt["result"]["document_path"] = str(out)
            write_text_bounded(
                side,
                json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            )
            return
        if out.suffix.lower() in {".yaml", ".yml"}:
            from runtime_deps import yaml_dump

            document = (
                result.get("shot")
                or result.get("packet")
                or result.get("motion_contract")
                or artifact
            )
            write_text_bounded(out, yaml_dump(document, sort_keys=False))
            return
        write_text_bounded(
            out,
            json.dumps(artifact, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )
        return

    if markdown and not sys.stdout.isatty():
        if artifact.get("surface") in {"design", "script"} and artifact.get("action") in {
            "create",
            "build",
            "improve",
            "update",
            "adapt",
            "expand",
            "summarize",
            "rewrite",
            "compress",
        }:
            sys.stdout.write(markdown)
            return
    sys.stdout.write(json.dumps(artifact, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def _surface_registry(surface: str):
    return build_surface(surface)


def run(surface: str, actions: set[str]) -> int:
    if surface not in VALID_SURFACES:
        raise ValueError(f"unknown surface: {surface}")

    parser = argparse.ArgumentParser(prog=f"kubrick do {surface}")
    parser.add_argument("--surface-action", choices=sorted(actions), required=True)
    parser.add_argument("--brief")
    parser.add_argument("--input")
    parser.add_argument("--evidence")
    parser.add_argument("--design", help="Optional design.md path for revision linkage")
    parser.add_argument("--provider", default="generic")
    parser.add_argument("--project-id", default="local-project")
    parser.add_argument("--output")
    parser.add_argument("--format", default="markdown")
    parser.add_argument("--duration", type=float, default=8.0)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument(
        "--artifact-root",
        help="Optional directory for receipts/artifacts/qa/metadata tree",
    )
    args = parser.parse_args()
    strict_token = bind_strict(bool(args.strict))
    try:
        loaded_input = _load_optional(args.input)
        loaded_evidence = _load_optional(args.evidence)
        loaded_design = _load_optional(getattr(args, "design", None))
        if args.brief:
            # Never treat multiline / long inline briefs as filesystem paths.
            looks_inline = (
                "\n" in args.brief
                or args.brief.strip().startswith("dramatic_problem")
                or len(args.brief) > 512
            )
            if not looks_inline:
                try:
                    if Path(args.brief).expanduser().exists():
                        loaded = _load_optional(args.brief)
                        if loaded is not None:
                            args.brief = loaded
                except OSError:
                    pass
                except (FileNotFoundError, PathSafetyError):
                    pass
        if surface == "design" and args.surface_action in {"create", "build"}:
            if not args.brief and not loaded_evidence and loaded_input:
                loaded_evidence = loaded_input

        request = ProductionRequest(
            surface=surface,
            action=args.surface_action,
            brief=args.brief,
            input_text=loaded_input,
            evidence=loaded_evidence,
            design_text=loaded_design,
            provider=args.provider,
            project_id=args.project_id,
            format=args.format,
            duration=args.duration,
            output=args.output,
        )
        registry = _surface_registry(surface)
        # Restrict to the entrypoint's declared actions for fail-closed routing.
        if args.surface_action not in actions:
            artifact = {
                "status": "NOT_COMPUTABLE",
                "authority": "NOT_COMPUTABLE",
                "surface": surface,
                "action": args.surface_action,
                "diagnostic": {
                    "code": "UNKNOWN_ACTION",
                    "message": f"Action not enabled on {surface}",
                },
            }
            _write_artifact(artifact, args.output)
            return 4

        result = registry.execute(request)
        artifact = result.to_dict()
        # Preserve legacy compile_surface parity fields used by older tests.
        if "shared_invariants" not in artifact:
            artifact["shared_invariants"] = result.to_dict().get("shared_invariants")

        if args.artifact_root:
            root = resolve_bounded_path(args.artifact_root, for_write=True)
            root.mkdir(parents=True, exist_ok=True)
            write_artifact_tree(result, root)

        _write_artifact(artifact, args.output)
    except PathSafetyError as exc:
        fail = {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": surface,
            "action": args.surface_action,
            "diagnostic": {"code": "PATH_POLICY", "message": str(exc)},
        }
        print(json.dumps(fail, indent=2, sort_keys=True), flush=True)
        return 2
    except FileNotFoundError as exc:
        fail = {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": surface,
            "action": args.surface_action,
            "diagnostic": {"code": "INSUFFICIENT_EVIDENCE", "message": str(exc)},
        }
        print(json.dumps(fail, indent=2, sort_keys=True), flush=True)
        return 4
    except OSError as exc:
        fail = {
            "status": "NOT_COMPUTABLE",
            "authority": "NOT_COMPUTABLE",
            "surface": surface,
            "action": args.surface_action,
            "diagnostic": {"code": "IO_ERROR", "message": str(exc)},
        }
        print(json.dumps(fail, indent=2, sort_keys=True), flush=True)
        return 1
    finally:
        unbind_strict(strict_token)

    if artifact.get("status") == "NOT_COMPUTABLE":
        return 4
    return 0
