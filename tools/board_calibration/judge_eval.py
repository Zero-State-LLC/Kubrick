#!/usr/bin/env python3
"""Judge accuracy: ask each manifest question on every image that has a truth label for it.

  python tools/board_calibration/judge_eval.py --out /tmp/judge.json
  python tools/board_calibration/judge_eval.py --report /tmp/judge.json

Asks the manifest ``questions`` (``{key: {question, expect}}``) through
``LoopbackVlmJudge`` on the gate's default crop. ``truth[key]`` is the true
answer to the question. Results are saved after every image and a rerun resumes.
The report lists accuracy per question, split by true answer.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import manifest as mf  # noqa: E402

mf.use_repo_paths()


def report(data: dict[str, Any]) -> str:
    stats: dict[str, collections.Counter[str]] = {}
    for row in data.get("rows", []):
        for key, truth in row["truth"].items():
            answer = row["answers"].get(key)
            s = stats.setdefault(key, collections.Counter())
            s["n"] += 1
            s["unknown"] += answer not in ("yes", "no")
            s["ok"] += answer == truth
            s["truth_" + truth] += 1
            s["ok_" + truth] += answer == truth
    lines = [f"{'question':18} {'n':>3} {'acc':>5} {'unk':>4}  truth=yes  truth=no"]
    total: collections.Counter[str] = collections.Counter()
    for key, s in stats.items():
        yes = f"{s['ok_yes']}/{s['truth_yes']}" if s["truth_yes"] else "-"
        no = f"{s['ok_no']}/{s['truth_no']}" if s["truth_no"] else "-"
        lines.append(f"{key:18} {s['n']:3} {s['ok'] / s['n']:.2f} {s['unknown']:4}  "
                     f"{yes:>9}  {no:>8}")
        total.update(s)
    if total["n"]:
        lines.append(f"all {total['n']} acc {total['ok'] / total['n']:.2f} "
                     f"unknown {total['unknown']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mf.add_common_args(parser)
    parser.add_argument("--out")
    parser.add_argument("--report", metavar="RESULTS", help="only print the report of a file")
    parser.add_argument("--only", action="append", default=[], help="question key (repeat)")
    parser.add_argument("--url", default=os.environ.get("KUBRICK_BOARD_VLM_URL", ""))
    parser.add_argument("--model", default=os.environ.get("KUBRICK_BOARD_VLM_MODEL", ""))
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    if args.report:
        with open(args.report, encoding="utf-8") as handle:
            print(report(json.load(handle)))
        return 0
    if not args.out:
        parser.error("--out is required unless --report is given")

    from kubrick.qc.board_pixels import isolate_subject, load_rgb
    from kubrick.qc.board_vision import BackendUnavailable, LoopbackVlmJudge

    man = mf.load(args.manifest)
    root_map = mf.roots(man, args.root)
    questions = {k: v for k, v in (man.get("questions") or {}).items()
                 if not args.only or k in args.only}
    items = [i for i in man["items"] if any(k in questions for k in i.get("truth", {}))]
    if args.verify and (problems := mf.verify(items, root_map)):
        print("\n".join(problems), file=sys.stderr)
        return 1
    judge = LoopbackVlmJudge(url=args.url, model=args.model or None, timeout=args.timeout)
    config = {"questions": questions, "judge": judge.name, "url": judge.url,
              "manifest": mf.file_digest(args.manifest)}
    results = mf.ResultFile(args.out, {"config": config, "judge": judge.name,
                                       "questions": questions})

    def job(item: dict[str, Any]) -> None:
        if results.done(item["path"]):
            return
        crop = isolate_subject(load_rgb(mf.resolve(item["path"], root_map)))
        truth = {k: v for k, v in item["truth"].items() if k in questions}
        answers: dict[str, Any] = {}
        for key in truth:
            started = time.time()
            try:
                answers[key] = judge.ask(crop.image, "", questions[key]["question"])
            except BackendUnavailable as exc:
                answers[key] = f"error: {exc}"
            answers[key + "_s"] = round(time.time() - started, 1)
        results.add({"path": item["path"], "id": item["id"], "crop": crop.method,
                     "truth": truth, "answers": answers})
        print(len(results.rows), item["id"], flush=True)

    print(len(items), "images", len(questions), "questions", flush=True)
    with ThreadPoolExecutor(max(1, args.workers)) as pool:
        list(pool.map(job, items))
    print(report(results.save([item["path"] for item in items])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
