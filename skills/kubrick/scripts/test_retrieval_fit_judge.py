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


def test_fit_tie_breaks_on_probability_then_order() -> None:
    ranked = [
        {"pattern_id": "a", "total_score": 0.5},
        {"pattern_id": "b", "total_score": 0.5},
        {"pattern_id": "c", "total_score": 0.5},
        {"pattern_id": "d", "total_score": 0.7},
    ]
    verdicts = {k: "fit" for k in "abcd"}
    chosen, reason = fit_select(
        ranked, verdicts, floor=0.4, threshold=0.55, min_dramatic_fit=0.15, max_supporting=3,
        probabilities={"a": 0.7, "b": 0.9, "c": 0.7, "d": 0.6},
    )
    assert reason is None
    # Lexical stays primary (d), then b by probability, then a before c by order.
    assert [str(x["pattern_id"]) for x in chosen] == ["d", "b", "a", "c"]
    plain, _ = fit_select(
        ranked, verdicts, floor=0.4, threshold=0.55, min_dramatic_fit=0.15, max_supporting=3
    )
    assert [str(x["pattern_id"]) for x in plain] == ["d", "a", "b", "c"]


from kubrick.corpus.fit_judge import PRIMARY_FIT_PROBABILITY  # noqa: E402

PERMISSIVE = load_recorded(FIXTURES / "jev-fit-verdicts-permissive.yaml")


def test_permissive_judge_refuses_vocab_soup() -> None:
    receipt = _receipt(BRIEFS["nonsense-vocab"], PERMISSIVE)
    assert receipt["status"] == "NOT_COMPUTABLE"
    assert receipt["selected_primary_grammar"] is None
    assert receipt["reason_vector"][0] == "JEV_FIT_PRIMARY_MARGINAL"
    assert receipt["fit_judge"]["fit_count"] == 7


def test_permissive_judge_refuses_sourdough_weak_lexical_leader() -> None:
    brief = BRIEFS["nonsense-sourdough"]
    receipt = _receipt(brief, PERMISSIVE)
    assert receipt["status"] == "NOT_COMPUTABLE"
    assert receipt["reason_vector"][0] == "JEV_FIT_NONE"
    assert receipt["fit_judge"]["lexical_primary"] == "withheld_cause_consequence_only"
    assert _receipt(brief, None)["status"] == "SELECTED"


def test_permissive_judge_keeps_myslef_briefs() -> None:
    for brief in (BRIEFS["myslef-plain"], _example("myslef-minder")):
        receipt = _receipt(brief, PERMISSIVE)
        assert receipt["status"] == "SELECTED"
        assert receipt["selected_primary_grammar"] in MYSLEF_FIT


def test_primary_floor_refuses_without_falling_through() -> None:
    ranked: list[dict[str, Any]] = [
        {"pattern_id": "a", "total_score": 0.65},
        {"pattern_id": "b", "total_score": 0.60},
        {"pattern_id": "c", "total_score": 0.55},
    ]
    verdicts: dict[str, str] = {"a": "fit", "b": "fit", "c": "fit"}
    common: dict[str, Any] = {
        "floor": 0.4,
        "threshold": 0.55,
        "min_dramatic_fit": 0.15,
        "max_supporting": 2,
    }

    probabilities = {"a": 0.68, "b": 0.97, "c": 0.9}
    selected, reason = fit_select(
        ranked, verdicts, probabilities=probabilities, primary_floor=0.75, **common
    )
    assert selected == []
    assert reason == "JEV_FIT_PRIMARY_MARGINAL"

    selected, reason = fit_select(
        ranked, verdicts, probabilities=probabilities, primary_floor=None, **common
    )
    assert [item["pattern_id"] for item in selected] == ["a", "b", "c"]
    assert reason is None

    missing_a = {"b": 0.97, "c": 0.9}
    selected, reason = fit_select(
        ranked, verdicts, probabilities=missing_a, primary_floor=0.75, **common
    )
    assert [item["pattern_id"] for item in selected] == ["a", "b", "c"]

    higher = {"a": 0.8, "b": 0.97, "c": 0.9}
    selected, reason = fit_select(
        ranked, verdicts, probabilities=higher, primary_floor=0.75, **common
    )
    assert [item["pattern_id"] for item in selected] == ["a", "b", "c"]
    assert selected[0]["pattern_id"] == "a"


def test_current_recordings_unchanged_by_primary_floor() -> None:
    expected = {
        "myslef-plain": "SELECTED",
        "authority-plain": "SELECTED",
        "nonsense-vocab": "NOT_COMPUTABLE",
        "nonsense-sourdough": "NOT_COMPUTABLE",
        "cats-and-dogs": "NOT_COMPUTABLE",
    }
    receipts: dict[str, dict[str, Any]] = {}
    for name, status in expected.items():
        receipt = _receipt(BRIEFS[name], RECORDED)
        assert receipt["status"] == status
        receipts[name] = receipt
    probabilities = [
        receipt["fit_judge"].get("primary_fit_probability")
        for receipt in receipts.values()
    ]
    assert PRIMARY_FIT_PROBABILITY in probabilities
