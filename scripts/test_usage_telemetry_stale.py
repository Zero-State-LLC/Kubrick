from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from kubrick.runtime.telemetry import (  # noqa: E402
    build_usage_event,
    pending_event_count,
    pending_events,
    queue_event,
    set_consent,
)


def test_incompatible_queued_event_is_discarded_without_blocking_later_events(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / "state"
    set_consent(state_dir, {"usage"})
    first_actions = {"removed_intent": {"run"}}
    stale = build_usage_event(
        intent="removed_intent",
        action="run",
        return_code=0,
        duration_seconds=0.3,
        kubrick_version="0.27.14",
        allowed_actions=first_actions,
    )
    assert queue_event(state_dir, stale, allowed_actions=first_actions)
    current_actions = {"compile": {"run"}}
    current = build_usage_event(
        intent="compile",
        action="run",
        return_code=0,
        duration_seconds=0.3,
        kubrick_version="0.27.15",
        allowed_actions=current_actions,
    )
    assert queue_event(state_dir, current, allowed_actions=current_actions)

    with sqlite3.connect(state_dir / "telemetry.sqlite3") as connection:
        rows = connection.execute(
            "SELECT sequence, payload FROM pending_event ORDER BY sequence"
        ).fetchall()
        stale_payload = json.loads(rows[0][1])
        stale_payload["intent"] = "removed_intent"
        connection.execute(
            "UPDATE pending_event SET payload = ? WHERE sequence = ?",
            (json.dumps(stale_payload, separators=(",", ":"), sort_keys=True), rows[0][0]),
        )

    assert pending_events(state_dir, allowed_actions=current_actions) == [current]
    assert pending_event_count(state_dir) == 1
