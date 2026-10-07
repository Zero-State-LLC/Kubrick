"""Prep-only dialogue cue sheet and mix plan (issue #71). Never calls ElevenLabs."""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence

from kubrick.providers.video_prep_common import (
    build_parser,
    closed,
    emit,
    frame_label_matches,
    frames_of,
    number,
    prepare,
    timeline,
)

ACTION = "cues"
MIX_VARIANTS: list[dict[str, object]] = [
    {
        "name": "ducked",
        "music_under_dialogue_db": -12,
        "integrated_lufs": -14,
        "true_peak_dbtp": -1,
    },
    {
        "name": "muted",
        "music_under_dialogue_db": None,
        "integrated_lufs": -14,
        "true_peak_dbtp": -1,
    },
]


def parse_line(raw: object) -> tuple[str | None, str] | None:
    if isinstance(raw, str):
        if ":" in raw:
            speaker, text = raw.split(":", 1)
            return (speaker.strip() or None), text.strip()
        return None, raw.strip()
    if isinstance(raw, Mapping):
        speaker = raw.get("character", raw.get("speaker"))
        text = raw.get("line", raw.get("text"))
        if isinstance(text, str):
            return (str(speaker) if speaker is not None else None), text.strip()
    return None


def _voice_of(document: Mapping[str, object], speaker: str) -> Mapping[str, object] | None:
    chars = document.get("characters")
    if not isinstance(chars, Mapping):
        return None
    for name, entry in chars.items():
        if str(name).casefold() == speaker.casefold() and isinstance(entry, Mapping):
            voice = entry.get("voice")
            return voice if isinstance(voice, Mapping) else None
    return None


def resolve_voice(
    document: Mapping[str, object], speaker: str | None, shot: object
) -> tuple[str | None, str | None]:
    """Return (voice_id, violation_message)."""
    voice = _voice_of(document, speaker) if speaker else None
    if voice is None:
        return None, None
    if voice.get("speaks") is False:
        return None, f"speaker {speaker!r} is locked silent but speaks in shot {shot!r}"
    raw_banned = voice.get("never_clone_of")
    banned = {str(b).casefold() for b in raw_banned} if isinstance(raw_banned, list) else set()
    for key in ("library_id", "voice_id", "name"):
        ident = voice.get(key)
        if isinstance(ident, str) and ident and ident.casefold() in banned:
            return None, f"voice {ident!r} for {speaker!r} in shot {shot!r} is in never_clone_of"
    vid = voice.get("library_id") or voice.get("voice_id")
    if not isinstance(vid, str) or not vid:
        return None, None
    return vid, None


def build_cues(
    document: Mapping[str, object], rows: Sequence[Mapping[str, object]]
) -> tuple[list[dict[str, object]], list[dict[str, object]]] | str:
    cues: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    frames = frames_of(document)
    for row in rows:
        frame = next((f for f in frames if frame_label_matches(f, row.get("shot"))), None)
        lines = frame.get("speech_lines") if frame else None
        for raw in lines if isinstance(lines, list) else []:
            parsed = parse_line(raw)
            if parsed is None:
                continue
            speaker, text = parsed
            voice, violation = resolve_voice(document, speaker, row.get("shot"))
            if violation:
                return violation
            if voice is None:
                warnings.append(
                    {
                        "code": "VOICE_UNASSIGNED",
                        "shot": row.get("shot"),
                        "speaker": speaker,
                        "message": "no library_id/voice_id for speaker",
                    }
                )
            cues.append(
                {
                    "cue": len(cues) + 1,
                    "shot": row.get("shot"),
                    "start": row.get("start"),
                    "end": row.get("end"),
                    "speaker": speaker,
                    "text": text,
                    "characters": len(text),
                    "voice": voice,
                }
            )
    return cues, warnings


def estimate(
    document: Mapping[str, object], cues: Sequence[Mapping[str, object]]
) -> dict[str, object] | str:
    cfg = document.get("elevenlabs")
    cfg = cfg if isinstance(cfg, Mapping) else {}
    raw_rate = cfg.get("credits_per_character", 1.0)
    rate = number(raw_rate)
    if rate is None or rate < 0:
        return "ELEVENLABS_RATE_INVALID"
    cap = number(cfg.get("cap_credits")) if "cap_credits" in cfg else None
    if "cap_credits" in cfg and cap is None:
        return "ELEVENLABS_CAP_UNVERIFIABLE"
    chars = sum(int(number(c.get("characters")) or 0) for c in cues)
    total = round(rate * chars, 4)
    return {
        "label": "INFERRED",
        "credits_per_character": rate,
        "characters": chars,
        "total_credits": total,
        "cap_credits": cap,
        "within_cap": None if cap is None else total <= cap,
    }


def _gate_lines(
    document: Mapping[str, object],
    cues: Sequence[Mapping[str, object]],
    *,
    override: bool,
    override_source: str,
    verdicts_path: str | None,
    ledger_path: str | None,
) -> tuple[dict[str, object], dict[str, object] | None]:
    """Judge spoken lines before the ElevenLabs credit estimate."""
    from kubrick.gates.jev_gate import attach_gate, gate_prompts
    from kubrick.gates.jev_holds import prompts_for_cues

    gate = gate_prompts(
        document,
        prompts_for_cues(document, cues),
        override=override,
        override_source=override_source,
        verdicts_path=verdicts_path,
    )
    if not gate.get("blocks_spend"):
        return gate, None
    payload = closed(ACTION, str(gate.get("code")), str(gate.get("message")))
    attach_gate(payload, gate, ledger_path)
    return gate, payload


def _amount(value: object) -> float | None:
    """A non-negative fixture number, or None. Booleans are not numbers here."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return float(value)


def _shown(value: float) -> int | float:
    return int(value) if float(value).is_integer() else value


def _sfx_line(
    status: str, credits: int | float | None, line: str, **extra: object,
) -> dict[str, object]:
    return {"status": status, "credits": credits, "line": line, "source": "fixture", **extra}


def _frame_effects(frames: Sequence[Mapping[str, object]]) -> list[tuple[object, object]]:
    found: list[tuple[object, object]] = []
    for frame in frames:
        raw = frame.get("sfx")
        if raw is None:
            continue
        shot = frame.get("shot_id", frame.get("frame_id"))
        entries = raw if isinstance(raw, list) else [raw]
        found.extend((shot, entry) for entry in entries)
    return found


def sfx_estimate(
    document: Mapping[str, object], frames: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    """SFX credits from fixtures only. ElevenLabs is not called. Issue #108.

    A flat ``sfx.credits`` wins. Otherwise frame ``sfx`` effects are priced at
    ``sfx.credits_per_second`` (``seconds`` per effect, else ``sfx.default_seconds``).
    No effects and no ``sfx`` block is an explicit zero. Effects with no rate are
    ``MISSING`` so the cue sheet cannot look fully costed.
    """
    raw = document.get("sfx")
    effects = _frame_effects(frames)
    bad = _sfx_line("NOT_COMPUTABLE", None, "sfx not computable")
    if raw is not None and not isinstance(raw, Mapping):
        return bad
    cfg: Mapping[str, object] = raw if isinstance(raw, Mapping) else {}
    if "credits" in cfg:
        flat = _amount(cfg.get("credits"))
        if flat is None:
            return bad
        return _sfx_line("PROPOSED", _shown(flat), f"sfx {_shown(flat)}", effects=len(effects))
    if not effects:
        return _sfx_line("PROPOSED", 0, "sfx 0", effects=0)
    if "credits_per_second" not in cfg:
        return _sfx_line(
            "MISSING", None, "sfx estimate missing", code="SFX_ESTIMATE_MISSING",
            effects=len(effects),
        )
    rate = _amount(cfg.get("credits_per_second"))
    default = _amount(cfg.get("default_seconds")) if "default_seconds" in cfg else None
    if rate is None or ("default_seconds" in cfg and default is None):
        return bad
    detail: list[dict[str, object]] = []
    total = 0.0
    for shot, entry in effects:
        name: object = entry
        seconds: float | None = default
        if isinstance(entry, Mapping):
            name = entry.get("effect", entry.get("name"))
            if "seconds" in entry:
                seconds = _amount(entry.get("seconds"))
        if not isinstance(name, str) or not name.strip() or seconds is None:
            return bad
        cost = round(seconds * rate, 4)
        total += cost
        detail.append({
            "shot": shot, "effect": name.strip(), "seconds": _shown(seconds),
            "credits": _shown(cost),
        })
    shown = _shown(round(total, 4))
    return _sfx_line(
        "PROPOSED", shown, f"sfx {shown}", effects=len(detail),
        credits_per_second=_shown(rate), effects_detail=detail,
    )


def cue_sheet(
    document: Mapping[str, object],
    plan: Mapping[str, object],
    *,
    jev_override: bool = False,
    jev_verdicts: str | None = None,
    run_ledger: str | None = None,
) -> dict[str, object]:
    from kubrick.gates.jev_gate import attach_gate, override_requested

    try:
        rows = timeline(plan)
    except ValueError as exc:
        return closed(ACTION, "EDIT_PLAN_INVALID", str(exc))
    built = build_cues(document, rows)
    if isinstance(built, str):
        return closed(ACTION, "VOICE_LOCK_VIOLATION", built)
    cues, warnings = built
    requested, source = override_requested(jev_override)
    gate, blocked = _gate_lines(
        document,
        cues,
        override=requested,
        override_source=source,
        verdicts_path=jev_verdicts,
        ledger_path=run_ledger,
    )
    if blocked is not None:
        return blocked
    est = estimate(document, cues)
    if isinstance(est, str):
        payload = closed(ACTION, est, "elevenlabs pricing/cap config is not a valid number")
        attach_gate(payload, gate, run_ledger)
        return payload
    if est["within_cap"] is False:
        payload = closed(
            ACTION,
            "ELEVENLABS_CAP_EXCEEDED",
            f"inferred {est['total_credits']} credits exceed cap {est['cap_credits']}",
        )
        attach_gate(payload, gate, run_ledger)
        return payload
    cued = [
        frame for frame in frames_of(document)
        if any(frame_label_matches(frame, row.get("shot")) for row in rows)
    ]
    sfx = sfx_estimate(document, cued)
    if sfx.get("status") == "MISSING":
        refused = closed(
            ACTION, "SFX_ESTIMATE_MISSING",
            "frames declare sfx but the plan has no sfx.credits or sfx.credits_per_second",
        )
        attach_gate(refused, gate, run_ledger)
        return refused
    if sfx.get("status") != "PROPOSED":
        refused = closed(ACTION, "SFX_NOT_COMPUTABLE", "sfx estimate is not a fixture number")
        attach_gate(refused, gate, run_ledger)
        return refused
    payload = {
        "status": "PROPOSED",
        "authority": "PROPOSED",
        "final_clock": plan.get("final_clock"),
        "cues": cues,
        "mix_variants": [dict(v) for v in MIX_VARIANTS],
        "elevenlabs_estimate": est,
        "sfx_estimate": sfx,
        "warnings": warnings,
    }
    ledger_error = attach_gate(payload, gate, run_ledger)
    if ledger_error:
        refused = closed(ACTION, ledger_error.split()[0], ledger_error)
        refused["jev_gate"] = dict(gate)
        refused["run_ledger"] = [{
            "kind": "jev_gate",
            "checked_before_spend": True,
            "result": dict(gate),
            "ledger_error": ledger_error,
        }]
        return refused
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    from kubrick.gates.jev_gate import add_jev_arguments

    parser = build_parser("PROPOSED dialogue cue sheet and mix plan (prep only)")
    add_jev_arguments(parser)
    args = parser.parse_args(argv)
    prepared = prepare(args)
    if isinstance(prepared, dict):
        return emit(args, ACTION, prepared)
    document, plan = prepared
    return emit(
        args,
        ACTION,
        cue_sheet(
            document,
            plan,
            jev_override=bool(args.jev_override),
            jev_verdicts=args.jev_verdicts,
            run_ledger=args.run_ledger,
        ),
    )


if __name__ == "__main__":
    sys.exit(main())
