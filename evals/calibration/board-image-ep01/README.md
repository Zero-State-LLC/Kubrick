# EP-01 board image gate calibration set

The labeled MYSLEF EP-01 set used to calibrate the board image gate on
2026-10-04 ([`docs/BOARD-IMAGE-CALIBRATION.md`](../../../docs/BOARD-IMAGE-CALIBRATION.md)).
MYSLEF is Danny's own project. The full-size images (about 55 MB) are not in
the repo; the manifest lists each one with its sha256.

| File | What it is |
|---|---|
| `manifest.json` | 83 images: id, path under a root, kind, identity label, note, sha256, gate truth, pins. Format in `tools/board_calibration/manifest.py` |
| `locks-v0.26.yaml` | The plan-alley locks as of 0.26.0 |
| `locks-v0.26-authored.yaml` | The hand-written lock checks tried with 0.26.0 |
| `locks-v0.27.yaml` | The locks after the 0.27.0 wording fixes |
| `results/*.summary.json` | `gate_metrics.py --json` for each run below |
| `thumbnails/` | Six 256-pixel previews of what the labels mean |

## Where the full set lives

On the operator box: `/workspace/myslef/ep01-boards` (boards),
`/workspace/myslef/ep01-restart/boards` (restart boards),
`/workspace/kubrick-calib/frames` (take frames, mid and end of each take), and
`/workspace/myslef` (rejected character sheets). Elsewhere, copy the set and
point the roots at it with `--root boards=DIR` (repeat per root) or
`KUBRICK_CALIB_ROOT_BOARDS=DIR`. `--verify` checks every file and sha256
first.

## Rerun

Start a judge first ([`docs/BOARD-VISION-SETUP.md`](../../../docs/BOARD-VISION-SETUP.md)),
then from the repo root:

```bash
source ~/.config/kubrick/board-vision.env
python tools/board_calibration/gate_run.py --verify \
  --locks evals/calibration/board-image-ep01/locks-v0.27.yaml --out /tmp/gate-v0.27.json
python tools/board_calibration/gate_metrics.py /tmp/gate-v0.27.json
python tools/board_calibration/judge_eval.py --out /tmp/judge.json
python tools/board_calibration/identity.py --out /tmp/identity.json --detect
```

`gate_run.py --dry-run` prints the questions without a judge. Results are
written after every image; rerunning with the same `--out` resumes.

## Numbers on 2026-10-04 (Spark judge, 60 clean and 7 defective head images)

| Locks | Clean blocked | Defective blocked |
|---|---|---|
| `locks-v0.26.yaml` (shipped 0.26.0) | 19 of 60 | 5 of 7 |
| `locks-v0.26-authored.yaml` | 12 of 60 | 6 of 7 |
| `locks-v0.27.yaml` | 11 of 60 | 7 of 7 |

Reruns move single answers, so treat a few boards of difference as noise.
