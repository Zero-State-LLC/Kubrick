# Security and Threat Model: Kubrick

Kubrick is a local, stdlib-first Hermes skill. It does not require network access,
API keys, or privileged installation for core creative work.

## Trust boundaries

| Surface | Trust | Notes |
|---|---|---|
| Local CLI (`scripts/kubrick.py`) | Trusted operator | Caller controls project files |
| Optional MCP (`kubrick_do`) | **Untrusted args** | Intent/action allowlisted; flags validated; paths bounded |
| Continuity Forge / model / vision APIs | Optional external | Never required; adapters are syntax-only |
| Pattern corpus (`references/`, `schemas/`) | Read-only at runtime | Ordinary operators must not mutate these trees |
| `out/` (project or skill) | Mutable overlay | Cache, receipts, and project outputs only |

## Path policy

- Set `KUBRICK_PROJECT_DIR` to pin the project root (defaults to cwd).
- Reads may come from the project root or the skill root (examples, schemas, references).
- Writes must stay inside the project root or skill `out/`. Retrieval cache and receipts go to `<project>/out/kubrick/retrieval/`.
- Writes into `references/` (except `usage/`), `schemas/`, `scripts/`, `skills/`, `.git`, and core contract files are rejected.

## Intake bounds

Structured YAML/JSON intake is rejected when it exceeds `2_000_000` bytes before parse.
YAML loading uses `yaml.safe_load` only.

## Installer

`install.sh` / `install.ps1` stage under `$HERMES_HOME`, validate before activation,
swap atomically, and keep backups **outside** the skills discovery tree. They do not
download remote payloads.

## Authority

Local outputs are `PROPOSED` or `OBSERVATION`. Weak or contradictory evidence returns
`NOT_COMPUTABLE`. Corpus confidence and Forge canon are never auto-mutated by Kubrick.

## Reporting

Report security issues privately to the repository owner. Do not open public issues
for exploitable path/MCP bypasses before a fix is available.
