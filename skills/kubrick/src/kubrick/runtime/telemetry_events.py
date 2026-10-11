"""Versioned Kubrick telemetry event contract and privacy validation."""

from __future__ import annotations

import datetime as dt
import math
import re
import sys
import uuid
from collections.abc import Collection, Mapping
from typing import Any

EVENT_FIELDS = frozenset(
    {
        "schema_version",
        "event_id",
        "event_day",
        "kubrick_version",
        "python_minor",
        "platform",
        "event_type",
        "intent",
        "action",
        "result",
        "reason_code",
        "duration_bucket",
        "pattern_id",
        "user_vote",
    }
)


EXIT_RESULTS: dict[int, tuple[str, str | None]] = {
    0: ("success", None),
    1: ("failure", "EXIT_CODE_1_VALIDATION_OR_EXECUTION_FAILURE"),
    2: ("failure", "EXIT_CODE_2_INVALID_COMMAND_OR_ARGUMENTS"),
    3: ("failure", "EXIT_CODE_3_OPTIONAL_DEPENDENCY_UNAVAILABLE"),
    4: ("not_computable", "EXIT_CODE_4_NOT_COMPUTABLE"),
}


OTHER_EXIT_RESULT = ("failure", "EXIT_CODE_OTHER")


_EVENT_SLUG = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


UUID_V4_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


_PATTERN_ID = re.compile(r"^[a-z0-9_]{1,96}$")


class TelemetryError(ValueError):
    """A telemetry event cannot be safely represented by the v1 contract."""


def _duration_bucket(seconds: float) -> str:
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        raise TelemetryError("DURATION_INVALID")
    value = float(seconds)
    if not math.isfinite(value) or value < 0:
        raise TelemetryError("DURATION_INVALID")
    if value < 0.1:
        return "lt_100ms"
    if value < 0.5:
        return "100_499ms"
    if value < 2:
        return "500_1999ms"
    if value <= 10:
        return "2_10s"
    return "gt_10s"


def _platform_family() -> str:
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform == "win32":
        return "windows"
    return "other"


def build_usage_event(
    *,
    intent: str,
    action: str,
    return_code: int,
    duration_seconds: float,
    kubrick_version: str,
    allowed_actions: Mapping[str, Collection[str]],
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Build an event exclusively from coarse, allowlisted runtime values."""
    if not isinstance(intent, str) or not isinstance(action, str):
        raise TelemetryError("INTENT_ACTION_INVALID")
    if not _EVENT_SLUG.fullmatch(intent) or not _EVENT_SLUG.fullmatch(action):
        raise TelemetryError("INTENT_ACTION_INVALID")
    if intent not in allowed_actions or action not in allowed_actions[intent]:
        raise TelemetryError("INTENT_ACTION_NOT_ALLOWED")
    if isinstance(return_code, bool) or not isinstance(return_code, int):
        raise TelemetryError("EXIT_CODE_INVALID")
    if not isinstance(kubrick_version, str) or not kubrick_version or len(kubrick_version) > 32:
        raise TelemetryError("VERSION_INVALID")

    timestamp = now or dt.datetime.now(dt.timezone.utc)
    if (
        not isinstance(timestamp, dt.datetime)
        or timestamp.tzinfo is None
        or timestamp.utcoffset() is None
    ):
        raise TelemetryError("TIMESTAMP_NOT_TIMEZONE_AWARE")
    utc_day = timestamp.astimezone(dt.timezone.utc).date().isoformat()
    result, reason_code = EXIT_RESULTS.get(return_code, OTHER_EXIT_RESULT)
    return {
        "schema_version": "1",
        "event_id": str(uuid.uuid4()),
        "event_day": utc_day,
        "kubrick_version": kubrick_version,
        "python_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
        "platform": _platform_family(),
        "event_type": "usage",
        "intent": intent,
        "action": action,
        "result": result,
        "reason_code": reason_code,
        "duration_bucket": _duration_bucket(duration_seconds),
        "pattern_id": None,
        "user_vote": None,
    }


def build_quality_feedback_event(
    *,
    pattern_id: str,
    user_vote: str,
    kubrick_version: str,
    allowed_pattern_ids: Collection[str],
    allowed_actions: Mapping[str, Collection[str]],
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Build an explicit, pattern-scoped vote without free-text feedback."""
    if (
        not isinstance(pattern_id, str)
        or not _PATTERN_ID.fullmatch(pattern_id)
        or pattern_id not in allowed_pattern_ids
    ):
        raise TelemetryError("PATTERN_ID_NOT_ALLOWED")
    if not isinstance(user_vote, str) or user_vote not in {"useful", "mixed", "not_useful"}:
        raise TelemetryError("USER_VOTE_INVALID")
    if not isinstance(kubrick_version, str) or not re.fullmatch(
        r"[0-9]+\.[0-9]+\.[0-9]+", kubrick_version
    ):
        raise TelemetryError("VERSION_INVALID")
    if "telemetry" not in allowed_actions or "feedback" not in allowed_actions["telemetry"]:
        raise TelemetryError("INTENT_ACTION_NOT_ALLOWED")
    timestamp = now or dt.datetime.now(dt.timezone.utc)
    if (
        not isinstance(timestamp, dt.datetime)
        or timestamp.tzinfo is None
        or timestamp.utcoffset() is None
    ):
        raise TelemetryError("TIMESTAMP_NOT_TIMEZONE_AWARE")
    event = {
        "schema_version": "1",
        "event_id": str(uuid.uuid4()),
        "event_day": timestamp.astimezone(dt.timezone.utc).date().isoformat(),
        "kubrick_version": kubrick_version,
        "python_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
        "platform": _platform_family(),
        "event_type": "quality_feedback",
        "intent": "telemetry",
        "action": "feedback",
        "result": None,
        "reason_code": None,
        "duration_bucket": None,
        "pattern_id": pattern_id,
        "user_vote": user_vote,
    }
    return validate_event(
        event,
        allowed_actions=allowed_actions,
        allowed_pattern_ids=allowed_pattern_ids,
        feedback_enabled=True,
    )


def validate_event(
    event: object,
    *,
    allowed_actions: Mapping[str, Collection[str]],
    allowed_pattern_ids: Collection[str] = (),
    feedback_enabled: bool = False,
) -> dict[str, Any]:
    """Validate an event at the client/network boundary without echoing input."""
    if not isinstance(event, dict) or set(event) != EVENT_FIELDS:
        raise TelemetryError("EVENT_FIELDS_INVALID")

    if event["schema_version"] != "1":
        raise TelemetryError("SCHEMA_VERSION_INVALID")
    event_id = event["event_id"]
    if not isinstance(event_id, str) or len(event_id) != 36:
        raise TelemetryError("EVENT_ID_INVALID")
    try:
        parsed_id = uuid.UUID(event_id)
    except (ValueError, AttributeError):
        raise TelemetryError("EVENT_ID_INVALID") from None
    if parsed_id.version != 4 or str(parsed_id) != event_id:
        raise TelemetryError("EVENT_ID_INVALID")

    event_day = event["event_day"]
    if not isinstance(event_day, str) or len(event_day) != 10:
        raise TelemetryError("EVENT_DAY_INVALID")
    try:
        parsed_day = dt.date.fromisoformat(event_day)
    except ValueError:
        raise TelemetryError("EVENT_DAY_INVALID") from None
    if parsed_day.isoformat() != event_day:
        raise TelemetryError("EVENT_DAY_INVALID")

    version = event["kubrick_version"]
    if (
        not isinstance(version, str)
        or len(version) > 32
        or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version)
    ):
        raise TelemetryError("VERSION_INVALID")
    python_minor = event["python_minor"]
    if not isinstance(python_minor, str) or not re.fullmatch(r"3\.[0-9]{1,2}", python_minor):
        raise TelemetryError("PYTHON_VERSION_INVALID")
    platform = event["platform"]
    if not isinstance(platform, str) or platform not in {"linux", "macos", "windows", "other"}:
        raise TelemetryError("PLATFORM_INVALID")

    event_type = event["event_type"]
    if not isinstance(event_type, str) or event_type not in {"usage", "quality_feedback"}:
        raise TelemetryError("EVENT_TYPE_INVALID")
    intent, action = event["intent"], event["action"]
    if (
        not isinstance(intent, str)
        or not isinstance(action, str)
        or not _EVENT_SLUG.fullmatch(intent)
        or not _EVENT_SLUG.fullmatch(action)
        or intent not in allowed_actions
        or action not in allowed_actions[intent]
    ):
        raise TelemetryError("INTENT_ACTION_NOT_ALLOWED")

    result = event["result"]
    reason_code = event["reason_code"]
    if reason_code is not None and not isinstance(reason_code, str):
        raise TelemetryError("REASON_CODE_INVALID")
    if event_type == "usage":
        if result == "success":
            valid_reason_codes = {None}
        elif result == "failure":
            valid_reason_codes = {code[1] for code in EXIT_RESULTS.values() if code[0] == "failure"}
            valid_reason_codes.add(OTHER_EXIT_RESULT[1])
        elif result == "not_computable":
            valid_reason_codes = {EXIT_RESULTS[4][1]}
        else:
            raise TelemetryError("RESULT_INVALID")
        if reason_code not in valid_reason_codes:
            raise TelemetryError("REASON_CODE_INVALID")
    else:
        if result is not None:
            raise TelemetryError("RESULT_INVALID")
        if reason_code is not None:
            raise TelemetryError("REASON_CODE_INVALID")

    duration_bucket = event["duration_bucket"]
    if event_type == "usage":
        if not isinstance(duration_bucket, str) or duration_bucket not in {
            "lt_100ms",
            "100_499ms",
            "500_1999ms",
            "2_10s",
            "gt_10s",
        }:
            raise TelemetryError("DURATION_BUCKET_INVALID")
    elif duration_bucket is not None:
        raise TelemetryError("DURATION_BUCKET_INVALID")

    pattern_id, user_vote = event["pattern_id"], event["user_vote"]
    if event_type == "usage":
        if pattern_id is not None or user_vote is not None:
            raise TelemetryError("USAGE_EVENT_HAS_FEEDBACK")
    else:
        if not feedback_enabled:
            raise TelemetryError("FEEDBACK_NOT_ENABLED")
        if not isinstance(pattern_id, str) or pattern_id not in allowed_pattern_ids:
            raise TelemetryError("PATTERN_ID_NOT_ALLOWED")
        if not isinstance(user_vote, str) or user_vote not in {"useful", "mixed", "not_useful"}:
            raise TelemetryError("USER_VOTE_INVALID")

    return {key: event[key] for key in EVENT_FIELDS}
