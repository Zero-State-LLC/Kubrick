#!/usr/bin/env python3
"""Identity score calibration: DINOv2 similarity of each image to the manifest refs.

  python tools/board_calibration/identity.py --out /tmp/identity.json [--detect]
  python tools/board_calibration/identity.py --report /tmp/identity.json

Scores every item (and nothing else) against the manifest ``refs`` with the
gate's ``Dinov2Embedder`` (``KUBRICK_BOARD_EMBED_MODEL``) on the gate's default
crop and on the full image. ``--detect`` also scores OWLv2 ``a person`` and
``a head`` crops (downloads google/owlv2-base-patch16-ensemble once). The
report prints, per crop, the keep and drift spread, AUC(keep > drift), and
how many drift and keep images each threshold would block. Needs the
board-vision extra.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import manifest as mf  # noqa: E402

mf.use_repo_paths()

OWL = "google/owlv2-base-patch16-ensemble"
QUERIES = ("a person", "a head")
THRESHOLDS = (0.5, 0.6, 0.7, 0.75, 0.8, 0.85)


def _detector() -> Any:
    import torch
    from PIL import Image
    from transformers import Owlv2ForObjectDetection, Owlv2Processor

    proc = Owlv2Processor.from_pretrained(OWL)
    det = Owlv2ForObjectDetection.from_pretrained(OWL).eval()

    def detect(path: str) -> dict[str, tuple[float, tuple[int, int, int, int]]]:
        image = Image.open(path).convert("RGB")
        inputs = proc(text=[list(QUERIES)], images=image, return_tensors="pt")
        with torch.no_grad():
            out = det(**inputs)
        side = max(image.size)  # OWLv2 pads to a square
        res = proc.post_process_grounded_object_detection(
            out, threshold=0.05, target_sizes=torch.tensor([[side, side]]))[0]
        best: dict[str, tuple[float, tuple[int, int, int, int]]] = {}
        for score, label, box in zip(res["scores"].tolist(), res["labels"].tolist(),
                                     res["boxes"].tolist()):
            x0, y0, x1, y1 = box
            clip = (max(0, int(x0)), max(0, int(y0)), min(image.width, int(x1)),
                    min(image.height, int(y1)))
            if clip[2] - clip[0] > 8 and clip[3] - clip[1] > 8 and (
                    QUERIES[label] not in best or score > best[QUERIES[label]][0]):
                best[QUERIES[label]] = (score, clip)
        return best

    return detect


def _auc(pos: list[float], neg: list[float]) -> float:
    pairs = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return pairs / (len(pos) * len(neg))


def report(rows: list[dict[str, Any]]) -> str:
    lines = []
    for mode in ("auto", "full", "person", "head"):
        by = {label: sorted(r[mode] for r in rows if r["identity"] == label
                            and r["kind"] in ("board", "frame") and r.get(mode) is not None)
              for label in ("keep", "drift", "alt", "na")}
        by["offmodel"] = sorted(r[mode] for r in rows if r["identity"] == "offmodel"
                                and r.get(mode) is not None)
        if not by["keep"] or not by["drift"]:
            continue
        lines.append(f"\n== crop={mode}")
        for label, values in by.items():
            if values:
                lines.append(f" {label:8} n={len(values)} min={values[0]:.3f} "
                             f"med={statistics.median(values):.3f} max={values[-1]:.3f}")
        lines.append(f" AUC(keep>drift)={_auc(by['keep'], by['drift']):.3f}")
        lines.append("  thr   drift blocked   keep blocked   offmodel blocked")
        for thr in THRESHOLDS:
            lines.append(f"  {thr:.2f}  {sum(v < thr for v in by['drift']):3}/{len(by['drift'])}"
                         f"         {sum(v < thr for v in by['keep']):3}/{len(by['keep'])}"
                         f"        {sum(v < thr for v in by['offmodel']):3}/"
                         f"{len(by['offmodel'])}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mf.add_common_args(parser)
    parser.add_argument("--out")
    parser.add_argument("--report", metavar="RESULTS")
    parser.add_argument("--detect", action="store_true", help="also score OWLv2 crops")
    args = parser.parse_args(argv)
    if args.report:
        with open(args.report, encoding="utf-8") as handle:
            print(report(json.load(handle)))
        return 0
    if not args.out:
        parser.error("--out is required unless --report is given")

    from kubrick.qc.board_pixels import crop, isolate_subject, load_rgb
    from kubrick.qc.board_vision import Dinov2Embedder, cosine

    man = mf.load(args.manifest)
    root_map = mf.roots(man, args.root)
    refs = [p for group in (man.get("refs") or {}).values() for p in group]
    if args.verify and (problems := mf.verify(man["items"], root_map)):
        print("\n".join(problems), file=sys.stderr)
        return 1
    embedder = Dinov2Embedder()
    ref_vecs = [embedder.embed(isolate_subject(load_rgb(mf.resolve(p, root_map))).image)
                for p in refs]

    def score(image: Any) -> float:
        vec = embedder.embed(image)
        return round(max(cosine(vec, ref) for ref in ref_vecs), 4)

    detect = _detector() if args.detect else None
    rows = []
    for item in man["items"]:
        path = mf.resolve(item["path"], root_map)
        image = load_rgb(path)
        auto = isolate_subject(image)
        row = {k: item.get(k) for k in ("id", "path", "kind", "identity", "note")}
        row.update(auto_method=auto.method, auto=score(auto.image), full=score(image))
        for query, (det_score, box) in (detect(path) if detect else {}).items():
            key = query.split()[-1]
            row.update({key: score(crop(image, box)), key + "_box": list(box),
                        key + "_det": round(det_score, 3)})
        rows.append(row)
        print(item["identity"], row["auto"], row.get("head"), item["id"], flush=True)
    Path(args.out).write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
    print(report(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
