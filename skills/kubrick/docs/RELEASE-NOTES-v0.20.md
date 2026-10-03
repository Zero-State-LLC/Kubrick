# Kubrick v0.20.0 Release Notes

v0.20.0 adds reference scope, location and count locks, lock carriers, a
proposed retime plan, a take-impact report, and a start-frame gate. The
production envelope schema id stays `0.16.0`. Issues #39–#44 shipped in
v0.21.0.

## Added

- #33: A character reference may set `applies_to`. `scope` without `applies_to`
  is author metadata. A two-person frame with an attached reference that is
  not scoped to exactly one on-screen id warns `REFERENCE_BLEED_RISK`. A
  scoped reference adds one binding line. The line names the reference, the
  subject, and who it does not apply to.
- #34: Storyboard `location` references are linted against location locks and
  `counts`. A contradiction warns `LOCATION_REFERENCE_CONTRADICTION` and
  `--strict` exits non-zero. `counts` compile to `exactly N name` lines. A
  frame `counts` entry overrides that key. `cast: []` compiles to `nobody is
  in frame` and drops wardrobe and identity lines. `characters: []` alone does
  not drop identity lines.
- #35: Each identity, wardrobe, prop, and light lock records a carrier:
  `start_frame`, `reference`, `prompt_positive`, or `prompt_negative_only`.
  Precedence is a chain or start frame, then a scoped reference, then a
  positive line. A critical lock carried only by a negative warns
  `NEGATIVE_ONLY_LOCK`. Provider data adds `negative_prompt_effective`
  (false for Keyframe). The table is `lock_carriers` on the adapter output.
- #36: `video --action retime` proposes a generation plan, an edit plan, and
  the script clock against the final clock. A short beat, a chained shot, a
  reused take, or a provider that is not multi-shot is its own generation.
  Two or more remaining contiguous beats share one clip. A non-zero delta
  without `accept_clock_delta` is `CLOCK_DELTA_UNACCEPTED`. No provider is
  called.
- #37: `storyboard --action impact` reads `takes.yaml` as OBSERVATION. It
  replays declared prop states from a retake's observed end and warns
  `STALE_TAKE` when a later take starts from a different state. It does not
  write observations back onto the storyboard.
- #38: A chained Keyframe shot without `start_frame.asset` warns
  `START_FRAME_MISSING` and includes an ffmpeg handoff string. `--strict`
  exits non-zero. `verified: true` with an asset is silent and `startImage`
  carries the asset. `verified: false` with an asset warns
  `START_FRAME_UNVERIFIED`. Kubrick does not run ffmpeg.

## Example

Generic compile shows the scoped head-lock, the location contradiction, and
the count line. It exits 0 without `--strict` and non-zero with `--strict`
because the location reference and the head-lock reference still contradict
their locks.

```bash
python3 scripts/kubrick.py compile \
  --brief examples/myslef-minder/brief.yaml \
  --mode storyboard \
  --storyboard-plan examples/myslef-minder/storyboard-plan.yaml \
  --provider generic \
  --out /tmp/myslef-minder-generic
```

Prompts contain `exactly one laptop`. Shot 03 binds
`head-lock-short-flush.png` to myslef once. Shot 06 says `nobody is in frame`
and carries no wardrobe or identity line. The receipt warns
`REFERENCE_LOCK_CONTRADICTION` and `LOCATION_REFERENCE_CONTRADICTION`
(the lit doorway and `laptop x4`). `location-ref-v2` does not warn.

Keyframe adapt exits 0 without `--strict`. Status stays `PROPOSED`. Shot 04
`startImage` keeps `atSeconds` 2 from the join and adds `asset`. Shot 06
`startImage` stays `{sourceFrame: frame-002}` and warns `START_FRAME_MISSING`
with `ffmpeg -ss 3.583 -i shot-04-v8.mp4 -frames:v 1 06-start.png`. The red
chest light is `prompt_negative_only` on shots 03 and 05 (`NEGATIVE_ONLY_LOCK`)
and `start_frame` on the chained shot 04. `lock_carriers` is on the movie.

```bash
python3 scripts/kubrick.py video --action adapt \
  --provider keyframe \
  --input examples/myslef-minder/storyboard-plan.yaml \
  --output /tmp/myslef-minder-keyframe.yaml
```

Retime of the same plan, with no `--takes`, is `PROPOSED`. Shots 03–06 are
separate generations. Edit in/out is 0–2, 1.6–2.6, 0–2, and 0–1. Script clock
6, final clock 12, delta 6. Exit 0 because the plan sets `accept_clock_delta`.

```bash
python3 scripts/kubrick.py video --action retime \
  --provider keyframe \
  --input examples/myslef-minder/storyboard-plan.yaml \
  --output /tmp/myslef-minder-retime.yaml
```

Impact of retake 04 against `takes.yaml` is `PROPOSED` and exits 0. Shot 06
warns `STALE_TAKE`: the chair was observed `beside the desk` and does not
continue retake 04's observed end `C3 far end`. The storyboard file is
unchanged.

```bash
python3 scripts/kubrick.py storyboard --action impact \
  --storyboard examples/myslef-minder/storyboard-plan.yaml \
  --takes examples/myslef-minder/takes.yaml \
  --retake 04 \
  --output /tmp/myslef-minder-impact.yaml
```

## Notes

- The installer receipt schema id stays `1.0.0`.
- No Keyframe, ElevenLabs, or OpenRouter call is required for this prep.
- Kubrick emits the ffmpeg string and does not run it.
