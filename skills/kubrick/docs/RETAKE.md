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

Video cues add `sfx_estimate`. The line is `sfx 0` when the plan has no
`sfx` fixture. A declared `sfx.credits` number is copied onto the line.
That estimate is not an ElevenLabs call.

Fixtures: `evals/fixtures/ep01/retake_routes.yaml`.
