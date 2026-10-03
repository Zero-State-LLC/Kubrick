#!/usr/bin/env python3
"""Report PyYAML/jsonschema availability and the routed actions they gate.

Routed as ``kubrick do check --action deps``. Observation only: exit 0 when every
validation dependency is importable (READY), exit 3 otherwise (DEGRADED).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import runtime_deps  # noqa: E402
from manifest_contract import load_manifest  # noqa: E402

SCHEMA_VERSION = "1.0.0"
TRACKED_MODULES = ("yaml", "jsonschema")


def blocked_actions(manifest: Mapping[str, object], missing: set[str]) -> list[str]:
    """Sorted ``intent.action`` keys whose declared requirements include a missing module."""
    table = manifest.get("action_requirements")
    if not isinstance(table, dict):
        return []
    blocked: list[str] = []
    for key, modules in table.items():
        if not isinstance(modules, list):
            continue
        if any(isinstance(m, str) and m in missing for m in modules):
            blocked.append(str(key))
    return sorted(blocked)


def build_report(manifest: Mapping[str, object]) -> dict[str, object]:
    missing = set(runtime_deps.missing_modules(TRACKED_MODULES))
    modules: dict[str, object] = {
        module: {
            "package": runtime_deps.package_name(module),
            "available": module not in missing,
        }
        for module in TRACKED_MODULES
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "DEGRADED" if missing else "READY",
        "modules": modules,
        "blocked_actions": blocked_actions(manifest, missing),
        "install": runtime_deps.INSTALL,
        "authority": "OBSERVATION",
    }


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(
        description="Report Kubrick validation dependency availability."
    ).parse_args(argv)
    report = build_report(load_manifest())
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "READY" else 3


if __name__ == "__main__":
    raise SystemExit(main())
