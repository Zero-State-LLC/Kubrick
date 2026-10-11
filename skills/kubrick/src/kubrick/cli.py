#!/usr/bin/env python3
"""Unified Hermes-native CLI for Kubrick's deterministic tools.

Primary surface:
  kubrick do <intent> [--action <action>] [flags]

Also:
  kubrick recipe <name>
  kubrick help [<intent>]
  kubrick aliases
  <legacy-command> [flags]   # soft aliases via intent_router
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

from kubrick.paths import SCRIPTS, SKILL_ROOT, telemetry_state_dir

ROOT = SKILL_ROOT
PY = sys.executable
FIRST_CLASS_PRODUCTION_SURFACES = {"design", "script", "image", "video"}

import kubrick.runtime.caller_paths as caller_paths  # noqa: E402
import kubrick.runtime.intent_router as ir  # noqa: E402
import kubrick.runtime.runtime_deps as runtime_deps  # noqa: E402
import kubrick.runtime.telemetry as telemetry  # noqa: E402
from kubrick.runtime.diagnostics import abort, diagnostic  # noqa: E402


def _abort_router(error: ir.RouterError) -> None:
    abort(
        diagnostic(
            status="INVALID_COMMAND",
            code="ROUTER_ERROR",
            exit_code=error.exit_code,
            message=error.message,
            context={"surface": "kubrick"},
        )
    )


def _is_agent() -> bool:
    """Quiet mode for agents / non-TTY (suppress alias deprecation notes)."""
    return os.environ.get("KUBRICK_AGENT") == "1" or not sys.stderr.isatty()


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


def _pin_caller_cwd() -> None:
    """Remember this process cwd before any child starts with cwd=ROOT.

    Wizard re-dispatch inherits the environment, so a nested ``kubrick.py``
    keeps the original caller even though that child is started in the skill root.
    """
    if not os.environ.get("KUBRICK_CALLER_CWD", "").strip():
        os.environ["KUBRICK_CALLER_CWD"] = os.getcwd()


def _child_env(*, include_telemetry_token: bool = False) -> dict[str, str]:
    """Prepare a child environment while isolating the telemetry credential.

    Artifact placement and relative path flags read ``KUBRICK_CALLER_CWD``.
    Path policy still keys off ``KUBRICK_PROJECT_DIR``. Only the dedicated
    telemetry adapter receives ``KUBRICK_TELEMETRY_TOKEN``.
    """
    env = dict(os.environ)
    if not include_telemetry_token:
        env.pop("KUBRICK_TELEMETRY_TOKEN", None)
    if not env.get("KUBRICK_CALLER_CWD"):
        env["KUBRICK_CALLER_CWD"] = os.getcwd()
    return env


def _prepared_argv(argv: list[str], env: dict[str, str]) -> list[str]:
    """Absolutize relative path flags against the caller cwd (#82)."""
    caller = env.get("KUBRICK_CALLER_CWD", "").strip() or os.getcwd()
    return caller_paths.rewrite(argv, caller)


def _dispatch_smoke(call: ir.IntentCall) -> None:
    """check smoke: validate manifest, skill, then pattern corpus (composite)."""
    env = _child_env()
    argv = _prepared_argv(list(call.argv), env)
    for script in (
        "validate_manifest.py",
        "validate_hermes_skill.py",
        "validate_pattern_corpus.py",
    ):
        r = subprocess.run([PY, str(SCRIPTS / script), *argv], cwd=ROOT, env=env)
        if r.returncode != 0:
            raise SystemExit(r.returncode)
    print("check smoke: PASS")
    raise SystemExit(0)


def _execution_argv(call: ir.IntentCall) -> list[str]:
    """Build implementation argv without leaking router-only semantics.

    First-class production surfaces intentionally route multiple actions to one
    deterministic runtime. Forward the resolved action as an explicit internal
    flag so the implementation never has to infer operator intent.
    """
    argv = list(call.argv)
    if call.intent == "telemetry":
        argv = ["--action", call.action, *argv]
    if call.script.name == "generate_design_spec.py":
        return argv
    if call.intent in FIRST_CLASS_PRODUCTION_SURFACES:
        argv = ["--surface-action", call.action, *argv]
    return argv


def _record_usage_best_effort(
    call: ir.IntentCall, return_code: int, duration_seconds: float
) -> None:
    """Record only resolved action metadata; telemetry cannot change dispatch."""
    if call.intent in {"check", "telemetry"}:
        return
    if os.environ.get("CI", "").strip().lower() in {"1", "true", "yes"}:
        return
    allowed_actions = {
        intent: frozenset(spec.actions) for intent, spec in ir.INTENT_REGISTRY.items()
    }
    try:
        telemetry.record_usage_event(
            telemetry_state_dir(),
            intent=call.intent,
            action=call.action,
            return_code=return_code,
            duration_seconds=duration_seconds,
            kubrick_version=ir.MANIFEST["version"],
            allowed_actions=allowed_actions,
            endpoint=os.environ.get("KUBRICK_TELEMETRY_ENDPOINT"),
            bearer_token=os.environ.get("KUBRICK_TELEMETRY_TOKEN"),
        )
    except Exception:
        # Opt-in telemetry is best effort and must never change Kubrick's result.
        return


def _top_help(argv: list[str]) -> bool:
    if argv and not (argv[0] in {"-h", "--help", "help"} and len(argv) == 1):
        return False
    sys.stdout.write(ir.format_top_level_help())
    raise SystemExit(0)


def _intent_help(argv: list[str]) -> bool:
    if not (argv and argv[0] == "help" and len(argv) >= 2):
        return False
    try:
        sys.stdout.write(ir.format_intent_help(argv[1]))
    except ir.RouterError as error:
        _abort_router(error)
    raise SystemExit(0)


def _receipts(argv: list[str]) -> bool:
    if not argv or argv[0] != "receipts":
        return False
    env = _child_env()
    receipt = [PY, str(SCRIPTS / "list_receipts.py"), *_prepared_argv(argv[1:], env)]
    raise SystemExit(subprocess.call(receipt, cwd=ROOT, env=env))


def _qa_sugar(argv: list[str]) -> list[str]:
    if not (argv and argv[0] == "qa" and len(argv) >= 2):
        return argv
    surface = argv[1]
    if surface not in FIRST_CLASS_PRODUCTION_SURFACES:
        _abort_router(ir.RouterError("usage: kubrick qa <design|script|image|video> ..."))
    return ["do", surface, "--action", "qa", *argv[2:]]


def _validate_sugar(argv: list[str]) -> list[str]:
    if not (argv and argv[0] == "validate" and len(argv) >= 2):
        return argv
    surface = argv[1]
    if surface == "design":
        return ["do", "design", "--action", "validate", *argv[2:]]
    if surface == "script":
        return ["do", "script", "--action", "diagnose", *argv[2:]]
    if surface in {"image", "video"}:
        return ["do", surface, "--action", "qa", *argv[2:]]
    _abort_router(ir.RouterError("usage: kubrick validate <design|script|image|video> ..."))
    return argv


def _bare_surface(argv: list[str]) -> list[str]:
    bare = (
        bool(argv)
        and argv[0] in FIRST_CLASS_PRODUCTION_SURFACES
        and (len(argv) == 1 or (not argv[1].startswith("-") and argv[1] != "do"))
    )
    if not bare:
        return argv
    rest = argv[1:]
    action = rest[0] if rest and not rest[0].startswith("-") else None
    if action:
        rest = rest[1:]
    return ["do", argv[0], *(["--action", action] if action else []), *rest]


def _aliases(argv: list[str]) -> bool:
    if not argv or argv[0] != "aliases":
        return False
    sys.stdout.write(ir.format_aliases())
    raise SystemExit(0)


def _recipe(argv: list[str]) -> list[str]:
    if not argv or argv[0] != "recipe":
        return argv
    if len(argv) < 2:
        _abort_router(ir.RouterError("usage: kubrick recipe <name>"))
    try:
        return ir.resolve_recipe(argv[1])
    except ir.RouterError as error:
        _abort_router(error)
    return argv


def _wizard(argv: list[str]) -> bool:
    if not _is_wizard_argv(argv):
        return False
    import kubrick.runtime.kubrick_wizard as wiz

    raise SystemExit(wiz.main(_wizard_flags(argv)))


def _do_help(argv: list[str]) -> bool:
    if not (
        len(argv) >= 2 and argv[0] == "do" and any(tok in {"-h", "--help"} for tok in argv[2:])
    ):
        return False
    try:
        sys.stdout.write(ir.format_intent_help(argv[1]))
    except ir.RouterError as error:
        _abort_router(error)
    raise SystemExit(0)


def _prepare_argv(argv: list[str]) -> list[str]:
    _top_help(argv)
    _intent_help(argv)
    _receipts(argv)
    argv = _qa_sugar(argv)
    argv = _validate_sugar(argv)
    argv = _bare_surface(argv)
    _aliases(argv)
    argv = _recipe(argv)
    _wizard(argv)
    _do_help(argv)
    return argv


def _dispatch(argv: list[str]) -> None:
    try:
        call = ir.resolve(argv)
    except ir.RouterError as error:
        if error.message == "HELP":
            sys.stdout.write(ir.format_top_level_help())
            raise SystemExit(0)
        _abort_router(error)
        raise SystemExit(error.exit_code)
    if call.legacy_name and not _is_agent() and os.environ.get("KUBRICK_QUIET") != "1":
        print(
            f"note: `{call.legacy_name}` is a legacy alias; "
            f"prefer `kubrick do {call.intent} --action {call.action}`",
            file=sys.stderr,
        )
    if call.intent == "check" and call.action == "smoke":
        _dispatch_smoke(call)
    runtime_deps.check_action(ir.MANIFEST, call.intent, call.action)
    env = _child_env(include_telemetry_token=call.intent == "telemetry")
    started = time.monotonic()
    try:
        result = subprocess.run(
            [PY, str(call.script), *_prepared_argv(_execution_argv(call), env)],
            cwd=ROOT,
            env=env,
        )
    except (OSError, subprocess.SubprocessError):
        _record_usage_best_effort(call, 1, max(0.0, time.monotonic() - started))
        raise
    _record_usage_best_effort(call, result.returncode, max(0.0, time.monotonic() - started))
    raise SystemExit(result.returncode)


def main() -> None:
    _pin_caller_cwd()
    _dispatch(_prepare_argv(sys.argv[1:]))


if __name__ == "__main__":
    main()
