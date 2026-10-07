"""#91: retrieval needs lexical eligibility and a recorded fit verdict."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import kubrick.corpus.retrieve_symbolic_patterns as base  # noqa: E402
import kubrick.corpus.retrieve_symbolic_patterns_registry as registry  # noqa: E402
from kubrick.corpus.fit_judge import STRUCTURAL_FLOOR, fit_select, load_recorded  # noqa: E402

FIXTURES = ROOT / "evals" / "fixtures" / "retrieval"
RECORDED = load_recorded(FIXTURES / "jev-fit-verdicts.yaml")
BRIEFS = yaml.safe_load((FIXTURES / "plain-briefs.yaml").read_text("utf-8"))["briefs"]
MYSLEF_FIT = {"withheld_cause_consequence_only", "dormant_watcher_background_presence"}
AUTHORITY_FIT = {"kubrick_center_transfer_authority", "interface_badge_authority_transfer"}


def _receipt(brief: dict[str, Any], fit: object = RECORDED) -> dict[str, Any]:
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
    payload = registry.build_receipt(brief, ranked, ledger, matched, routes, fit)
    receipt = payload["retrieval_receipt"]
    assert isinstance(receipt, dict)
    return receipt


def _example(name: str) -> dict[str, Any]:
    loaded = yaml.safe_load((ROOT / "examples" / name / "brief.yaml").read_text("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_lexical_alone_shows_the_bug() -> None:
    assert _receipt(BRIEFS["myslef-plain"], None)["status"] == "NOT_COMPUTABLE"
    assert _receipt(BRIEFS["authority-plain"], None)["status"] == "NOT_COMPUTABLE"
    assert _receipt(BRIEFS["nonsense-sourdough"], None)["status"] == "SELECTED"
    assert _receipt(BRIEFS["nonsense-vocab"], None)["status"] == "SELECTED"


def test_plain_briefs_pass_without_rewording() -> None:
    myslef = _receipt(BRIEFS["myslef-plain"])
    assert myslef["status"] == "SELECTED"
    assert myslef["selected_primary_grammar"] in MYSLEF_FIT
    assert myslef["fit_judge"]["primary_verdict"] == "fit"
    authority = _receipt(BRIEFS["authority-plain"])
    assert authority["status"] == "SELECTED"
    assert authority["selected_primary_grammar"] in AUTHORITY_FIT
    assert authority["request_hash"].endswith("-jevfit")


def test_example_briefs_still_select_with_the_judge() -> None:
    myslef = _receipt(_example("myslef-minder"))
    assert myslef["status"] == "SELECTED"
    assert myslef["selected_primary_grammar"] in MYSLEF_FIT
    authority = _receipt(_example("authority-transfer-storyboard"))
    assert authority["selected_primary_grammar"] == "kubrick_center_transfer_authority"


def test_nonsense_briefs_are_refused() -> None:
    for name in ("nonsense-vocab", "nonsense-sourdough", "cats-and-dogs"):
        receipt = _receipt(BRIEFS[name])
        assert receipt["status"] == "NOT_COMPUTABLE", name
        assert receipt["selected_primary_grammar"] is None
        assert receipt["reason_vector"][0] == "JEV_FIT_NONE"


def test_unrecorded_brief_fails_closed() -> None:
    receipt = _receipt({"dramatic_problem": "a brief nobody recorded"})
    assert receipt["status"] == "NOT_COMPUTABLE"
    assert receipt["reason_vector"][0] == "JEV_FIT_UNAVAILABLE"


def test_fit_select_rules() -> None:
    def item(pid: str, total: float, fit: float = 0.0) -> dict[str, object]:
        return {"pattern_id": pid, "total_score": total, "score_components": {"dramatic_fit": fit}}

    ranked = [item("a", 0.70, 0.30), item("b", 0.60, 0.0), item("c", 0.45), item("d", 0.0)]
    chosen, reason = fit_select(
        ranked, {"a": "weak", "b": "weak", "c": " FIT ", "d": "fit"},
        floor=STRUCTURAL_FLOOR, threshold=0.55, min_dramatic_fit=0.15, max_supporting=2,
    )
    assert reason is None
    assert [str(x["pattern_id"]) for x in chosen] == ["c"]
    weak_only, why_weak = fit_select(
        ranked, {"a": "weak", "b": "weak"},
        floor=0.4, threshold=0.55, min_dramatic_fit=0.15, max_supporting=2,
    )
    assert weak_only == [] and why_weak == "JEV_FIT_NONE"
    none, why = fit_select(
        ranked, {}, floor=0.4, threshold=0.55, min_dramatic_fit=0.15, max_supporting=2,
    )
    assert none == [] and why == "JEV_FIT_NONE"
    low, below = fit_select(
        ranked, {"d": "fit"}, floor=0.4, threshold=0.55, min_dramatic_fit=0.15, max_supporting=2,
    )
    assert low == [] and below == "JEV_FIT_BELOW_FLOOR"


def test_screen_floor_and_breadth_cap() -> None:
    from kubrick.corpus.fit_judge import screen_verdicts

    verdicts = {"a": "fit", "b": "fit", "c": "weak", "d": "fit"}
    screened, reason = screen_verdicts(
        verdicts, {"a": 0.9, "b": 0.5}, fit_floor=0.6, max_fit_share=0.2, corpus_size=10,
    )
    assert screened == {"a": "fit", "b": "weak", "c": "weak", "d": "fit"}
    assert reason is None
    many = {str(i): "fit" for i in range(4)}
    _broad, too = screen_verdicts(many, {}, fit_floor=0.6, max_fit_share=0.2, corpus_size=10)
    assert too == "JEV_FIT_TOO_BROAD"
    assert verdicts["b"] == "fit"


def test_fit_request_is_generic_and_carries_counter_examples() -> None:
    from kubrick.corpus.fit_request import COUNTER_EXAMPLES, build_fit_request

    request = build_fit_request(
        {"dramatic_problem": "x", "unrelated": "y"},
        {"p1": {"title": "t", "dramatic_operations": ["a", "b", "c", "d", "e"]}},
    )
    state = request["state"]
    assert isinstance(state, dict)
    assert state["brief"] == {"dramatic_problem": "x"}
    assert state["counter_examples"] == COUNTER_EXAMPLES
    questions = request["questions"]
    assert isinstance(questions, dict) and set(questions) == {"p1"}
