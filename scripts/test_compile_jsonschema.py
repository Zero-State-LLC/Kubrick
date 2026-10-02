#!/usr/bin/env python3
"""Runtime dependency tests for issue #19."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def _shadow_env() -> tuple[tempfile.TemporaryDirectory[str], dict[str, str]]:
    directory = tempfile.TemporaryDirectory()
    shadow = Path(directory.name)
    shadow_text = "raise ImportError('shadowed jsonschema')\n"
    (shadow / "jsonschema.py").write_text(shadow_text, encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(shadow) + os.pathsep + env.get("PYTHONPATH", "")
    env["KUBRICK_DIAGNOSTICS"] = "json"
    return directory, env


def test_missing_jsonschema_is_actionable() -> None:
    directory, env = _shadow_env()
    try:
        result = subprocess.run(
            [PY, str(ROOT / "scripts/kubrick_compile.py")],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
    finally:
        directory.cleanup()
    assert result.returncode == 3, (result.returncode, result.stderr)
    assert "Traceback" not in result.stderr
    assert "Traceback" not in result.stdout
    payload = json.loads(result.stderr)
    assert payload["code"] == "JSONSCHEMA_REQUIRED"
    assert payload["exit_code"] == 3
    assert payload["context"]["package"] == "jsonschema"
    assert "python3 -m pip install -r requirements.txt" in payload["message"]
    assert "jsonschema" in payload["message"]


def test_validate_artifact_names_missing_jsonschema() -> None:
    directory, env = _shadow_env()
    env.pop("KUBRICK_DIAGNOSTICS", None)
    try:
        result = subprocess.run(
            [PY, str(ROOT / "scripts/validate_artifact.py")],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
    finally:
        directory.cleanup()
    assert result.returncode == 1, result.stderr
    assert result.stderr.startswith("jsonschema required")
    assert "python3 -m pip install -r requirements.txt" in result.stderr
    assert "Traceback" not in result.stderr


def test_runtime_dependencies_are_declared() -> None:
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = project.split("[project]", 1)[1].split("[project.optional", 1)[0]
    assert "PyYAML>=6" in block
    assert "jsonschema>=4" in block
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "PyYAML>=6" in requirements
    assert "jsonschema>=4" in requirements
    for name in ("install.sh", "install.ps1"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "requirements.txt" in text
        assert "audit_release_version.py" in text
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "python3 -m pip install -r requirements.txt" in skill
    assert "PyYAML and jsonschema are optional" not in skill


def main() -> None:
    test_missing_jsonschema_is_actionable()
    test_validate_artifact_names_missing_jsonschema()
    test_runtime_dependencies_are_declared()
    print("compile dependency tests: PASS")


if __name__ == "__main__":
    main()
