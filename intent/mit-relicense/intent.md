# Intent: relicense Kubrick under MIT

## Problem

Kubrick is now a public repository and its history was scanned clean. The
license is still the Zero State Proprietary License v1.0
(`LicenseRef-Zero-State-Proprietary-1.0`), which does not fit a public skill.

## Proposed outcome

The repository is licensed under the standard MIT License, copyright
"Copyright (c) 2026 Zero State LLC", SPDX `MIT`. This includes the `SKILL.md`
frontmatter `license` field (a skill-contract change), LICENSE, LICENSE_POLICY.md,
CONTRIBUTING.md, README.md, the Hermes submission doc, the skill validator,
the license tests, and the `skills/kubrick/` mirror. The README is rewritten
in plain English and its public badges are restored.

Out of scope: any other `SKILL.md` field, cinematic or CLI behavior, and the
film-content word "proprietary" in `references/` patterns.

## Affected users / systems

Hermes operators and other agent hosts, the hub mirror, CI license checks,
downstream users of the repository.

## Constraints / non-goals

- Only the `license` field of `SKILL.md` changes.
- Existing third-party notices stay in place.

## Open questions

None. The owner requested the change.

## Verified / assumed claims

| Claim | Label | Basis |
|---|---|---|
| Repository is public | `OBSERVED` | Owner statement, PR #147 |
| History scanned clean | `INFERRED` | Owner statement; not re-run here |

## Author / date

- Author: Daniel Meyer (requested), drafted by an agent
- Date: 2026-10-09
- Status: ACCEPTED: Danny, 2026-10-10 PT
