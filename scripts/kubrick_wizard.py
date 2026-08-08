#!/usr/bin/env python3
"""Kubrick wizard — guided plan/resolve for Hermes + CLI. Stdlib only."""

from __future__ import annotations

import argparse
import json
import subprocess
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
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise WizardError(f"answers must be valid JSON: {e}") from e
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

    # Spec: compile brief is required for --run only; defer to resolve_plan.
    if intent == "compile":
        missing = [m for m in missing if m != "brief"]

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
        # retrieve script may use different flag — map query to --brief when no brief
        if answers.get("query") and not answers.get("brief"):
            argv.extend(["--brief", answers["query"]])
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


def parse_wizard_argv(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse wizard flags from argv list (no program name)."""
    p = argparse.ArgumentParser(prog="kubrick do wizard")
    p.add_argument("--answers", default=None, help="path to answers JSON, or - for stdin")
    p.add_argument("--preset", choices=sorted(PRESETS), default=None)
    p.add_argument("--print-only", action="store_true", help="plan only (default without --run)")
    p.add_argument("--run", action="store_true", help="execute resolved plan via kubrick.py")
    p.add_argument("--json", action="store_true", help="emit plan as JSON")
    return p.parse_args(argv)


def _execute_plan(plan: dict[str, Any]) -> int:
    """Re-enter kubrick do path without nesting wizard."""
    argv = list(plan["argv"])
    if argv[:2] == ["do", "wizard"] or (argv and argv[0] == "wizard"):
        print("wizard error: refusing to dispatch wizard", file=sys.stderr)
        return 2
    r = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "kubrick.py"), *argv],
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    return int(r.returncode)


def main(argv: list[str] | None = None) -> int:
    """CLI entry for wizard flags. Used by kubrick.py special-case and direct invoke."""
    import intent_router as ir

    args = parse_wizard_argv(argv)

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
        sys.stdout.flush()
        if not args.run:
            return 0
        return _execute_plan(plan)
    except WizardError as e:
        print(f"wizard error: {e.message}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"wizard error: invalid JSON: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
