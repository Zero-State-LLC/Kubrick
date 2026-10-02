#!/usr/bin/env python3
"""Video shot and adapt helpers kept out of the production-surface module."""
from __future__ import annotations

from collections.abc import Callable, Mapping

from brief_constraints import attach_shot_locks, ratio_token, string_list
from prompt_text import dedupe_clauses, join_clauses

Digest = Callable[[object], str]
BaseMeta = Callable[..., dict[str, object]]
Attach = Callable[[dict[str, object], str | None], dict[str, object]]
Revision = Callable[[str | None], str | None]
FieldsFn = Callable[[str | None, str | None], dict[str, object]]
ClaimsFn = Callable[[dict[str, object]], dict[str, object]]
ParseFn = Callable[[str], tuple[dict[str, object], float | None]]


def _text(fields: Mapping[str, object], key: str) -> str:
    value = fields.get(key)
    if isinstance(value, str):
        return value
    return ""


def _strings(fields: Mapping[str, object], key: str, limit: int | None = None) -> list[str]:
    value = fields.get(key)
    if not isinstance(value, list):
        return []
    items = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    if limit is None:
        return items
    return items[:limit]


def _duration_param(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise TypeError(f"duration {value!r} is not a number")
    return float(value)


def _map(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _shot_prompt(shot: Mapping[str, object]) -> str:
    stored = shot.get("prompt")
    if isinstance(stored, str) and stored.strip() and stored.strip() != "NOT_COMPUTABLE":
        return stored.strip()
    start = _map(shot.get("start_state"))
    end = _map(shot.get("end_state"))
    action = _map(shot.get("action"))
    camera = _map(shot.get("camera"))
    return join_clauses(
        [
            start.get("observable") or start.get("summary") or "",
            action.get("path_or_change") or action.get("verb") or "",
            end.get("summary") or "",
            camera.get("framing") or "",
        ]
    )


def _state_constraints(shot: Mapping[str, object]) -> list[str]:
    end = _map(shot.get("end_state"))
    action = _map(shot.get("action"))
    residue = end.get("residue")
    tail: list[object] = list(residue[:2]) if isinstance(residue, list) else []
    raw = [action.get("path_or_change") or "", end.get("summary") or "", *tail]
    kept = [item for item in raw if item and str(item) != "NOT_COMPUTABLE"]
    return dedupe_clauses(kept)


def _negative_list(shot: Mapping[str, object]) -> list[object]:
    raw = shot.get("negative_constraints")
    if isinstance(raw, list):
        return list(raw)
    return []


def _shared_from_shot(shot: Mapping[str, object]) -> dict[str, object]:
    shared: dict[str, object] = {"negative_constraints": _negative_list(shot)}
    locks = string_list(shot.get("character_locks"))
    if locks:
        shared["character_locks"] = locks
    ratio = shot.get("aspect_ratio")
    if isinstance(ratio, str):
        token = ratio_token(ratio)
        if token:
            shared["aspect_ratio"] = token
    return shared


def shot_dict_to_adapter_packet(
    shot: Mapping[str, object],
    provider: str,
    digest: Digest,
) -> dict[str, object]:
    prompt = _shot_prompt(shot)
    params: dict[str, object] = {}
    if shot.get("duration_seconds") is not None:
        params["duration_seconds"] = _duration_param(shot.get("duration_seconds"))
    continuity = shot.get("continuity_invariants")
    frame: dict[str, object] = {
        "frame_id": shot.get("shot_id") or f"frame-{digest(prompt)}",
        "prompt": prompt or "NOT_COMPUTABLE",
        "state_constraints": _state_constraints(shot),
        "continuity_from_previous": list(continuity) if isinstance(continuity, list) else [],
        "provider_parameters": params,
    }
    return {
        "source_graph_id": shot.get("source_state_id") or "surface",
        "provider": provider,
        "frames": [frame],
        "shared_constraints": _shared_from_shot(shot),
        "validation": {"status": "VALID", "errors": []},
        "private_state_policy": {
            "graph_mutation_allowed": False,
            "pattern_links_exposed": False,
            "lexicon_links_exposed": False,
        },
        "duration_seconds": shot.get("duration_seconds"),
    }


def _storyboard_meta(
    brief: str | None,
    evidence: str | None,
    project_id: str,
    duration: float,
    design_text: str | None,
    input_text: str | None,
    design_revision: Revision,
    base_meta: BaseMeta,
    attach: Attach,
) -> dict[str, object] | None:
    from storyboard_prompts import shots_from_text

    shots = (
        shots_from_text(input_text, float(duration))
        or shots_from_text(evidence, float(duration))
        or shots_from_text(brief, float(duration))
    )
    if not shots:
        return None
    meta = base_meta(
        "video",
        "shot",
        project_id,
        {"brief": brief or "", "evidence": evidence or "", "input": input_text or ""},
    )
    result: dict[str, object] = {"implementation_state": "DOMAIN", "shot": shots[0]}
    if len(shots) > 1:
        result["shots"] = shots
    meta["result"] = result
    meta["artifact_type"] = "shot-contract"
    revision = design_revision(design_text)
    first = shots[0]
    if revision and isinstance(first, dict):
        first["source_design_revision"] = revision
    return attach(meta, design_text)


def _framing(fields: Mapping[str, object]) -> str:
    cinematic = _strings(fields, "cinematic_channel")
    if cinematic:
        return cinematic[0]
    if "camera" in _text(fields, "raw").lower():
        return "evidenced framing"
    return "NOT_COMPUTABLE"


def _brief_shot(
    fields: Mapping[str, object],
    project_id: str,
    duration: float,
    design_text: str | None,
    digest: Digest,
    design_revision: Revision,
    claim_bundle: ClaimsFn,
) -> tuple[dict[str, object], str]:
    raw = _text(fields, "raw")
    end_summary = _text(fields, "desired_state_change") or "NOT_COMPUTABLE"
    shot: dict[str, object] = {
        "shot_id": f"shot-{digest(fields)}",
        "source_state_id": f"state-{digest(project_id)}",
        "duration_seconds": float(duration),
        "start_state": {
            "summary": "pre-action institutional arrangement",
            "observable": _text(fields, "dramatic_problem"),
            "evidence": _strings(fields, "observable_evidence", 4),
        },
        "action": {
            "subject": "primary figure",
            "verb": "transfers" if "transfer" in raw.lower() else "changes",
            "path_or_change": end_summary,
            "causal_actions": _strings(fields, "causal_actions", 3),
        },
        "camera": {
            "framing": _framing(fields),
            "position": "NOT_COMPUTABLE",
            "movement": "static unless evidenced",
            "lens_behavior": "NOT_COMPUTABLE",
        },
        "physics": {"required": [], "forbidden": ["teleportation", "identity swap"]},
        "end_state": {
            "summary": end_summary,
            "residue": _strings(fields, "residue", 3),
        },
        "continuity_invariants": [
            "preserve_identity",
            "preserve_ownership_rules",
            "preserve_residue",
        ],
        "negative_constraints": [
            "named occult labels",
            "geometry reset",
            "residue erasure",
        ],
        "claims": claim_bundle(dict(fields)),
    }
    revision = design_revision(design_text)
    if revision:
        shot["source_design_revision"] = revision
    return shot, end_summary


def _missing_shot(action: str, message: str) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "NOT_COMPUTABLE",
        "authority": "NOT_COMPUTABLE",
        "surface": "video",
        "action": action,
        "diagnostic": {"code": "INSUFFICIENT_EVIDENCE", "message": message},
    }
    if action == "shot" and message == "desired end state not evidenced":
        payload["not_computable"] = ["end_state"]
    return payload


def compile_video_shot(
    brief: str | None,
    evidence: str | None,
    project_id: str,
    duration: float,
    design_text: str | None,
    input_text: str | None,
    *,
    extract_fields: FieldsFn,
    design_revision: Revision,
    claim_bundle: ClaimsFn,
    digest: Digest,
    base_meta: BaseMeta,
    attach: Attach,
) -> dict[str, object]:
    routed = _storyboard_meta(
        brief,
        evidence,
        project_id,
        duration,
        design_text,
        input_text,
        design_revision,
        base_meta,
        attach,
    )
    if routed is not None:
        return routed
    fields = extract_fields(brief, evidence)
    if not _text(fields, "raw"):
        return _missing_shot("shot", "Provide --brief or --evidence")
    shot, end_summary = _brief_shot(
        fields,
        project_id,
        duration,
        design_text,
        digest,
        design_revision,
        claim_bundle,
    )
    if end_summary == "NOT_COMPUTABLE":
        return _missing_shot("shot", "desired end state not evidenced")
    attach_shot_locks(shot, brief, evidence, input_text)
    meta = base_meta("video", "shot", project_id, fields)
    meta["result"] = {"implementation_state": "DOMAIN", "shot": shot}
    meta["artifact_type"] = "shot-contract"
    return attach(meta, design_text)


def _capability_stop(
    meta: dict[str, object],
    provider: str,
    diagnostic: object,
    capabilities: object,
) -> dict[str, object]:
    meta["status"] = "NOT_COMPUTABLE"
    meta["authority"] = "NOT_COMPUTABLE"
    meta["diagnostic"] = diagnostic
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "provider": provider,
        "capabilities": capabilities,
    }
    meta["artifact_type"] = "video-prompt-packet"
    meta["not_computable"] = ["provider_capability"]
    return meta


def _provider_failure(adapted: Mapping[str, object], provider: str) -> dict[str, object]:
    code = adapted.get("code") or "PROVIDER_CAPABILITY"
    message = adapted.get("message") or "provider adaptation failed"
    return {
        "implementation_state": "DOMAIN",
        "provider": provider,
        "diagnostic_code": str(code),
        "diagnostic_message": str(message),
        "adapted_packet": adapted,
    }


def compile_video_adapt(
    packet_text: str | None,
    project_id: str,
    provider: str,
    *,
    base_meta: BaseMeta,
    digest: Digest,
    parse_input: ParseFn,
) -> dict[str, object]:
    if not packet_text:
        return _missing_shot("adapt", "--input packet is required")
    from provider_capabilities import capabilities_for, check_video_adapt, normalize_provider

    meta = base_meta("video", "adapt", project_id, {"packet": packet_text, "provider": provider})
    normalized = str(normalize_provider(provider))
    try:
        adapter_packet, duration = parse_input(packet_text)
        cap_err = check_video_adapt(provider, duration=duration)
        if cap_err:
            caps = cap_err.get("capabilities") if isinstance(cap_err, Mapping) else None
            return _capability_stop(meta, normalized, cap_err, caps or capabilities_for(provider))
        from adapt_provider import adapt

        adapted = adapt(dict(adapter_packet), provider)
        if _closed_failure(adapted):
            failure = _provider_failure(adapted, normalized)
            meta["status"] = "NOT_COMPUTABLE"
            meta["authority"] = "NOT_COMPUTABLE"
            meta["diagnostic"] = {
                "code": failure["diagnostic_code"],
                "message": failure["diagnostic_message"],
            }
            meta["result"] = {
                "implementation_state": "DOMAIN",
                "provider": normalized,
                "capabilities": capabilities_for(provider),
                "adapted_packet": failure["adapted_packet"],
            }
            meta["artifact_type"] = "video-prompt-packet"
            meta["not_computable"] = ["provider_capability"]
            return meta
        _store_adapt_result(meta, adapted, provider, normalized, duration)
        token = digest({"packet": packet_text, "provider": provider})
        meta["artifact_id"] = f"kubrick-video-adapt-{token}"
    except Exception as exc:  # noqa: BLE001 — surface must fail closed, not crash
        meta["status"] = "NOT_COMPUTABLE"
        meta["authority"] = "NOT_COMPUTABLE"
        meta["diagnostic"] = {"code": "ADAPTER_NOT_COMPUTABLE", "message": str(exc)}
        meta["result"] = {
            "implementation_state": "DOMAIN",
            "provider": normalized,
            "capabilities": capabilities_for(provider),
        }
    meta["artifact_type"] = "video-prompt-packet"
    return meta


def _closed_failure(adapted: object) -> bool:
    if not isinstance(adapted, Mapping):
        return False
    if adapted.get("status") != "NOT_COMPUTABLE":
        return False
    return "shots" not in adapted and "frames" not in adapted


def _report_status(adapted: Mapping[str, object]) -> tuple[object, str]:
    report = adapted.get("preservation_report") or adapted.get("validation") or {}
    status = "VALID"
    if isinstance(report, Mapping):
        reported = report.get("status")
        if isinstance(reported, str) and reported:
            status = reported
        else:
            validation = adapted.get("validation")
            if isinstance(validation, Mapping) and isinstance(validation.get("status"), str):
                status = str(validation.get("status"))
    return report, status


def _store_adapt_result(
    meta: dict[str, object],
    adapted: Mapping[str, object],
    provider: str,
    normalized: str,
    duration: float | None,
) -> None:
    from provider_capabilities import capabilities_for

    report, status = _report_status(adapted)
    preserved = report if isinstance(report, Mapping) else {"status": status}
    meta["result"] = {
        "implementation_state": "DOMAIN",
        "provider": normalized,
        "capabilities": capabilities_for(provider),
        "adapted_packet": adapted,
        "preservation_report": preserved,
        "duration_seconds": duration,
    }
    if status != "VALID":
        meta["status"] = "NOT_COMPUTABLE"
        meta["authority"] = "NOT_COMPUTABLE"
        meta["not_computable"] = ["provider_semantic_preservation"]
