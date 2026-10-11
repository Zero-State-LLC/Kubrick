# Security and Threat Model: Kubrick

Kubrick is a local, stdlib-first Hermes skill. Core creative work needs no network
access, API key, or privileged installation. Usage telemetry is a separate, optional
network surface. The current client keeps it disabled until the operator grants
consent and configures an HTTPS endpoint and bearer credential. This repository has
no selected or provisioned collector.

## Trust boundaries

| Surface | Trust | Notes |
|---|---|---|
| Local CLI (`scripts/kubrick.py`) | Trusted operator | Caller controls project files |
| Optional MCP (`kubrick_do`) | **Untrusted args** | Intent/action allowlisted; flags validated; paths bounded |
| Continuity Forge / model / vision APIs | Optional external | Never required; adapters are syntax-only |
| Telemetry outbox | Per-user local state | Default-off; stores only scope consent and bounded allowlisted events |
| Current telemetry client | Optional external request | Requires consent, an HTTPS endpoint, and a configured bearer token |
| Proposed collector | Not deployed | Design draft recommends anonymous ingestion; owner approval and a separate client change are required |
| Pattern corpus (`references/`, `schemas/`) | Read-only at runtime | Ordinary operators must not mutate these trees |
| `out/` (project or skill) | Mutable overlay | Cache, receipts, and project outputs only |

## Path policy

- Set `KUBRICK_PROJECT_DIR` to pin the project root (defaults to cwd).
- Reads may come from the project root or the skill root (examples, schemas, references).
- Writes must stay inside the project root or skill `out/`. Retrieval cache and receipts go to `<project>/out/kubrick/retrieval/`.
- Writes into `references/` (except `usage/`), `schemas/`, `scripts/`, `skills/`, `.git`, and core contract files are rejected.
- Telemetry consent and its bounded outbox are the only user-state exception: they live under the OS per-user state directory, not inside project files or `out/`. POSIX permissions are `0700` for the directory and `0600` for the SQLite database; Windows relies on the local profile ACL.

## Telemetry network boundary

- Usage and quality-feedback consent are separate and default off. Disabling a scope deletes its queued events; disabling all clears the queue.
- Only fixed schema fields are sent. Prompts, output, files, paths, project IDs, receipts, free text, and exception details are excluded.
- Transmission requires consent, an HTTPS endpoint without URL credentials/query/fragment, and a bearer token in `KUBRICK_TELEMETRY_TOKEN`. The token is not stored or printed and is removed from subprocess environments except for the telemetry adapter.
- Redirects are rejected. Events remain queued unless the collector returns HTTP `202`; telemetry errors do not change the creative command's exit status.
- The current token requirement is a transport configuration gate, not proof of client identity. A distributed CLI cannot protect a shared secret. The [collector design draft](.hermes/plans/2026-10-10-kubrick-telemetry-collector-design.md) recommends anonymous ingestion; it is not implemented or approved for launch.
- Do not configure a collector until its owner approves the authentication or abuse-control model, request limits, provider-side source-IP processing and notice, access, retention/deletion, budget, logging, and incident response. The anonymous design also needs a separate client change to remove the token requirement. This repository does not provision collector or Databricks infrastructure. See `references/telemetry.md` for the current client contract.

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
