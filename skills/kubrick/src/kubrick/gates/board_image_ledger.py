#!/usr/bin/env python3
"""Opt-out and run-ledger helpers for the board image gate."""
from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from typing import TextIO


def opt_out_requested(reason: str | None) -> tuple[bool, str, str]:
    """``(requested, reason, source)``. The flag wins over ``KUBRICK_BOARD_IMAGE_OPT_OUT``."""
    if reason is not None:
        return True, reason.strip(), "flag"
    raw = os.environ.get("KUBRICK_BOARD_IMAGE_OPT_OUT")
    if raw is not None and raw.strip():
        return True, raw.strip(), "env"
    return False, "", ""


def log_opt_out(record: Mapping[str, object], sink: TextIO | None = None) -> None:
    """One stderr line. ``sink`` is for tests."""
    line = "BOARD_IMAGE_OPT_OUT " + json.dumps(record, sort_keys=True)
    print(line, file=sys.stderr if sink is None else sink)


def ledger_entry(gate: Mapping[str, object]) -> dict[str, object]:
    return {"kind": "board_image_gate", "checked_before_spend": True, "result": dict(gate)}


def attach_board_gate(
    payload: dict[str, object], gate: Mapping[str, object], ledger_path: str | None,
) -> str | None:
    """Write the gate onto the payload, add a run-ledger entry, and append it to the file."""
    from kubrick.gates.jev_gate import append_run_ledger

    entry = ledger_entry(gate)
    payload["board_image_gate"] = dict(gate)
    existing = payload.get("run_ledger")
    rows = list(existing) if isinstance(existing, list) else []
    payload["run_ledger"] = [*rows, entry]
    if not ledger_path:
        return None
    try:
        append_run_ledger(ledger_path, entry)
    except ValueError as exc:
        return str(exc)
    return None
