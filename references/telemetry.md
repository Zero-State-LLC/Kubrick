# Kubrick telemetry: privacy and operations

Telemetry is optional, default-off, and separate from the local pattern-evolution workflow. Kubrick never uploads prompts, briefs, generated output, file contents, paths, project identifiers, receipts, stdout/stderr, exception text, or free-form feedback. Aggregated events may inform a human-reviewed proposal; they never edit the corpus or raise pattern confidence automatically.

## Consent and commands

Usage and quality feedback are independent scopes. Neither is enabled by default. Disabling one scope removes its queued events; disabling without `--scope` disables both and clears the queue.

```text
kubrick do telemetry --action status
kubrick do telemetry --action enable --scope usage
kubrick do telemetry --action enable --scope quality-feedback
kubrick do telemetry --action preview
kubrick do telemetry --action feedback --pattern-id <known-pattern-id> --vote useful
kubrick do telemetry --action flush
kubrick do telemetry --action disable --scope usage
kubrick do telemetry --action disable
```

`preview` displays only allowlisted queued events. If transmission is not configured or a prior send failed, this lets the operator inspect the remaining local queue before running an explicit `flush`. When an approved endpoint and token are configured, usage events trigger a bounded send attempt at the end of the command; the explicit feedback action also queues its fixed event and attempts a send. Feedback requires a pattern ID in the frozen catalog for the installed Kubrick version and one fixed vote (`useful`, `mixed`, or `not_useful`). Locally added pattern files are excluded. It accepts no free text. Normal usage instrumentation excludes `check` and `telemetry` actions and does not record in CI.

## Event contract

Each event follows `schemas/usage-telemetry-event-v1.schema.json`. The fixed fields are schema version, random event UUID, UTC day, Kubrick version, Python minor version, OS family, event type, manifest-allowlisted intent/action, coarse result/reason code and duration bucket, plus nullable pattern ID and fixed user vote. No stable install, user, or project identifier is generated.

The local outbox is SQLite at the OS per-user state location: Linux `$XDG_STATE_HOME/kubrick/telemetry` (or `~/.local/state/kubrick/telemetry`), macOS `~/Library/Application Support/Kubrick/telemetry`, and Windows `%LOCALAPPDATA%/Kubrick/telemetry`. POSIX directory/database modes are `0700`/`0600`; Windows uses the local profile's ACL. The queue is bounded to 500 events / 1 MiB, with a 4 KiB event limit and 20-event / 32 KiB request limit.

The installed release's feedback allowlist is stored at `references/telemetry-catalogs/<version>.json`; runtime reads only the exact manifest-version file and never scans local pattern JSON files. When previewing or flushing, a queued event that no longer validates against the installed event contract is discarded individually, so it cannot block later valid events. A release that lacks a matching feedback catalog accepts no feedback pattern IDs.

## Network gate

The client sends only when the relevant consent scope is enabled and both `KUBRICK_TELEMETRY_ENDPOINT` and `KUBRICK_TELEMETRY_TOKEN` are configured. The endpoint must be HTTPS without URL credentials, query, or fragment; the token is sent only as a bearer authorization header and is never stored in the outbox or printed. The request uses the fixed `KubrickTelemetry/1` user-agent, not a Python-version header. The parent CLI strips the token from child environments except for the dedicated telemetry adapter. Redirects are rejected. A bounded POST is acknowledged and removed from the local queue only after HTTP `202`; failures leave events queued and do not change the Kubrick command's exit result.

Do not configure transmission until the collector owner has approved the endpoint, bearer-token issuance and rotation, ingestion limits, access controls, retention/deletion policy, and incident response. This client change does not provision a collector, storage, Databricks workspace, or production endpoint. `status` reports only whether endpoint/auth configuration is valid, never their values.

## Collector design status

No production collector, cloud account, bucket, or endpoint is selected or provisioned in this repository. The client above still requires an HTTPS endpoint and `KUBRICK_TELEMETRY_TOKEN`.

The [collector design draft](../.hermes/plans/2026-10-10-kubrick-telemetry-collector-design.md) recommends an anonymous public endpoint for opted-in events. A packaged CLI cannot keep a shared bearer secret private. The proposed service would treat every event as untrusted. This is a design recommendation, not launch approval. It does not change the current client behavior.

The draft recommends direct Cloudflare Worker-to-R2 writes with daily aggregation. It does not add Queues or require Databricks. If an AWS Databricks workspace becomes the primary analytics target, use S3 unless the R2 and Unity Catalog Auto Loader path passes an end-to-end test.

The proposed limit is 500 accepted batches per UTC day, with at most 20 events and 32 KiB per request. This is not a billing cap. The service would need edge throttling, billing alerts, and an emergency disable control. The draft proposes 30-day raw retention and 13-month aggregate retention. A queued event may remain in raw storage for about 62 days from its event day, and lifecycle deletion is not exact-time.

The proposed 30-day acceptance window and storage-retention periods apply to a future collector; they do not describe current client queue expiry. The local client outbox has count and size bounds but currently no age-based expiry, so valid pending events can be retried indefinitely while consent remains enabled and delivery stays configured. Contract-incompatible entries are discarded individually when the queue is read.

Before enabling an endpoint, the owner must approve the account and jurisdiction, abuse controls, provider-side source-IP processing and notice, budget, retention, access, logging, and incident response. The client also needs a separate change to remove its bearer-token requirement. Feedback IDs must come from the catalog shipped with the reported Kubrick version, not locally added patterns.
