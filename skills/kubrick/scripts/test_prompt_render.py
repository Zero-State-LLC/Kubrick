#!/usr/bin/env python3
"""Prompt fidelity tests for issues #16, #17, #18, and #21."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from adapt_provider import adapt  # noqa: E402
from build_model_adapter_packet import build as build_packet  # noqa: E402
from build_motif_graph import build as build_graph  # noqa: E402
from compare_visual_observation import compare  # noqa: E402
from prompt_text import (  # noqa: E402
    _FEATURES,
    append_unique,
    character_lock_positive,
    field_label,
    is_blank,
    join_clauses,
    positive_prompt,
    render_frame_prompt,
    render_name,
)
from storyboard_prompts import adapter_packet_from_document  # noqa: E402
from surface_compilers import (  # noqa: E402
    _shot_dict_to_adapter_packet,
    video_adapt,
    video_shot,
)

FIXTURE = ROOT / "evals/fixtures/myslef/storyboard-plan.yaml"
LABELS = {
    "observed_1": "cheap minder chair in a Westlake basement bot-farm",
    "observed_2": "industrial speaker grille set in myslef's mouth",
    "observed_3": "smaller right optic with a spiderweb crack",
}
GENERAL_NEGATIVES = [
    "named occult labels",
    "geometry reset",
    "residue erasure",
    "no named esoterica",
    "no continuity reset",
    "no unexplained motif reset",
]
CLAUSE = "kept unit becomes the only presence left in the room"
MARKERS = (
    "laptop cartoon audio under the hum",
    "minder voice cut off mid-syllable",
    "silent speaker becomes sounding speaker",
    "occupied chair becomes empty chair",
)


def myslef_document() -> dict[str, object]:
    loaded = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def myslef_packet() -> dict[str, object]:
    document = myslef_document()
    packet = adapter_packet_from_document(document, provider="generic")
    frames = packet["frames"]
    assert isinstance(frames, list)
    for frame, seconds in zip(frames, (4, 10, 4, 5), strict=True):
        assert isinstance(frame, dict)
        frame["provider_parameters"] = {"duration_seconds": seconds}
    shared = packet["shared_constraints"]
    assert isinstance(shared, dict)
    shared["negative_constraints"] = [*GENERAL_NEGATIVES, "no nose"]
    return packet


def _valid_graph() -> dict:
    spec = {
        "graph_id": "myslef-graph",
        "symbolic_intent": {"desired_state_change": "the room keeps one presence"},
        "observed_forms": [
            {"id": key, "observed_form": label, "initial_state": "present"}
            for key, label in LABELS.items()
        ],
        "relations": [
            {"source": "observed_2", "target": "observed_1", "relation": "transfers"},
            {"source": "observed_3", "target": "observed_1", "relation": "crosses"},
        ],
        "layers": {
            "layout_geometry": ["server racks around one cheap chair"],
            "semantics_function": ["surveillance reversed"],
            "attributes_states": ["occupied seat"],
        },
        "convergence_sites": [
            {
                "site_id": "primary",
                "node_ids": ["observed_1", "observed_2"],
                "edge_ids": [0],
            }
        ],
        "residue": ["the chair stays tipped"],
        "surface_output": {
            "audience_prompt": "a basement room",
            "geometry": ["racks frame the room"],
            "light": [],
            "material": [],
            "state_differentials": [],
            "convergence": [],
            "residue": [],
        },
    }
    graph = build_graph(spec)
    assert graph["validation"]["status"] == "VALID", graph["validation"]
    return graph


def _assert_clean(prompt: str) -> None:
    assert "motif ownership" in prompt
    assert "ownershi " not in prompt
    assert "observed_1" not in prompt
    assert "observed_2" not in prompt
    assert "observed_3" not in prompt
    assert "None" not in prompt


def test_field_label_and_blank_and_name() -> None:
    assert field_label("motif_ownership") == "motif ownership"
    assert field_label("node_states") == "node state"
    assert field_label("object_states") == "object state"
    assert field_label("light_states") == "light state"
    assert field_label("material_states") == "material state"
    assert field_label("residue_add") == "residue add"
    for value in (None, "None", " none ", "", "NOT_COMPUTABLE", "not_computable"):
        assert is_blank(value)
    assert is_blank("chair") is False
    assert render_name("observed_1", LABELS) == LABELS["observed_1"]
    assert render_name("observed_9", {}) is None
    assert render_name("chair", {}) == "chair"
    assert render_name("None", LABELS) is None
    assert render_name("", LABELS) is None


def test_dedupe_keeps_order_and_stored_prompt() -> None:
    assert join_clauses([CLAUSE, "other", CLAUSE, "other"]) == f"{CLAUSE}; other"
    stored = f"{CLAUSE}; {CLAUSE}"
    assert append_unique(stored, [CLAUSE, "new clause"]) == f"{stored}; new clause"


def test_character_lock_lexicon_and_general_negatives() -> None:
    for feature, pair in _FEATURES.items():
        found = character_lock_positive(f"no {feature}")
        assert found == pair
        text = positive_prompt("face", [], [f"no {feature}"])
        assert pair[0] in text and pair[1] in text
    assert character_lock_positive("character-lock: no nose") == _FEATURES["nose"]
    assert character_lock_positive("identity-lock: no eyes") == _FEATURES["eyes"]
    assert character_lock_positive("identity: without hair") == _FEATURES["hair"]
    assert character_lock_positive("no nose on the left") == _FEATURES["nose"]
    for negative in GENERAL_NEGATIVES:
        assert character_lock_positive(negative) is None
        assert negative not in positive_prompt("room", [], [negative])


def test_none_and_unlabeled_ids_are_omitted() -> None:
    frame = {
        "node_states": {"observed_1": None, "observed_9": "present"},
        "object_states": {"chair": None, "lamp": "on"},
        "motif_ownership": {"observed_2": "myslef"},
    }
    prompt = render_frame_prompt([], frame, {"observed_2": LABELS["observed_2"]})
    assert "None" not in prompt
    assert "observed_" not in prompt
    assert "lamp" in prompt
    assert "motif ownership" in prompt
    assert LABELS["observed_1"] not in prompt


def test_four_myslef_prompts_are_distinct() -> None:
    document = myslef_document()
    frames = document["frames"]
    assert isinstance(frames, list)
    graph = _valid_graph()
    packet = build_packet(graph, {"frames": frames}, "generic")
    prompts = [str(frame["prompt"]) for frame in packet["frames"]]
    assert len(prompts) == 4
    assert len(set(prompts)) == 4
    for prompt, marker in zip(prompts, MARKERS, strict=True):
        _assert_clean(prompt)
        assert marker in prompt
        assert LABELS["observed_1"] in prompt
        assert "node state " in prompt
        assert "object state " in prompt
        assert "light state " in prompt
        assert "material state " in prompt
    shot = video_shot(None, None, "myslef", input_text=FIXTURE.read_text(encoding="utf-8"))
    shot_prompts = [item["prompt"] for item in shot["result"]["shots"]]
    assert len(set(shot_prompts)) == 4
    adapted = video_adapt(FIXTURE.read_text(encoding="utf-8"), "myslef", "generic")
    assert adapted["status"] != "NOT_COMPUTABLE"
    adapted_prompts = [item["prompt"] for item in adapted["result"]["adapted_packet"]["frames"]]
    assert len(set(adapted_prompts)) == 4


def test_repeated_clause_and_general_negatives_stay_out() -> None:
    shot = {
        "shot_id": "shot-repeat",
        "start_state": {"observable": CLAUSE},
        "action": {"path_or_change": CLAUSE},
        "end_state": {"summary": CLAUSE, "residue": [CLAUSE]},
        "camera": {"framing": CLAUSE},
        "duration_seconds": 4,
        "negative_constraints": [*GENERAL_NEGATIVES, "no nose"],
    }
    packet = _shot_dict_to_adapter_packet(shot)
    prompt = packet["frames"][0]["prompt"]
    assert prompt.count(CLAUSE) == 1
    rendered = adapt(packet, "generic")
    positive = rendered["frames"][0]["prompt"]
    assert positive.count(CLAUSE) == 1
    assert "smooth featureless skin where a nose would be" in positive
    assert "the locked character's face has no nose" in positive
    for negative in GENERAL_NEGATIVES:
        assert negative not in positive
    assert rendered["frames"][0]["negative_constraints"] == shot["negative_constraints"]


def _positive_body(provider: str, frame: dict) -> str:
    prompt = str(frame["prompt"])
    if provider == "midjourney":
        return prompt.split(" --ar ", 1)[0]
    if provider == "sd3":
        return prompt
    return prompt


def test_every_positive_provider_rephrases_locks_only() -> None:
    packet = myslef_packet()
    packet["shared_constraints"]["visual_identity"] = []
    first = packet["frames"][0]
    first["continuity_from_previous"] = []
    first["state_constraints"] = []
    source = str(first["prompt"])
    for provider in ("generic", "grok-imagine", "flux", "sd3", "midjourney"):
        rendered = adapt(packet, provider)
        assert rendered["validation"]["status"] == "VALID", (provider, rendered["validation"])
        frame = rendered["frames"][0]
        body = _positive_body(provider, frame)
        assert source in body
        assert "smooth featureless skin where a nose would be" in body
        assert "the locked character's face has no nose" in body
        for negative in GENERAL_NEGATIVES:
            assert negative not in body
        if provider == "midjourney":
            assert "--no geometry reset" in frame["prompt"]
        elif provider in {"flux", "sd3"}:
            assert "geometry reset" in frame["negative_prompt"]
        else:
            assert "geometry reset" in frame["negative_constraints"]
    empty = adapt(packet, "sd3")
    assert empty["frames"][0]["prompt"].startswith(f"subject: {source}")
    assert "composition:" not in empty["frames"][0]["prompt"]


def test_ownership_correction_uses_full_label() -> None:
    expected = {
        "graph_id": "g1",
        "frames": [{"frame_id": "f1", "motif_ownership": {"speaker": "myslef"}}],
    }
    observation = {
        "source_graph_id": "g1",
        "frame_id": "f1",
        "observed": {"motif_ownership": {}},
    }
    report = compare(expected, observation)
    change = " ".join(report["correction_packet"]["change"])
    assert "set motif ownership speaker to myslef" in change
    assert "ownershi " not in change
    assert "ownershi " not in json.dumps(report)


def main() -> None:
    test_field_label_and_blank_and_name()
    test_dedupe_keeps_order_and_stored_prompt()
    test_character_lock_lexicon_and_general_negatives()
    test_none_and_unlabeled_ids_are_omitted()
    test_four_myslef_prompts_are_distinct()
    test_repeated_clause_and_general_negatives_stay_out()
    test_every_positive_provider_rephrases_locks_only()
    test_ownership_correction_uses_full_label()
    print("prompt render tests: PASS")


if __name__ == "__main__":
    main()
