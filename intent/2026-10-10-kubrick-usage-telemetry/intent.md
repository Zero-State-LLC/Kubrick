# Intent

Status: Accepted by the user in chat on 2026-10-10 after reviewing the telemetry plan ("okay continue"). Acceptance covers the Kubrick-side, opt-in client and event contract only. Collector provisioning, Databricks workspace changes, production endpoint selection, data upload, and deployment remain gated on explicit infrastructure details and authorization.

## Problem

Kubrick currently has no opt-in usage telemetry. Its local pattern-outcome receipts include project identifiers, source receipt paths, and optional free-text notes, so uploading those receipts would expose more user/project data than needed. Maintainers lack aggregated evidence about command outcomes, failure reasons, latency, and explicitly rated pattern usefulness.

## Proposed outcome

Add a versioned, strict allowlist event contract; Kubrick-side consent controls that are disabled by default; a bounded local event queue; best-effort HTTPS flushing only when the user opted in and an approved HTTPS endpoint plus bearer credential are configured; and coarse usage events at the actual CLI dispatch boundary. Keep usage and quality-feedback consent separate. Never include prompts, briefs, outputs, files, project IDs, paths, free text, exception text, credentials, or provider payloads in event data. The separately configured bearer token may appear only in the HTTPS Authorization header; never store or print it. Do not send a stable user/install identifier. Add user-facing documentation and regenerate the packaging mirror. A missing/unapproved endpoint or credential means no upload; it does not block ordinary Kubrick use.

A future, separately authorized backend may validate and batch the event contract into cloud object storage. Databricks is optional and is not required for a first pilot. The backend remains outside this accepted implementation scope until the owner approves the account, jurisdiction, service owner, retention, abuse controls, and spend limits. Aggregate metrics must inform human-reviewed proposals only; no automatic corpus or confidence mutation.

## Affected users / systems

- Kubrick CLI users and maintainers.
- `src/kubrick/cli.py`, telemetry runtime/client, manifest routing, tests, `SECURITY.md`, `SKILL.md`, and user/operator docs.
- Generated `skills/kubrick/` mirror and existing CI/validation gates.
- A future separate collector/Databricks project, not modified or deployed in this scope.

## Constraints / non-goals

- Core creative behavior remains offline; telemetry is opt-in, uses standard-library transport only, and cannot change the command’s exit status or output.
- Keep the root repository canonical and regenerate the Hub mirror with `bash scripts/sync_hub_skill.sh`; never hand-edit `skills/kubrick/`.
- Explicitly extend `SECURITY.md` only to permit Kubrick’s owner-only telemetry-consent/outbox directory in the platform user-state location. Keep all other writes inside the project root or skill `out/`; do not write telemetry state into `references/`, `schemas/`, or the skill payload.
- Only allowlisted fields and stable categorical codes may cross the network boundary. No raw receipts, prompts, user content, project paths/IDs, host/user names, or exception text.
- No stable installation identifier, account linkage, advertising, model training, paid service, account creation, production data, deploy/pin workflow, official Hub submission, external publication, push, or merge.
- `SKILL.md` edits are limited to documenting new opt-in commands/defaults and the data boundary; do not rewrite unrelated runtime behavior.
- Do not change corpus contents, pattern confidence, or proposal authority. Telemetry is evidence for human decisions only.

## Open questions

- Does the owner approve the design draft's isolated Cloudflare Worker and R2 recommendation, its jurisdiction, and its anonymous-ingestion abuse controls? If Databricks on AWS is the primary analytics target, compare native S3 or validate the R2 and Unity Catalog Auto Loader path before selecting storage.
- Is there an existing Databricks workspace and a named cost/data owner? If not, keep the client’s provider-neutral event contract and do not provision Databricks.
- What retention and privacy notice are approved for the eventual backend? The plan’s 30-day raw / 13-month aggregate periods are proposals, not approvals.
- V1 deliberately cannot report unique active users, retention, or cohorts. A stable pseudonymous identifier would require a separate intent and a deletion/reset design.

The [collector design draft](../../.hermes/plans/2026-10-10-kubrick-telemetry-collector-design.md) records the conditional Worker/R2 recommendation, anonymous-ingestion tradeoffs, proposed limits and retention, and owner-dependent launch gates. It does not expand the accepted client scope or authorize provisioning, endpoint selection, uploads, or deployment. The current client still requires a bearer token; it needs a separate change before it can send to the proposed anonymous endpoint.

## Verified / assumed claims

| Claim | Label | Basis |
|---|---|---|
| The current Kubrick checkout has no telemetry-named files. | `OBSERVED` | `search_files` for `*telemetry*` in the repository returned 0 files. |
| The local security policy currently permits writes only inside the project root or skill `out/`; the client state directory therefore needs an explicit narrow policy exception or a different path. | `OBSERVED` | `SECURITY.md:16-21`. The accepted design permits only the narrowly scoped owner-only telemetry state path. |
| `scripts/kubrick.py` is a thin shim and actual dispatch lives in `src/kubrick/cli.py`. | `OBSERVED` | Read `scripts/kubrick.py:1-32` and `src/kubrick/cli.py:245-270`. |
| Existing `learn outcome` receipts contain `project_id`, `source_compile_receipt`, optional notes, and proposal-only authority. | `OBSERVED` | `scripts/record_pattern_outcome.py` and `scripts/propose_pattern_evolution.py` source context. |
| Aggregate usage events and explicitly submitted categorical feedback can help prioritize fixes without uploading creative content. | `INFERRED` | Proposed event schema and the current local proposal-only evolution workflow. |
| No collector or Databricks workspace/endpoint has been selected for Kubrick. | `NOT_COMPUTABLE` | No such configuration was present in the inspected checkout; external account/workspace state has not been inspected or authorized. |

## Author / date

- Author: Hermes Agent
- Date: 2026-10-10
