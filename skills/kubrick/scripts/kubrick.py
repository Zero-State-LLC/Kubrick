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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
PY = sys.executable
FIRST_CLASS_PRODUCTION_SURFACES = {"design", "script", "image", "video"}

sys.path.insert(0, str(SCRIPTS))
import intent_router as ir  # noqa: E402
from diagnostics import abort, diagnostic  # noqa: E402


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


def _dispatch_smoke(call: ir.IntentCall) -> None:
    """check smoke: validate manifest, skill, then pattern corpus (composite)."""
    for script in (
        "validate_manifest.py",
        "validate_hermes_skill.py",
        "validate_pattern_corpus.py",
    ):
        r = subprocess.run([PY, str(SCRIPTS / script), *call.argv], cwd=ROOT)
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
    if call.intent in FIRST_CLASS_PRODUCTION_SURFACES:
        argv = ["--surface-action", call.action, *argv]
    return argv


def main() -> None:
    argv = sys.argv[1:]

    if not argv or (argv[0] in {"-h", "--help", "help"} and len(argv) == 1):
        sys.stdout.write(ir.format_top_level_help())
        raise SystemExit(0)

    if argv[0] == "help" and len(argv) >= 2:
        try:
            sys.stdout.write(ir.format_intent_help(argv[1]))
        except ir.RouterError as e:
            _abort_router(e)
        raise SystemExit(0)

    if argv[0] == "receipts":
        raise SystemExit(subprocess.call([PY, str(SCRIPTS / "list_receipts.py"), *argv[1:]], cwd=ROOT))

    if argv[0] == "qa" and len(argv) >= 2:
        # sugar: kubrick qa <surface> ... → do <surface> --action qa ...
        surface = argv[1]
        if surface in FIRST_CLASS_PRODUCTION_SURFACES:
            argv = ["do", surface, "--action", "qa", *argv[2:]]
        else:
            _abort_router(ir.RouterError("usage: kubrick qa <design|script|image|video> ..."))

    if argv[0] == "validate" and len(argv) >= 2:
        # sugar: kubrick validate design|script → surface validate/diagnose
        surface = argv[1]
        if surface == "design":
            argv = ["do", "design", "--action", "validate", *argv[2:]]
        elif surface == "script":
            argv = ["do", "script", "--action", "diagnose", *argv[2:]]
        elif surface in {"image", "video"}:
            argv = ["do", surface, "--action", "qa", *argv[2:]]
        else:
            _abort_router(ir.RouterError("usage: kubrick validate <design|script|image|video> ..."))

    if argv[0] in FIRST_CLASS_PRODUCTION_SURFACES and (len(argv) == 1 or not argv[1].startswith("-") and argv[1] != "do"):
        # sugar: kubrick design create ... → do design --action create ...
        surface = argv[0]
        rest = argv[1:]
        action = None
        if rest and not rest[0].startswith("-"):
            action = rest[0]
            rest = rest[1:]
        argv = ["do", surface, *(["--action", action] if action else []), *rest]

    if argv[0] == "aliases":
        sys.stdout.write(ir.format_aliases())
        raise SystemExit(0)

    if argv[0] == "recipe":
        if len(argv) < 2:
            _abort_router(ir.RouterError("usage: kubrick recipe <name>"))
        try:
            argv = ir.resolve_recipe(argv[1])
        except ir.RouterError as e:
            _abort_router(e)

    # wizard special-case: plan/--run re-dispatch without nesting via ir.resolve
    if _is_wizard_argv(argv):
        import kubrick_wizard as wiz

        raise SystemExit(wiz.main(_wizard_flags(argv)))

    # do <intent> --help / -h → intent help (do not pass --help into scripts)
    if (
        len(argv) >= 2
        and argv[0] == "do"
        and any(tok in {"-h", "--help"} for tok in argv[2:])
    ):
        try:
            sys.stdout.write(ir.format_intent_help(argv[1]))
        except ir.RouterError as e:
            _abort_router(e)
        raise SystemExit(0)

    try:
        call = ir.resolve(argv)
    except ir.RouterError as e:
        if e.message == "HELP":
            sys.stdout.write(ir.format_top_level_help())
            raise SystemExit(0)
        _abort_router(e)

    if (
        call.legacy_name
        and not _is_agent()
        and os.environ.get("KUBRICK_QUIET") != "1"
    ):
        print(
            f"note: `{call.legacy_name}` is a legacy alias; "
            f"prefer `kubrick do {call.intent} --action {call.action}`",
            file=sys.stderr,
        )

    if call.intent == "check" and call.action == "smoke":
        _dispatch_smoke(call)

    result = subprocess.run(
        [PY, str(call.script), *_execution_argv(call)],
        cwd=ROOT,
    )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
