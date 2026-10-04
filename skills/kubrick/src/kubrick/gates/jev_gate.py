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

from kubrick.gates.hold_scope import holds_for_prompt
from kubrick.gates.jev_client import (
    JevClient,
    JevUnreachable,
    judge_prompt,
    prompt_sha256,
    resolve_client,
)
from kubrick.gates.jev_holds import hold_list

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
        help="JSON file of recorded verdicts keyed by the judged prompt and holds",
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

def _blocked_ids(holds: Sequence[Mapping[str, object]]) -> set[str]:
    return {
        str(item.get("shot"))
        for item in holds
        if item.get("blocked") is True and isinstance(item.get("shot"), str)
    }


def _prompt_labels(prompt: Mapping[str, object]) -> set[str]:
    """Shot id plus aliases such as ``frame_id``. A string of labels is not a list."""
    names: set[str] = set()
    shot = prompt.get("shot")
    if isinstance(shot, str) and shot.strip():
        names.add(shot.strip())
    raw = prompt.get("labels")
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        for item in raw:
            if isinstance(item, str) and item.strip():
                names.add(item.strip())
    return names


def _local_blocks(
    prompts: Sequence[Mapping[str, object]], holds: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    blocked = _blocked_ids(holds)
    checks: list[dict[str, object]] = []
    for prompt in prompts:
        matched = _prompt_labels(prompt) & blocked
        if not matched:
            continue
        shot = prompt.get("shot")
        label = shot.strip() if isinstance(shot, str) and shot.strip() else sorted(matched)[0]
        hold_id = sorted(matched)[0]
        checks.append({
            "shot": label,
            "channel": prompt.get("channel"),
            "prompt_sha256": prompt_sha256(str(prompt.get("prompt") or "")),
            "verdict": "fail",
            "findings": [{
                "code": "BLOCKED_SHOT",
                "hold_id": hold_id,
                "message": f"shot {hold_id} is on the hold list",
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
    blocked = _blocked_ids(holds)
    local = _local_blocks(prompts, holds)
    try:
        judge = resolve_client(verdicts_path, client)
    except JevUnreachable as exc:
        if local:
            return _blocked_hold(holds, local, override, override_source)
        return _unreachable(holds, exc.reason, override, override_source, [], log)
    checks = list(local)
    judged: list[str] = []
    for prompt in prompts:
        shot = prompt.get("shot")
        if _prompt_labels(prompt) & blocked:
            continue
        try:
            verdict = judge.judge(judge_prompt(prompt), holds_for_prompt(holds, prompt))
        except JevUnreachable as exc:
            failed = [item for item in checks if item.get("verdict") == "fail"]
            if failed:
                return _blocked_hold(holds, failed, override, override_source)
            return _unreachable(holds, exc.reason, override, override_source, judged, log)
        judged.append(str(shot or ""))
        text = prompt.get("prompt")
        raw_findings = verdict.get("findings")
        findings = list(raw_findings) if isinstance(raw_findings, list) else []
        check: dict[str, object] = {
            "shot": prompt.get("shot"),
            "channel": prompt.get("channel"),
            "location": prompt.get("location"),
            "prompt_sha256": prompt_sha256(text if isinstance(text, str) else ""),
            "verdict": verdict.get("verdict"),
            "findings": findings,
        }
        raw_results = verdict.get("hold_results")
        if isinstance(raw_results, list):
            check["hold_results"] = raw_results
        checks.append(check)
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


def _hold_texts(document: Mapping[str, object]) -> list[str]:
    holds = hold_list(document)
    if isinstance(holds, str):
        return []
    texts: list[str] = []
    for item in holds:
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            texts.append(text.strip())
    return texts


def _frame_for(document: Mapping[str, object], shot: object) -> Mapping[str, object]:
    from kubrick.plan.continuity_locks import frame_id

    label = shot.strip() if isinstance(shot, str) else ""
    raw = document.get("frames")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return {}
    frames = [frame for frame in raw if isinstance(frame, Mapping)]
    for index, frame in enumerate(frames, start=1):
        if label and label in {frame_id(frame, index), str(frame.get("frame_id") or "")}:
            return frame
    return {}


def _lint_block(
    document: Mapping[str, object],
    prompts: Sequence[Mapping[str, object]],
) -> dict[str, object] | None:
    from kubrick.prompts.prompt_lint import BLOCKING, lint_text

    if not prompts:
        return None
    holds = _hold_texts(document)
    findings: list[dict[str, str]] = []
    for prompt in prompts:
        text = prompt.get("prompt")
        if not isinstance(text, str):
            continue
        frame = _frame_for(document, prompt.get("shot"))
        findings.extend(lint_text(text, holds=holds, frame=frame or None))
    blocking = [item for item in findings if item["code"] in BLOCKING]
    if not blocking:
        return None
    first = blocking[0]
    return _result(
        status="BLOCKED",
        authority="NOT_COMPUTABLE",
        code=first["code"],
        blocks=True,
        message=first["message"],
        holds=[],
        checks=[{"code": item["code"], "message": item["message"]} for item in blocking],
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
    from kubrick.runtime.io_safety import load_structured, write_structured

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
    """Lint the compiled text, then the hold list, before any Jev call."""
    if isinstance(prompts, str):
        return check_before_spend(
            prompts,
            [],
            override=override,
            override_source=override_source,
        )
    blocked = _lint_block(document, prompts)
    if blocked is not None:
        return blocked
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
