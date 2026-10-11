#!/usr/bin/env python3
"""CLI adapter for explicit Kubrick telemetry controls."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parents[1] / "src")
sys.path.insert(0, _SRC)

from kubrick.runtime.telemetry_cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
