#!/usr/bin/env python3
"""Corpus hygiene for issue #80: catalogs, links, grammars, fixtures, and audit."""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import audit_corpus_coverage as audit  # noqa: E402
import provider_capabilities as caps  # noqa: E402
import retrieve_symbolic_patterns as base  # noqa: E402
import retrieve_symbolic_patterns_registry as registry  # noqa: E402

FIXTURE_CAPS = ROOT / "evals" / "fixtures" / "models" / "capabilities.yaml"
PATTERN_ID = "demo_pattern"
AS_OF = date(2026, 10, 2)
_ID_LINE = re.compile(r"^\s*-?\s*(?:id|pattern_id):\s*([a-z0-9_\-]+)\s*$")
_LIST_ID = re.compile(r"^\s*-\s+([a-z0-9_\-]+)\s*$")
_JOB = re.compile(r"(?ms)^  validation-eval:\n(.*?)(?=^  [a-z0-9-]+:|\Z)")
_ALIASES = {"bind": "conjunction", "fragment": "fragmentation"}
_RETIRED = (
    re.compile(r"(?<![A-Za-z0-9_])bresson_hands(?![A-Za-z0-9_])"),
    re.compile(r"(?<![A-Za-z0-9_])kubrick_red_culmination(?![A-Za-z0-9_])"),
)
_SKIP_DIRS = {".git", "out", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache"}
_FOLDS = {
    "bresson_gesture_object_transfer": (
        "precise hand action carries relational information that dialogue withholds",
        "touching, passing, opening, or refusing the object changes causal state",
        "extreme close view of the hand at the moment of contact",
    ),
    "kubrick_red_culmination_state": (
        "red residue remains after the irreversible action",
        "delayed red field before the color occupies area",
        "warm-light takeover of a previously neutral source",
    ),
}


@contextmanager
def fixture_capabilities() -> Iterator[None]:
    """Point capability reads at the lab fixture, then restore the shipped file."""

    previous_path = caps._MODEL_PATH
    previous_cache = caps._CACHE
    caps._MODEL_PATH = FIXTURE_CAPS
    caps._CACHE = None
    try:
        yield
    finally:
        caps._MODEL_PATH = previous_path
        caps._CACHE = previous_cache


def _mentions(text: str, ident: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(ident)}(?![A-Za-z0-9_])", text) is not None


def _ids_in(path: Path) -> set[str]:
    found: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _ID_LINE.match(line) or _LIST_ID.match(line)
        if match:
            found.add(match.group(1))
    return found


def _as_dict(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return {str(key): item for key, item in value.items()}


def _records() -> list[tuple[str, dict[str, object]]]:
    root = ROOT / "references" / "patterns"
    records: list[tuple[str, dict[str, object]]] = []
    for path in sorted(root.rglob("*.json")):
        payload = _as_dict(json.loads(path.read_text(encoding="utf-8")))
        records.append((path.relative_to(root).parts[0], payload))
    return records


def _mapped_family(tokens: object) -> str | None:
    if not isinstance(tokens, list):
        return None
    families = set(audit.GRAMMAR_FAMILIES)
    for token in tokens:
        if not isinstance(token, str):
            continue
        if token in families:
            return token
        alias = _ALIASES.get(token)
        if alias is not None:
            return alias
    return None


def _manual_routes(text: str) -> dict[str, int]:
    """Count two-space route items. Registry keys are not indented further."""

    counts: dict[str, int] = {}
    current: str | None = None
    inside = False
    for line in text.splitlines():
        if line.strip() == "default_routes:":
            inside = True
            current = None
            continue
        if not inside:
            continue
        if line and not line.startswith(" "):
            break
        if re.fullmatch(r"  [a-z0-9_\-]+:", line):
            current = line.strip()[:-1]
            counts[current] = 0
            continue
        if current is not None and line.startswith("  - "):
            counts[current] += 1
    return counts


def _retired_hits() -> list[str]:
    hits: list[str] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [name for name in dirnames if name not in _SKIP_DIRS]
        for name in filenames:
            path = Path(dirpath) / name
            if path.suffix not in {".py", ".json", ".yaml", ".yml", ".md"}:
                continue
            if path.name == "test_corpus_hygiene.py":
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if any(needle.search(text) for needle in _RETIRED):
                hits.append(path.relative_to(ROOT).as_posix())
    return hits


def _plant(
    root: Path,
    *,
    domain: str = "cinematic",
    directory: str | None = None,
    links: list[str] | None = None,
    family: str | None = "initiation",
    omit_links: bool = False,
    index: bool = True,
    manifest: bool = True,
    registered: bool = True,
    lexicon: str = "## 86. Water\n",
) -> audit.CorpusPaths:
    folder = directory or domain
    chosen_links = ["water"] if links is None else links
    payload: dict[str, object] = {
        "pattern_id": PATTERN_ID,
        "domain": domain,
        "source_status": "VALIDATED",
        "applicable_formats": ["feature"],
        "applicable_genres": ["drama"],
        "cultural_scope": ["fixture scope"],
    }
    if not omit_links:
        payload["lexicon_links"] = chosen_links
    if family is not None:
        payload["grammar_family"] = family
    pattern_dir = root / "references" / "patterns" / folder
    pattern_dir.mkdir(parents=True)
    (pattern_dir / f"{PATTERN_ID}.json").write_text(json.dumps(payload), encoding="utf-8")
    references = root / "references"
    item = f"  - {PATTERN_ID}\n" if index else ""
    (references / "corpus-index.yaml").write_text(
        f"index_version: '0.11.5'\nby_domain:\n  cinematic:\n{item}",
        encoding="utf-8",
    )
    manifests = references / "pattern-manifests"
    manifests.mkdir()
    relative = f"references/patterns/{folder}/{PATTERN_ID}.json"
    if manifest:
        manifest_text = f"patterns:\n  - id: {PATTERN_ID}\n    path: {relative}\n"
    else:
        manifest_text = "patterns: []\n"
    (manifests / "wave.yaml").write_text(manifest_text, encoding="utf-8")
    if registered:
        registry_text = (
            "default_routes:\n  identity_and_transformation:\n"
            f"  - {PATTERN_ID}\n"
        )
    else:
        registry_text = "default_routes:\n  identity_and_transformation: []\n"
    (references / "executable-corpus-registry.yaml").write_text(registry_text, encoding="utf-8")
    (references / "esoteric-alchemical-lexicon.md").write_text(lexicon, encoding="utf-8")
    return audit.CorpusPaths(
        root=root,
        patterns=references / "patterns",
        manifests=manifests,
        index=references / "corpus-index.yaml",
        registry=references / "executable-corpus-registry.yaml",
        lexicon=references / "esoteric-alchemical-lexicon.md",
    )


def _fail(paths: audit.CorpusPaths, expected: str) -> None:
    report = audit.build_report(paths)
    assert report["errors"] == [expected], report["errors"]
    assert report["status"] == "FAIL"
    assert report["warnings"] == []


def _registry_status(brief_path: Path) -> str:
    """Status from the registry entrypoint compile and the Hermes evals call.

    These briefs stay under the base scorer's threshold. The route bonus is
    what makes the registry receipt SELECTED.
    """

    brief = base.read_brief(brief_path)
    ledger = base.ledger_snapshot(brief)
    patterns = base.load_all_patterns()
    routes, strong = registry.route_registry()
    matched = registry.route_matches(brief, routes)
    ranked = sorted(
        (
            registry.score_with_registry(pattern, brief, ledger, routes, matched, strong)
            for pattern in patterns.values()
        ),
        key=lambda item: (-item["total_score"], item["pattern_id"]),
    )
    receipt = registry.build_receipt(brief, ranked, ledger, matched, routes)
    status = receipt["retrieval_receipt"]["status"]
    assert isinstance(status, str)
    return status


def test_every_sidecar_is_indexed_registered_and_manifested() -> None:
    records = _records()
    ids = {str(payload["pattern_id"]) for _directory, payload in records}
    index_path = ROOT / "references" / "corpus-index.yaml"
    registry_path = ROOT / "references" / "executable-corpus-registry.yaml"
    manifest_dir = ROOT / "references" / "pattern-manifests"
    index_text = index_path.read_text(encoding="utf-8")
    registry_text = registry_path.read_text(encoding="utf-8")
    manifests = sorted(manifest_dir.glob("*.yaml"))
    manifest_text = "\n".join(path.read_text(encoding="utf-8") for path in manifests)
    listed: set[str] = set()
    for path in manifests:
        listed |= _ids_in(path)
    for pattern_id in ids:
        assert _mentions(index_text, pattern_id), pattern_id
        assert _mentions(registry_text, pattern_id), pattern_id
        assert _mentions(manifest_text, pattern_id), pattern_id
    assert ids == _ids_in(index_path)
    assert ids == _ids_in(registry_path)
    assert ids == listed
    assert (manifest_dir / "wave2.yaml").is_file()
    report = audit.build_report()
    assert report["status"] == "PASS", report["errors"]
    assert report["warnings"] == []
    assert report["total_sidecars"] == len(ids)
    assert report["sidecars_not_in_index"] == []


def test_directories_match_domains_and_thin_fields_are_filled() -> None:
    moved = {
        "myth-folklore": "propp_villainy_lack_mediation",
        "ritual-liminal": "liminal_threshold_crossing",
        "sound-rhythmic": "acousmatic_sound",
    }
    for domain, pattern_id in moved.items():
        path = ROOT / "references" / "patterns" / domain / f"{pattern_id}.json"
        assert path.is_file(), path
    for legacy in ("myth", "ritual", "sound"):
        assert not (ROOT / "references" / "patterns" / legacy).exists()
    for directory, payload in _records():
        assert directory == payload["domain"]
        status = payload["source_status"]
        assert isinstance(status, str) and status.strip()
        for field in audit.THIN_FIELDS[1:]:
            value = payload[field]
            assert isinstance(value, list) and value, (payload["pattern_id"], field)
            assert all(isinstance(item, str) and item.strip() for item in value)


def test_duplicate_sidecars_are_merged() -> None:
    cinematic = ROOT / "references" / "patterns" / "cinematic"
    assert not (cinematic / "bresson_hands.json").exists()
    assert not (cinematic / "kubrick_red_culmination.json").exists()
    for pattern_id, lines in _FOLDS.items():
        raw = (cinematic / f"{pattern_id}.json").read_text(encoding="utf-8")
        blob = json.dumps(_as_dict(json.loads(raw)))
        for line in lines:
            assert line in blob
    red_path = cinematic / "kubrick_red_culmination_state.json"
    red = _as_dict(json.loads(red_path.read_text(encoding="utf-8")))
    assert red["grammar_family"] == "coagulation"
    assert _retired_hits() == []


def test_lexicon_links_resolve() -> None:
    slugs = audit.lexicon_slugs(
        (ROOT / "references" / "esoteric-alchemical-lexicon.md").read_text(encoding="utf-8")
    )
    assert "alkhaest" in slugs
    assert "doppelganger" in slugs
    assert "alkahest" not in slugs
    links: set[str] = set()
    for _directory, payload in _records():
        raw = payload["lexicon_links"]
        assert isinstance(raw, list)
        links.update(str(item) for item in raw)
    for dead in ("alkahest", "panopticon", "offscreen_space", "empty_center", "malkuth"):
        assert dead not in links
    assert "alkhaest" in links
    assert "doppelganger" in links
    report = audit.build_report()
    errors = report["errors"]
    assert isinstance(errors, list)
    assert report["status"] == "PASS"
    assert not any(str(item).startswith("dead lexicon link:") for item in errors)


def test_grammar_family_maps_clear_registry_names() -> None:
    families = set(audit.GRAMMAR_FAMILIES)
    for _directory, payload in _records():
        family = payload.get("grammar_family")
        if family is not None:
            assert family in families
        mapped = _mapped_family(payload.get("transformation_grammars"))
        if mapped is not None:
            assert family == mapped
        pattern_id = payload["pattern_id"]
        if pattern_id == "denis_marching":
            assert family == "conjunction"
        if pattern_id == "kubrick_red_culmination_state":
            assert family == "coagulation"


def test_route_counts_follow_registry_lists() -> None:
    text = (ROOT / "references" / "executable-corpus-registry.yaml").read_text(encoding="utf-8")
    manual = _manual_routes(text)
    report = audit.build_report()
    assert report["route_counts"] == manual
    assert manual
    assert all(count >= 1 for count in manual.values())


def test_fixture_models_are_not_shipped() -> None:
    shipped = (ROOT / "assets" / "models" / "capabilities.yaml").read_text(encoding="utf-8")
    fixture = FIXTURE_CAPS.read_text(encoding="utf-8")
    for name in ("seedance-lab", "seedance-stale", "seedance-effective"):
        assert name not in shipped
        assert name in fixture
    lab = caps.provider_capabilities("keyframe", "seedance-lab", path=FIXTURE_CAPS)
    assert lab["start_frame_hold_seconds"] == 0.5
    stale = caps.capability_warnings(
        "keyframe", {"model": "seedance-stale"}, as_of=AS_OF, path=FIXTURE_CAPS,
    )
    assert stale and stale[0]["code"] == "CAPABILITY_STALE"
    loaded = yaml.safe_load(shipped)
    assert isinstance(loaded, dict)
    assert loaded["version"] == "1"


def test_fixture_context_swaps_the_model_file() -> None:
    with fixture_capabilities():
        lab = caps.provider_capabilities("keyframe", "seedance-lab")
        assert lab["start_frame_hold_seconds"] == 0.5
    assert caps.default_model("keyframe") == "seedance-2.5"


def test_unused_cinematic_pattern_schema_is_gone() -> None:
    assert not (ROOT / "schemas" / "cinematic-pattern.schema.json").exists()
    manifest = (ROOT / "kubrick.manifest.yaml").read_text(encoding="utf-8")
    guide = (ROOT / "references" / "retrieval-and-continuity.md").read_text(encoding="utf-8")
    assert "cinematic-pattern.schema.json" not in manifest
    assert "cinematic-pattern.schema.json" not in guide
    schema = _as_dict(json.loads(
        (ROOT / "schemas" / "symbolic-narrative-pattern.schema.json").read_text(encoding="utf-8")
    ))
    properties = _as_dict(schema["properties"])
    grammar = _as_dict(properties["grammar_family"])
    assert grammar["enum"] == list(audit.GRAMMAR_FAMILIES)


def test_validation_eval_runs_coverage_audit() -> None:
    for relative in (
        ".github/workflows/hermes-evals.yml",
        "docs/ci/hermes-evals.hardened.yml",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        match = _JOB.search(text)
        assert match, relative
        assert "python scripts/audit_corpus_coverage.py" in match.group(1)


def test_dead_lexicon_link_fails() -> None:
    with tempfile.TemporaryDirectory() as directory:
        paths = _plant(Path(directory), links=["alkahest"])
        _fail(paths, "dead lexicon link: demo_pattern: alkahest")


def test_unindexed_sidecar_fails() -> None:
    with tempfile.TemporaryDirectory() as directory:
        _fail(_plant(Path(directory), index=False), "unindexed sidecar: demo_pattern")


def test_unmanifested_sidecar_fails() -> None:
    with tempfile.TemporaryDirectory() as directory:
        _fail(_plant(Path(directory), manifest=False), "unmanifested sidecar: demo_pattern")


def test_unregistered_sidecar_fails() -> None:
    with tempfile.TemporaryDirectory() as directory:
        _fail(_plant(Path(directory), registered=False), "unregistered sidecar: demo_pattern")


def test_directory_domain_mismatch_fails() -> None:
    with tempfile.TemporaryDirectory() as directory:
        paths = _plant(Path(directory), domain="myth-folklore", directory="myth")
        _fail(paths, "directory/domain mismatch: demo_pattern: myth != myth-folklore")


def test_invalid_grammar_family_fails() -> None:
    with tempfile.TemporaryDirectory() as directory:
        paths = _plant(Path(directory), family="not_a_family")
        _fail(paths, "invalid grammar_family: demo_pattern: not_a_family")


def test_thin_sidecar_fails() -> None:
    with tempfile.TemporaryDirectory() as directory:
        paths = _plant(Path(directory), omit_links=True)
        _fail(paths, "thin sidecar: demo_pattern: missing lexicon_links")


def test_minimal_corpus_passes() -> None:
    with tempfile.TemporaryDirectory() as directory:
        report = audit.build_report(_plant(Path(directory)))
        assert report["status"] == "PASS", report["errors"]
        assert report["errors"] == []
        assert report["warnings"] == []
        assert report["route_counts"] == {"identity_and_transformation": 1}
        assert report["total_sidecars"] == 1


def test_myslef_and_authority_retrieval_select() -> None:
    briefs = (
        ROOT / "examples" / "myslef-minder" / "brief.yaml",
        ROOT / "examples" / "authority-transfer-storyboard" / "brief.yaml",
    )
    for brief in briefs:
        assert _registry_status(brief) == "SELECTED"


def main() -> None:
    test_every_sidecar_is_indexed_registered_and_manifested()
    test_directories_match_domains_and_thin_fields_are_filled()
    test_duplicate_sidecars_are_merged()
    test_lexicon_links_resolve()
    test_grammar_family_maps_clear_registry_names()
    test_route_counts_follow_registry_lists()
    test_fixture_models_are_not_shipped()
    test_fixture_context_swaps_the_model_file()
    test_unused_cinematic_pattern_schema_is_gone()
    test_validation_eval_runs_coverage_audit()
    test_dead_lexicon_link_fails()
    test_unindexed_sidecar_fails()
    test_unmanifested_sidecar_fails()
    test_unregistered_sidecar_fails()
    test_directory_domain_mismatch_fails()
    test_invalid_grammar_family_fails()
    test_thin_sidecar_fails()
    test_minimal_corpus_passes()
    test_myslef_and_authority_retrieval_select()
    print("corpus hygiene: PASS")


if __name__ == "__main__":
    main()
