#!/usr/bin/env python3
"""Labeled image manifest for board image gate calibration.

Format (JSON), see evals/calibration/board-image-ep01/manifest.json:

- ``roots``: ``{name: directory}``. An item ``path`` is ``<root name>/<relative path>``.
  Override a root with ``--root name=DIR`` or ``KUBRICK_CALIB_ROOT_<NAME>``.
- ``character``: the plan character id the lock questions name.
- ``refs``: ``{group: [path, ...]}`` identity references.
- ``questions``: ``{key: {question, expect}}`` direct judge questions (judge accuracy).
- ``board_checks``: extra gate checks added to the character spec (gate runs).
- ``items``: ``id``, ``path``, ``kind`` (board, frame, offmodel), ``identity``
  (keep, drift, alt, na, offmodel), ``note``, ``sha256``, optional ``truth``
  (``{question key or "gate:<lock id>": "yes" | "no"}``; for a gate lock ``yes``
  means the image keeps the lock), and optional ``pins``
  (``{keyword: true answer}`` for any gate question that contains the keyword).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
_SRC = str(ROOT / "src")


def use_repo_paths() -> None:
    """Put the repo ``src`` first (never let scripts/kubrick.py shadow it) and the root next."""
    if sys.path[:1] != [_SRC]:
        while _SRC in sys.path:
            sys.path.remove(_SRC)
        sys.path.insert(0, _SRC)
    if str(ROOT) not in sys.path:
        sys.path.insert(1, str(ROOT))


def load(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise SystemExit(f"{path}: not a calibration manifest (no items list)")
    return data


def roots(manifest: Mapping[str, Any], overrides: Sequence[str] = ()) -> dict[str, str]:
    found = {str(k): str(v) for k, v in (manifest.get("roots") or {}).items()}
    for name in list(found):
        env = os.environ.get(f"KUBRICK_CALIB_ROOT_{name.upper()}", "").strip()
        if env:
            found[name] = env
    for item in overrides:
        name, sep, folder = item.partition("=")
        if not sep:
            raise SystemExit(f"--root wants name=DIR, not {item!r}")
        found[name] = folder
    return found


def resolve(path: str, root_map: Mapping[str, str]) -> str:
    name, _, rest = path.partition("/")
    if name not in root_map:
        raise SystemExit(f"unknown root {name!r} in {path!r}")
    return str(Path(root_map[name]) / rest)


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(items: Iterable[Mapping[str, Any]], root_map: Mapping[str, str]) -> list[str]:
    """Problems with the local copy of the set: missing files or changed bytes."""
    problems = []
    for item in items:
        path = resolve(item["path"], root_map)
        if not os.path.isfile(path):
            problems.append(f"missing {item['path']} ({path})")
        elif item.get("sha256") and sha256(path) != item["sha256"]:
            problems.append(f"changed {item['path']} (sha256 differs)")
    return problems


def gate_items(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Items with at least one ``gate:<lock>`` truth label (the gate A/B set)."""
    return [item for item in manifest["items"]
            if any(key.startswith("gate:") for key in item.get("truth", {}))]


def defective(item: Mapping[str, Any]) -> bool:
    return any(value == "no" for key, value in item.get("truth", {}).items()
               if key.startswith("gate:"))


class ResultFile:
    """JSON results written after every row (atomic replace), resumable by key."""

    def __init__(self, path: str | Path, header: Mapping[str, Any], key: str = "path") -> None:
        self.path = Path(path)
        self.header = dict(header)
        self.key = key
        self.rows: dict[str, dict[str, Any]] = {}
        self.order: list[str] = []
        self._lock = threading.Lock()
        if self.path.exists():
            for row in json.loads(self.path.read_text(encoding="utf-8")).get("rows", []):
                self.rows[row[key]] = row

    def done(self, key: str) -> bool:
        return key in self.rows

    def add(self, row: dict[str, Any]) -> None:
        with self._lock:
            self.rows[row[self.key]] = row
            self._write()

    def save(self, order: Sequence[str]) -> dict[str, Any]:
        with self._lock:
            self.order = list(order)
            return self._write()

    def _write(self) -> dict[str, Any]:
        keys = self.order or list(self.rows)
        data = dict(self.header, rows=[self.rows[k] for k in keys if k in self.rows])
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)
        return data


def add_common_args(parser: Any) -> None:
    parser.add_argument("--manifest", default=str(ROOT / "evals/calibration/board-image-ep01/"
                                                  "manifest.json"))
    parser.add_argument("--root", action="append", default=[], metavar="NAME=DIR",
                        help="override an image root from the manifest")
    parser.add_argument("--verify", action="store_true",
                        help="check every image exists and matches its sha256 first")
