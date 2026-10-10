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
