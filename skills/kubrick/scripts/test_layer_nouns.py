#!/usr/bin/env python3
"""Brief-layer noun tests for issue #20."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_motif_graph import build  # noqa: E402
from layer_leakage import leakage_findings  # noqa: E402

PREFIX = "attribute leakage detected across disentangled layers"
PY = sys.executable


def _spec(layers: dict[str, list[str]]) -> dict[str, object]:
    return {
        "graph_id": "chair-graph",
        "symbolic_intent": {"desired_state_change": "the chair empties"},
        "observed_forms": [
            {"id": "observed_1", "observed_form": "cheap chair", "initial_state": "present"},
            {"id": "observed_2", "observed_form": "speaker", "initial_state": "present"},
            {"id": "observed_3", "observed_form": "optic", "initial_state": "present"},
        ],
        "relations": [
            {"source": "observed_2", "target": "observed_1", "relation": "transfers"},
            {"source": "observed_3", "target": "observed_1", "relation": "crosses"},
        ],
        "layers": layers,
        "convergence_sites": [
            {"site_id": "primary", "node_ids": ["observed_1", "observed_2"], "edge_ids": [0]}
        ],
        "residue": ["chair stays tipped"],
        "surface_output": {
            "audience_prompt": "a room",
            "geometry": [],
            "light": [],
            "material": [],
            "state_differentials": [],
            "convergence": [],
            "residue": [],
        },
    }


def test_shared_noun_is_valid() -> None:
    layers = {
        "layout_geometry": ["server racks around one cheap chair", "chair"],
        "semantics_function": ["surveillance reversed"],
        "attributes_states": ["occupied chair", "vacated chair", "chair"],
    }
    assert leakage_findings(layers) == []
    graph = build(_spec(layers))
    assert graph["validation"]["status"] == "VALID", graph["validation"]
    assert graph["validation"]["attribute_leakage"] == []


def test_verbatim_phrase_names_layers() -> None:
    layers = {
        "layout_geometry": ["occupied chair"],
        "semantics_function": ["watching the room"],
        "attributes_states": ["  Occupied   Chair "],
    }
    findings = leakage_findings(layers)
    assert findings == [
        f"{PREFIX}: phrase 'occupied chair' is repeated in layout_geometry and attributes_states"
    ]
    graph = build(_spec(layers))
    assert graph["validation"]["status"] == "INVALID"
    assert graph["validation"]["attribute_leakage"] == findings
    assert PREFIX in graph["validation"]["errors"][0]
    assert "occupied chair" in graph["validation"]["errors"][0]
    assert "layout_geometry" in graph["validation"]["errors"][0]
    assert "attributes_states" in graph["validation"]["errors"][0]


def test_phrase_pairs_and_within_layer_duplicate() -> None:
    shared = {
        "layout_geometry": ["occupied chair", "occupied chair"],
        "semantics_function": ["occupied chair"],
        "attributes_states": ["occupied chair"],
    }
    findings = leakage_findings(shared)
    assert len(findings) == 3
    assert all(item.startswith(PREFIX) for item in findings)
    assert "semantics_function and attributes_states" in findings[-1]
    alone = {
        "layout_geometry": ["occupied chair", "occupied chair"],
        "semantics_function": ["watching"],
        "attributes_states": ["vacated chair"],
    }
    assert leakage_findings(alone) == []


def test_cli_accepts_shared_chair_noun() -> None:
    layers = {
        "layout_geometry": ["one cheap chair"],
        "semantics_function": ["consequence without cause"],
        "attributes_states": ["occupied chair"],
    }
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "spec.json"
        path.write_text(json.dumps(_spec(layers)), encoding="utf-8")
        result = subprocess.run(
            [PY, str(ROOT / "scripts/build_motif_graph.py"), "--input", str(path)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = yaml.safe_load(result.stdout)
    assert payload["validation"]["status"] == "VALID"


def main() -> None:
    test_shared_noun_is_valid()
    test_verbatim_phrase_names_layers()
    test_phrase_pairs_and_within_layer_duplicate()
    test_cli_accepts_shared_chair_noun()
    print("layer noun tests: PASS")


if __name__ == "__main__":
    main()
