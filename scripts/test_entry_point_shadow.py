"""scripts/kubrick.py must never shadow the kubrick package (editable install bug, 0.27.0).

With ``pip install -e .`` or ``PYTHONPATH=src``, ``src`` is on ``sys.path`` but
after ``scripts/`` (pytest puts the test directory first). The shims used to add
``src`` only when it was absent, so ``import kubrick.gates`` loaded
``scripts/kubrick.py`` and failed with "'kubrick' is not a package".
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SRC = ROOT / "src"


def _run(code: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, PYTHONPATH=str(SRC))
    return subprocess.run(
        [sys.executable, "-c", code], cwd=str(ROOT), env=env,
        capture_output=True, text=True, timeout=120, check=False,
    )


def test_shim_import_with_src_after_scripts() -> None:
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "import board_image_gate\n"
        "import kubrick\n"
        "assert hasattr(kubrick, '__path__'), kubrick\n"
        "print(board_image_gate.__name__)\n"
    ) % str(SCRIPTS)
    done = _run(code)
    assert done.returncode == 0, done.stderr
    assert "kubrick.gates.board_image_gate" in done.stdout


def test_import_kubrick_by_name_hands_over_to_package() -> None:
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "import kubrick\n"
        "import kubrick.cli\n"
        "assert hasattr(kubrick, '__path__'), kubrick\n"
        "assert %r in sys.path, 'scripts/ must stay on sys.path'\n"
        "print('ok')\n"
    ) % (str(SCRIPTS), str(SCRIPTS))
    done = _run(code)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "ok"


def test_cli_runs_with_src_on_pythonpath() -> None:
    env = dict(os.environ, PYTHONPATH=str(SRC))
    done = subprocess.run(
        [sys.executable, str(SCRIPTS / "kubrick.py"), "--help"], cwd=str(ROOT), env=env,
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert done.returncode == 0, done.stderr
    assert "usage: kubrick" in done.stdout
