#!/usr/bin/env python3
"""Kubrick CLI. Implementation: kubrick.cli."""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
_scripts = Path(__file__).resolve().parent
sys.path[:] = [item for item in sys.path if Path(item).resolve() != _scripts.resolve()]
sys.path.insert(0, str(_SRC))

from kubrick.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
