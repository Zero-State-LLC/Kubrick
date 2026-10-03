#!/usr/bin/env python3
"""Build provider-neutral model adapter packets from Kubrick graph/storyboard state."""
from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from pathlib import Path

try:
    import yaml
except ImportError:
    raise SystemExit("pyyaml required")

from brief_constraints import carried_shared  # noqa: E402
from prompt_text import (  # noqa: E402
    continuity_clauses,
    continuity_for_frame,
    node_labels,
    node_state_constraints,
    render_frame_prompt,
)
from shot_plan import (  # noqa: E402
    attach_plan,
    document_from_sources,
    enrich_prompts,
    prompted_parameters,
)


def load(path: str) -> dict:
    p = Path(path)
    return json_or_yaml(p)


def json_or_yaml(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        import json

        data = json.loads(text)
    else:
        data = yaml.safe_load(text) or {}
    return data if isinstance(data, dict) else {}


def save(path: str, data: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _labels(graph: Mapping[str, object]) -> dict[str, str]:
    raw = graph.get("nodes") or []
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return {}
    nodes = [node for node in raw if isinstance(node, Mapping)]
    return node_labels(nodes)


def _fallback_frame(graph: Mapping[str, object]) -> dict[str, object]:
    states: dict[str, object] = {}
    raw = graph.get("nodes") or []
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        for node in raw:
            if isinstance(node, Mapping) and node.get("id"):
                states[str(node.get("id"))] = node.get("target_state")
    sites = []
    raw_sites = graph.get("convergence_sites") or []
    if isinstance(raw_sites, Sequence) and not isinstance(raw_sites, (str, bytes)):
        for site in raw_sites:
            if isinstance(site, Mapping) and site.get("site_id"):
                sites.append(site.get("site_id"))
    return {
        "frame_id": "frame-001",
        "node_states": states,
        "motif_ownership": {},
        "object_states": {},
        "light_states": {},
        "material_states": {},
        "residue": list(graph.get("residue") or []),
        "convergence_sites": sites,
        "prohibited_resets": [],
    }


def _shared(graph: Mapping[str, object]) -> list[object]:
    surface = graph.get("surface_output") or {}
    if not isinstance(surface, Mapping):
        return []
    shared: list[object] = []
    for key in ("geometry", "light", "material"):
        values = surface.get(key) or []
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
            shared.extend(values)
    return shared


def _rendered_frames(
    mapping_frames: Sequence[Mapping[str, object]],
    prompts: Sequence[str],
    graph_id: object,
    labels: Mapping[str, str],
) -> list[dict[str, object]]:
    frames: list[dict[str, object]] = []
    previous: Mapping[str, object] | None = None
    for frame, prompt in zip(mapping_frames, prompts):
        raw_continuity = continuity_clauses(str(graph_id), previous, labels) if previous else []
        continuity = continuity_for_frame(raw_continuity, frame)
        frames.append(
            {
                "frame_id": frame.get("frame_id", f"frame-{len(frames) + 1:03d}"),
                "prompt": prompt or "evidenced frame state",
                "state_constraints": node_state_constraints(frame, labels),
                "continuity_from_previous": continuity,
                "provider_parameters": prompted_parameters(frame),
            }
        )
        previous = frame
    return frames


def build(graph: dict, storyboard: dict | None, provider: str) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    if graph.get("validation", {}).get("status") != "VALID":
        errors.append("source graph is not VALID")
    graph_id = graph.get("graph_id")
    if not graph_id:
        errors.append("source graph_id missing")
    labels = _labels(graph)
    shared = _shared(graph)
    source_frames = (storyboard or {}).get("frames") or [_fallback_frame(graph)]
    mapping_frames = [frame for frame in source_frames if isinstance(frame, Mapping)]
    board = storyboard if isinstance(storyboard, Mapping) else None
    document = document_from_sources(graph, board)
    prompts, prep = enrich_prompts(
        document,
        mapping_frames,
        provider,
        lambda frame: render_frame_prompt(shared, frame, labels) or "evidenced frame state",
    )
    frames = _rendered_frames(mapping_frames, prompts, graph_id, labels)
    errors.extend(prep.errors)
    if not frames:
        errors.append("no frames available for adaptation")
    prohibited: set[str] = set()
    for frame in source_frames:
        if isinstance(frame, Mapping):
            for item in frame.get("prohibited_resets", []) or []:
                prohibited.add(str(item))
    packet = {
        "schema_version": "1.0.0",
        "adapter_id": f"kubrick-{provider}-adapter-v1",
        "provider": provider,
        "source_graph_id": graph_id or "unknown",
        "mode": "storyboard" if storyboard else "single-frame",
        "shared_constraints": {
            "visual_identity": shared,
            "continuity_rules": [
                "preserve graph identity",
                "preserve residue",
                "preserve ownership until explicitly changed",
            ],
            "prohibited_resets": sorted(prohibited),
        },
        "frames": frames,
        "private_state_policy": {
            "graph_mutation_allowed": False,
            "pattern_links_exposed": False,
            "lexicon_links_exposed": False,
        },
        "validation": {
            "status": "VALID" if not errors else "INVALID",
            "errors": errors,
            "warnings": warnings,
        },
    }
    shared_constraints = packet["shared_constraints"]
    if isinstance(shared_constraints, dict):
        shared_constraints.update(carried_shared(graph))
    attach_plan(
        packet,
        prep_warnings=prep.warnings,
        technique_suggestions=prep.techniques,
        characters=document.get("characters"),
        props=document.get("props"),
        short_beat_threshold_seconds=document.get("short_beat_threshold_seconds"),
    )
    if document.get("strict") is True:
        packet["strict"] = True
    return packet


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", required=True)
    parser.add_argument("--storyboard")
    parser.add_argument("--provider", default="generic")
    parser.add_argument("--output")
    args = parser.parse_args()
    storyboard = load(args.storyboard) if args.storyboard else None
    packet = build(load(args.graph), storyboard, args.provider)
    rendered = yaml.safe_dump(packet, sort_keys=False)
    if args.output:
        save(args.output, packet)
    else:
        print(rendered)
    raise SystemExit(0 if packet["validation"]["status"] == "VALID" else 1)


if __name__ == "__main__":
    main()
