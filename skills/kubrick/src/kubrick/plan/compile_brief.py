#!/usr/bin/env python3
"""Brief-to-graph fields shared by the Kubrick compiler. Behavior matches v0.19."""
from __future__ import annotations

import hashlib
import json

from kubrick.plan.brief_constraints import carried_brief_fields


def complete_surface(brief: dict) -> dict:
    supplied = brief.get("surface_output") or {}
    convergence = [brief.get("convergence_effect", "relation becomes materially visible")]
    return {
        "audience_prompt": supplied.get("audience_prompt", brief.get("audience_prompt", "")),
        "geometry": supplied.get("geometry", brief.get("geometry", [])),
        "light": supplied.get("light", brief.get("light", brief.get("lighting", []))),
        "material": supplied.get("material", brief.get("material", brief.get("materials", []))),
        "state_differentials": supplied.get(
            "state_differentials", brief.get("state_differentials", []),
        ),
        "convergence": supplied.get("convergence", convergence),
        "residue": supplied.get("residue", brief.get("residue", [])),
    }


def _default_motifs(brief: dict, graph: dict, selected: str) -> list[dict]:
    edges = graph.get("edges", []) + [{}]
    has_edges = bool(graph.get("edges"))
    motifs = []
    for node, edge in zip(graph.get("nodes", []), edges):
        consequence = edge.get("transformation", "") if has_edges else "state changes"
        motifs.append({
            "motif_id": selected,
            "dramatic_function": brief.get("dramatic_problem", "transform pressure"),
            "observed_form": node.get("observed_form", ""),
            "recurrences": [{
                "state": node.get("initial_state", "present"),
                "mutation": node.get("target_state", "transformed"),
                "consequence": consequence,
            }],
        })
    return motifs


def _convergence_sites(brief: dict, graph: dict) -> list[dict]:
    sites = []
    for site in graph.get("convergence_sites", []):
        functions = site.get("functions") or [
            site.get("observable_effect", ""),
            brief.get("desired_state_change", "transformed"),
        ]
        sites.append({"site_id": site.get("site_id"), "functions": functions})
    return sites


def build_structured_packet(brief: dict, graph: dict, selected: str) -> dict:
    channels = brief.get("symbolic_channels") or {
        "diegetic": brief.get("diegetic_channel", []),
        "dramaturgical": brief.get("dramaturgical_channel", []),
        "cinematic": brief.get("cinematic_channel", []),
    }
    motifs = brief.get("motifs", []) or _default_motifs(brief, graph, selected)
    cultural = brief.get("cultural_sources", [])
    if not cultural and brief.get("cultural_context"):
        cultural = [{
            "source": brief["cultural_context"],
            "boundary": brief.get(
                "cultural_boundary",
                "project-specific transfer only; no universal equivalence",
            ),
        }]
    actions = brief.get("causal_actions") or [
        edge.get("transformation", "")
        for edge in graph.get("edges", [])
        if edge.get("transformation")
    ]
    return {
        "dramatic_function": brief.get("dramatic_problem", "transform pressure"),
        "causal_actions": actions,
        "motifs": motifs,
        "channels": channels,
        "convergence_sites": _convergence_sites(brief, graph),
        "cultural_sources": cultural,
        "interpretation_claims": brief.get("interpretation_claims", []),
        "production_constraints": brief.get("production_constraints", []),
    }


def fallback_forms(brief: dict, selected: str) -> list[dict]:
    evidence = (brief.get("observable_evidence") or [])[:3]
    return [{
        "id": f"observed_{index + 1}",
        "kind": "motif",
        "observed_form": str(value),
        "initial_state": "present",
        "target_state": brief.get("desired_state_change", "mutated"),
        "provenance_label": "OBSERVED",
        "pattern_links": [selected],
    } for index, value in enumerate(evidence)]


def default_relations(brief: dict, forms: list[dict]) -> list[dict]:
    return [{
        "source": forms[0].get("id", "observed_1"),
        "target": forms[1].get("id", "observed_2"),
        "relation": "opposes",
        "pressure": 0.7,
        "transformation": brief.get("desired_state_change", "relation changes"),
    }]


def _default_sites(brief: dict, forms: list[dict]) -> list[dict]:
    return [{
        "site_id": "primary",
        "node_ids": [forms[0].get("id"), forms[1].get("id")],
        "edge_ids": [0],
        "observable_effect": brief.get(
            "convergence_effect", "relation becomes materially visible",
        ),
        "mask_priority": 0.9,
    }]


def graph_spec(brief: dict, forms: list[dict], relations: list[dict]) -> dict:
    layers = {
        "layout_geometry": brief.get("geometry", []),
        "semantics_function": [brief.get("dramatic_problem", "")],
        "attributes_states": brief.get("state_differentials", []),
    }
    digest = hashlib.sha256(json.dumps(brief, sort_keys=True).encode()).hexdigest()[:16]
    return {
        "graph_id": digest,
        "symbolic_intent": {
            "dramatic_function": brief.get("dramatic_problem", "transform pressure"),
            "emotional_force": brief.get("character_pressure", "pressure"),
            "desired_state_change": brief.get("desired_state_change", "transformed"),
        },
        "observed_forms": forms,
        "relations": relations,
        "layers": brief.get("layers", layers),
        "convergence_sites": brief.get("convergence_sites", _default_sites(brief, forms)),
        "residue": brief.get("residue", []),
        "surface_output": complete_surface(brief),
        **carried_brief_fields(brief),
    }
