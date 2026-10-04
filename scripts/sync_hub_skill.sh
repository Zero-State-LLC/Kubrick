#!/usr/bin/env bash
# Sync root development package into skills/kubrick for Hermes hub/tap discovery.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${KUBRICK_HUB_DEST:-${ROOT}/skills/kubrick}"
mkdir -p "${DEST}"

copy_tree() {
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
      --exclude '.git/' \
      --exclude '.github/' \
      --exclude 'skills/' \
      --exclude 'out/' \
      --exclude 'dist/' \
      --exclude '__pycache__/' \
      --exclude '**/__pycache__/' \
      --exclude '.mypy_cache/' \
      --exclude '.ruff_cache/' \
      --exclude '.pytest_cache/' \
      --exclude '*.pyc' \
      --exclude 'PR_BODY.md' \
      --exclude 'PR_BODY_HARDENING.md' \
      --exclude 'PUSH_INSTRUCTIONS.md' \
      --exclude 'scripts/package_optional_skill.sh' \
      --exclude 'scripts/sync_hub_skill.sh' \
      --exclude 'tests/' \
      "${ROOT}/" "${DEST}/"
  else
    rm -rf "${DEST}"
    mkdir -p "${DEST}"
    tar -C "${ROOT}" \
      --exclude '.git' \
      --exclude '.github' \
      --exclude 'skills' \
      --exclude 'out' \
      --exclude 'dist' \
      --exclude '__pycache__' \
      --exclude '.mypy_cache' \
      --exclude '.ruff_cache' \
      --exclude '.pytest_cache' \
      --exclude '*.pyc' \
      --exclude 'PR_BODY.md' \
      --exclude 'PR_BODY_HARDENING.md' \
      --exclude 'PUSH_INSTRUCTIONS.md' \
      --exclude 'tests' \
      --exclude 'scripts/package_optional_skill.sh' \
      --exclude 'scripts/sync_hub_skill.sh' \
      -cf - . | tar -C "${DEST}" -xf -
  fi
}

copy_tree
find "${DEST}" -type d \( -name '__pycache__' -o -name '.mypy_cache' -o -name '.ruff_cache' -o -name '.pytest_cache' \) -prune -exec rm -rf {} + 2>/dev/null || true
find "${DEST}" -type f -name '*.pyc' -delete 2>/dev/null || true
rm -f "${DEST}/scripts/package_optional_skill.sh" "${DEST}/scripts/sync_hub_skill.sh" \
  "${DEST}/PR_BODY.md" "${DEST}/PR_BODY_HARDENING.md" "${DEST}/PUSH_INSTRUCTIONS.md" 2>/dev/null || true
echo "Synced root → ${DEST}"
echo "files: $(find "${DEST}" -type f | wc -l)"
