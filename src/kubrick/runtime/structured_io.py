"""Shared JSON/YAML mapping loader."""

from __future__ import annotations

import json
from pathlib import Path


def load_mapping(path: str | Path) -> dict[str, object]:
    """Load a JSON (.json) or YAML (anything else) file that must contain a mapping."""
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    result: object
    if file_path.suffix.lower() == ".json":
        result = json.loads(text)
    else:
        from kubrick.runtime.runtime_deps import yaml_load

        result = yaml_load(text)
    if not result:
        return {}
    if not isinstance(result, dict):
        raise ValueError(f"{path} must contain a mapping")
    return {str(key): val for key, val in result.items()}
