#!/usr/bin/env python3
"""Compare adjacent Kubrick storyboard frames for continuity and intended mutation.

Fails closed: a frame without a non-empty string frame_id makes the result
NOT_COMPUTABLE (exit 4). Residue or convergence loss is INVALID (exit 1).
"""
from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from io_safety import PathSafetyError, write_text_bounded

_FIELDS = ("node_states", "motif_ownership", "object_states", "light_states", "material_states")
_EXIT = {"VALID": 0, "INVALID": 1, "NOT_COMPUTABLE": 4}


def load(path: str) -> object:
    source = Path(path)
    text = source.read_text(encoding="utf-8")
    if source.suffix == ".json":
        return json.loads(text)
    from runtime_deps import yaml_load

    loaded = yaml_load(text)
    return {} if loaded is None else loaded


def _map(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _frames(storyboard: Mapping[str, object]) -> list[Mapping[str, object]]:
    raw = storyboard.get("frames")
    if not isinstance(raw, list):
        return []
    return [_map(item) for item in raw]


def _id_errors(frames: Sequence[Mapping[str, object]]) -> list[str]:
    errors: list[str] = []
    for index, frame in enumerate(frames, start=1):
        ident = frame.get("frame_id")
        if not isinstance(ident, str) or not ident.strip():
            errors.append(f"frame {index} lacks a non-empty string frame_id")
    return errors


def _deltas(left: Mapping[str, object], right: Mapping[str, object]) -> dict[str, object]:
    deltas: dict[str, object] = {}
    for field in _FIELDS:
        a, b = _map(left.get(field)), _map(right.get(field))
        changed = {
            key: {"from": a.get(key), "to": b.get(key)}
            for key in sorted(set(a) | set(b))
            if a.get(key) != b.get(key)
        }
        if changed:
            deltas[field] = changed
    return deltas


def _lost(left: Mapping[str, object], right: Mapping[str, object], key: str) -> list[str]:
    return sorted(set(_strings(left.get(key))) - set(_strings(right.get(key))))


def _transition(
    left: Mapping[str, object], right: Mapping[str, object], errors: list[str],
) -> dict[str, object]:
    a, b = str(left.get("frame_id")), str(right.get("frame_id"))
    residue = _lost(left, right, "residue")
    convergence = _lost(left, right, "convergence_sites")
    resets = _strings(right.get("prohibited_resets"))
    if residue:
        errors.append(f"{a}->{b} lost residue: {residue}")
    if convergence:
        errors.append(f"{a}->{b} lost convergence: {convergence}")
    if resets:
        errors.append(f"{b} contains prohibited resets: {resets}")
    bad = bool(residue or convergence or resets)
    return {
        "from": a,
        "to": b,
        "deltas": _deltas(left, right),
        "residue_lost": residue,
        "convergence_lost": convergence,
        "required_mutations": _strings(right.get("required_mutations")),
        "status": "INVALID" if bad else "VALID",
    }


def compare(document: object) -> dict[str, object]:
    storyboard = _map(document)
    frames = _frames(storyboard)
    errors = _id_errors(frames)
    if not isinstance(document, Mapping):
        errors = ["storyboard is not a mapping"]
    transitions: list[dict[str, object]] = []
    if errors:
        status = "NOT_COMPUTABLE"
    else:
        for left, right in zip(frames, frames[1:]):
            transitions.append(_transition(left, right, errors))
        status = "INVALID" if errors else "VALID"
    return {
        "storyboard_id": storyboard.get("storyboard_id"),
        "transition_count": len(transitions),
        "transitions": transitions,
        "status": status,
        "errors": errors,
    }


def _write(path: str, text: str) -> None:
    from diagnostics import abort, diagnostic

    try:
        write_text_bounded(path, text)
    except PathSafetyError as exc:
        abort(diagnostic(
            status="NOT_COMPUTABLE",
            code="PATH_POLICY",
            exit_code=2,
            message=str(exc),
            context={"output": path},
        ))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storyboard", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    result = compare(load(args.storyboard))
    text = json.dumps(result, indent=2)
    if args.output:
        _write(args.output, text)
    print(text)
    raise SystemExit(_EXIT[str(result["status"])])


if __name__ == "__main__":
    main()
