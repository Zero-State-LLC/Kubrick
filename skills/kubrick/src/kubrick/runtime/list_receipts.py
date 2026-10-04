#!/usr/bin/env python3
"""List or inspect Kubrick production receipts (v0.16)."""
from __future__ import annotations

import argparse
import json

from kubrick.runtime.io_safety import resolve_bounded_path  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(prog="kubrick receipts")
    parser.add_argument("--root", default="out", help="Artifact root containing receipts/")
    parser.add_argument("--receipt-id")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    root = resolve_bounded_path(args.root, for_write=False)
    receipts_dir = root / "receipts" if (root / "receipts").is_dir() else root
    if not receipts_dir.exists():
        print(json.dumps({"status": "NOT_COMPUTABLE", "message": f"no receipts under {root}"}, indent=2))
        return 4

    files = sorted(receipts_dir.glob("*.json"))
    if args.receipt_id:
        files = [f for f in files if args.receipt_id in f.name]
    files = files[: max(1, args.limit)]
    items = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        items.append(
            {
                "path": str(path),
                "receipt_id": data.get("receipt_id") or path.stem,
                "receipt_hash": data.get("receipt_hash"),
                "surface": data.get("surface"),
                "action": data.get("action"),
                "timestamp": data.get("timestamp"),
            }
        )
    print(json.dumps({"status": "PASS", "count": len(items), "receipts": items}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
