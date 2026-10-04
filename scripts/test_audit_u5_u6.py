#!/usr/bin/env python3
"""Audit tests for #65 (runtime dependency gating) and #66 (MCP hardening)."""
from __future__ import annotations

import ast
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
TRACKED = {"yaml", "jsonschema"}
HAS_YAML = find_spec("yaml") is not None
HAS_JSONSCHEMA = find_spec("jsonschema") is not None

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
_SRC = str(REPO / "src")
if sys.path[:1] != [_SRC]:  # src first, or scripts/kubrick.py shadows the package
    while _SRC in sys.path:
        sys.path.remove(_SRC)
    sys.path.insert(0, _SRC)

from kubrick.paths import implementation_of  # noqa: E402


def _manifest() -> dict[str, object]:
    data = json.loads((REPO / "kubrick.manifest.yaml").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _handler_raises(handler: ast.ExceptHandler) -> bool:
    return any(isinstance(node, ast.Raise) for node in ast.walk(handler))


def _top_level_imports(body: list[ast.stmt]) -> list[str]:
    names: list[str] = []
    for node in body:
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                names.append(node.module)
        elif isinstance(node, ast.Try):
            if node.handlers and all(_handler_raises(h) for h in node.handlers):
                names += _top_level_imports(node.body)
        elif isinstance(node, ast.If):
            names += _top_level_imports(node.body) + _top_level_imports(node.orelse)
    return names


def _local_module(name: str) -> Path | None:
    if name.startswith("kubrick."):
        path = REPO / "src" / Path(*name.split(".")).with_suffix(".py")
        return path if path.is_file() else None
    flat = SCRIPTS / f"{name}.py"
    return flat if flat.is_file() else None


def _deps_of(script: Path, seen: set[Path]) -> set[str]:
    if script.is_file():
        script = implementation_of(script)
    if script in seen or not script.is_file():
        return set()
    seen.add(script)
    tree = ast.parse(script.read_text(encoding="utf-8"))
    found: set[str] = set()
    for name in _top_level_imports(tree.body):
        top = name.split(".")[0]
        if top in TRACKED:
            found.add(top)
            continue
        nxt = _local_module(name) or _local_module(top)
        if nxt is not None:
            found |= _deps_of(nxt, seen)
    return found


def _run_py(code: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, "-c", code], cwd=REPO, env=env, text=True, capture_output=True
    )


def _last_json(text: str) -> dict[str, object]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        lines = [ln for ln in text.splitlines() if ln.strip()]
        data = json.loads(lines[-1])
    assert isinstance(data, dict)
    return data


class ManifestRequirementsTest(unittest.TestCase):
    def test_manifest_matches_module_level_imports(self) -> None:
        manifest = _manifest()
        intents = manifest["intents"]
        assert isinstance(intents, dict)
        detected: dict[str, list[str]] = {}
        for intent, spec in intents.items():
            for action, script in (spec.get("actions") or {}).items():
                deps = _deps_of(SCRIPTS / str(script), set())
                if deps:
                    detected[f"{intent}.{action}"] = sorted(deps)
        declared_raw = manifest.get("action_requirements") or {}
        assert isinstance(declared_raw, dict)
        declared = {k: sorted(v) for k, v in declared_raw.items() if v}
        self.assertEqual(detected, declared)

    def test_validate_manifest_rejects_bad_requirements(self) -> None:
        from manifest_contract import validate_manifest

        for bad in ({"nope.x": ["yaml"]}, {"check.artifact": ["numpy"]}):
            data = copy.deepcopy(_manifest())
            data["action_requirements"] = bad
            self.assertTrue(validate_manifest(data, root=REPO), bad)


class DispatchGateTest(unittest.TestCase):
    def test_ledger_blocked_without_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            argv = ["kubrick.py", "do", "ledger", "init",
                    "--project-id", "x", "--out", str(Path(tmp) / "l.yaml")]
            code = (
                "import runpy,sys; sys.modules['yaml']=None; "
                f"sys.argv={argv!r}; "
                f"runpy.run_path({str(SCRIPTS / 'kubrick.py')!r}, run_name='__main__')"
            )
            proc = _run_py(code, {"KUBRICK_DIAGNOSTICS": "json"})
        self.assertEqual(proc.returncode, 4, proc.stderr)
        diag = _last_json(proc.stderr)
        self.assertEqual(diag.get("code"), "DEPENDENCY_MISSING")
        context = diag.get("context")
        assert isinstance(context, dict)
        self.assertEqual(context.get("intent"), "ledger")


class CheckDepsTest(unittest.TestCase):
    def test_normal_run(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "check_deps.py")],
            cwd=REPO, text=True, capture_output=True,
        )
        expected = 0 if HAS_YAML and HAS_JSONSCHEMA else 3
        self.assertEqual(proc.returncode, expected, proc.stderr)
        report = _last_json(proc.stdout)
        self.assertEqual(report["status"], "READY" if expected == 0 else "DEGRADED")

    def test_without_jsonschema(self) -> None:
        code = (
            "import runpy,sys; sys.modules['jsonschema']=None; "
            "sys.argv=['check_deps.py']; "
            f"runpy.run_path({str(SCRIPTS / 'check_deps.py')!r}, run_name='__main__')"
        )
        proc = _run_py(code)
        self.assertEqual(proc.returncode, 3, proc.stderr)
        blocked = _last_json(proc.stdout)["blocked_actions"]
        assert isinstance(blocked, (list, dict))
        self.assertIn("check.artifact", blocked)


class McpHarness:
    def __init__(self, env_extra: dict[str, str] | None = None) -> None:
        self.env = dict(os.environ)
        self.env.update(env_extra or {})

    def run(self, lines: list[bytes]) -> list[dict[str, object]]:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "mcp_kubrick_server.py")],
            cwd=REPO, env=self.env, input=b"".join(ln + b"\n" for ln in lines),
            capture_output=True, timeout=300,
        )
        out: list[dict[str, object]] = []
        for raw in proc.stdout.decode("utf-8").splitlines():
            if raw.strip():
                out.append(json.loads(raw))
        return out


def _req(msg_id: int, method: str, params: dict[str, object] | None = None) -> bytes:
    msg: dict[str, object] = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        msg["params"] = params
    return json.dumps(msg).encode("utf-8")


def _call(msg_id: int, arguments: dict[str, object]) -> bytes:
    return _req(msg_id, "tools/call", {"name": "kubrick_do", "arguments": arguments})


def _result(resp: dict[str, object]) -> dict[str, object]:
    result = resp.get("result")
    assert isinstance(result, dict), resp
    return result


def _structured(resp: dict[str, object]) -> dict[str, object]:
    sc = _result(resp).get("structuredContent")
    assert isinstance(sc, dict), resp
    return sc


@unittest.skipUnless(HAS_YAML, "server manifest tooling expects yaml stack")
class McpServerTest(unittest.TestCase):
    def test_basic_methods(self) -> None:
        resps = McpHarness().run([_req(1, "initialize", {}), _req(2, "tools/list"),
                                  _req(3, "ping")])
        self.assertEqual([r.get("id") for r in resps], [1, 2, 3])
        self.assertIn("serverInfo", _result(resps[0]))
        self.assertTrue(_result(resps[1])["tools"])
        self.assertEqual(_result(resps[2]), {})

    def test_oversized_request(self) -> None:
        pad = "x" * 1000
        big = json.dumps({"jsonrpc": "2.0", "id": 9, "method": "ping", "p": pad}).encode()
        resps = McpHarness({"KUBRICK_MCP_MAX_BYTES": "256"}).run([big, _req(2, "ping")])
        self.assertEqual(len(resps), 2, resps)
        err = resps[0].get("error")
        assert isinstance(err, dict)
        self.assertEqual(err["code"], -32600)
        self.assertEqual(resps[1].get("id"), 2)
        self.assertEqual(_result(resps[1]), {})

    def test_unknown_action_rejected(self) -> None:
        resps = McpHarness().run([_call(1, {"intent": "check", "action": "nope_zz"})])
        result = _result(resps[0])
        self.assertTrue(result["isError"])
        self.assertIn("MCP arg policy", json.dumps(result["content"]))

    def test_timeout(self) -> None:
        resps = McpHarness({"KUBRICK_MCP_TIMEOUT": "0.001"}).run(
            [_call(1, {"intent": "check", "action": "manifest"})]
        )
        self.assertEqual(_structured(resps[0]).get("code"), "MCP_TIMEOUT")

    def test_check_manifest_ok(self) -> None:
        resps = McpHarness().run([_call(1, {"intent": "check", "action": "manifest"})])
        self.assertFalse(_result(resps[0])["isError"], resps[0])


if __name__ == "__main__":
    unittest.main()
