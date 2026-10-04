#!/usr/bin/env python3
"""Health check for the reference Jev adapter. Uses the local fixture only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
for folder in (ROOT, SCRIPTS):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from jev_client import JevUnreachable, parse_verdict  # noqa: E402

from tools.jev_adapter.adapter import judge_fixture  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "health.json"


def health_check(path: Path | None = None) -> dict[str, object]:
    """Judge the fixture prompt and require a parseable verdict. No network."""
    fixture_path = FIXTURE if path is None else path
    try:
        raw = json.loads(fixture_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "network": False, "reason": f"fixture unreadable: {exc}"}
    if not isinstance(raw, dict):
        return {"ok": False, "network": False, "reason": "fixture must be an object"}
    prompt = raw.get("prompt")
    holds = raw.get("holds")
    if not isinstance(prompt, dict) or not isinstance(holds, list):
        return {"ok": False, "network": False, "reason": "fixture prompt or holds missing"}
    hold_rows = [item for item in holds if isinstance(item, dict)]
    judged = judge_fixture(prompt, hold_rows, raw)
    try:
        parsed = parse_verdict(judged)
    except JevUnreachable as exc:
        return {"ok": False, "network": False, "reason": exc.reason}
    expect = raw.get("expect")
    if not isinstance(expect, dict) or parsed.get("verdict") != expect.get("verdict"):
        return {"ok": False, "network": False, "reason": "verdict does not match the fixture"}
    return {
        "ok": True,
        "network": False,
        "verdict": parsed["verdict"],
        "fixture": fixture_path.name,
    }


def main() -> int:
    result = health_check()
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") is True else 1


if __name__ == "__main__":
    sys.exit(main())
