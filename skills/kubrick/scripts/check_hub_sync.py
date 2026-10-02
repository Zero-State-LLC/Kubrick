#!/usr/bin/env python3
"""Fail CI when skills/kubrick drifts from the root skill payload.

The hub layout under skills/kubrick is a packaging mirror. Root remains the
source of truth; this gate forces an explicit sync via scripts/sync_hub_skill.sh.
"""
from __future__ import annotations

import argparse
import filecmp
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HUB = ROOT / "skills" / "kubrick"

# Paths compared relative to ROOT / HUB. Keep in sync with sync_hub_skill.sh excludes.
COMPARE_ROOTS = [
    "SKILL.md",
    "VERSION",
    "LICENSE",
    "CHANGELOG.md",
    "QUICKSTART.md",
    "README.md",
    "kubrick.manifest.yaml",
    "pyproject.toml",
    "requirements.txt",
    "install.sh",
    "scripts",
    "schemas",
    "references",
    "examples",
    "templates",
    "evals",
    "docs",
    "assets",
]

EXCLUDE_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".git",
    ".github",
    "out",
    "dist",
    "skills",
    "usage",
}
EXCLUDE_FILE_NAMES = {
    "package_optional_skill.sh",
    "sync_hub_skill.sh",
    "PR_BODY.md",
    "PR_BODY_HARDENING.md",
    "PUSH_INSTRUCTIONS.md",
}


def iter_files(base: Path) -> set[str]:
    found: set[str] = set()
    if not base.exists():
        return found
    if base.is_file():
        return {base.name}

    for path in base.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(base).parts
        if any(part in EXCLUDE_DIR_NAMES for part in rel_parts[:-1]):
            continue
        if path.name in EXCLUDE_FILE_NAMES:
            continue
        found.add(path.relative_to(base).as_posix())
    return found


def collect_mismatches() -> list[str]:
    errors: list[str] = []
    if not HUB.is_dir():
        # Packaged Hermes optional-skill installs omit the hub mirror on purpose.
        if not (ROOT / ".git").exists():
            return []
        return ["skills/kubrick missing — run scripts/sync_hub_skill.sh"]

    for relative in COMPARE_ROOTS:
        src = ROOT / relative
        dst = HUB / relative
        if not src.exists():
            continue
        if src.is_file():
            if not dst.is_file():
                errors.append(f"hub missing file: {relative}")
            elif not filecmp.cmp(src, dst, shallow=False):
                errors.append(f"hub drift: {relative}")
            continue

        src_files = iter_files(src)
        dst_files = iter_files(dst)
        # Hub may omit packaging-only scripts; ignore those filenames everywhere.
        src_files = {f for f in src_files if Path(f).name not in EXCLUDE_FILE_NAMES}
        dst_files = {f for f in dst_files if Path(f).name not in EXCLUDE_FILE_NAMES}
        missing = sorted(src_files - dst_files)
        extra = sorted(dst_files - src_files)
        for item in missing:
            errors.append(f"hub missing: {relative}/{item}")
        for item in extra:
            # Allow hub to lag on brand-new hardening helpers only if absent from sync excludes;
            # extras still fail to keep the mirror strict.
            errors.append(f"hub extra: {relative}/{item}")
        for item in sorted(src_files & dst_files):
            if not filecmp.cmp(src / item, dst / item, shallow=False):
                errors.append(f"hub drift: {relative}/{item}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    errors = collect_mismatches()
    payload = {
        "status": "PASS" if not errors else "FAIL",
        "error_count": len(errors),
        "errors": errors[:200],
        "hint": "run: bash scripts/sync_hub_skill.sh",
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        if errors:
            print("skills/kubrick hub sync: FAIL", file=sys.stderr)
            for err in errors[:50]:
                print(f"  - {err}", file=sys.stderr)
            if len(errors) > 50:
                print(f"  … {len(errors) - 50} more", file=sys.stderr)
            print("Fix: bash scripts/sync_hub_skill.sh", file=sys.stderr)
        else:
            print("skills/kubrick hub sync: PASS")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
