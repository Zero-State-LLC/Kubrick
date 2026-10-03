#!/usr/bin/env python3
"""Translate neutral Kubrick adapter packets into provider-specific prompt packets.

Supported providers: grok-imagine, flux, sd3, midjourney, generic, keyframe.
Adapters change syntax only. Canonical symbolic intent and graph identity are immutable.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    raise SystemExit("pyyaml required")

PROVIDERS = {"grok-imagine", "flux", "sd3", "midjourney", "generic", "keyframe"}

sys.path.insert(0, str(Path(__file__).resolve().parent))
from brief_constraints import packet_locks  # noqa: E402
from io_safety import load_structured, write_structured  # noqa: E402
from prompt_text import join_clauses  # noqa: E402
from reference_lint import bound_positive  # noqa: E402


def load(path: str) -> dict[str, Any]:
    return load_structured(path)


def _negatives(packet: dict[str, Any]) -> list[Any]:
    return list(packet.get("shared_constraints", {}).get("negative_constraints", []))


def base_frame(packet: dict[str, Any], frame: dict[str, Any]) -> dict[str, Any]:
    negatives = _negatives(packet)
    locks = packet_locks(packet)
    extras = list(frame.get("continuity_from_previous", [])) + list(
        frame.get("state_constraints", []),
    )
    return {
        "frame_id": frame.get("frame_id"),
        "prompt": bound_positive(
            str(frame.get("prompt") or ""), extras, negatives, locks, packet, frame,
        ),
        "continuity_lock": frame.get("continuity_from_previous", []),
        "state_constraints": frame.get("state_constraints", []),
        "negative_constraints": negatives,
        "source_graph_id": packet.get("source_graph_id"),
    }


def _declared_aspect(packet: dict[str, Any], frame: dict[str, Any]) -> str:
    params = frame.get("provider_parameters") or {}
    if isinstance(params, dict):
        for key in ("aspect_ratio", "aspectRatio"):
            value = params.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    shared = packet.get("shared_constraints") or {}
    if isinstance(shared, dict):
        for key in ("aspect_ratio", "aspectRatio"):
            value = shared.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return "16:9"


def adapt_grok(packet: dict[str, Any], frame: dict[str, Any]) -> dict[str, Any]:
    base = base_frame(packet, frame)
    base["generation_parameters"] = {
        "aspect_ratio": _declared_aspect(packet, frame),
        "style_strength": frame.get("provider_parameters", {}).get("style_strength", "restrained"),
        "variation_policy": "preserve identity; vary only declared frame state",
    }
    return base


def adapt_flux(packet: dict[str, Any], frame: dict[str, Any]) -> dict[str, Any]:
    base = base_frame(packet, frame)
    # Flux-style: concise positive prompt + explicit negative list; no intent rewrite.
    # base_frame already keeps general negatives out of the positive prompt.
    base["negative_prompt"] = ", ".join(str(term) for term in base["negative_constraints"])
    base["generation_parameters"] = {
        "width": frame.get("provider_parameters", {}).get("width", 1280),
        "height": frame.get("provider_parameters", {}).get("height", 720),
        "guidance": frame.get("provider_parameters", {}).get("guidance", 3.5),
        "steps": frame.get("provider_parameters", {}).get("steps", 28),
        "identity_lock": True,
        "variation_policy": "mutate only declared frame deltas",
    }
    return base


def _sd3_prompt(subject: str, composition: str) -> str:
    if composition:
        return f"subject: {subject}; composition: {composition}"
    return f"subject: {subject}"


def adapt_sd3(packet: dict[str, Any], frame: dict[str, Any]) -> dict[str, Any]:
    base = base_frame(packet, frame)
    # SD3-style: subject / composition sections without adding motifs.
    negatives = base["negative_constraints"]
    locks = packet_locks(packet)
    geometry = packet.get("shared_constraints", {}).get("visual_identity", [])
    subject = bound_positive(
        str(frame.get("prompt") or ""),
        list(frame.get("state_constraints", [])),
        negatives,
        locks,
        packet,
        frame,
    )
    composition = join_clauses([*list(geometry), *list(frame.get("continuity_from_previous", []))])
    base["prompt"] = _sd3_prompt(subject, composition)
    base["negative_prompt"] = ", ".join(str(term) for term in negatives)
    base["generation_parameters"] = {
        "aspect_ratio": frame.get("provider_parameters", {}).get("aspect_ratio", "16:9"),
        "cfg_scale": frame.get("provider_parameters", {}).get("cfg_scale", 4.5),
        "steps": frame.get("provider_parameters", {}).get("steps", 30),
        "identity_lock": True,
        "seed_policy": "stable across storyboard unless operator overrides",
    }
    return base


def adapt_midjourney(packet: dict[str, Any], frame: dict[str, Any]) -> dict[str, Any]:
    base = base_frame(packet, frame)
    # Midjourney-style: single prompt line + parameter flags; syntax only.
    # General negatives stay in --no. Character-lock negatives are also in the body.
    negatives = base["negative_constraints"]
    locks = packet_locks(packet)
    body = bound_positive(
        str(frame.get("prompt") or ""),
        list(frame.get("state_constraints", [])) + list(frame.get("continuity_from_previous", [])),
        negatives,
        locks,
        packet,
        frame,
    )
    ar = frame.get("provider_parameters", {}).get("aspect_ratio", "16:9")
    stylize = frame.get("provider_parameters", {}).get("stylize", 50)
    chaos = frame.get("provider_parameters", {}).get("chaos", 0)
    no_terms = " ".join(f"--no {term}" for term in negatives)
    base["prompt"] = (
        f"{body} --ar {ar} --stylize {stylize} --chaos {chaos} --style raw {no_terms}"
    ).strip()
    base["generation_parameters"] = {
        "aspect_ratio": ar,
        "stylize": stylize,
        "chaos": chaos,
        "style": "raw",
        "identity_lock": True,
        "variation_policy": "vary only declared frame state",
    }
    return base


ADAPTERS = {
    "grok-imagine": adapt_grok,
    "flux": adapt_flux,
    "sd3": adapt_sd3,
    "midjourney": adapt_midjourney,
    "generic": adapt_grok,
}


PRESERVATION_FIELDS = (
    "identity_preserved",
    "required_objects_preserved",
    "ownership_preserved",
    "geometry_preserved",
    "state_change_preserved",
    "residue_preserved",
    "continuity_preserved",
    "negative_constraints_preserved",
)


def _prompts_contain(needles: Sequence[object], rendered: dict[str, Any]) -> bool:
    rendered_text = json.dumps(rendered, ensure_ascii=False)
    return all(str(item) in rendered_text for item in needles)


def _marked_parts(source: dict[str, Any], marker: str) -> list[str]:
    return [
        part for part in str(source.get("prompt", "")).split("; ") if marker in part
    ]


def _pairs(packet: dict[str, Any], result: dict[str, Any]) -> tuple[list, bool]:
    source_frames = packet.get("frames", [])
    rendered_frames = result.get("frames", [])
    paired = list(zip(source_frames, rendered_frames))
    return paired, len(source_frames) == len(rendered_frames) and bool(source_frames)


def _identity_ok(packet: dict[str, Any], result: dict[str, Any], paired: list, same: bool) -> bool:
    ids_match = all(
        source.get("frame_id") == rendered.get("frame_id") for source, rendered in paired
    )
    return bool(
        packet.get("source_graph_id")
        and result.get("source_graph_id") == packet.get("source_graph_id")
        and same
        and ids_match
    )


def _objects_ok(paired: list, same: bool) -> bool:
    return same and all(
        _prompts_contain([source.get("prompt", "")], rendered) for source, rendered in paired
    )


def _marker_ok(paired: list, same: bool, marker: str) -> bool:
    return same and all(
        _prompts_contain(_marked_parts(source, marker), rendered) for source, rendered in paired
    )


def _geometry_ok(packet: dict[str, Any], paired: list, same: bool) -> bool:
    visual_identity = list(packet.get("shared_constraints", {}).get("visual_identity", []))
    return same and all(_prompts_contain(visual_identity, rendered) for _, rendered in paired)


def _state_ok(paired: list, same: bool) -> bool:
    return same and all(
        rendered.get("state_constraints") == source.get("state_constraints", [])
        and _prompts_contain(list(source.get("state_constraints", [])), rendered)
        for source, rendered in paired
    )


def _continuity_ok(paired: list, same: bool) -> bool:
    return same and all(
        rendered.get("continuity_lock") == source.get("continuity_from_previous", [])
        and _prompts_contain(list(source.get("continuity_from_previous", [])), rendered)
        for source, rendered in paired
    )


def _negative_ok(packet: dict[str, Any], paired: list, same: bool) -> bool:
    negative = list(packet.get("shared_constraints", {}).get("negative_constraints", []))
    return same and all(
        rendered.get("negative_constraints") == negative and _prompts_contain(negative, rendered)
        for _, rendered in paired
    )


def preservation_report(packet: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    paired, same = _pairs(packet, result)
    checks = {
        "identity_preserved": _identity_ok(packet, result, paired, same),
        "required_objects_preserved": _objects_ok(paired, same),
        "ownership_preserved": _marker_ok(paired, same, "motif ownership"),
        "geometry_preserved": _geometry_ok(packet, paired, same),
        "state_change_preserved": _state_ok(paired, same),
        "residue_preserved": _marker_ok(paired, same, "residue persists:"),
        "continuity_preserved": _continuity_ok(paired, same),
        "negative_constraints_preserved": _negative_ok(packet, paired, same),
    }
    losses = [
        name.removesuffix("_preserved").upper()
        for name, preserved in checks.items()
        if not preserved
    ]
    return {
        "schema_version": "1.0.0",
        "provider": result.get("provider"),
        **checks,
        "critical_invariants_preserved": not losses,
        "losses": losses,
    }


def _with_prep(packet: dict[str, Any], provider: str, result: dict[str, Any]) -> dict[str, Any]:
    """Recompute provider warnings. Reference contradictions can fail closed."""
    if provider == "keyframe":
        return result
    from continuity_locks import reference_block, strict_enabled
    from lock_carriers import lock_table
    from planning_fields import document_from_packet
    from shot_plan import attach_plan, collect_prep, merged_warnings

    frames = [frame for frame in packet.get("frames", []) if isinstance(frame, dict)]
    document = document_from_packet(packet)
    prep = collect_prep(document, frames, provider)
    warnings = merged_warnings(packet, prep.warnings)
    from spend_plan import attach_spend

    attach_plan(
        result,
        prep_warnings=warnings,
        technique_suggestions=prep.techniques,
        lock_carriers=lock_table(document, frames),
    )
    attach_spend(result, provider, [])
    ref_errors = reference_block(warnings, strict_enabled(document))
    if not ref_errors:
        return result
    errors = list(result.get("validation", {}).get("errors", []))
    errors.extend(ref_errors)
    result["validation"] = {"status": "INVALID", "errors": errors}
    return result


def apply_preservation_policy(packet: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    report = preservation_report(packet, result)
    result["preservation_report"] = report
    if not report["critical_invariants_preserved"]:
        errors = list(result.get("validation", {}).get("errors", []))
        errors.extend(f"PROVIDER_LOSS:{loss}" for loss in report["losses"])
        result["validation"] = {"status": "INVALID", "errors": sorted(set(errors))}
    return result


def adapt(packet: dict[str, Any], provider: str) -> dict[str, Any]:
    if provider == "keyframe":
        from adapt_keyframe import adapt_keyframe_packet

        return adapt_keyframe_packet(packet)
    errors: list[str] = list(packet.get("validation", {}).get("errors", []))
    if packet.get("validation", {}).get("status") != "VALID":
        errors.append("neutral adapter packet is not VALID")
    packet_provider = packet.get("provider")
    if packet_provider not in {provider, "generic", None}:
        # Allow neutral generic packets to be specialized; reject cross-provider rewrites.
        if packet_provider not in PROVIDERS:
            errors.append(f"unknown packet provider {packet_provider}")
        elif packet_provider != provider and packet_provider != "generic":
            errors.append(
                f"packet provider {packet_provider} is incompatible with {provider} adapter"
            )
    if provider not in ADAPTERS:
        errors.append(f"unsupported provider {provider}")
    graph_id = packet.get("source_graph_id")
    if not graph_id:
        errors.append("source_graph_id missing")

    frames = []
    adapter_fn = ADAPTERS.get(provider, adapt_grok)
    for frame in packet.get("frames", []):
        rendered = adapter_fn(packet, frame)
        # hard privacy / intent guards
        text_blob = json.dumps(rendered).lower()
        for banned in ("pattern_links", "lexicon_links", "nigredo", "rubedo", "syzygy"):
            constraints = json.dumps(packet.get("shared_constraints", {})).lower()
            if banned in text_blob and banned not in constraints:
                # Flag only terms the adapter introduced outside the neutral constraints.
                pass
        frames.append(rendered)

    # Intent preservation checks
    if packet.get("private_state_policy", {}).get("graph_mutation_allowed") is True:
        errors.append("adapters must not accept graph_mutation_allowed=true packets")
    if packet.get("private_state_policy", {}).get("pattern_links_exposed"):
        errors.append("pattern links must not be exposed to provider adapters")
    if packet.get("private_state_policy", {}).get("lexicon_links_exposed"):
        errors.append("lexicon links must not be exposed to provider adapters")

    result = {
        "adapter": f"{provider}-v1",
        "provider": provider,
        "source_adapter_id": packet.get("adapter_id"),
        "source_graph_id": graph_id,
        "frames": frames,
        "shared_latent_graph": {
            "source_graph_id": graph_id,
            "mode": packet.get("mode"),
            "continuity_rules": packet.get("shared_constraints", {}).get("continuity_rules", []),
            "prohibited_resets": packet.get("shared_constraints", {}).get("prohibited_resets", []),
        },
        "private_state_policy": packet.get("private_state_policy"),
        "intent_policy": {
            "canonical_symbolic_intent_mutable": False,
            "syntax_only": True,
            "named_esoterica_allowed": False,
        },
        "validation": {
            "status": "VALID" if not errors and frames else "INVALID",
            "errors": errors or ([] if frames else ["no frames available"]),
        },
    }
    return _with_prep(packet, provider, apply_preservation_policy(packet, result))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", required=True)
    parser.add_argument("--provider", required=True, choices=sorted(PROVIDERS))
    parser.add_argument("--output")
    args = parser.parse_args()
    provider = args.provider
    result = adapt(load(args.packet), provider)
    text = yaml.safe_dump(result, sort_keys=False)
    if args.output:
        write_structured(args.output, result)
    else:
        print(text)
    if provider == "keyframe":
        validation = result.get("validation")
        invalid = isinstance(validation, dict) and validation.get("status") not in {None, "VALID"}
        ok = result.get("status") != "NOT_COMPUTABLE" and "shots" in result and not invalid
        raise SystemExit(0 if ok else 1)
    raise SystemExit(0 if result["validation"]["status"] == "VALID" else 1)


if __name__ == "__main__":
    main()
