#!/usr/bin/env python3
"""Jev pre-spend gate. Issue #90.

Before any credit-spending step, each compiled prompt is judged against the
plan hold list. The gate runs first. A hold hit blocks the spend. If Jev
cannot be reached, the gate blocks unless the operator set an explicit
override, and that override is logged. Kubrick still does not call Keyframe,
ElevenLabs, or any image provider.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import TextIO

from jev_client import (
    JevClient,
    JevUnreachable,
    judge_prompt,
    prompt_sha256,
    resolve_client,
)
from jev_holds import hold_list

_OVERRIDE_VALUES = frozenset({"1", "true", "yes"})


def add_jev_arguments(parser: argparse.ArgumentParser) -> None:
    """Flags for the spend commands. Override never bypasses a hold hit."""
    parser.add_argument(
        "--jev-override",
        action="store_true",
        help="allow spend when Jev is unreachable; the override is logged",
    )
    parser.add_argument(
        "--jev-verdicts",
        default=None,
        help="JSON file of recorded Jev verdicts keyed by prompt sha256",
    )
    parser.add_argument(
        "--run-ledger",
        default=None,
        help="append the gate result to this run ledger",
    )


def override_requested(flag: bool) -> tuple[bool, str]:
    """Explicit operator override: the CLI flag, or ``KUBRICK_JEV_OVERRIDE``."""
    if flag:
        return True, "flag"
    raw = os.environ.get("KUBRICK_JEV_OVERRIDE", "").strip().casefold()
    if raw in _OVERRIDE_VALUES:
        return True, "env"
    return False, ""

def _local_blocks(
    prompts: Sequence[Mapping[str, object]], holds: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    blocked = {
        str(item.get("shot"))
        for item in holds
        if item.get("blocked") is True and isinstance(item.get("shot"), str)
    }
    checks: list[dict[str, object]] = []
    for prompt in prompts:
        shot = str(prompt.get("shot") or "")
        if shot not in blocked:
            continue
        checks.append({
            "shot": shot,
            "channel": prompt.get("channel"),
            "prompt_sha256": prompt_sha256(str(prompt.get("prompt") or "")),
            "verdict": "fail",
            "findings": [{
                "code": "BLOCKED_SHOT",
                "hold_id": shot,
                "message": f"shot {shot} is on the hold list",
            }],
        })
    return checks


def _check_message(checks: Sequence[Mapping[str, object]]) -> str:
    parts: list[str] = []
    for check in checks:
        findings = check.get("findings")
        if not isinstance(findings, Sequence) or isinstance(findings, (str, bytes)):
            continue
        for finding in findings:
            if not isinstance(finding, Mapping):
                continue
            code = finding.get("code")
            message = finding.get("message")
            hold_id = finding.get("hold_id")
            prefix = f"shot {check.get('shot')}: {code}"
            if isinstance(hold_id, str) and hold_id:
                prefix = f"{prefix} {hold_id}"
            parts.append(f"{prefix}: {message}")
    return "; ".join(parts)


def _result(
    *,
    status: str,
    authority: str,
    code: str,
    blocks: bool,
    message: str,
    holds: Sequence[Mapping[str, object]],
    checks: Sequence[Mapping[str, object]],
    override: bool,
    override_logged: bool,
    override_source: str,
) -> dict[str, object]:
    return {
        "status": status,
        "authority": authority,
        "code": code,
        "blocks_spend": blocks,
        "checked_before_spend": True,
        "override": override,
        "override_logged": override_logged,
        "override_source": override_source or None,
        "hold_ids": [str(item.get("id")) for item in holds if item.get("id") is not None],
        "checks": [dict(item) for item in checks],
        "message": message,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def log_override(record: Mapping[str, object], sink: TextIO | None = None) -> None:
    """One stderr line. ``sink`` is for tests."""
    line = "JEV_OVERRIDE " + json.dumps(record, sort_keys=True)
    print(line, file=sys.stderr if sink is None else sink)


def check_before_spend(
    holds: Sequence[Mapping[str, object]] | str,
    prompts: Sequence[Mapping[str, object]],
    *,
    override: bool = False,
    override_source: str = "",
    client: JevClient | None = None,
    verdicts_path: str | None = None,
    log: Callable[[Mapping[str, object]], None] | None = None,
) -> dict[str, object]:
    """Judge prompts before spend. Never call this after a paid step was emitted."""
    if isinstance(holds, str):
        return _result(
            status="BLOCKED",
            authority="NOT_COMPUTABLE",
            code=holds.split()[0],
            blocks=True,
            message=holds,
            holds=[],
            checks=[],
            override=False,
            override_logged=False,
            override_source="",
        )
    if not holds or not prompts:
        code = "NO_HOLDS" if not holds else "NO_SPEND"
        return _result(
            status="PASS",
            authority="PROPOSED",
            code=code,
            blocks=False,
            message="no hold check was required before this step",
            holds=holds,
            checks=[],
            override=False,
            override_logged=False,
            override_source="",
        )
    local = _local_blocks(prompts, holds)
    try:
        judge = resolve_client(verdicts_path, client)
    except JevUnreachable as exc:
        if local:
            return _blocked_hold(holds, local, override, override_source)
        return _unreachable(holds, exc.reason, override, override_source, [], log)
    checks = list(local)
    blocked_shots = {item.get("shot") for item in local}
    judged: list[str] = []
    for prompt in prompts:
        shot = prompt.get("shot")
        if shot in blocked_shots:
            continue
        try:
            verdict = judge.judge(judge_prompt(prompt), holds)
        except JevUnreachable as exc:
            if checks:
                return _blocked_hold(holds, checks, override, override_source)
            return _unreachable(holds, exc.reason, override, override_source, judged, log)
        judged.append(str(shot or ""))
        text = prompt.get("prompt")
        raw_findings = verdict.get("findings")
        findings = list(raw_findings) if isinstance(raw_findings, list) else []
        checks.append({
            "shot": prompt.get("shot"),
            "channel": prompt.get("channel"),
            "location": prompt.get("location"),
            "prompt_sha256": prompt_sha256(text if isinstance(text, str) else ""),
            "verdict": verdict.get("verdict"),
            "findings": findings,
        })
    failed = [item for item in checks if item.get("verdict") == "fail"]
    if failed:
        return _blocked_hold(holds, failed, override, override_source)
    return _result(
        status="PASS",
        authority="PROPOSED",
        code="CLEAR",
        blocks=False,
        message="Jev passed every prompt against the hold list",
        holds=holds,
        checks=checks,
        override=False,
        override_logged=False,
        override_source="",
    )


def _blocked_hold(
    holds: Sequence[Mapping[str, object]],
    checks: Sequence[Mapping[str, object]],
    override: bool,
    override_source: str,
) -> dict[str, object]:
    message = _check_message(checks)
    if override:
        message = f"{message}; operator override does not bypass a hold hit"
    return _result(
        status="BLOCKED",
        authority="NOT_COMPUTABLE",
        code="JEV_HOLD",
        blocks=True,
        message=message,
        holds=holds,
        checks=checks,
        override=False,
        override_logged=False,
        override_source=override_source if override else "",
    )


def _unreachable(
    holds: Sequence[Mapping[str, object]],
    reason: str,
    override: bool,
    override_source: str,
    judged: Sequence[str],
    log: Callable[[Mapping[str, object]], None] | None,
) -> dict[str, object]:
    if override:
        record: dict[str, object] = {
            "event": "JEV_OVERRIDE",
            "source": override_source or "flag",
            "reason": "JEV_UNREACHABLE",
            "detail": reason,
            "shots_judged": list(judged),
        }
        if log is None:
            log_override(record)
        else:
            log(record)
        return _result(
            status="PASS",
            authority="PROPOSED",
            code="JEV_OVERRIDE",
            blocks=False,
            message=f"Jev is unreachable ({reason}); operator override allowed the spend",
            holds=holds,
            checks=[],
            override=True,
            override_logged=True,
            override_source=override_source or "flag",
        )
    return _result(
        status="BLOCKED",
        authority="NOT_COMPUTABLE",
        code="JEV_UNREACHABLE",
        blocks=True,
        message=f"Jev is unreachable: {reason}",
        holds=holds,
        checks=[],
        override=False,
        override_logged=False,
        override_source="",
    )


def ledger_entry(gate: Mapping[str, object]) -> dict[str, object]:
    return {
        "kind": "jev_gate",
        "checked_before_spend": True,
        "result": dict(gate),
    }


def append_run_ledger(path: str, entry: Mapping[str, object]) -> None:
    """Append one gate entry. A corrupt ledger fails closed instead of being replaced."""
    from io_safety import load_structured, write_structured

    try:
        raw = load_structured(path)
    except OSError:
        raw = {"entries": []}
    except ValueError as exc:
        raise ValueError(f"LEDGER_INVALID {exc}") from exc
    if not isinstance(raw, Mapping):
        raise ValueError("LEDGER_INVALID run ledger must be an object")
    entries = raw.get("entries")
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        raise ValueError("LEDGER_INVALID run ledger entries must be a list")
    updated = dict(raw)
    updated["entries"] = [*entries, dict(entry)]
    try:
        write_structured(path, updated)
    except OSError as exc:
        raise ValueError(f"LEDGER_WRITE_FAILED {exc}") from exc


def attach_gate(
    payload: dict[str, object],
    gate: Mapping[str, object],
    ledger_path: str | None,
) -> str | None:
    """Write the gate onto the payload and, when asked, the run ledger file."""
    entry = ledger_entry(gate)
    payload["jev_gate"] = dict(gate)
    payload["run_ledger"] = [entry]
    if not ledger_path:
        return None
    try:
        append_run_ledger(ledger_path, entry)
    except ValueError as exc:
        return str(exc)
    return None


def gate_prompts(
    document: Mapping[str, object],
    prompts: Sequence[Mapping[str, object]] | str,
    *,
    override: bool = False,
    override_source: str = "",
    client: JevClient | None = None,
    verdicts_path: str | None = None,
    log: Callable[[Mapping[str, object]], None] | None = None,
) -> dict[str, object]:
    """Hold list from ``document``, then the pre-spend check."""
    if isinstance(prompts, str):
        return check_before_spend(
            prompts,
            [],
            override=override,
            override_source=override_source,
        )
    holds = hold_list(document)
    return check_before_spend(
        holds,
        prompts,
        override=override,
        override_source=override_source,
        client=client,
        verdicts_path=verdicts_path,
        log=log,
    )
