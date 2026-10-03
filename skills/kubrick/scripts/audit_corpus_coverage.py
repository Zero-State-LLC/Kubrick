#!/usr/bin/env python3
"""Audit Kubrick's executable corpus without external services.

Uses only the Python standard library. YAML files are inspected structurally
with conservative line parsing; pattern sidecars are parsed as JSON.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path

from io_safety import PathSafetyError, write_text_bounded

ROOT = Path(__file__).resolve().parent.parent
PATTERNS = ROOT / "references" / "patterns"
MANIFESTS = ROOT / "references" / "pattern-manifests"
INDEX = ROOT / "references" / "corpus-index.yaml"
REGISTRY = ROOT / "references" / "executable-corpus-registry.yaml"
REPORT = ROOT / "out" / "kubrick" / "corpus-coverage.json"

ID_LINE = re.compile(r"^\s*-?\s*(?:id|pattern_id):\s*([a-z0-9_\-]+)\s*$")
PATH_LINE = re.compile(r"^\s*path:\s*(\S+)\s*$")
LIST_ID = re.compile(r"^\s*-\s+([a-z0-9_\-]+)\s*$")


def parse_yaml_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    if not path.exists():
        return ids
    for line in path.read_text(encoding="utf-8").splitlines():
        match = ID_LINE.match(line) or LIST_ID.match(line)
        if match:
            ids.add(match.group(1))
    return ids


def parse_manifest_paths(path: Path) -> list[str]:
    paths: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = PATH_LINE.match(line)
        if match:
            paths.append(match.group(1))
    return paths


def _route_counts() -> dict[str, int]:
    route_counts: dict[str, int] = defaultdict(int)
    registry_text = REGISTRY.read_text(encoding="utf-8") if REGISTRY.exists() else ""
    current_route = None
    in_routes = False
    for line in registry_text.splitlines():
        if line.strip() == "default_routes:":
            in_routes = True
            continue
        if in_routes and line and not line.startswith(" "):
            break
        if in_routes:
            route_match = re.match(r"^\s{2}([a-z0-9_\-]+):\s*$", line)
            if route_match:
                current_route = route_match.group(1)
                continue
            if current_route and re.match(r"^\s{4}-\s+", line):
                route_counts[current_route] += 1
    return route_counts


def _emit_report(report: Mapping[str, object], argv: list[str] | None) -> None:
    parser = argparse.ArgumentParser(description="Audit corpus coverage.")
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)
    destination = Path(args.output) if args.output else REPORT
    text = json.dumps(report, indent=2) + "\n"
    try:
        write_text_bounded(destination, text)
    except PathSafetyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(text, end="")


def main(argv: list[str] | None = None) -> int:
    errors: list[str] = []
    warnings: list[str] = []
    patterns: dict[str, dict] = {}
    files_by_id: dict[str, str] = {}
    domains: Counter[str] = Counter()
    tiers: Counter[str] = Counter()
    lexicon_links: Counter[str] = Counter()

    for path in sorted(PATTERNS.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"invalid JSON: {path.relative_to(ROOT)}: {exc}")
            continue
        pattern_id = payload.get("pattern_id")
        if not pattern_id:
            errors.append(f"missing pattern_id: {path.relative_to(ROOT)}")
            continue
        if pattern_id in patterns:
            errors.append(f"duplicate pattern_id: {pattern_id}")
        patterns[pattern_id] = payload
        files_by_id[pattern_id] = str(path.relative_to(ROOT))
        domains[payload.get("domain", "UNKNOWN")] += 1
        tiers[payload.get("source_tier", "UNKNOWN")] += 1
        lexicon_links.update(payload.get("lexicon_links", []))
        if path.stem != pattern_id:
            errors.append(f"filename/id mismatch: {path.stem} != {pattern_id}")

    manifest_ids: set[str] = set()
    manifest_paths: set[str] = set()
    manifest_coverage: dict[str, int] = {}
    for manifest in sorted(MANIFESTS.glob("*.yaml")):
        ids = parse_yaml_ids(manifest)
        paths = set(parse_manifest_paths(manifest))
        manifest_ids.update(ids)
        manifest_paths.update(paths)
        manifest_coverage[manifest.name] = len(ids)
        for rel in paths:
            if not (ROOT / rel).exists():
                errors.append(f"manifest path missing: {manifest.name}: {rel}")

    registry_ids = parse_yaml_ids(REGISTRY)
    index_ids = parse_yaml_ids(INDEX)
    sidecar_ids = set(patterns)

    unmanifested = sorted(sidecar_ids - manifest_ids)
    missing_sidecars = sorted(manifest_ids - sidecar_ids)
    registry_missing = sorted(registry_ids - sidecar_ids)
    registry_unlisted = sorted(sidecar_ids - registry_ids)
    index_missing = sorted(index_ids - sidecar_ids)

    if unmanifested:
        warnings.append(f"{len(unmanifested)} sidecars are not represented in wave manifests")
    if registry_unlisted:
        warnings.append(f"{len(registry_unlisted)} sidecars are not listed in executable registry")
    if index_missing:
        warnings.append(f"{len(index_missing)} index tokens do not resolve to executable sidecars")

    route_counts = _route_counts()

    report = {
        "status": "PASS" if not errors else "FAIL",
        "total_sidecars": len(sidecar_ids),
        "manifested_sidecars": len(sidecar_ids & manifest_ids),
        "registry_sidecars": len(sidecar_ids & registry_ids),
        "domains": dict(sorted(domains.items())),
        "source_tiers": dict(sorted(tiers.items())),
        "route_counts": dict(sorted(route_counts.items())),
        "top_lexicon_links": lexicon_links.most_common(20),
        "manifest_coverage": manifest_coverage,
        "unmanifested_sidecars": unmanifested,
        "manifest_ids_without_sidecars": missing_sidecars,
        "registry_ids_without_sidecars": registry_missing,
        "sidecars_not_in_registry": registry_unlisted,
        "index_references_without_sidecars": index_missing,
        "errors": errors,
        "warnings": warnings,
    }

    _emit_report(report, argv)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
