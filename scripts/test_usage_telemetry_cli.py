from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import kubrick.cli as cli  # noqa: E402
import kubrick.runtime.intent_router as intent_router  # noqa: E402
import kubrick.runtime.telemetry as telemetry  # noqa: E402
import kubrick.runtime.telemetry_cli as telemetry_cli  # noqa: E402
from kubrick.runtime.telemetry import get_consent, pending_events, set_consent  # noqa: E402


def test_telemetry_actions_route_to_the_adapter_with_action_forwarded() -> None:
    call = intent_router.resolve(["do", "telemetry", "--action", "status"])
    assert call.script.name == "telemetry.py"
    assert call.action == "status"
    assert cli._execution_argv(call) == ["--action", "status"]
    enable_call = intent_router.resolve(
        ["do", "telemetry", "--action", "enable", "--scope", "usage"]
    )
    assert cli._execution_argv(enable_call) == ["--action", "enable", "--scope", "usage"]
    feedback_call = intent_router.resolve(
        [
            "do",
            "telemetry",
            "--action",
            "feedback",
            "--pattern-id",
            "known_pattern",
            "--vote",
            "useful",
        ]
    )
    assert cli._execution_argv(feedback_call) == [
        "--action",
        "feedback",
        "--pattern-id",
        "known_pattern",
        "--vote",
        "useful",
    ]


def test_child_environment_only_forwards_telemetry_token_to_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = "synthetic-test-token"
    monkeypatch.setenv("KUBRICK_TELEMETRY_TOKEN", token)
    assert "KUBRICK_TELEMETRY_TOKEN" not in cli._child_env()
    assert cli._child_env(include_telemetry_token=True)["KUBRICK_TELEMETRY_TOKEN"] == token


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


def test_pattern_allowlist_uses_only_the_versioned_shipped_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shipped = "shipped_pattern"
    local = "local_only_pattern"
    catalog = tmp_path / "references" / "telemetry-catalogs" / "0.27.15.json"
    catalog.parent.mkdir(parents=True)
    catalog.write_text(
        json.dumps({"kubrick_version": "0.27.15", "pattern_ids": [shipped]}),
        encoding="utf-8",
    )
    local_pattern = tmp_path / "references" / "patterns" / f"{local}.json"
    local_pattern.parent.mkdir(parents=True)
    local_pattern.write_text(json.dumps({"pattern_id": local}), encoding="utf-8")
    monkeypatch.setattr(telemetry_cli, "SKILL_ROOT", tmp_path)
    monkeypatch.setitem(telemetry_cli.MANIFEST, "version", "0.27.15")

    assert telemetry_cli._pattern_ids() == frozenset({shipped})
    monkeypatch.setitem(telemetry_cli.MANIFEST, "version", "0.27.16")
    assert telemetry_cli._pattern_ids() == frozenset()


def test_current_release_catalog_covers_the_shipped_pattern_corpus() -> None:
    corpus_ids = {
        payload["pattern_id"]
        for path in (ROOT / "references" / "patterns").rglob("*.json")
        for payload in [json.loads(path.read_text(encoding="utf-8"))]
        if isinstance(payload, dict) and isinstance(payload.get("pattern_id"), str)
    }

    assert telemetry_cli._pattern_ids() == frozenset(corpus_ids)


def test_telemetry_script_propagates_failure_exit_status(tmp_path: Path) -> None:
    env = dict(os.environ)
    env["XDG_STATE_HOME"] = str(tmp_path)
    env.pop("KUBRICK_TELEMETRY_TOKEN", None)
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "telemetry.py"),
            "--action",
            "feedback",
            "--pattern-id",
            "known_pattern",
            "--vote",
            "useful",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "consent_required"


def test_cli_dispatch_records_only_allowlisted_usage_after_explicit_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_dir = tmp_path / "state"
    set_consent(state_dir, {"usage"})
    monkeypatch.setenv("KUBRICK_TELEMETRY_TOKEN", "test-token-never-forwarded")
    monkeypatch.setattr(cli, "telemetry_state_dir", lambda: state_dir)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("KUBRICK_TELEMETRY_ENDPOINT", raising=False)
    captured_child_env: dict[str, str] = {}

    def fake_run(*args: object, **kwargs: object) -> SimpleNamespace:
        child_env = kwargs["env"]
        assert isinstance(child_env, dict)
        captured_child_env.update(child_env)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as exit_info:
        cli._dispatch(["do", "compile", "--action", "run", "--brief", "private-prompt-token"])
    assert exit_info.value.code == 0
    assert "KUBRICK_TELEMETRY_TOKEN" not in captured_child_env

    actions = {
        intent: frozenset(spec.actions) for intent, spec in intent_router.INTENT_REGISTRY.items()
    }
    events = pending_events(state_dir, allowed_actions=actions)
    assert len(events) == 1
    assert events[0]["intent"] == "compile"
    assert events[0]["action"] == "run"
    assert set(events[0]) == telemetry.EVENT_FIELDS
    assert "private-prompt-token" not in json.dumps(events)


def test_cli_dispatch_skips_ci_and_telemetry_failures_do_not_change_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_dir = tmp_path / "state"
    monkeypatch.setattr(cli, "telemetry_state_dir", lambda: state_dir)
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=7),
    )
    set_consent(state_dir, {"usage"})
    monkeypatch.setenv("CI", "true")
    with pytest.raises(SystemExit) as ci_exit:
        cli._dispatch(["do", "compile", "--action", "run"])
    assert ci_exit.value.code == 7
    assert (
        pending_events(
            state_dir,
            allowed_actions={"compile": {"run"}, **{"telemetry": {"feedback"}}},
        )
        == []
    )

    monkeypatch.delenv("CI")
    monkeypatch.setattr(
        cli.telemetry,
        "record_usage_event",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("private failure")),
    )
    with pytest.raises(SystemExit) as telemetry_exit:
        cli._dispatch(["do", "compile", "--action", "run"])
    assert telemetry_exit.value.code == 7
