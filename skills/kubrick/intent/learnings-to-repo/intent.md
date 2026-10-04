# Intent: make today's board gate work repeatable from the repo (0.27.0)

## Problem

The 2026-10-04 board gate work left key pieces only on the operator box: the
judge launchers, the loopback proxy to the Spark vision model with its
User-Agent and thinking-off workarounds, the gate env file, the EP-01
calibration scripts, and the lock wording fixes in the MYSLEF plans. An
editable install also broke the scripts/ entry points ("'kubrick' is not a
package"). Nobody else could rerun the setup or reproduce the numbers.

## Proposed outcome

- `tools/board_vision/`: a provider-agnostic loopback adapter for any
  OpenAI-compatible vision endpoint (every provider detail in a profile;
  Spark is one example profile), launchers, a template env with no secrets,
  a one-command setup, a health check, and a fail-closed test.
- `tools/board_calibration/` plus `evals/calibration/board-image-ep01/`: the
  identity, judge accuracy, and gate run harness with CLI args, a labeled
  manifest with sha256 per image, lock files, and six thumbnails.
- The lock wording fixes (mouth grille in `red-chest-led`, the longer lens
  glow question as a lens `checks` entry) in the box plans and the repo lock
  files, rerun on EP-01 through Spark.
- Every `scripts/` entry point puts `src` first, and `scripts/kubrick.py`
  imported as `kubrick` hands the name to the package.
- A "Learnings to repo" rule in `AGENTS.md`.

## Affected users / systems

Operators running the board image gate, agents rerunning calibration, the
hub mirror (all new files are payload), CI (new tests, no network).

## Constraints / non-goals

- The gate stays loopback-only and fail closed. No gate behavior change other
  than reading a YAML bare `expect: no` as `no`.
- No secrets in the tree: keys come from an env var or file a profile names.
- No full-size EP-01 images in the repo; the manifest says where they live.
- New modules under the 500-line cap. No spend, no paid API in tests.

## Verified / assumed claims

| Claim | Label | Basis |
|---|---|---|
| `PYTHONPATH=src pytest scripts` failed with "'kubrick' is not a package" | `OBSERVED` | reproduced on main d0a5666 |
| The new harness reproduces the 0.26.0 numbers from the saved results | `OBSERVED` | `gate_metrics.py` on `gate_atomic_spark.json`: 19/60, 5/7 |

## Author / date

- Author: Grok Bot for Daniel Meyer (operator approval 2026-10-04 15:10 PT,
  provider-agnostic adapter 15:14 PT)
- Date: 2026-10-04
