# Board image gate calibration: MYSLEF EP-01 (2026-10-04)

This note records how the 0.25.1 default identity threshold was chosen and
how accurate the local judge was on the same images. Everything ran on one
CPU box with free open-weights models. No paid API and no generation call
was made. The labeled images are local MYSLEF files and are not in the repo.

## Set

- Approved references: the EP-01 head lock (locked shot 05 front frame as
  `head_lock`, plus the 3/4, profile, and back views as `views`).
- Kept boards (15): the head-lock boards that were used or passed QC
  (01, 02, 06B, 07, 08, 09, 10, 11, 12, 15 and the restart boards b09r and
  b11r).
- Drift boards (15): the v1 and v2 boards for 01, 06B, 07, 08, 09, 11, 12
  and 15 that were re-rolled because the head drifted before the head-lock
  sheet existed.
- Other boards: 6 head-lock alternates rejected for head size, lens sides, a
  knee tear, or aspect ratio, and 8 boards with no face (inserts, POV).
- Take frames (34): the middle and last used frame of every EP-01 take, kept
  and rejected. Every take came from a head-lock board, so all count as kept
  for identity. Their rejections were lock details: grille light (01 t1),
  lights on the back (07 t1), blue lens glow (12 t1), human hands (10 t1,
  t2), framing (11 t1), head growth at the end (09 t1).

This is a small set: 15 drift boards, all from one character and one image
model. Treat every number below as a first estimate.

## Identity similarity

Score: the gate's own code (`Dinov2Embedder`, `isolate_subject`, max cosine
over the views), DINOv2-small CLS features. Three crops were compared: the
gate default (border contrast, no plan box), a person box, and a head box.
The person and head boxes came from an open-vocabulary detector run by hand
for this study; the gate does not include one.

| Crop | Kept boards | Drift boards | AUC kept over drift |
|---|---|---|---|
| Gate default | 0.112 to 0.870, median 0.177 | 0.098 to 0.844, median 0.161 | 0.60 |
| Person box | 0.047 to 0.852, median 0.132 | 0.024 to 0.851, median 0.115 | 0.49 |
| Head box | 0.535 to 0.886, median 0.704 | 0.571 to 0.850, median 0.707 | 0.52 |

Head box, block when the score is below the threshold:

| Threshold | Drift blocked (recall) | Precision | Kept boards blocked | Kept boards and frames blocked |
|---|---|---|---|---|
| 0.50 | 0/15 | n/a | 0/15 | 1/47 |
| 0.60 | 3/15 | 0.75 | 1/15 | 9/47 |
| 0.70 (old default) | 7/15 | 0.50 | 7/15 | 23/47 |
| 0.80 | 11/15 | 0.50 | 11/15 | 32/47 |

With the gate default crop, the old 0.70 blocked 13 of 15 kept boards and 38
of 49 kept boards and frames. Only close-ups pass, because a medium or wide
board is mostly alley or server room.

Three off-model images (the rejected long-barrel and chest-fan character
sheets and the retired head composite) scored 0.32 to 0.46 on a head crop
and 0.41 to 0.44 with the default crop.

DINOv2-base and mean patch features did not help (head-crop AUC 0.48 to
0.54).

### Choice: 0.50

- No threshold separates drift from kept heads. The drift on EP-01 was
  subtle (a plumper face, a smaller head, a human-looking back of the head)
  and DINOv2 global similarity does not see it.
- 0.50 passes every kept board on a head crop and blocks the off-model heads.
  It is an off-model floor, not a drift detector.
- Give a medium or wide board a head box in `board_subject_boxes`. Without
  one the score is about 0.1 to 0.3 and the board blocks. Since 0.25.1 the
  mismatch row says so, so nobody regenerates a correct board for it.
- Known limit: the lock questions use the same crop. With a head box, a
  hands question sees no hands; on the end-to-end run the judge answered
  neither yes nor no, so the row was UNVERIFIED and blocked. A separate
  identity box is follow-up work.

## Local judge accuracy

Model `qwen2.5vl:3b` through Ollama on 127.0.0.1, temperature 0, on the
gate's default crop. 77 images, 477 yes-or-no questions.

| Check | Accuracy | Defect present, judge caught it | Clean, judge passed it |
|---|---|---|---|
| Plan lock `red-chest-led` (gate wording) | 0.69 | 1/5 | 45/62 |
| Plan lock `lenses` (gate wording) | 0.46 | 2/2 | 29/65 |
| Plan lock `speaker-mouth` (gate wording) | 0.90 | n/a | 60/67 |
| Silicon hands | 0.75 | 9/10 human hands | 3/6 silicon hands |
| Dome head | 0.90 | n/a | 60/67 |
| Lens glow | 0.22 | 2/2 | 13/65 |
| Light on head, grille, hood, back or spine | 0.21 | 2/5 | 12/62 |
| Lens sides | 0.69 | n/a | 41/59 |

With the three plan-alley locks as the gate builds them, 38 of 60 clean
boards and frames would block and 6 of 7 defective ones would block. Two
calls got HTTP 500 when the model runner was killed for memory, and 25
answers were not yes or no. Both count as UNVERIFIED and block.

A smaller A/B on 29 images tried asking negative locks as "does the image
show any of these" instead of "is this statement true: no ...". It did not
help (0.62 against 0.62 on the default crop, 0.56 against 0.56 on a person
crop), so the judge prompt is unchanged. A person crop helped the hands
question a little (12 of 14 right against 11 of 14) and not the light or
glow questions. `qwen3-vl:4b-instruct` was also tried and its
runner was killed for memory on the third image.

What this means:

- The 3B judge is good at one thing that cost real credits on EP-01: it
  flagged 9 of 10 human-hand images. A `board_checks` silicon-hands question
  is worth keeping.
- It is not reliable on lens glow or body lights, and it misses silicon
  hands half the time. Expect false blocks. Use recorded answers
  (`--board-judge-answers`) after a human look, or a logged
  `--board-image-opt-out REASON`, until a stronger local model fits.

## Spark judge (2026-10-04)

The same 77 images and 477 questions were rerun through the Spark box: a
Qwen3.5 vision model (`Qwen3_5ForConditionalGeneration`, image input) served
by SGLang behind an OpenAI-compatible `/v1` endpoint. The gate still only
talks to loopback. A small proxy on the operator box listens on
127.0.0.1:11435, takes the judge's Ollama-style `/api/generate` call, and
forwards it to Spark with the key from the box environment. Thinking is off
and the temperature is 0. If Spark or the proxy is down the proxy answers
HTTP 502, the judge raises `BackendUnavailable`, and every lock check is
UNVERIFIED, which blocks as before. The proxy lives on the box, not in this
repo; point `KUBRICK_BOARD_VLM_URL` at it. Ollama with `qwen2.5vl:3b` on
127.0.0.1:11434 stays the fallback.

| Check | `qwen2.5vl:3b` | Spark Qwen3.5 | Defect caught (Spark) | Clean passed (Spark) |
|---|---|---|---|---|
| Plan lock `red-chest-led` (gate wording) | 0.69 | 0.63 | 4/5 | 38/62 |
| Plan lock `lenses` (gate wording) | 0.46 | 0.67 | 2/2 | 43/65 |
| Plan lock `speaker-mouth` (gate wording) | 0.90 | 0.96 | n/a | 64/67 |
| Silicon hands | 0.75 | 0.81 | 10/10 human hands | 3/6 silicon hands |
| Dome head | 0.90 | 0.93 | n/a | 62/67 |
| Lens glow | 0.22 | 0.97 | 1/2 | 64/65 |
| Light on head, grille, hood, back or spine | 0.21 | 0.91 | 4/5 | 57/62 |
| Lens sides | 0.69 | 0.46 | n/a | 27/59 |
| All 477 | 0.58 | 0.79 | | |

Every Spark call answered yes or no (0 unknown against 25) in about 0.9
seconds (CPU 3B: tens of seconds). Per question, Spark fixed 152 answers the
3B model got wrong and broke 52 it got right.

The gate effect barely moved. With the three plan-alley locks as the gate
builds them, 36 of 60 clean boards and frames would block (38 with the 3B
model) and 7 of 7 defective ones would block (6). Asked directly ("is either
lens glowing", "is there any light on the head or back"), Spark is right
about 9 times in 10. Asked as the gate's compound negative statement ("is
this statement true: no light on the head, hood or temple, no light along the
spine or on the back"), it is not. A rerun of the same gate questions moved
the clean-blocked count from 36 to 41, so treat a few boards of difference as
noise.

Prompt variants on the 201 gate-wording questions, Spark, default crop:

| Variant | Clean blocked | Defective blocked | Accuracy |
|---|---|---|---|
| Gate wording as shipped | 36 to 41 of 60 | 7 of 7 | 0.75 |
| "Design rule, answer no only if clearly broken" | 30 of 60 | 5 of 7 | 0.81 |
| "Check each part" | 50 of 60 | 6 of 7 | 0.59 |
| "Does the image show any of these" (negated) | 48 of 60 | 6 of 7 | 0.71 |
| Gate wording with thinking on | 49 of 60 | 7 of 7 | 0.71 (14 not yes or no) |

None is clearly better: the one that blocks fewer clean boards lets two
defective ones through. The judge prompt is unchanged.

What this means:

- Spark is a better judge for `board_checks` written as one direct question
  with `expect` (clean boards pass about 9 times in 10), but the defect
  counts are tiny and it caught only 1 of 2 lens-glow and 4 of 5 body-light
  defects, so a pass is not proof. For lens glow and body lights, prefer a
  question like "Is either of the character's round camera lenses glowing
  or emitting light?" with `expect: no` over compound `character_locks`
  text.
- The compound plan-lock questions still block most clean boards. Keep the
  recorded-answers path or a logged opt-out for them, or split a lock into
  single direct `board_checks`.
- Lens sides (left and right) got worse. Do not make it a blocking check.
