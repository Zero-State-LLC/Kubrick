#!/usr/bin/env python3
"""Hold-list QC on frames with a vision judge (#93).

Each hold is one yes-or-no question with an expected answer. The judge (the board gate's
``LockJudge``: a loopback VLM, or recorded answers) is asked every hold on every sampled
frame. A frame is ``pass`` when the answer equals ``expect``, ``fail`` when it is the other
answer, and ``unverified`` on anything else (unknown answer, backend down). A hold is:

- ``pass``: every frame passes;
- ``fail``: every frame fails;
- ``borderline``: frames disagree;
- ``unverified``: any frame is unverified (fail closed).

The report is PROPOSED. ``vlm`` in the report is a ``take_qc`` fixture verdict, so the take
check can consume a judged run without calling a model itself: any ``fail`` hold is a defect
``VLM_HOLD_FAIL``; otherwise any ``unverified`` hold makes the verdict ``not_computable``;
otherwise ``pass`` (borderline holds are listed but, like a marginal score, are not defects).

  python scripts/hold_vision.py --holds holds.yaml --frame mid=2.0=frames/a-mid.png \\
      --frame end=4.0=frames/a-end.png [--answers recorded.json] [--crop full] [--out r.json]

The judge is resolved like the board gate: ``--answers`` / ``KUBRICK_BOARD_JUDGE_ANSWERS``
replays recorded answers, otherwise ``KUBRICK_BOARD_VLM_URL`` (loopback only). A hold may
name a ``judge``; ``--judge NAME=answers:PATH`` or ``--judge NAME=vlm:URL[@MODEL]`` routes
those holds to another judge, so a cheap model can take the easy holds and a stronger one
the hard ones. A paid model
is reached only through a loopback adapter that enforces its own budget; this module never
holds a key and never calls a remote host.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from kubrick.qc.board_pixels import RGBImage, file_sha256, isolate_subject, load_rgb
from kubrick.qc.board_vision import (
    BackendUnavailable,
    LockJudge,
    LoopbackVlmJudge,
    RecordedJudge,
    parse_answer,
    resolve_judge,
)

ANSWERS = ("yes", "no")
DEFECT_CODE = "VLM_HOLD_FAIL"


@dataclass(frozen=True)
class Hold:
    hold_id: str
    question: str
    expect: str
    judge: str | None = None


@dataclass(frozen=True)
class Frame:
    label: str
    t: float | None
    image: RGBImage
    sha256: str


def parse_holds(raw: object) -> list[Hold]:
    """Holds from ``[{hold_id, question, expect}]`` or ``{holds: [...]}``. Raises ValueError."""
    rows = raw.get("holds") if isinstance(raw, Mapping) else raw
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise ValueError("holds must be a list")
    holds: list[Hold] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("each hold must be an object")
        hold_id = str(row.get("hold_id") or "").strip()
        question = str(row.get("question") or "").strip()
        expect = str(row.get("expect") or "").strip().casefold()
        if not hold_id or not question or expect not in ANSWERS:
            raise ValueError(f"hold needs hold_id, question, and expect yes|no: {dict(row)!r}")
        if hold_id in seen:
            raise ValueError(f"duplicate hold_id {hold_id!r}")
        seen.add(hold_id)
        judge = str(row.get("judge") or "").strip() or None
        holds.append(Hold(hold_id, question, expect, judge))
    if not holds:
        raise ValueError("no holds")
    return holds


def frame_verdict(answer: str, expect: str) -> str:
    if answer not in ANSWERS:
        return "unverified"
    return "pass" if answer == expect else "fail"


def hold_verdict(verdicts: Sequence[str]) -> str:
    if not verdicts or "unverified" in verdicts:
        return "unverified"
    if all(v == "pass" for v in verdicts):
        return "pass"
    if all(v == "fail" for v in verdicts):
        return "fail"
    return "borderline"


def _ask(judge: LockJudge, frame: Frame, question: str) -> str:
    try:
        return parse_answer(judge.ask(frame.image, frame.sha256, question))
    except BackendUnavailable:
        return "unavailable"


def judge_holds(
    holds: Sequence[Hold], frames: Sequence[Frame], judge: LockJudge,
    routes: Mapping[str, LockJudge] | None = None,
) -> dict[str, object]:
    """Ask every hold on every frame and return the per-hold report.

    A hold naming a ``judge`` is asked through ``routes[judge]``; a named judge that is not
    routed makes that hold unverified (fail closed). Other holds use ``judge``.
    """
    routes = routes or {}
    rows: list[dict[str, object]] = []
    for hold in holds:
        per_frame: list[dict[str, object]] = []
        hold_judge = routes.get(hold.judge) if hold.judge else judge
        for frame in frames:
            answer = "unrouted" if hold_judge is None else _ask(hold_judge, frame, hold.question)
            per_frame.append({"frame": frame.label, "t": frame.t, "answer": answer,
                              "verdict": frame_verdict(answer, hold.expect)})
        verdict = hold_verdict([str(item["verdict"]) for item in per_frame])
        failing = [item["t"] for item in per_frame
                   if item["verdict"] == "fail" and isinstance(item["t"], (int, float))]
        rows.append({
            "hold_id": hold.hold_id, "question": hold.question, "expect": hold.expect,
            "judge": str(getattr(hold_judge, "name", hold.judge)),
            "verdict": verdict, "frames": per_frame,
            "t_start": min(failing) if failing else None,
            "t_end": max(failing) if failing else None,
        })
    counts = {name: sum(1 for row in rows if row["verdict"] == name)
              for name in ("pass", "fail", "borderline", "unverified")}
    return {
        "authority": "PROPOSED",
        "judge": str(getattr(judge, "name", type(judge).__name__)),
        "frames": [{"frame": f.label, "t": f.t, "sha256": f.sha256} for f in frames],
        "holds": rows,
        "counts": counts,
        "vlm": take_qc_verdict(rows),
    }


def take_qc_verdict(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """The ``vlm`` fixture verdict ``take_qc`` reads."""
    failed = [row for row in rows if row.get("verdict") == "fail"]
    if failed:
        return {"status": "fail", "defects": [
            {"hold_id": row["hold_id"], "defect_code": DEFECT_CODE} for row in failed]}
    if any(row.get("verdict") == "unverified" for row in rows):
        return {"status": "not_computable"}
    return {"status": "pass"}


def markdown(report: Mapping[str, object]) -> str:
    """A per-hold QC table."""
    lines = ["| Hold | Expect | Verdict | Answers |", "|---|---|---|---|"]
    holds = report.get("holds")
    for row in holds if isinstance(holds, list) else []:
        frames = row.get("frames") if isinstance(row, Mapping) else None
        answers = ", ".join(f"{f['frame']}: {f['answer']}" for f in frames or [])
        lines.append(f"| {row['hold_id']} | {row['expect']} | {row['verdict']} | {answers} |")
    return "\n".join(lines)


def parse_judge_route(spec: str) -> tuple[str, LockJudge]:
    """Parse a ``--judge`` value ``NAME=answers:PATH`` or ``NAME=vlm:URL[@MODEL]``."""
    if "=" not in spec:
        raise ValueError("missing '=' in judge spec")

    name_part, rest = spec.split("=", 1)
    name = name_part.strip()
    if not name:
        raise ValueError("empty NAME in judge spec")

    if ":" not in rest:
        raise ValueError("missing ':' after '=' in judge spec")

    kind_part, value = rest.split(":", 1)
    kind = kind_part.strip().lower()

    if kind == "answers":
        if value == "":
            raise ValueError("empty VALUE in judge spec")
        return (name, RecordedJudge.from_file(value))

    if kind == "vlm":
        if value == "":
            raise ValueError("empty VALUE in judge spec")

        url: str
        model: str | None
        if "@" in value:
            parts = value.rsplit("@", 1)
            url = parts[0]
            model = parts[1] or None
        else:
            url = value
            model = None

        if url == "":
            raise ValueError("empty URL in vlm judge spec")

        return (name, LoopbackVlmJudge(url=url, model=model))

    raise ValueError(f"unknown KIND: {kind!r}")


def _load_frame(spec: str, use_crop: bool) -> Frame:
    label, sep, rest = spec.partition("=")
    t_text, sep2, path = rest.partition("=")
    if not sep or not sep2 or not label or not path:
        raise ValueError(f"--frame must be LABEL=T=PATH (T may be empty): {spec!r}")
    t = float(t_text) if t_text.strip() else None
    image = load_rgb(path)
    if use_crop:
        image = isolate_subject(image).image
    return Frame(label, t, image, file_sha256(path))


def _read_holds(path: str) -> list[Hold]:
    text = Path(path).read_text(encoding="utf-8")
    if path.endswith((".yaml", ".yml")):
        import yaml

        return parse_holds(yaml.safe_load(text))
    return parse_holds(json.loads(text))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--holds", required=True, help="YAML or JSON hold list")
    parser.add_argument("--frame", action="append", default=[], metavar="LABEL=T=PATH")
    parser.add_argument("--answers", help="recorded judge answers (offline)")
    parser.add_argument("--judge", action="append", default=[], metavar="NAME=KIND:VALUE",
                        help="route holds with judge: NAME to answers:PATH or vlm:URL[@MODEL]")
    parser.add_argument("--crop", choices=("subject", "full"), default="subject",
                        help="subject: the board gate's default crop (default); full: whole frame")
    parser.add_argument("--out", help="write the JSON report here")
    parser.add_argument("--markdown", action="store_true", help="print the table, not JSON")
    args = parser.parse_args(argv)
    try:
        holds = _read_holds(args.holds)
        if not args.frame:
            raise ValueError("at least one --frame is required")
        frames = [_load_frame(spec, args.crop == "subject") for spec in args.frame]
        judge = resolve_judge(args.answers)
        routes = dict(parse_judge_route(spec) for spec in args.judge)
    except (OSError, ValueError, BackendUnavailable) as exc:
        print(f"hold vision: ERROR: {exc}", file=sys.stderr)
        return 2
    report = judge_holds(holds, frames, judge, routes)
    text = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(markdown(report) if args.markdown else text)
    counts = report["counts"]
    assert isinstance(counts, dict)
    return 1 if counts["fail"] or counts["unverified"] else 0


if __name__ == "__main__":
    sys.exit(main())
