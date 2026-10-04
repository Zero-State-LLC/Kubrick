#!/usr/bin/env python3
"""Atomic yes-or-no questions for the board image gate lock checks.

A lock is asked as one direct question per clause, each with its expected
answer, instead of one compound "is this statement true" question. On the
MYSLEF EP-01 set the Spark judge was right about 9 times in 10 on direct
single questions and blocked 36 of 60 clean boards on the compound wording
(docs/BOARD-IMAGE-CALIBRATION.md).

Clause rules, applied to the lock text:

- ``no X`` and ``not X`` ask "Does the character show any X?" and expect ``no``.
- ``S never V`` asks "Do S V?" (or "Does S V?") and expects ``no``.
- Any other clause asks "Does the character show X?" (or "Is it true in this
  image that X?" when X has its own verb) and expects ``yes``.

The questions name the character, not the image: on EP-01 "Does the image
show any words?" blocked 16 clean alley boards for street signs, and "Does
the character show any words?" blocked 1.

Clauses are split at commas, semicolons, and ``and`` only where the next part
starts a new negative clause, so "no light on the head, hood or temple" stays
one question. A lock may list its own ``checks`` (``question``, ``expect``,
``severity``) to replace the split; they inherit the lock's ``severity``.

Severity is ``block`` or ``warn``. A question about the left or right side
defaults to ``warn``: the Spark judge scored 0.46 on lens sides. An explicit
``severity`` wins. A bad ``severity`` or ``expect``, a check with no question,
or one question given two different ``expect`` values is
``BOARD_GATE_CONFIG_INVALID`` and blocks; it is never dropped.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence

from kubrick.qc.board_pixels import RGBImage
from kubrick.qc.board_vision import BackendUnavailable, LockJudge

SEVERITIES = ("block", "warn")
_NEGATORS = ("no ", "not ", "never ")
_SIDE = re.compile(r"\b(left|right)\b", re.IGNORECASE)
_NEVER = re.compile(r"^(?P<subject>.+?)\s+never\s+(?P<verb>\S+)(?P<rest>.*)$", re.IGNORECASE)
_FINITE = re.compile(r"\b(is|are|has|have|stays|stay)\b", re.IGNORECASE)
_IRREGULAR = {"has": "have", "does": "do", "goes": "go"}
_SPLIT = re.compile(r"\s*[,;]\s*|\s+and\s+(?=(?:no|not|never)\s)", re.IGNORECASE)


def _prefix(name: str) -> str:
    return f"Answer only yes or no. Look at the character {name} in this image. "


def _starts_clause(part: str) -> bool:
    lowered = part.casefold()
    return lowered.startswith(_NEGATORS) or _NEVER.match(part) is not None


def split_clauses(text: str) -> list[str]:
    """Clauses of a lock text. A part that does not start a clause joins the last one."""
    parts = [part.strip() for part in _SPLIT.split(text.strip().rstrip(".")) if part.strip()]
    clauses: list[str] = []
    for part in parts:
        if clauses and not _starts_clause(part):
            clauses[-1] = f"{clauses[-1]}, {part}"
        else:
            clauses.append(part)
    return clauses


def _base_verb(verb: str) -> str:
    lowered = verb.casefold()
    if lowered in _IRREGULAR:
        return _IRREGULAR[lowered]
    if lowered.endswith("ies") and len(lowered) > 4:
        return verb[:-3] + "y"
    if re.search(r"(ch|sh|x|ss|z)es$", lowered):
        return verb[:-2]
    if lowered.endswith("s") and not lowered.endswith("ss"):
        return verb[:-1]
    return verb


def _never_question(match: re.Match[str]) -> str:
    subject = match.group("subject").strip()
    verb = match.group("verb")
    rest = match.group("rest").rstrip()
    words = subject.split()
    if len(words) > 1 and words[-1].casefold() in {"is", "are"}:
        copula = words[-1].casefold().capitalize()
        return f"{copula} {' '.join(words[:-1])} {verb}{rest}?"
    head = words[-1].casefold()
    plural = head.endswith("s") and not head.endswith("ss")
    auxiliary = "Do" if plural else "Does"
    return f"{auxiliary} {subject} {_base_verb(verb)}{rest}?"


def clause_question(clause: str) -> tuple[str, str]:
    """``(question, expect)`` for one clause, without the prompt prefix."""
    lowered = clause.casefold()
    for negator in ("no ", "not "):
        if lowered.startswith(negator):
            return f"Does the character show any {clause[len(negator):].strip()}?", "no"
    match = _NEVER.match(clause)
    if match is not None:
        return _never_question(match), "no"
    if _FINITE.search(clause):
        return f"Is it true in this image that {clause}?", "yes"
    return f"Does the character show {clause}?", "yes"


def default_severity(question: str) -> str:
    return "warn" if _SIDE.search(question) else "block"


def severity_of(
    row: Mapping[str, object], question: str, inherited: object = None,
) -> str | None:
    """The row's severity, else ``inherited``, else the side default. ``None`` when invalid."""
    raw = row.get("severity", inherited)
    if raw is None:
        return default_severity(question)
    value = str(raw).strip().casefold()
    return value if value in SEVERITIES else None


def _check(lock_id: str, question: str, expect: str, severity: str, part: int,
           source: str) -> dict[str, str]:
    return {"lock_id": lock_id, "question": question, "expect": expect,
            "severity": severity, "part": str(part), "lock_text": source}


def invalid_check(lock_id: str, question: str, error: str) -> dict[str, str]:
    """A check that cannot be asked. The gate reports it as ``BOARD_GATE_CONFIG_INVALID``."""
    return {"lock_id": lock_id, "question": question, "expect": "", "severity": "block",
            "part": "", "lock_text": question, "error": error}


def _expect_text(raw: object) -> str:
    """``expect`` as text. YAML reads a bare ``no`` as ``False``, which means ``no``."""
    if isinstance(raw, bool):
        return "yes" if raw else "no"
    if raw is None or raw == "":
        return "yes"
    return str(raw).strip().casefold()


def explicit_checks(
    lock_id: str, rows: Sequence[object], inherited: object = None,
) -> list[dict[str, str]]:
    """Hand-written checks. A row with no question, a bad expect, or a bad severity is invalid.

    ``inherited`` is the lock's own ``severity``; a row's ``severity`` wins.
    """
    found: list[dict[str, str]] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            found.append(invalid_check(lock_id, "", f"check {index} is not a mapping"))
            continue
        question = str(row.get("question") or "").strip()
        expect = _expect_text(row.get("expect"))
        severity = severity_of(row, question, inherited)
        if not question:
            found.append(invalid_check(lock_id, "", f"check {index} has no question"))
        elif expect not in {"yes", "no"}:
            found.append(invalid_check(lock_id, question, f"expect must be yes or no, not "
                                                          f"{row.get('expect')!r}"))
        elif severity is None:
            raw = row.get("severity", inherited)
            found.append(invalid_check(lock_id, question,
                                       f"severity must be block or warn, not {raw!r}"))
        else:
            found.append(_check(lock_id, question, expect, severity, index, question))
    return found


def atomic_checks(
    name: str, lock_id: str, text: str, severity: object = None,
) -> list[dict[str, str]]:
    """One direct question per clause of ``text``. ``severity`` applies to every part."""
    found: list[dict[str, str]] = []
    for index, clause in enumerate(split_clauses(text), start=1):
        body, expect = clause_question(clause)
        question = _prefix(name) + body
        level = severity_of({"severity": severity}, body)
        if level is None:
            found.append(invalid_check(lock_id, question, f"severity must be block or warn, "
                                                          f"not {severity!r}"))
            continue
        found.append(_check(lock_id, question, expect, level, index, text))
    return found


def _lock_row(shot: str, status: str, code: str | None, **extra: object) -> dict[str, object]:
    row: dict[str, object] = {"shot": shot, "check": "lock_detail", "status": status}
    if code:
        row["code"] = code
    row.update({key: value for key, value in extra.items() if value is not None})
    return row


def _verdict(answer: str, expect: str) -> tuple[str, str | None, str | None]:
    if answer == expect:
        return "PASS", None, None
    if answer in {"yes", "no"}:
        return "FAIL", "BOARD_LOCK_DETAIL_FAIL", None
    return "UNVERIFIED", "BOARD_LOCK_DETAIL_UNVERIFIED", "the judge did not answer yes or no"


def judge_lock_checks(
    shot: str,
    name: str,
    image: RGBImage,
    digest: str,
    questions: Sequence[Mapping[str, str]],
    get_judge: Callable[[], LockJudge],
) -> list[dict[str, object]]:
    """Ask every atomic question on its own. One row per question.

    A ``block`` question that fails is ``BOARD_LOCK_DETAIL_FAIL``; one that
    cannot be answered is ``BOARD_LOCK_DETAIL_UNVERIFIED``. Both block spend.
    A ``warn`` question that fails or cannot be answered is ``WARN`` with
    ``BOARD_LOCK_DETAIL_WARN`` and never blocks; ``verdict`` keeps what it was.
    An invalid check is a ``lock_config`` row with ``BOARD_GATE_CONFIG_INVALID``
    and blocks (fail closed).
    """
    rows: list[dict[str, object]] = []
    for item in questions:
        severity = item.get("severity", "block")
        base: dict[str, object] = {
            "character": name, "lock_id": item["lock_id"], "question": item["question"],
            "expect": item["expect"], "severity": severity, "part": item.get("part"),
        }
        if item.get("error"):
            config = _lock_row(shot, "FAIL", "BOARD_GATE_CONFIG_INVALID", detail=item["error"],
                               **base)
            config["check"] = "lock_config"
            rows.append(config)
            continue
        judge_name: str | None = None
        answer: str | None = None
        try:
            judge = get_judge()
            judge_name = judge.name
            answer = judge.ask(image, digest, item["question"])
            status, code, detail = _verdict(answer, item["expect"])
        except BackendUnavailable as exc:
            status, code, detail = "UNVERIFIED", "BOARD_LOCK_DETAIL_UNVERIFIED", str(exc)
        verdict = None
        if severity == "warn" and status != "PASS":
            verdict, status, code = status, "WARN", "BOARD_LOCK_DETAIL_WARN"
        rows.append(_lock_row(shot, status, code, answer=answer, judge=judge_name,
                              verdict=verdict, detail=detail, **base))
    return rows


def lock_verdicts(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """One verdict per shot, character, and lock from its atomic rows.

    Any blocking ``FAIL`` makes the lock ``FAIL``; else any blocking
    ``UNVERIFIED`` makes it ``UNVERIFIED`` (fail closed); else any ``WARN``
    makes it ``WARN``; else ``PASS``.
    """
    order = ("FAIL", "UNVERIFIED", "WARN", "PASS")
    grouped: dict[tuple[str, str, str], list[str]] = {}
    for row in rows:
        if row.get("check") not in {"lock_detail", "lock_config"}:
            continue
        key = (str(row.get("shot")), str(row.get("character")), str(row.get("lock_id")))
        grouped.setdefault(key, []).append(str(row.get("status")))
    verdicts: list[dict[str, object]] = []
    for (shot, character, lock_id), statuses in grouped.items():
        status = next(item for item in order if item in statuses or item == "PASS")
        verdicts.append({"shot": shot, "character": character, "lock_id": lock_id,
                         "status": status, "questions": len(statuses)})
    return verdicts


def warn_only_rows(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """A warning entry for every ``warn`` question that did not pass."""
    found: list[dict[str, object]] = []
    for row in rows:
        if row.get("status") != "WARN":
            continue
        answer = row.get("answer") or row.get("detail") or "no answer"
        found.append({
            "shot": row.get("shot"),
            "code": "BOARD_LOCK_DETAIL_WARN",
            "message": (
                f"{row.get('character')} lock {row.get('lock_id')!r} ({row.get('verdict')}, "
                f"warn only): {row.get('question')} expected {row.get('expect')}, got {answer}"
            ),
            "recommendation": "look at the board; this check does not block spend",
        })
    return found
