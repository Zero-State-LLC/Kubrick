#!/usr/bin/env python3
"""Retrieval ignores stop-words and refuses a weak dramatic fit (#76)."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    raise SystemExit("pyyaml required")

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import retrieve_symbolic_patterns as base  # noqa: E402
import retrieve_symbolic_patterns_registry as registry  # noqa: E402

PY = sys.executable
REQUIRED_STOP_WORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "in", "is", "of", "on", "or", "the", "to", "with",
})
AUTHORITY_BRIEF = ROOT / "examples" / "authority-transfer-storyboard" / "brief.yaml"
AUTHORITY_LEDGER = ROOT / "examples" / "authority-transfer-storyboard" / "symbolic-ledger.yaml"
MYSLEF_BRIEF = ROOT / "examples" / "myslef-minder" / "brief.yaml"


def _ledger() -> dict[str, Any]:
    return {
        "active": [],
        "retired": [],
        "prohibited": [],
        "unresolved_payoffs": [],
        "saturation_score": 0.0,
        "symbolic_debt": 0.0,
        "collisions": [],
        "prohibited_cultural_scopes": [],
    }


def _scored(pattern_id: str, score: float, dramatic_fit: float) -> dict[str, Any]:
    return {
        "pattern_id": pattern_id,
        "total_score": score,
        "score_components": {
            "dramatic_fit": dramatic_fit,
            "character_fit": 0.0,
            "cinematic_fit": 0.0,
            "cultural_fit": 0.65,
            "source_quality": 0.95,
            "mutation_potential": 0.95,
            "continuity_compatibility": 0.9,
            "payoff_compatibility": 0.75,
        },
        "collisions": [],
        "production_cost_score": 0.3,
    }


def _receipt(payload: dict[str, Any]) -> dict[str, Any]:
    receipt = payload.get("retrieval_receipt")
    if not isinstance(receipt, dict):
        raise AssertionError(f"missing retrieval_receipt: {payload!r}")
    return receipt


def _registry_receipt(brief: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    ledger = base.ledger_snapshot(brief)
    routes, strong = registry.route_registry()
    matched = registry.route_matches(brief, routes)
    ranked = sorted(
        (
            registry.score_with_registry(pattern, brief, ledger, routes, matched, strong)
            for pattern in base.load_all_patterns().values()
        ),
        key=lambda item: (-item["total_score"], item["pattern_id"]),
    )
    payload = registry.build_receipt(brief, ranked, ledger, matched, routes)
    return _receipt(payload), matched


def _run_retrieve(brief: Path, project: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["KUBRICK_PROJECT_DIR"] = str(project)
    env["KUBRICK_DIAGNOSTICS"] = "json"
    return subprocess.run(
        [PY, str(ROOT / "scripts" / "kubrick.py"), "retrieve", "--brief", str(brief), "--no-cache"],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def _load_stdout(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    loaded = yaml.safe_load(proc.stdout)
    if not isinstance(loaded, dict):
        raise AssertionError(proc.stdout + proc.stderr)
    return loaded


def test_stop_words_cover_the_required_set() -> None:
    assert REQUIRED_STOP_WORDS <= base.STOP_WORDS
    assert registry.base.STOP_WORDS is base.STOP_WORDS


def test_tokens_and_overlap_ignore_stop_words() -> None:
    tokens = base._tokens("cats and dogs")
    assert tokens == {"cats", "dogs"}
    assert "and" not in base._tokens("authority_and_institutions")
    assert base._overlap("cats and dogs", "transfer authority and access") == 0.0
    assert base._overlap("cats and dogs", "dogs chase a system") == 0.5
    assert base._tokens("and or the a an of to") == set()


def test_route_match_refuses_stop_word_only_overlap() -> None:
    routes = {
        "authority_and_institutions": {"kubrick_center_transfer_authority"},
        "and": {"kubrick_center_transfer_authority"},
        "the_and_of": set(),
    }
    assert registry.route_matches({"dramatic_problem": "cats and dogs"}, routes) == []
    assert registry.route_matches({"dramatic_problem": "and or the"}, routes) == []
    matched = registry.route_matches({"dramatic_problem": "institutional authority"}, routes)
    assert matched == ["authority_and_institutions"]


def test_registry_routes_for_real_and_empty_briefs() -> None:
    routes, _strong = registry.route_registry()
    cats, _ = _registry_receipt({"dramatic_problem": "cats and dogs"})
    assert cats["status"] == "NOT_COMPUTABLE"
    assert "LOW_DRAMATIC_FIT" in cats["reason_vector"]
    assert cats["matched_registry_routes"] == []
    assert registry.route_matches({"dramatic_problem": "cats and dogs"}, routes) == []
    authority = yaml.safe_load(AUTHORITY_BRIEF.read_text(encoding="utf-8"))
    assert isinstance(authority, dict)
    matched = registry.route_matches(authority, routes)
    assert "authority_and_institutions" in matched
    assert "and" not in base._tokens("authority_and_institutions")


def test_selection_floor_rejects_weak_dramatic_fit() -> None:
    brief = {"dramatic_problem": "cats and dogs"}
    ledger = _ledger()
    ranked = [_scored("weak_pattern", 0.9, 0.14), _scored("real_pattern", 0.7, 0.15)]
    base_receipt = _receipt(base.build_receipt(brief, ranked, ledger))
    registry_receipt = _receipt(registry.build_receipt(brief, ranked, ledger, [], {}))
    assert base_receipt["status"] == "SELECTED"
    assert base_receipt["selected_primary_grammar"] == "real_pattern"
    assert registry_receipt["status"] == "SELECTED"
    assert registry_receipt["selected_primary_grammar"] == "real_pattern"
    weak_only = [_scored("weak_pattern", 0.9, 0.0)]
    refused = _receipt(base.build_receipt(brief, weak_only, ledger))
    refused_registry = _receipt(registry.build_receipt(brief, weak_only, ledger, [], {}))
    assert refused["status"] == "NOT_COMPUTABLE"
    assert refused_registry["status"] == "NOT_COMPUTABLE"
    assert "LOW_DRAMATIC_FIT" in refused["reason_vector"]
    assert "LOW_DRAMATIC_FIT" in refused_registry["reason_vector"]
    assert not base.selection_eligible(_scored("edge", 0.55, base.MIN_DRAMATIC_FIT - 0.01))
    assert base.selection_eligible(_scored("edge", base.THRESHOLD, base.MIN_DRAMATIC_FIT))


def test_cats_and_dogs_cli_is_not_computable() -> None:
    with tempfile.TemporaryDirectory() as raw:
        project = Path(raw)
        brief = project / "brief.yaml"
        brief.write_text("dramatic_problem: cats and dogs\n", encoding="utf-8")
        proc = _run_retrieve(brief, project)
    receipt = _receipt(_load_stdout(proc))
    assert proc.returncode == 4, proc.stderr
    assert receipt["status"] == "NOT_COMPUTABLE"
    assert "LOW_DRAMATIC_FIT" in receipt["reason_vector"]
    assert receipt["selected_primary_grammar"] is None
    assert receipt["matched_registry_routes"] == []


def test_authority_transfer_still_selects() -> None:
    brief = yaml.safe_load(AUTHORITY_BRIEF.read_text(encoding="utf-8"))
    ledger = yaml.safe_load(AUTHORITY_LEDGER.read_text(encoding="utf-8"))
    assert isinstance(brief, dict)
    assert isinstance(ledger, dict)
    plain, _matched = _registry_receipt(brief)
    merged = dict(brief)
    merged["symbolic_ledger"] = ledger
    with_ledger, _matched_ledger = _registry_receipt(merged)
    for receipt in (plain, with_ledger):
        assert receipt["status"] == "SELECTED"
        assert receipt["selected_primary_grammar"] == "kubrick_center_transfer_authority"
        ranked = receipt["ranked_patterns"]
        assert isinstance(ranked, list) and ranked
        primary = ranked[0]
        assert isinstance(primary, dict)
        components = primary["score_components"]
        assert isinstance(components, dict)
        assert components["dramatic_fit"] >= base.MIN_DRAMATIC_FIT
    with tempfile.TemporaryDirectory() as raw:
        proc = _run_retrieve(AUTHORITY_BRIEF, Path(raw))
    cli_receipt = _receipt(_load_stdout(proc))
    assert proc.returncode == 0, proc.stderr
    assert cli_receipt["status"] == "SELECTED"
    assert cli_receipt["selected_primary_grammar"] == "kubrick_center_transfer_authority"


def test_myslef_brief_still_selects() -> None:
    brief = yaml.safe_load(MYSLEF_BRIEF.read_text(encoding="utf-8"))
    assert isinstance(brief, dict)
    receipt, matched = _registry_receipt(brief)
    assert receipt["status"] == "SELECTED"
    fitting = {
        "withheld_cause_consequence_only",
        "dormant_watcher_background_presence",
        "acousmatic_sound",
        "anempathetic_sound_indifference",
        "automaton_uncanny_double",
    }
    assert receipt["selected_primary_grammar"] in fitting
    assert "authority_and_institutions" not in matched
    ranked = receipt["ranked_patterns"]
    assert isinstance(ranked, list) and ranked
    primary = ranked[0]
    assert isinstance(primary, dict)
    components = primary["score_components"]
    assert isinstance(components, dict)
    assert components["dramatic_fit"] >= base.MIN_DRAMATIC_FIT



def test_cache_key_carries_selection_policy() -> None:
    import retrieve_symbolic_patterns as base
    import retrieve_symbolic_patterns_registry as registry

    brief = {"dramatic_problem": "cats and dogs"}
    ledger = base.ledger_snapshot(brief)
    original = base.SELECTION_POLICY
    keys = (base.cache_key(brief, ledger), registry.cache_key(brief, ledger))
    try:
        base.SELECTION_POLICY = "older-policy"
        changed = (base.cache_key(brief, ledger), registry.cache_key(brief, ledger))
    finally:
        base.SELECTION_POLICY = original
    assert keys[0] != changed[0]
    assert keys[1] != changed[1]


def main() -> None:
    test_stop_words_cover_the_required_set()
    test_tokens_and_overlap_ignore_stop_words()
    test_route_match_refuses_stop_word_only_overlap()
    test_registry_routes_for_real_and_empty_briefs()
    test_selection_floor_rejects_weak_dramatic_fit()
    test_cache_key_carries_selection_policy()
    test_cats_and_dogs_cli_is_not_computable()
    test_authority_transfer_still_selects()
    test_myslef_brief_still_selects()
    print("retrieval floor tests: PASS")


if __name__ == "__main__":
    main()
