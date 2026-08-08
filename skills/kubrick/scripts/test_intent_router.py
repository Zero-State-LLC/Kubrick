# scripts/test_intent_router.py
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import intent_router as ir
from manifest_contract import load_manifest

PY = sys.executable

EXPECTED_INTENTS = {
    "compile", "retrieve", "ledger", "design", "script", "image", "video",
    "storyboard", "adapt", "visual", "learn", "check", "operate", "mcp", "bundle",
    "wizard",
}

REQUIRED_LEGACY = {
    "compile", "retrieve", "ledger", "design-build", "design-create",
    "design-improve", "script-create", "script-improve", "image-prompt",
    "video-shot", "storyboard-propagate", "storyboard-compare",
    "adapter-build", "adapt-provider", "adapt-grok", "adapt-flux",
    "adapt-sd3", "adapt-midjourney", "visual-normalize", "visual-compare",
    "visual-correct", "correction-govern", "closed-loop-qa", "outcome-record",
    "evolution-propose", "forge-signals", "validate-skill", "validate-corpus",
    "coverage", "artifact-validate", "repeatability", "eval", "operator",
    "mcp-server", "grok-review-bundle",
    "create", "revise", "inspect", "validate",
}


def test_intent_count_and_names():
    assert set(ir.INTENT_REGISTRY) == EXPECTED_INTENTS


def test_router_is_derived_from_canonical_manifest():
    manifest = load_manifest()
    assert set(ir.INTENT_REGISTRY) == set(manifest["intents"])
    assert set(ir.ALIAS_TABLE) == set(manifest["legacy_aliases"])
    assert ir.RECIPES == manifest["recipes"]
    for name, spec in ir.INTENT_REGISTRY.items():
        declared = manifest["intents"][name]
        assert spec.description == declared["description"]
        assert spec.actions == declared["actions"]
        assert spec.default_action == declared["default_action"]


def test_every_required_legacy_alias_exists_and_resolves():
    assert REQUIRED_LEGACY <= set(ir.ALIAS_TABLE)
    for name, alias in ir.ALIAS_TABLE.items():
        assert alias.intent in ir.INTENT_REGISTRY, name
        assert alias.action in ir.INTENT_REGISTRY[alias.intent].actions, name


def test_first_class_surface_matrix():
    cases = {
        ("design", "improve"): "design_surface.py",
        ("script", "diagnose"): "script_surface.py",
        ("image", "sequence"): "image_surface.py",
        ("video", "motion"): "video_surface.py",
    }
    for (intent, action), script_name in cases.items():
        call = ir.resolve(["do", intent, "--action", action, "--brief", "test"])
        assert call.intent == intent
        assert call.action == action
        assert call.script.name == script_name
        assert call.argv == ["--brief", "test"]


def test_first_class_defaults():
    expected = {
        "design": "create",
        "script": "create",
        "image": "prompt",
        "video": "shot",
    }
    for intent, action in expected.items():
        call = ir.resolve(["do", intent, "--brief", "test"])
        assert call.action == action


def test_first_class_legacy_aliases():
    cases = {
        "design-improve": ("design", "improve", "design_surface.py"),
        "script-create": ("script", "create", "script_surface.py"),
        "image-prompt": ("image", "prompt", "image_surface.py"),
        "video-shot": ("video", "shot", "video_surface.py"),
    }
    for alias, expected in cases.items():
        call = ir.resolve([alias, "--brief", "test"])
        assert (call.intent, call.action, call.script.name) == expected


def test_resolve_do_adapt_provider():
    call = ir.resolve([
        "do", "adapt", "--action", "provider", "--provider", "flux",
        "--packet", "p.yaml", "--output", "o.yaml",
    ])
    assert call.script.name == "adapt_provider.py"
    assert call.argv == ["--provider", "flux", "--packet", "p.yaml", "--output", "o.yaml"]


def test_ledger_passthrough_action():
    call = ir.resolve(["ledger", "audit", "--ledger", "L.yaml"])
    assert call.intent == "ledger"
    assert call.action == "audit"
    assert call.argv[0] == "audit"


def test_unknown_intent_fails_closed():
    try:
        ir.resolve(["do", "nope"])
        raise AssertionError("expected RouterError")
    except ir.RouterError as exc:
        assert exc.exit_code == 2


def test_help_lists_first_class_surfaces():
    text = ir.format_top_level_help()
    for intent in ("design", "script", "image", "video"):
        assert intent in text
    assert "adapt-flux" not in text


def test_recipes_resolve():
    for recipe, intent in {
        "storyboard-example": "compile",
        "design-improvement": "design",
        "script-diagnosis": "script",
        "image-prompt": "image",
        "video-shot": "video",
    }.items():
        assert ir.resolve(ir.resolve_recipe(recipe)).intent == intent


def test_entrypoint_forwards_surface_action():
    brief = (
        "dramatic_problem: badge changes hands\n"
        "desired_state_change: access transfers\n"
        "character_pressure: outsider waits"
    )
    proc = subprocess.run(
        [PY, str(ROOT / "scripts/kubrick.py"), "do", "video", "--action", "shot", "--brief", brief],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr
    artifact = json.loads(proc.stdout)
    assert artifact["surface"] == "video"
    assert artifact["action"] == "shot"
    shot = artifact["result"]["shot"]
    assert shot["start_state"] and shot["end_state"]
    assert "continuity_invariants" in shot


def test_surface_fails_closed_without_evidence():
    proc = subprocess.run(
        [PY, str(ROOT / "scripts/kubrick.py"), "do", "image", "--action", "qa"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 4
    artifact = json.loads(proc.stdout)
    assert artifact["status"] == "NOT_COMPUTABLE"
    assert artifact["diagnostic"]["code"] == "INSUFFICIENT_EVIDENCE"


def test_mcp_tools_list_includes_only_kubrick_do():
    req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n"
    proc = subprocess.run(
        [PY, str(ROOT / "scripts/mcp_kubrick_server.py")],
        input=req,
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0
    listed = json.loads(proc.stdout.strip().splitlines()[0])
    assert {tool["name"] for tool in listed["result"]["tools"]} == {"kubrick_do"}


def main():
    test_intent_count_and_names()
    test_router_is_derived_from_canonical_manifest()
    test_every_required_legacy_alias_exists_and_resolves()
    test_first_class_surface_matrix()
    test_first_class_defaults()
    test_first_class_legacy_aliases()
    test_resolve_do_adapt_provider()
    test_ledger_passthrough_action()
    test_unknown_intent_fails_closed()
    test_help_lists_first_class_surfaces()
    test_recipes_resolve()
    test_entrypoint_forwards_surface_action()
    test_surface_fails_closed_without_evidence()
    test_mcp_tools_list_includes_only_kubrick_do()
    print("intent_router unit: first-class production surfaces PASS")


if __name__ == "__main__":
    main()
