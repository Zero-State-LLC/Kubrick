# Kubrick telemetry collector and analytics design

**Status:** Draft design. Not approved for implementation or deployment.
**Date:** 2026-10-10
**Scope:** Collector and batch analytics only. No code, cloud resources, endpoint, upload, or deployment is authorized by this document.

## Goal

Receive consented Kubrick telemetry, validate it, retain it for a bounded period, and produce aggregate usage and quality signals for human review. Keep event contents separate from Kubrick prompts, outputs, project data, and local pattern-evolution receipts.

## Non-goals

- Do not provision a collector, storage account, queue, Databricks workspace, or endpoint.
- Recommend a design and pilot limits, but do not select a production account, jurisdiction, endpoint, owner, or billing authorization without the relevant owner.
- Do not collect prompts, generated text, files, paths, project or account identifiers, free text, exception text, or stable installation identifiers.
- Do not report unique users, user cohorts, or per-user behavior.
- Do not train a model or automatically change Kubrick patterns, pattern confidence, or corpus content.

## Existing client contract

These details were checked in `src/kubrick/runtime/telemetry.py`, `src/kubrick/runtime/telemetry_store.py`, `src/kubrick/runtime/telemetry_cli.py`, `schemas/usage-telemetry-event-v1.schema.json`, and `references/telemetry.md`.

- The client sends `POST` with `Content-Type: application/json`, a bearer token, and the fixed `KubrickTelemetry/1` user agent.
- The request body is `{"schema_version":"1","events":[...]}`. Each event also has its own `schema_version` field.
- A batch has at most 20 events and 32 KiB. An event is limited to 4 KiB. The client timeout is 0.5 seconds.
- The event schema rejects unknown fields. Events carry a random UUIDv4, UTC day, Kubrick version, Python minor version, OS family, allowlisted intent and action, coarse result and reason, duration bucket, and nullable pattern ID and fixed vote.
- The client accepts only HTTP `202` as acknowledgment. It rejects redirects and retains events on every other response or network failure. It removes the batch after `202`.
- Usage and quality-feedback consent are separate and default off. Revoking a scope clears its queued events. No event is queued or sent without consent and valid endpoint and token configuration.
- The client does not currently report a maximum queue age. A queued event can be retried after an arbitrary delay unless the client adds an expiry rule.
- `_pattern_ids()` loads IDs from `references/patterns/**/*.json` in the installed skill tree. That may include locally added pattern files. The current check proves that an ID exists in that tree, not that Kubrick shipped it.

The accepted intent limits this phase to a design. This research resolves technical defaults but cannot establish private account ownership, user geography, legal approval, or spending authority.

## Research findings and design decisions

Research used official IETF, Cloudflare, and Databricks documentation retrieved on 2026-10-10. The source titles and the claims they support appear below.

### Decisions for the design

1. **Use a Cloudflare Worker with direct R2 batch writes and a daily Cron aggregation as the conditional default, if the owner approves an isolated Kubrick account or project.** Keep the collector in a separate backend repository. Do not add Queues to v1: direct R2 writes give `202` a simple durable-acceptance meaning, while a queue would add consumer recovery and replay policy.

   R2 documents synchronous durable writes and strong consistency.[2][3]

   Queues are at-least-once and unordered.[12] Generate a fresh random object key for each POST; R2 permits at most one concurrent write to a key per second, and higher rates return `429`, so a lost-response retry must not overwrite the original key.[16]

2. **Do not create a Databricks workspace just for the first low-volume pilot.** No workspace is selected. If Databricks is the primary analytics environment on AWS, prefer S3 as the lower-ambiguity native Auto Loader source unless R2 is validated in the target workspace.

   Databricks documents R2 external locations in Unity Catalog.[15] Auto Loader supports Unity Catalog volumes.[14][17]

   Test the R2 volume with Auto Loader in directory-listing mode first; do not assume R2 file-notification support.[18]
3. **Use public anonymous ingestion for opted-in telemetry; do not require or embed a client bearer secret.** RFC 8252 says a secret distributed with a native app is not confidential and cannot prove the app's identity.[1] This best fits the no-account/no-stable-user-or-install-ID constraint, but makes the endpoint abuse-exposed. Require strict validation, edge request throttling, an accepted-data ceiling, billing alerts, and an emergency disable switch; never persist source IPs in Kubrick analytics or application logs. The owner must approve provider-side network-metadata processing and the abuse posture before any endpoint is enabled. If that risk is unacceptable, stop rather than substituting a shared cohort token.
4. **Set an initial ceiling of 500 accepted batches per UTC day, with at most 20 events and 32 KiB per request.** Separately throttle all incoming requests at the edge. This is an ingestion limit, not a billing ceiling: public invalid or abusive requests can still invoke the Worker. The maximum accepted payload is 16,384,000 bytes per day, or 468.75 MiB over 30 days, before aggregates. Return `429` after the accepted-data ceiling and keep events queued locally.
5. **Expire the local outbox when `event_day` is more than 30 calendar days old; reject older events. Retain raw objects for 30 days from receipt and aggregates for 13 months.** These are engineering defaults, not legal conclusions. Keep only event-ID digests until 60 days after `event_day`. R2 lifecycle objects are typically deleted within 24 hours after expiry, but this is not an exact-time deletion guarantee and lifecycle-rule changes can take longer.[4] Since the client reports a UTC day, raw data may ordinarily remain for about 62 days from event occurrence; do not present that as a guaranteed maximum.
6. **Suppress aggregate cells with fewer than 20 events.** Treat this as a small-cell safeguard, not anonymization. Do not report unique users or cohorts.
7. **Allow feedback only for pattern IDs shipped in the reported Kubrick version.** The current `_pattern_ids()` scan reads every local JSON file under `references/patterns/`; that is not a shipped-catalog check. The client must switch to a release-owned catalog before any endpoint is enabled.
8. **Keep the client's 0.5-second timeout as its command-wait budget.** Add `Retry-After` handling and jittered exponential backoff, capped at one attempt per eligible invocation and a six-hour maximum delay. Each POST writes a new uniquely named raw batch object; if a `202` is lost, the retry can create a duplicate raw batch, but downstream event-ID deduplication must prevent duplicate analytical events. Do not overwrite a content-derived key because R2 limits concurrent writes to the same key.[16]
9. **Disable persisted request logging for the telemetry service.** Set `observability.enabled = false` and `observability.logs.invocation_logs = false`. Do not enable Traces, Issues, Logpush, or R2 Data Access Logs. Do not put request bodies, tokens, event IDs, or exception payloads in logs. Verify the deployed configuration rather than relying on defaults.

### Evidence and constraints

- RFC 8252, section 8.5, says not to treat a shared secret distributed with a native app as confidential or as proof of app identity.[1]
- Cloudflare R2 documents synchronous writes and strong consistency.[2][3] It permits one concurrent write per object key, so request retries must use unique keys and deduplicate by event ID downstream.[16]
  Its lifecycle documentation says deletion usually completes within 24 hours after expiration, while lifecycle changes for existing objects can take longer.[4] R2 bucket jurisdiction cannot be changed after creation.[5]
- Cloudflare Workers documents UTC Cron Triggers.[8] Its current limits list 50 subrequests per invocation on the Free plan and 10,000 on Paid.[9] The Paid plan has a $5 monthly minimum.[10]
- R2's published free allowance includes 10 GB-months of storage, 1 million Class A operations, and 10 million Class B operations.[11] At the proposed accepted-data ceiling, up to 500 raw object writes per day and the corresponding daily reads are within those R2 allowances if the account has no unrelated usage. Public rejected traffic can still incur Worker costs; this estimate is not a billing cap. The $5 Worker Paid base, other account usage, edge abuse controls, and billing alerts still need owner approval.
- Cloudflare's Wrangler configuration says persisted Worker logs default to enabled for new Workers.[6]
  Invocation logs include request, response, and related metadata. Set `observability.enabled = false` and `observability.logs.invocation_logs = false` explicitly.[6][7]
  Workers Logs retention is 3 days on Free and 7 days on Paid.[7] Cloudflare's Observability pricing changes on December 1, 2026.[13]
- Databricks Auto Loader lists Amazon S3, ADLS, GCS, Unity Catalog volumes, and Azure Blob Storage; R2 is not named as a direct native source.[14]
- Databricks separately documents R2 external locations in Unity Catalog.[15]
- Auto Loader supports Unity Catalog volumes, and its directory-listing mode is documented for this source type.[17][18] This makes an R2-backed volume plausible, but validate the exact combination in the approved workspace and do not assume R2 file notifications are supported.
- File-name searches found no files with `wrangler`, `cloudflare`, `databricks`, or `supabase` in their names, and no `.github/workflows` filename containing `deploy`. This does not rule out other deployment configurations or private accounts.

Sources are listed at the end of this plan. Supplemental sources retrieved October 11, 2026.

## Recommended architecture

1. Kubrick posts a bounded batch to a public Cloudflare Worker endpoint only after local opt-in. The Worker treats every caller as untrusted and validates the entire envelope and every event before writing anything; it does not authenticate a client identity.
2. The Worker writes the complete batch to a dedicated, private R2 bucket using a fresh random object key for each POST, then returns `202` only after the R2 write succeeds. It does not wait for analytics processing. A lost response followed by retry can create another raw object; downstream event-ID deduplication prevents double counting.
3. A daily UTC Cron Trigger processes bounded R2 batches, deduplicates by `event_id`, checks the data-quality gates, and writes aggregate outputs. A cursor or checkpoint must make job retries idempotent and keep each invocation within the selected Workers plan limits.
4. Edge throttling limits all inbound POST traffic; a separate daily accepted-batch ceiling rejects further valid batches with `429`. These controls reduce abuse but do not establish a hard billing ceiling. Require account billing alerts and an emergency disable switch.
5. Set `observability.enabled = false` and `observability.logs.invocation_logs = false`. Do not enable Traces, Issues, Logpush, or R2 Data Access Logs. Use only aggregate service metrics that do not contain event or request identifiers. Verify these settings in the deployed Worker and bucket.
6. Reviewers use aggregate outputs to decide whether to propose Kubrick changes. No service writes to Kubrick's corpus.

Do not create this Worker or bucket until the owner confirms an isolated Cloudflare account or project, jurisdiction, service owner, budget, public anonymous-ingestion abuse posture, source-IP handling/notice, edge throttling, billing alerts, and emergency shutdown. A separate product's Cloudflare account is not automatically approved for Kubrick data. Databricks is optional, not a v1 requirement. If an approved workspace already exists, test the R2-backed Unity Catalog volume in the target runtime and grant Databricks read-only access to the required prefix.

## Proposed HTTP contract

The route below is a design proposal, not a selected production URL.

| Operation | Caller | Request | Success |
| --- | --- | --- | --- |
| `POST /v1/telemetry/events` | Any untrusted caller; Kubrick CLI sends only after local opt-in | Current version-1 envelope and events over HTTPS; no client credential | `202 Accepted` only after the entire batch is durably recorded |

Use the event schema in `schemas/usage-telemetry-event-v1.schema.json` as the authority for event fields. Add one versioned batch-envelope schema before implementation. It must define the outer `schema_version`, event count, and byte limit without duplicating or redefining event fields.

The collector must validate the entire request before writing. It must enforce 20 events and 32 KiB maximum request size, reject unknown event fields, validate real calendar dates and UUIDv4 values, and enforce the fixed enums and formats. Do not accept partial batches. A successful response may be `{"status":"accepted"}`. The client branches on status and does not need event IDs or a reflected request body in the response.

Use one error envelope for all failures: `{"error":{"code":"...","message":"...","retryable":false}}`. Do not include submitted values, credentials, event bodies, or internal storage details in the response.

| Failure | Status and stable code | Retry behavior |
| --- | --- | --- |
| Invalid JSON, envelope, event, or unsupported version | `400 INVALID_BATCH` | Permanent until the client or queued event changes |
| Request exceeds limits | `413 BATCH_TOO_LARGE` | Permanent for that batch |
| Event day exceeds the 30-calendar-day acceptance window | `410 EVENT_EXPIRED` | Permanent; offer explicit discard |
| Conflicting reuse of an event ID with different content | `409 EVENT_ID_CONFLICT` | Permanent; quarantine for review |
| Rate limit | `429 RATE_LIMITED`, with `Retry-After` | Retry after the indicated delay |
| Durable storage or service failure | `503 UNAVAILABLE` | Retry with bounded backoff |

The client currently treats every non-`202` result as a generic failure and retains the batch. Before production, it needs a safe path for permanent `4xx` responses so one invalid event cannot be retried forever. Keep the event queued until the user can inspect a safe error code and explicitly retry or discard it. The client should also honor `Retry-After` and add bounded retry backoff. These are client follow-up changes, not part of this design-only task.

Keep the 0.5-second client timeout as the command-wait limit. Measure acknowledgment latency in the pilot. Do not increase the client timeout without a separately reviewed client change. If the server records a batch but the response is lost, a retry may create another raw object but must not create a second curated event.

## Trust and authorization boundary

| Path | Caller trust | Authentication | Authorization |
| --- | --- | --- | --- |
| `POST /v1/telemetry/events` | Public, untrusted caller | HTTPS; no client authentication | May submit only bounded version-1 telemetry batches; no read, query, admin, or corpus-write permission |
| Daily ingestion job | Internal service identity | Hosting platform service identity | May read the telemetry landing area and write curated and aggregate tables only |
| Aggregate dashboards | Named analyst or maintainer role | Organization identity provider | Read aggregate views only; no access to credentials or request bodies |
| Abuse controls and retention administration | Named service owner | Organization identity provider with least privilege | Configure edge throttling, accepted-data limits, emergency disable, and retention |

The current client requires `KUBRICK_TELEMETRY_TOKEN`, so it is not yet compatible with this recommendation. A separate client change must remove that requirement before any endpoint is enabled; do not replace it with a shared cohort token, which is extractable and does not prove caller identity.[1] Local opt-in is not verifiable by the public service. Treat submitted events as spoofable, noisy input and never use them for automatic corpus changes. If the product later requires account-linked attribution or a managed roster, that is a scope change requiring an explicit identity and deletion design.

## Storage and duplicate handling

- Write each validated batch as one durable unit under a fresh random object key per POST. Return `202` only after the write confirms. A storage failure returns a retryable error and leaves the client's queue intact. Repeated POSTs may create duplicate raw objects; unique event IDs and idempotent curated merges prevent duplicate counts.
- Give `event_id` a unique constraint in curated storage. Use an idempotent merge keyed by `event_id`. Repeated delivery of the same event must not change aggregate counts.
- If the same event ID arrives with a different canonical payload hash, quarantine the conflicting batch and report a bounded operational error. Never overwrite the first accepted event silently.
- Expire local events when `event_day` is more than 30 calendar days old. Reject events outside that window with `410 EVENT_EXPIRED`. Retain raw objects for 30 days from durable acceptance, then delete them. R2 lifecycle deletion is typically within 24 additional hours under an unchanged policy, but is not an exact-time guarantee; rule changes can take longer.[4] Retain only an event-ID digest until 60 days after `event_day`.
- Store event data and server ingestion time only. Do not persist authorization headers, request bodies in web logs, client IP addresses, hostnames, or raw network metadata in analytics tables.
- Restrict access to the raw landing area to the collector and ingestion job. Give analysts access to aggregate views, not raw events.

## Batch analytics and quality gates

Run a bounded daily UTC Worker job. Use an idempotent merge keyed by `event_id`; repeated job runs must produce the same aggregate output. Defer Databricks from v1.

Publish aggregates for:

- Usage counts by event day, Kubrick version, Python minor, platform, intent, action, result, reason code, and duration bucket.
- Feedback counts by approved pattern ID, Kubrick version, vote, and event day.

Do not calculate unique users or retention. Do not join telemetry to accounts, projects, donation data, local receipts, or unrelated service logs. Suppress every aggregate cell with fewer than 20 events. The privacy owner must approve the threshold and dimensions before launch. A threshold of 20 is not anonymization.

Stop a batch before publishing if any event fails schema validation, a duplicate key has conflicting content, required fields are null, prohibited fields appear, the deduplication check fails, or counts fall outside an owner-approved range. Record pipeline run ID, source batch IDs, row counts, duplicate counts, and gate outcomes without copying event bodies into run logs. Rerunning the same source batches must not change curated event counts or aggregates.

## Privacy, retention, and operations

Treat event records as pseudonymous operational data, not anonymous data. The absence of a user or install ID does not prevent an event's timestamp, version, platform, action, or pattern ID from being identifying in a small population.

Do not persist request bodies, client credentials, or caller IP addresses in gateway or application logs. Edge throttling may transiently process source IPs; disclose and approve that provider-side processing, and do not retain the IP in Kubrick storage. If the selected host cannot meet this boundary, its logging and retention behavior is a blocker. Keep abuse metrics separate from event bodies and approve their retention.

Cloudflare's Worker invocation logs include request, response, and related metadata. New Workers default to enabled observability. Disable persisted request logs and traces explicitly. The provider still processes network metadata to deliver HTTP requests. Name that processing in the consent notice and verify the selected account's logging configuration before launch. If the account cannot keep request-level logs disabled, do not use it for this service.

Use 30 days from durable acceptance for raw objects and 13 months for aggregates as the design defaults. Obtain a named data owner's approval for these periods, deletion, backups, incident response, access reviews, and spend limits. Under a stable lifecycle policy, raw-object deletion is typically within 24 hours after expiry; policy changes or operational delays can extend that.[4] A client may queue an event for up to 30 calendar days before upload, so the raw-data window is ordinarily about 62 days from event time, not a guaranteed maximum. Because the client sends no stable user identifier and removes accepted events from its local queue, the service cannot delete one user's historical events on request. Disclose both limits before enabling consent. If per-user deletion is required, stop and design a separate identity and deletion protocol.

Provide operational alerts for rejection rates, edge-throttle hits, accepted-data ceiling, storage errors, batch latency, schema-version changes, and spend. The runbook must cover abuse response, emergency shutdown, storage outage, invalid-batch quarantine, schema changes, and data deletion. Set request, accepted-event, storage, and monthly cost controls before deployment.

## Remaining gates before implementation

1. Which organization-owned Cloudflare account or project can host an isolated Kubrick service, and who owns the separate backend repository?
2. Which R2 jurisdiction is required? Choose it before creating a bucket because the jurisdiction cannot be changed later.
3. Does the owner accept public anonymous ingestion, its spoofable data, and provider-side source-IP processing for edge abuse controls? What throttling, billing alerts, and emergency shutdown are required?
4. Who approves the 30-day raw retention, 13-month aggregate retention, 20-event suppression threshold, deletion limits, and consent notice?
5. What monthly budget and billing controls are approved? Public prices cannot establish account-level usage or a hard billing ceiling.
6. Can the owner verify that Worker logs and invocation logs are off, and that Traces, Issues, Logpush, and R2 Data Access Logs are not enabled? Recheck log pricing before launch because Cloudflare changes its Observability pricing on December 1, 2026.
7. Who owns incident response, access review, and production approval?

Databricks workspace selection is not a v1 gate because the pilot can aggregate in a scheduled Worker. If the owner confirms an existing workspace, test the documented R2 external-location and Auto Loader Unity Catalog path in that workspace; if Databricks on AWS is the primary analytics target, compare against native S3 before selecting R2.

Do not build or deploy the collector until these decisions are recorded and the user separately authorizes execution.

## Acceptance criteria for a later implementation

- A versioned envelope contract refers to the existing event schema as the event-field authority.
- The API validates whole batches and returns `202` only after durable acceptance; no partial acknowledgment occurs.
- Repeated delivery and repeated pipeline runs do not change curated counts. Conflicting event-ID reuse is quarantined.
- Credentials, event bodies, caller IPs, prompts, outputs, paths, project identifiers, and user identifiers do not enter persistent access logs or analytics tables.
- Unknown or locally added pattern IDs cannot leave the client. Only IDs from an owner-approved Kubrick-shipped catalog can appear in feedback events.
- Permanent client rejections do not cause endless retries or silent data loss. Retry timing stays bounded.
- Retention, deletion limits, access controls, budget limits, incident response, and privacy notice have named owners and approval before a production endpoint is enabled.
- Aggregate output informs human review only and cannot write to the Kubrick corpus.

## Verification plan for a later implementation

- Contract tests cover valid v1 batches, unknown fields, invalid dates, unsupported versions, oversized batches, and mixed-validity batches. Abuse tests cover anonymous malformed floods, throttling, accepted-data caps, and emergency disable.
- Ingestion integration tests prove that storage failure never returns `202`, and that a lost response followed by a retry produces one curated event.
- Pipeline tests replay the same batch twice, check event-ID uniqueness, exercise conflicting event IDs, and verify every quality gate blocks publication.
- Log and storage scans prove that headers, request bodies, IP addresses, and prohibited content are absent from persistent records.
- A staging load test verifies the client timeout and request limits. A retry test verifies rate limits and service failures do not lose events or cause unbounded requests.
- An access-control test proves that analyst roles can read aggregates but cannot read raw events or credentials.

## Review focus

1. A locally added pattern ID must be rejected before transmission. The telemetry-client task owns this test.
2. A timed-out request retried with the same event IDs must not double-count. The collector and pipeline task own this test.
3. A batch with one invalid event must not partially persist or return `202`. The collector task owns this test.
4. A permanent `4xx` response must not create an endless retry loop or silently discard queued events. The telemetry-client task owns this test.
5. Anonymous submissions must remain bounded under spoofing and abuse; reject noisy signals from publication and do not add client identity. The service-owner and security-review task own this gate.

## Constitution and scope check

Checked against `SECURITY.md`, `references/telemetry.md`, and the accepted intent in `intent/2026-10-10-kubrick-usage-telemetry/intent.md`.

- The design preserves opt-in consent, strict event allowlisting, no stable user or installation ID, and human review before any corpus change.
- The design does not expand the narrow per-user local-state exception. The collector stores no Kubrick client state in project files.
- The design follows the security rule that no collector is configured until its owner approves the anonymous-ingestion abuse posture, limits, access, retention and deletion, and incident response.
- No conflict with the stated security constraints was found. The hosting stack and the approval owners remain unresolved.

**Handoff:** Not prepared. The design recommends a separate Cloudflare Worker and R2 service, but no backend repository, approved account, jurisdiction, budget, or service owner is confirmed. This document is a draft design, not implementation or deployment evidence.

## Sources

[1] https://www.rfc-editor.org/rfc/rfc8252: IETF RFC 8252, OAuth 2.0 for Native Apps
[2] https://developers.cloudflare.com/r2/reference/durability: Cloudflare R2, Durability
[3] https://developers.cloudflare.com/r2/reference/consistency: Cloudflare R2, Consistency model
[4] https://developers.cloudflare.com/r2/buckets/object-lifecycles: Cloudflare R2, Object lifecycles
[5] https://developers.cloudflare.com/r2/reference/data-location: Cloudflare R2, Data location
[6] https://developers.cloudflare.com/workers/wrangler/configuration: Cloudflare Workers, Wrangler observability configuration
[7] https://developers.cloudflare.com/workers/observability/logs: Cloudflare Workers, Logs
[8] https://developers.cloudflare.com/workers/configuration/cron-triggers: Cloudflare Workers, Cron Triggers
[9] https://developers.cloudflare.com/workers/platform/limits: Cloudflare Workers, Limits
[10] https://developers.cloudflare.com/workers/platform/pricing: Cloudflare Workers, Pricing
[11] https://developers.cloudflare.com/r2/pricing: Cloudflare R2, Pricing
[12] https://developers.cloudflare.com/queues/reference/delivery-guarantees: Cloudflare Queues, Delivery guarantees
[13] https://developers.cloudflare.com/workers/observability/pricing: Cloudflare Workers, Observability pricing
[14] https://docs.databricks.com/aws/en/ingestion/cloud-object-storage/auto-loader: Databricks, What is Auto Loader?
[15] https://docs.databricks.com/aws/en/connect/unity-catalog/cloud-storage/external-locations-r2: Databricks, Connect to a Cloudflare R2 external location
[16] https://developers.cloudflare.com/r2/platform/limits/: Cloudflare R2, Limits
[17] https://docs.databricks.com/aws/en/ingestion/cloud-object-storage/auto-loader/unity-catalog: Databricks, Auto Loader with Unity Catalog
[18] https://docs.databricks.com/aws/en/ingestion/cloud-object-storage/auto-loader/file-detection-modes: Databricks, Compare Auto Loader file detection modes
