#!/usr/bin/env python3
"""Turn a missing PyYAML or jsonschema import into DEPENDENCY_MISSING."""
from __future__ import annotations

import importlib
from types import ModuleType

from diagnostics import SCHEMA_VERSION, abort

INSTALL = "python3 -m pip install -r requirements.txt"
_PACKAGES = {"yaml": "PyYAML", "jsonschema": "jsonschema"}


def dependency_missing(module: str) -> dict[str, object]:
    """Diagnostic for a validation runtime package that is not installed."""
    package = _PACKAGES.get(module, module)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "DEPENDENCY_UNAVAILABLE",
        "code": "DEPENDENCY_MISSING",
        "exit_code": 4,
        "message": f"{package} is required; install it with `{INSTALL}`",
        "reason_vector": ["DEPENDENCY_MISSING"],
        "context": {"package": package, "module": module, "install": INSTALL},
        "recoverable": True,
    }


def require_module(module: str) -> ModuleType:
    """Import ``module`` or abort with DEPENDENCY_MISSING (exit 4)."""
    try:
        candidate = importlib.import_module(module)
    except ImportError:
        candidate = None
    if not isinstance(candidate, ModuleType):
        abort(dependency_missing(module))
        raise SystemExit(4)
    return candidate


def yaml_load(text: str) -> object:
    """``yaml.safe_load`` or DEPENDENCY_MISSING."""
    return getattr(require_module("yaml"), "safe_load")(text)


def yaml_dump(data: object, *, sort_keys: bool = False) -> str:
    """``yaml.safe_dump`` or DEPENDENCY_MISSING."""
    dumped = getattr(require_module("yaml"), "safe_dump")(data, sort_keys=sort_keys)
    if not isinstance(dumped, str):
        abort(dependency_missing("yaml"))
        raise SystemExit(4)
    return dumped
