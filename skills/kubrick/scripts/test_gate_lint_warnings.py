from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from kubrick.gates.jev_gate import gate_prompts, lint_warnings  # noqa: E402


def _prompts(text: str) -> list[dict[str, str]]:
    return [{"shot": "s1", "prompt": text}]


def test_lettering_warning_is_reported() -> None:
    """A bare hand prompt reports the unlocked lettering warning."""
    warnings = lint_warnings({}, _prompts("A hand holds a mug."))
    assert any(w["code"] == "PROP_LETTERING_UNLOCKED" and w["shot"] == "s1" for w in warnings)


def test_gate_surfaces_warning_without_blocking() -> None:
    """The gate result carries lint_warnings and stays non-blocking."""
    result = gate_prompts(
        {},
        _prompts("A hand holds a mug."),
        override=True,
        override_source="test",
    )
    codes = [w["code"] for w in result["lint_warnings"]]
    assert "PROP_LETTERING_UNLOCKED" in codes
    assert not result.get("blocks_spend")


def test_clean_prompt_has_no_warning_key() -> None:
    """Clean prompt text leaves the lint_warnings key off the result."""
    result = gate_prompts(
        {},
        _prompts("An unbranded mug with no lettering sits on a table."),
        override=True,
        override_source="test",
    )
    assert "lint_warnings" not in result


def test_duplicates_collapse() -> None:
    """Repeated findings on the same code and shot collapse to one entry."""
    prompts = _prompts("A hand holds a mug.") + _prompts("A hand holds a mug.")
    warnings = lint_warnings({}, prompts)
    assert [w["code"] for w in warnings].count("PROP_LETTERING_UNLOCKED") == 1


if __name__ == "__main__":
    test_lettering_warning_is_reported()
    test_gate_surfaces_warning_without_blocking()
    test_clean_prompt_has_no_warning_key()
    test_duplicates_collapse()
    print("ok")
