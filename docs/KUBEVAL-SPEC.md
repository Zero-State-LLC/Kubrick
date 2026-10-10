# KUBEVAL-001: Automated, Cost-Constrained Model Evaluation

Status: **PROPOSED SPECIFICATION**, not implemented. Intent: [2026-10-10-kubeval-001](../intent/2026-10-10-kubeval-001.md). Product baseline: **Kubrick v0.27.14**. Owner approval remains required for spend, canonical promotion, and production policy changes.

## 1. Mission and scope

KUBEVAL selects the cheapest *qualified* model/provider route for each Kubrick evaluation or generative task, optimizing **cost and time to an accepted result** under non-negotiable quality and safety limits. It uses OpenRouter as a changing candidate marketplace, not as ground truth or the sole production selector. Its primary operating modes are `smoke` (offline, 5-10 cases), `optimize` (budgeted experiments), and `qualify` (held-out release assessment). No live API call is required in CI.

Goals: fully automated cheap benchmarking, paired A/B and ablation comparisons, per-task models, targeted escalation, reproducible receipts, low overhead, and bounded spend. Non-goals: guaranteeing perfection, treating a single VLM opinion as truth, adding a new hosted service, silently changing Kubrick canon, or generating paid videos by default.

## 2. Domain model and ubiquitous language

- **Task**: declared evaluation workload (`prompt_lint`, `hold_judge`, `board_vision`, `identity`, `take_qc`, `narrative`, `prompt_compilation`, `generation`). Task determines modalities, policy and rubric.
- **Case**: immutable brief, expected constraints, rights/privacy label, asset hashes, labeled ground truth and scene/project lineage.
- **Candidate route**: exact model ID, provider policy, endpoint/modalities, prompt/judge revision, decoding settings and price snapshot.
- **Champion**: currently qualified route for a task and cohort, distinct from the OpenRouter default router.
- **Challenger**: eligible but not yet promoted route.
- **Attempt**: one dispatch, elapsed time, token usage, actual cost, output hashes and result classification.
- **Acceptance**: satisfaction of a frozen rubric plus all hard constraints. A missing verification is `NOT_COMPUTABLE`, never an acceptance.
- **Experiment**: frozen paired cases, candidate routes, comparison design, budget and randomization seed.
- **Qualification**: statistically supported, reproducible evidence allowing a proposed promotion. Qualification does not grant authority to publish or spend.

## 3. Existing architecture integration

Reuse `tools/board_calibration/`, `evals/calibration/board-image-ep01/`, `src/kubrick/qc/`, `src/kubrick/gates/`, existing receipts and provider adapter patterns. Proposed `tools/kubeval/` (catalog, planner, runner, score, compare, report, storage); proposed `evals/benchmarks/` and `evals/protocols/`; proposed SQLite under ignored `out/kubeval/`. Do not create `KUBEVAL` as an autonomous authority. Root remains source of truth; no new skill route or `SKILL.md` change until separately accepted and tested.

## 4. Workflow

1. **DISCOVER**: poll OpenRouter catalog on a bounded TTL; normalize advertised model IDs, modality support, context, parameters, price units and availability. Store catalog snapshot plus retrieval timestamp; unknown pricing = ineligible for paid dispatch.
2. **FILTER**: require the task's image/text/tool/structured-output support; enforce provider data-use and zero-retention rules where required, provider allowlist, max expected price and locality/privacy classification. Providers cannot be silently substituted across controlled arms.
3. **PLAN**: choose eligible champion plus 1-3 challengers, block duplicates, stratify cases by independent project, character and defect family, freeze prompts/rubrics and randomized A/B order. Start with champion/challenger; introduce contextual bandits only after sufficient data, calibrated uncertainty and conservative exploration.
4. **RUN**: prefer free deterministic validations; reuse recorded image and judgment evidence; invoke remote model only when allowed by manifest and budget. Save each attempt atomically to SQLite and receipt JSON. Respect bounded concurrency, retries, timeouts and per-request maxima; do not retry a deterministic quality failure unchanged.
5. **EVALUATE**: machine checks first. Labeled cases score recall, specificity, false blocks, false passes, calibration, abstention and severity; creative cases use independent blinded pairwise human labels and an empirically calibrated secondary judge. An independent judge may not evaluate itself as authoritative ground truth.
6. **ESCALATE**: send only relevant hashed crop/frame/question to a stronger qualified judge when cheaper evidence is unresolved. Critical uncertain cases stay `NOT_COMPUTABLE` pending human review; a cheaper model cannot erase a known hard lock hit.
7. **COMPARE**: compute quality first, then conditional cost and latency. Estimate accepted-result cost from actual attempts, including failed and repeated calls, not just list prices.
8. **QUALIFY**: on untouched split, test hard-block regression, category-specific lower confidence bounds, blinded human preference, cost, p50/p95 time to acceptance and robustness. A promotion proposal is generated only if all hard gates pass.
9. **MONITOR**: benchmark champion periodically and on meaningful model/provider or code changes. Detect drift or price increases, invalidate stale snapshots, revert to last qualified route where policy permits, otherwise fail closed.

State machine: `DISCOVERED -> ELIGIBLE -> EXPERIMENTAL -> VALIDATED -> QUALIFIED -> PROPOSED_FOR_PROMOTION -> APPROVED_ACTIVE`; `INELIGIBLE`, `REJECTED`, `STALE`, `NOT_COMPUTABLE` terminate or suspend. Only an authorized operator can perform `PROPOSED_FOR_PROMOTION -> APPROVED_ACTIVE`.

## 5. Experimental design

- **Offline A/B first**: same frozen inputs and labels, different model/prompt/route; pair observations, randomize order and track exact provider.
- **Ablation**: compare unaided model to model + Kubrick; compare grammar, compiler, reference packs, board gate, judge, and retake router in isolation. Keep all other variables unchanged.
- **Live production**: opt-in only; hold generator, decoding policy, initial image, budget and acceptance rubric constant wherever possible. Compare seeded attempts only where seed is supported; otherwise repeat and account for randomness. Image and video spend require separate owner authorization.
- **Dataset**: initial target 120 development, 60 validation, 60 sealed holdout, 40 adversarial. These are *proposed targets*, not existing labeled data. Group splits by project, character and shot lineage; detect duplicates/perceptual near-duplicates across groups.
- **Current EP-01**: development/regression only; never treat tuned EP-01 wording as independent test of 0.27.0. Gather a new labeled, genuinely held-out, multi-project set before qualification.
- **Subjective evaluation**: blinded pairwise preference with ties/neither, justification and multi-rater agreement; Bradley-Terry summaries where appropriate. Never replace independent labels with the candidate judge's self-rating.
- **Statistics**: paired, project-clustered bootstrap intervals; category-specific confusion matrices and confidence limits; declare minimally important effects and sample thresholds in protocol *before* qualification. Seven known defects cannot verify near-perfect recall.
- **Repeated tuning**: validation can guide candidates; do not repeatedly peek at sealed holdout. Once exposed for candidate tuning, retire/reclassify it and seal new examples.

## 6. Metrics and hard policy

Primary lexicographic rule: **hard constraints first**, then expected cost and time to an accepted result. Never trade a critical canon/identity/safety failure for a lower mean quality score. Per-task quality floors and severity taxonomy are in frozen protocol, not guessed by dynamic model.

Measure (a) per-category recall/specificity, false blocks, false passes and abstention; (b) quality rubric and pairwise preference; (c) accepted results / attempts; (d) total billed and estimated cost, `total_attempt_spend / accepted_count` with a zero-acceptance explicit undefined state; (e) wall-clock time to first acceptance including escalation and retries, p50/p95; (f) human intervention rate; (g) provider/model stability; (h) bytes/images leaving trust boundary.

Avoid ratio-of-means confusion. Aggregate spend across all attempts (including failed attempts) divided by accepted results and report uncertainty and per-cohort distribution. Display spend and time as separate Pareto axes; only score quality-eligible routes. Track high-severity miss counts and uncertainty explicitly.

## 7. Routing and escalation policy

Tier 0: deterministic Python, schema, hashes, static locks and geometries; no API spend.
Tier 1: cached approved local judge or cheapest qualified OpenRouter route for routine labeled tasks.
Tier 2: specialized stronger qualified VLM/reasoner for difficult or uncertain *specific* check, carrying minimum necessary evidence.
Tier 3: unresolved critical observations require operator adjudication; no automatic pass or unrestricted spend.

OpenRouter discovery is **candidate enumeration**, not trust. Fetch provider pricing/capabilities each TTL and retain exact raw snapshots and endpoint identity. Use OpenRouter `provider` filters, `require_parameters`, `max_price`, latency/throughput sorting where supported; require `allow_fallbacks: false` for controlled provider experiments unless fallback is the measured treatment. Record any actual fallback on production attempts. Never assume cost/latency features are stable without adapter contract tests.

Privacy: explicit data classification and per-case external transfer permission. Unapproved private reference images, faces, proprietary project frames, or client material are **local only**. OpenRouter zero-data-retention eligibility must be checked and enforced when required; ZDR does not itself constitute owner consent. Redact secrets and minimize image payloads. Credentials from env/secret manager only, never receipts, repo or logs.

## 8. Budget control and failure handling

Configurable hard max per call, per run, per day, per task and provider, with a separate authorized allowance for image/video generation. Suggested *example* default: USD 2/day eval ceiling and 15% exploration share; these are **not an authorization** to incur charges. Default mode is `offline` and max external spend **zero**, until explicit spend grant. Preflight reserve conservative upper-bound costs using max input/output tokens; prevent concurrent oversubscription via atomic reservations. Reconcile billed usage and release unused reservations. When usage cannot be reconciled or estimated within ceiling, halt new calls and return `NOT_COMPUTABLE`. Prevent repeat spend on exhausted cases. Implement cancellation, jittered bounded 429/5xx retries, circuit breakers, and idempotency to the extent providers support it. TTL caches must include payload/prompt/judge/model/version/permission hashes; privacy policy is part of cache key. No background spend without explicit schedule and authorization.

## 9. Data and interface contracts (proposed)

```yaml
schema: kubeval.experiment.v1
id: KUBEVAL-001-smoke
mode: offline # offline | optimize | qualify
task: board_vision
dataset:
  manifest: evals/benchmarks/board-v1/manifest.json
  sha256: REQUIRED
  split: development
controls:
  seed: 42
  concurrency: 2
  max_attempts_per_case: 1
  external_spend_authorized: false
  run_budget_usd: 0
  daily_budget_usd: 0
  exploration_share: 0
candidates:
  - route_id: champion-recorded
    model: fixture
    provider: local
  - route_id: challenger-recorded
    model: fixture
    provider: local
policy:
  critical_failure_action: block
  not_computable_action: block
  automatic_promotion: false
outputs:
  receipt_dir: out/kubeval/runs
```

Required case schema: case ID, `project_id`, lineage key, task, modality, declared source rights, data classification, hashes, ground-truth annotation version, defect severity, rubric version, frozen split. Required attempt receipt: experiment/case/route/provider, model/version, provider fallback, snapshot, prompt fingerprint, input/output hashes, timestamps, latency, tokens, estimated/actual bill, outcome, abstention, failure code, retries, evidence pointers. Store hashes or references for proprietary assets, never raw private payloads by default.

Proposed commands (not yet implemented): `python tools/kubeval/run.py --experiment ...`, `python tools/kubeval/compare.py --runs ...`, `python tools/kubeval/report.py --run ...`.

## 10. Verification and acceptance

| ID | Required acceptance test | Expected |
|---|---|---|
| KV-01 | Offline replay with same manifest and recorded outcomes | Identical score/decision receipts, excluding explicitly variable timestamps |
| KV-02 | Missing label, hash mismatch, unsupported modality | NOT_COMPUTABLE, no paid dispatch |
| KV-03 | Budget exhausted and two concurrent requests | No authorization overspend, no new calls |
| KV-04 | Candidate false pass of critical lock | Disqualified regardless of cheapness or aesthetics |
| KV-05 | Holdout leakage / near-duplicate project lineage | Qualification blocked |
| KV-06 | Judge rates its own outputs without independent truth | Not accepted as qualification evidence |
| KV-07 | Provider failure / catalog pricing drift | Bounded fallback where authorized, otherwise fail closed |
| KV-08 | Secret or private non-consented image submitted | Dispatch blocked, sensitive content absent from receipt |
| KV-09 | Independent lower-cost route with equivalent quality | Proposal-only winner and evidence bundle |
| KV-10 | Cheaper but slower route | Show Pareto tradeoff; obey explicit policy |
| KV-11 | Retake scenario with failed attempts | All attempts count toward cost/time to usable result |
| KV-12 | Promotion request | Requires approver record; no implicit route switch |

## 11. Phased work and version proposal

- **v0.28**: freeze evaluation schema/rubrics, migrate EP-01 receipts, create offline replay and budget ledger, deterministic tests. No API spend.
- **v0.29**: optional OpenRouter discovery adapter, price/capability snapshot, permission gates, dry-run routing and low-cost A/B with authorized spend.
- **v0.30**: independent multi-project board/identity datasets, VLM cascade, calibrated judges, project-grouped qualification.
- **v0.31**: production-loop and retake evaluation with separately approved image/video spend, latency and unit economics.
- **v0.32**: statistical champion/challenger, monitored proposals, human-approved routing promotion and rollback. Contextual bandit only if exploration evidence justifies it.

Versions are candidate roadmap allocations, not a release commitment. Each phase requires journey -> workflow -> state transition -> contract -> acceptance test -> implementation task and existing intent/PR gates.

## 12. First implementation slice and order

1. Define `kubeval.case.v1`, `experiment.v1`, `attempt.v1` and human judgment rubric with JSON Schema.
2. Build offline recorded replay from existing board calibration manifests; verify old measurements exactly.
3. Add SQLite receipt/budget ledger and immutable data split provenance.
4. Build paired score report with confusion matrices, confidence intervals and Pareto chart/table.
5. Add OpenRouter catalog adapter behind network/expense opt-in and mock adapter tests.
6. Add selective tier-1/tier-2 judge escalation; preserve current Jev and board gate.
7. Acquire independent labeled cross-project cases before proposing model promotion.

## 13. Sources and uncertainty

Repository: [README](../README.md), [board calibration](BOARD-IMAGE-CALIBRATION.md), [board image gate](JEV-PRE-SPEND-GATE.md), [take QC](TAKE-QC.md), [roadmap](ROADMAP.md), [agent contract](../AGENTS.md).
OpenRouter official docs: [provider routing](https://openrouter.ai/docs/guides/routing/provider-selection), [usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting). The API integration must validate current model catalog fields and receipts in adapter contract tests. No live model benchmark or paid call was executed to create this specification.
