#!/usr/bin/env python3
"""Turn a missing PyYAML or jsonschema import into DEPENDENCY_MISSING."""
from __future__ import annotations

import importlib.util
from collections.abc import Iterable, Mapping
from types import ModuleType

from kubrick.runtime.diagnostics import SCHEMA_VERSION, abort

INSTALL = "python3 -m pip install -r requirements.txt"
_PACKAGES = {"yaml": "PyYAML", "jsonschema": "jsonschema"}


def package_name(module: str) -> str:
    """Distribution name that provides ``module``."""
    return _PACKAGES.get(module, module)


def dependency_missing(module: str) -> dict[str, object]:
    """Diagnostic for a validation runtime package that is not installed."""
    package = package_name(module)
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


def missing_modules(modules: Iterable[str]) -> list[str]:
    """Sorted unique names from ``modules`` that cannot be imported (no import side effects)."""
    missing: set[str] = set()
    for module in modules:
        try:
            spec = importlib.util.find_spec(module)
        except (ImportError, ValueError):
            spec = None
        if spec is None:
            missing.add(module)
    return sorted(missing)


def action_requirements(manifest: Mapping[str, object], intent: str, action: str) -> list[str]:
    """Modules the routed ``intent.action`` imports at module level, per the manifest."""
    table = manifest.get("action_requirements")
    if not isinstance(table, dict):
        return []
    entry = table.get(f"{intent}.{action}")
    if not isinstance(entry, list):
        return []
    return [module for module in entry if isinstance(module, str)]


def check_action(manifest: Mapping[str, object], intent: str, action: str) -> None:
    """Abort with DEPENDENCY_MISSING (exit 4) before dispatching an action that cannot import."""
    missing = missing_modules(action_requirements(manifest, intent, action))
    if not missing:
        return
    diag = dependency_missing(missing[0])
    context = diag.get("context")
    merged: dict[str, object] = dict(context) if isinstance(context, dict) else {}
    merged.update({"intent": intent, "action": action, "missing": missing})
    diag["context"] = merged
    abort(diag)
    raise SystemExit(4)


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
