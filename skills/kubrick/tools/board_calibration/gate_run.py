#!/usr/bin/env python3
"""Run the board image gate's lock checks over a labeled set and score them.

  python tools/board_calibration/gate_run.py \
      --locks evals/calibration/board-image-ep01/locks-v0.27.yaml --out /tmp/gate-v0.27.json

Uses the gate's own ``lock_questions`` and ``judge_lock_checks`` on the gate's
default crop, so a run measures what the gate would block. Questions come from
``--locks`` (a YAML file with ``locks:``) or ``--plan`` (a full plan: its
``locks`` and ``characters.<id>``), plus the manifest's ``board_checks``. The
judge is ``LoopbackVlmJudge`` at ``--url`` (default ``KUBRICK_BOARD_VLM_URL``),
so it must be a loopback URL. Results are written after every image and a
rerun resumes from the file; delete it to start over.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import manifest as mf  # noqa: E402

mf.use_repo_paths()

from tools.board_calibration.gate_metrics import report, summarize  # noqa: E402

FIELDS = ("lock_id", "part", "question", "expect", "severity", "answer", "status", "verdict",
          "detail")


def build_questions(man: dict[str, Any], doc: dict[str, Any], character: str) -> list[dict]:
    from kubrick.gates.board_image_plan import characters_of, lock_questions

    spec = dict(characters_of(doc).get(character) or {}) if doc.get("characters") else {}
    spec["board_checks"] = list(spec.get("board_checks") or []) + list(
        man.get("board_checks") or [])
    return lock_questions(doc, character, spec)


def main(argv: list[str] | None = None) -> int:
    import yaml

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mf.add_common_args(parser)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--locks", help="YAML file with a locks: list")
    source.add_argument("--plan", help="a full Kubrick plan YAML")
    parser.add_argument("--character", help="default: the manifest character")
    parser.add_argument("--url", default=os.environ.get("KUBRICK_BOARD_VLM_URL", ""))
    parser.add_argument("--model", default=os.environ.get("KUBRICK_BOARD_VLM_MODEL", ""))
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0, help="first N images only (smoke)")
    parser.add_argument("--out", required=True)
    parser.add_argument("--dry-run", action="store_true", help="print the questions and stop")
    args = parser.parse_args(argv)

    from kubrick.gates.board_lock_checks import judge_lock_checks, lock_verdicts
    from kubrick.qc.board_pixels import isolate_subject, load_rgb
    from kubrick.qc.board_vision import LoopbackVlmJudge

    man = mf.load(args.manifest)
    root_map = mf.roots(man, args.root)
    character = args.character or man.get("character") or ""
    with open(args.locks or args.plan, encoding="utf-8") as handle:
        doc = yaml.safe_load(handle) or {}
    questions = build_questions(man, doc, character)
    for q in questions:
        print(q["lock_id"], q["expect"], q["severity"], q["question"].split("image. ")[-1])
    if args.dry_run:
        return 0
    items = mf.gate_items(man)[: args.limit or None]
    if args.verify and (problems := mf.verify(items, root_map)):
        print("\n".join(problems), file=sys.stderr)
        return 1
    judge = LoopbackVlmJudge(url=args.url, model=args.model or None, timeout=args.timeout)
    results = mf.ResultFile(args.out, {"source": args.locks or args.plan, "judge": judge.name,
                                       "questions": questions})

    def job(item: dict[str, Any]) -> None:
        if results.done(item["path"]):
            return
        started = time.time()
        crop = isolate_subject(load_rgb(mf.resolve(item["path"], root_map)))
        checks = judge_lock_checks(item["id"], character, crop.image, "", questions,
                                   lambda: judge)
        results.add({
            "path": item["path"], "id": item["id"], "crop": crop.method,
            "truth": {k: v for k, v in item.get("truth", {}).items()
                      if k.startswith("gate:") or k == "lens_sides"},
            "pins": item.get("pins", {}),
            "checks": [{k: c.get(k) for k in FIELDS} for c in checks],
            "locks": lock_verdicts(checks), "secs": round(time.time() - started, 1),
        })
        print(len(results.rows), item["id"], "".join(str(c["status"])[0] for c in checks),
              flush=True)

    print(len(items), "images", len(questions), "questions", flush=True)
    with ThreadPoolExecutor(max(1, args.workers)) as pool:
        list(pool.map(job, items))
    data = results.save([item["path"] for item in items])
    print(report(summarize(data)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
