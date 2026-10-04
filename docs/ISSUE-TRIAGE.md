# Issue triage (hygiene follow-up)

Maintainer note from the repo-hygiene follow-up (cloud agent cannot write GitHub
issues via `gh` in this environment).

| Issue | Recommendation | Rationale |
|---|---|---|
| [#33](https://github.com/Zero-State-LLC/Kubrick/issues/33) — v0.15 first-class production surfaces | **Close as completed** | Shipped on Hermes `main` in v0.15/v0.16 (`design`/`script`/`image`/`video`, shared engine, schemas, examples, release docs). |
| [#32](https://github.com/Zero-State-LLC/Kubrick/issues/32) — OpenClaw align with Hermes | **Keep open** until owner confirms | Permanent `openclaw` branch still the dual-edition handoff; see [`OPENCLAW-ALIGNMENT.md`](OPENCLAW-ALIGNMENT.md). Close when remaining acceptance boxes (e.g. portability pytest) are green and docs match. |

Suggested close comment for #33:

> Closing as completed on Hermes `main` via v0.15/v0.16 first-class production surfaces. OpenClaw edition parity continues under #32.
