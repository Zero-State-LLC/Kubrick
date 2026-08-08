# scripts/test_wizard.py
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from kubrick_wizard import (  # noqa: E402
    ANSWERS_SCHEMA,
    WizardError,
    interactive_collect,
    merge_preset,
    resolve_plan,
    validate_answers,
)
import intent_router as ir  # noqa: E402

REG = ir.INTENT_REGISTRY


def test_interactive_check():
    with mock.patch("builtins.input", side_effect=["check", "smoke"]):
        ans = interactive_collect(REG)
    assert ans["intent"] == "check"
    validated = validate_answers(ans, REG)
    plan = resolve_plan(validated)
    assert plan["intent"] == "check"


def test_preset_verify_argv():
    raw = merge_preset("verify", None)
    ans = validate_answers(raw, REG)
    plan = resolve_plan(ans, run=False)
    assert plan["schema"] == "kubrick-wizard-plan.v1"
    assert plan["intent"] == "check"
    assert plan["action"] == "smoke"
    assert plan["argv"][:3] == ["do", "check", "--action"]
    assert "smoke" in plan["argv"]
    assert plan["run"] is False


def test_preset_storyboard_compile_requires_brief_for_run():
    raw = merge_preset("storyboard-compile", {"out": "/tmp/out"})
    ans = validate_answers(raw, REG)
    with pytest.raises(WizardError):
        resolve_plan(ans, run=True)
    plan = resolve_plan(ans, run=False)
    assert plan["intent"] == "compile"
    assert any("brief" in s.lower() or "out" in s.lower() for s in plan["safety"])


def test_storyboard_compile_with_brief():
    raw = merge_preset(
        "storyboard-compile",
        {
            "brief": "examples/authority-transfer-storyboard/brief.yaml",
            "out": "/tmp/kb",
        },
    )
    ans = validate_answers(raw, REG)
    plan = resolve_plan(ans)
    assert plan["argv"][0:2] == ["do", "compile"]
    assert "--brief" in plan["argv"]
    assert "--out" in plan["argv"]
    assert "--mode" in plan["argv"] and "storyboard" in plan["argv"]


def test_unknown_key_rejected():
    with pytest.raises(WizardError):
        validate_answers(
            {"schema": ANSWERS_SCHEMA, "intent": "check", "nope": 1},
            REG,
        )


def test_allow_mutate_string_rejected():
    with pytest.raises(WizardError):
        validate_answers(
            {
                "schema": ANSWERS_SCHEMA,
                "intent": "learn",
                "action": "evolve",
                "allow_mutate": "false",
            },
            REG,
        )


def test_mutate_without_allow_rejected():
    with pytest.raises(WizardError):
        validate_answers(
            {
                "schema": ANSWERS_SCHEMA,
                "intent": "ledger",
                "action": "mutate",
                "allow_mutate": False,
            },
            REG,
        )


def test_unknown_intent_rejected():
    with pytest.raises(WizardError):
        validate_answers(
            {"schema": ANSWERS_SCHEMA, "intent": "not-an-intent"},
            REG,
        )


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "kubrick.py"), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )


def test_wizard_help_lists_or_runs():
    r = run_cli("do", "wizard", "--help")
    # either wizard-specific help or top-level; returncode 0
    assert r.returncode == 0


def test_wizard_print_only_verify_json():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "a.json"
        p.write_text(json.dumps({
            "schema": "kubrick-wizard-answers.v1",
            "intent": "check",
            "action": "smoke",
        }), encoding="utf-8")
        r = run_cli("do", "wizard", "--answers", str(p), "--json")
        assert r.returncode == 0, r.stderr
        plan = json.loads(r.stdout)
        assert plan["intent"] == "check"
        assert plan["action"] == "smoke"
        assert plan["run"] is False


def test_wizard_non_tty_without_answers_exits_2():
    r = run_cli("do", "wizard")
    assert r.returncode == 2
    assert "answers" in r.stderr.lower() or "non-interactive" in r.stderr.lower()


def test_wizard_run_verify_smoke():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "a.json"
        p.write_text(json.dumps({
            "schema": "kubrick-wizard-answers.v1",
            "intent": "check",
            "action": "smoke",
        }), encoding="utf-8")
        r = run_cli("do", "wizard", "--answers", str(p), "--run")
        assert r.returncode == 0, r.stdout + r.stderr
        assert "PASS" in r.stdout or "smoke" in r.stdout.lower() or r.returncode == 0

