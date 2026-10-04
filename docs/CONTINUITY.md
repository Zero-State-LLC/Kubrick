# Continuity carriers

A shot's picture is carried in this order:

1. **Start image.** The first frame the model must match.
2. **References.** Character, prop, and location images that stay in force.
3. **End image.** The frame the shot has to land on, when one is anchored.
4. **Prompt.** Motion and the one camera move. It does not restate the still.

Local plans stay **PROPOSED**. A weak or contradictory carrier is
`NOT_COMPUTABLE`. This note is the carrier model. It does not add a provider
call.

Take QC reads the first frame, the middle, the last frame, each cut, and the
end of the 1.6 second hold. Those measurements are fixtures in CI. See
[`TAKE-QC.md`](TAKE-QC.md).
