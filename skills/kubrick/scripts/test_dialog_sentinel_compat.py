"""dialog-validate still finds the no-dialogue sentinel in artifacts from before 0.27.11."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kubrick.surfaces.surface_script_extra import script_dialog_validate  # noqa: E402

EM = "\u2014"


def _codes(text: str) -> list[str]:
    result = script_dialog_validate(text, "p")
    findings = result.get("findings") or (result.get("result") or {}).get("findings") or []
    return [str(f.get("code")) for f in findings if isinstance(f, dict)]


def test_sentinel_found_with_either_separator() -> None:
    for sep in (":", " " + EM):
        text = "# Compressed script: p\n\nNOT_COMPUTABLE" + sep + " no dialogue evidenced\n"
        assert "DIALOGUE_ABSENT" in _codes(text), sep


def test_no_sentinel_no_finding() -> None:
    assert "DIALOGUE_ABSENT" not in _codes("# Script\n\nA: hello.\nB: hi.\n")
