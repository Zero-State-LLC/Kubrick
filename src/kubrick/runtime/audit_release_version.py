#!/usr/bin/env python3
"""Audit Kubrick release-version declarations against the VERSION manifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from kubrick.paths import SKILL_ROOT
from kubrick.runtime.version_surfaces import build_report

ROOT = SKILL_ROOT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    report = build_report(ROOT)
    rendered = json.dumps(report, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered)
    mismatches = report["mismatches"]
    raise SystemExit(1 if args.strict and mismatches else 0)


if __name__ == "__main__":
    main()
