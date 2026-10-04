#!/usr/bin/env python3
"""Entry point. Implementation: kubrick.providers.provider_capabilities."""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

if __name__ == "__main__":
    import runpy  # noqa: E402

    runpy.run_module("kubrick.providers.provider_capabilities", run_name="__main__")
else:
    import kubrick.providers.provider_capabilities as _impl  # noqa: E402

    _loaded = sys.modules.get(__name__)
    if _loaded is not None and _loaded is not _impl:
        for _key, _value in vars(_impl).items():
            if _key.startswith("__") and _key.endswith("__"):
                continue
            setattr(_loaded, _key, _value)
    sys.modules[__name__] = _impl
