# Intent: fail a pull request that adds an em dash

## Problem

The operator keeps correcting em dashes (U+2014) in Kubrick docs and code. A
cloud agent left one in the v0.24.0 README tagline. About 150 Markdown files
on main already contain em dashes, so a whole-tree check would fail every
build and nobody would fix it.

## Proposed outcome

CI fails a pull request whose diff adds a line with an em dash. Lines that are
already on the base branch are not checked (a ratchet). The error names the
file, the line, and the fix.

Out of scope: rewriting the existing em dashes, and checking pushes to `main`
(the pull request gate is where the change is reviewed).

## Affected users / systems

CI (`ci.yml` build job), contributors and agents opening pull requests, the
hub mirror (the new script is skill payload and is mirrored).

## Constraints / non-goals

- No `SKILL.md` change. No change to cinematic or CLI behavior.
- New modules stay under the 500-line cap.
- Root is the source of truth; `bash scripts/sync_hub_skill.sh` refreshes the
  mirror, and the check skips `skills/kubrick/` because `check_hub_sync`
  already proves it matches root.
- Fail closed: if git cannot produce the diff (missing base ref), the check
  errors instead of passing.

## Open questions

None blocking. A fixture that must contain an em dash can mark the line with
`em-dash: allow`.

## Verified / assumed claims

| Claim | Label | Basis |
|---|---|---|
| About 150 Markdown files on main contain an em dash | `OBSERVED` | `git grep -l` on main 5905834 |
| The check would have caught the v0.24.0 README tagline | `OBSERVED` | `--base 6669cc0~1` reports `README.md:2` |
| `actions/checkout` needs `fetch-depth: 0` for `base...HEAD` | `INFERRED` | the default shallow clone has no merge base |

## Author / date

- Author: Grok Bot for Daniel Meyer (operator approval 2026-10-04 02:56 PT)
- Date: 2026-10-04
