#!/usr/bin/env python3
"""Audit U2: runtime artifacts stay project-local and failures fail closed."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parent
RETRIEVE = SCRIPTS / "retrieve_symbolic_patterns_registry.py"
GOVERN = SCRIPTS / "govern_correction_iteration.py"
REFERENCES_USAGE = REPO / "references" / "usage"
HAS_YAML = importlib.util.find_spec("yaml") is not None

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
_SRC = str(REPO / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

GOOD_BRIEF = {
    "dramatic_problem": (
        "authority remains active after the leader exits because access and "
        "geometry preserve the system"
    ),
    "desired_state_change": "personal command becomes institutional pressure",
    "character_pressure": "a subordinate receives access while the former authority is excluded",
}
WEAK_BRIEF = {"dramatic_problem": "zzqx", "symbolic_ledger": {"saturation_score": 0.99}}


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _run(
    script: Path, args: list[str], cwd: Path, project_dir: Path
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["KUBRICK_PROJECT_DIR"] = str(project_dir)
    env["KUBRICK_DIAGNOSTICS"] = "json"
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _snapshot(root: Path) -> list[str] | None:
    if not root.exists():
        return None
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def _receipt_status(stdout: str) -> str:
    import yaml

    data = yaml.safe_load(stdout)
    if not isinstance(data, dict):
        return ""
    receipt = data.get("retrieval_receipt")
    if not isinstance(receipt, dict):
        return ""
    status = receipt.get("status")
    return status if isinstance(status, str) else ""


@unittest.skipUnless(HAS_YAML, "PyYAML not installed")
class RetrievalArtifactTests(unittest.TestCase):
    def test_receipts_written_under_project_out(self) -> None:
        before = _snapshot(REFERENCES_USAGE)
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            brief = _write_json(tmp / "brief.json", dict(GOOD_BRIEF))
            proc = _run(RETRIEVE, ["--brief", str(brief)], cwd=tmp, project_dir=tmp)
            self.assertIn(proc.returncode, (0, 4), msg=proc.stderr)
            receipts = tmp / "out" / "kubrick" / "retrieval" / "receipts"
            self.assertTrue(receipts.is_dir(), msg=proc.stderr)
            written = [p for p in receipts.iterdir() if p.is_file()]
            self.assertTrue(written, msg="no receipt files written")
        self.assertEqual(before, _snapshot(REFERENCES_USAGE))

    def test_weak_brief_is_not_computable(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            brief = _write_json(tmp / "weak.json", dict(WEAK_BRIEF))
            proc = _run(RETRIEVE, ["--brief", str(brief)], cwd=tmp, project_dir=tmp)
            status = _receipt_status(proc.stdout)
            self.assertEqual(status, "NOT_COMPUTABLE", msg=proc.stdout + proc.stderr)
            self.assertEqual(proc.returncode, 4, msg=proc.stderr)

    def test_project_dir_is_file_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            brief = _write_json(tmp / "brief.json", dict(GOOD_BRIEF))
            not_a_dir = tmp / "project-file"
            not_a_dir.write_text("not a directory\n", encoding="utf-8")
            proc = _run(RETRIEVE, ["--brief", str(brief)], cwd=tmp, project_dir=not_a_dir)
            self.assertEqual(proc.returncode, 4, msg=proc.stdout + proc.stderr)
            self.assertIn("ARTIFACT_DIR_UNWRITABLE", proc.stderr)


class GovernanceTests(unittest.TestCase):
    def test_not_computable_report_aborts(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            report = _write_json(tmp / "report.json", {"overall_status": "NOT_COMPUTABLE"})
            output = tmp / "x.yaml"
            args = ["--current", str(report), "--iteration", "1", "--output", str(output)]
            proc = _run(GOVERN, args, cwd=tmp, project_dir=tmp)
            self.assertEqual(proc.returncode, 4, msg=proc.stdout + proc.stderr)
            self.assertIn("FIDELITY_NOT_COMPUTABLE", proc.stderr)


class ArtifactPathsUnitTests(unittest.TestCase):
    def test_kubrick_out_dir_creates_project_local_dir(self) -> None:
        import artifact_paths

        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            with mock.patch.dict(os.environ, {"KUBRICK_PROJECT_DIR": str(tmp)}):
                path = artifact_paths.kubrick_out_dir("a", "b")
            expected = (tmp / "out" / "kubrick" / "a" / "b").resolve()
            self.assertEqual(path.resolve(), expected)
            self.assertTrue(path.is_dir())


class DispatcherProjectRootTests(unittest.TestCase):
    def test_child_env_records_caller_cwd(self) -> None:
        from kubrick.cli import _child_env

        with tempfile.TemporaryDirectory() as tmp:
            old = os.getcwd()
            try:
                os.chdir(tmp)
                with mock.patch.dict(os.environ, {"KUBRICK_CALLER_CWD": ""}):
                    env = _child_env()
            finally:
                os.chdir(old)
            self.assertEqual(Path(env["KUBRICK_CALLER_CWD"]).resolve(), Path(tmp).resolve())
            self.assertNotEqual(env.get("KUBRICK_PROJECT_DIR"), tmp)

    def test_out_dir_uses_caller_cwd_without_project_dir(self) -> None:
        import artifact_paths

        with tempfile.TemporaryDirectory() as tmp:
            env = {"KUBRICK_PROJECT_DIR": "", "KUBRICK_CALLER_CWD": tmp}
            with mock.patch.dict(os.environ, env):
                path = artifact_paths.kubrick_out_dir("retrieval")
            self.assertEqual(path, (Path(tmp) / "out" / "kubrick" / "retrieval").resolve())

    def test_project_dir_wins_over_caller_cwd(self) -> None:
        import artifact_paths

        with tempfile.TemporaryDirectory() as proj, tempfile.TemporaryDirectory() as caller:
            env = {"KUBRICK_PROJECT_DIR": proj, "KUBRICK_CALLER_CWD": caller}
            with mock.patch.dict(os.environ, env):
                path = artifact_paths.kubrick_out_dir()
            self.assertEqual(path, (Path(proj) / "out" / "kubrick").resolve())


if __name__ == "__main__":
    unittest.main()
