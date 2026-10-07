#!/usr/bin/env python3
"""Acceptance for #93: hold-list QC on EP-01 restart take frames against the labeled verdicts.

  python tools/board_calibration/hold_vision_eval.py --record /tmp/answers.json --out /tmp/r.json
  python tools/board_calibration/hold_vision_eval.py \
      --answers evals/fixtures/ep01/hold-vision/recorded-answers.json

For each take of the chosen shots (default 01 07 09 10 11 12), the manifest's take frames (mid
and end) are judged with ``kubrick.qc.hold_vision`` on the gate's default crop. The labeled
verdict for a hold on a take uses the same rule as the module (all frames pass, all fail, or
borderline when the labels differ). A take scores one mismatch per hold whose verdict differs
from the label, and an unverified hold counts as a mismatch. Acceptance: at most one mismatch
per shot (summed over its takes).

``--answers`` replays recorded answers keyed by image sha256 and needs no image files, so CI
can run it offline at zero credits. ``--record`` writes the live answers in that format.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import manifest as mf  # noqa: E402

mf.use_repo_paths()

from kubrick.qc.board_pixels import RGBImage, isolate_subject, load_rgb  # noqa: E402
from kubrick.qc.board_vision import LoopbackVlmJudge, RecordedJudge, parse_answer  # noqa: E402
from kubrick.qc.hold_vision import (  # noqa: E402
    Frame,
    frame_verdict,
    hold_verdict,
    judge_holds,
    parse_holds,
)

ROOT = Path(__file__).resolve().parents[2]
HOLDS = ROOT / "evals/fixtures/ep01/hold-vision/holds.yaml"
TAKE = re.compile(r"^frames:v(?P<shot>[0-9]+[A-Z]?)-(?P<take>t[0-9]+)-(?P<pos>mid|end)\.png$")
POS_T = {"mid": 2.0, "end": 4.0}


class Recorder:
    """Wrap a judge and keep its answers by image sha256."""

    def __init__(self, inner: Any) -> None:
        self.inner, self.name, self.table = inner, getattr(inner, "name", "judge"), {}

    def ask(self, image: RGBImage, image_sha256: str, question: str) -> str:
        answer = self.inner.ask(image, image_sha256, question)
        self.table.setdefault(image_sha256, {})[question] = parse_answer(answer)
        return answer


def takes(man: dict[str, Any], shots: set[str]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in man["items"]:
        match = TAKE.match(item["id"])
        if match and match["shot"].lstrip("0") in shots and item.get("truth"):
            out[f"{match['shot']}-{match['take']}"].append({**item, "pos": match["pos"]})
    return {k: sorted(v, key=lambda i: POS_T[i["pos"]]) for k, v in sorted(out.items())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mf.add_common_args(parser)
    parser.add_argument("--shots", nargs="*", default=["01", "07", "09", "10", "11", "12"])
    parser.add_argument("--answers", help="recorded answers (offline replay)")
    parser.add_argument("--record", help="write live answers here")
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    import yaml

    holds = parse_holds(yaml.safe_load(HOLDS.read_text(encoding="utf-8")))
    man = mf.load(args.manifest)
    shots = {s.lstrip("0") for s in args.shots}
    judge: Any
    if args.answers:
        judge = RecordedJudge.from_file(args.answers)
    else:
        judge = Recorder(LoopbackVlmJudge())
        root_map = mf.roots(man, args.root)
    blank = RGBImage(1, 1, b"\0\0\0")
    rows, per_shot = [], defaultdict(int)
    for take, items in takes(man, shots).items():
        frames = []
        for item in items:
            image = blank if args.answers else isolate_subject(
                load_rgb(mf.resolve(item["path"], root_map))).image
            frames.append(Frame(item["pos"], POS_T[item["pos"]], image, item["sha256"]))
        labeled = [h for h in holds if all(h.hold_id in i["truth"] for i in items)]
        report = judge_holds(labeled, frames, judge)
        mismatches = []
        for row in report["holds"]:  # type: ignore[union-attr]
            truth = hold_verdict([frame_verdict(i["truth"][row["hold_id"]], row["expect"])
                                  for i in items])
            if row["verdict"] != truth:
                mismatches.append({"hold_id": row["hold_id"], "judged": row["verdict"],
                                   "labeled": truth})
        shot = take.split("-")[0]
        per_shot[shot] += len(mismatches)
        rows.append({"take": take, "holds": len(labeled), "mismatches": mismatches,
                     "notes": sorted({str(i.get("note")) for i in items})})
        print(f"{take:8} holds {len(labeled)} mismatches {len(mismatches)} "
              + ", ".join(f"{m['hold_id']}({m['judged']}!={m['labeled']})" for m in mismatches))
    ok = all(n <= 1 for n in per_shot.values())
    summary = {"judge": getattr(judge, "name", "judge"), "per_shot_mismatches": dict(per_shot),
               "accept_within_one_per_shot": ok, "takes": rows}
    print(json.dumps({"per_shot_mismatches": dict(per_shot), "accept": ok}))
    if args.out:
        Path(args.out).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    if args.record and isinstance(judge, Recorder):
        Path(args.record).write_text(json.dumps({"answers": judge.table}, indent=1, sort_keys=True)
                                     + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
