#!/usr/bin/env python3
"""Optional stdio MCP-like operator surface over the Kubrick CLI.

Does not become authoritative. Weak evidence fails closed. Requires no extra
dependencies beyond the skill's declared Python stack.

Primary tool: kubrick_do → python scripts/kubrick.py do <intent> …

Protocol: newline-delimited JSON-RPC 2.0 messages on stdin/stdout.
Methods: initialize, tools/list, tools/call, ping.

Security: intents/actions are allowlisted from the canonical manifest; args are
flag-validated and path-containing values are bounded to the project/skill roots.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
sys.path.insert(0, str(ROOT / "scripts"))

from io_safety import PathSafetyError, project_root, validate_mcp_tool_args  # noqa: E402
from manifest_contract import load_manifest  # noqa: E402

MANIFEST = load_manifest()
VERSION = str(MANIFEST.get("version", "0.15.0"))
_PROVIDER_LIST = ", ".join(str(name) for name in MANIFEST.get("providers", []))

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


def respond(msg_id: Any, result: Any = None, error: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name != "kubrick_do":
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"unknown tool {name}"}],
        }
    arguments = arguments or {}
    intent = arguments.get("intent")
    if not intent:
        return {
            "isError": True,
            "content": [
                {
                    "type": "text",
                    "text": "kubrick_do requires 'intent' (e.g. adapt, visual, check)",
                }
            ],
            "structuredContent": {
                "status": "NOT_COMPUTABLE",
                "exit_code": 2,
                "fail_closed": True,
            },
        }
    action = arguments.get("action")
    args = arguments.get("args") or []
    if not isinstance(args, list):
        args = [args]

    try:
        cleaned = validate_mcp_tool_args(
            str(intent),
            str(action) if action is not None else None,
            args,
            intents=MANIFEST["intents"],
            root=project_root(),
        )
    except (PathSafetyError, ValueError) as exc:
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"MCP arg policy rejection: {exc}"}],
            "structuredContent": {
                "status": "INVALID_COMMAND",
                "exit_code": 2,
                "fail_closed": True,
                "code": "MCP_ARG_POLICY",
            },
        }

    cli: list[str] = ["do", str(intent)]
    if action:
        cli += ["--action", str(action)]
    cli += cleaned

    proc = subprocess.run(
        [PY, str(ROOT / "scripts/kubrick.py"), *cli],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    text = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
    if proc.returncode != 0:
        return {
            "isError": True,
            "content": [
                {
                    "type": "text",
                    "text": text.strip() or f"tool failed with code {proc.returncode}",
                }
            ],
            "structuredContent": {
                "status": "NOT_COMPUTABLE",
                "exit_code": proc.returncode,
                "fail_closed": True,
            },
        }
    return {
        "isError": False,
        "content": [{"type": "text", "text": text.strip()}],
        "structuredContent": {"status": "OK", "exit_code": 0, "fail_closed": True},
    }


def _request_error(message: object) -> dict[str, Any] | None:
    if not isinstance(message, dict):
        return {"code": -32600, "message": "invalid request"}
    if message.get("jsonrpc") != "2.0":
        return {"code": -32600, "message": "invalid request"}
    method = message.get("method")
    if not isinstance(method, str) or not method:
        return {"code": -32600, "message": "invalid request"}
    return None


def _params_error(message: dict[str, Any]) -> dict[str, Any] | None:
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


def handle(message: dict[str, Any]) -> None:
    method = message.get("method")
    msg_id = message.get("id")
    raw_params = message.get("params")
    params = raw_params if isinstance(raw_params, dict) else {}

    if method == "initialize":
        respond(
            msg_id,
            {
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
            },
        )
        return
    if method == "notifications/initialized":
        return
    if method == "ping":
        respond(msg_id, {})
        return
    if method == "tools/list":
        respond(
            msg_id,
            {
                "tools": [
                    {
                        "name": t["name"],
                        "description": t["description"],
                        "inputSchema": t["inputSchema"],
                    }
                    for t in TOOLS
                ]
            },
        )
        return
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}
        respond(msg_id, call_tool(str(name), arguments))
        return
    if msg_id is not None:
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


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            respond(None, error={"code": -32700, "message": "parse error"})
            continue
        try:
            dispatch(message)
        except Exception as exc:
            msg_id = message.get("id") if isinstance(message, dict) else None
            respond(msg_id, error={"code": -32603, "message": f"internal error: {exc}"})


if __name__ == "__main__":
    main()
