#!/usr/bin/env python3
"""Scope, view, and per-hold verdicts for the pre-spend gate. Issue #99.

A hold with no scope object still applies to every prompt. Recorded samples
whose probability sits in 0.4–0.6 are not a pass.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from kubrick.plan.lock_aspect import ASPECTS, pov_skips

_VIEWS = frozenset({"front", "rear", "pov"})
_SAMPLE_LIMIT = 3
_REAR = "seen from behind there is NO visible light"


def _names(value: object) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    found: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            found.append(item.strip())
    return found


def frame_place(frame: Mapping[str, object]) -> str | None:
    raw = frame.get("location")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if isinstance(raw, Mapping):
        for key in ("id", "name"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def frame_view(frame: Mapping[str, object]) -> str | None:
    raw = frame.get("view")
    if isinstance(raw, str) and raw.strip().casefold() in _VIEWS:
        return raw.strip().casefold()
    camera = frame.get("camera")
    if isinstance(camera, Mapping):
        nested = camera.get("view")
        if isinstance(nested, str) and nested.strip().casefold() in _VIEWS:
            return nested.strip().casefold()
    return None


def prop_in_place(prop: Mapping[str, object], place: str | None) -> bool:
    """A prop with ``locations`` is absent outside that list."""
    raw = prop.get("locations")
    if place is None or not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return True
    names = {item.strip() for item in raw if isinstance(item, str) and item.strip()}
    return not names or place in names


def _scope(hold: Mapping[str, object]) -> dict[str, list[str]]:
    raw = hold.get("scope")
    if not isinstance(raw, Mapping):
        return {"locations": [], "shots": [], "characters": []}
    return {
        "locations": _names(raw.get("locations")),
        "shots": _names(raw.get("shots")),
        "characters": _names(raw.get("characters")),
    }


def _labels(prompt: Mapping[str, object]) -> set[str]:
    names = set(_names(prompt.get("labels")))
    shot = prompt.get("shot")
    if isinstance(shot, str) and shot.strip():
        names.add(shot.strip())
    return names


def scoped_out(
    hold: Mapping[str, object],
    location: str,
    labels: set[str],
    characters: set[str],
    view: str,
) -> bool:
    rule = _scope(hold)
    if rule["locations"] and location not in rule["locations"]:
        return True
    if rule["shots"] and labels.isdisjoint(rule["shots"]):
        return True
    if rule["characters"] and characters.isdisjoint(rule["characters"]):
        return True
    if pov_skips(hold, view):
        return True
    views = _names(hold.get("views"))
    return bool(views) and view not in views


_LOCATION_UNSPECIFIED = (
    "LOCATION_UNSPECIFIED a location-scoped hold needs a prompt location"
)


def _place(prompt: Mapping[str, object]) -> str:
    raw = prompt.get("location")
    if isinstance(raw, str):
        return raw.strip()
    return ""


def holds_for_prompt(
    holds: Sequence[Mapping[str, object]],
    prompt: Mapping[str, object],
) -> list[dict[str, object]] | str:
    """Holds that apply to this prompt. A blank location fails closed.

    A location-scoped hold is not dropped when ``prompt.location`` is missing
    or whitespace. That case returns ``LOCATION_UNSPECIFIED`` and blocks spend.
    """
    place = _place(prompt)
    if not place and any(_scope(hold)["locations"] for hold in holds):
        return _LOCATION_UNSPECIFIED
    view = prompt.get("view")
    view_name = view.strip().casefold() if isinstance(view, str) else ""
    characters = set(_names(prompt.get("characters")))
    labels = _labels(prompt)
    chosen: list[dict[str, object]] = []
    for hold in holds:
        if scoped_out(hold, place, labels, characters, view_name):
            continue
        chosen.append(dict(hold))
    return chosen


def scoped_lock_lines(
    holds: Sequence[Mapping[str, object]],
    prompt: Mapping[str, object],
) -> list[str] | str:
    """Texts a scoped hold requires in this prompt. A blank location fails closed."""
    chosen = holds_for_prompt(holds, prompt)
    if isinstance(chosen, str):
        return chosen
    lines: list[str] = []
    for hold in chosen:
        rule = _scope(hold)
        if not (rule["locations"] or rule["shots"] or rule["characters"]):
            continue
        text = hold.get("text")
        if isinstance(text, str) and text.strip():
            lines.append(text.strip())
    return lines


def prompt_hold_texts(
    holds: Sequence[Mapping[str, object]],
    prompt: Mapping[str, object],
) -> list[str] | str:
    """Hold texts that apply to this prompt by scope, view and cast (0.27.14)."""
    from kubrick.gates.lock_phrases import _cast_applies

    chosen = holds_for_prompt(holds, prompt)
    if isinstance(chosen, str):
        return chosen
    texts: list[str] = []
    for hold in chosen:
        text = hold.get("text")
        if _cast_applies(hold, prompt) and isinstance(text, str) and text.strip():
            texts.append(text.strip())
    return texts


def annotate_hold(item: Mapping[str, object], built: dict[str, object]) -> dict[str, object]:
    """Copy scope, anchor, views, and salience when the author set them."""
    anchor = item.get("anchor")
    if isinstance(anchor, str) and anchor.strip():
        built["anchor"] = anchor.strip()
    views = _names(item.get("views"))
    if views:
        built["views"] = views
    salience = item.get("salience")
    if isinstance(salience, (int, float)) and not isinstance(salience, bool):
        built["salience"] = float(salience)
    aspect = item.get("aspect")
    if isinstance(aspect, str) and aspect.strip().casefold() in ASPECTS:
        built["aspect"] = aspect.strip().casefold()
    rear = item.get("rear")
    if isinstance(rear, str) and rear.strip():
        built["rear"] = rear.strip()
    raw_scope = item.get("scope")
    if isinstance(raw_scope, Mapping):
        built["scope"] = _scope(item)
    return built


def _frame_prompt(frame: Mapping[str, object]) -> dict[str, object]:
    place = frame_place(frame) or ""
    view = frame_view(frame) or ""
    shot = frame.get("shot_id") or frame.get("frame_id")
    return {
        "shot": shot if isinstance(shot, str) else "",
        "location": place,
        "view": view,
        "characters": _names(frame.get("characters")),
        "labels": _names([frame.get("frame_id"), frame.get("shot_id")]),
    }


def view_clauses(document: Mapping[str, object], frame: Mapping[str, object]) -> list[str]:
    """Rear frames get the explicit rear negation, not only a folded sentence."""
    if frame_view(frame) != "rear":
        return []
    raw = document.get("locks")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    prompt = _frame_prompt(frame)
    lines: list[str] = []
    for lock in raw:
        if not isinstance(lock, Mapping) or scoped_out(
            lock,
            str(prompt["location"]),
            set(_names(prompt["labels"])),
            set(_names(prompt["characters"])),
            "rear",
        ):
            continue
        rear = lock.get("rear")
        if isinstance(rear, str) and rear.strip():
            lines.append(rear.strip())
            continue
        anchor = lock.get("anchor")
        views = _names(lock.get("views"))
        if isinstance(anchor, str) and anchor.strip() and (not views or "rear" in views):
            lines.append(f"{_REAR} on the {anchor.strip()}")
    return lines


def _probability(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number < 0 or number > 1:
        return None
    return number


def sample_marginal(payload: Mapping[str, object]) -> bool:
    values: list[object] = [payload.get("p")]
    raw = payload.get("holds")
    if isinstance(raw, list):
        values.extend(item.get("p") for item in raw if isinstance(item, Mapping))
    return any(
        (p := _probability(value)) is not None and 0.4 <= p <= 0.6
        for value in values
    )


def choose_sample(found: Mapping[str, object]) -> dict[str, object]:
    """Use up to three samples. A probability in 0.4–0.6 is not a pass."""
    samples = found.get("samples")
    if not isinstance(samples, list):
        return dict(found)
    chosen: Mapping[str, object] | None = None
    count = 0
    for item in samples:
        if not isinstance(item, Mapping):
            continue
        count += 1
        if count > _SAMPLE_LIMIT:
            break
        chosen = item
        if not sample_marginal(item):
            return dict(item)
    if chosen is None or sample_marginal(chosen):
        return {
            "verdict": "fail",
            "findings": [{
                "code": "JEV_MARGIN",
                "message": "p stayed between 0.4 and 0.6 after 3 samples",
            }],
        }
    return dict(chosen)


def per_hold_verdict(payload: Mapping[str, object]) -> dict[str, object] | None:
    """One row per hold. A weak hold fails alone; the others can pass."""
    raw = payload.get("holds")
    if not isinstance(raw, list) or not raw:
        return None
    if not all(isinstance(item, Mapping) and "present" in item for item in raw):
        return None
    results: list[dict[str, object]] = []
    findings: list[dict[str, str]] = []
    for item in raw:
        hold_id = item.get("hold_id")
        if not isinstance(hold_id, str) or not hold_id.strip():
            return {"error": "Jev hold verdict is incomplete"}
        flags = [item.get(key) for key in ("present", "located", "strong")]
        if not all(isinstance(flag, bool) for flag in flags):
            return {"error": "Jev hold verdict is incomplete"}
        passed = all(flag is True for flag in flags)
        name = hold_id.strip()
        results.append({
            "hold_id": name,
            "present": item.get("present"),
            "located": item.get("located"),
            "strong": item.get("strong"),
            "passed": passed,
        })
        if not passed:
            findings.append({
                "code": "JEV_HOLD",
                "hold_id": name,
                "message": f"hold {name} failed present, located, or strong",
            })
    return {
        "verdict": "fail" if findings else "pass",
        "findings": findings,
        "hold_results": results,
    }
