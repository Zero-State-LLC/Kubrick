"""Shared scalar coercion helpers (replaces duplicated private copies)."""

from __future__ import annotations

_BLANK_TOKENS = frozenset({"", "none", "not_computable"})


def as_float(value: object) -> float | None:
    """Return float for int/float/str inputs; None for bool, other types or bad strings."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def as_number(value: object) -> float | None:
    """Return float for real numeric inputs only (strings and bools are rejected)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def is_blank(value: object) -> bool:
    """True for None or textual placeholders that carry no evidence."""
    if value is None:
        return True
    return str(value).strip().casefold() in _BLANK_TOKENS
