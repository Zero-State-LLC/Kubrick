#!/usr/bin/env python3
"""Score a gate run: clean blocked, defective caught, per lock and per question.

  python tools/board_calibration/gate_metrics.py RESULTS.json [--json]

An image is defective when any ``gate:<lock>`` truth is ``no``. It is blocked
when any check is ``FAIL`` or ``UNVERIFIED`` (a ``warn`` check never blocks).
A question's true answer is known when a manifest ``pins`` keyword appears in
it, when its lock id (``-`` as ``_``) is a truth key, or when the image keeps
that lock (then the true answer is the question's ``expect``).
"""
from __future__ import annotations

import argparse
import collections
import json
from collections.abc import Mapping
from typing import Any

BLOCKING = ("FAIL", "UNVERIFIED")


def _tail(question: str) -> str:
    return question.split("image. ", 1)[-1]


def question_truth(row: Mapping[str, Any], check: Mapping[str, Any]) -> str | None:
    text = str(check.get("question", "")).casefold()
    for keyword, answer in (row.get("pins") or {}).items():
        if keyword.casefold() in text:
            return str(answer)
    truth = row.get("truth") or {}
    lock = str(check.get("lock_id", ""))
    if lock.replace("-", "_") in truth:
        return str(truth[lock.replace("-", "_")])
    if truth.get("gate:" + lock) == "yes":
        return str(check.get("expect"))
    return None


def summarize(data: Mapping[str, Any]) -> dict[str, Any]:
    outcome: collections.Counter[tuple[bool, bool]] = collections.Counter()
    missed: list[str] = []
    false_blocks: collections.Counter[str] = collections.Counter()
    per_q: dict[str, collections.Counter[str]] = {}
    per_lock: dict[str, collections.Counter[str]] = {}
    warns = 0
    unanswered = 0
    calls = 0
    for row in data.get("rows", []):
        truth = row.get("truth") or {}
        bad = any(v == "no" for k, v in truth.items() if k.startswith("gate:"))
        blocking = [c for c in row["checks"] if c.get("status") in BLOCKING]
        outcome[(bad, bool(blocking))] += 1
        if bad and not blocking:
            missed.append(row.get("id") or row["path"])
        if not bad:
            for check in blocking:
                false_blocks[_tail(check["question"])] += 1
        for check in row["checks"]:
            calls += 1
            unanswered += check.get("answer") not in ("yes", "no")
            warns += check.get("status") == "WARN"
            answer = question_truth(row, check)
            if answer is not None:
                stats = per_q.setdefault(_tail(check["question"]), collections.Counter())
                stats["n"] += 1
                stats["ok"] += check.get("answer") == answer
        for verdict in row.get("locks", []):
            lock_truth = truth.get("gate:" + verdict["lock_id"])
            if lock_truth is None:
                continue
            stats = per_lock.setdefault(verdict["lock_id"], collections.Counter())
            caught = verdict["status"] in BLOCKING
            stats["n"] += 1
            stats["ok"] += (verdict["status"] == "PASS") == (lock_truth == "yes")
            stats["defect"] += lock_truth == "no"
            stats["caught"] += lock_truth == "no" and caught
            stats["clean"] += lock_truth == "yes"
            stats["clean_pass"] += lock_truth == "yes" and verdict["status"] == "PASS"
    return {
        "images": sum(outcome.values()),
        "clean_blocked": outcome[(False, True)],
        "clean": outcome[(False, True)] + outcome[(False, False)],
        "defective_blocked": outcome[(True, True)],
        "defective": outcome[(True, True)] + outcome[(True, False)],
        "missed": missed,
        "calls": calls, "unanswered": unanswered, "warn_rows": warns,
        "per_lock": {k: dict(v) for k, v in per_lock.items()},
        "per_question": {k: dict(v) for k, v in per_q.items()},
        "clean_blocked_by_question": dict(false_blocks.most_common()),
    }


def report(summary: Mapping[str, Any]) -> str:
    lines = [
        f"images {summary['images']}",
        f"clean blocked: {summary['clean_blocked']} of {summary['clean']}",
        f"defective blocked: {summary['defective_blocked']} of {summary['defective']}"
        f" missed {summary['missed']}",
        f"answers not yes/no or errors: {summary['unanswered']} of {summary['calls']}",
        f"warn rows: {summary['warn_rows']}", "", "per lock:",
    ]
    for lock, s in summary["per_lock"].items():
        lines.append(f"  {lock:15} acc {s['ok']}/{s['n']}  defect caught "
                     f"{s.get('caught', 0)}/{s.get('defect', 0)}  clean passed "
                     f"{s.get('clean_pass', 0)}/{s.get('clean', 0)}")
    lines += ["", "per question (where the labels pin the truth):"]
    for question, s in summary["per_question"].items():
        lines.append(f"  {s['ok']}/{s['n']}  {question}")
    lines += ["", "clean images blocked, by question:"]
    for question, count in summary["clean_blocked_by_question"].items():
        lines.append(f"  {count:3}  {question}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    with open(args.results, encoding="utf-8") as handle:
        summary = summarize(json.load(handle))
    print(json.dumps(summary, indent=1) if args.json else report(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
