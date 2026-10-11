"""Explicit CLI controls for Kubrick's privacy-minimal telemetry client."""

from __future__ import annotations

import argparse
import json
import os
import re
from collections.abc import Sequence
from typing import Any

from kubrick.paths import SKILL_ROOT, telemetry_state_dir
from kubrick.runtime.intent_router import INTENT_REGISTRY, MANIFEST
from kubrick.runtime.telemetry import (
    TelemetryError,
    build_quality_feedback_event,
    flush_pending_events,
    get_consent,
    is_valid_bearer_token,
    is_valid_https_endpoint,
    pending_event_count,
    pending_events,
    queue_event,
    set_consent,
)

_ALLOWED_ACTIONS = {intent: frozenset(spec.actions) for intent, spec in INTENT_REGISTRY.items()}
_PATTERN_ID = re.compile(r"^[a-z0-9_]{1,96}$")
_SCOPE_NAMES = {"usage": "usage", "quality-feedback": "quality_feedback"}


def _pattern_ids() -> frozenset[str]:
    pattern_root = SKILL_ROOT / "references" / "patterns"
    if not pattern_root.is_dir():
        return frozenset()
    found: set[str] = set()
    for path in pattern_root.rglob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        pattern_id = payload.get("pattern_id") if isinstance(payload, dict) else None
        if isinstance(pattern_id, str) and _PATTERN_ID.fullmatch(pattern_id):
            found.add(pattern_id)
    return frozenset(found)


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kubrick telemetry",
        description="Inspect and control opt-in, privacy-minimal Kubrick telemetry.",
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=("status", "enable", "disable", "preview", "flush", "feedback"),
    )
    parser.add_argument("--scope", choices=tuple(_SCOPE_NAMES))
    parser.add_argument("--pattern-id")
    parser.add_argument("--vote", choices=("useful", "mixed", "not_useful"))
    return parser


def _status(state_dir: Any, endpoint: str | None, bearer_token: str | None) -> int:
    try:
        scopes = get_consent(state_dir)
        count = pending_event_count(state_dir)
    except TelemetryError:
        _emit({"status": "state_unavailable"})
        return 1
    _emit(
        {
            "status": "ok",
            "consent": sorted(scopes),
            "endpoint_configured": is_valid_https_endpoint(endpoint),
            "authentication_configured": is_valid_bearer_token(bearer_token),
            "pending_event_count": count,
        }
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    state_dir = telemetry_state_dir()
    endpoint = os.environ.get("KUBRICK_TELEMETRY_ENDPOINT")
    bearer_token = os.environ.get("KUBRICK_TELEMETRY_TOKEN")
    action = args.action

    if action == "status":
        return _status(state_dir, endpoint, bearer_token)

    if action == "enable":
        if not args.scope:
            _emit({"status": "scope_required"})
            return 2
        scope = _SCOPE_NAMES[args.scope]
        try:
            current = get_consent(state_dir)
            set_consent(state_dir, current | {scope})
            enabled_scopes = sorted(get_consent(state_dir))
        except TelemetryError:
            _emit({"status": "state_unavailable"})
            return 1
        notice = (
            "Usage events may include UTC day, Kubrick version, Python minor, OS family, "
            "intent/action, outcome code, and coarse duration; never prompts, files, or paths."
            if scope == "usage"
            else "Feedback includes only a known pattern ID, a fixed vote, UTC day, "
            "Kubrick version, Python minor, and OS family; no free text."
        )
        _emit(
            {
                "status": "enabled",
                "scope": args.scope,
                "consent": enabled_scopes,
                "notice": notice,
                "transmission": (
                    "HTTPS only when KUBRICK_TELEMETRY_ENDPOINT is valid and "
                    "KUBRICK_TELEMETRY_TOKEN is configured"
                ),
            }
        )
        return 0

    if action == "disable":
        try:
            scopes = get_consent(state_dir)
            if args.scope:
                scopes = scopes - {_SCOPE_NAMES[args.scope]}
            else:
                scopes = frozenset()
            set_consent(state_dir, scopes)
            remaining = sorted(get_consent(state_dir))
        except TelemetryError:
            _emit({"status": "state_unavailable"})
            return 1
        _emit({"status": "disabled", "consent": remaining})
        return 0

    if action == "preview":
        try:
            scopes = get_consent(state_dir)
            patterns = _pattern_ids() if "quality_feedback" in scopes else frozenset()
            events = pending_events(
                state_dir,
                allowed_actions=_ALLOWED_ACTIONS,
                allowed_pattern_ids=patterns,
            )
        except TelemetryError:
            _emit({"status": "queue_unavailable", "events": []})
            return 1
        _emit({"status": "ok", "events": events})
        return 0

    if action == "flush":
        try:
            scopes = get_consent(state_dir)
        except TelemetryError:
            _emit({"status": "state_unavailable", "sent": 0})
            return 1
        patterns = _pattern_ids() if "quality_feedback" in scopes else frozenset()
        result = flush_pending_events(
            state_dir,
            endpoint,
            allowed_actions=_ALLOWED_ACTIONS,
            allowed_pattern_ids=patterns,
            bearer_token=bearer_token,
        )
        _emit({"status": result.status, "sent": result.sent})
        return (
            0
            if result.status
            in {"disabled", "not_configured", "auth_not_configured", "empty", "accepted"}
            else 1
        )

    if action == "feedback":
        if not args.pattern_id or not args.vote:
            _emit({"status": "pattern_id_and_vote_required"})
            return 2
        try:
            scopes = get_consent(state_dir)
            if "quality_feedback" not in scopes:
                _emit({"status": "consent_required"})
                return 2
            patterns = _pattern_ids()
            event = build_quality_feedback_event(
                pattern_id=args.pattern_id,
                user_vote=args.vote,
                kubrick_version=MANIFEST["version"],
                allowed_pattern_ids=patterns,
                allowed_actions=_ALLOWED_ACTIONS,
            )
            queued = queue_event(
                state_dir,
                event,
                allowed_actions=_ALLOWED_ACTIONS,
                allowed_pattern_ids=patterns,
            )
        except TelemetryError:
            _emit({"status": "feedback_rejected"})
            return 2
        if not queued:
            _emit({"status": "queue_full_or_consent_changed"})
            return 1
        result = flush_pending_events(
            state_dir,
            endpoint,
            allowed_actions=_ALLOWED_ACTIONS,
            allowed_pattern_ids=patterns,
            bearer_token=bearer_token,
        )
        _emit(
            {
                "status": "sent" if result.status == "accepted" else "queued",
                "flush_status": result.status,
            }
        )
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
