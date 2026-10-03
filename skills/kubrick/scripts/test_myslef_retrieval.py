#!/usr/bin/env python3
"""The real MYSLEF brief retrieves a fitting pattern (#81)."""
from __future__ import annotations

import json
import sys
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

MYSLEF_BRIEF = ROOT / "examples" / "myslef-minder" / "brief.yaml"
MYSLEF_FIXTURE = ROOT / "evals" / "fixtures" / "myslef" / "minder-brief.yaml"
AUTHORITY_BRIEF = ROOT / "examples" / "authority-transfer-storyboard" / "brief.yaml"
AUTHORITY_PROBLEM = (
    "authority remains active after the leader exits because access and "
    "geometry preserve the system"
)
FITTING = frozenset({
    "withheld_cause_consequence_only",
    "dormant_watcher_background_presence",
    "acousmatic_sound",
    "anempathetic_sound_indifference",
    "automaton_uncanny_double",
})
WAVE3 = (
    "withheld_cause_consequence_only",
    "dormant_watcher_background_presence",
    "automaton_uncanny_double",
    "anempathetic_sound_indifference",
    "power_failure_world_response",
    "horror_domestic_trap",
)


def _receipt(brief: dict[str, Any]) -> dict[str, Any]:
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
    receipt = payload["retrieval_receipt"]
    assert isinstance(receipt, dict)
    return receipt


def _load_brief(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _dramatic_fit(receipt: dict[str, Any], pattern_id: str) -> float:
    ranked = receipt["ranked_patterns"]
    assert isinstance(ranked, list)
    for item in ranked:
        if isinstance(item, dict) and item.get("pattern_id") == pattern_id:
            components = item.get("score_components")
            assert isinstance(components, dict)
            fit = components.get("dramatic_fit")
            assert isinstance(fit, (int, float)) and not isinstance(fit, bool)
            return float(fit)
    raise AssertionError(f"{pattern_id} missing from ranked patterns")


def test_myslef_brief_selects_a_fitting_pattern() -> None:
    assert MYSLEF_FIXTURE.read_bytes() == MYSLEF_BRIEF.read_bytes()
    receipt = _receipt(_load_brief(MYSLEF_BRIEF))
    assert receipt["status"] == "SELECTED"
    primary = receipt["selected_primary_grammar"]
    assert isinstance(primary, str)
    assert primary in FITTING
    assert _dramatic_fit(receipt, primary) >= base.MIN_DRAMATIC_FIT


def test_authority_transfer_still_selects_center_transfer() -> None:
    brief = _load_brief(AUTHORITY_BRIEF)
    assert brief["dramatic_problem"] == AUTHORITY_PROBLEM
    receipt = _receipt(brief)
    assert receipt["status"] == "SELECTED"
    assert receipt["selected_primary_grammar"] == "kubrick_center_transfer_authority"
    assert _dramatic_fit(receipt, "kubrick_center_transfer_authority") >= base.MIN_DRAMATIC_FIT


def test_cats_and_dogs_stays_not_computable() -> None:
    receipt = _receipt({"dramatic_problem": "cats and dogs"})
    assert receipt["status"] == "NOT_COMPUTABLE"
    assert receipt["selected_primary_grammar"] is None
    reasons = receipt["reason_vector"]
    assert isinstance(reasons, list)
    assert "LOW_DRAMATIC_FIT" in reasons


def test_wave3_sidecars_are_catalogued() -> None:
    index = (ROOT / "references" / "corpus-index.yaml").read_text(encoding="utf-8")
    registry_text = (ROOT / "references" / "executable-corpus-registry.yaml").read_text(
        encoding="utf-8"
    )
    manifest = (ROOT / "references" / "pattern-manifests" / "wave3.yaml").read_text(
        encoding="utf-8"
    )
    for pattern_id in WAVE3:
        matches = list((ROOT / "references" / "patterns").rglob(f"{pattern_id}.json"))
        assert len(matches) == 1, pattern_id
        loaded: object = json.loads(matches[0].read_text(encoding="utf-8"))
        assert isinstance(loaded, dict)
        assert loaded.get("pattern_id") == pattern_id
        assert loaded.get("domain") == matches[0].parent.name
        confidence = loaded.get("confidence")
        assert isinstance(confidence, (int, float)) and not isinstance(confidence, bool)
        assert confidence <= 0.8
        mutation = loaded.get("mutation_requirements")
        assert isinstance(mutation, dict)
        assert mutation.get("required") is True
        variables = mutation.get("variables")
        assert isinstance(variables, list) and variables
        assert isinstance(loaded.get("non_transferable_surface"), str)
        assert loaded.get("non_transferable_surface")
        risks = loaded.get("misuse_risks")
        assert isinstance(risks, list) and risks
        assert pattern_id in index
        assert pattern_id in registry_text
        assert pattern_id in manifest


def main() -> None:
    test_myslef_brief_selects_a_fitting_pattern()
    test_authority_transfer_still_selects_center_transfer()
    test_cats_and_dogs_stays_not_computable()
    test_wave3_sidecars_are_catalogued()
    print("myslef retrieval: PASS")


if __name__ == "__main__":
    main()
