"""Hermetic contract tests for the Kubrick optional Hermes skill."""
from __future__ import annotations

import ast
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
_CANDIDATES = [
    _HERE.parents[2] / "optional-skills" / "creative" / "kubrick",
    _HERE.parents[2],
]
SKILL_DIR = next((path for path in _CANDIDATES if (path / "SKILL.md").is_file()), _CANDIDATES[0])


def _frontmatter_text() -> str:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    match = re.search(r"^---\n(.*?)\n---", text, re.DOTALL)
    assert match, "SKILL.md missing YAML frontmatter"
    return match.group(1)


def _scalar(field: str) -> str:
    match = re.search(rf"^{re.escape(field)}: (.+)$", _frontmatter_text(), re.MULTILINE)
    assert match, f"SKILL.md missing single-line {field}"
    return match.group(1).strip()


_MARKETING_WORDS = ("powerful", "comprehensive", "seamless", "advanced")


def test_frontmatter_matches_hermes_contract() -> None:
    skill_bytes = (SKILL_DIR / "SKILL.md").read_bytes()
    assert skill_bytes.startswith(b"---\n"), "frontmatter must start at byte 0"
    description = _scalar("description")
    assert description == "Builds continuity-safe cinematic stories and visuals."
    assert len(description) <= 60
    assert description.endswith(".")
    assert description.count(".") == 1
    assert not any(word in description.lower() for word in _MARKETING_WORDS)
    assert _scalar("name") == "kubrick"
    assert _scalar("version") == (SKILL_DIR / "VERSION").read_text(encoding="utf-8").strip()
    assert _scalar("author") == "Daniel Meyer (scrimshawlife-ctrl), Hermes Agent"
    assert "Zero State Proprietary License" in (SKILL_DIR / "LICENSE").read_text()
    assert _scalar("license") == "LicenseRef-Zero-State-Proprietary-1.0"
    assert _scalar("platforms") == "[linux, macos, windows]"
    frontmatter = _frontmatter_text()
    assert "related_skills: []" in frontmatter
    assert re.search(r"^  hermes:\n    tags:", frontmatter, re.MULTILINE)
    assert "blueprint:" not in frontmatter
    assert "required_environment_variables:" not in frontmatter


def test_skill_uses_modern_section_order() -> None:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    required = [
        "# Kubrick Skill",
        "## When to Use",
        "## Prerequisites",
        "## How to Run",
        "## Quick Reference",
        "## Procedure",
        "## Pitfalls",
        "## Verification",
    ]
    positions = [text.index(heading) for heading in required]
    assert positions == sorted(positions)
    assert "standalone Hermes skill" in text
    assert "${HERMES_SKILL_DIR}" in text
    assert "`terminal`" in text
    assert "[[as_document]]" in text
    assert "NOT_COMPUTABLE" in text
    assert "When Not to Use" in text


@pytest.mark.parametrize(
    "name",
    ["brief.yaml", "symbolic-ledger.yaml", "storyboard-plan.yaml"],
)
def test_storyboard_recipe_fixture_is_shipped(name: str) -> None:
    assert (SKILL_DIR / "examples" / "authority-transfer-storyboard" / name).is_file()


def test_manifest_storyboard_recipe_paths_exist() -> None:
    manifest = json.loads((SKILL_DIR / "kubrick.manifest.yaml").read_text(encoding="utf-8"))
    argv = manifest["recipes"]["storyboard-example"]
    referenced = [arg for arg in argv if arg.startswith("examples/")]
    assert len(referenced) == 3
    assert all((SKILL_DIR / path).is_file() for path in referenced)


def test_router_resolves_storyboard_recipe() -> None:
    path = SKILL_DIR / "scripts" / "intent_router.py"
    spec = importlib.util.spec_from_file_location("kubrick_intent_router", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    argv = module.resolve_recipe("storyboard-example")
    assert argv[:2] == ["do", "compile"]
    assert all((SKILL_DIR / arg).is_file() for arg in argv if arg.startswith("examples/"))


def test_shipped_python_scripts_parse() -> None:
    for path in (SKILL_DIR / "scripts").glob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
