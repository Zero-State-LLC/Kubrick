"""0.27.7: POV shots skip character appearance lock lines and keep action lines."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kubrick.gates.hold_scope import holds_for_prompt  # noqa: E402
from kubrick.gates.jev_holds import compiled_prompts, hold_list  # noqa: E402
from kubrick.gates.lock_phrases import missing_lock_phrases  # noqa: E402
from kubrick.plan.lock_aspect import lock_aspect, pov_skips  # noqa: E402
from kubrick.plan.lock_carriers import lock_table  # noqa: E402
from kubrick.prompts.storyboard_prompts import shots_from_document  # noqa: E402

COAT = "hero wears a long red coat"
CUP = "hero holds a blue cup in the right hand"
GLOW = "a faint green glow on the hero's collar"


def _plan() -> dict[str, object]:
    return {
        "storyboard_id": "pov-test",
        "locks": [
            {"id": "coat", "kind": "wardrobe", "critical": True, "character": "hero",
             "positive": COAT},
            {"id": "cup", "kind": "prop", "critical": True, "character": "hero",
             "positive": CUP},
            {"id": "glow", "kind": "light", "aspect": "appearance", "critical": True,
             "character": "hero", "positive": GLOW},
        ],
        "frames": [
            {"frame_id": "f1", "characters": ["hero"], "view": "pov",
             "action": "hero lifts the cup", "node_states": {"a": "x"}},
            {"frame_id": "f2", "characters": ["hero"], "camera": {"view": "POV"},
             "action": "hero looks down", "node_states": {"a": "x"}},
            {"frame_id": "f3", "characters": ["hero"], "action": "hero waits",
             "node_states": {"a": "x"}},
        ],
    }


def test_aspect_is_explicit_or_from_kind() -> None:
    assert lock_aspect({"kind": "identity"}) == "appearance"
    assert lock_aspect({"kind": "wardrobe"}) == "appearance"
    assert lock_aspect({"kind": "prop"}) == "action"
    assert lock_aspect({"kind": "light"}) == "action"
    assert lock_aspect({"kind": "light", "aspect": " Appearance "}) == "appearance"
    assert lock_aspect({"kind": "wardrobe", "aspect": "action"}) == "action"
    assert lock_aspect({"kind": "wardrobe", "aspect": "nonsense"}) == "appearance"


def test_pov_skips_only_character_appearance() -> None:
    coat = {"kind": "wardrobe", "character": "hero"}
    assert pov_skips(coat, "pov") and pov_skips(coat, " POV ")
    assert not pov_skips(coat, "front") and not pov_skips(coat, None)
    assert not pov_skips({"kind": "wardrobe"}, "pov")
    assert not pov_skips({"kind": "prop", "character": "hero"}, "pov")


def test_compiled_pov_prompt_keeps_action_drops_appearance() -> None:
    shots = {str(s["shot_id"]): str(s["prompt"]) for s in shots_from_document(_plan())}
    for pov in ("f1", "f2"):
        assert CUP in shots[pov]
        assert COAT not in shots[pov] and GLOW not in shots[pov]
    assert COAT in shots["f3"] and CUP in shots["f3"] and GLOW in shots["f3"]


def test_carriers_skip_pov_appearance_rows() -> None:
    plan = _plan()
    frames = plan["frames"]
    assert isinstance(frames, list)
    rows = lock_table(plan, frames)
    pov = {(r["shot"], r["lock"]) for r in rows if r["shot"] in {"f1", "f2"}}
    assert ("f1", "cup") in pov and ("f2", "cup") in pov
    assert not {("f1", "coat"), ("f1", "glow"), ("f2", "coat"), ("f2", "glow")} & pov
    assert all(r.get("code") != "LOCK_POSITIVE_NOT_IN_PROMPT" for r in rows)


def test_phrase_gate_and_holds_agree_on_pov() -> None:
    plan = _plan()
    holds = hold_list(plan)
    prompts = compiled_prompts(plan, "keyframe")
    assert isinstance(holds, list) and isinstance(prompts, list)
    assert missing_lock_phrases(prompts, holds) == []
    first = holds_for_prompt(holds, prompts[0])
    assert isinstance(first, list)
    assert {str(h["id"]) for h in first} >= {"cup"}
    assert not {"coat", "glow"} & {str(h["id"]) for h in first}
    edited = [dict(prompts[0], prompt=str(prompts[0]["prompt"]).replace(CUP, "hands"))]
    failed = missing_lock_phrases(edited, holds)
    ids = []
    for check in failed:
        findings = check["findings"]
        assert isinstance(findings, list)
        ids.append(findings[0]["hold_id"])
    assert ids == ["cup"]
