#!/usr/bin/env python3
"""Spend safety: late bills, billed-rate quotes, Jev timeout, adapter health. Issue #98."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT))

from jev_client import (  # noqa: E402
    HttpJevClient,
    JevUnreachable,
    configured_timeout,
    resolve_client,
)
from spend_safety import (  # noqa: E402
    quote_unavailable,
    reconcile_late_bill,
)
from take_ledger import reconcile_late_bill_file  # noqa: E402
from video_runbook import record_provider_result, runbook  # noqa: E402

from tools.jev_adapter.health import health_check  # noqa: E402

_ENV = ("KUBRICK_JEV_TIMEOUT", "KUBRICK_JEV_URL", "KUBRICK_JEV_VERDICTS", "KUBRICK_JEV_OVERRIDE")

PLAN: dict[str, object] = {
    "frames": [
        {"frame_id": "f1", "shot_id": "01", "duration_seconds": 4},
        {"frame_id": "f2", "shot_id": "02", "duration_seconds": 4},
    ],
}


def _map(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value


def _rows(value: object) -> list[dict[str, object]]:
    assert isinstance(value, list)
    return [item for item in value if isinstance(item, dict)]


def _restore_env(saved: dict[str, str | None]) -> None:
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _clear_jev_env() -> dict[str, str | None]:
    saved = {key: os.environ.get(key) for key in _ENV}
    for key in _ENV:
        os.environ.pop(key, None)
    return saved


def _generation(seconds: int, available: bool) -> dict[str, object]:
    return {
        "generation_plan": [{
            "shot": "01",
            "mode": "new_generation",
            "generated_seconds": seconds,
            "estimate_available": available,
        }],
        "edit_plan": [],
        "final_clock": seconds,
    }


def test_unavailable_five_seconds_uses_billed_table() -> None:
    quoted = quote_unavailable(5)
    assert quoted["status"] == "INFERRED"
    assert quoted["credits"] == 77
    assert quoted["credits"] != 5 * 15.5
    assert quoted["credits"] != 0
    saved = _clear_jev_env()
    try:
        document = dict(PLAN)
        document["budget_cap_credits"] = 77
        result = runbook(document, _generation(5, False), "keyframe", None)
    finally:
        _restore_env(saved)
    assert result["status"] == "PROPOSED", result
    estimate = _map(result["spend_estimate"])
    assert estimate["unavailable_quote"] == "billed_rate_table"
    assert estimate["total_credits"] == 77
    shot = _rows(estimate["shots"])[0]
    assert shot["credits"] == 77
    assert shot["quote"] == "billed_rate_table"
    rules = _map(result["spend_rules"])
    assert rules["one_node_per_call"] is True
    assert rules["retry_submit"] is False
    regen = [op for op in _rows(result["ops"]) if op["op"] == "regenerate"]
    assert len(regen) == 1
    assert regen[0]["nodes"] == 1
    assert regen[0]["credits"] == 77


def test_missing_billed_duration_is_not_zero_or_a_rate_product() -> None:
    quoted = quote_unavailable(7)
    assert quoted["status"] == "NOT_COMPUTABLE"
    assert quoted["credits"] is None
    assert quoted["credits"] != 0
    assert quoted["credits"] != 7 * 15.5
    assert quote_unavailable(5.5)["status"] == "NOT_COMPUTABLE"
    assert quote_unavailable(True)["credits"] is None
    saved = _clear_jev_env()
    try:
        result = runbook(dict(PLAN), _generation(7, False), "keyframe", None)
    finally:
        _restore_env(saved)
    assert result["status"] == "NOT_COMPUTABLE"
    assert result["code"] == "PRICING_UNAVAILABLE"
    assert "total_inferred_credits" not in result


def test_timeout_is_reconcile_later_not_a_second_submit() -> None:
    recorded = record_provider_result({
        "code": -32001,
        "objectKey": " obj-1 ",
    })
    assert recorded["kind"] == "reconcile_later"
    assert recorded["retry_submit"] is False
    assert recorded["second_submit"] is False
    assert recorded["poll_object_key"] == "obj-1"
    assert recorded["poll_seconds"] == 360
    assert recorded["nodes_per_call"] == 1
    nested = record_provider_result({"error": {"code": -32001}, "object_key": "obj-2"})
    assert nested["kind"] == "reconcile_later"
    other = record_provider_result({"code": 200, "objectKey": "obj-3"})
    assert other["kind"] == "submit_result"
    assert other["second_submit"] is False
    reconciled = reconcile_late_bill([recorded], {"object_key": "obj-1", "credits": 77})
    assert reconciled["status"] == "PROPOSED"
    assert reconciled["appended_submit"] is False
    entries = _rows(reconciled["entries"])
    assert entries[0]["reconciled"] is True
    assert entries[0]["billed_credits"] == 77
    assert entries[1]["kind"] == "late_bill"
    assert entries[1]["submit"] is False
    assert all(item.get("kind") != "submit" for item in entries)
    assert all(item.get("op") != "regenerate" for item in entries)
    missing = reconcile_late_bill([recorded], {"credits": 77})
    assert missing["status"] == "NOT_COMPUTABLE"
    assert missing["appended_submit"] is False
    again = reconcile_late_bill(entries, {"objectKey": "obj-1", "credits": 77})
    assert again["status"] == "NOT_COMPUTABLE"


def test_ledger_file_reconciles_without_a_submit() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "ledger.json")
        Path(path).write_text(json.dumps({
            "entries": [{
                "kind": "reconcile_later",
                "poll_object_key": "obj-9",
                "retry_submit": False,
            }],
        }), encoding="utf-8")
        result = reconcile_late_bill_file(path, {"object_key": "obj-9", "credits": 62})
        saved = json.loads(Path(path).read_text(encoding="utf-8"))
        broken = reconcile_late_bill_file(path, {"object_key": "missing", "credits": 1})
    assert result["status"] == "PROPOSED"
    assert result["appended_submit"] is False
    kinds = [item["kind"] for item in _rows(saved["entries"])]
    assert kinds == ["reconcile_later", "late_bill"]
    assert broken["status"] == "NOT_COMPUTABLE"


def test_jev_timeout_env_and_fail_closed() -> None:
    saved = _clear_jev_env()
    try:
        assert configured_timeout(None) == 10.0
        os.environ["KUBRICK_JEV_TIMEOUT"] = "3.5"
        seen: list[float] = []

        def transport(url: str, body: Mapping[str, object], timeout: float) -> object:
            del url, body
            seen.append(timeout)
            raise TimeoutError("timed out")

        client = HttpJevClient(
            "https://jev.example/judge",
            transport=transport,
            sleeper=lambda _seconds: None,
        )
        assert client.timeout == 3.5
        try:
            client.judge({"prompt": "holds still"}, [])
        except JevUnreachable as exc:
            assert "timed out" in exc.reason
        else:
            raise AssertionError("a dead endpoint must fail closed")
        assert seen == [3.5, 3.5, 3.5]
        explicit = HttpJevClient("https://jev.example/judge", timeout=8)
        assert explicit.timeout == 8
        os.environ["KUBRICK_JEV_TIMEOUT"] = "0"
        try:
            HttpJevClient("https://jev.example/judge")
        except JevUnreachable:
            pass
        else:
            raise AssertionError("a non-positive timeout must fail closed")
        os.environ["KUBRICK_JEV_TIMEOUT"] = "nope"
        try:
            configured_timeout(None)
        except JevUnreachable:
            pass
        else:
            raise AssertionError("a non-numeric timeout must fail closed")
        os.environ["KUBRICK_JEV_URL"] = "https://jev.example/judge"
        os.environ["KUBRICK_JEV_TIMEOUT"] = "4"
        resolved = resolve_client()
        assert isinstance(resolved, HttpJevClient)
        assert resolved.timeout == 4.0
    finally:
        _restore_env(saved)


def test_retry_then_pass_does_not_retry_a_bad_verdict() -> None:
    calls = {"n": 0}

    def flaky(url: str, body: Mapping[str, object], timeout: float) -> object:
        del url, body, timeout
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("once")
        return {"verdict": "pass", "findings": []}

    client = HttpJevClient(
        "https://jev.example/judge",
        timeout=2,
        transport=flaky,
        sleeper=lambda _seconds: None,
    )
    assert client.judge({"prompt": "holds still"}, [])["verdict"] == "pass"
    assert calls["n"] == 2

    def bad(url: str, body: Mapping[str, object], timeout: float) -> object:
        del url, body, timeout
        calls["n"] += 1
        return {"verdict": "pass", "findings": [{"code": "X", "message": "no"}]}

    calls["n"] = 0
    strict = HttpJevClient(
        "https://jev.example/judge",
        timeout=2,
        transport=bad,
        sleeper=lambda _seconds: None,
    )
    try:
        strict.judge({"prompt": "holds still"}, [])
    except JevUnreachable as exc:
        assert exc.retryable is False
    else:
        raise AssertionError("a contradictory verdict must fail closed")
    assert calls["n"] == 1


def test_reference_adapter_health_stays_local() -> None:
    def refuse_network(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("the reference adapter must not open a connection")

    original = urllib.request.urlopen
    urllib.request.urlopen = refuse_network
    try:
        result = health_check()
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "jev_adapter" / "health.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        urllib.request.urlopen = original
    assert result["ok"] is True
    assert result["network"] is False
    assert result["verdict"] == "pass"
    assert proc.returncode == 0, proc.stderr
    printed = json.loads(proc.stdout)
    assert printed["ok"] is True
    assert printed["network"] is False
    for path in (ROOT / "tools" / "jev_adapter").glob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        assert "elevenlabs" not in text
        assert "produce_movie" not in text


def main() -> None:
    test_unavailable_five_seconds_uses_billed_table()
    test_missing_billed_duration_is_not_zero_or_a_rate_product()
    test_timeout_is_reconcile_later_not_a_second_submit()
    test_ledger_file_reconciles_without_a_submit()
    test_jev_timeout_env_and_fail_closed()
    test_retry_then_pass_does_not_retry_a_bad_verdict()
    test_reference_adapter_health_stays_local()
    print("spend safety tests: PASS")


if __name__ == "__main__":
    main()
