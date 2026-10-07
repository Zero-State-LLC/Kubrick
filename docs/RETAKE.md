# Retake router

`src/kubrick/qc/edit_route.py` recommends the next step. It does not call
Aleph, Luma, Wan, SAM2, Jev, or ElevenLabs, and it does not write the corpus.

| Label | Recommendation |
|---|---|
| `LOCALIZED_MATERIAL` | Mask edit. Provider `aleph` unless the defect names `luma_modify` or `wan_vace`. Mask `sam2_track`. |
| `LOCALIZED_LIGHT` | Mask edit. Provider `luma_modify` by default. |
| `FRAMING` | Re-board. |
| `MOTION_INFEASIBLE` | Re-plan. |
| `IDENTITY` | Fix the reference. |

Shot 10 faint nails is `LOCALIZED_MATERIAL`. The instruction is to mask the
nails and not retake the shot. `full_retake` is false.

A Jev label that disagrees with the route, or more than one label, drafts a
drift entry. The draft is `PROPOSED`, `applied: false`, and
`needs_human_approval: true`. `apply_drafts` returns `NOT_COMPUTABLE` and
does not create a file. Pattern evolution stays proposal-only.

Video cues add `sfx_estimate` (issue #108). Any frame may list sound effects
under `sfx`, each a name or `{effect, seconds}`. The plan prices them with
`sfx.credits_per_second` (and `sfx.default_seconds` for effects without
`seconds`), and the cue sheet shows one row per effect under
`effects_detail`. A flat `sfx.credits` number wins and is copied onto the
line. No effects and no `sfx` block gives the explicit line `sfx 0`. Frames
that declare effects with no rate fail closed with `SFX_ESTIMATE_MISSING`, and
a bad number is `SFX_NOT_COMPUTABLE`. The estimate comes from plan fixtures
only and is not an ElevenLabs call.

```yaml
sfx: {credits_per_second: 40, default_seconds: 2}
frames:
  - shot_id: "01"
    sfx: [{effect: door slam, seconds: 1.5}, rain bed]
```

Fixtures: `evals/fixtures/ep01/retake_routes.yaml`.
