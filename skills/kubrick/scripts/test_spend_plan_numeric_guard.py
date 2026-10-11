#!/usr/bin/env python3
"""Regression tests for finite spend estimates and budget caps."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from spend_plan import budget_error, spend_estimate  # noqa: E402


def test_non_finite_spend_inputs_fail_closed() -> None:
    for seconds in (float("nan"), float("inf"), float("-inf"), 1e308):
        estimate = spend_estimate("keyframe", [{"generated_seconds": seconds}])
        assert estimate["status"] == "NOT_COMPUTABLE"
        assert estimate["total_credits"] is None
        assert str(budget_error(estimate, 100)).startswith("BUDGET_CAP_UNVERIFIABLE")

    large_finite = 10 ** 1000
    estimate = spend_estimate("keyframe", [{"generated_seconds": large_finite}])
    assert estimate["status"] == "NOT_COMPUTABLE"
    assert estimate["total_credits"] is None
    assert str(budget_error(estimate, 100)).startswith("BUDGET_CAP_UNVERIFIABLE")

    invalid_totals = (
        {"status": "INFERRED", "total_credits": float("nan")},
        {"status": "INFERRED", "total_credits": float("inf")},
        {"status": "INFERRED", "total_credits": large_finite},
    )
    for estimate in invalid_totals:
        assert str(budget_error(estimate, 100)).startswith("BUDGET_CAP_UNVERIFIABLE")

    finite_estimate = {"status": "INFERRED", "total_credits": 5}
    for cap in (float("nan"), float("inf"), float("-inf"), large_finite):
        assert str(budget_error(finite_estimate, cap)).startswith("BUDGET_CAP_UNVERIFIABLE")


def test_malformed_generated_seconds_fail_closed() -> None:
    malformed_rows: list[dict[str, object]] = [
        {"shot": "bad", "generated_seconds": "12"},
        {"shot": "bad", "generated_seconds": None},
        {"shot": "bad", "generated_seconds": True},
        {"shot": "bad"},
    ]
    valid_row: dict[str, object] = {"shot": "good", "generated_seconds": 1}

    for malformed in malformed_rows:
        estimate = spend_estimate("keyframe", [valid_row, malformed])
        assert estimate["status"] == "NOT_COMPUTABLE"
        assert estimate["total_credits"] is None
        assert str(budget_error(estimate, 100)).startswith(
            "BUDGET_CAP_UNVERIFIABLE"
        )


def test_empty_rows_remain_an_inferred_zero_estimate() -> None:
    estimate = spend_estimate("keyframe", [])
    assert estimate["status"] == "INFERRED"
    assert estimate["total_credits"] == 0


def test_finite_negative_duration_behavior_remains_unchanged() -> None:
    estimate = spend_estimate(
        "keyframe", [{"shot": "negative", "generated_seconds": -1}]
    )
    assert estimate["status"] == "INFERRED"
    assert estimate["total_credits"] == -15.5
