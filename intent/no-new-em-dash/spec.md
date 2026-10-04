# Spec: em dash ratchet

Intent: [`intent.md`](intent.md). Status: accepted with the intent.

## Where it runs

`ci.yml`, build job, on `pull_request` only, before Python setup:
`python3 scripts/check_no_new_em_dash.py --base origin/${{ github.base_ref }}`.
Checkout uses `fetch-depth: 0` so the merge base exists.

## Modules

| Module | Role |
|---|---|
| `src/kubrick/runtime/check_no_new_em_dash.py` | Diff parse, hit filter, CLI |
| `scripts/check_no_new_em_dash.py` | Entry point |
| `scripts/test_check_no_new_em_dash.py` | Tests (synthetic diff and a temp git repo) |

## Behavior

- Runs `git diff --unified=0 -M BASE...HEAD` limited to `*.md`, `*.py`,
  `*.yaml`, `*.yml`, `*.json`, `*.txt`, `*.toml`, `*.sh`. Renames are
  detected, so a moved file does not count as all-new lines.
- A hit is an added line that contains U+2014, is not under
  `skills/kubrick/`, and does not carry `em-dash: allow`.
- Output per hit: `path:line: em dash; rewrite with a period, comma, colon,
  or parentheses`, then the line.
- Exit 0 pass, 1 hits, 2 git error (fail closed).
