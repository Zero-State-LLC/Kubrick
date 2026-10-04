#!/usr/bin/env python3
"""Board image gate. Pixel checks on start and board images before video spend.

On by default in ``video runbook``. For each paid shot that carries a board
image, the gate:

1. crops the character (a plan box, else the border-contrast box),
2. compares a DINOv2 embedding of the crop with the approved ``ref_pack``
   identity views (``views`` and ``head_lock``) and fails below the identity
   threshold (``BOARD_IDENTITY_MISMATCH``),
3. asks yes-or-no questions built from the character lock list through a
   pluggable judge (``BOARD_LOCK_DETAIL_FAIL``),
4. applies the cheap cut rules: a hard cut may not reuse an earlier board
   (``BOARD_REUSED_ON_CUT``) and a board that hides the identity may not open
   a shot that reveals it (``START_FRAME_HIDES_IDENTITY``).

Fail closed: a check that cannot run (no local model, no reference views, an
unreadable image) is UNVERIFIED and blocks spend like a failure. The only way
past is ``--board-image-opt-out REASON`` (or ``KUBRICK_BOARD_IMAGE_OPT_OUT``),
which skips the image checks for the run and is logged with its reason.
Nothing here calls a paid API or spends credits.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from kubrick.gates.board_image_ledger import (
    attach_board_gate,
    ledger_entry,
    log_opt_out,
    opt_out_requested,
)
from kubrick.gates.board_image_plan import (
    DEFAULT_IDENTITY_THRESHOLD,
    as_list,
    board_source,
    characters_of,
    frame_label,
    frame_labels,
    hides_identity,
    identity_threshold_for,
    identity_views,
    is_hard_cut,
    lock_questions,
    on_screen,
    subject_box,
)
from kubrick.qc.board_pixels import (
    Crop,
    ImageUnreadable,
    RGBImage,
    file_sha256,
    isolate_subject,
    load_rgb,
)
from kubrick.qc.board_vision import (
    BackendUnavailable,
    Embedder,
    LockJudge,
    cosine,
    resolve_embedder,
    resolve_judge,
)

_RECOMMENDATION = (
    "regenerate the board for this shot from the approved ref_pack identity views "
    "(one image, about 7 cr) and rerun the gate before any video spend"
)
# Most specific first. The first blocking code in this order names the result.
_PRIORITY = (
    "BOARD_GATE_CONFIG_INVALID",
    "BOARD_IMAGE_MISSING",
    "BOARD_IMAGE_UNREADABLE",
    "BOARD_REUSED_ON_CUT",
    "START_FRAME_HIDES_IDENTITY",
    "BOARD_IDENTITY_MISMATCH",
    "BOARD_LOCK_DETAIL_FAIL",
    "BOARD_IDENTITY_UNVERIFIED",
    "BOARD_LOCK_DETAIL_UNVERIFIED",
)

__all__ = [
    "DEFAULT_IDENTITY_THRESHOLD",
    "add_board_image_arguments",
    "attach_board_gate",
    "check_board_images",
    "ledger_entry",
    "lock_questions",
    "log_opt_out",
    "opt_out_requested",
]

LogSink = Callable[[Mapping[str, object]], None]


@dataclass
class _Backends:
    """Lazily resolved backends. A resolve failure is remembered, not retried."""

    embedder: Embedder | None = None
    judge: LockJudge | None = None
    answers_path: str | None = None
    embed_error: str = ""
    judge_error: str = ""
    cache: dict[str, list[float]] = field(default_factory=dict)

    def get_embedder(self) -> Embedder:
        if self.embedder is None and not self.embed_error:
            try:
                self.embedder = resolve_embedder()
            except BackendUnavailable as exc:
                self.embed_error = str(exc)
        if self.embedder is None:
            raise BackendUnavailable(self.embed_error)
        return self.embedder

    def get_judge(self) -> LockJudge:
        if self.judge is None and not self.judge_error:
            try:
                self.judge = resolve_judge(self.answers_path)
            except BackendUnavailable as exc:
                self.judge_error = str(exc)
        if self.judge is None:
            raise BackendUnavailable(self.judge_error)
        return self.judge


def add_board_image_arguments(parser: argparse.ArgumentParser) -> None:
    """Flags for spend commands. The gate is on unless an opt-out names a reason."""
    parser.add_argument(
        "--board-image-opt-out",
        default=None,
        metavar="REASON",
        help="skip the board image checks for this run; the reason is logged",
    )
    parser.add_argument(
        "--board-judge-answers",
        default=None,
        help="JSON file of recorded yes/no answers keyed by board sha256 and question",
    )
    parser.add_argument(
        "--board-identity-threshold",
        type=float,
        default=None,
        help=f"identity similarity floor (default {DEFAULT_IDENTITY_THRESHOLD})",
    )


def _row(
    shot: str, check: str, status: str, code: str | None, **extra: object,
) -> dict[str, object]:
    row: dict[str, object] = {"shot": shot, "check": check, "status": status}
    if code:
        row["code"] = code
    row.update({key: value for key, value in extra.items() if value is not None})
    return row


def _identity(
    shot: str,
    name: str,
    crop: Crop,
    views: Sequence[Path],
    threshold: float,
    backends: _Backends,
) -> dict[str, object]:
    base = {"character": name, "crop": crop.method, "threshold": threshold}
    if not views:
        return _row(shot, "identity", "UNVERIFIED", "BOARD_IDENTITY_UNVERIFIED",
                    detail=f"{name} has no approved ref_pack identity views", **base)
    try:
        embedder = backends.get_embedder()
        board = embedder.embed(crop.image)
        scores: list[tuple[float, str]] = []
        skipped: list[str] = []
        for view in views:
            try:
                digest = file_sha256(view)
                if digest not in backends.cache:
                    picture = load_rgb(view)
                    backends.cache[digest] = embedder.embed(isolate_subject(picture).image)
                scores.append((cosine(board, backends.cache[digest]), str(view)))
            except (ImageUnreadable, ValueError) as exc:
                skipped.append(f"{view}: {exc}")
    except BackendUnavailable as exc:
        return _row(shot, "identity", "UNVERIFIED", "BOARD_IDENTITY_UNVERIFIED",
                    detail=str(exc), **base)
    if not scores:
        return _row(shot, "identity", "UNVERIFIED", "BOARD_IDENTITY_UNVERIFIED",
                    detail="no reference view could be read: " + "; ".join(skipped), **base)
    best, ref = max(scores)
    passed = best >= threshold
    return _row(
        shot, "identity", "PASS" if passed else "FAIL",
        None if passed else "BOARD_IDENTITY_MISMATCH",
        score=round(best, 4), ref=ref, embedder=embedder.name,
        skipped_refs=skipped or None, **base,
    )


def _lock_rows(
    shot: str,
    name: str,
    crop: Crop,
    digest: str,
    questions: Sequence[Mapping[str, str]],
    backends: _Backends,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in questions:
        base = {"character": name, "lock_id": item["lock_id"], "question": item["question"],
                "expect": item["expect"]}
        try:
            judge = backends.get_judge()
            answer = judge.ask(crop.image, digest, item["question"])
        except BackendUnavailable as exc:
            rows.append(_row(shot, "lock_detail", "UNVERIFIED", "BOARD_LOCK_DETAIL_UNVERIFIED",
                             detail=str(exc), **base))
            continue
        if answer == item["expect"]:
            rows.append(_row(shot, "lock_detail", "PASS", None, answer=answer,
                             judge=judge.name, **base))
        elif answer in {"yes", "no"}:
            rows.append(_row(shot, "lock_detail", "FAIL", "BOARD_LOCK_DETAIL_FAIL",
                             answer=answer, judge=judge.name, **base))
        else:
            rows.append(_row(shot, "lock_detail", "UNVERIFIED", "BOARD_LOCK_DETAIL_UNVERIFIED",
                             answer=answer, judge=judge.name,
                             detail="the judge did not answer yes or no", **base))
    return rows


def _check_frame(
    document: Mapping[str, object],
    frame: Mapping[str, object],
    shot: str,
    image: RGBImage,
    digest: str,
    base_dir: Path,
    explicit_threshold: float | None,
    backends: _Backends,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    table = characters_of(document)
    names = on_screen(frame, list(table))
    if not names:
        return rows
    single = len(names) == 1
    for name in names:
        spec = table[name]
        threshold = identity_threshold_for(document, spec, explicit_threshold)
        if isinstance(threshold, str):
            rows.append(_row(shot, "config", "FAIL", "BOARD_GATE_CONFIG_INVALID",
                             character=name, detail=threshold))
            continue
        box = subject_box(frame, name, single)
        if box is None and not single:
            crop = Crop(image, (0, 0, image.width, image.height), "full_frame")
        else:
            crop = isolate_subject(image, box)
        views = identity_views(spec, base_dir)
        rows.append(_identity(shot, name, crop, views, threshold, backends))
        questions = lock_questions(document, name, spec)
        rows.extend(_lock_rows(shot, name, crop, digest, questions, backends))
    return rows


def _result(
    *,
    status: str,
    code: str,
    blocks: bool,
    message: str,
    checks: Sequence[Mapping[str, object]],
    warnings: Sequence[Mapping[str, object]],
    opt_out: bool = False,
    opt_out_reason: str = "",
    opt_out_source: str = "",
    backends: _Backends | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "status": status,
        "authority": "NOT_COMPUTABLE" if blocks else "PROPOSED",
        "code": code,
        "blocks_spend": blocks,
        "checked_before_spend": True,
        "default_on": True,
        "policy": "fail_closed",
        "opt_out": opt_out,
        "opt_out_reason": opt_out_reason or None,
        "opt_out_source": opt_out_source or None,
        "default_identity_threshold": DEFAULT_IDENTITY_THRESHOLD,
        "checks": [dict(item) for item in checks],
        "warnings": [dict(item) for item in warnings],
        "message": message,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    if blocks:
        result["recommendation"] = _RECOMMENDATION
    if backends is not None:
        result["backends"] = {
            "embedder": backends.embedder.name if backends.embedder else None,
            "embedder_error": backends.embed_error or None,
            "judge": backends.judge.name if backends.judge else None,
            "judge_error": backends.judge_error or None,
        }
    return result


def check_board_images(
    document: Mapping[str, object],
    *,
    shots: set[str] | None = None,
    base_dir: str | Path | None = None,
    embedder: Embedder | None = None,
    judge: LockJudge | None = None,
    answers_path: str | None = None,
    identity_threshold: float | None = None,
    opt_out: bool = False,
    opt_out_reason: str = "",
    opt_out_source: str = "",
    log: LogSink | None = None,
) -> dict[str, object]:
    """Check the board image of every selected shot. ``shots=None`` checks them all."""
    if opt_out:
        return _opted_out(opt_out_reason, opt_out_source, shots, log)
    root = Path(base_dir) if base_dir is not None else Path.cwd()
    backends = _Backends(embedder=embedder, judge=judge, answers_path=answers_path)
    checks: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    earlier: dict[str, str] = {}
    checked = 0
    for index, frame in enumerate(_frame_rows(document), start=1):
        shot = frame_label(frame, index)
        path, explicit, asset = board_source(frame, root)
        selected = shots is None or bool(frame_labels(frame, index) & shots)
        if path is None:
            if selected and asset:
                warnings.append({
                    "shot": shot,
                    "code": "BOARD_IMAGE_NOT_LOCAL",
                    "message": f"start_frame.asset {asset!r} is not a local image; "
                               "its pixels were not checked",
                    "recommendation": "set board_image to the local board file to check it",
                })
            continue
        try:
            digest = file_sha256(path)
            image = load_rgb(path) if selected else None
        except ImageUnreadable as exc:
            if selected:
                code = "BOARD_IMAGE_MISSING" if not path.is_file() else "BOARD_IMAGE_UNREADABLE"
                checks.append(_row(shot, "image", "FAIL", code, path=str(path), detail=str(exc),
                                   explicit=explicit))
            continue
        reused = earlier.get(digest)
        earlier.setdefault(digest, shot)
        if not selected or image is None:
            continue
        checked += 1
        checks.append(_row(shot, "image", "PASS", None, path=str(path), sha256=digest,
                           size=[image.width, image.height]))
        if reused is not None and is_hard_cut(frame):
            checks.append(_row(shot, "cut_rule", "FAIL", "BOARD_REUSED_ON_CUT", path=str(path),
                               detail=f"hard cut reuses the board from shot {reused}"))
        if hides_identity(frame):
            checks.append(_row(shot, "cut_rule", "FAIL", "START_FRAME_HIDES_IDENTITY",
                               detail="the board hides the identity the shot reveals"))
        checks.extend(_check_frame(document, frame, shot, image, digest, root,
                                   identity_threshold, backends))
    return _summarize(checks, warnings, checked, backends)


def _frame_rows(document: Mapping[str, object]) -> list[Mapping[str, object]]:
    return [item for item in as_list(document.get("frames")) if isinstance(item, Mapping)]


def _opted_out(
    reason: str, source: str, shots: set[str] | None, log: LogSink | None,
) -> dict[str, object]:
    if not reason:
        return _result(
            status="BLOCKED",
            code="BOARD_OPT_OUT_REASON_MISSING",
            blocks=True,
            message="the board image opt-out needs a non-blank reason",
            checks=[],
            warnings=[],
        )
    record: dict[str, object] = {
        "event": "BOARD_IMAGE_OPT_OUT",
        "source": source or "flag",
        "reason": reason,
        "shots": sorted(shots) if shots is not None else None,
    }
    if log is None:
        log_opt_out(record)
    else:
        log(record)
    return _result(
        status="PASS",
        code="BOARD_IMAGE_OPT_OUT",
        blocks=False,
        message=f"board image checks skipped by operator opt-out: {reason}",
        checks=[],
        warnings=[],
        opt_out=True,
        opt_out_reason=reason,
        opt_out_source=source or "flag",
    )


def _summarize(
    checks: Sequence[Mapping[str, object]],
    warnings: Sequence[Mapping[str, object]],
    checked: int,
    backends: _Backends,
) -> dict[str, object]:
    bad = [row for row in checks if row.get("status") in {"FAIL", "UNVERIFIED"}]
    if not bad:
        code = "BOARD_IMAGES_CLEAR" if checked else "NO_BOARD_IMAGES"
        message = (
            f"{checked} board image(s) passed identity and lock checks"
            if checked else "no paid shot carries a local board image"
        )
        return _result(status="PASS", code=code, blocks=False, message=message,
                       checks=checks, warnings=warnings, backends=backends)
    codes = {str(row.get("code")) for row in bad}
    code = next((item for item in _PRIORITY if item in codes), str(bad[0].get("code")))
    parts = []
    for row in bad:
        detail = row.get("detail")
        score = row.get("score")
        text = f"shot {row.get('shot')}: {row.get('code')}"
        if row.get("character"):
            text += f" {row.get('character')}"
        if score is not None:
            text += f" similarity {score} below {row.get('threshold')}"
        if row.get("lock_id") and row.get("answer") is not None:
            text += f" lock {row.get('lock_id')!r} answered {row.get('answer')}"
        elif row.get("lock_id"):
            text += f" lock {row.get('lock_id')!r}"
        if isinstance(detail, str) and detail:
            text += f" ({detail})"
        parts.append(text)
    message = "; ".join(parts) + f"; {_RECOMMENDATION}, or pass --board-image-opt-out REASON"
    return _result(status="BLOCKED", code=code, blocks=True, message=message,
                   checks=checks, warnings=warnings, backends=backends)


def main(argv: Sequence[str] | None = None) -> int:
    from kubrick.runtime.io_safety import load_structured, write_text_bounded

    parser = argparse.ArgumentParser(
        description="Check board images against reference views and locks. No spend.",
    )
    parser.add_argument("--input", required=True, help="storyboard plan (YAML/JSON)")
    parser.add_argument("--shot", action="append", default=None, help="shot to check")
    parser.add_argument("--out", default=None)
    add_board_image_arguments(parser)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        raw = load_structured(args.input)
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "NOT_COMPUTABLE", "message": str(exc)}, indent=2))
        return 2
    if not isinstance(raw, Mapping):
        print(json.dumps({"status": "NOT_COMPUTABLE", "message": "plan must be a mapping"}))
        return 2
    requested, reason, source = opt_out_requested(args.board_image_opt_out)
    report = check_board_images(
        raw,
        shots=set(args.shot) if args.shot else None,
        base_dir=Path(args.input).resolve().parent,
        answers_path=args.board_judge_answers,
        identity_threshold=args.board_identity_threshold,
        opt_out=requested,
        opt_out_reason=reason,
        opt_out_source=source,
    )
    text = json.dumps(report, indent=2)
    if args.out:
        write_text_bounded(args.out, text + "\n")
    print(text)
    return 4 if report.get("blocks_spend") else 0


if __name__ == "__main__":
    sys.exit(main())
