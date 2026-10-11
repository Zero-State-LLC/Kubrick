from __future__ import annotations

import datetime as dt
import json
import stat
import sys
import uuid
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import kubrick.runtime.telemetry as telemetry  # noqa: E402
import kubrick.runtime.telemetry_cli as telemetry_cli  # noqa: E402
import kubrick.runtime.telemetry_store as telemetry_store  # noqa: E402
from kubrick.paths import telemetry_state_dir  # noqa: E402
from kubrick.runtime.manifest_contract import load_manifest  # noqa: E402
from kubrick.runtime.telemetry import (  # noqa: E402
    TelemetryError,
    acknowledge_events,
    build_quality_feedback_event,
    build_usage_event,
    flush_pending_events,
    get_consent,
    pending_events,
    queue_event,
    set_consent,
    validate_event,
)  # noqa: E402


def test_build_usage_event_uses_allowlisted_coarse_fields() -> None:
    event = build_usage_event(
        intent="compile",
        action="run",
        return_code=4,
        duration_seconds=0.2,
        kubrick_version="0.27.15",
        allowed_actions={"compile": {"run"}},
        now=dt.datetime(2026, 10, 10, 12, 0, tzinfo=dt.timezone.utc),
    )

    assert set(event) == {
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
    assert event["schema_version"] == "1"
    assert uuid.UUID(str(event["event_id"])).version == 4
    assert event["event_day"] == "2026-10-10"
    assert dt.date.fromisoformat(str(event["event_day"]))
    assert event["event_type"] == "usage"
    assert event["intent"] == "compile"
    assert event["action"] == "run"
    assert event["result"] == "not_computable"
    assert event["reason_code"] == "EXIT_CODE_4_NOT_COMPUTABLE"
    assert event["duration_bucket"] == "100_499ms"
    assert event["pattern_id"] is None
    assert event["user_vote"] is None
    assert not ({"argv", "path", "project_id", "raw_prompt", "exception"} & set(event))


def test_validate_event_rejects_extra_private_fields_without_echoing_them() -> None:
    event = build_usage_event(
        intent="compile",
        action="run",
        return_code=0,
        duration_seconds=0.3,
        kubrick_version="0.27.15",
        allowed_actions={"compile": {"run"}},
    )
    event["project_id"] = "private-project-42"

    with pytest.raises(TelemetryError) as error:
        validate_event(event, allowed_actions={"compile": {"run"}})

    assert str(error.value) == "EVENT_FIELDS_INVALID"
    assert "private-project-42" not in str(error.value)


def test_usage_event_schema_is_registered_and_accepts_built_event() -> None:
    schema_path = ROOT / "schemas" / "usage-telemetry-event-v1.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)

    manifest = load_manifest()
    assert "schemas/usage-telemetry-event-v1.schema.json" in manifest["schemas"]
    event = build_usage_event(
        intent="compile",
        action="run",
        return_code=0,
        duration_seconds=0.3,
        kubrick_version=manifest["version"],
        allowed_actions={"compile": {"run"}},
    )
    Draft202012Validator(schema).validate(event)


def test_validate_event_rejects_wrong_scalar_types_as_telemetry_errors() -> None:
    event = build_usage_event(
        intent="compile",
        action="run",
        return_code=0,
        duration_seconds=0.3,
        kubrick_version="0.27.15",
        allowed_actions={"compile": {"run"}},
    )
    event["platform"] = []

    with pytest.raises(TelemetryError):
        validate_event(event, allowed_actions={"compile": {"run"}})


def test_unmapped_process_exit_code_is_coarsened_to_a_fixed_reason() -> None:
    event = build_usage_event(
        intent="compile",
        action="run",
        return_code=73,
        duration_seconds=0.3,
        kubrick_version="0.27.15",
        allowed_actions={"compile": {"run"}},
    )
    assert event["result"] == "failure"
    assert event["reason_code"] == "EXIT_CODE_OTHER"
    assert not {"return_code", "exit_code", "process_exit_code"} & event.keys()


def test_telemetry_state_dir_uses_platform_user_state_locations() -> None:
    home = Path("/home/test-user")
    assert telemetry_state_dir(
        platform="linux", environ={"XDG_STATE_HOME": "/state"}, home=home
    ) == Path("/state/kubrick/telemetry")
    assert telemetry_state_dir(platform="darwin", environ={}, home=home) == Path(
        "/home/test-user/Library/Application Support/Kubrick/telemetry"
    )
    assert telemetry_state_dir(
        platform="win32", environ={"LOCALAPPDATA": "C:/Users/test/AppData/Local"}, home=home
    ) == Path("C:/Users/test/AppData/Local/Kubrick/telemetry")


def test_consent_defaults_off_and_scopes_persist_separately(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    assert get_consent(state_dir) == frozenset()
    assert not state_dir.exists()

    set_consent(state_dir, {"usage"})
    assert get_consent(state_dir) == frozenset({"usage"})

    set_consent(state_dir, {"usage", "quality_feedback"})
    assert get_consent(state_dir) == frozenset({"usage", "quality_feedback"})

    set_consent(state_dir, set())
    assert get_consent(state_dir) == frozenset()


def test_consent_rejects_unknown_scope(tmp_path: Path) -> None:
    with pytest.raises(TelemetryError, match="CONSENT_SCOPE_INVALID"):
        set_consent(tmp_path / "state", {"all-data"})


def test_local_queue_is_opt_in_deduplicated_and_acknowledged(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    event = build_usage_event(
        intent="compile",
        action="run",
        return_code=0,
        duration_seconds=0.3,
        kubrick_version="0.27.15",
        allowed_actions={"compile": {"run"}},
    )
    actions = {"compile": {"run"}}

    assert not queue_event(state_dir, event, allowed_actions=actions)
    assert not state_dir.exists()

    set_consent(state_dir, {"usage"})
    assert queue_event(state_dir, event, allowed_actions=actions)
    assert queue_event(state_dir, event, allowed_actions=actions)
    assert pending_events(state_dir, allowed_actions=actions) == [event]

    acknowledge_events(state_dir, [event["event_id"]])
    assert pending_events(state_dir, allowed_actions=actions) == []


def test_queue_is_bounded_and_consent_revocation_clears_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_dir = tmp_path / "state"
    actions = {"compile": {"run"}}
    set_consent(state_dir, {"usage"})
    monkeypatch.setattr(telemetry_store, "MAX_QUEUE_EVENTS", 1)

    def event() -> dict[str, object]:
        return build_usage_event(
            intent="compile",
            action="run",
            return_code=0,
            duration_seconds=0.3,
            kubrick_version="0.27.15",
            allowed_actions=actions,
        )

    assert queue_event(state_dir, event(), allowed_actions=actions)
    assert not queue_event(state_dir, event(), allowed_actions=actions)
    assert len(pending_events(state_dir, allowed_actions=actions)) == 1

    set_consent(state_dir, set())
    assert pending_events(state_dir, allowed_actions=actions) == []


def test_telemetry_state_files_are_private_on_posix(tmp_path: Path) -> None:
    if sys.platform == "win32":
        pytest.skip("POSIX file modes are not available on Windows")
    state_dir = tmp_path / "state"
    set_consent(state_dir, {"usage"})
    assert stat.S_IMODE(state_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE((state_dir / "telemetry.sqlite3").stat().st_mode) == 0o600


def test_flush_is_disabled_and_rejects_non_https_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("network access occurred without valid telemetry consent and endpoint")

    monkeypatch.setattr(telemetry, "_post_collector", forbidden)
    actions = {"compile": {"run"}}
    state_dir = tmp_path / "state"
    assert (
        flush_pending_events(
            state_dir, "https://collector.example/events", allowed_actions=actions
        ).status
        == "disabled"
    )

    set_consent(state_dir, {"usage"})
    assert (
        flush_pending_events(
            state_dir, "http://collector.example/events", allowed_actions=actions
        ).status
        == "invalid_endpoint"
    )
    handler = telemetry._NoRedirectHandler()
    original = telemetry.urlrequest.Request("https://collector.example/events")
    handler.redirect_request(
        original, object(), 302, "Found", {}, "http://untrusted.example/events"
    )


def test_flush_requires_a_bearer_token_before_network_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_dir = tmp_path / "state"
    actions = {"compile": {"run"}}
    set_consent(state_dir, {"usage"})
    event = build_usage_event(
        intent="compile",
        action="run",
        return_code=0,
        duration_seconds=0.3,
        kubrick_version="0.27.15",
        allowed_actions=actions,
    )
    assert queue_event(state_dir, event, allowed_actions=actions)

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("network access occurred without a bearer token")

    monkeypatch.setattr(telemetry, "_post_collector", forbidden)
    result = flush_pending_events(
        state_dir, "https://collector.example/events", allowed_actions=actions
    )
    assert result.status == "auth_not_configured"
    assert pending_events(state_dir, allowed_actions=actions) == [event]


def test_bearer_tokens_reject_whitespace_and_control_characters() -> None:
    assert telemetry.is_valid_bearer_token("synthetic-test-token")
    for token in (None, "", " leading", "trailing ", "line\nbreak", "control\x00"):
        assert not telemetry.is_valid_bearer_token(token)


def test_failed_flush_keeps_events_queued_without_exposing_network_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actions = {"compile": {"run"}}
    state_dir = tmp_path / "state"
    set_consent(state_dir, {"usage"})
    event = build_usage_event(
        intent="compile",
        action="run",
        return_code=0,
        duration_seconds=0.3,
        kubrick_version="0.27.15",
        allowed_actions=actions,
    )
    assert queue_event(state_dir, event, allowed_actions=actions)

    def fail(*args: object, **kwargs: object) -> None:
        raise telemetry.urlerror.URLError("private server response")

    monkeypatch.setattr(telemetry, "_post_collector", fail)
    result = flush_pending_events(
        state_dir,
        "https://collector.example/events",
        allowed_actions=actions,
        bearer_token="synthetic-test-token",
    )
    assert result.status == "failed"
    assert "private server response" not in repr(result)
    assert pending_events(state_dir, allowed_actions=actions) == [event]


def test_flush_removes_events_only_after_durable_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actions = {"compile": {"run"}}
    state_dir = tmp_path / "state"
    set_consent(state_dir, {"usage"})
    event = build_usage_event(
        intent="compile",
        action="run",
        return_code=0,
        duration_seconds=0.3,
        kubrick_version="0.27.15",
        allowed_actions=actions,
    )
    assert queue_event(state_dir, event, allowed_actions=actions)

    class Accepted:
        status = 202

        def __enter__(self) -> "Accepted":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    captured: dict[str, object] = {}

    def accept(request: object, *, timeout: float) -> Accepted:
        captured["request"] = request
        captured["timeout"] = timeout
        return Accepted()

    monkeypatch.setattr(telemetry, "_post_collector", accept)
    result = flush_pending_events(
        state_dir,
        "https://collector.example/events",
        allowed_actions=actions,
        bearer_token="synthetic-test-token",
    )
    request = captured["request"]
    assert isinstance(request, telemetry.urlrequest.Request)
    assert isinstance(request.data, bytes)
    body = json.loads(request.data)
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer synthetic-test-token"
    assert request.get_header("User-agent") == "KubrickTelemetry/1"
    timeout = captured["timeout"]
    assert isinstance(timeout, (int, float))
    assert timeout <= 1
    assert set(body) == {"schema_version", "events"}
    assert body["events"] == [event]
    assert result.status == "accepted"
    assert result.sent == 1
    assert pending_events(state_dir, allowed_actions=actions) == []


def test_flush_keeps_events_when_collector_does_not_return_202(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actions = {"compile": {"run"}}
    state_dir = tmp_path / "state"
    set_consent(state_dir, {"usage"})
    event = build_usage_event(
        intent="compile",
        action="run",
        return_code=0,
        duration_seconds=0.3,
        kubrick_version="0.27.15",
        allowed_actions=actions,
    )
    assert queue_event(state_dir, event, allowed_actions=actions)

    class NotAccepted:
        status = 200

        def __enter__(self) -> "NotAccepted":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(telemetry, "_post_collector", lambda *args, **kwargs: NotAccepted())
    result = flush_pending_events(
        state_dir,
        "https://collector.example/events",
        allowed_actions=actions,
        bearer_token="synthetic-test-token",
    )
    assert result.status == "failed"
    assert result.sent == 0
    assert pending_events(state_dir, allowed_actions=actions) == [event]


def test_quality_feedback_is_separately_opted_in_and_schema_valid(tmp_path: Path) -> None:
    pattern_ids = {"alchemical_separation_signal_from_noise"}
    actions = {"telemetry": {"feedback"}}
    event = build_quality_feedback_event(
        pattern_id="alchemical_separation_signal_from_noise",
        user_vote="useful",
        kubrick_version="0.27.15",
        allowed_pattern_ids=pattern_ids,
        allowed_actions=actions,
        now=dt.datetime(2026, 10, 11, tzinfo=dt.timezone.utc),
    )
    schema = json.loads(
        (ROOT / "schemas" / "usage-telemetry-event-v1.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(event)
    assert event["result"] is None
    assert event["duration_bucket"] is None

    state_dir = tmp_path / "state"
    assert not queue_event(
        state_dir,
        event,
        allowed_actions=actions,
        allowed_pattern_ids=pattern_ids,
    )
    set_consent(state_dir, {"quality_feedback"})
    assert queue_event(
        state_dir,
        event,
        allowed_actions=actions,
        allowed_pattern_ids=pattern_ids,
    )
    assert pending_events(
        state_dir,
        allowed_actions=actions,
        allowed_pattern_ids=pattern_ids,
    ) == [event]

    set_consent(state_dir, {"usage"})
    assert (
        pending_events(
            state_dir,
            allowed_actions=actions,
            allowed_pattern_ids=pattern_ids,
        )
        == []
    )


def test_telemetry_cli_consent_controls_do_not_reveal_endpoint_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    state_dir = tmp_path / "state"
    monkeypatch.setattr(telemetry_cli, "telemetry_state_dir", lambda: state_dir)
    monkeypatch.setenv(
        "KUBRICK_TELEMETRY_ENDPOINT", "https://collector.example/events?token=private"
    )
    monkeypatch.setenv("KUBRICK_TELEMETRY_TOKEN", "private-token-never-print")

    assert telemetry_cli.main(["--action", "status"]) == 0
    status_output = capsys.readouterr().out
    status = json.loads(status_output)
    assert status["consent"] == []
    assert not status["endpoint_configured"]
    assert status["authentication_configured"]
    assert "private" not in status_output

    assert telemetry_cli.main(["--action", "enable", "--scope", "usage"]) == 0
    assert get_consent(state_dir) == frozenset({"usage"})
    assert telemetry_cli.main(["--action", "disable"]) == 0
    assert get_consent(state_dir) == frozenset()
