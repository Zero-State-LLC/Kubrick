# Design: Kubrick Operator Intent Router

**Date:** 2026-07-30  
**Status:** Approved for planning (pending user review of this written spec)  
**Repo:** `scrimshawlife-ctrl/Kubrick` (Hermes skill)  
**Scope:** CLI / operator surface only, not corpus, Forge kernel, or generation APIs

## Problem

Kubrick’s unified CLI exposes ~29 top-level peer commands via a flat map in `scripts/kubrick.py`. Hermes must choose among too many peers. Humans get an ungrouped help dump and high flag noise. Related tools are inconsistently nested (`ledger`, `operator` have subcommands; `adapt-*` and `visual-*` do not).

## Goals

1. **Hermes-first routing:** skill docs and MCP prefer a small, stable set of intents.
2. **Human usability:** grouped help, defaults, recipes, clearer errors.
3. **Soft cutover:** all existing command names keep working as aliases.
4. **No new domain logic** in the router; existing `scripts/*.py` remain implementations.
5. Preserve invariants: fail closed, proposal-only evolution, Forge canonical, MCP non-authoritative.

## Non-goals

- Removing legacy command names in this change (hard cutover is a later release).
- Rewriting compile/visual/learn business logic.
- Making MCP authoritative over the CLI.
- Automatic corpus mutation or silent authority promotion.

## Approach

**Intent router** with dual presentation:

```text
python scripts/kubrick.py do <intent> [--action <action>] [flags]
python scripts/kubrick.py <legacy-command> [flags]   # soft alias → do
```

One execution path; two ways to name it.

## Intent catalog

Twelve stable intents (kebab-case):

| Intent | Purpose | Primary actions |
|---|---|---|
| `compile` | Full brief → graph → storyboard → provider packet | (default: run compile) |
| `retrieve` | Registry-aware pattern retrieval | (default: retrieve) |
| `ledger` | Project symbolic ledger | `init`, `audit`, `mutate`, `rehydrate`, `apply-forge`, `export-retrieval`, `record-pattern` |
| `design` | Design-specification compilation | (default: build) |
| `storyboard` | Multi-frame state | `propagate`, `compare` |
| `adapt` | Neutral + provider prompt packets | `build`, `provider` (with `--provider`) |
| `visual` | Visual QA loop | `normalize`, `compare`, `correct`, `govern`, `closed-loop` |
| `learn` | Outcomes and multi-signal evolution | `outcome`, `evolve`, `forge-signals` |
| `check` | Validation and regression | `skill`, `corpus`, `coverage`, `artifact`, `repeatability`, `eval`, `smoke` |
| `operate` | Graph/ledger operators | `saturation-score`, `counterpoint`, `convergence-lock`, `surface-occult-audit`, `symbolic-architecture-export`, `motif-mutation` |
| `mcp` | Optional MCP server | (default: serve) |
| `bundle` | Grok review bundle | (default: build) |

### Legacy alias map (complete)

Every current top-level name maps to exactly one intent/action:

| Legacy | Intent | Action / notes |
|---|---|---|
| `compile` | `compile` | default |
| `retrieve` | `retrieve` | default |
| `ledger` | `ledger` | pass-through subcommand as action |
| `design-build` | `design` | `build` |
| `storyboard-propagate` | `storyboard` | `propagate` |
| `storyboard-compare` | `storyboard` | `compare` |
| `adapter-build` | `adapt` | `build` |
| `adapt-provider` | `adapt` | `provider` |
| `adapt-grok` | `adapt` | `provider` + `provider=grok-imagine` |
| `adapt-flux` | `adapt` | `provider` + `provider=flux` |
| `adapt-sd3` | `adapt` | `provider` + `provider=sd3` |
| `adapt-midjourney` | `adapt` | `provider` + `provider=midjourney` |
| `visual-normalize` | `visual` | `normalize` |
| `visual-compare` | `visual` | `compare` |
| `visual-correct` | `visual` | `correct` |
| `correction-govern` | `visual` | `govern` |
| `closed-loop-qa` | `visual` | `closed-loop` |
| `outcome-record` | `learn` | `outcome` |
| `evolution-propose` | `learn` | `evolve` |
| `forge-signals` | `learn` | `forge-signals` |
| `validate-skill` | `check` | `skill` |
| `validate-corpus` | `check` | `corpus` |
| `coverage` | `check` | `coverage` |
| `artifact-validate` | `check` | `artifact` |
| `repeatability` | `check` | `repeatability` |
| `eval` | `check` | `eval` |
| `operator` | `operate` | pass-through subcommand as action |
| `mcp-server` | `mcp` | `serve` |
| `grok-review-bundle` | `bundle` | `build` |

## Architecture

```text
kubrick.py
  ├─ parse argv
  ├─ if "do": IntentCall from flags
  ├─ else: IntentCall from ALIAS_TABLE[legacy]
  └─ dispatch IntentCall → scripts/<impl>.py via subprocess

intent_router.py  (new)
  ├─ INTENT_REGISTRY
  ├─ ALIAS_TABLE
  ├─ resolve_do(argv) -> IntentCall
  ├─ resolve_alias(name, argv) -> IntentCall
  └─ build_script_argv(call) -> (script_path, argv)

scripts/*.py  (unchanged domain logic)
```

### IntentCall (internal)

```text
intent: str
action: str
script: Path
argv: list[str]
legacy_name: str | None   # set when invoked via alias
```

### Dispatch rules

1. Validate intent ∈ registry.
2. Validate action ∈ intent’s allowed actions (or apply default action).
3. Map router flags → implementation flags via per-intent argv builders.
4. Run underlying script; pass through stdout, stderr, exit code.
5. Do not reinterpret domain exit codes (including `NOT_COMPUTABLE` paths).

## Human usability

### Help

- `kubrick` / `kubrick --help`: list the **12 intents** only, one line each; footer notes “legacy aliases still work; see `kubrick aliases`”.
- `kubrick do <intent> --help`: actions and flags for that intent only.
- `kubrick help <intent>`: same as above (sugar).
- `kubrick aliases`: print alias table (for humans/docs; agents rarely need it).

### Defaults

| Situation | Default |
|---|---|
| `do adapt` with `--provider` set, no `--action` | action = `provider` |
| `do adapt` with graph/storyboard paths, no provider | action = `build` |
| `do visual` with expected + observation + graph + frame | action = `closed-loop` if no `--action` |
| `do check` with no `--action` | action = `smoke` (validate-skill + validate-corpus) |
| `do compile` / `retrieve` / `design` / `mcp` / `bundle` | single default action |

Defaults never invent missing domain inputs; missing required paths still fail closed with an example command.

### Recipes (human sugar, not new intents)

Thin wrappers that expand to a full `do` invocation with known-good flags:

| Recipe | Expands to |
|---|---|
| `kubrick recipe storyboard-example` | canonical authority-transfer compile (grok-imagine) |
| `kubrick recipe verify` | `do check --action smoke` then note full `eval` command |

Recipes live in the router config; they do not bypass scripts.

### Feedback

- **TTY:** multi-line human messages; alias deprecation one-liner on stderr.
- **Non-TTY or `KUBRICK_AGENT=1`:** single-line errors (`error: …; valid: a|b|c`); deprecation suppressed unless `KUBRICK_DEPRECATE=1`.
- **Success:** prefer one summary line when the underlying script already prints a receipt (do not double-wrap JSON).

## MCP

Prefer **one tool**: `kubrick_do` with parameters:

- `intent` (required)
- `action` (optional; defaults apply)
- `args` (object or string list of CLI flags)

MCP server shells `python scripts/kubrick.py do …`. MCP remains optional and non-authoritative.

Optional later: thin per-intent tools that still call `do` (not required for v1).

## Error handling

| Case | Exit | Message |
|---|---|---|
| Unknown intent | 2 | list of 12 intents |
| Unknown action | 2 | list of actions for that intent |
| Missing required inputs | 2 | what is missing + one example command |
| Underlying script failure | passthrough | stdout/stderr unchanged |
| Domain `NOT_COMPUTABLE` | passthrough | unchanged from script |

## Migration plan

1. Implement `intent_router.py` + rewrite `kubrick.py` entry to use it.
2. Wire all 29 aliases through the router (behavior-preserving).
3. Update `SKILL.md`, `QUICKSTART.md`, `README.md` to teach `do <intent>` first; aliases appendix.
4. Point MCP at `kubrick_do`.
5. Keep CI using either aliases or `do` forms (both must pass).
6. **Not in this change:** delete aliases; tag a later deprecation release if needed.

## Testing

| Test | Asserts |
|---|---|
| Registry completeness | every legacy name maps to one intent/action |
| Alias ≡ do | same script path + equivalent argv for representative commands |
| Help surface | top-level help lists intents, not 29 peers |
| Defaults | adapt/visual/check default action selection |
| MCP | tools/list includes `kubrick_do`; call runs |
| Regression | existing `test_wave2_wave3`, outcome governance, hermes eval, design-spec tests pass via aliases |

## Documentation touch list

- `SKILL.md`: Unified CLI section → intents first
- `QUICKSTART.md`: reorganize around intents + recipes
- `README.md`: operator commands table
- `scripts/mcp_kubrick_server.py`: tool surface
- `docs/archive/releases/ROADMAP-v0.13.md` or a short note in changelog under Unreleased / next patch

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Argv mapping bugs change behavior | golden IntentCall tests; pass-through remainder for unmapped flags where safe |
| Agents still call 29 names | soft aliases forever until a later hard cut; skill documents only intents |
| Help becomes too abstract | per-intent `--help` with concrete examples |
| Recipe drift | recipes only wrap documented canonical examples |

## Success criteria

1. Hermes skill contract documents ≤12 intents as the primary operator surface.
2. `kubrick --help` does not list 29 peers as first-class choices.
3. All pre-change CI commands still succeed without modification (aliases).
4. Equivalent `do` form exists for every prior workflow in QUICKSTART.
5. Human can run the storyboard example via a single recipe or a short `do compile` line with defaults documented.

## Open decisions (resolved in brainstorm)

| Decision | Choice |
|---|---|
| Primary simplification | Intent router (`do <intent>`) |
| Compatibility | Soft aliases for all legacy names |
| Human UX | Grouped help, defaults, recipes, TTY deprecation hints |
| MCP | Single `kubrick_do` tool |

## Out of scope follow-ups

- Hard removal of aliases
- JSON error envelopes (`--json-errors`)
- In-process import of scripts (no subprocess) for speed
- Auto-discovery of project paths beyond conservative defaults
