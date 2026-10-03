#!/usr/bin/env python3
"""Audit Kubrick's executable corpus without external services.

Uses only the Python standard library. YAML catalogs are read with
conservative line parsing. Pattern sidecars are parsed as JSON.

The audit fails closed when a sidecar is missing from the index, a wave
manifest, or the executable registry, when a catalog names a missing
sidecar, when a lexicon link does not match a lexicon heading, when a
pattern directory disagrees with ``domain``, or when ``grammar_family``
is outside the transformation-grammar registry.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from io_safety import PathSafetyError, write_text_bounded

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "out" / "kubrick" / "corpus-coverage.json"

# Snake-case ids of the 17 entries in transformation-grammar-registry.md.
GRAMMAR_FAMILIES = (
    "calcination",
    "dissolution",
    "separation",
    "conjunction",
    "fermentation",
    "distillation",
    "coagulation",
    "sublimation",
    "putrefaction",
    "fixation",
    "circulation",
    "multiplication",
    "projection",
    "initiation",
    "contamination",
    "fragmentation",
    "descent",
)

THIN_FIELDS = (
    "source_status",
    "applicable_formats",
    "applicable_genres",
    "cultural_scope",
    "lexicon_links",
)

ID_LINE = re.compile(r"^\s*-?\s*(?:id|pattern_id):\s*([a-z0-9_\-]+)\s*$")
PATH_LINE = re.compile(r"^\s*path:\s*(\S+)\s*$")
LIST_ID = re.compile(r"^\s*-\s+([a-z0-9_\-]+)\s*$")
HEADING = re.compile(r"^##\s+(?:\d+\.\s+)?(.+?)\s*$", re.MULTILINE)
ROUTE_KEY = re.compile(r"^  ([a-z0-9_\-]+):\s*$")
ROUTE_ITEM = re.compile(r"^  - \S+")


@dataclass(frozen=True)
class CorpusPaths:
    """Locations the coverage audit reads. Tests can point these at a fixture."""

    root: Path
    patterns: Path
    manifests: Path
    index: Path
    registry: Path
    lexicon: Path


def default_paths(root: Path | None = None) -> CorpusPaths:
    base = root or ROOT
    references = base / "references"
    return CorpusPaths(
        root=base,
        patterns=references / "patterns",
        manifests=references / "pattern-manifests",
        index=references / "corpus-index.yaml",
        registry=references / "executable-corpus-registry.yaml",
        lexicon=references / "esoteric-alchemical-lexicon.md",
    )


def _slug(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text)
    plain = "".join(char for char in folded if not unicodedata.combining(char))
    lowered = plain.lower().replace("'", "").replace("\u2019", "")
    return re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")


def lexicon_slugs(text: str) -> set[str]:
    """Heading slugs, plus a few mechanical trims of those headings.

    Diacritics fold (``Doppelgänger`` matches ``doppelganger``). A leading
    ``the_`` or ``the_principle_of_`` may be dropped. The token ``et`` and the
    text before `` or `` may be dropped. Links still have to name a heading.
    """

    found: set[str] = set()
    for heading in HEADING.findall(text):
        base = _slug(heading)
        if not base:
            continue
        found.add(base)
        if base.startswith("the_principle_of_"):
            found.add(base[len("the_principle_of_") :])
        elif base.startswith("the_"):
            found.add(base[4:])
        if "_or_" in base:
            found.add(base.split("_or_", 1)[0])
        if "_et_" in base:
            found.add(base.replace("_et_", "_"))
    found.discard("")
    return found


def parse_yaml_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    if not path.is_file():
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


def route_counts(registry_text: str) -> dict[str, int]:
    """Count pattern ids under each ``default_routes`` key.

    Registry lists sit at the same indent as the route key (``  - id``),
    not one level deeper. A four-space item pattern never matched, so the
    published counts stayed empty.
    """

    counts: dict[str, int] = {}
    current: str | None = None
    in_routes = False
    for line in registry_text.splitlines():
        if line.strip() == "default_routes:":
            in_routes = True
            current = None
            continue
        if not in_routes:
            continue
        if line and not line.startswith(" "):
            break
        route_match = ROUTE_KEY.match(line)
        if route_match:
            current = route_match.group(1)
            counts.setdefault(current, 0)
            continue
        if current and ROUTE_ITEM.match(line):
            counts[current] += 1
    return counts


def _string_list(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    items = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    if len(items) != len(value):
        return None
    return items


def _thin_fields(payload: Mapping[str, object]) -> list[str]:
    missing: list[str] = []
    status = payload.get("source_status")
    if not isinstance(status, str) or not status.strip():
        missing.append("source_status")
    for key in THIN_FIELDS[1:]:
        if _string_list(payload.get(key)) is None:
            missing.append(key)
    return missing


def _load_sidecars(
    paths: CorpusPaths,
) -> tuple[dict[str, dict[str, object]], list[str], Counter[str], Counter[str]]:
    patterns: dict[str, dict[str, object]] = {}
    errors: list[str] = []
    domains: Counter[str] = Counter()
    tiers: Counter[str] = Counter()
    if not paths.patterns.is_dir():
        errors.append(f"pattern directory missing: {paths.patterns}")
        return patterns, errors, domains, tiers
    for path in sorted(paths.patterns.rglob("*.json")):
        relative = path.relative_to(paths.root).as_posix()
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"invalid JSON: {relative}: {exc}")
            continue
        if not isinstance(loaded, dict):
            errors.append(f"pattern sidecar must be an object: {relative}")
            continue
        payload = {str(key): value for key, value in loaded.items()}
        pattern_id = payload.get("pattern_id")
        if not isinstance(pattern_id, str) or not pattern_id:
            errors.append(f"missing pattern_id: {relative}")
            continue
        if pattern_id in patterns:
            errors.append(f"duplicate pattern_id: {pattern_id}")
        if path.stem != pattern_id:
            errors.append(f"filename/id mismatch: {path.stem} != {pattern_id}")
        patterns[pattern_id] = payload
        domain = payload.get("domain")
        domains[domain if isinstance(domain, str) else "UNKNOWN"] += 1
        tier = payload.get("source_tier")
        tiers[tier if isinstance(tier, str) else "UNKNOWN"] += 1
        directory = path.relative_to(paths.patterns).parts[0]
        if not isinstance(domain, str) or directory != domain:
            shown = domain if isinstance(domain, str) else "UNKNOWN"
            errors.append(f"directory/domain mismatch: {pattern_id}: {directory} != {shown}")
        thin = _thin_fields(payload)
        if thin:
            errors.append(f"thin sidecar: {pattern_id}: missing {', '.join(thin)}")
        family = payload.get("grammar_family")
        if family is not None and family not in GRAMMAR_FAMILIES:
            errors.append(f"invalid grammar_family: {pattern_id}: {family}")
    return patterns, errors, domains, tiers


def _catalog_errors(
    paths: CorpusPaths, sidecar_ids: set[str],
) -> tuple[list[str], set[str], dict[str, int]]:
    errors: list[str] = []
    manifest_ids: set[str] = set()
    coverage: dict[str, int] = {}
    if paths.manifests.is_dir():
        for manifest in sorted(paths.manifests.glob("*.yaml")):
            ids = parse_yaml_ids(manifest)
            manifest_ids.update(ids)
            coverage[manifest.name] = len(ids)
            for rel in parse_manifest_paths(manifest):
                if not (paths.root / rel).is_file():
                    errors.append(f"manifest path missing: {manifest.name}: {rel}")
    else:
        errors.append("pattern manifest directory missing")
    registry_ids = parse_yaml_ids(paths.registry)
    index_ids = parse_yaml_ids(paths.index)
    pairs = (
        ("unmanifested sidecar", sidecar_ids - manifest_ids),
        ("manifest id without sidecar", manifest_ids - sidecar_ids),
        ("unregistered sidecar", sidecar_ids - registry_ids),
        ("registry id without sidecar", registry_ids - sidecar_ids),
        ("unindexed sidecar", sidecar_ids - index_ids),
        ("index id without sidecar", index_ids - sidecar_ids),
    )
    for label, found in pairs:
        errors.extend(f"{label}: {pattern_id}" for pattern_id in sorted(found))
    return errors, manifest_ids, coverage


def _link_errors(
    patterns: Mapping[str, Mapping[str, object]], slugs: set[str],
) -> tuple[list[str], Counter[str]]:
    errors: list[str] = []
    counts: Counter[str] = Counter()
    for pattern_id in sorted(patterns):
        links = _string_list(patterns[pattern_id].get("lexicon_links"))
        if links is None:
            continue
        counts.update(links)
        for link in links:
            if link not in slugs:
                errors.append(f"dead lexicon link: {pattern_id}: {link}")
    return errors, counts


def build_report(paths: CorpusPaths | None = None) -> dict[str, object]:
    """Return the coverage report. ``status`` is FAIL when ``errors`` is non-empty."""

    chosen = paths or default_paths()
    patterns, errors, domains, tiers = _load_sidecars(chosen)
    catalog_errors, manifest_ids, coverage = _catalog_errors(chosen, set(patterns))
    errors.extend(catalog_errors)
    if chosen.lexicon.is_file():
        slugs = lexicon_slugs(chosen.lexicon.read_text(encoding="utf-8"))
    else:
        slugs = set()
        errors.append("lexicon missing")
    link_errors, lexicon_counts = _link_errors(patterns, slugs)
    errors.extend(link_errors)
    registry_text = chosen.registry.read_text(encoding="utf-8") if chosen.registry.is_file() else ""
    registry_ids = parse_yaml_ids(chosen.registry)
    index_ids = parse_yaml_ids(chosen.index)
    sidecar_ids = set(patterns)
    return {
        "status": "FAIL" if errors else "PASS",
        "total_sidecars": len(sidecar_ids),
        "manifested_sidecars": len(sidecar_ids & manifest_ids),
        "registry_sidecars": len(sidecar_ids & registry_ids),
        "indexed_sidecars": len(sidecar_ids & index_ids),
        "domains": dict(sorted(domains.items())),
        "source_tiers": dict(sorted(tiers.items())),
        "route_counts": dict(sorted(route_counts(registry_text).items())),
        "top_lexicon_links": lexicon_counts.most_common(20),
        "manifest_coverage": coverage,
        "unmanifested_sidecars": sorted(sidecar_ids - manifest_ids),
        "manifest_ids_without_sidecars": sorted(manifest_ids - sidecar_ids),
        "registry_ids_without_sidecars": sorted(registry_ids - sidecar_ids),
        "sidecars_not_in_registry": sorted(sidecar_ids - registry_ids),
        "sidecars_not_in_index": sorted(sidecar_ids - index_ids),
        "index_references_without_sidecars": sorted(index_ids - sidecar_ids),
        "errors": errors,
        "warnings": [],
    }


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
    report = build_report(default_paths())
    _emit_report(report, argv)
    errors = report["errors"]
    return 1 if isinstance(errors, list) and errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
