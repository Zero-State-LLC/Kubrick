#!/usr/bin/env python3
"""Plan reading for the board image gate: board sources, views, locks, thresholds.

No pixels and no models here. ``board_image_gate`` owns the checks.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

# Max cosine similarity over the approved views, DINOv2-small CLS features on
# the character crop. Calibrated on MYSLEF EP-01 (docs/BOARD-IMAGE-CALIBRATION.md):
# on a head crop every kept board scored 0.535 or more and off-model heads
# 0.32 to 0.46. It is an off-model floor, not a drift detector: kept and
# drifted heads overlap (AUC about 0.52). A wide board needs a
# board_subject_boxes head box, since a whole-frame crop scores 0.10 to 0.30.
DEFAULT_IDENTITY_THRESHOLD = 0.50
_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
_HIDDEN_VIEWS = frozenset({"back", "rear", "back_view", "occluded", "head_occluded"})
_IDENTITY_GROUPS = ("views", "head_lock")


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _map(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def as_list(value: object) -> list[object]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return list(value)
    return []


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def frame_labels(frame: Mapping[str, object], index: int) -> set[str]:
    found = {f"frame-{index:03d}"}
    for key in ("frame_id", "shot_id"):
        raw = frame.get(key)
        if raw is not None and str(raw).strip():
            found.add(str(raw).strip())
    return found


def frame_label(frame: Mapping[str, object], index: int) -> str:
    for key in ("shot_id", "frame_id"):
        raw = frame.get(key)
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    return f"frame-{index:03d}"


def _resolve(path: str, base_dir: Path) -> Path:
    candidate = Path(path).expanduser()
    return candidate if candidate.is_absolute() else base_dir / candidate


def board_source(
    frame: Mapping[str, object], base_dir: Path,
) -> tuple[Path | None, bool, str]:
    """``(path, explicit, asset)``. An explicit ``board_image`` must exist.

    ``start_frame.asset`` is checked only when it resolves to a local image
    file. A provider asset id has no pixels here and is reported, not checked.
    """
    start = _map(frame.get("start_frame"))
    explicit = _text(frame.get("board_image")) or _text(start.get("board_image"))
    if explicit:
        return _resolve(explicit, base_dir), True, explicit
    asset = _text(start.get("asset"))
    if not asset:
        return None, False, ""
    resolved = _resolve(asset, base_dir)
    if resolved.suffix.casefold() in _IMAGE_SUFFIXES and resolved.is_file():
        return resolved, False, asset
    return None, False, asset


def is_hard_cut(frame: Mapping[str, object]) -> bool:
    join = frame.get("join")
    if isinstance(join, str) and join.strip().casefold() == "cut":
        return True
    if frame.get("new_angle") is True:
        return True
    raw = [frame.get("cut"), *as_list(frame.get("cut"))]
    parts = [item for item in raw if isinstance(item, str)]
    blob = " ".join(parts).casefold().replace("_", "-")
    return "thirty-degree" in blob or "new-angle" in blob


def _board_view(frame: Mapping[str, object]) -> str:
    start = _map(frame.get("start_frame"))
    view = _text(frame.get("board_view")) or _text(start.get("view"))
    return view.casefold().replace("-", "_").replace(" ", "_")


def characters_of(document: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    raw = document.get("characters")
    if not isinstance(raw, Mapping):
        return {}
    return {str(key): value for key, value in raw.items() if isinstance(value, Mapping)}


def on_screen(frame: Mapping[str, object], names: Sequence[str]) -> list[str]:
    """Characters to check, with the skill contract's screen semantics.

    ``cast`` limits the list, and ``cast: []`` means nobody is in frame.
    ``characters: []`` alone does not, so it checks every character, the same
    as a frame that names nobody.
    """
    cast = frame.get("cast")
    if isinstance(cast, Sequence) and not isinstance(cast, (str, bytes)):
        present = {str(item).strip() for item in cast if str(item).strip()}
        return [name for name in names if name in present]
    raw = frame.get("characters")
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        present = {str(item).strip() for item in raw if str(item).strip()}
        if present:
            return [name for name in names if name in present]
    return list(names)


def identity_views(spec: Mapping[str, object], base_dir: Path) -> list[Path]:
    """Approved identity views from ``ref_pack.views`` and ``ref_pack.head_lock``."""
    pack = _map(spec.get("ref_pack"))
    found: list[Path] = []
    for group in _IDENTITY_GROUPS:
        raw = pack.get(group)
        rows = [raw] if isinstance(raw, Mapping) else as_list(raw)
        for row in rows:
            entry = _map(row)
            role = _text(entry.get("ref_role")) or "identity"
            path = _text(entry.get("path"))
            if path and role == "identity":
                found.append(_resolve(path, base_dir))
    return found


def lock_questions(
    document: Mapping[str, object], name: str, spec: Mapping[str, object],
) -> list[dict[str, str]]:
    """Yes-or-no questions from the character lock list, deduplicated by text.

    Sources: ``characters.<id>.character_locks``, ``characters.<id>.locks``,
    plan ``locks`` with ``character: <id>``, and explicit
    ``characters.<id>.board_checks`` (``question``, ``expect``).
    """
    texts: list[tuple[str, str]] = []
    for item in [*as_list(spec.get("character_locks")), *as_list(spec.get("locks"))]:
        if isinstance(item, str) and item.strip():
            texts.append((item.strip(), item.strip()))
        else:
            row = _map(item)
            text = _lock_text(row)
            if text:
                texts.append((_text(row.get("id")) or text, text))
    for item in as_list(document.get("locks")):
        row = _map(item)
        if _text(row.get("character")) != name:
            continue
        text = _lock_text(row)
        if text:
            texts.append((_text(row.get("id")) or text, text))
    questions: list[dict[str, str]] = []
    seen: set[str] = set()
    for lock_id, text in texts:
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        questions.append({
            "lock_id": lock_id,
            "question": (
                f"Answer only yes or no. Look at the character {name} in this image. "
                f"Is this statement true: {text}?"
            ),
            "expect": "yes",
        })
    for item in as_list(spec.get("board_checks")):
        row = _map(item)
        question = _text(row.get("question"))
        expect = _text(row.get("expect")).casefold() or "yes"
        if not question or expect not in {"yes", "no"} or question.casefold() in seen:
            continue
        seen.add(question.casefold())
        questions.append({
            "lock_id": _text(row.get("id")) or question,
            "question": question,
            "expect": expect,
        })
    return questions


def identity_threshold_for(
    document: Mapping[str, object], spec: Mapping[str, object], explicit: float | None,
) -> float | str:
    """CLI value, else ``ref_pack.identity_threshold``, else the plan, else the default."""
    candidates: list[tuple[str, object]] = [
        ("--board-identity-threshold", explicit),
        ("ref_pack.identity_threshold", _map(spec.get("ref_pack")).get("identity_threshold")),
        ("board_image_gate.identity_threshold",
         _map(document.get("board_image_gate")).get("identity_threshold")),
    ]
    for source, raw in candidates:
        if raw is None:
            continue
        value = _number(raw)
        if value is None or not 0.0 < value <= 1.0:
            return f"{source} must be a number above 0 and at most 1"
        return value
    return DEFAULT_IDENTITY_THRESHOLD


def _lock_text(row: Mapping[str, object]) -> str:
    return _text(row.get("negative")) or _text(row.get("positive")) or _text(row.get("text"))


def crop_hint(method: str) -> str | None:
    """Why a low score on a heuristic crop may be the crop, not the board."""
    if method == "plan_box":
        return None
    return (
        f"the {method} crop is not a head crop; on EP-01 a kept medium or wide board "
        "scored 0.10 to 0.30 this way, so set board_subject_boxes to the head box "
        "and rerun before regenerating the board"
    )


def subject_box(frame: Mapping[str, object], name: str, single: bool) -> Sequence[object] | None:
    boxes = _map(frame.get("board_subject_boxes"))
    raw = boxes.get(name)
    if raw is None and single:
        raw = frame.get("board_subject_box")
    listed = as_list(raw)
    return listed or None


def hides_identity(frame: Mapping[str, object]) -> bool:
    """A back or occluded board on a shot that reveals the identity."""
    return _board_view(frame) in _HIDDEN_VIEWS and frame.get("reveals_identity") is True
