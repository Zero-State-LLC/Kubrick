#!/usr/bin/env python3
"""Retake impact against observed takes. Issue #37.

Takes are OBSERVATION. They are never written back onto the storyboard.
A downstream take's ``observed_start_state`` is what that take was cut against.
When it is omitted, the declared storyboard start is used. Equal text, or the
same resolved state id, is a match. A token that starts with a state id and a
space resolves to that id. ``prop_assignments`` errors fail closed.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence

from continuity_locks import frame_field, frame_id, prop_assignments, resolve_state, warning
from io_safety import load_structured, write_structured

_ARROW = "->"


def _labels(frame: Mapping[str, object], index: int) -> set[str]:
    labels = {frame_id(frame, index)}
    raw = frame_field(frame, "shot_id")
    if isinstance(raw, str) and raw.strip():
        labels.add(raw.strip())
    return labels


def _shot_name(frame: Mapping[str, object], index: int) -> str:
    raw = frame_field(frame, "shot_id")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return frame_id(frame, index)


def _states(document: Mapping[str, object], prop_id: str) -> dict[str, str]:
    props = document.get("props")
    if not isinstance(props, Mapping):
        return {}
    prop = props.get(prop_id)
    if not isinstance(prop, Mapping):
        return {}
    raw = prop.get("states")
    if not isinstance(raw, Mapping):
        return {}
    return {str(key): str(value) for key, value in raw.items()}


def _resolve(states: Mapping[str, str], token: str) -> str | None:
    found = resolve_state(states, token)
    if found is not None:
        return found
    folded = token.strip().casefold()
    hits = [key for key in states if folded.startswith(key.casefold() + " ")]
    if len(hits) == 1:
        return hits[0]
    return None


def _same(states: Mapping[str, str], left: str, right: str) -> bool:
    if left.strip().casefold() == right.strip().casefold():
        return True
    resolved_left, resolved_right = _resolve(states, left), _resolve(states, right)
    return resolved_left is not None and resolved_left == resolved_right


def _bucket(take: Mapping[str, object] | None, key: str, field: str) -> dict[str, str]:
    if take is None:
        return {}
    state = take.get(key)
    if not isinstance(state, Mapping):
        return {}
    raw = state.get(field)
    if not isinstance(raw, Mapping):
        return {}
    return {str(name): str(value) for name, value in raw.items() if str(value).strip()}


def _declared_start(frame: Mapping[str, object], prop_id: str) -> str | None:
    raw = frame_field(frame, "prop_states")
    if not isinstance(raw, Mapping):
        return None
    value = raw.get(prop_id)
    if not isinstance(value, str) or not value.strip():
        return None
    if _ARROW in value:
        return value.split(_ARROW, 1)[0].strip()
    return value.strip()


def _find(
    frames: Sequence[Mapping[str, object]],
    retake: str,
) -> int | None:
    token = retake.strip()
    for index, frame in enumerate(frames):
        if token in _labels(frame, index + 1):
            return index
    return None


def _take_for(
    takes: Sequence[Mapping[str, object]],
    frame: Mapping[str, object],
    index: int,
) -> Mapping[str, object] | None:
    labels = _labels(frame, index)
    for take in takes:
        shot = take.get("shot")
        if isinstance(shot, str) and shot.strip() in labels:
            return take
    return None


def _frames(document: Mapping[str, object]) -> list[Mapping[str, object]]:
    raw = document.get("frames")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    return [frame for frame in raw if isinstance(frame, Mapping)]


def _stale(
    shot: str,
    kind: str,
    name: str,
    actual: str,
    expected: str,
    retake: str,
) -> dict[str, str | None]:
    return warning(
        "STALE_TAKE",
        shot,
        (
            f"shot {shot} {kind} {name} observed '{actual}' does not continue "
            f"retake {retake} observed end '{expected}'"
        ),
        f"chain_from {retake} so this take starts from the observed end",
    )


def _compare_props(
    document: Mapping[str, object],
    frame: Mapping[str, object],
    index: int,
    take: Mapping[str, object] | None,
    expected: Mapping[str, str],
    retake: str,
) -> list[dict[str, str | None]]:
    shot = _shot_name(frame, index)
    observed = _bucket(take, "observed_start_state", "props")
    found: list[dict[str, str | None]] = []
    for prop_id, end_state in expected.items():
        actual = observed.get(prop_id)
        if actual is None:
            actual = _declared_start(frame, prop_id)
        if actual is None or _same(_states(document, prop_id), end_state, actual):
            continue
        found.append(_stale(shot, "prop", prop_id, actual, end_state, retake))
    return found


def _compare_wardrobe(
    frame: Mapping[str, object],
    index: int,
    take: Mapping[str, object] | None,
    expected: Mapping[str, str],
    retake: str,
) -> list[dict[str, str | None]]:
    shot = _shot_name(frame, index)
    observed = _bucket(take, "observed_start_state", "wardrobe")
    found: list[dict[str, str | None]] = []
    for name, end_state in expected.items():
        actual = observed.get(name)
        if actual is None or actual.strip().casefold() == end_state.strip().casefold():
            continue
        found.append(_stale(shot, "wardrobe", name, actual, end_state, retake))
    return found


def _closed(message: str, retake: str) -> dict[str, object]:
    return {
        "status": "NOT_COMPUTABLE",
        "authority": "NOT_COMPUTABLE",
        "action": "impact",
        "label": "OBSERVATION",
        "retake": retake,
        "code": "NOT_COMPUTABLE",
        "message": message,
        "prep_warnings": [],
    }


def impact(
    storyboard: Mapping[str, object],
    takes: Sequence[Mapping[str, object]],
    retake: str,
) -> dict[str, object]:
    """PROPOSED impact report. Does not mutate ``storyboard``."""
    frames = _frames(storyboard)
    _lines, errors = prop_assignments(storyboard, frames)
    if errors:
        return _closed(errors[0], retake)
    index = _find(frames, retake)
    if index is None:
        return _closed(f"retake {retake} is not on the storyboard", retake)
    source = _take_for(takes, frames[index], index + 1)
    if source is None:
        return _closed(f"retake {retake} has no take", retake)
    end_props = _bucket(source, "observed_end_state", "props")
    end_wardrobe = _bucket(source, "observed_end_state", "wardrobe")
    label = _shot_name(frames[index], index + 1)
    warnings: list[dict[str, str | None]] = []
    for later_index, frame in enumerate(frames[index + 1:], start=index + 2):
        later_take = _take_for(takes, frame, later_index)
        warnings.extend(_compare_props(
            storyboard, frame, later_index, later_take, end_props, label,
        ))
        warnings.extend(_compare_wardrobe(frame, later_index, later_take, end_wardrobe, label))
    return {
        "status": "PROPOSED",
        "authority": "PROPOSED",
        "action": "impact",
        "label": "OBSERVATION",
        "retake": label,
        "prep_warnings": warnings,
    }


def _load_takes(path: str) -> list[Mapping[str, object]]:
    loaded = load_structured(path)
    if isinstance(loaded, list):
        return [item for item in loaded if isinstance(item, Mapping)]
    if isinstance(loaded, dict):
        raw = loaded.get("takes")
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, Mapping)]
    return []


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Propose retake impact. Takes stay observations.")
    parser.add_argument("--storyboard")
    parser.add_argument("--plan")
    parser.add_argument("--takes", required=True)
    parser.add_argument("--retake", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(list(argv) if argv is not None else None)
    source = args.storyboard or args.plan
    if not source:
        print("impact needs --storyboard or --plan", file=sys.stderr)
        return 4
    document = load_structured(source)
    if not isinstance(document, dict):
        print("impact storyboard must be a mapping", file=sys.stderr)
        return 4
    result = impact(document, _load_takes(args.takes), args.retake)
    if args.output:
        write_structured(args.output, result)
    else:
        import yaml

        print(yaml.safe_dump(result, sort_keys=False))
    return 0 if result.get("status") == "PROPOSED" else 4


if __name__ == "__main__":
    raise SystemExit(main())
