# Intent

## Problem

The retime planner from #36 reports `final_clock` as the sum of new generations (12.0s on the MYSLEF example), but the edit plan only uses the trimmed windows (6.0s). That shows a false 6s difference from the script, which the example hid with `accept_clock_delta: true`.

## Proposed outcome

This corrects the retime rule in `intent/upgrades-33-44/intent.md`. `final_clock` is the edited runtime: the sum of each shot's trimmed edit window (out minus in, or planned duration when untrimmed). Generated seconds are reported separately as `generated_seconds`, which uses the old rule (new generations summed, shared clips counted once, reused shots add 0). The `SKILL.md` runtime contract is updated to match. A take trimmed longer than its beat still fails closed unless `accept_clock_delta` is set. The MYSLEF example drops its override.

Out of scope: any other retime behaviour.

## Affected users / systems

Hermes operators reading retime output; the `SKILL.md` runtime contract; the MYSLEF example; tests.

## Constraints / non-goals

Fail-closed behaviour on real clock deltas is unchanged. No writes into `references/`.

## Open questions

None.

## Verified / assumed claims

- **Verified:** MYSLEF regression on main 79567bc gave final 12.0 vs script 6.0 with no real delta. With the fix it gives 6.0 / 6.0 / delta 0.0, generated 12.0, 145 tests passed.
- **Verified:** Danny accepted this intent and the `SKILL.md` contract change on 2026-10-02 at 9:36 PM PT, including merging PR #46.
