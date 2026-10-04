#!/usr/bin/env python3
"""Release-version surface tests for issue #23."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from version_surfaces import (  # noqa: E402
    ENGINE_SOURCE,
    ENVELOPE_SCHEMA_VERSION,
    INSTALLER_RECEIPT_SCHEMA_VERSION,
    SURFACE_COMMON_SOURCE,
    build_report,
)


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _aligned(root: Path, version: str = "0.18.0") -> None:
    _write(root, "VERSION", version + "\n")
    _write(root, "kubrick.manifest.yaml", json.dumps({"version": version}))
    _write(root, "pyproject.toml", f'[project]\nname = "kubrick-skill"\nversion = "{version}"\n')
    _write(
        root,
        "SKILL.md",
        "---\nname: kubrick\nversion: "
        + version
        + "\n---\nSee docs/ROADMAP.md and CHANGELOG.md.\n",
    )
    _write(
        root,
        "README.md",
        f"<em>{version} — Prompt fidelity and Keyframe</em>\n"
        "docs/ROADMAP.md\nCHANGELOG.md\n",
    )
    _write(root, "CHANGELOG.md", f"## [{version}] — 2026-10-02\n")
    _write(root, "docs/ROADMAP.md", "# Roadmap\n")
    _write(root, "docs/RELEASE-CHECKLIST.md", f"- [x] aligned to v{version}\n")
    _write(root, ENGINE_SOURCE, 'SCHEMA_VERSION = "0.16.0"\n')
    _write(root, SURFACE_COMMON_SOURCE, '{ "schema_version": "0.16.0" }\n')


def test_repo_surfaces_match_product_version() -> None:
    report = build_report(ROOT)
    assert report["status"] == "READY", report["mismatches"]
    assert report["expected_version"] == "0.24.0"
    assert report["tag_allowed"] is True
    declarations = report["declarations"]
    assert isinstance(declarations, dict)
    for name, observed in declarations.items():
        assert observed == "0.24.0", (name, observed)
    envelopes = report["envelope_schema_versions"]
    assert envelopes == {
        ENGINE_SOURCE: ENVELOPE_SCHEMA_VERSION,
        SURFACE_COMMON_SOURCE: ENVELOPE_SCHEMA_VERSION,
    }
    schemas = report["non_tracking_schemas"]
    assert schemas["installer_receipt"] == INSTALLER_RECEIPT_SCHEMA_VERSION
    assert schemas["production_envelope"] == "0.16.0"
    assert report["mismatches"] == []
    rendered = json.dumps(report)
    assert "installer_receipt" in rendered
    assert INSTALLER_RECEIPT_SCHEMA_VERSION != "0.18.0"


def test_manifest_drift_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _aligned(root)
        _write(root, "kubrick.manifest.yaml", json.dumps({"version": "0.16.0"}))
        report = build_report(root)
    assert report["status"] == "NOT_READY"
    mismatches = report["mismatches"]
    assert isinstance(mismatches, list)
    found = [item for item in mismatches if item["file"] == "kubrick.manifest.yaml"]
    assert found and found[0]["observed"] == "0.16.0"
    assert found[0]["expected"] == "0.18.0"


def test_envelope_schema_does_not_track_product_version() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _aligned(root)
        report = build_report(root)
        assert report["mismatches"] == []
        assert report["envelope_schema_versions"][ENGINE_SOURCE] == "0.16.0"
        _write(root, ENGINE_SOURCE, 'SCHEMA_VERSION = "0.18.0"\n')
        drifted = build_report(root)
    mismatches = drifted["mismatches"]
    assert isinstance(mismatches, list)
    engine = [item for item in mismatches if item["file"] == ENGINE_SOURCE]
    assert engine and engine[0]["expected"] == "0.16.0"
    assert engine[0]["observed"] == "0.18.0"
    assert "does not track the product version" in str(engine[0]["reason"])


def test_archived_version_files_do_not_satisfy_the_current_set() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _aligned(root)
        (root / "docs/ROADMAP.md").unlink()
        (root / "docs/RELEASE-CHECKLIST.md").unlink()
        _write(root, "docs/archive/releases/ROADMAP-v0.18.md", "# Roadmap\n")
        _write(
            root,
            "docs/archive/releases/RELEASE-CHECKLIST-v0.18.md",
            "- [x] aligned to v0.18.0\n",
        )
        report = build_report(root)
    assert report["status"] == "NOT_READY"
    mismatches = report["mismatches"]
    assert isinstance(mismatches, list)
    files = {item["file"] for item in mismatches}
    assert "docs/ROADMAP.md" in files
    assert "docs/RELEASE-CHECKLIST.md" in files


def test_mirror_copy_is_audited() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _aligned(root)
        _write(root, "skills/kubrick/VERSION", "0.16.0\n")
        _write(root, "skills/kubrick/kubrick.manifest.yaml", json.dumps({"version": "0.18.0"}))
        _write(root, "skills/kubrick/pyproject.toml", '[project]\nversion = "0.18.0"\n')
        _write(root, "skills/kubrick/SKILL.md", "version: 0.18.0\n")
        report = build_report(root)
    mismatches = report["mismatches"]
    assert isinstance(mismatches, list)
    mirror = [item for item in mismatches if item["file"] == "skills/kubrick/VERSION"]
    assert mirror and mirror[0]["observed"] == "0.16.0"


def main() -> None:
    test_repo_surfaces_match_product_version()
    test_manifest_drift_is_rejected()
    test_envelope_schema_does_not_track_product_version()
    test_archived_version_files_do_not_satisfy_the_current_set()
    test_mirror_copy_is_audited()
    print("version surface tests: PASS")


if __name__ == "__main__":
    main()
