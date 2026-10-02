#!/usr/bin/env python3
"""Product-version surfaces for a Kubrick release.

The 0.17.0 smoke failure happened because VERSION moved and
kubrick.manifest.yaml stayed on 0.16.0. validate_manifest.py compares those
two, but the installer did not run the release audit, and hub sync only
byte-compares trees. A drift copied into both trees stays invisible.

The production envelope schema id is 0.16.0. It does not track the product
version. Goldens and tests pin it. The installer receipt schema id is 1.0.0
and does not track the product version either.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path

ENVELOPE_SCHEMA_VERSION = "0.16.0"
INSTALLER_RECEIPT_SCHEMA_VERSION = "1.0.0"

_SKILL_VERSION = re.compile(r"^version:\s*([^\s]+)", re.MULTILINE)
_README_VERSION = re.compile(r"<em>(0\.\d+\.\d+)\s+—")
_CHANGELOG_VERSION = re.compile(r"^## \[(0\.\d+\.\d+)\]", re.MULTILINE)
_NOTES_VERSION = re.compile(r"^# Kubrick v(0\.\d+\.\d+) Release Notes", re.MULTILINE)
_ENGINE_SCHEMA = re.compile(r'^SCHEMA_VERSION = "([^"]+)"', re.MULTILINE)
_COMPILER_SCHEMA = re.compile(r'"schema_version": "([^"]+)"')
_PYPROJECT_VERSION = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)


def product_version(root: Path) -> str:
    path = root / "VERSION"
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _read(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _mismatch(file: str, expected: object, observed: object, reason: str) -> dict[str, object]:
    return {"file": file, "expected": expected, "observed": observed, "reason": reason}


def manifest_version(path: Path) -> str | None:
    text = _read(path)
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    version = data.get("version") if isinstance(data, dict) else None
    return version if isinstance(version, str) else None


def pyproject_version(text: str) -> str | None:
    if "[project]" not in text:
        return None
    section = text.split("[project]", 1)[1].split("[", 1)[0]
    match = _PYPROJECT_VERSION.search(section)
    return match.group(1) if match else None


def _search(text: str, pattern: re.Pattern[str]) -> str | None:
    if not text:
        return None
    match = pattern.search(text)
    return match.group(1) if match else None


def release_names(version: str) -> tuple[str, str, str]:
    line = ".".join(version.split(".")[:2]) if version else "0.0"
    return (
        f"docs/RELEASE-NOTES-v{line}.md",
        f"docs/ROADMAP-v{line}.md",
        f"docs/RELEASE-CHECKLIST-v{line}.md",
    )


def text_declarations(root: Path, version: str) -> dict[str, str | None]:
    notes, _roadmap, _checklist = release_names(version)
    skill = _read(root / "SKILL.md")
    readme = _read(root / "README.md")
    changelog = _read(root / "CHANGELOG.md")
    notes_text = _read(root / notes)
    return {
        "SKILL.md": _search(skill, _SKILL_VERSION),
        "README.md": _search(readme, _README_VERSION),
        "CHANGELOG.md": _search(changelog, _CHANGELOG_VERSION),
        notes: _search(notes_text, _NOTES_VERSION),
    }


def reference_checks(root: Path, version: str) -> dict[str, dict[str, bool]]:
    notes, roadmap, checklist = release_names(version)
    required = {
        "README.md": [roadmap, notes],
        "SKILL.md": [roadmap, notes],
        checklist: [f"v{version}"],
    }
    checks: dict[str, dict[str, bool]] = {}
    for relative, values in required.items():
        text = _read(root / relative)
        checks[relative] = {value: value in text for value in values}
    return checks


def envelope_schema_versions(root: Path) -> dict[str, str | None]:
    engine = _read(root / "scripts/production_engine.py")
    compilers = _read(root / "scripts/surface_compilers.py")
    return {
        "scripts/production_engine.py": _search(engine, _ENGINE_SCHEMA),
        "scripts/surface_compilers.py": _search(compilers, _COMPILER_SCHEMA),
    }


def envelope_mismatches(found: Mapping[str, str | None]) -> list[dict[str, object]]:
    mismatches: list[dict[str, object]] = []
    for name, observed in found.items():
        if observed == ENVELOPE_SCHEMA_VERSION:
            continue
        mismatches.append(
            _mismatch(
                name,
                ENVELOPE_SCHEMA_VERSION,
                observed,
                "envelope schema id must stay 0.16.0 and does not track the product version",
            )
        )
    return mismatches


def _record(
    declarations: dict[str, str | None],
    mismatches: list[dict[str, object]],
    file: str,
    expected: str,
    observed: str | None,
) -> None:
    declarations[file] = observed
    if observed != expected:
        reason = "version mismatch" if observed is not None else "missing file"
        mismatches.append(_mismatch(file, expected, observed, reason))


def mirror_declarations(
    root: Path,
    expected: str,
) -> tuple[dict[str, str | None], list[dict[str, object]]]:
    hub = root / "skills" / "kubrick"
    declarations: dict[str, str | None] = {}
    mismatches: list[dict[str, object]] = []
    if not hub.is_dir():
        return declarations, mismatches
    version_file = hub / "VERSION"
    if version_file.is_file():
        observed_version = version_file.read_text(encoding="utf-8").strip()
    else:
        observed_version = None
    _record(declarations, mismatches, "skills/kubrick/VERSION", expected, observed_version)
    _record(
        declarations,
        mismatches,
        "skills/kubrick/kubrick.manifest.yaml",
        expected,
        manifest_version(hub / "kubrick.manifest.yaml"),
    )
    _record(
        declarations,
        mismatches,
        "skills/kubrick/pyproject.toml",
        expected,
        pyproject_version(_read(hub / "pyproject.toml")),
    )
    _record(
        declarations,
        mismatches,
        "skills/kubrick/SKILL.md",
        expected,
        _search(_read(hub / "SKILL.md"), _SKILL_VERSION),
    )
    return declarations, mismatches


def build_report(root: Path) -> dict[str, object]:
    expected = product_version(root)
    declarations: dict[str, str | None] = {"VERSION": expected or None}
    mismatches: list[dict[str, object]] = []
    if not expected:
        mismatches.append(_mismatch("VERSION", "non-empty version", None, "missing file"))

    manifest = manifest_version(root / "kubrick.manifest.yaml")
    _record(declarations, mismatches, "kubrick.manifest.yaml", expected, manifest)
    _record(
        declarations,
        mismatches,
        "pyproject.toml",
        expected,
        pyproject_version(_read(root / "pyproject.toml")),
    )
    for relative, observed in text_declarations(root, expected).items():
        _record(declarations, mismatches, relative, expected, observed)

    checks = reference_checks(root, expected)
    for relative, values in checks.items():
        for value, present in values.items():
            if not present:
                mismatches.append(
                    _mismatch(relative, value, None, "missing current release reference")
                )

    mirror, mirror_mismatches = mirror_declarations(root, expected)
    declarations.update(mirror)
    mismatches.extend(mirror_mismatches)

    envelopes = envelope_schema_versions(root)
    mismatches.extend(envelope_mismatches(envelopes))

    return {
        "status": "READY" if not mismatches else "NOT_READY",
        "expected_version": expected,
        "declarations": declarations,
        "reference_checks": checks,
        "envelope_schema_versions": envelopes,
        "non_tracking_schemas": {
            "production_envelope": ENVELOPE_SCHEMA_VERSION,
            "installer_receipt": INSTALLER_RECEIPT_SCHEMA_VERSION,
        },
        "mismatches": mismatches,
        "tag_allowed": not mismatches,
    }
