# Jev pre-spend gate

`video runbook` and `video cues` check every prompt that would be spent
before they record a credit figure or a paid operation. Kubrick does not call
Keyframe, ElevenLabs, or an image provider. The gate only decides whether
those proposed operations may be written.

## Hold list

If the plan sets `hold_list`, that list is the whole check. It must be a list.
A string, mapping, or other non-list is `HOLD_LIST_INVALID` and blocks the
spend. The gate does not fall back to locks when that field is present. Each
entry is a string or an object with `text`, `negative`, or `positive`. An
entry with `blocked: true` and `shot` is a local block. The shot is matched
against the prompt shot and its aliases (`frame_id` and `shot_id`). It does
not need a Jev verdict, and an override does not clear it.

When `hold_list` is absent, the gate builds the list from:

- plan `locks` (presence checks; critical unless the lock says otherwise)
- `location.locks` (presence checks for that location)
- prop `states` (`in_scope_only`, so a state must not leak onto a shot that
  is outside its scope)

Before any Jev call the compiled text is linted. A scoped hold that applies
to the prompt and is not stated in the text is `LOCK_MISSING_IN_BOARD` and
blocks spend. A blank or whitespace prompt `location` while a hold names
`scope.locations` is `LOCATION_UNSPECIFIED` and blocks spend; the hold is not
dropped. See [`scoped-holds.md`](scoped-holds.md).

An empty hold list passes with code `NO_HOLDS` and does not call Jev. A step
with no prompts to spend passes with `NO_SPEND`.

Keyframe prompts are the compiled shot text. That text is what Keyframe would
copy into both the image prompt and the video prompt. Cue prompts are the
spoken lines that would be sent to ElevenLabs.

## Jev

Resolution order:

1. `--jev-verdicts FILE`, or `KUBRICK_JEV_VERDICTS`, a JSON object
   `{"verdicts": {"<sha256>": {"verdict": "pass"|"fail", "findings": [...]}}}`.
   The key is the sha256 of the canonical JSON for the judged prompt
   (`shot`, `channel`, `surfaces`, `location`, `prompt`) and the hold list.
   A change to either does not reuse the recorded verdict.
2. `KUBRICK_JEV_URL`, an `http` or `https` endpoint

The live call is `POST {"prompt": {...}, "holds": [...]}`. A usable response
is `{"verdict": "pass"|"fail", "findings": [{"code", "message", "hold_id"?}]}`.
A pass with findings, a missing verdict, or a transport error is unreachable.
A transport failure on a later prompt is unreachable too. If an earlier prompt
already failed a hold, that hold still blocks and the override does not clear it.

If Jev is not configured or cannot be reached, the command exits 4 with
`JEV_UNREACHABLE` and writes no paid operations and no credit estimate.

## Override

`--jev-override`, or `KUBRICK_JEV_OVERRIDE` set to `1`, `true`, or `yes`,
allows the spend only when Jev is unreachable. The command prints one stderr
line, `JEV_OVERRIDE` plus a JSON record. A hold hit still blocks, including
when the override flag is set. The message says the override does not bypass
a hold hit.

## Ledger

The payload always carries `jev_gate` (`checked_before_spend: true`) and
`run_ledger` with one `kind: jev_gate` entry. `--run-ledger PATH` appends
that entry to a file. Once the Jev gate passes, `video runbook` also carries
`board_image_gate` and a second `kind: board_image_gate` ledger entry, which
`--run-ledger` appends too. A corrupt ledger is `LEDGER_INVALID` and is not
replaced. A successful judgment that cannot be written is
`LEDGER_WRITE_FAILED` and includes no paid operations.

## Board image checks

`video runbook` runs a second gate after Jev passes and before any credit
figure or paid operation: the board image gate in
`src/kubrick/gates/board_image_gate.py`. It looks at the pixels of each paid
shot's start or board image. It is **on by default**. The video model copies
the board, so a wrong board is a wrong shot (EP-01 lost 124 cr to a board
with human hands on a silicon-hand lock).

### Which images

- `board_image` on the frame (or `start_frame.board_image`) is always
  checked. A path that does not exist is `BOARD_IMAGE_MISSING`. A file that
  cannot be decoded is `BOARD_IMAGE_UNREADABLE`. Both block.
- `start_frame.asset` is checked when it resolves to a local `.png`,
  `.jpg`, `.jpeg`, or `.webp` file. A provider asset id has no pixels here.
  It is reported as the warning `BOARD_IMAGE_NOT_LOCAL` and does not block;
  set `board_image` to the local file to check it.
- Relative paths resolve against the plan file's folder.
- A shot with no board (refs-only) needs no check. A run with no checked
  board passes with `NO_BOARD_IMAGES`.

### Identity

For each character on the frame (`cast`, else a non-empty `characters`, else
every plan character; `cast: []` means nobody is in frame, `characters: []`
alone does not):

1. Crop the character. `board_subject_boxes.<character>` (or
   `board_subject_box` on a one-character frame) is a normalized
   `[x0, y0, x1, y1]` box. Without one, the crop is the bounding box of the
   pixels that differ from the border color. A frame with several characters
   and no box uses the full frame. The report names the method
   (`plan_box`, `border_contrast`, or `full_frame`).
2. Embed the crop and each approved identity view
   (`characters.<id>.ref_pack.views` and `head_lock`, role `identity`) with
   DINOv2 (`facebook/dinov2-small`, CPU, local, free). Set
   `KUBRICK_BOARD_EMBED_MODEL` to use another local DINOv2 checkpoint.
3. The score is the highest cosine similarity across the views. Below the
   threshold is `BOARD_IDENTITY_MISMATCH` and blocks.

The default threshold is **0.50** (since 0.25.1). It was calibrated on the
MYSLEF EP-01 kept and drifted boards; see
[`BOARD-IMAGE-CALIBRATION.md`](BOARD-IMAGE-CALIBRATION.md). On a head crop
every kept board scored 0.535 or more and off-model heads scored 0.32 to
0.46. It is an off-model floor, not a drift detector: kept and drifted heads
overlapped (AUC about 0.52), so no threshold separated them. A medium or
wide board needs a head box in `board_subject_boxes`; without one the crop
is mostly background, a kept board scored 0.10 to 0.30, and the mismatch row
says to add the box before regenerating. Set the threshold with, from highest
precedence: `--board-identity-threshold`, then
`characters.<id>.ref_pack.identity_threshold`, then
`board_image_gate.identity_threshold` on the plan. A value outside (0, 1] is
`BOARD_GATE_CONFIG_INVALID` and blocks.

### Locked details

Each character's lock list becomes yes-or-no questions: `character_locks`,
`characters.<id>.locks`, plan `locks` with `character: <id>`, and explicit
`characters.<id>.board_checks` (`question`, `expect: yes|no`,
`severity: block|warn`).

Since 0.26.0 a lock is asked as one direct question per clause, each with
its expected answer, not as one compound "is this statement true" question.
The lock text (`negative`, else `positive`, else `text`) is split at commas,
semicolons, and `and`, but only where the next part starts a new negative
clause, so a list such as "head, hood or temple" stays in one question:

| Clause | Question | Expect |
|---|---|---|
| `no X` or `not X` | Does the character show any X? | `no` |
| `S never V` | Do S V? (Does, for a singular subject) | `no` |
| anything else | Does the character show X? (Is it true in this image that X?, when X has its own verb) | `yes` |

For example, `negative: the lenses never glow, no human eyes, no long lens
barrels` asks "Do the lenses glow?", "Does the character show any human eyes?",
and "Does the character show any long lens barrels?", each expecting `no`. Every
question goes to the judge on its own. To word a lock's questions yourself,
give the lock a `checks` list (`question`, `expect`, `severity`); it
replaces the split.

The answers are combined per lock (the report's `locks` list). A wrong
answer to a `block` question is `BOARD_LOCK_DETAIL_FAIL` and blocks. A
`block` question the judge cannot answer is `BOARD_LOCK_DETAIL_UNVERIFIED`
and blocks too (fail closed). A `warn` question that fails or cannot be
answered is a `WARN` row and a `BOARD_LOCK_DETAIL_WARN` warning; it never
blocks spend. Severity defaults to `block`, except a question that names the
left or right side defaults to `warn`, because the judge scored 0.46 on lens
sides (see the calibration note). Set `severity` on a `board_checks` row, a
lock `checks` row, or a whole lock to override it; a lock's `checks` inherit
the lock's severity. When two sources ask the same question, the stricter
severity wins. A severity other than `block` or `warn`, an `expect` other
than `yes` or `no`, a `checks` row with no question, or one question given
two different `expect` values is `BOARD_GATE_CONFIG_INVALID` and blocks; the
gate never drops it silently.

Recorded answers are keyed by the exact question, so answers recorded before
0.26.0 for compound questions no longer match and come back UNVERIFIED.
Record them again.

The judge is pluggable (`LockJudge.ask(image, image_sha256, question)` in
`src/kubrick/qc/board_vision.py`). Resolution order:

1. `--board-judge-answers FILE`, or `KUBRICK_BOARD_JUDGE_ANSWERS`: recorded
   answers, `{"answers": {"<board sha256>": {"<question>": "yes"|"no"}}}`.
2. The default: a local vision-language model behind an Ollama-compatible
   `/api/generate` endpoint at `KUBRICK_BOARD_VLM_URL`, model
   `KUBRICK_BOARD_VLM_MODEL` (default `qwen2.5vl:3b`). The URL must be on
   the loopback interface (`localhost`, `127.0.0.1`, `::1`). A remote URL is
   refused, so the judge itself never calls a remote or paid API.
   The loopback check covers only the first hop. A proxy on loopback that
   speaks `/api/generate` can forward the image and question to another
   machine, so such a proxy is a spend and data boundary the owner must
   approve; the gate cannot prove where it sends requests. The operator box
   runs one, approved 2026-10-04, for the free self-hosted Spark Qwen3.5
   vision model on 127.0.0.1:11435. A proxy that cannot reach its upstream
   must return an error so the check stays UNVERIFIED. See the calibration
   note for its accuracy. The repo ships such a proxy for any
   OpenAI-compatible vision endpoint, with the provider in a profile:
   [`BOARD-VISION-SETUP.md`](BOARD-VISION-SETUP.md#adapter-contract).

### Fail-closed policy

A check that cannot run is **UNVERIFIED**, and UNVERIFIED blocks spend just
like a failure. This matches the Jev gate, where an unreachable judge blocks:

- No `torch`, `transformers`, or `Pillow`, or the model cannot load:
  `BOARD_IDENTITY_UNVERIFIED`.
- A character on the board has no readable identity views:
  `BOARD_IDENTITY_UNVERIFIED`.
- No local vision-language model is configured or reachable, no recorded
  answer exists, or the judge does not answer yes or no:
  `BOARD_LOCK_DETAIL_UNVERIFIED`.

Set up the local models and the judge with one command,
`bash tools/board_vision/setup.sh` (steps in
[`BOARD-VISION-SETUP.md`](BOARD-VISION-SETUP.md)). It installs the
`board-vision` extra from `pyproject.toml`. Since 0.27.0 an editable install
(`pip install -e ".[board-vision]"`) is safe in the venv you test from: every
`scripts/` entry point puts `src` first, so `scripts/kubrick.py` no longer
shadows the `kubrick` package. The local judge
was measured on EP-01 too: `qwen2.5vl:3b` caught 9 of 10 human-hand images
but was unreliable on lens glow and body lights, so expect false blocks (see
the calibration note). CI does not install it; tests use
tiny fixture PNGs in `evals/fixtures/board_images/` and a mocked embedder.
8-bit PNG boards decode with the standard library. JPEG and WebP need Pillow.

### Cut rules

- A hard cut (`join: cut`, `new_angle: true`, or a `cut` naming
  `thirty-degree` or `new-angle`) whose board is byte-identical to an earlier
  shot's board is `BOARD_REUSED_ON_CUT`. Build a fresh board for the new
  angle from the canon refs.
- A board whose `board_view` (or `start_frame.view`) is `back`, `rear`, or
  `occluded` on a shot with `reveals_identity: true` is
  `START_FRAME_HIDES_IDENTITY`. Give that shot a board that shows the
  identity, or use refs-only.

### On failure

The command exits 4 with the most specific code first (missing or unreadable
image, cut rule, mismatch, lock failure, then UNVERIFIED). The message names
each shot and points to the fix: regenerate the board for that shot from the
approved `ref_pack` identity views (one image, about 7 cr) and rerun the gate
before any video spend. No paid operation and no credit estimate are written.

### Opt-out

`--board-image-opt-out REASON`, or `KUBRICK_BOARD_IMAGE_OPT_OUT=REASON`,
skips the board image checks for that run. The reason is required: a blank
reason is `BOARD_OPT_OUT_REASON_MISSING` and blocks. The command prints one
stderr line, `BOARD_IMAGE_OPT_OUT` plus a JSON record with the reason and the
shots, and the gate result (`opt_out_reason`) goes into the run ledger. The
opt-out does not touch the Jev gate.

## Canon lock file

A plan may name its canon lock file with `canon_locks: <path>`. A relative
path is looked up from the plan's folder, then each parent folder, then the
working directory. A plan lock can map to a canon lock with a
different id through `canon_id`. Before `video runbook`, `cues`, or `cut-qa`
load anything else, each mapped lock's `positive` and `negative` lines are
compared with the canon (whitespace ignored). Any difference fails closed with
`LOCK_CANON_DRIFT`. Kubrick holds no canon itself; the plan names its own
file. The MYSLEF example points at
`evals/calibration/board-image-ep01/locks-v0.27.yaml` as a test case.

## MYSLEF

`evals/fixtures/jev/myslef-v023.json` stores the v0.23 compiled prompts for
shots 03–06 and recorded fail verdicts for the missing red-chest lock.
`evals/fixtures/jev/myslef-hand-fixed.json` stores the same prompts with the
lock restored as the plan states it (the positive line naming the one red
chest LED and the negative line), plus an alley shot that does not carry the
chair lock. Those recorded verdicts pass. A critical lock with both lines
enforces both: a picture prompt that drops either the negative or the positive
line is `MISSING_LOCK` even when the recorded verdict says pass (issue #107).
A lock with a `character` is skipped for a prompt whose `characters` list
leaves that character out, so an empty-cast shot (MYSLEF shot 06) does not
have to state a body light. Each compiled row takes that list from the frame's
`cast` first, then `characters`, as the prompt compiler does (0.27.13). Since
0.27.14 the compiler writes each applicable lock `negative` line after the
positive lines, so the live example plan states both critical lines on shots
03 to 05. The prompt lint does not read a plan lock's own negative line as a
`POSITIVE_NEGATIVE_CONFLICT`; other negations still are. Spoken cues are not picture prompts. `scripts/test_jev_gate.py`
checks the live compiler against the v0.23 snapshot, so a prompt change does
not inherit an old verdict.

## Codes

| Code | Meaning |
|---|---|
| `JEV_HOLD` | A prompt hit a hold. Spend is blocked. |
| `JEV_UNREACHABLE` | Jev is down, unconfigured, or returned a verdict the gate cannot trust. |
| `JEV_OVERRIDE` | Jev was unreachable and the operator override was logged. |
| `JEV_PROMPT_MISSING` | A paid shot has no compiled prompt. |
| `LOCK_CANON_DRIFT` | A plan lock's `positive` or `negative` line differs from the same lock (or its `canon_id`) in the plan's `canon_locks` file. |
| `LOCK_CANON_MISSING` | A plan lock names a `canon_id` that the canon lock file does not have. |
| `LOCK_CANON_UNREADABLE` | `canon_locks` is not a path, or the file cannot be loaded or has no `locks` list. |
| `HOLD_LIST_INVALID` | `hold_list` is not a list, or an entry has no text. |
| `NO_HOLDS` | The plan has nothing to check. |
| `NO_SPEND` | This step has no prompt that would be spent. |
| `CLEAR` | Jev passed every prompt. |
| `BLOCKED_SHOT` | The shot is marked blocked on the hold list. |
| `LOCK_MISSING_IN_BOARD` | A scoped hold that applies to the prompt is not stated in it. Blocks before Jev. |
| `LOCATION_UNSPECIFIED` | The prompt location is blank while a hold is location-scoped. Blocks before Jev. |
| `MISSING_LOCK` | A recorded or live finding: required lock text is absent. |
| `OUT_OF_SCOPE_LOCK` | A finding a judge may return when an in-scope-only hold leaks. |
| `BRAND_PRONE` | A finding a judge may return for brand-prone wording. |
| `BOARD_IDENTITY_MISMATCH` | A board crop is below the identity threshold against every approved view. Blocks. |
| `BOARD_IDENTITY_UNVERIFIED` | The identity check could not run (no local model, no readable views). Blocks. |
| `BOARD_LOCK_DETAIL_FAIL` | The judge answered a locked-detail question the wrong way. Blocks. |
| `BOARD_LOCK_DETAIL_UNVERIFIED` | No local judge, no recorded answer, or no yes-or-no answer. Blocks. |
| `BOARD_LOCK_DETAIL_WARN` | A `severity: warn` lock question failed or could not be answered. Warns, never blocks. |
| `BOARD_IMAGE_MISSING` | A declared `board_image` does not exist. Blocks. |
| `BOARD_IMAGE_UNREADABLE` | A board file cannot be decoded. Blocks. |
| `BOARD_REUSED_ON_CUT` | A hard cut reuses an earlier shot's board. Blocks. |
| `START_FRAME_HIDES_IDENTITY` | A back or occluded board opens a shot that reveals the identity. Blocks. |
| `BOARD_GATE_CONFIG_INVALID` | The identity threshold is not a number in (0, 1]. Blocks. |
| `BOARD_OPT_OUT_REASON_MISSING` | The opt-out was set with a blank reason. Blocks. |
| `BOARD_IMAGE_OPT_OUT` | The operator skipped the board image checks; the reason is logged. |
| `BOARD_IMAGES_CLEAR` | Every checked board passed. |
| `NO_BOARD_IMAGES` | No paid shot carries a local board image. |
| `BOARD_IMAGE_NOT_LOCAL` | Warning: a `start_frame.asset` is not a local file, so its pixels were not checked. |
