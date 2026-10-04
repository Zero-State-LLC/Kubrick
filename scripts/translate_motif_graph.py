#!/usr/bin/env python3
"""Entry point. Implementation: kubrick.adapters.translate_motif_graph."""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parents[1] / "src")
if sys.path[:1] != [_SRC]:  # src first, or scripts/kubrick.py shadows the package
    while _SRC in sys.path:
        sys.path.remove(_SRC)
    sys.path.insert(0, _SRC)

if __name__ == "__main__":
    import runpy  # noqa: E402

    runpy.run_module("kubrick.adapters.translate_motif_graph", run_name="__main__")
else:
    import kubrick.adapters.translate_motif_graph as _impl  # noqa: E402

    _loaded = sys.modules.get(__name__)
    if _loaded is not None and _loaded is not _impl:
        for _key, _value in vars(_impl).items():
            if _key.startswith("__") and _key.endswith("__"):
                continue
            setattr(_loaded, _key, _value)
    sys.modules[__name__] = _impl
