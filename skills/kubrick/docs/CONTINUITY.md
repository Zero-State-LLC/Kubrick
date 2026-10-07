# Continuity carriers

A shot's picture is carried in this order:

1. **Start image.** The first frame the model must match.
2. **References.** Character, prop, and location images that stay in force.
3. **End image.** The frame the shot has to land on, when one is anchored.
4. **Prompt.** Motion and the one camera move. It does not restate the still.

A plan lock with a `positive` line counts as a prompt carrier only when the
compiled shot prompt actually says that line. When the prompt omits it, the
`lock_carriers` row is `unverified` with code `LOCK_POSITIVE_NOT_IN_PROMPT`.
A lock with a `character` only applies to shots where that character is cast.

Local plans stay **PROPOSED**. A weak or contradictory carrier is
`NOT_COMPUTABLE`. This note is the carrier model. It does not add a provider
call.

Take QC reads the first frame, the middle, the last frame, each cut, and the
end of the 1.6 second hold. Those measurements are fixtures in CI. See
[`TAKE-QC.md`](TAKE-QC.md).

When a start frame is used, the video line is one action and one camera move.
The still, including head ratio, stays on the image prompt. Keyframe
`create_movie` has `startImage` and no end-image field. An end framing that
anchors a size, crop, or head-ratio change is recorded as
`END_IMAGE_UNSUPPORTED` on the prep warnings. See [`FRAMING.md`](FRAMING.md).
