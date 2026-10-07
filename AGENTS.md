# Agent contract: Kubrick

You are working in **Kubrick** (`Zero-State-LLC/Kubrick`), a standalone
Hermes skill. This file is the canonical contract for Cursor, Claude,
Codex, Grok, and OpenClaw. Harness adapters (`CLAUDE.md`) only point here.

`SKILL.md` is the Hermes runtime contract. Do not rewrite it unless an
accepted intent is explicitly the skill-contract change. Do not add a
deploy or pin workflow. `scripts/check_workflows.py` rejects one.

## Intent

Read the active `intent.md` under [`intent/`](intent/README.md) before
editing. Next stage is `spec.md` / plan. Do not skip to code.

If the change is non-trivial and no intent exists, draft one from
[`intent/_TEMPLATE.md`](intent/_TEMPLATE.md) and wait for a human to
accept it. Trivial docs and chore fixes do not need an intent file.

## Commands

| Task | Command |
|---|---|
| Smoke | `python scripts/kubrick.py do check --action smoke` |
| Skill contract | `python scripts/validate_hermes_skill.py` |
| Hub sync | `python scripts/check_hub_sync.py` |
| Docs links | `python scripts/check_doc_links.py` |
| No new em dashes | `python scripts/check_no_new_em_dash.py --base origin/main` |

After skill-payload edits: `bash scripts/sync_hub_skill.sh` then the hub
check. Root is the source of truth; `skills/kubrick/` is the packaging
mirror. Do not invent commands.

Production modules live in `src/kubrick/`. Each `scripts/<name>.py` file is
the entry point that loads that module. The command stays
`python scripts/kubrick.py`.

## Invariants

- Fail closed: weak or contradictory evidence → `NOT_COMPUTABLE`.
- Local outputs stay **PROPOSED** until explicitly promoted.
- Pattern evolution is proposal-only. Never auto-apply corpus mutations.
- Do not write into `references/` during ordinary work.
- Do not put secrets, tokens, or live credentials in the tree.
- Do not invent cinematic or CLI behavior `SKILL.md` does not name.
- Do not add a deploy or pin workflow. The workflow check fails the build.

## Learnings to repo

Develop Kubrick as you learn. A lesson from a run (a workaround, a wording
fix, a calibration number, a setup step, a bug found on the way) becomes
code, a test, a doc, or harness in this repo in the same change or the next
one. Do not leave it only in a tracker note, a box script, or a scratch
folder. Templates go in, secrets and large media do not: commit a template
env, a manifest, or thumbnails and say where the rest lives. Example: the
board judge setup and calibration harness under `tools/` (0.27.0).

## Escalation

If CI, tests, or validators look wrong (missing coverage, silent skips,
green-but-inert checks, or a suite that contradicts the skill contract):

1. Open a bounded defect issue labeled `bug`.
2. Do **not** patch tests, fixtures, or CI to force green.
3. Do **not** weaken an assertion, rewrite `SKILL.md`, or skip hub sync
   to match a broken path.

A red honest check is better than a green lie.

Owner-gated (human yes): official Hermes hub submit, Continuity Forge
promotion, license/legal, and spend. Agents do not buy things or publish
the skill as official.

## Team context

Org and partner status is not this repo. When a task needs it, load
[Zero-State-LLC/agent-context](https://github.com/Zero-State-LLC/agent-context):

1. `HANDOFF.md`
2. `STATUS.md`
3. `DECISIONS.md` only if a prior choice affects this task

Clone: `gh repo clone Zero-State-LLC/agent-context ~/agent-context`.
Pull `--ff-only` before trusting a local copy.

## Skills

Name only skills that already exist. Do not invent skills or bots.
The Hermes skill in this repo is `kubrick` (`SKILL.md`). Defaults when
no other named skills apply: `anti-slop-code`, `production-systems`,
`google-developer-style`.
