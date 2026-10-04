#!/usr/bin/env python3
"""Full take QC on top of the fixture scorer.

VLM verdicts, identity similarity, and timestamps are fixtures. ffmpeg runs
only when the document opts in and the caller passes a runner. This module
does not call subprocess and does not call a model.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from kubrick.qc.vision_observe import sample_times, score_take

Runner = Callable[[Sequence[Mapping[str, object]]], Mapping[str, object]]
_IDENTITY = 0.85


def _float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _mapping(value: object) -> Mapping[str, object] | None:
    if isinstance(value, Mapping):
        return value
    return None


def _defect(code: str, hold_id: str) -> dict[str, object]:
    return {"hold_id": hold_id, "score": 2, "defect_code": code, "t_start": 0.0, "t_end": 0.0}


def _opted_in(document: Mapping[str, object]) -> bool:
    if document.get("ffmpeg") is True:
        return True
    opt = _mapping(document.get("opt_in"))
    return opt is not None and opt.get("ffmpeg") is True


def _vlm(document: Mapping[str, object]) -> tuple[list[dict[str, object]], str | None]:
    raw = document.get("vlm")
    if raw is None:
        return [], None
    verdict = _mapping(raw)
    if verdict is None:
        return [], "vlm verdict must be an object"
    live = verdict.get("live") is True
    named = bool(_text(verdict.get("provider")) or _text(verdict.get("endpoint")))
    if live or named:
        return [], "VLM calls are not run; supply a fixture verdict"
    status = _text(verdict.get("status")).casefold()
    if status in {"", "not_computable"}:
        return [], "vlm fixture verdict is not computable"
    if status == "pass":
        return [], None
    if status != "fail":
        return [], "vlm fixture status must be pass, fail, or not_computable"
    defects: list[dict[str, object]] = []
    rows = verdict.get("defects")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return [], "vlm fail verdict has no defects"
    for item in rows:
        if not isinstance(item, Mapping):
            continue
        code = _text(item.get("defect_code"))
        if code:
            defects.append(_defect(code, _text(item.get("hold_id")) or "vlm"))
    if not defects:
        return [], "vlm fail verdict has no defects"
    return defects, None


def _text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _identity(document: Mapping[str, object]) -> tuple[list[dict[str, object]], str | None]:
    raw = document.get("identity")
    if raw is None:
        return [], None
    found = _mapping(raw)
    if found is None:
        return [], "identity similarity must be an object"
    similarity = _float(found.get("similarity"))
    threshold = _float(found.get("threshold"))
    if threshold is None:
        threshold = _IDENTITY if "threshold" not in found else None
    if similarity is None or threshold is None:
        return [], "identity similarity or threshold is missing"
    if similarity < threshold:
        return [_defect("identity", "identity")], None
    return [], None


def _times(value: object) -> list[float] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    found: list[float] = []
    for item in value:
        if isinstance(item, Mapping):
            number = _float(item.get("t"))
        else:
            number = _float(item)
        if number is None:
            return None
        found.append(number)
    return found


def _timestamps(
    document: Mapping[str, object], samples: Sequence[float],
) -> tuple[list[dict[str, object]], str | None]:
    if "timestamps" not in document:
        return [], None
    duration = _float(document.get("duration_seconds"))
    times = _times(document.get("timestamps"))
    if duration is None or times is None:
        return [], "timestamps are not a list of times inside the duration"
    if any(point < 0 or point > duration for point in times):
        return [], "a timestamp falls outside the take duration"
    missing = [point for point in samples if not any(abs(point - seen) <= 0.001 for seen in times)]
    if missing:
        return [_defect("timestamp_gap", "clock")], None
    return [], None


def _ffmpeg(
    document: Mapping[str, object], runner: Runner | None,
) -> tuple[list[dict[str, object]], str | None, list[Mapping[str, object]]]:
    if not _opted_in(document):
        return [], None, []
    if runner is None:
        message = "ffmpeg was requested and no runner is configured; the command is not executed"
        return [], message, []
    from kubrick.qc.video_cut_qa import cut_qa

    plan = _mapping(document.get("plan")) or {"final_clock": document.get("duration_seconds")}
    final = _text(document.get("final")) or "final.mp4"
    commands = cut_qa(document, plan, final, 0.3, 0.1)
    rows = commands.get("commands")
    payload = rows if isinstance(rows, list) else []
    issued = [item for item in payload if isinstance(item, Mapping)]
    try:
        result = runner(issued)
    except Exception as exc:
        return [], f"ffmpeg runner failed: {exc}", issued
    if result.get("status") == "NOT_COMPUTABLE":
        return [], _text(result.get("message")) or "ffmpeg runner is not computable", issued
    defects: list[dict[str, object]] = []
    raw = result.get("defects")
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, Mapping) and _text(item.get("defect_code")):
                defects.append(_defect(_text(item.get("defect_code")), "ffmpeg"))
    return defects, None, issued


def score_full(
    document: Mapping[str, object],
    *,
    runner: Runner | None = None,
) -> dict[str, object]:
    """Score the fixture core, then the full-take checks. Reports stay PROPOSED."""
    core = score_take(document)
    samples = core.get("samples")
    clock = [float(item) for item in samples] if isinstance(samples, list) else []
    if not clock:
        duration = _float(document.get("duration_seconds")) or 0.0
        clock = sample_times(duration, None, 1.6)
    blocks: list[str] = []
    extra: list[dict[str, object]] = []
    for defects, message in (_vlm(document), _identity(document), _timestamps(document, clock)):
        extra.extend(defects)
        if message:
            blocks.append(message)
    ffmpeg_defects, ffmpeg_message, issued = _ffmpeg(document, runner)
    extra.extend(ffmpeg_defects)
    if ffmpeg_message:
        blocks.append(ffmpeg_message)
    raw_defects = core.get("defects")
    found: list[dict[str, object]] = []
    if isinstance(raw_defects, list):
        found.extend(item for item in raw_defects if isinstance(item, dict))
    found.extend(extra)
    blocked = core.get("status") == "NOT_COMPUTABLE" or bool(blocks)
    report = dict(core)
    report["status"] = "NOT_COMPUTABLE" if blocked else "PROPOSED"
    report["authority"] = report["status"]
    report["defects"] = found
    executed = bool(issued) and not ffmpeg_message
    report["ffmpeg"] = {"opted_in": _opted_in(document), "executed": executed}
    if blocks:
        report["message"] = "; ".join(blocks)
    return report
