#!/usr/bin/env python3
"""Plan hold list and the compiled prompts the pre-spend gate judges.

The hold list is ``hold_list`` when the plan sets it. Otherwise it is the plan
``locks``, ``location.locks``, and prop-state texts. Prop states are in-scope
inventory. Critical locks are presence checks.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from continuity_locks import frame_id


def plan_scope(document: Mapping[str, object]) -> str:
    """Location scope token for holds that belong to the plan location."""
    location = document.get("location")
    if isinstance(location, str) and location.strip():
        return location.strip()
    if isinstance(location, Mapping):
        for key in ("id", "name"):
            value = location.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        if location.get("locks"):
            return "plan-location"
    return "plan"


def shot_location(document: Mapping[str, object], frame: Mapping[str, object]) -> str:
    raw = frame.get("location")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if isinstance(raw, Mapping):
        for key in ("id", "name"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return plan_scope(document)


def _shot_label(frame: Mapping[str, object], index: int) -> str:
    raw = frame.get("shot_id")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return frame_id(frame, index)


def _labels(frame: Mapping[str, object], index: int) -> set[str]:
    return {frame_id(frame, index), _shot_label(frame, index)}


def _as_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _hold(
    *,
    hold_id: str,
    kind: str,
    text: str,
    scope: str,
    requirement: str,
    critical: bool,
    character: str | None = None,
    shot: str | None = None,
    blocked: bool = False,
    negative: str | None = None,
    positive: str | None = None,
) -> dict[str, object]:
    found: dict[str, object] = {
        "id": hold_id,
        "kind": kind,
        "text": text,
        "scope": scope,
        "requirement": requirement,
        "critical": critical,
        "blocked": blocked,
    }
    if character:
        found["character"] = character
    if shot:
        found["shot"] = shot
    if negative:
        found["negative"] = negative
    if positive:
        found["positive"] = positive
    return found


def _text_of(item: Mapping[str, object]) -> tuple[str, str | None, str | None] | None:
    negative = item.get("negative")
    positive = item.get("positive")
    text = item.get("text") or item.get("term")
    neg = negative.strip() if isinstance(negative, str) and negative.strip() else None
    pos = positive.strip() if isinstance(positive, str) and positive.strip() else None
    plain = text.strip() if isinstance(text, str) and text.strip() else None
    chosen = neg or pos or plain
    if chosen is None:
        return None
    return chosen, neg, pos


def _mapping_hold(
    item: Mapping[str, object], index: int, scope: str,
) -> dict[str, object] | str:
    parsed = _text_of(item)
    shot = item.get("shot")
    shot_id = shot.strip() if isinstance(shot, str) and shot.strip() else None
    blocked = item.get("blocked") is True
    if parsed is None and not (blocked and shot_id):
        return f"HOLD_LIST_INVALID hold {index} has no text"
    text, negative, positive = parsed if parsed is not None else ("", None, None)
    raw_id = item.get("id")
    hold_id = raw_id.strip() if isinstance(raw_id, str) and raw_id.strip() else f"hold-{index}"
    kind = item.get("kind")
    kind_text = kind.strip() if isinstance(kind, str) and kind.strip() else "lock"
    character = item.get("character")
    who = character.strip() if isinstance(character, str) and character.strip() else None
    own_scope = item.get("scope")
    if isinstance(own_scope, str) and own_scope.strip():
        scope = own_scope.strip()
    requirement = "do_not_spend" if blocked else "present"
    if not blocked:
        raw_req = item.get("requirement")
        if isinstance(raw_req, str) and raw_req.strip():
            requirement = raw_req.strip()
    return _hold(
        hold_id=hold_id,
        kind=kind_text,
        text=text or f"shot {shot_id} is blocked",
        scope=scope,
        requirement=requirement,
        critical=_as_bool(item.get("critical"), True),
        character=who,
        shot=shot_id,
        blocked=blocked,
        negative=negative,
        positive=positive,
    )


def _explicit_holds(raw: Sequence[object], scope: str) -> list[dict[str, object]] | str:
    holds: list[dict[str, object]] = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, str) and item.strip():
            holds.append(_hold(
                hold_id=f"hold-{index}",
                kind="lock",
                text=item.strip(),
                scope=scope,
                requirement="present",
                critical=True,
            ))
            continue
        if isinstance(item, Mapping):
            built = _mapping_hold(item, index, scope)
            if isinstance(built, str):
                return built
            holds.append(built)
            continue
        return f"HOLD_LIST_INVALID hold {index} is not a lock"
    return holds


def _plan_locks(raw: object, scope: str) -> list[dict[str, object]] | str:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    return _explicit_holds(list(raw), scope)


def _location_holds(document: Mapping[str, object], scope: str) -> list[dict[str, object]]:
    location = document.get("location")
    if not isinstance(location, Mapping):
        return []
    holds: list[dict[str, object]] = []
    raw = location.get("locks")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return holds
    index = 0
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            continue
        index += 1
        holds.append(_hold(
            hold_id=f"location-{index}",
            kind="location",
            text=item.strip(),
            scope=scope,
            requirement="present",
            critical=False,
        ))
    return holds


def _prop_holds(document: Mapping[str, object], scope: str) -> list[dict[str, object]]:
    raw = document.get("props")
    if not isinstance(raw, Mapping):
        return []
    holds: list[dict[str, object]] = []
    for prop_id, spec in raw.items():
        if not isinstance(spec, Mapping):
            continue
        states = spec.get("states")
        if not isinstance(states, Mapping):
            continue
        for state_id, text in states.items():
            if not isinstance(text, str) or not text.strip():
                continue
            holds.append(_hold(
                hold_id=f"prop-{prop_id}-{state_id}",
                kind="prop",
                text=text.strip(),
                scope=scope,
                requirement="in_scope_only",
                critical=False,
            ))
    return holds


def hold_list(document: Mapping[str, object]) -> list[dict[str, object]] | str:
    """The plan hold list, or ``HOLD_LIST_INVALID ...`` when it cannot be trusted."""
    scope = plan_scope(document)
    if "hold_list" in document:
        explicit = document.get("hold_list")
        if isinstance(explicit, (str, bytes)) or not isinstance(explicit, Sequence):
            return "HOLD_LIST_INVALID hold_list must be a list"
        return _explicit_holds(list(explicit), scope)
    locks = _plan_locks(document.get("locks"), scope)
    if isinstance(locks, str):
        return locks
    return [*locks, *_location_holds(document, scope), *_prop_holds(document, scope)]


def _frames(document: Mapping[str, object]) -> list[Mapping[str, object]]:
    raw = document.get("frames")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    return [frame for frame in raw if isinstance(frame, Mapping)]


def compiled_prompts(
    document: Mapping[str, object], channel: str,
) -> list[dict[str, object]] | str:
    """Compiled per-shot prompts. Keyframe copies this text into image and video prompts."""
    frames = _frames(document)
    if not frames:
        return []
    from storyboard_prompts import shots_from_document

    rendered = shots_from_document(document)
    if len(rendered) != len(frames):
        return "JEV_PROMPT_MISSING compiled prompt count does not match the frames"
    surfaces = ["image", "video"] if channel == "keyframe" else [channel]
    prompts: list[dict[str, object]] = []
    for index, pair in enumerate(zip(frames, rendered), start=1):
        frame, shot = pair
        text = shot.get("prompt") if isinstance(shot, Mapping) else None
        label = _shot_label(frame, index)
        if not isinstance(text, str) or not text.strip():
            return f"JEV_PROMPT_MISSING shot {label} has no compiled prompt"
        prompts.append({
            "shot": label,
            "labels": sorted(_labels(frame, index)),
            "channel": channel,
            "surfaces": surfaces,
            "location": shot_location(document, frame),
            "prompt": text,
        })
    return prompts


def select_prompts(
    prompts: Sequence[Mapping[str, object]], labels: set[str],
) -> list[dict[str, object]] | str:
    """Prompts for the shots that would be spent. Unknown shots fail closed."""
    if not labels:
        return []
    selected: list[dict[str, object]] = []
    seen: set[str] = set()
    for prompt in prompts:
        names = prompt.get("labels")
        if not isinstance(names, Sequence) or isinstance(names, (str, bytes)):
            continue
        matched = labels & {str(item) for item in names}
        if not matched:
            continue
        selected.append(dict(prompt))
        seen |= matched
    missing = labels - seen
    if missing:
        listed = ", ".join(sorted(missing))
        return f"JEV_PROMPT_MISSING no compiled prompt for shot(s): {listed}"
    return selected


def prompts_for_cues(
    document: Mapping[str, object], cues: Sequence[Mapping[str, object]],
) -> list[dict[str, object]] | str:
    """Spoken lines that would be sent to ElevenLabs."""
    frames = _frames(document)
    prompts: list[dict[str, object]] = []
    for index, cue in enumerate(cues, start=1):
        text = cue.get("text")
        if not isinstance(text, str) or not text.strip():
            return f"JEV_PROMPT_MISSING cue {index} has no text"
        shot = cue.get("shot")
        label = str(shot) if shot is not None else str(index)
        frame = next(
            (
                item for i, item in enumerate(frames, start=1)
                if label in _labels(item, i)
            ),
            None,
        )
        location = shot_location(document, frame) if frame is not None else plan_scope(document)
        prompts.append({
            "shot": label,
            "labels": [label],
            "channel": "elevenlabs",
            "surfaces": ["audio"],
            "location": location,
            "prompt": text,
        })
    return prompts
