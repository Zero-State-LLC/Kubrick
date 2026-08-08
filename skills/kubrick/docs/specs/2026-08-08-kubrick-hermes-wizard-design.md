# Design: Kubrick Hermes Wizard

**Date:** 2026-08-08  
**Status:** Approved  
**Version target:** 0.15.0 (minor — new public operator surface)  
**Hosts:** Hermes (CLI, gateway, Desktop); optional OpenClaw packaging unchanged  
**Repos:** Target delivery **Zero-State-LLC/Kubrick** (org) via PR; local development may start from `scrimshawlife-ctrl/Kubrick` / `~/Kubrick` and sync  
**Related:** Operator intent router  
[`2026-07-30-operator-intent-router-design.md`](../archive/superpowers/specs/2026-07-30-operator-intent-router-design.md)  
**Parallel pattern:** Abraxas Orchestra Hermes wizard (Approach C: CLI + chat protocol)

## Intent

Add a guided **wizard** that collapses Kubrick’s twelve-intent operator surface into a single, testable path so Hermes agents (and humans) do not freestyle `do` flags, invent occult-facing packet labels, or mutate ledgers/corpus without explicit operator intent.

The wizard is **Approach C**:

1. A thin **CLI intent** (`wizard`) on the existing intent router — interactive for real TTYs, fully non-interactive for agents.
2. A **Hermes routing protocol** in `SKILL.md` / runtime contract: chat-driven Q&A → answers JSON → `do wizard --print-only` / `--run`.
3. **Presets** for the production happy path **and** free resolution of any registered intent/action.

## Non-goals (YAGNI)

- Native Electron multi-step form inside Hermes Desktop
- Auto-apply pattern evolution or silent corpus mutation
- Replacing conversational screenplay drafting (wizard guides **deterministic tools**, not all prose)
- Reimplementing compile / visual / adapt / ledger business logic inside the wizard
- Network install / remote brief fetch
- Making MCP authoritative over the CLI

## Context

Kubrick 0.14.0 already ships:

```text
python3 scripts/kubrick.py do <intent> [--action <action>] [flags]
```

| Intent | Role |
|--------|------|
| `compile` | Brief → graph / storyboard / image packets |
| `retrieve` | Registry-aware pattern retrieval |
| `ledger` | Project symbolic ledger |
| `design` | Design-specification compilation |
| `storyboard` | Multi-frame state |
| `adapt` | Neutral packet + provider adaptation |
| `visual` | Visual QA loop |
| `learn` | Outcomes and multi-signal evolution (proposal-only apply) |
| `check` | Validation and regression |
| `operate` | Graph/ledger operators |
| `mcp` | Optional MCP server |
| `bundle` | Grok review bundle |

Canonical registry: `kubrick.manifest.yaml`. Resolve logic: `scripts/intent_router.py`.

Hermes Desktop uses the **same agent, skills, and tools** as CLI/gateway. Interactive stdin wizards are unreliable on the agent tool path; chat + non-interactive CLI is the Desktop-safe contract.

## Purpose & CLI surface

```text
python3 scripts/kubrick.py do wizard [options]
# optional soft alias for humans:
python3 scripts/kubrick.py wizard [options]
```

| Mode | Flags | Behavior |
|------|--------|----------|
| Interactive | default when TTY and no complete answers | Numbered / prompted collect; safe defaults |
| Non-interactive | `--answers PATH\|-` and/or `--preset NAME` | Fully determined; exit non-zero on invalid |
| Plan only | default when `--run` omitted; accept `--print-only` as no-op | Print resolved plan + exact argv; no mutation beyond printing |
| Execute | `--run` | Dispatch via existing intent router / same path as normal `do` |
| Machine out | `--json` | Emit `kubrick-wizard-plan.v1` JSON on stdout |
| Presets | `--preset` (see table) | Seed answers; overridable by `--answers` |

**Safety defaults:**

- Prefer print-only. `--run` is explicit.
- Never set `allow_mutate: true` unless answers explicitly include it as JSON boolean `true`.
- Bool fields (`allow_mutate`, and any future flags of that class) must be real JSON/Python `bool`s — string `"false"` is rejected (Orchestra lesson).
- Non-TTY without enough answers to resolve → exit `2` with guidance to use `--answers` / chat (Desktop-safe).
- Never write into `references/` from wizard-driven paths.
- Preserve authority classes: draft/proposal unless external authority is explicit.

## Step flow

Wizard resolves to **one primary `do <intent> [--action …]`** per invocation (v1 single-shot).

```text
1. Intent
   From answers.intent or preset (must be a registered intent, not nested wizard)

2. Action
   answers.action if set; else manifest default_action when present;
   else required (exit 2 if still missing for intents without default)

3. Path/flag fields by intent
   compile: brief (required for --run), ledger?, storyboard_plan?, mode?, provider?, out?
   adapt: packet and/or build inputs; provider for action provider
   visual: expected, observation, action (normalize|compare|correct|govern|closed-loop)
   ledger: action (init|audit|mutate|…); project/out paths; mutate requires allow_mutate
   learn evolve / operate write-like actions: require allow_mutate true
   check: action (default smoke)
   … map remaining intents to existing CLI flags without inventing new domain flags

4. Resolve → plan (argv after `do`, rationale, safety)

5. If --run → dispatch via normal kubrick do path (in-process preferred)
```

### Presets

| Preset | Intent | Seed defaults |
|--------|--------|----------------|
| `storyboard-compile` | `compile` | mode storyboard; provider grok-imagine if unset; requires brief (+ optional ledger, storyboard_plan, out) |
| `verify` | `check` | action smoke |
| `visual-qa` | `visual` | prefer closed-loop when inputs allow; requires expected + observation (or documented closed-loop inputs) |
| `adapt-provider` | `adapt` | action provider; requires packet + provider |
| `ledger-init` | `ledger` | action init; requires project/out fields per existing CLI |
| `design-build` | `design` | action build |
| `retrieve` | `retrieve` | action retrieve; requires query/problem fields per existing CLI |

Recipe parity: `storyboard-example` and `verify` recipes in the manifest remain; wizard presets are the **guided** form of the same happy paths.

## Answers schema (`kubrick-wizard-answers.v1`)

```json
{
  "schema": "kubrick-wizard-answers.v1",
  "intent": "compile",
  "action": null,
  "brief": "path/to/brief.yaml",
  "ledger": null,
  "storyboard_plan": null,
  "provider": "grok-imagine",
  "mode": "storyboard",
  "out": "out/kubrick/project",
  "packet": null,
  "expected": null,
  "observation": null,
  "query": null,
  "project": null,
  "allow_mutate": false,
  "extra_flags": []
}
```

### Validation rules

| Rule | Exit |
|------|------|
| Missing `schema` or wrong value | 2 |
| Unknown keys | 2 (strict) |
| Unknown `intent` (not in manifest registry) | 2 |
| Unknown `action` for intent | 2 |
| Missing required fields for intent/action | 2 (list missing keys) |
| `allow_mutate` not a bool when present | 2 |
| Mutating action without `allow_mutate: true` | 2 |
| Interactive on non-TTY without complete answers | 2 |
| Answers file IO error | 2 (no traceback) |

`extra_flags` is an optional list of string tokens appended after mapped flags; still subject to downstream CLI validation. Prefer named fields over `extra_flags` when a flag is common.

On-disk JSON Schema: `schemas/wizard-answers.v1.schema.json` (required for 0.15.0). Prefer JSON for agent parity with Orchestra even if other Kubrick schemas are YAML.

## Plan schema (`kubrick-wizard-plan.v1`)

```json
{
  "schema": "kubrick-wizard-plan.v1",
  "group": "creative",
  "intent": "compile",
  "action": "run",
  "argv": ["do", "compile", "--brief", "…", "--mode", "storyboard", "--out", "…"],
  "rationale": "Storyboard compile from brief with optional ledger.",
  "safety": [
    "print-only unless --run",
    "writes only under --out when run",
    "allow_mutate false"
  ],
  "run": false
}
```

**Groups (logical only, for Hermes routing copy):**

| Group | Intents |
|-------|---------|
| **creative** | compile, retrieve, adapt, storyboard, design, bundle |
| **ops** | ledger, visual, learn, operate |
| **meta** | check, mcp, wizard |

Human stdout: short prose + exact:

```text
python3 scripts/kubrick.py do compile --brief … --out …
```

## Components

| Piece | Location | Role |
|-------|----------|------|
| Wizard implementation | `scripts/kubrick_wizard.py` | Validate answers, merge presets, build argv, interactive prompts, plan format |
| CLI / router | `kubrick.manifest.yaml` intent `wizard`; `scripts/kubrick.py` / `intent_router.py` registration | Surface `do wizard` |
| Soft alias | optional `wizard` → `do wizard` | Human sugar |
| Answers schema | `schemas/wizard-answers.v1.schema.json` | Contract |
| Hermes protocol | `SKILL.md`, `references/hermes-runtime-contract.md` | Chat → answers → wizard |
| Tests | `tests/test_wizard.py` | Presets, validation, argv, non-TTY, allow_mutate, IO |
| Smoke / recipe | smoke or recipe `wizard-verify` | Non-interactive print-only |
| Docs | README, QUICKSTART, CHANGELOG, VERSION | Discoverability + 0.15.0 |

**Implementation constraints:**

- Prefer stdlib-only wizard core (match router posture). Optional PyYAML only if reading YAML answers is explicitly required later — **v1 answers are JSON**.
- Reuse `intent_router` resolve for `--run`; do not duplicate script maps.
- Prefer in-process dispatch equivalent to `kubrick.py do …`.
- Interactive TTY only when `sys.stdin.isatty()` and answers incomplete.
- Interactive mutate: require typing `CONFIRM` (not bare yes) when `allow_mutate` would be set true.

## Hermes + Desktop routing protocol

When the skill activates and the user is unsure which `do` command to run, wants a guided production path, or has not named a concrete intent:

1. Prefer **wizard** over freestyle `do` argv assembly.
2. Collect missing fields **in chat, one question at a time** (or accept a full dump if already provided). Desktop chat is the UX surface; do not open interactive stdin from the agent tool path.
3. Write answers JSON to a temp path under `/tmp` or under a user-chosen `--out` parent.
4. Run `do wizard --answers … --print-only` (optionally `--json`).
5. Show the plan; on approval, `do wizard --answers … --run` **or** execute the printed argv with the same skill root.
6. Never set `allow_mutate: true` unless the user explicitly requested ledger mutation, evolution apply, or operate locks after understanding the risk.
7. Keep esoteric/occult systems **latent** in audience-facing packets (existing SKILL rule).

Update Hermes routing tables:

| User wants… | Prefer |
|-------------|--------|
| Guided path / unsure / Desktop collect | `do wizard` |
| Known single job with full flags | `do <intent>` directly |
| Built-in example | `recipe storyboard-example` or preset `storyboard-compile` |

## Errors & security

| Case | Behavior |
|------|----------|
| Validation failure | stderr message + exit 2 |
| Downstream failure on `--run` | propagate that command’s exit code (0/1/2/3/4 per manifest) |
| Path / write surfaces | unchanged from existing intents; wizard itself only reads answers and prints (or dispatches) |
| Mutating ops | blocked unless `allow_mutate: true` |

## Testing

`tests/test_wizard.py` (project test style — pytest if suite is pytest, else unittest):

1. Each preset resolves to expected intent + critical argv tokens.
2. Default plan never includes mutate/evolve/lock without `allow_mutate`.
3. `allow_mutate: "false"` (string) rejected.
4. Unknown intent / keys rejected.
5. Non-TTY interactive path exits 2 without hanging.
6. Missing answers file → exit 2, no traceback.
7. Compile preset without brief: print-only may warn; `--run` fails closed.
8. Smoke: answers for `verify` / check smoke → plan contains check + smoke.

## Versioning & release

- Ship as **0.15.0** (new intent + skill contract).
- Align `VERSION`, `SKILL.md`, `kubrick.manifest.yaml`, CHANGELOG, install scripts per existing release checklist.
- Deliver to **Zero-State-LLC/Kubrick** via PR with green CI (mirror Orchestra’s org/PR discipline).

## Implementation order (for writing-plans)

1. `kubrick_wizard.py` — pure resolve/validate + plan structs (unit-testable).
2. Wire `wizard` intent + argparse flags; register in manifest + router.
3. Interactive prompts (TTY only).
4. `--run` via existing `do` dispatch.
5. Schema file + tests + smoke/recipe line.
6. SKILL.md / hermes-runtime-contract / README / CHANGELOG / VERSION 0.15.0.
7. Open PR against org repo `Zero-State-LLC/Kubrick`.

## Success criteria

- Hermes Desktop chat can complete storyboard-compile or verify without any stdin interactive prompts.
- Agents produce the same argv a careful human would for compile / check / visual / adapt.
- No mutate/evolve without explicit `allow_mutate: true`.
- Existing intents and fail-closed behavior unchanged.
- `do check --action smoke` and wizard tests remain green.

## Spec self-review notes

- Unknown keys: strict reject only.
- Answers schema required for 0.15.0.
- `--run` uses existing do dispatch (not a second parallel implementation).
- Smoke uses answers **file**, not fragile inline shell JSON alone.
- Org repo is the delivery target; personal fork may be development origin if already configured.
