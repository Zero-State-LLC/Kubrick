"""Prep-only retake runbook (issue #69). Emits PROPOSED Keyframe ops; never calls them."""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence

from video_prep_common import build_parser, closed, emit, number, prepare, rows_of

ACTION = "runbook"


def _wait_and_check() -> list[dict[str, object]]:
    return [
        {"op": "wait", "tool": "keyframe.wait", "on": "processingJobId", "max_wait_seconds": 45},
        {"op": "check_credits", "tool": "keyframe.get_movie", "args": {"includeCredits": True}},
    ]


def _selected(row: Mapping[str, object], retake: set[str] | None) -> bool:
    return retake is None or str(row.get("shot")) in retake


def _clip_members(rows: Sequence[Mapping[str, object]], clip: object) -> list[Mapping[str, object]]:
    return [r for r in rows if r.get("mode") == "in_multi_shot_clip" and r.get("clip_id") == clip]


def _paid_rows(
    rows: Sequence[Mapping[str, object]], retake: set[str] | None
) -> list[Mapping[str, object]]:
    paid: list[Mapping[str, object]] = []
    for row in rows:
        mode = row.get("mode")
        if mode == "new_generation" and _selected(row, retake):
            paid.append(row)
        elif mode == "in_multi_shot_clip":
            if any(_selected(m, retake) for m in _clip_members(rows, row.get("clip_id"))):
                paid.append(row)
    return paid


def _reuse(row: Mapping[str, object], edits: Sequence[Mapping[str, object]]) -> dict[str, object]:
    match = next((e for e in edits if str(e.get("shot")) == str(row.get("shot"))), None)
    return {
        "op": "reuse",
        "shot": row.get("shot"),
        "source": match.get("source") if match else None,
        "trim": {
            "in": match.get("in") if match else None,
            "out": match.get("out") if match else None,
        },
        "credits": 0,
        "paid": False,
    }


def _regen(shots: object, seconds: float, credits: float, clip: object = None) -> dict[str, object]:
    op: dict[str, object] = {"op": "regenerate", "tool": "keyframe.retake_shots"}
    if clip is not None:
        op["clip_id"] = clip
        op["shots"] = shots
    else:
        op["shot"] = shots
    op.update(
        {
            "generated_seconds": round(seconds, 4),
            "credits": round(credits, 4),
            "credits_label": "INFERRED",
            "paid": True,
        }
    )
    return op


def build_ops(
    plan: Mapping[str, object], paid: Sequence[Mapping[str, object]], credits: Mapping[str, float]
) -> list[dict[str, object]]:
    rows = rows_of(plan.get("generation_plan"))
    edits = rows_of(plan.get("edit_plan"))
    paid_ids = {id(r) for r in paid}
    ops: list[dict[str, object]] = []
    seen_clips: set[str] = set()
    for row in rows:
        shot = str(row.get("shot"))
        if row.get("mode") == "in_multi_shot_clip" and id(row) in paid_ids:
            clip = str(row.get("clip_id"))
            if clip in seen_clips:
                continue
            seen_clips.add(clip)
            members = _clip_members(rows, row.get("clip_id"))
            seconds = number(row.get("generated_seconds")) or 0.0
            total = sum(credits.get(str(m.get("shot")), 0.0) for m in members)
            ops.append(_regen([m.get("shot") for m in members], seconds, total, clip))
            ops.extend(_wait_and_check())
        elif id(row) in paid_ids:
            seconds = number(row.get("generated_seconds")) or 0.0
            ops.append(_regen(row.get("shot"), seconds, credits.get(shot, 0.0)))
            ops.extend(_wait_and_check())
        else:
            ops.append(_reuse(row, edits))
    ops.append(
        {
            "op": "rejoin",
            "tool": "keyframe.edit_movie",
            "credits": 0,
            "paid": False,
            "edit_plan": plan.get("edit_plan"),
            "final_clock": plan.get("final_clock"),
        }
    )
    ops.append(_wait_and_check()[1])
    return [{"step": i, **op} for i, op in enumerate(ops, start=1)]


def _paid_labels(paid: Sequence[Mapping[str, object]]) -> set[str]:
    return {str(row.get("shot")) for row in paid if row.get("shot") is not None}


def _refuse_ledger(
    gate: Mapping[str, object], message: str,
) -> dict[str, object]:
    refused = closed(ACTION, message.split()[0], message)
    refused["jev_gate"] = dict(gate)
    refused["run_ledger"] = [{
        "kind": "jev_gate",
        "checked_before_spend": True,
        "result": dict(gate),
        "ledger_error": message,
    }]
    return refused


def _gate_paid(
    document: Mapping[str, object],
    paid: Sequence[Mapping[str, object]],
    provider: str,
    *,
    override: bool,
    override_source: str,
    verdicts_path: str | None,
    ledger_path: str | None,
) -> tuple[dict[str, object], dict[str, object] | None]:
    """Run the Jev gate before any spend figure or paid op is built."""
    from jev_gate import attach_gate, gate_prompts
    from jev_holds import compiled_prompts, select_prompts

    compiled = compiled_prompts(document, provider)
    selected: list[dict[str, object]] | str
    if isinstance(compiled, str):
        selected = compiled
    else:
        selected = select_prompts(compiled, _paid_labels(paid))
    gate = gate_prompts(
        document,
        selected,
        override=override,
        override_source=override_source,
        verdicts_path=verdicts_path,
    )
    if not gate.get("blocks_spend"):
        return gate, None
    payload = closed(ACTION, str(gate.get("code")), str(gate.get("message")))
    attach_gate(payload, gate, ledger_path)
    return gate, payload


def runbook(
    document: Mapping[str, object],
    plan: Mapping[str, object],
    provider: str,
    retake_args: Sequence[str] | None,
    *,
    jev_override: bool = False,
    jev_override_source: str = "",
    jev_verdicts: str | None = None,
    run_ledger: str | None = None,
) -> dict[str, object]:
    from jev_gate import attach_gate, override_requested
    from spend_plan import budget_error, spend_estimate

    rows = rows_of(plan.get("generation_plan"))
    retake = {str(s) for s in retake_args} if retake_args else None
    if retake is not None:
        unknown = sorted(retake - {str(r.get("shot")) for r in rows})
        if unknown:
            return closed(ACTION, "RETAKE_UNKNOWN", f"unknown retake shot(s): {unknown}")
    paid = _paid_rows(rows, retake)
    requested, source = override_requested(jev_override)
    if jev_override_source:
        source = jev_override_source
    _gate, blocked = _gate_paid(
        document,
        paid,
        provider,
        override=requested,
        override_source=source,
        verdicts_path=jev_verdicts,
        ledger_path=run_ledger,
    )
    if blocked is not None:
        return blocked
    estimate = spend_estimate(provider, paid)
    if estimate.get("status") == "NOT_COMPUTABLE":
        payload = closed(ACTION, "PRICING_UNAVAILABLE", f"no pricing for provider {provider!r}")
        attach_gate(payload, _gate, run_ledger)
        return payload
    error = budget_error(estimate, document.get("budget_cap_credits"))
    if error:
        payload = closed(ACTION, error.split()[0].rstrip(":"), error)
        attach_gate(payload, _gate, run_ledger)
        return payload
    credits: dict[str, float] = {}
    for item in rows_of(estimate.get("shots")):
        credits[str(item.get("shot"))] = number(item.get("credits")) or 0.0
    payload = {
        "status": "PROPOSED",
        "authority": "PROPOSED",
        "provider": provider,
        "final_clock": plan.get("final_clock"),
        "ops": build_ops(plan, paid, credits),
        "spend_estimate": estimate,
        "total_inferred_credits": estimate.get("total_credits"),
    }
    ledger_error = attach_gate(payload, _gate, run_ledger)
    if ledger_error:
        return _refuse_ledger(_gate, ledger_error)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    from jev_gate import add_jev_arguments

    parser = build_parser("PROPOSED Keyframe retake runbook (prep only)")
    parser.add_argument("--retake", action="append", default=None, help="shot to regenerate")
    add_jev_arguments(parser)
    args = parser.parse_args(argv)
    prepared = prepare(args, args.retake)
    if isinstance(prepared, dict):
        return emit(args, ACTION, prepared)
    document, plan = prepared
    return emit(
        args,
        ACTION,
        runbook(
            document,
            plan,
            args.provider,
            args.retake,
            jev_override=bool(args.jev_override),
            jev_verdicts=args.jev_verdicts,
            run_ledger=args.run_ledger,
        ),
    )


if __name__ == "__main__":
    sys.exit(main())
