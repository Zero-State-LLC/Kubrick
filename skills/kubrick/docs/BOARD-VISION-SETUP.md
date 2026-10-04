# Board vision setup: the board image gate judge on an operator box

The board image gate ([`JEV-PRE-SPEND-GATE.md`](JEV-PRE-SPEND-GATE.md#board-image-checks))
needs two local pieces: the DINOv2 embedder for the identity check and a
yes-or-no vision judge for the lock checks. The gate only talks to a
loopback URL (`KUBRICK_BOARD_VLM_URL`). This page sets both up from
`tools/board_vision/` and defines the contract any judge must meet.
Calibration numbers are in [`BOARD-IMAGE-CALIBRATION.md`](BOARD-IMAGE-CALIBRATION.md).

## Files

| File | Role |
|---|---|
| `tools/board_vision/setup.sh` | One-command setup (below) |
| `tools/board_vision/vlm_proxy.py` | Loopback adapter: Ollama `/api/generate` in, OpenAI-compatible `/chat/completions` out |
| `tools/board_vision/kubrick-vlm-proxy` | Start, stop, status for the adapter. Reads a profile |
| `tools/board_vision/kubrick-vlm` | Start, stop, status for a local Ollama judge |
| `tools/board_vision/health.py` | `check` (ask the judge one question) and `fail-closed` (no network) |
| `tools/board_vision/board-vision.env.example` | Gate settings template, copied to `~/.config/kubrick/board-vision.env` |
| `tools/board_vision/profiles/*.env.example` | Profiles: a blank adapter template, a local OpenAI-compatible server, a local Ollama judge, and the Spark box as one example |

No file in the repo holds a key. A profile names where the key is
(`KUBRICK_VLM_API_KEY_ENV` or `KUBRICK_VLM_API_KEY_FILE`); the adapter reads it
at start and never logs or returns it.

## Setup

From the repo root, in the venv Kubrick runs from:

```bash
# Any OpenAI-compatible vision endpoint, through the loopback adapter:
cp tools/board_vision/profiles/openai-compatible.env.example /tmp/vision.env  # then edit
bash tools/board_vision/setup.sh proxy --profile /tmp/vision.env --name vision

# Or a local Ollama judge (CPU, weaker), from profiles/ollama-local.env.example:
bash tools/board_vision/setup.sh ollama
```

`setup.sh` runs five steps and is safe to rerun:

1. Dependencies: `pip install -e ".[board-vision]"` (torch, transformers,
   Pillow). Editable is safe since 0.27.0. Set `KUBRICK_PYTHON` to pick the
   interpreter and `KUBRICK_SETUP_SKIP_PIP=1` to skip.
2. Model download: the DINOv2 embedder (`KUBRICK_BOARD_EMBED_MODEL`, default
   `facebook/dinov2-small`) and, for `ollama`, the Ollama model named by
   `KUBRICK_OLLAMA_MODEL` in the profile (`profiles/ollama-local.env.example`
   by default, copied to `~/.config/kubrick/ollama.env`).
3. Launchers: symlinks in `KUBRICK_BIN` (default `~/bin`) for `kubrick-vlm`,
   `kubrick-vlm-proxy`, and `kubrick-vlm-NAME` for the profile. An existing
   non-link file is backed up first.
4. Config: copies `board-vision.env.example` to
   `~/.config/kubrick/board-vision.env` and the profile to
   `~/.config/kubrick/vlm-NAME.env`, never overwriting either.
5. Start, health check, fail-closed test: starts the backend, writes its
   URL (and, for `ollama`, its model) into `board-vision.env` after a
   backup, sources that file, then runs `health.py check` (one question about a plain red image must come back
   `yes`) and `health.py fail-closed`.

Day to day:

```bash
kubrick-vlm-NAME start            # or: kubrick-vlm start
source ~/.config/kubrick/board-vision.env
python tools/board_vision/health.py check
```

The box has no service manager, so nothing starts after a reboot until you
run the start command. Logs are in `~/.local/share/kubrick-vlm/`.

## Fail-closed test

`python tools/board_vision/health.py fail-closed` uses no network. It passes
only when every one of these blocks:

- the adapter in front of an upstream that refuses connections answers HTTP
  502, and the judge raises `BackendUnavailable` (the gate's UNVERIFIED);
- a judge URL with nothing listening raises `BackendUnavailable`;
- a non-loopback judge URL is refused;
- the adapter refuses to start on a public listen address, with no upstream
  URL, with a plain-http upstream that is not loopback, or with a key source
  that is configured but empty.

## Adapter contract

Any provider or local server plugs in if it meets this contract. Nothing
about a provider is in the code; it is all in the profile.

### Profile settings

| Variable | Required | Meaning |
|---|---|---|
| `KUBRICK_VLM_UPSTREAM_URL` | yes | Base URL ending in `/v1`. A non-loopback upstream must be `https` |
| `KUBRICK_VLM_PROXY_ADDR` | no | Listen address, default `127.0.0.1:11435`. Loopback only |
| `KUBRICK_VLM_UPSTREAM_MODEL` | no | Model id. Empty: the first `data[].id` from `GET {upstream}/models` |
| `KUBRICK_VLM_API_KEY_ENV` | no | Name of the env var holding the key, sent as `Authorization: Bearer` |
| `KUBRICK_VLM_API_KEY_FILE` | no | File holding the key, read when that env var is empty |
| `KUBRICK_VLM_EXTRA_HEADERS` | no | JSON object of extra headers, for example a `User-Agent` |
| `KUBRICK_VLM_EXTRA_BODY` | no | JSON object deep-merged into every chat request, for example to turn off a thinking mode |
| `KUBRICK_VLM_MAX_TOKENS` | no | Default 64. The judge needs one word |
| `KUBRICK_VLM_TIMEOUT` | no | Upstream timeout in seconds, default 120 |

With neither key setting, no `Authorization` header is sent. Profiles are
shell-sourced, so keep JSON values in single quotes.

### Request

The gate sends the adapter what it sends Ollama:

```json
POST /api/generate
{"model": "<label>", "prompt": "Answer only yes or no. ...", "images": ["<base64 PNG>"],
 "stream": false, "options": {"temperature": 0}}
```

The adapter forwards:

```json
POST {upstream}/chat/completions
{"model": "<upstream model>", "temperature": 0, "max_tokens": 64,
 "messages": [{"role": "user", "content": [
   {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
   {"type": "text", "text": "Answer only yes or no. ..."}]}],
 ...KUBRICK_VLM_EXTRA_BODY}
```

`/api/chat` is accepted too. Streaming is refused (HTTP 400).

### Response

The upstream must return `choices[0].message.content` as a string. The
adapter answers `{"model": ..., "response": "<content, trimmed>", "done": true}`.
The gate reads the first word of `response`: `yes` or `no` is an answer;
anything else (a sentence that starts another way, an empty reply, reasoning
text) is UNVERIFIED and blocks. A model that thinks before answering must have
thinking turned off through `KUBRICK_VLM_EXTRA_BODY`, or its answer may land
outside `content` and be cut off by `max_tokens`.

### Errors and timeouts

| Situation | Adapter | Gate |
|---|---|---|
| Upstream HTTP error, network error, timeout (`KUBRICK_VLM_TIMEOUT`) | 502 | UNVERIFIED, blocks |
| Reply without `choices[0].message.content` | 502 | UNVERIFIED, blocks |
| Adapter down | none | UNVERIFIED, blocks (judge timeout 120 s by default) |
| `GET /api/tags` with the upstream down | 502 | (health only) |

`GET /api/version` answers without calling the upstream, so the launcher can
tell "adapter up" from "upstream reachable".

## Example profile: the Spark box

`profiles/spark.env.example` points at the Zero State Spark box (Qwen3.5
vision served by SGLang). It needs two settings learned on 2026-10-04: a
`User-Agent` header, because the CDN in front answers HTTP 403 to Python's
default one, and `{"chat_template_kwargs": {"enable_thinking": false}}`,
because with thinking on the answer lands in `reasoning_content`. The key is
read from `SPARK_API_KEY` or `~/.config/spark/api_key`. Routing the judge to
Spark is an owner-approved spend and data boundary (Danny, 2026-10-04); the
loopback rule cannot tell that a proxy forwards.

```bash
bash tools/board_vision/setup.sh proxy --profile tools/board_vision/profiles/spark.env.example --name spark
kubrick-vlm-spark start
```
