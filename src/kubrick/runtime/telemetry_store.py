"""Local consent and bounded telemetry outbox persistence."""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Any

from .telemetry_events import UUID_V4_RE, TelemetryError, validate_event

CONSENT_SCOPES = frozenset({"usage", "quality_feedback"})


_STATE_DB = "telemetry.sqlite3"


MAX_QUEUE_EVENTS = 500


MAX_QUEUE_BYTES = 1_048_576


MAX_EVENT_BYTES = 4_096


MAX_BATCH_EVENTS = 20


MAX_BATCH_BYTES = 32_768


def _state_connection(state_dir: Path, *, create: bool) -> sqlite3.Connection | None:
    state_dir = Path(state_dir)
    db_path = state_dir / _STATE_DB
    if not create and not db_path.exists():
        return None
    if state_dir.is_symlink() or db_path.is_symlink():
        raise TelemetryError("STATE_PATH_UNSAFE")
    try:
        if create:
            state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            if os.name != "nt":
                os.chmod(state_dir, 0o700)
            if not db_path.exists():
                try:
                    descriptor = os.open(
                        db_path,
                        os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                        0o600,
                    )
                except FileExistsError:
                    pass
                else:
                    os.close(descriptor)
            if db_path.is_symlink():
                raise TelemetryError("STATE_PATH_UNSAFE")
            if os.name != "nt":
                os.chmod(db_path, 0o600)
        elif not db_path.is_file():
            return None
        connection = sqlite3.connect(db_path, timeout=1.0)
        connection.execute("CREATE TABLE IF NOT EXISTS consent (scope TEXT PRIMARY KEY)")
        connection.execute(
            """CREATE TABLE IF NOT EXISTS pending_event (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                payload_bytes INTEGER NOT NULL
            )"""
        )
        return connection
    except (OSError, sqlite3.Error) as exc:
        raise TelemetryError("STATE_UNAVAILABLE") from exc


def get_consent(state_dir: Path) -> frozenset[str]:
    """Return persisted telemetry scopes; an absent state is opt-out."""
    connection = _state_connection(state_dir, create=False)
    if connection is None:
        return frozenset()
    try:
        scopes = frozenset(row[0] for row in connection.execute("SELECT scope FROM consent"))
        if not scopes <= CONSENT_SCOPES:
            raise TelemetryError("STATE_INVALID")
        return scopes
    except sqlite3.Error as exc:
        raise TelemetryError("STATE_UNREADABLE") from exc
    finally:
        connection.close()


def set_consent(state_dir: Path, scopes: Collection[str]) -> None:
    """Persist explicit scopes and discard pending events no longer consented to."""
    if not isinstance(scopes, Collection) or isinstance(scopes, (str, bytes)):
        raise TelemetryError("CONSENT_SCOPE_INVALID")
    try:
        selected = frozenset(scopes)
    except TypeError:
        raise TelemetryError("CONSENT_SCOPE_INVALID") from None
    if any(not isinstance(scope, str) for scope in selected) or not selected <= CONSENT_SCOPES:
        raise TelemetryError("CONSENT_SCOPE_INVALID")
    connection = _state_connection(state_dir, create=True)
    assert connection is not None
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM consent")
        connection.executemany("INSERT INTO consent(scope) VALUES (?)", [(s,) for s in selected])
        if selected == CONSENT_SCOPES:
            pass
        elif "usage" in selected:
            connection.execute("DELETE FROM pending_event WHERE event_type != 'usage'")
        elif "quality_feedback" in selected:
            connection.execute("DELETE FROM pending_event WHERE event_type != 'quality_feedback'")
        else:
            connection.execute("DELETE FROM pending_event")
        connection.commit()
    except sqlite3.Error as exc:
        connection.rollback()
        raise TelemetryError("STATE_UNAVAILABLE") from exc
    finally:
        connection.close()


def queue_event(
    state_dir: Path,
    event: Mapping[str, Any],
    *,
    allowed_actions: Mapping[str, Collection[str]],
    allowed_pattern_ids: Collection[str] = (),
) -> bool:
    """Validate and durably queue one event only when its scope is enabled."""
    scopes = get_consent(state_dir)
    event_type = event.get("event_type")
    scope = event_type if isinstance(event_type, str) and event_type in CONSENT_SCOPES else None
    if scope is None or scope not in scopes:
        return False
    validated = validate_event(
        event,
        allowed_actions=allowed_actions,
        allowed_pattern_ids=allowed_pattern_ids,
        feedback_enabled="quality_feedback" in scopes,
    )
    payload = json.dumps(validated, separators=(",", ":"), sort_keys=True)
    payload_bytes = len(payload.encode("utf-8"))
    if payload_bytes > MAX_EVENT_BYTES:
        raise TelemetryError("EVENT_TOO_LARGE")

    connection = _state_connection(state_dir, create=True)
    assert connection is not None
    try:
        connection.execute("BEGIN IMMEDIATE")
        current_scopes = frozenset(
            row[0] for row in connection.execute("SELECT scope FROM consent")
        )
        if scope not in current_scopes:
            connection.rollback()
            return False
        duplicate = connection.execute(
            "SELECT payload FROM pending_event WHERE event_id = ?",
            (validated["event_id"],),
        ).fetchone()
        if duplicate is not None:
            if duplicate[0] != payload:
                raise TelemetryError("EVENT_ID_COLLISION")
            connection.commit()
            return True
        count, size = connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(payload_bytes), 0) FROM pending_event"
        ).fetchone()
        if count >= MAX_QUEUE_EVENTS or size + payload_bytes > MAX_QUEUE_BYTES:
            connection.commit()
            return False
        connection.execute(
            """INSERT INTO pending_event(event_id, event_type, payload, payload_bytes)
               VALUES (?, ?, ?, ?)""",
            (validated["event_id"], event_type, payload, payload_bytes),
        )
        connection.commit()
        return True
    except TelemetryError:
        connection.rollback()
        raise
    except sqlite3.Error as exc:
        connection.rollback()
        raise TelemetryError("STATE_UNAVAILABLE") from exc
    finally:
        connection.close()


def pending_events(
    state_dir: Path,
    *,
    allowed_actions: Mapping[str, Collection[str]],
    allowed_pattern_ids: Collection[str] = (),
) -> list[dict[str, Any]]:
    """Read a bounded, revalidated batch from the local queue."""
    scopes = get_consent(state_dir)
    if not scopes:
        return []
    connection = _state_connection(state_dir, create=False)
    if connection is None:
        return []
    events: list[dict[str, Any]] = []
    try:
        rows = connection.execute("SELECT event_type, payload FROM pending_event ORDER BY sequence")
        for event_type, payload in rows:
            if event_type not in scopes:
                continue
            try:
                candidate = json.loads(payload)
            except (TypeError, json.JSONDecodeError) as exc:
                raise TelemetryError("OUTBOX_CORRUPT") from exc
            validated = validate_event(
                candidate,
                allowed_actions=allowed_actions,
                allowed_pattern_ids=allowed_pattern_ids,
                feedback_enabled="quality_feedback" in scopes,
            )
            if validated["event_type"] != event_type:
                raise TelemetryError("OUTBOX_CORRUPT")
            next_events = [*events, validated]
            batch = {"schema_version": "1", "events": next_events}
            batch_bytes = len(
                json.dumps(batch, separators=(",", ":"), sort_keys=True).encode("utf-8")
            )
            if len(events) >= MAX_BATCH_EVENTS or batch_bytes > MAX_BATCH_BYTES:
                break
            events.append(validated)
        return events
    except sqlite3.Error as exc:
        raise TelemetryError("STATE_UNREADABLE") from exc
    finally:
        connection.close()


def pending_event_count(state_dir: Path) -> int:
    """Return the local queue size without reading or exposing event payloads."""
    connection = _state_connection(state_dir, create=False)
    if connection is None:
        return 0
    try:
        row = connection.execute("SELECT COUNT(*) FROM pending_event").fetchone()
        return int(row[0])
    except sqlite3.Error as exc:
        raise TelemetryError("STATE_UNREADABLE") from exc
    finally:
        connection.close()


def acknowledge_events(state_dir: Path, event_ids: Collection[str]) -> None:
    """Remove only the acknowledged event IDs, preserving concurrent additions."""
    if isinstance(event_ids, (str, bytes)):
        raise TelemetryError("EVENT_IDS_INVALID")
    values = list(event_ids)
    if any(not isinstance(event_id, str) for event_id in values):
        raise TelemetryError("EVENT_IDS_INVALID")
    selected = list(dict.fromkeys(values))
    if len(selected) > MAX_BATCH_EVENTS or any(
        UUID_V4_RE.fullmatch(event_id) is None for event_id in selected
    ):
        raise TelemetryError("EVENT_IDS_INVALID")
    connection = _state_connection(state_dir, create=False)
    if connection is None:
        return
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.executemany(
            "DELETE FROM pending_event WHERE event_id = ?",
            [(event_id,) for event_id in selected],
        )
        connection.commit()
    except sqlite3.Error as exc:
        connection.rollback()
        raise TelemetryError("STATE_UNAVAILABLE") from exc
    finally:
        connection.close()
