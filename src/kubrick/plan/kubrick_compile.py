#!/usr/bin/env python3
"""Compile a Kubrick brief into validated private, storyboard, and provider artifacts."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn

from kubrick.paths import SKILL_ROOT
from kubrick.runtime.diagnostics import abort, diagnostic
from kubrick.runtime.runtime_identity import compile_identity

try:
    import yaml
except ImportError:
    abort(diagnostic(
        status="DEPENDENCY_UNAVAILABLE",
        code="PY_YAML_REQUIRED",
        exit_code=3,
        message="PyYAML is required for compile; install the validation runtime profile",
        context={"package": "PyYAML", "profile": "validation"},
    ))
try:
    import jsonschema  # noqa: F401
except ImportError:
    abort(diagnostic(
        status="DEPENDENCY_UNAVAILABLE",
        code="JSONSCHEMA_REQUIRED",
        exit_code=3,
        message=(
            "jsonschema is required for compile; install it with: "
            "python3 -m pip install -r requirements.txt"
        ),
        context={
            "package": "jsonschema",
            "profile": "validation",
            "install": "python3 -m pip install -r requirements.txt",
        },
    ))

ROOT = SKILL_ROOT
from kubrick.plan.compile_brief import (  # noqa: E402
    build_structured_packet,
    default_relations,
    fallback_forms,
    graph_spec,
)
from kubrick.plan.shot_plan import dedupe_warnings, warnings_in  # noqa: E402
from kubrick.runtime.io_safety import (  # noqa: E402
    PathSafetyError,
    load_structured,
    resolve_bounded_path,
    write_structured,
    write_text_bounded,
)

_BLOCKING = (
    "REFERENCE_LOCK_CONTRADICTION",
    "LOCATION_REFERENCE_CONTRADICTION",
    "START_FRAME_MISSING",
)
PY = sys.executable
RUN_IDENTITY: dict = {}
_PROVIDERS = {"generic", "grok-imagine", "flux", "sd3", "midjourney", "keyframe"}


def read(path: str | Path) -> dict:
    return load_structured(path)


def write(path: str | Path, data: dict) -> None:
    write_structured(path, data)


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)


def fail(out, stage, reasons, diagnostic_output=None, extras=None) -> NoReturn:
    clipped = diagnostic_output[-2000:] if diagnostic_output else ""
    payload = diagnostic(
        status="NOT_COMPUTABLE",
        code="COMPILE_NOT_COMPUTABLE",
        exit_code=4,
        message=f"compile stopped at {stage}",
        reason_vector=reasons,
        context={"stage": stage, "implementation_output": clipped},
    )
    final = {
        "status": "NOT_COMPUTABLE",
        "compiler_version": "0.3.0",
        **RUN_IDENTITY,
        "stage": stage,
        "reason_vector": reasons,
        "diagnostic": payload,
    }
    if isinstance(extras, dict):
        for key, value in extras.items():
            if value not in (None, [], {}):
                final[key] = value
    receipt = json.dumps(final, indent=2) + "\n"
    write_text_bounded(out / "compile-receipt.json", receipt)
    print(json.dumps(final, indent=2))
    raise SystemExit(4)


def prep_extras(*paths):
    warnings: list = []
    techniques: list = []
    for path in paths:
        if not path or not Path(path).is_file():
            continue
        try:
            data = read(path)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        warnings.extend(warnings_in(data))
        raw = data.get("technique_suggestions")
        if isinstance(raw, list) and raw:
            techniques = raw
    extras: dict = {}
    deduped = dedupe_warnings(warnings)
    if deduped:
        extras["prep_warnings"] = deduped
    if techniques:
        extras["technique_suggestions"] = techniques
    return extras


def blocking_codes(extras: dict) -> list[str]:
    warnings = extras.get("prep_warnings") or []
    found: list[str] = []
    for item in warnings:
        code = item.get("code") if isinstance(item, dict) else None
        if code in _BLOCKING and code not in found:
            found.append(code)
    return found


def validate(out, artifact, schema, label):
    report = out / f"schema-{label}.json"
    result = run([
        PY, str(ROOT / "scripts/validate_artifact.py"),
        "--artifact", str(artifact),
        "--schema", str(ROOT / schema),
        "--output", str(report),
    ])
    if result.returncode != 0:
        fail(
            out, "schema-validation", [f"{label.upper()}_SCHEMA_INVALID"],
            result.stdout or result.stderr,
        )
    return report.name


def _compile_storyboard(out, graph_path, plan_path, artifacts, schema_reports):
    if not plan_path:
        fail(out, "storyboard", ["STORYBOARD_PLAN_REQUIRED"])
    storyboard_path = out / "storyboard-symbolic-state.yaml"
    prop = run([
        PY, str(ROOT / "scripts/propagate_graph_state.py"),
        "--graph", str(graph_path),
        "--plan", plan_path,
        "--output", str(storyboard_path),
    ])
    if prop.returncode != 0:
        fail(out, "storyboard", ["STORYBOARD_PROPAGATION_FAILED"], prop.stdout or prop.stderr)
    transition_path = out / "storyboard-transition-report.json"
    compared = run([
        PY, str(ROOT / "scripts/compare_frame_state.py"),
        "--storyboard", str(storyboard_path),
        "--output", str(transition_path),
    ])
    if compared.returncode != 0:
        fail(
            out, "storyboard", ["STORYBOARD_CONTINUITY_FAILED"],
            compared.stdout or compared.stderr,
        )
    schema_reports["storyboard"] = validate(
        out, storyboard_path, "schemas/storyboard-symbolic-state.schema.yaml", "storyboard",
    )
    artifacts.update({
        "storyboard_state": storyboard_path.name,
        "storyboard_transitions": transition_path.name,
    })
    return storyboard_path


def _provider_packet(out, adapter_path, provider: str):
    provider_path = out / f"{provider}-prompt-packet.yaml"
    if provider == "grok-imagine":
        command = [
            PY, str(ROOT / "scripts/adapt_grok_imagine.py"),
            "--packet", str(adapter_path), "--output", str(provider_path),
        ]
    else:
        command = [
            PY, str(ROOT / "scripts/adapt_provider.py"),
            "--packet", str(adapter_path),
            "--provider", provider,
            "--output", str(provider_path),
        ]
    return provider_path, run(command)


def _finish_adapter(out, *, strict: bool, provider: str, adapter_path, artifacts):
    if provider not in _PROVIDERS:
        extras = prep_extras(adapter_path)
        hits = blocking_codes(extras) if strict else []
        if hits:
            fail(out, "adapter", hits, None, extras)
        return extras
    provider_path, provider_run = _provider_packet(out, adapter_path, provider)
    extras = prep_extras(adapter_path, provider_path)
    hits = blocking_codes(extras) if strict else []
    if provider_run.returncode != 0:
        reasons = [f"{provider.upper().replace('-', '_')}_ADAPTER_FAILED", *hits]
        fail(out, "adapter", reasons, provider_run.stdout or provider_run.stderr, extras)
    if hits:
        fail(out, "adapter", hits, None, extras)
    artifacts["provider_packet"] = provider_path.name
    return extras


def _compile_adapter(out, graph_path, provider, storyboard_path, artifacts, schema_reports, strict):
    adapter_path = out / "model-adapter-packet.yaml"
    command = [
        PY, str(ROOT / "scripts/build_model_adapter_packet.py"),
        "--graph", str(graph_path),
        "--provider", provider,
        "--output", str(adapter_path),
    ]
    if storyboard_path:
        command.extend(["--storyboard", str(storyboard_path)])
    adapter = run(command)
    if adapter.returncode != 0:
        extras = prep_extras(adapter_path)
        reasons = ["MODEL_ADAPTER_BUILD_FAILED", *(blocking_codes(extras) if strict else [])]
        fail(out, "adapter", reasons, adapter.stdout or adapter.stderr, extras)
    schema_reports["adapter"] = validate(
        out, adapter_path, "schemas/model-adapter-packet.schema.yaml", "adapter",
    )
    artifacts["model_adapter"] = adapter_path.name
    return _finish_adapter(
        out, strict=strict, provider=provider, adapter_path=adapter_path, artifacts=artifacts,
    )


def _load_request(args):
    try:
        out = resolve_bounded_path(args.out, for_write=True)
        out.mkdir(parents=True, exist_ok=True)
        brief = read(args.brief)
        if args.ledger:
            brief["symbolic_ledger"] = read(args.ledger)
    except (PathSafetyError, OSError, ValueError) as exc:
        abort(diagnostic(
            status="INVALID_COMMAND",
            code="PATH_POLICY",
            exit_code=2,
            message=str(exc),
            context={"surface": "compile"},
        ))
    plan = read(args.storyboard_plan) if args.storyboard_plan else None
    return out, brief, plan


def _selected_grammar(out: Path, normalized: Path) -> str:
    retrieval = run([
        PY, str(ROOT / "scripts/retrieve_symbolic_patterns_registry.py"),
        "--brief", str(normalized), "--no-cache",
    ])
    try:
        receipt = yaml.safe_load(retrieval.stdout) or {}
    except Exception:
        receipt = {}
    write(out / "retrieval-receipt.yaml", receipt)
    nested = receipt.get("retrieval_receipt") or {}
    selected = nested.get("selected_primary_grammar")
    if retrieval.returncode != 0 or not isinstance(selected, str) or not selected:
        fail(out, "retrieval", nested.get("reason_vector", ["RETRIEVAL_FAILED"]))
    return selected


def _observed(brief: dict, selected: str) -> tuple[list, list]:
    forms = brief.get("observed_forms") or []
    if len(forms) < 2:
        forms = fallback_forms(brief, selected)
    if len(forms) < 2:
        return forms, []
    relations = brief.get("relations") or default_relations(brief, forms)
    return forms, relations


def _private_graph(out: Path, brief: dict, selected: str):
    forms, relations = _observed(brief, selected)
    if len(forms) < 2:
        fail(out, "graph", ["INSUFFICIENT_OBSERVED_FORMS"])
    graph_input = out / "graph-input.yaml"
    write(graph_input, graph_spec(brief, forms, relations))
    graph_path = out / "motif-graph.private.yaml"
    graph_run = run([
        PY, str(ROOT / "scripts/build_motif_graph.py"),
        "--input", str(graph_input), "--output", str(graph_path),
    ])
    if graph_run.returncode != 0:
        fail(out, "graph", ["GRAPH_INVALID"], graph_run.stderr or graph_run.stdout)
    schema_reports = {
        "graph": validate(
            out, graph_path, "schemas/motif-structure-graph.schema.yaml", "graph",
        ),
    }
    return graph_path, schema_reports, read(graph_path)


def _audience(out: Path, graph_path: Path, mode: str) -> None:
    translate = run([
        PY, str(ROOT / "scripts/translate_motif_graph.py"),
        "--graph", str(graph_path), "--mode", mode,
    ])
    try:
        audience = yaml.safe_load(translate.stdout) or {}
    except Exception:
        audience = {}
    write(out / "audience-constraints.yaml", audience)
    text_audit = run([
        PY, str(ROOT / "scripts/audit_anti_slop.py"),
        "--text", yaml.safe_dump(audience), "--json",
    ])
    try:
        text_data = json.loads(text_audit.stdout)
    except Exception:
        text_data = {
            "status": "FAIL",
            "violations": [{"gate": "UNKNOWN", "repair": "inspect audit output"}],
        }
    write_text_bounded(out / "text-anti-slop-report.json", json.dumps(text_data, indent=2) + "\n")
    if translate.returncode != 0 or text_audit.returncode != 0:
        fail(
            out, "translation", ["TRANSLATION_OR_TEXT_AUDIT_FAILED"],
            translate.stderr or text_audit.stdout,
        )


def main() -> None:
    global RUN_IDENTITY
    parser = argparse.ArgumentParser()
    parser.add_argument("--brief", required=True)
    parser.add_argument("--ledger")
    parser.add_argument(
        "--mode",
        choices=["single-frame", "scene", "storyboard", "diagnostic"],
        default="single-frame",
    )
    parser.add_argument("--storyboard-plan")
    parser.add_argument(
        "--provider",
        choices=["none", "generic", "grok-imagine", "flux", "sd3", "midjourney", "keyframe"],
        default="none",
    )
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out, brief, plan = _load_request(args)
    identity_input = {"brief": brief, "storyboard_plan": plan}
    plan_strict = isinstance(plan, dict) and plan.get("strict") is True
    strict = bool(args.strict) or brief.get("strict") is True or plan_strict
    RUN_IDENTITY = compile_identity(identity_input, mode=args.mode, provider=args.provider)
    normalized = out / "brief.normalized.yaml"
    write(normalized, brief)
    selected = _selected_grammar(out, normalized)
    graph_path, schema_reports, graph = _private_graph(out, brief, selected)
    structured_path = out / "structured-symbolic-packet.yaml"
    write(structured_path, build_structured_packet(brief, graph, selected))
    structured = run([
        PY, str(ROOT / "scripts/audit_symbolic_structure.py"),
        "--input", str(structured_path),
        "--output", str(out / "structured-anti-slop-report.json"),
    ])
    if structured.returncode != 0:
        fail(out, "structured-audit", ["STRUCTURED_ANTI_SLOP_FAILED"], structured.stdout)
    _audience(out, graph_path, args.mode)
    artifacts = {
        "retrieval": "retrieval-receipt.yaml",
        "private_graph": graph_path.name,
        "structured_packet": structured_path.name,
        "structured_audit": "structured-anti-slop-report.json",
        "audience": "audience-constraints.yaml",
        "text_audit": "text-anti-slop-report.json",
    }
    storyboard_path = None
    if args.mode == "storyboard":
        storyboard_path = _compile_storyboard(
            out, graph_path, args.storyboard_plan, artifacts, schema_reports,
        )
    if args.provider != "none":
        extras = _compile_adapter(
            out, graph_path, args.provider, storyboard_path,
            artifacts, schema_reports, strict,
        )
    else:
        extras = {}
    final = {
        "status": "COMPILED",
        "compiler_version": "0.3.0",
        **RUN_IDENTITY,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "provider": args.provider,
        "selected_primary": selected,
        "artifacts": artifacts,
        "schema_reports": schema_reports,
        "reason_vector": [],
    }
    final.update(extras)
    receipt = json.dumps(final, indent=2) + "\n"
    write_text_bounded(out / "compile-receipt.json", receipt)
    print(json.dumps(final, indent=2))


if __name__ == "__main__":
    main()
