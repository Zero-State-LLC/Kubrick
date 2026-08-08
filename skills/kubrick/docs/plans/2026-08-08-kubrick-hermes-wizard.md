# Kubrick Hermes Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `kubrick do wizard` (and soft alias `wizard`) — non-interactive `--answers`/`--preset` plan+run for Hermes Desktop/agents, optional TTY interactive — as Kubrick **0.15.0**, delivered toward **Zero-State-LLC/Kubrick**.

**Architecture:** Stdlib module `scripts/kubrick_wizard.py` validates answers, merges presets, builds `do <intent> …` argv plans. `scripts/kubrick.py` special-cases `do wizard` / top-level `wizard` (like `recipe`) so `--run` re-enters `ir.resolve` + normal subprocess dispatch without recursive wizard loops. Manifest lists `wizard` for help/discovery. Hermes protocol in `SKILL.md` + `references/hermes-runtime-contract.md`.

**Tech Stack:** Python ≥ 3.10, stdlib for wizard core; pytest (suite lives under `scripts/test_*.py`); existing `intent_router` + `kubrick.manifest.yaml`. Spec: `docs/specs/2026-08-08-kubrick-hermes-wizard-design.md`.

## Global Constraints

- Wizard core: **stdlib only** (JSON answers, no PyYAML required for v1).
- Do not reimplement compile/visual/adapt/ledger logic — only build argv for existing `do` paths.
- Default is **print-only**; `--run` is explicit.
- `allow_mutate` must be real `bool`; default `false`; string `"false"` rejected.
- Mutating actions (ledger `mutate`, learn `evolve`, operate lock-style writes) require `allow_mutate: true`.
- Non-TTY without complete answers → exit `2` (no hang on `input()`).
- Unknown answer keys rejected (strict).
- Never write into `references/`.
- Keep occult systems latent in audience packets (existing SKILL rule).
- Version bump to **0.15.0** only in final docs/version task.
- Update `scripts/test_intent_router.py` `EXPECTED_INTENTS` when adding `wizard`.
- Delivery: PR to org **Zero-State-LLC/Kubrick** (dev may use `scrimshawlife-ctrl/Kubrick` remote first).
- Tests: `pytest scripts/test_wizard.py -q` and full `pytest scripts/test_*.py -q` before release task.

## File map

| File | Responsibility |
|------|----------------|
| `scripts/kubrick_wizard.py` | Answers merge/validate, plan resolve, interactive collect, format human/json, `main`/flags |
| `scripts/kubrick.py` | Special-case `do wizard` / `wizard` before `ir.resolve`; `--run` re-dispatch |
| `scripts/intent_router.py` | Help text includes wizard if driven purely from manifest (usually automatic) |
| `kubrick.manifest.yaml` | Register intent `wizard` + optional soft alias; recipes optional |
| `schemas/wizard-answers.v1.schema.json` | Answers contract |
| `scripts/test_wizard.py` | Unit + CLI subprocess tests |
| `scripts/test_intent_router.py` | EXPECTED_INTENTS includes `wizard` |
| `SKILL.md`, `references/hermes-runtime-contract.md` | Hermes routing protocol |
| `README.md`, `QUICKSTART.md`, `CHANGELOG.md`, `VERSION`, `pyproject.toml` version | 0.15.0 surface |

---

### Task 1: Core resolve library (TDD)

**Files:**
- Create: `scripts/kubrick_wizard.py`
- Create: `scripts/test_wizard.py`

**Interfaces:**
- Consumes: intent names/actions from a small dict or `intent_router.INTENT_REGISTRY` (prefer import `intent_router` for live registry)
- Produces:
  - `ANSWERS_SCHEMA = "kubrick-wizard-answers.v1"`
  - `PLAN_SCHEMA = "kubrick-wizard-plan.v1"`
  - `PRESETS: dict[str, dict]`
  - `ALLOWED_KEYS: frozenset`
  - `MUTATING_ACTIONS: frozenset` of `(intent, action)` pairs that require `allow_mutate`
  - `class WizardError(Exception)` with `.message` and optional `.missing: list[str]`
  - `def load_answers(path_or_dash: str) -> dict`
  - `def merge_preset(preset: str | None, answers: dict | None) -> dict`
  - `def validate_answers(answers: dict, registry: dict) -> dict`
  - `def resolve_plan(answers: dict, *, run: bool = False) -> dict`
  - `def format_plan_human(plan: dict, prog: str = "scripts/kubrick.py") -> str`
  - `def format_plan_json(plan: dict) -> str`
  - `def interactive_collect(registry: dict) -> dict` (can stub list/check only in T1)

- [ ] **Step 1: Write failing tests** in `scripts/test_wizard.py`:

```python
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
    merge_preset,
    resolve_plan,
    validate_answers,
)
import intent_router as ir  # noqa: E402

REG = ir.INTENT_REGISTRY


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
```

- [ ] **Step 2: Run tests — expect fail**

```bash
cd /home/scrimshawlife/Kubrick
pytest scripts/test_wizard.py -q
```

Expected: import error / module not found.

- [ ] **Step 3: Implement `scripts/kubrick_wizard.py`**

Core logic (stdlib):

```python
#!/usr/bin/env python3
"""Kubrick wizard — guided plan/resolve for Hermes + CLI. Stdlib only."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ANSWERS_SCHEMA = "kubrick-wizard-answers.v1"
PLAN_SCHEMA = "kubrick-wizard-plan.v1"

ALLOWED_KEYS = frozenset({
    "schema", "intent", "action", "brief", "ledger", "storyboard_plan",
    "provider", "mode", "out", "packet", "expected", "observation",
    "query", "project", "allow_mutate", "extra_flags",
    "output",  # adapt often uses --output
})

# (intent, action) pairs that require allow_mutate true
MUTATING_ACTIONS = frozenset({
    ("ledger", "mutate"),
    ("learn", "evolve"),
    ("operate", "convergence-lock"),
    ("operate", "motif-mutation"),
})

PRESETS: dict[str, dict[str, Any]] = {
    "storyboard-compile": {
        "schema": ANSWERS_SCHEMA,
        "intent": "compile",
        "action": "run",
        "mode": "storyboard",
        "provider": "grok-imagine",
    },
    "verify": {
        "schema": ANSWERS_SCHEMA,
        "intent": "check",
        "action": "smoke",
    },
    "visual-qa": {
        "schema": ANSWERS_SCHEMA,
        "intent": "visual",
        "action": "closed-loop",
    },
    "adapt-provider": {
        "schema": ANSWERS_SCHEMA,
        "intent": "adapt",
        "action": "provider",
    },
    "ledger-init": {
        "schema": ANSWERS_SCHEMA,
        "intent": "ledger",
        "action": "init",
    },
    "design-build": {
        "schema": ANSWERS_SCHEMA,
        "intent": "design",
        "action": "build",
    },
    "retrieve": {
        "schema": ANSWERS_SCHEMA,
        "intent": "retrieve",
        "action": "retrieve",
    },
}

LOGICAL_GROUP = {
    "compile": "creative", "retrieve": "creative", "adapt": "creative",
    "storyboard": "creative", "design": "creative", "bundle": "creative",
    "ledger": "ops", "visual": "ops", "learn": "ops", "operate": "ops",
    "check": "meta", "mcp": "meta", "wizard": "meta",
}


class WizardError(Exception):
    def __init__(self, message: str, missing: list[str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.missing = missing or []


def load_answers(path_or_dash: str) -> dict[str, Any]:
    try:
        if path_or_dash == "-":
            text = sys.stdin.read()
        else:
            text = Path(path_or_dash).read_text(encoding="utf-8")
    except OSError as e:
        raise WizardError(f"cannot read answers file: {e}") from e
    data = json.loads(text)
    if not isinstance(data, dict):
        raise WizardError("answers must be a JSON object")
    return data


def merge_preset(preset: str | None, answers: dict[str, Any] | None) -> dict[str, Any]:
    base: dict[str, Any] = {}
    if preset:
        if preset not in PRESETS:
            raise WizardError(f"unknown preset: {preset}")
        base = dict(PRESETS[preset])
    if answers:
        base.update(answers)
    base.setdefault("schema", ANSWERS_SCHEMA)
    return base


def validate_answers(answers: dict[str, Any], registry: dict) -> dict[str, Any]:
    unknown = set(answers) - ALLOWED_KEYS
    if unknown:
        raise WizardError(f"unknown keys: {sorted(unknown)}")
    if answers.get("schema") != ANSWERS_SCHEMA:
        raise WizardError(f"schema must be {ANSWERS_SCHEMA}")
    intent = answers.get("intent")
    if intent not in registry:
        raise WizardError(f"unknown intent: {intent}")
    if intent == "wizard":
        raise WizardError("wizard cannot target intent wizard")

    out = dict(answers)
    out.setdefault("allow_mutate", False)
    if not isinstance(out["allow_mutate"], bool):
        raise WizardError("allow_mutate must be a JSON boolean")

    action = out.get("action")
    spec = registry[intent]
    if action is None:
        action = spec.default_action
        out["action"] = action
    if action is None:
        raise WizardError(f"action required for intent {intent}", missing=["action"])
    if action not in spec.actions:
        raise WizardError(f"unknown action {action!r} for intent {intent}")

    if (intent, action) in MUTATING_ACTIONS and not out["allow_mutate"]:
        raise WizardError(f"{intent}/{action} requires allow_mutate: true")

    missing: list[str] = []
    if intent == "compile":
        if not out.get("brief"):
            missing.append("brief")
        # out required only for --run (checked in resolve_plan)
    elif intent == "adapt" and action == "provider":
        if not out.get("packet"):
            missing.append("packet")
        if not out.get("provider"):
            missing.append("provider")
    elif intent == "visual" and action in {"compare", "closed-loop", "correct"}:
        # soft: require expected/observation for compare-like; closed-loop may need both
        if action != "closed-loop":
            if not out.get("expected"):
                missing.append("expected")
            if not out.get("observation"):
                missing.append("observation")
    elif intent == "retrieve":
        if not out.get("query") and not out.get("brief"):
            missing.append("query")

    # validate_answers: for print-only soft missing is OK for compile brief?
    # Spec: missing required → 2. Compile brief is required always in validate
    # except we allow print-only warn — design says compile brief required for --run.
    # Keep brief in missing only enforced at resolve_plan when run=True for compile.
    if intent == "compile":
        missing = [m for m in missing if m != "brief"]  # defer to resolve_plan

    if missing:
        raise WizardError(f"missing required fields: {missing}", missing=missing)

    if out.get("extra_flags") is not None and not isinstance(out["extra_flags"], list):
        raise WizardError("extra_flags must be a list of strings")
    return out


def resolve_plan(answers: dict[str, Any], *, run: bool = False) -> dict[str, Any]:
    intent = answers["intent"]
    action = answers["action"]
    safety = ["print-only unless --run", f"allow_mutate {answers.get('allow_mutate')}"]
    argv: list[str] = ["do", intent, "--action", action]

    def add_opt(flag: str, key: str) -> None:
        val = answers.get(key)
        if val:
            argv.extend([flag, str(val)])

    if intent == "compile":
        if run and not answers.get("brief"):
            raise WizardError("compile --run requires brief")
        if run and not answers.get("out"):
            raise WizardError("compile --run requires out")
        if not answers.get("brief"):
            safety.append("warning: brief missing — required for --run")
        if not answers.get("out"):
            safety.append("warning: out missing — required for --run")
        add_opt("--brief", "brief")
        add_opt("--ledger", "ledger")
        add_opt("--storyboard-plan", "storyboard_plan")
        add_opt("--mode", "mode")
        add_opt("--provider", "provider")
        add_opt("--out", "out")
    elif intent == "check":
        pass  # action already set
    elif intent == "adapt":
        add_opt("--packet", "packet")
        add_opt("--provider", "provider")
        add_opt("--output", "output")
        add_opt("--out", "out")
    elif intent == "visual":
        add_opt("--expected", "expected")
        add_opt("--observation", "observation")
        add_opt("--out", "out")
    elif intent == "ledger":
        add_opt("--project", "project")
        add_opt("--out", "out")
    elif intent == "retrieve":
        add_opt("--brief", "brief")
        # retrieve script may use different flag — map query to --brief or documented flag
        if answers.get("query") and not answers.get("brief"):
            argv.extend(["--brief", answers["query"]])  # adjust if script uses --query
        add_opt("--out", "out")
    else:
        add_opt("--out", "out")
        add_opt("--brief", "brief")
        add_opt("--packet", "packet")

    for tok in answers.get("extra_flags") or []:
        if not isinstance(tok, str):
            raise WizardError("extra_flags entries must be strings")
        argv.append(tok)

    return {
        "schema": PLAN_SCHEMA,
        "group": LOGICAL_GROUP.get(intent, "ops"),
        "intent": intent,
        "action": action,
        "argv": argv,
        "rationale": f"Plan for do {intent} --action {action}.",
        "safety": safety,
        "run": run,
    }


def format_plan_json(plan: dict[str, Any]) -> str:
    return json.dumps(plan, indent=2, sort_keys=True) + "\n"


def format_plan_human(plan: dict[str, Any], prog: str = "scripts/kubrick.py") -> str:
    line = " ".join(_q(a) for a in plan["argv"])
    return (
        f"Kubrick wizard plan — {plan['group']}/{plan['intent']}/{plan['action']}\n"
        f"{plan['rationale']}\n"
        f"Safety: {'; '.join(plan['safety'])}\n\n"
        f"python3 {prog} {line}\n\n"
        + ("(will execute via --run)\n" if plan.get("run") else "Print-only. Re-run with --run to execute.\n")
    )


def _q(s: str) -> str:
    if not s or any(c in s for c in " \t\n\"'$&|;<>"):
        return json.dumps(s)
    return s


def interactive_collect(registry: dict) -> dict[str, Any]:
    """TTY prompts → answers. Caller ensures isatty."""
    intents = sorted(registry.keys())
    print("Kubrick wizard — intents:")
    for i, name in enumerate(intents, 1):
        print(f"  {i}. {name}")
    choice = input("Intent number or name: ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(intents):
        intent = intents[int(choice) - 1]
    elif choice in registry:
        intent = choice
    else:
        raise WizardError(f"invalid intent: {choice}")
    answers: dict[str, Any] = {"schema": ANSWERS_SCHEMA, "intent": intent}
    actions = sorted(registry[intent].actions.keys())
    print("Actions:", ", ".join(actions))
    default = registry[intent].default_action or (actions[0] if actions else "")
    act = input(f"Action [{default}]: ").strip() or default
    answers["action"] = act
    if intent == "compile":
        answers["brief"] = input("brief path: ").strip() or None
        answers["out"] = input("out dir: ").strip() or None
        answers["mode"] = input("mode [storyboard]: ").strip() or "storyboard"
        answers["ledger"] = input("ledger path [empty]: ").strip() or None
        answers["provider"] = input("provider [grok-imagine]: ").strip() or "grok-imagine"
    elif intent == "check":
        pass
    else:
        for key, prompt in (
            ("packet", "packet path"),
            ("provider", "provider"),
            ("expected", "expected path"),
            ("observation", "observation path"),
            ("out", "out path"),
            ("query", "query/brief"),
            ("project", "project path"),
        ):
            val = input(f"{prompt} [empty]: ").strip()
            if val:
                answers[key] = val
    if (intent, act) in MUTATING_ACTIONS:
        conf = input("Type CONFIRM to allow mutate: ").strip()
        if conf != "CONFIRM":
            raise WizardError("mutate aborted")
        answers["allow_mutate"] = True
    return answers


def parse_wizard_argv(argv: list[str]) -> dict[str, Any]:
    """Parse wizard flags from argv list (no program name). Returns namespace-like dict."""
    # Implement simple argparse in main() of this module — see Task 2.
    raise NotImplementedError


def main(argv: list[str] | None = None) -> int:
    """CLI entry for wizard flags. Used by kubrick.py special-case and direct invoke."""
    # Fully implemented in Task 2 when wiring; Task 1 may leave a minimal stub
    # that only supports library functions for unit tests.
    raise SystemExit("use via kubrick do wizard — wire in Task 2")


if __name__ == "__main__":
    raise SystemExit(main())
```

**Note:** Adjust retrieve flag names to match `retrieve_symbolic_patterns_registry.py` (`--brief` is known from compile path). Inspect adapt_provider flags (`--packet`, `--provider`, `--output`) from existing router tests.

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest scripts/test_wizard.py -q
```

- [ ] **Step 5: Commit**

```bash
git add scripts/kubrick_wizard.py scripts/test_wizard.py
git commit -m "feat(wizard): add resolve/validate library and unit tests"
```

---

### Task 2: Wire `do wizard` / soft alias in CLI

**Files:**
- Modify: `scripts/kubrick.py`
- Modify: `kubrick.manifest.yaml` (add intent `wizard`)
- Modify: `scripts/test_intent_router.py` (`EXPECTED_INTENTS` add `"wizard"`)
- Modify: `scripts/kubrick_wizard.py` (`main` + argparse)
- Modify: `scripts/test_wizard.py` (CLI tests)

**Interfaces:**
- `kubrick_wizard.main(argv: list[str]) -> int` handles flags after stripping `do wizard` / `wizard`
- On `--run`, call back into a re-dispatch function that does **not** accept wizard as target

- [ ] **Step 1: Add CLI tests**

```python
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
```

- [ ] **Step 2: Run — expect fail** (unknown intent wizard)

- [ ] **Step 3: Manifest + router expectation**

In `kubrick.manifest.yaml` under `intents`:

```yaml
# JSON-style file is actually JSON — use JSON syntax:
"wizard": {
  "description": "Guided plan/execute for Hermes (answers JSON or interactive TTY)",
  "default_action": "plan",
  "actions": {
    "plan": "kubrick_wizard.py"
  }
}
```

**Important:** `kubrick.py` must **special-case** wizard **before** `subprocess.run` to the wizard script for plan mode, so `--run` can re-dispatch. Implement in `kubrick.py`:

```python
def _is_wizard_argv(argv: list[str]) -> bool:
    if not argv:
        return False
    if argv[0] == "wizard":
        return True
    return argv[0] == "do" and len(argv) >= 2 and argv[1] == "wizard"


def _wizard_flags(argv: list[str]) -> list[str]:
    if argv[0] == "wizard":
        return argv[1:]
    # do wizard [flags]
    return argv[2:]


# in main(), after recipe handling, before ir.resolve:
if _is_wizard_argv(argv):
    import kubrick_wizard as wiz
    raise SystemExit(wiz.main(_wizard_flags(argv)))
```

Implement `kubrick_wizard.main`:

```python
def main(argv: list[str] | None = None) -> int:
    import argparse
    import intent_router as ir

    p = argparse.ArgumentParser(prog="kubrick do wizard")
    p.add_argument("--answers", default=None)
    p.add_argument("--preset", choices=sorted(PRESETS), default=None)
    p.add_argument("--print-only", action="store_true")
    p.add_argument("--run", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    try:
        answers_in = load_answers(args.answers) if args.answers else None
        if args.preset or answers_in is not None:
            raw = merge_preset(args.preset, answers_in)
        else:
            if not sys.stdin.isatty():
                print(
                    "wizard: non-interactive use requires --answers and/or --preset "
                    "(Hermes Desktop: collect fields in chat, then pass --answers)",
                    file=sys.stderr,
                )
                return 2
            raw = interactive_collect(ir.INTENT_REGISTRY)
        answers = validate_answers(raw, ir.INTENT_REGISTRY)
        plan = resolve_plan(answers, run=bool(args.run))
        if args.json:
            sys.stdout.write(format_plan_json(plan))
        else:
            sys.stdout.write(format_plan_human(plan))
        if not args.run:
            return 0
        return _execute_plan(plan)
    except WizardError as e:
        print(f"wizard error: {e.message}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"wizard error: invalid JSON: {e}", file=sys.stderr)
        return 2


def _execute_plan(plan: dict[str, Any]) -> int:
    """Re-enter kubrick do path without nesting wizard."""
    import intent_router as ir
    from pathlib import Path
    import subprocess
    argv = list(plan["argv"])
    if not argv or argv[0] != "do" or (len(argv) > 1 and argv[1] == "wizard"):
        print("wizard error: refusing to dispatch wizard", file=sys.stderr)
        return 2
    call = ir.resolve(argv)
    if call.intent == "check" and call.action == "smoke":
        # duplicate smoke composite or invoke via subprocess kubrick.py
        r = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent / "kubrick.py"), *argv],
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        return int(r.returncode)
    r = subprocess.run(
        [sys.executable, str(call.script), *call.argv],
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    return int(r.returncode)
```

Prefer re-invoking `kubrick.py` for all `--run` cases to reuse smoke composite:

```python
def _execute_plan(plan: dict) -> int:
    argv = list(plan["argv"])
    if argv[:2] == ["do", "wizard"] or (argv and argv[0] == "wizard"):
        print("wizard error: refusing to dispatch wizard", file=sys.stderr)
        return 2
    r = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "kubrick.py"), *argv],
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    return int(r.returncode)
```

Update `EXPECTED_INTENTS` in `test_intent_router.py` to include `"wizard"`.

- [ ] **Step 4: Run tests**

```bash
pytest scripts/test_wizard.py scripts/test_intent_router.py -q
```

- [ ] **Step 5: Commit**

```bash
git add scripts/kubrick.py scripts/kubrick_wizard.py scripts/test_wizard.py \
  scripts/test_intent_router.py kubrick.manifest.yaml
git commit -m "feat(wizard): register do wizard CLI (print-only + answers)"
```

---

### Task 3: Interactive TTY coverage

**Files:**
- Modify: `scripts/kubrick_wizard.py` (polish `interactive_collect` if needed)
- Modify: `scripts/test_wizard.py`

- [ ] **Step 1: Test interactive check path**

```python
def test_interactive_check():
    with mock.patch("builtins.input", side_effect=["check", "smoke"]):
        ans = interactive_collect(REG)
    assert ans["intent"] == "check"
    validated = validate_answers(ans, REG)
    plan = resolve_plan(validated)
    assert plan["intent"] == "check"
```

- [ ] **Step 2: GREEN + commit**

```bash
pytest scripts/test_wizard.py -q
git add scripts/kubrick_wizard.py scripts/test_wizard.py
git commit -m "feat(wizard): interactive TTY collect path"
```

---

### Task 4: `--run` integration

**Files:**
- Modify: `scripts/test_wizard.py`
- Modify: `scripts/kubrick_wizard.py` if execute path incomplete

- [ ] **Step 1: Integration test — verify preset --run**

```python
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
```

Optional: compile --run against example brief into temp out (heavier but strong).

- [ ] **Step 2: GREEN + commit**

```bash
pytest scripts/test_wizard.py -q
git add scripts/test_wizard.py scripts/kubrick_wizard.py
git commit -m "feat(wizard): --run re-dispatch via kubrick do path"
```

---

### Task 5: JSON Schema + smoke/recipe

**Files:**
- Create: `schemas/wizard-answers.v1.schema.json`
- Modify: `kubrick.manifest.yaml` (`schemas` list append; optional recipe `wizard-verify`)
- Modify: validation if schemas are enumerated for check skill

- [ ] **Step 1: Schema file** matching design (`additionalProperties: false`, intent enum from registry intents except nesting rules enforced in Python).

- [ ] **Step 2: Recipe**

```json
"wizard-verify": ["do", "wizard", "--preset", "verify", "--json"]
```

Or smoke script line if project has smoke.sh — prefer recipe + pytest.

- [ ] **Step 3: Run**

```bash
python3 scripts/kubrick.py recipe wizard-verify
pytest scripts/test_wizard.py scripts/test_intent_router.py -q
```

- [ ] **Step 4: Commit**

```bash
git add schemas/wizard-answers.v1.schema.json kubrick.manifest.yaml
git commit -m "feat(wizard): answers JSON schema and verify recipe"
```

---

### Task 6: Hermes docs + version 0.15.0 + org PR prep

**Files:**
- Modify: `SKILL.md` (wizard protocol + when unsure prefer wizard)
- Modify: `references/hermes-runtime-contract.md`
- Modify: `README.md`, `QUICKSTART.md`
- Modify: `CHANGELOG.md`
- Bump: `VERSION` → `0.15.0`, `kubrick.manifest.yaml` version, `SKILL.md` version, `pyproject.toml` version
- Follow existing release checklist patterns under `docs/RELEASE-CHECKLIST-v0.14.md` as template for notes if needed

- [ ] **Step 1: Docs** — mirror Orchestra SKILL wizard section: chat collect → answers → print-only → run; never freestyle `allow_mutate`.

- [ ] **Step 2: Version bump** to 0.15.0 everywhere parity requires.

- [ ] **Step 3: Full gate**

```bash
python3 scripts/kubrick.py do check --action smoke
pytest scripts/ -q
```

- [ ] **Step 4: Commit**

```bash
git commit -am "docs+release: Kubrick 0.15.0 Hermes wizard"
```

- [ ] **Step 5: Org delivery**

```bash
# ensure remote for org
git remote add org https://github.com/Zero-State-LLC/Kubrick.git  # if missing
git fetch org
git checkout -b feature/kubrick-hermes-wizard
git push -u org feature/kubrick-hermes-wizard
# or push to origin then open PR into Zero-State-LLC/Kubrick
gh pr create --repo Zero-State-LLC/Kubrick --base <default-branch> --head ...
```

Confirm default branch on org (may not be `main` — use `gh repo view Zero-State-LLC/Kubrick --json defaultBranchRef`).

---

## Spec coverage checklist

| Spec requirement | Task |
|------------------|------|
| `do wizard` surface | 2 |
| Presets | 1–2 |
| `--answers` / print-only / `--run` / `--json` | 1–4 |
| Strict keys + bool `allow_mutate` | 1 |
| Non-TTY exit 2 | 2 |
| Desktop chat protocol docs | 6 |
| Schema file | 5 |
| Reuse do dispatch | 2, 4 |
| 0.15.0 | 6 |
| Org PR | 6 |
| No references/ writes | 1 (no paths write there) |

## Self-review notes

- `EXPECTED_INTENTS` must include `wizard` or router tests fail.
- Prefer re-invoke `kubrick.py` for `--run` so check smoke composite stays correct.
- Manifest is JSON (despite `.yaml` name) — edit as JSON.
- Retrieve/adapt flag names must match real scripts (verify with `--help` / existing tests).

---

## Execution handoff

Plan complete and saved to `docs/plans/2026-08-08-kubrick-hermes-wizard.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — this session with checkpoints  

Which approach?
