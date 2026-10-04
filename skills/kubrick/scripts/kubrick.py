#!/usr/bin/env python3
"""Kubrick CLI. Implementation: kubrick.cli.

This file shares its name with the ``kubrick`` package in ``src/``. When
``scripts/`` comes before ``src/`` on ``sys.path`` (pytest adds it, and an
editable install or ``PYTHONPATH=src`` puts ``src`` later), ``import kubrick``
can load this file instead of the package. Every shim puts ``src`` first, and
if this file is still imported as ``kubrick`` it hands the name to the package.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parents[1] / "src")
_SCRIPTS = Path(__file__).resolve().parent

if __name__ == "kubrick":
    # Imported by name: put src first and hand the name to the package.
    sys.path[:] = [_SRC] + [item for item in sys.path if item != _SRC]
    del sys.modules["kubrick"]
    sys.modules["kubrick"] = importlib.import_module("kubrick")
else:
    sys.path[:] = [_SRC] + [
        item for item in sys.path
        if item != _SRC and Path(item or ".").resolve() != _SCRIPTS
    ]
    from kubrick.cli import main

    if __name__ == "__main__":
        main()
