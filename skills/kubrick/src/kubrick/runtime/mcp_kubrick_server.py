#!/usr/bin/env python3
"""Optional stdio MCP-like operator surface over the Kubrick CLI.

Does not become authoritative. Weak evidence fails closed. Requires no extra
dependencies beyond the skill's declared Python stack.

Primary tool: kubrick_do → python scripts/kubrick.py do <intent> …

Protocol: newline-delimited JSON-RPC 2.0 messages on stdin/stdout.
Methods: initialize, tools/list, tools/call, ping.

Security: intents/actions are allowlisted from the canonical manifest; args are
flag-validated and path-containing values are bounded to the project/skill roots.
Requests are byte-capped (KUBRICK_MCP_MAX_BYTES), calls are time-bounded
(KUBRICK_MCP_TIMEOUT), and missing runtime dependencies block spawning.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

from kubrick.paths import SKILL_ROOT

ROOT = SKILL_ROOT
PY = sys.executable

import kubrick.runtime.runtime_deps as runtime_deps  # noqa: E402
from kubrick.runtime.io_safety import (  # noqa: E402
    PathSafetyError,
    project_root,
    validate_mcp_tool_args,
)
from kubrick.runtime.manifest_contract import load_manifest  # noqa: E402

JsonDict = dict[str, object]

MANIFEST = load_manifest()
VERSION = str(MANIFEST.get("version", "0.15.0"))
_PROVIDER_LIST = ", ".join(str(name) for name in MANIFEST.get("providers", []))

DEFAULT_MAX_BYTES = 1_048_576
DEFAULT_TIMEOUT_S = 120.0
_DRAIN_CHUNK = 65_536

TOOLS = [
    {
        "name": "kubrick_do",
        "description": (
            "Run a Kubrick intent (compile, retrieve, adapt, visual, learn, check, "
            "design, script, image, video, …). Provider adapters: "
            f"{_PROVIDER_LIST}. The keyframe adapter emits a create_movie payload. "
            "Paths in args must stay inside KUBRICK_PROJECT_DIR (or cwd) / skill out/."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["intent"],
            "properties": {
                "intent": {
                    "type": "string",
                    "enum": sorted(MANIFEST["intents"].keys()),
                },
                "action": {"type": "string"},
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "CLI flags after intent/action, e.g. "
                        '["--provider","keyframe","--packet","p.yaml"]'
                    ),
                },
            },
        },
    }
]


def max_request_bytes() -> int:
    try:
        value = int(os.environ.get("KUBRICK_MCP_MAX_BYTES", ""))
    except ValueError:
        return DEFAULT_MAX_BYTES
    return value if value > 0 else DEFAULT_MAX_BYTES


def call_timeout_s() -> float:
    try:
        value = float(os.environ.get("KUBRICK_MCP_TIMEOUT", ""))
    except ValueError:
        return DEFAULT_TIMEOUT_S
    return value if value > 0 else DEFAULT_TIMEOUT_S


MAX_REQUEST_BYTES = max_request_bytes()
CALL_TIMEOUT_S = call_timeout_s()


def respond(msg_id: object, result: object = None, error: JsonDict | None = None) -> None:
    payload: JsonDict = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def _error_result(text: str, structured: JsonDict | None = None) -> JsonDict:
    result: JsonDict = {"isError": True, "content": [{"type": "text", "text": text}]}
    if structured is not None:
        result["structuredContent"] = structured
    return result


def _policy_error(exc: object) -> JsonDict:
    return _error_result(
        f"MCP arg policy rejection: {exc}",
        {
            "status": "INVALID_COMMAND",
            "exit_code": 2,
            "fail_closed": True,
            "code": "MCP_ARG_POLICY",
        },
    )


def _resolve_action(intent: str, action: object) -> str | None:
    if action:
        return str(action)
    spec = MANIFEST["intents"].get(intent)
    if isinstance(spec, dict):
        default = spec.get("default_action")
        if isinstance(default, str) and default:
            return default
    return None


def _validate(intent: str, action: object, arguments: JsonDict) -> list[str] | JsonDict:
    raw_args = arguments.get("args") or []
    args = raw_args if isinstance(raw_args, list) else [raw_args]
    if intent == "wizard":
        return _policy_error("intent 'wizard' is interactive and not exposed over MCP")
    try:
        return list(
            validate_mcp_tool_args(
                intent,
                str(action) if action is not None else None,
                args,
                intents=MANIFEST["intents"],
                root=project_root(),
            )
        )
    except (PathSafetyError, ValueError) as exc:
        return _policy_error(exc)


def _deps_error(intent: str, action: str) -> JsonDict | None:
    needed = runtime_deps.action_requirements(MANIFEST, intent, action)
    missing = runtime_deps.missing_modules(needed)
    if not missing:
        return None
    return _error_result(
        f"missing runtime dependencies for {intent}.{action}: {', '.join(missing)}",
        {
            "status": "DEPENDENCY_UNAVAILABLE",
            "code": "DEPENDENCY_MISSING",
            "exit_code": 4,
            "fail_closed": True,
            "missing": list(missing),
        },
    )


def _run_cli(cli: list[str]) -> JsonDict:
    timeout = call_timeout_s()
    try:
        proc = subprocess.run(
            [PY, str(ROOT / "scripts/kubrick.py"), *cli],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return _error_result(
            f"tool call exceeded {timeout}s",
            {
                "status": "NOT_COMPUTABLE",
                "code": "MCP_TIMEOUT",
                "exit_code": 1,
                "fail_closed": True,
                "timeout_s": timeout,
            },
        )
    text = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
    if proc.returncode != 0:
        return _error_result(
            text.strip() or f"tool failed with code {proc.returncode}",
            {"status": "NOT_COMPUTABLE", "exit_code": proc.returncode, "fail_closed": True},
        )
    return {
        "isError": False,
        "content": [{"type": "text", "text": text.strip()}],
        "structuredContent": {"status": "OK", "exit_code": 0, "fail_closed": True},
    }


def call_tool(name: str, arguments: JsonDict) -> JsonDict:
    if name != "kubrick_do":
        return _error_result(f"unknown tool {name}")
    arguments = arguments or {}
    raw_intent = arguments.get("intent")
    if not raw_intent:
        return _error_result(
            "kubrick_do requires 'intent' (e.g. adapt, visual, check)",
            {"status": "NOT_COMPUTABLE", "exit_code": 2, "fail_closed": True},
        )
    intent = str(raw_intent)
    raw_action = arguments.get("action")
    cleaned = _validate(intent, raw_action, arguments)
    if isinstance(cleaned, dict):
        return cleaned
    action = _resolve_action(intent, raw_action)
    if action is None:
        return _error_result(
            f"intent {intent!r} has no default action; 'action' is required",
            {
                "status": "INVALID_COMMAND",
                "code": "MCP_ACTION_REQUIRED",
                "exit_code": 2,
                "fail_closed": True,
            },
        )
    deps_problem = _deps_error(intent, action)
    if deps_problem is not None:
        return deps_problem
    return _run_cli(["do", intent, "--action", action, *cleaned])


def _request_error(message: object) -> JsonDict | None:
    if not isinstance(message, dict):
        return {"code": -32600, "message": "invalid request"}
    if message.get("jsonrpc") != "2.0":
        return {"code": -32600, "message": "invalid request"}
    method = message.get("method")
    if not isinstance(method, str) or not method:
        return {"code": -32600, "message": "invalid request"}
    return None


def _params_error(message: JsonDict) -> JsonDict | None:
    raw = message.get("params")
    if "params" in message and raw is not None and not isinstance(raw, dict):
        return {"code": -32602, "message": "invalid params"}
    if message.get("method") != "tools/call":
        return None
    params = raw if isinstance(raw, dict) else {}
    if not isinstance(params.get("name"), str):
        return {"code": -32602, "message": "invalid params"}
    arguments = params.get("arguments")
    if "arguments" in params and arguments is not None and not isinstance(arguments, dict):
        return {"code": -32602, "message": "invalid params"}
    return None


def _initialize_result() -> JsonDict:
    return {
        "protocolVersion": "2024-11-05",
        "capabilities": {"tools": {}},
        "serverInfo": {"name": "kubrick-operators", "version": VERSION},
        "instructions": (
            "Optional Kubrick operator surface. "
            "Use kubrick_do with intent and optional action/args. "
            "CLI remains authoritative for local work. "
            "Forge remains canonical for committed project state. "
            "Fail closed on weak evidence. "
            "Path args must remain inside KUBRICK_PROJECT_DIR/cwd; "
            "writes into skill references/schemas/scripts are rejected."
        ),
    }


def _tools_list() -> JsonDict:
    return {
        "tools": [
            {
                "name": t["name"],
                "description": t["description"],
                "inputSchema": t["inputSchema"],
            }
            for t in TOOLS
        ]
    }


def handle(message: JsonDict) -> None:
    method = message.get("method")
    msg_id = message.get("id")
    raw_params = message.get("params")
    params = raw_params if isinstance(raw_params, dict) else {}

    if method == "initialize":
        respond(msg_id, _initialize_result())
    elif method == "notifications/initialized":
        return
    elif method == "ping":
        respond(msg_id, {})
    elif method == "tools/list":
        respond(msg_id, _tools_list())
    elif method == "tools/call":
        arguments = params.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}
        respond(msg_id, call_tool(str(params.get("name")), arguments))
    elif msg_id is not None:
        respond(msg_id, error={"code": -32601, "message": f"Method not found: {method}"})


def dispatch(message: object) -> None:
    problem = _request_error(message)
    if problem is not None:
        msg_id = message.get("id") if isinstance(message, dict) and "id" in message else None
        respond(msg_id, error=problem)
        return
    if not isinstance(message, dict):
        respond(None, error={"code": -32600, "message": "invalid request"})
        return
    params_problem = _params_error(message)
    if params_problem is not None:
        respond(message.get("id"), error=params_problem)
        return
    handle(message)


def _drain_line() -> None:
    while True:
        chunk = sys.stdin.buffer.readline(_DRAIN_CHUNK)
        if not chunk or chunk.endswith(b"\n"):
            return


def _process_line(text: str) -> None:
    try:
        message = json.loads(text)
    except json.JSONDecodeError:
        respond(None, error={"code": -32700, "message": "parse error"})
        return
    try:
        dispatch(message)
    except Exception as exc:
        msg_id = message.get("id") if isinstance(message, dict) else None
        respond(msg_id, error={"code": -32603, "message": f"internal error: {exc}"})


def main() -> None:
    while True:
        cap = max_request_bytes()
        raw = sys.stdin.buffer.readline(cap + 1)
        if raw == b"":
            return
        if len(raw) > cap and not raw.endswith(b"\n"):
            _drain_line()
            respond(None, error={"code": -32600, "message": f"request exceeds {cap} bytes"})
            continue
        try:
            text = raw.decode("utf-8").strip()
        except UnicodeDecodeError:
            respond(None, error={"code": -32700, "message": "parse error"})
            continue
        if text:
            _process_line(text)


if __name__ == "__main__":
    main()
