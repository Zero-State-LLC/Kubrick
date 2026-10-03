#!/usr/bin/env python3
"""Propagate Kubrick graph identity and symbolic state across storyboard frames."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    import yaml
except ImportError:
    raise SystemExit("pyyaml required")

from brief_constraints import optional_frame_fields
from continuity_locks import introduced_residue
from planning_fields import planning_frame_fields, planning_root_fields


def load(path: str) -> dict:
    file_path = Path(path)
    if file_path.suffix == ".json":
        return json.loads(file_path.read_text())
    return yaml.safe_load(file_path.read_text()) or {}


def dump(path: str, data: dict) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _resets(
    states: dict[str, object],
    prior_states: dict[str, object],
    nodes: dict[str, dict],
) -> list[str]:
    resets: list[str] = []
    for node_id, value in states.items():
        initial = nodes.get(node_id, {}).get("initial_state")
        changed = node_id in prior_states and prior_states[node_id] != value
        if changed and value == initial:
            resets.append(f"{node_id}:reset-to-initial")
    return resets


def _one_frame(
    graph: dict,
    spec: dict,
    ordinal: int,
    states: dict[str, object],
    owners: dict[str, object],
    residue: list[str],
    resets: list[str],
) -> dict:
    required = spec.get("required_mutations", [])
    sites = [site.get("site_id") for site in graph.get("convergence_sites", [])]
    frame = {
        "frame_id": spec.get("frame_id", f"frame-{ordinal:03d}"),
        "ordinal": ordinal,
        "node_states": states,
        "motif_ownership": owners,
        "object_states": spec.get("object_states", {}),
        "light_states": spec.get("light_states", {}),
        "material_states": spec.get("material_states", {}),
        "residue": residue,
        "convergence_sites": spec.get("convergence_sites", sites),
        "required_mutations": required,
        "prohibited_resets": resets,
    }
    frame.update(optional_frame_fields(spec))
    frame.update(planning_frame_fields(spec))
    return frame


def _mutation_warnings(spec: dict, ordinal: int) -> list[str]:
    warnings: list[str] = []
    evidenced = json.dumps(spec, sort_keys=True)
    for item in spec.get("required_mutations", []):
        if item not in evidenced:
            warnings.append(f"frame {ordinal} required mutation not evidenced: {item}")
    return warnings


def propagate(graph: dict, plan: dict) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    frames: list[dict] = []
    nodes = {node["id"]: node for node in graph.get("nodes", [])}
    if graph.get("validation", {}).get("status") != "VALID":
        errors.append("source graph is not VALID")
    prior_states = {
        node_id: node.get("initial_state", "present") for node_id, node in nodes.items()
    }
    prior_owners: dict[str, object] = {node_id: None for node_id in nodes}
    pending = [str(item).strip() for item in graph.get("residue", []) if str(item).strip()]
    prior_residue: list[str] = []
    for ordinal, spec in enumerate(plan.get("frames", []), start=1):
        states = dict(prior_states)
        states.update(spec.get("node_states", {}))
        owners = dict(prior_owners)
        owners.update(spec.get("motif_ownership", {}))
        residue, pending = introduced_residue(
            prior_residue, spec.get("residue_add", []) or [], pending,
        )
        resets = _resets(states, prior_states, nodes)
        warnings.extend(_mutation_warnings(spec, ordinal))
        frames.append(_one_frame(graph, spec, ordinal, states, owners, residue, resets))
        if resets and not spec.get("allow_resets", False):
            errors.extend(f"frame {ordinal} prohibited reset: {item}" for item in resets)
        prior_states, prior_owners, prior_residue = states, owners, residue
    if len(frames) < 2:
        errors.append("at least two frames are required")
    result = {
        "schema_version": "1.0.0",
        "storyboard_id": plan.get("storyboard_id", "kubrick-storyboard"),
        "graph_id": graph.get("graph_id", "unknown"),
        "frames": frames,
        "validation": {
            "status": "VALID" if not errors else "INVALID",
            "errors": errors,
            "warnings": warnings,
            "frame_count": len(frames),
        },
    }
    result.update(planning_root_fields(plan))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    result = propagate(load(args.graph), load(args.plan))
    if args.output:
        dump(args.output, result)
    else:
        print(yaml.safe_dump(result, sort_keys=False))
    raise SystemExit(0 if result["validation"]["status"] == "VALID" else 1)


if __name__ == "__main__":
    main()
