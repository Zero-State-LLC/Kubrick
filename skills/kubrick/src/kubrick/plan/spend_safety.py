#!/usr/bin/env python3
"""Late-bill and unavailable-estimate rules. No provider is called.

Observed Seedance whole-second bills (4/5/6 seconds) are the billed-rate
table. ``estimateAvailable: false`` uses that table. A missing row is
``NOT_COMPUTABLE``, never zero and never ``seconds * 15.5``.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

TIMEOUT_CODE = -32001
POLL_SECONDS = 360
BILLED_CREDITS: dict[int, int] = {4: 62, 5: 77, 6: 93}

SPEND_RULES: dict[str, object] = {
    "one_node_per_call": True,
    "timeout_code": TIMEOUT_CODE,
    "on_timeout": "reconcile_later",
    "retry_submit": False,
    "poll_object_key_seconds": POLL_SECONDS,
    "unavailable_estimate": "billed_rate_table",
}


def whole_seconds(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number <= 0 or number != int(number):
        return None
    return int(number)


def estimate_available(row: Mapping[str, object]) -> bool:
    """False only when the provider said the estimate is unavailable."""
    if "estimate_available" in row:
        return row.get("estimate_available") is not False
    if "estimateAvailable" in row:
        return row.get("estimateAvailable") is not False
    return True


def quote_unavailable(seconds: object) -> dict[str, object]:
    """Credits from the billed-rate table. Never a rate product and never zero."""
    whole = whole_seconds(seconds)
    credits = None if whole is None else BILLED_CREDITS.get(whole)
    if whole is None or credits is None:
        return {
            "status": "NOT_COMPUTABLE",
            "credits": None,
            "generated_seconds": whole,
            "source": "billed_rate_table",
            "message": "estimateAvailable is false and this duration has no billed rate",
        }
    return {
        "status": "INFERRED",
        "credits": credits,
        "generated_seconds": whole,
        "source": "billed_rate_table",
        "estimate_available": False,
    }


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _whole(value: float) -> int | float:
    if value == int(value):
        return int(value)
    return value


def _closed_estimate(message: str) -> dict[str, object]:
    return {
        "label": "INFERRED",
        "status": "NOT_COMPUTABLE",
        "unit": None,
        "resolution": None,
        "rate": None,
        "shots": [],
        "total_credits": None,
        "message": message,
        "unavailable_quote": "billed_rate_table",
    }


def apply_unavailable_quotes(
    estimate: Mapping[str, object],
    paid: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Swap in billed credits where the provider withheld the estimate."""
    shots = estimate.get("shots")
    if not isinstance(shots, list):
        return _closed_estimate("spend estimate has no shot list")
    paid_by_shot: dict[str, Mapping[str, object]] = {}
    for row in paid:
        shot = row.get("shot")
        if isinstance(shot, str) and shot.strip():
            paid_by_shot[shot.strip()] = row
    revised: list[dict[str, object]] = []
    total = 0.0
    used_table = False
    for item in shots:
        if not isinstance(item, Mapping):
            return _closed_estimate("spend estimate shot is not an object")
        current = dict(item)
        label = current.get("shot")
        name = label.strip() if isinstance(label, str) else ""
        matched = paid_by_shot.get(name)
        if matched is not None and not estimate_available(matched):
            quoted = quote_unavailable(matched.get("generated_seconds"))
            if quoted.get("status") != "INFERRED":
                message = quoted.get("message")
                text = message if isinstance(message, str) else "billed rate is not computable"
                return _closed_estimate(text)
            current["credits"] = quoted["credits"]
            current["quote"] = "billed_rate_table"
            used_table = True
        amount = _number(current.get("credits"))
        if amount is None:
            return _closed_estimate("spend estimate credits are missing")
        total += amount
        revised.append(current)
    if not used_table:
        return dict(estimate)
    result = dict(estimate)
    result["shots"] = revised
    result["total_credits"] = _whole(total)
    result["unavailable_quote"] = "billed_rate_table"
    return result


def provider_code(payload: Mapping[str, object]) -> int | None:
    for key in ("code", "error_code"):
        value = payload.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    error = payload.get("error")
    if isinstance(error, Mapping):
        code = error.get("code")
        if isinstance(code, int) and not isinstance(code, bool):
            return code
    return None


def _object_key(payload: Mapping[str, object]) -> str | None:
    raw = payload.get("objectKey", payload.get("object_key"))
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def classify_submit(payload: Mapping[str, object]) -> dict[str, object]:
    """A ``-32001`` timeout is reconcile-later. It is not a second submit."""
    code = provider_code(payload)
    key = _object_key(payload)
    if code == TIMEOUT_CODE:
        return {
            "kind": "reconcile_later",
            "code": TIMEOUT_CODE,
            "retry_submit": False,
            "second_submit": False,
            "poll_object_key": key,
            "poll_seconds": POLL_SECONDS,
            "nodes_per_call": 1,
        }
    return {
        "kind": "submit_result",
        "code": code,
        "retry_submit": False,
        "second_submit": False,
        "poll_object_key": key,
        "nodes_per_call": 1,
    }


def _bill_credits(bill: Mapping[str, object]) -> float | None:
    return _number(bill.get("credits"))


def _bill_key(bill: Mapping[str, object]) -> str | None:
    return _object_key(bill)


def reconcile_late_bill(
    entries: Sequence[Mapping[str, object]],
    bill: Mapping[str, object],
) -> dict[str, object]:
    """Attach a late bill to its reconcile-later row. Do not append a submit."""
    kept = [dict(item) for item in entries]
    key = _bill_key(bill)
    credits = _bill_credits(bill)
    if key is None:
        return {
            "status": "NOT_COMPUTABLE",
            "reason": "late bill has no object key",
            "entries": kept,
            "appended_submit": False,
        }
    if credits is None:
        return {
            "status": "NOT_COMPUTABLE",
            "reason": "late bill credits are missing",
            "entries": kept,
            "appended_submit": False,
        }
    matched = False
    updated: list[dict[str, object]] = []
    for row in kept:
        if (
            not matched
            and row.get("kind") == "reconcile_later"
            and row.get("poll_object_key") == key
            and row.get("reconciled") is not True
        ):
            row["reconciled"] = True
            row["billed_credits"] = credits
            matched = True
        updated.append(row)
    if not matched:
        return {
            "status": "NOT_COMPUTABLE",
            "reason": "no reconcile-later row for this object key",
            "entries": updated,
            "appended_submit": False,
        }
    updated.append({
        "kind": "late_bill",
        "object_key": key,
        "credits": credits,
        "submit": False,
    })
    return {"status": "PROPOSED", "entries": updated, "appended_submit": False}
