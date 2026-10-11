"""Bounded HTTPS telemetry transport and best-effort usage recorder."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from .telemetry_events import (
    EVENT_FIELDS,
    EXIT_RESULTS,
    OTHER_EXIT_RESULT,
    TelemetryError,
    build_quality_feedback_event,
    build_usage_event,
    validate_event,
)
from .telemetry_store import (
    CONSENT_SCOPES,
    MAX_BATCH_BYTES,
    acknowledge_events,
    get_consent,
    pending_event_count,
    pending_events,
    queue_event,
    set_consent,
)

__all__ = [
    "EVENT_FIELDS",
    "EXIT_RESULTS",
    "OTHER_EXIT_RESULT",
    "TelemetryError",
    "build_quality_feedback_event",
    "build_usage_event",
    "validate_event",
    "FlushResult",
    "CONSENT_SCOPES",
    "get_consent",
    "set_consent",
    "queue_event",
    "pending_events",
    "pending_event_count",
    "acknowledge_events",
    "is_valid_https_endpoint",
    "is_valid_bearer_token",
    "flush_pending_events",
    "record_usage_event",
]


@dataclass(frozen=True)
class FlushResult:
    status: str
    sent: int = 0


class _NoRedirectHandler(urlrequest.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def _post_collector(request: urlrequest.Request, *, timeout: float) -> Any:
    opener = urlrequest.build_opener(_NoRedirectHandler())
    return opener.open(request, timeout=timeout)


def is_valid_https_endpoint(endpoint: str | None) -> bool:
    if (
        not isinstance(endpoint, str)
        or not endpoint
        or endpoint.strip() != endpoint
        or any(character.isspace() or ord(character) < 32 for character in endpoint)
    ):
        return False
    try:
        parsed = urlparse.urlsplit(endpoint)
        return bool(
            parsed.scheme == "https"
            and parsed.hostname
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and (parsed.port is None or 1 <= parsed.port <= 65535)
        )
    except ValueError:
        return False


def is_valid_bearer_token(token: str | None) -> bool:
    return bool(
        isinstance(token, str)
        and token
        and len(token) <= 8_192
        and all(33 <= ord(character) <= 126 for character in token)
    )


def flush_pending_events(
    state_dir: Path,
    endpoint: str | None,
    *,
    allowed_actions: Mapping[str, Collection[str]],
    allowed_pattern_ids: Collection[str] = (),
    bearer_token: str | None = None,
) -> FlushResult:
    """POST one bounded batch over HTTPS; retain it unless the collector returns 202."""
    try:
        scopes = get_consent(state_dir)
    except TelemetryError:
        return FlushResult("unavailable")
    if not scopes:
        return FlushResult("disabled")
    if not endpoint:
        return FlushResult("not_configured")
    try:
        if not is_valid_https_endpoint(endpoint):
            return FlushResult("invalid_endpoint")
        if not is_valid_bearer_token(bearer_token):
            return FlushResult("auth_not_configured")
        events = pending_events(
            state_dir,
            allowed_actions=allowed_actions,
            allowed_pattern_ids=allowed_pattern_ids,
        )
        if not events:
            return FlushResult("empty")
        current_scopes = get_consent(state_dir)
        events = [event for event in events if event["event_type"] in current_scopes]
        if not events:
            return FlushResult("disabled")
        payload = json.dumps(
            {"schema_version": "1", "events": events},
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(payload) > MAX_BATCH_BYTES:
            return FlushResult("invalid_batch")
        request = urlrequest.Request(
            endpoint,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {bearer_token}",
                "User-Agent": "KubrickTelemetry/1",
            },
            method="POST",
        )
        with _post_collector(request, timeout=0.5) as response:
            status = getattr(response, "status", None)
            if status is None:
                status = response.getcode()
        if status != 202:
            return FlushResult("failed")
        acknowledge_events(state_dir, [event["event_id"] for event in events])
        return FlushResult("accepted", len(events))
    except (urlerror.URLError, TimeoutError, OSError, ValueError, sqlite3.Error):
        return FlushResult("failed")


def record_usage_event(
    state_dir: Path,
    *,
    intent: str,
    action: str,
    return_code: int,
    duration_seconds: float,
    kubrick_version: str,
    allowed_actions: Mapping[str, Collection[str]],
    endpoint: str | None,
    bearer_token: str | None = None,
) -> FlushResult:
    """Best-effort capture: no state creation, event, or network before opt-in."""
    try:
        if "usage" not in get_consent(state_dir):
            return FlushResult("disabled")
        event = build_usage_event(
            intent=intent,
            action=action,
            return_code=return_code,
            duration_seconds=duration_seconds,
            kubrick_version=kubrick_version,
            allowed_actions=allowed_actions,
        )
        if not queue_event(state_dir, event, allowed_actions=allowed_actions):
            return FlushResult("queue_full_or_consent_changed")
        return flush_pending_events(
            state_dir,
            endpoint,
            allowed_actions=allowed_actions,
            bearer_token=bearer_token,
        )
    except TelemetryError:
        return FlushResult("unavailable")
