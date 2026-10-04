#!/usr/bin/env bash
# One-command setup for the Kubrick board image gate judge on an operator box.
#
#   bash tools/board_vision/setup.sh proxy --profile FILE [--name NAME]
#   bash tools/board_vision/setup.sh ollama [--profile FILE]   # default profiles/ollama-local.env.example
#   bash tools/board_vision/setup.sh none          # deps, launchers, env, fail-closed test
#
# proxy: any OpenAI-compatible vision endpoint through the loopback adapter.
#   FILE is a profile (see profiles/*.env.example). It is copied to
#   ~/.config/kubrick/vlm-NAME.env if absent, and kubrick-vlm-NAME is linked
#   to kubrick-vlm-proxy. NAME defaults to the profile file name before ".env".
#
# Steps (each is safe to rerun):
#   1. install the board-vision extra (torch, transformers, Pillow) into $KUBRICK_PYTHON
#   2. download the DINOv2 embedder (and the Ollama model for the ollama backend)
#   3. link the launchers into $KUBRICK_BIN (default ~/bin)
#   4. copy board-vision.env.example to ~/.config/kubrick/board-vision.env if absent
#   5. start the backend, run the health check, then the fail-closed test
#
# No secrets are read or written here. The proxy reads its key at start from
# the env var or file the profile names.
# Env: KUBRICK_PYTHON (default python3), KUBRICK_BIN, KUBRICK_CONFIG_DIR,
# KUBRICK_SETUP_SKIP_PIP=1, KUBRICK_SETUP_SKIP_DOWNLOAD=1.
set -euo pipefail
usage() { sed -n '3,6p' "$0" | sed 's/^# //' >&2; exit 2; }
BACKEND=${1:-}; [ $# -gt 0 ] && shift
PROFILE=""; NAME=""
while [ $# -gt 0 ]; do
  case "$1" in
    --profile) PROFILE=${2:-}; shift 2 ;;
    --name) NAME=${2:-}; shift 2 ;;
    *) usage ;;
  esac
done
case "$BACKEND" in
  proxy) [ -f "$PROFILE" ] || { echo "proxy needs --profile FILE" >&2; usage; } ;;
  ollama) PROFILE=${PROFILE:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/profiles/ollama-local.env.example} ;;
  none) ;;
  *) usage ;;
esac
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
PY=${KUBRICK_PYTHON:-python3}
BIN=${KUBRICK_BIN:-$HOME/bin}
CONF=${KUBRICK_CONFIG_DIR:-$HOME/.config/kubrick}
if [ "$BACKEND" = proxy ] && [ -z "$NAME" ]; then
  NAME=$(basename "$PROFILE"); NAME=${NAME%%.env*}
fi
case "$NAME" in ""|*[!a-z0-9_-]*) [ "$BACKEND" != proxy ] || { echo "bad --name $NAME" >&2; exit 2; } ;; esac
step() { printf '\n== %s\n' "$1"; }

step "1/5 board-vision extra into $("$PY" -c 'import sys; print(sys.prefix)')"
if [ "${KUBRICK_SETUP_SKIP_PIP:-0}" != 1 ]; then
  # Editable install is safe since 0.27.0: the scripts/ shims always put src first.
  "$PY" -m pip install -q -e "$ROOT[board-vision]"
else echo "skipped (KUBRICK_SETUP_SKIP_PIP=1)"; fi

step "2/5 model downloads"
if [ "${KUBRICK_SETUP_SKIP_DOWNLOAD:-0}" != 1 ]; then
  EMBED=${KUBRICK_BOARD_EMBED_MODEL:-facebook/dinov2-small}
  "$PY" -c "import sys, transformers as t; [f.from_pretrained(sys.argv[1]) for f in (t.AutoImageProcessor, t.AutoModel)]; print('embedder ready:', sys.argv[1])" "$EMBED"
  if [ "$BACKEND" = ollama ]; then
    mkdir -p "$CONF"; [ -e "$CONF/ollama.env" ] || cp "$PROFILE" "$CONF/ollama.env"
    "$HERE/kubrick-vlm" start
  fi
else echo "skipped (KUBRICK_SETUP_SKIP_DOWNLOAD=1)"; fi

step "3/5 launchers into $BIN"
mkdir -p "$BIN"
link() {
  local target=$1 name=$2
  if [ -e "$BIN/$name" ] && [ ! -L "$BIN/$name" ]; then
    cp -p "$BIN/$name" "$BIN/$name.bak-$(date +%Y%m%d-%H%M%S)"
  fi
  ln -sfn "$target" "$BIN/$name"; echo "$BIN/$name -> $target"
}
link "$HERE/kubrick-vlm" kubrick-vlm
link "$HERE/kubrick-vlm-proxy" kubrick-vlm-proxy
[ "$BACKEND" = proxy ] && [ "$NAME" != proxy ] && link "$HERE/kubrick-vlm-proxy" "kubrick-vlm-$NAME"

step "4/5 config files in $CONF"
mkdir -p "$CONF"
copy_once() {
  if [ -e "$2" ]; then echo "kept existing $2"; else cp "$1" "$2"; echo "wrote $2"; fi
}
copy_once "$HERE/board-vision.env.example" "$CONF/board-vision.env"
[ "$BACKEND" = proxy ] && copy_once "$PROFILE" "$CONF/vlm-$NAME.env"
[ "$BACKEND" = ollama ] && copy_once "$PROFILE" "$CONF/ollama.env"

step "5/5 start, health check, fail-closed test"
# shellcheck disable=SC1091
. "$CONF/board-vision.env"
case "$BACKEND" in
  proxy)
    "$BIN/kubrick-vlm-$NAME" start
    ADDR=$(set -a; . "$CONF/vlm-$NAME.env"; echo "${KUBRICK_VLM_PROXY_ADDR:-127.0.0.1:11435}")
    export KUBRICK_BOARD_VLM_URL="http://$ADDR" ;;
  ollama)
    eval "$(set -a; . "$CONF/ollama.env"; echo "export KUBRICK_BOARD_VLM_URL=http://${KUBRICK_OLLAMA_ADDR:-127.0.0.1:11434} KUBRICK_BOARD_VLM_MODEL=${KUBRICK_OLLAMA_MODEL}")" ;;
  none) echo "no backend started" ;;
esac
status=0
if [ "$BACKEND" != none ]; then "$PY" "$HERE/health.py" check || status=1; fi
"$PY" "$HERE/health.py" fail-closed || status=1
if [ "$status" = 0 ]; then echo "board vision setup: PASS"; else echo "board vision setup: FAIL" >&2; fi
exit "$status"
