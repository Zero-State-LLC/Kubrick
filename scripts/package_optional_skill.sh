#!/usr/bin/env bash
# Package Kubrick for NousResearch/hermes-agent optional-skills/creative/kubrick.
# Usage:
#   ./scripts/package_optional_skill.sh /path/to/hermes-agent
#   ./scripts/package_optional_skill.sh ./dist/hermes-agent-package
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_ROOT="${1:-}"

if [[ -z "${DEST_ROOT}" ]]; then
  echo "Usage: $0 <hermes-agent-repo-or-output-dir>" >&2
  exit 2
fi

TARGET="${DEST_ROOT%/}/optional-skills/creative/kubrick"
mkdir -p "${TARGET}"

# Core skill payload only: exclude git metadata, CI, historical planning docs,
# and packaging helpers that are not needed inside hermes-agent.
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete \
    --exclude '.git/' \
    --exclude '.github/' \
    --exclude 'dist/' \
    --exclude 'out/' \
    --exclude '__pycache__/' \
    --exclude '**/__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.pytest_cache/' \
    --exclude '.mypy_cache/' \
    --exclude '.ruff_cache/' \
    --exclude 'docs/archive/' \
    --exclude 'PR_BODY.md' \
    --exclude 'PR_BODY_HARDENING.md' \
    --exclude 'PUSH_INSTRUCTIONS.md' \
    --exclude 'scripts/package_optional_skill.sh' \
    --exclude 'scripts/sync_hub_skill.sh' \
    --exclude 'tests/' \
    --exclude 'skills/' \
    --exclude 'skills.sh.json' \
    "${ROOT}/" "${TARGET}/"
else
  rm -rf "${TARGET}"
  mkdir -p "${TARGET}"
  tar -C "${ROOT}" \
    --exclude '.git' \
    --exclude '.github' \
    --exclude 'dist' \
    --exclude 'out' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.pytest_cache' \
    --exclude '.mypy_cache' \
    --exclude '.ruff_cache' \
    --exclude 'docs/archive' \
    --exclude 'PR_BODY.md' \
    --exclude 'PR_BODY_HARDENING.md' \
    --exclude 'PUSH_INSTRUCTIONS.md' \
    --exclude 'scripts/package_optional_skill.sh' \
    --exclude 'scripts/sync_hub_skill.sh' \
    --exclude 'tests' \
    --exclude 'skills' \
    --exclude 'skills.sh.json' \
    -cf - . | tar -C "${TARGET}" -xf -
fi

# Repository-level tests live outside the optional skill payload in hermes-agent.
mkdir -p "${DEST_ROOT%/}/tests/skills"
cp "${ROOT}/tests/hermes-agent/test_kubrick_skill.py" \
  "${DEST_ROOT%/}/tests/skills/test_kubrick_skill.py"

# Drop any accidental caches that slipped through
find "${TARGET}" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "${TARGET}" -type f -name '*.pyc' -delete 2>/dev/null || true

echo "Packaged → ${TARGET}"
echo
echo "File inventory (depth ≤3):"
find "${TARGET}" -maxdepth 3 -type f | sort | head -200
echo "…"
echo "Total files: $(find "${TARGET}" -type f | wc -l)"
echo
echo "Sanity checks:"
test -f "${TARGET}/SKILL.md"
test -f "${TARGET}/LICENSE"
test -f "${TARGET}/examples/authority-transfer-storyboard/brief.yaml"
test -f "${TARGET}/examples/authority-transfer-storyboard/symbolic-ledger.yaml"
test -f "${TARGET}/examples/authority-transfer-storyboard/storyboard-plan.yaml"
test -f "${DEST_ROOT%/}/tests/skills/test_kubrick_skill.py"
python3 - "${TARGET}" <<'PY'
import re
import sys
from pathlib import Path

skill = Path(sys.argv[1]) / "SKILL.md"
text = skill.read_text(encoding="utf-8")
match = re.search(r"^description: (.*)$", text, re.MULTILINE)
assert match, "description must be a single-line frontmatter field"
description = match.group(1)
assert len(description) <= 60, len(description)
assert description.endswith("."), description

headings = [
    "# Kubrick Skill",
    "## When to Use",
    "## Prerequisites",
    "## How to Run",
    "## Quick Reference",
    "## Procedure",
    "## Pitfalls",
    "## Verification",
]
positions = [text.index(heading) for heading in headings]
assert positions == sorted(positions), "SKILL.md section order is not Hermes-compatible"
PY
! rg -n '/home/|/Users/[A-Za-z]' "${TARGET}/SKILL.md" "${TARGET}/README.md" "${TARGET}/QUICKSTART.md" || true
rg -n 'license:|author:|name: kubrick' "${TARGET}/SKILL.md" | head -10
echo
echo "Next:"
echo "  cd ${DEST_ROOT}"
echo "  git checkout -b feat/add-kubrick-skill   # if this is a hermes-agent checkout"
echo "  git add optional-skills/creative/kubrick"
echo "  git commit -m 'feat(skills): add Kubrick cinematic design skill'"
