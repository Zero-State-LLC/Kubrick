# Kubrick Operator Intent Router Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Kubrick’s flat 29-command CLI surface with a `do <intent>` router (12 intents), soft legacy aliases, human-friendly help/defaults/recipes, and a single MCP `kubrick_do` tool, without changing domain script behavior.

**Architecture:** New pure module `scripts/intent_router.py` owns `INTENT_REGISTRY`, `ALIAS_TABLE`, resolve functions, and argv builders. `scripts/kubrick.py` becomes a thin entry that resolves to an `IntentCall` and subprocesses the existing implementation script. MCP and docs switch primary teaching surface to `do`.

**Tech Stack:** Python 3.12 stdlib + existing pyyaml/jsonschema for regression tests; subprocess dispatch unchanged; no new runtime dependencies.

**Spec:** `docs/archive/superpowers/specs/2026-07-30-operator-intent-router-design.md`

## Global Constraints

- Soft cutover: every pre-existing top-level command name must keep working.
- Router contains no domain logic (no graph/ledger/evolve business rules).
- Pass through stdout, stderr, and exit codes from underlying scripts.
- Fail closed on unknown intent/action (exit code `2`).
- TTY deprecation hints on aliases; quiet when non-TTY or `KUBRICK_AGENT=1`.
- MCP remains optional and non-authoritative.
- Do not mutate corpus or auto-apply evolution.
- Prefer TDD: failing test first, then minimal implementation.
- Work on branch `agent/operator-intent-router` from current `main` (or rebase onto latest main).

## File map

| File | Responsibility |
|---|---|
| Create `scripts/intent_router.py` | Registry, aliases, resolve, argv builders, help text, recipes |
| Modify `scripts/kubrick.py` | Entry: parse → resolve → dispatch |
| Modify `scripts/mcp_kubrick_server.py` | Single `kubrick_do` tool (+ optional thin wrappers later) |
| Create `scripts/test_intent_router.py` | Unit + alias parity + help + defaults |
| Modify `SKILL.md`, `QUICKSTART.md`, `README.md` | Teach intents first; aliases appendix |
| Modify `CHANGELOG.md` | Unreleased / next version note |

---

### Task 1: IntentCall + registry + alias completeness tests

**Files:**
- Create: `scripts/intent_router.py`
- Create: `scripts/test_intent_router.py`

**Interfaces:**
- Produces: `IntentCall` dataclass; `INTENT_REGISTRY: dict[str, IntentSpec]`; `ALIAS_TABLE: dict[str, AliasSpec]`; `all_legacy_commands() -> set[str]`

- [ ] **Step 1: Write failing tests for registry structure**

```python
# scripts/test_intent_router.py
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import intent_router as ir

EXPECTED_INTENTS = {
    "compile", "retrieve", "ledger", "design", "storyboard", "adapt",
    "visual", "learn", "check", "operate", "mcp", "bundle",
}

# From design spec: must stay complete
EXPECTED_LEGACY = {
    "compile", "retrieve", "ledger", "design-build",
    "storyboard-propagate", "storyboard-compare",
    "adapter-build", "adapt-provider", "adapt-grok", "adapt-flux",
    "adapt-sd3", "adapt-midjourney",
    "visual-normalize", "visual-compare", "visual-correct",
    "correction-govern", "closed-loop-qa",
    "outcome-record", "evolution-propose", "forge-signals",
    "validate-skill", "validate-corpus", "coverage",
    "artifact-validate", "repeatability", "eval",
    "operator", "mcp-server", "grok-review-bundle",
}


def test_intent_count_and_names():
    assert set(ir.INTENT_REGISTRY) == EXPECTED_INTENTS


def test_every_legacy_maps_exactly_once():
    assert set(ir.ALIAS_TABLE) == EXPECTED_LEGACY
    for name, alias in ir.ALIAS_TABLE.items():
        assert alias.intent in ir.INTENT_REGISTRY, name
        actions = ir.INTENT_REGISTRY[alias.intent].actions
        assert alias.action in actions or alias.passthrough_action, name
```

- [ ] **Step 2: Run tests: expect fail (module missing)**

Run: `python3 scripts/test_intent_router.py`  
(or `python3 -c "import runpy; runpy.run_path('scripts/test_intent_router.py')"` with a `if __name__` runner)

Expected: `ModuleNotFoundError` or import error for `intent_router`

- [ ] **Step 3: Minimal `intent_router.py` types + tables**

```python
# scripts/intent_router.py
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

SCRIPTS = Path(__file__).resolve().parent

@dataclass(frozen=True)
class IntentCall:
    intent: str
    action: str
    script: Path
    argv: list[str]
    legacy_name: str | None = None

@dataclass(frozen=True)
class AliasSpec:
    intent: str
    action: str
    # When True, first remainder token may be treated as action (ledger, operator)
    passthrough_action: bool = False
    fixed_flags: tuple[str, ...] = ()

@dataclass(frozen=True)
class IntentSpec:
    description: str
    actions: dict[str, str]  # action -> script filename
    default_action: str | None = None
    # Optional specialized argv builder name keys later
```

Populate `INTENT_REGISTRY` with all 12 intents and their script filenames matching current `COMMANDS` in `kubrick.py`. Populate `ALIAS_TABLE` with all 29 legacy names per the design spec.

Example fragment:

```python
INTENT_REGISTRY: dict[str, IntentSpec] = {
    "compile": IntentSpec("Full brief-to-packet compile", {"run": "kubrick_compile.py"}, "run"),
    "adapt": IntentSpec(
        "Neutral packet and provider adaptation",
        {"build": "build_model_adapter_packet.py", "provider": "adapt_provider.py"},
        "build",
    ),
    # ... all 12
}

ALIAS_TABLE: dict[str, AliasSpec] = {
    "adapt-flux": AliasSpec("adapt", "provider", fixed_flags=("--provider", "flux")),
    "ledger": AliasSpec("ledger", "init", passthrough_action=True),  # action overridden by subcommand
    "operator": AliasSpec("operate", "saturation-score", passthrough_action=True),
    # ... all 29
}
```

Note: for `ledger` / `operator` passthrough, the real action is the first positional subcommand; `AliasSpec.action` is only a placeholder when argv empty.

- [ ] **Step 4: Add test runner main and re-run**

```python
def main():
    test_intent_count_and_names()
    test_every_legacy_maps_exactly_once()
    print("intent_router unit: registry PASS")

if __name__ == "__main__":
    main()
```

Run: `python3 scripts/test_intent_router.py`  
Expected: `intent_router unit: registry PASS`

- [ ] **Step 5: Commit**

```bash
git add scripts/intent_router.py scripts/test_intent_router.py
git commit -m "feat(cli): add intent registry and legacy alias tables"
```

---

### Task 2: Resolve `do` and legacy aliases → IntentCall

**Files:**
- Modify: `scripts/intent_router.py`
- Modify: `scripts/test_intent_router.py`

**Interfaces:**
- Produces: `resolve(argv: list[str]) -> IntentCall`  
  - `argv` is full argv after program name, e.g. `["do", "adapt", "--action", "provider", ...]` or `["adapt-flux", "--packet", "p.yaml"]`
- Produces: `RouterError(Exception)` with `.message` and `.exit_code == 2`

- [ ] **Step 1: Write failing resolve tests**

```python
import pytest  # only if pytest installed; else plain assert + raises

def test_resolve_do_adapt_provider():
    call = ir.resolve([
        "do", "adapt", "--action", "provider",
        "--provider", "flux", "--packet", "p.yaml", "--output", "o.yaml",
    ])
    assert call.intent == "adapt"
    assert call.action == "provider"
    assert call.script.name == "adapt_provider.py"
    assert call.argv == ["--provider", "flux", "--packet", "p.yaml", "--output", "o.yaml"]
    assert call.legacy_name is None

def test_resolve_alias_adapt_flux():
    call = ir.resolve(["adapt-flux", "--packet", "p.yaml", "--output", "o.yaml"])
    assert call.intent == "adapt"
    assert call.action == "provider"
    assert call.script.name == "adapt_provider.py"
    assert "--provider" in call.argv and "flux" in call.argv
    assert call.legacy_name == "adapt-flux"

def test_resolve_unknown_intent():
    try:
        ir.resolve(["do", "nope"])
        raise AssertionError("expected RouterError")
    except ir.RouterError as e:
        assert e.exit_code == 2
        assert "compile" in e.message or "valid" in e.message.lower()

def test_ledger_passthrough_action():
    call = ir.resolve(["ledger", "audit", "--ledger", "L.yaml"])
    assert call.intent == "ledger"
    assert call.action == "audit"
    assert call.script.name == "symbolic_ledger.py"
    assert call.argv[0] == "audit"
```

- [ ] **Step 2: Run: expect fail**

Run: `python3 scripts/test_intent_router.py`  
Expected: fail on missing `resolve`

- [ ] **Step 3: Implement `resolve`**

```python
class RouterError(Exception):
    def __init__(self, message: str, exit_code: int = 2):
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code

def resolve(argv: list[str]) -> IntentCall:
    if not argv:
        raise RouterError("missing command; try: kubrick do <intent> …")
    if argv[0] == "do":
        return _resolve_do(argv[1:])
    if argv[0] in {"help", "--help", "-h"} and len(argv) == 1:
        raise RouterError("HELP")  # entrypoint handles help specially, or return a HelpSentinel
    if argv[0] in ALIAS_TABLE or argv[0] in _legacy_direct():
        return _resolve_alias(argv[0], argv[1:])
    # also allow bare intent without do? Spec says primary is `do`; optional: `kubrick adapt …`
    if argv[0] in INTENT_REGISTRY:
        return _resolve_do(argv)
    raise RouterError(f"unknown command {argv[0]!r}; valid intents: {', '.join(sorted(INTENT_REGISTRY))}")
```

Implement `_resolve_do` and `_resolve_alias`:

- Parse `--action` from flags if present.
- Else use `default_action`, with default-selection rules:
  - `adapt`: if `--provider` present → `provider`, else `build`
  - `visual`: if enough closed-loop flags later → `closed-loop`; for v1 only apply default when `--action` omitted and no conflicting single-step flags; simplest v1: default `closed-loop` only when `--expected` and `--observation-input` present, else require `--action`
  - `check` with no action → `smoke`
- Strip router-only flags (`--action`) before building script argv.
- For provider adapters, map `provider` action always to `adapt_provider.py` with `--provider X` (except keep `adapt_grok` alias using either `adapt_grok_imagine.py` OR `adapt_provider.py --provider grok-imagine` (**prefer `adapt_provider.py` for all** to reduce scripts, but parity with current grok path requires calling `adapt_grok_imagine.py` for `adapt-grok` only if behavior differs; check scripts) if identical enough, use `adapt_provider.py` for all providers).

**Decision locked for plan:**  
- `adapt-grok` → script `adapt_grok_imagine.py` (preserve exact current path)  
- other providers → `adapt_provider.py`  
- `do adapt --action provider --provider grok-imagine` → `adapt_provider.py` (acceptable; document slight path difference) OR route grok-imagine to `adapt_grok_imagine.py` when provider is grok-imagine. **Use the latter for behavior safety.**

```python
def _script_for(intent: str, action: str, flags: list[str]) -> Path:
    if intent == "adapt" and action == "provider":
        provider = _flag_value(flags, "--provider")
        if provider == "grok-imagine":
            return SCRIPTS / "adapt_grok_imagine.py"
        return SCRIPTS / "adapt_provider.py"
    filename = INTENT_REGISTRY[intent].actions[action]
    return SCRIPTS / filename
```

For `ledger` and `operate`/`operator`: first positional is action/subcommand and remains first argv element for the script.

- [ ] **Step 4: Run tests: expect PASS**

Run: `python3 scripts/test_intent_router.py`  
Expected: all resolve tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/intent_router.py scripts/test_intent_router.py
git commit -m "feat(cli): resolve do and legacy aliases to IntentCall"
```

---

### Task 3: Wire `kubrick.py` entrypoint + help + recipes

**Files:**
- Modify: `scripts/kubrick.py` (replace COMMANDS map dispatch)
- Modify: `scripts/intent_router.py` (help formatters, recipes)
- Modify: `scripts/test_intent_router.py`

**Interfaces:**
- Produces: `format_top_level_help() -> str`
- Produces: `format_intent_help(intent: str) -> str`
- Produces: `resolve_recipe(name: str) -> list[str]`  # returns argv for resolve(), not shell

- [ ] **Step 1: Failing tests for help and recipe**

```python
def test_top_level_help_lists_intents_not_all_aliases():
    text = ir.format_top_level_help()
    assert "adapt" in text and "visual" in text and "learn" in text
    assert "adapt-flux" not in text  # aliases not first-class
    assert "do <intent>" in text or "kubrick do" in text

def test_recipe_storyboard_example():
    argv = ir.resolve_recipe("storyboard-example")
    call = ir.resolve(argv)
    assert call.intent == "compile"
    assert call.script.name == "kubrick_compile.py"
```

- [ ] **Step 2: Implement help + recipes**

```python
RECIPES = {
    "storyboard-example": [
        "do", "compile",
        "--brief", "examples/authority-transfer-storyboard/brief.yaml",
        "--ledger", "examples/authority-transfer-storyboard/symbolic-ledger.yaml",
        "--mode", "storyboard",
        "--storyboard-plan", "examples/authority-transfer-storyboard/storyboard-plan.yaml",
        "--provider", "grok-imagine",
        "--out", "out/kubrick/authority-transfer",
    ],
    "verify": ["do", "check", "--action", "smoke"],
}

def format_top_level_help() -> str:
    lines = [
        "usage: kubrick do <intent> [--action <action>] [flags]",
        "",
        "Intents:",
    ]
    for name in sorted(INTENT_REGISTRY):
        lines.append(f"  {name:12} {INTENT_REGISTRY[name].description}")
    lines += [
        "",
        "Sugar:  kubrick recipe <name>",
        "        kubrick help <intent>",
        "        kubrick aliases",
        "Legacy command names still work as aliases.",
    ]
    return "\n".join(lines) + "\n"
```

`check` action `smoke`: argv builder runs two scripts sequentially, **not pure single-script**. Handle in `kubrick.py` dispatch:

```python
if call.intent == "check" and call.action == "smoke":
    for script in ("validate_hermes_skill.py", "validate_pattern_corpus.py"):
        r = subprocess.run([PY, str(SCRIPTS/script), *call.argv], cwd=ROOT)
        if r.returncode != 0:
            raise SystemExit(r.returncode)
    print("check smoke: PASS")
    raise SystemExit(0)
```

- [ ] **Step 3: Rewrite `kubrick.py`**

```python
#!/usr/bin/env python3
from __future__ import annotations
import os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
sys.path.insert(0, str(Path(__file__).resolve().parent))
import intent_router as ir

def _is_agent() -> bool:
    return os.environ.get("KUBRICK_AGENT") == "1" or not sys.stderr.isatty()

def main() -> None:
    argv = sys.argv[1:]
    if not argv or argv[0] in {"-h", "--help", "help"} and len(argv) == 1:
        sys.stdout.write(ir.format_top_level_help())
        raise SystemExit(0)
    if argv[0] == "help" and len(argv) >= 2:
        sys.stdout.write(ir.format_intent_help(argv[1]))
        raise SystemExit(0)
    if argv[0] == "aliases":
        sys.stdout.write(ir.format_aliases())
        raise SystemExit(0)
    if argv[0] == "recipe":
        if len(argv) < 2:
            raise SystemExit("usage: kubrick recipe <name>")
        argv = ir.resolve_recipe(argv[1])
    try:
        call = ir.resolve(argv)
    except ir.RouterError as e:
        print(e.message, file=sys.stderr)
        raise SystemExit(e.exit_code)
    if call.legacy_name and not _is_agent() and os.environ.get("KUBRICK_QUIET") != "1":
        print(
            f"note: `{call.legacy_name}` is a legacy alias; prefer `kubrick do {call.intent} --action {call.action}`",
            file=sys.stderr,
        )
    # smoke multi-dispatch if needed
    if call.intent == "check" and call.action == "smoke":
        ...
    result = subprocess.run([PY, str(call.script), *call.argv], cwd=ROOT)
    raise SystemExit(result.returncode)

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Manual smoke**

```bash
python3 scripts/kubrick.py --help | head -20
python3 scripts/kubrick.py adapt-flux --help 2>&1 | head -5   # may pass through to adapt_provider help
python3 scripts/kubrick.py do check --action skill
python3 scripts/validate_hermes_skill.py   # still works direct
```

Expected: help shows 12 intents; `do check --action skill` exits 0 (validate-skill).

- [ ] **Step 5: Commit**

```bash
git add scripts/kubrick.py scripts/intent_router.py scripts/test_intent_router.py
git commit -m "feat(cli): wire intent router into kubrick entrypoint"
```

---

### Task 4: Alias parity + regression suite

**Files:**
- Modify: `scripts/test_intent_router.py`
- Optionally: `scripts/test_wave2_wave3.py` (no change if aliases preserved)

- [ ] **Step 1: Parity tests: same script for alias vs do**

```python
def test_alias_do_parity_matrix():
    cases = [
        (["validate-skill"], ["do", "check", "--action", "skill"]),
        (["closed-loop-qa", "--expected", "e", "--observation-input", "o",
          "--source-graph-id", "g", "--frame-id", "f1", "--out", "out/x"],
         ["do", "visual", "--action", "closed-loop", "--expected", "e",
          "--observation-input", "o", "--source-graph-id", "g",
          "--frame-id", "f1", "--out", "out/x"]),
        (["forge-signals", "--project-id", "p", "--input", "i.yaml", "--output", "o.yaml"],
         ["do", "learn", "--action", "forge-signals", "--project-id", "p",
          "--input", "i.yaml", "--output", "o.yaml"]),
    ]
    for legacy, modern in cases:
        a, b = ir.resolve(legacy), ir.resolve(modern)
        assert a.script == b.script
        assert a.argv == b.argv
```

- [ ] **Step 2: Run unit tests**

Run: `python3 scripts/test_intent_router.py`  
Expected: PASS

- [ ] **Step 3: Full regression via aliases (existing tests)**

```bash
python3 scripts/test_outcome_governance.py
python3 scripts/test_wave2_wave3.py
python3 scripts/test_design_specification.py
python3 scripts/kubrick.py do check --action skill
python3 scripts/kubrick.py validate-skill
python3 scripts/kubrick.py do check --action smoke
```

Expected: all PASS / exit 0

- [ ] **Step 4: Commit**

```bash
git add scripts/test_intent_router.py
git commit -m "test(cli): alias/do parity and regression via intent router"
```

---

### Task 5: MCP single tool `kubrick_do`

**Files:**
- Modify: `scripts/mcp_kubrick_server.py`
- Modify: `scripts/test_intent_router.py` (or small MCP smoke in same file)

- [ ] **Step 1: Replace TOOLS list with kubrick_do**

Keep optional thin wrappers only if needed for back-compat; **primary**:

```python
TOOLS = [
    {
        "name": "kubrick_do",
        "description": "Run a Kubrick intent (compile, retrieve, adapt, visual, learn, check, …)",
        "inputSchema": {
            "type": "object",
            "required": ["intent"],
            "properties": {
                "intent": {"type": "string"},
                "action": {"type": "string"},
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "CLI flags after intent/action, e.g. [\"--provider\",\"flux\",\"--packet\",\"p.yaml\"]",
                },
            },
        },
    }
]
```

`call_tool`:

```python
def call_tool(name, arguments):
    if name != "kubrick_do":
        return error...
    intent = arguments["intent"]
    action = arguments.get("action")
    args = arguments.get("args") or []
    cli = ["do", intent]
    if action:
        cli += ["--action", action]
    cli += list(args)
    proc = subprocess.run([PY, str(ROOT/"scripts/kubrick.py"), *cli], ...)
```

- [ ] **Step 2: Smoke tools/list**

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python3 scripts/kubrick.py mcp-server
# or: python3 scripts/mcp_kubrick_server.py
```

Expected: tool name `kubrick_do` present.

- [ ] **Step 3: Commit**

```bash
git add scripts/mcp_kubrick_server.py
git commit -m "feat(mcp): expose single kubrick_do tool over intent router"
```

---

### Task 6: Docs: SKILL, QUICKSTART, README, CHANGELOG

**Files:**
- Modify: `SKILL.md` (Unified CLI section)
- Modify: `QUICKSTART.md` (command list + examples using `do`)
- Modify: `README.md` (Operator Commands)
- Modify: `CHANGELOG.md` (Unreleased or 0.13.1 section)

- [ ] **Step 1: SKILL.md CLI block**

Replace the long peer list with:

```text
python scripts/kubrick.py do <intent> [--action <action>] [flags]

Intents: compile, retrieve, ledger, design, storyboard, adapt,
         visual, learn, check, operate, mcp, bundle

Examples:
  kubrick do compile --brief … --ledger … --mode storyboard --provider flux --out …
  kubrick do adapt --action provider --provider flux --packet … --output …
  kubrick do visual --action closed-loop --expected … --observation-input … --out …
  kubrick do learn --action forge-signals --project-id … --input … --output …
  kubrick do check --action smoke

Legacy names (adapt-flux, closed-loop-qa, …) remain as aliases.
```

- [ ] **Step 2: QUICKSTART: lead with intents; keep one “Aliases” subsection**

Update each numbered section’s example command to `do` form; leave one legacy example for compat.

- [ ] **Step 3: README operator table**

Same intent list; link to QUICKSTART recipes.

- [ ] **Step 4: CHANGELOG**

```markdown
## [Unreleased]

### Changed
- Operator CLI: primary surface is `kubrick do <intent>`; legacy command names remain soft aliases.
- MCP: single `kubrick_do` tool.
```

- [ ] **Step 5: Commit**

```bash
git add SKILL.md QUICKSTART.md README.md CHANGELOG.md
git commit -m "docs: teach kubrick do <intent> as primary operator surface"
```

---

### Task 7: Release hygiene + final verification

**Files:** none required unless `audit_release_version` needs a version bump (prefer **no version bump** until user asks; ship as unreleased on main).

- [ ] **Step 1: Full verification matrix**

```bash
python3 scripts/test_intent_router.py
python3 scripts/test_outcome_governance.py
python3 scripts/test_wave2_wave3.py
python3 scripts/test_design_specification.py
python3 scripts/kubrick.py do check --action skill
python3 scripts/kubrick.py do check --action corpus
python3 scripts/kubrick.py do check --action smoke
python3 scripts/kubrick.py validate-skill
python3 scripts/kubrick.py compile \
  --brief examples/authority-transfer-storyboard/brief.yaml \
  --ledger examples/authority-transfer-storyboard/symbolic-ledger.yaml \
  --mode storyboard \
  --storyboard-plan examples/authority-transfer-storyboard/storyboard-plan.yaml \
  --provider grok-imagine \
  --out out/kubrick/authority-transfer
python3 scripts/kubrick.py do compile \
  --brief examples/authority-transfer-storyboard/brief.yaml \
  --ledger examples/authority-transfer-storyboard/symbolic-ledger.yaml \
  --mode storyboard \
  --storyboard-plan examples/authority-transfer-storyboard/storyboard-plan.yaml \
  --provider flux \
  --out out/kubrick/authority-transfer-flux
python3 scripts/audit_release_version.py --strict
```

Expected: all green (strict version audit still READY for 0.13.0).

- [ ] **Step 2: Open PR**

```bash
git push -u origin HEAD
gh pr create --title "feat(cli): intent router (kubrick do <intent>)" \
  --body "Implements docs/superpowers/specs/2026-07-30-operator-intent-router-design.md"
```

- [ ] **Step 3: CI green then merge** (with user approval if required)

---

## Spec coverage checklist

| Spec requirement | Task |
|---|---|
| `do <intent>` primary surface | 2, 3 |
| 12 intents | 1 |
| Full 29 alias map | 1, 2, 4 |
| Soft deprecation TTY hints | 3 |
| Defaults (adapt/visual/check) | 2 |
| Recipes | 3 |
| Help lists intents not 29 peers | 3 |
| MCP `kubrick_do` | 5 |
| Docs update | 6 |
| Pass-through exit codes | 3, 4 |
| No domain logic in router | 1–3 (constraint) |
| Regression suite | 4, 7 |

## Placeholder / consistency self-review

- No TBD steps.
- `IntentCall` fields consistent across tasks.
- Grok provider script routing explicitly decided.
- Smoke multi-script dispatch isolated to `check`/`smoke` only.
