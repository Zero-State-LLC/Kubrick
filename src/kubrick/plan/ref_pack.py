#!/usr/bin/env python3
"""Per-character reference packs. Paths and hashes only. No image generation.

Issue #103. One pack is shared across movies. Seedance takes a start image
or reference images, not both. A chain that would have dropped references
without a code now warns ``REFS_DROPPED_BY_CHAIN``.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from kubrick.plan.continuity_locks import frame_id, warning
from kubrick.prompts.reference_lint import screen_mode

WarningRow = dict[str, str | None]
ROLES = ("identity", "material", "costume_prop", "location", "layout")
MODES = ("start_frame", "refs_only", "first_last")
_END_REASON = "Keyframe create_movie schema has startImage and no end-image field"
_GROUPS = (
    ("views", "identity"),
    ("head_lock", "identity"),
    ("material_inserts", "material"),
    ("refs", ""),
)


def _map(value: object) -> Mapping[str, object] | None:
    if isinstance(value, Mapping):
        return value
    return None


def _text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _rows(value: object) -> list[Mapping[str, object]]:
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _characters(document: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    raw = document.get("characters")
    if not isinstance(raw, Mapping):
        return {}
    return {str(key): value for key, value in raw.items() if isinstance(value, Mapping)}


def _pack(spec: Mapping[str, object]) -> Mapping[str, object] | None:
    return _map(spec.get("ref_pack"))


def pack_hashes(document: Mapping[str, object]) -> dict[str, str]:
    """Character id to the pack ``asset_hash``. Characters without a pack are omitted."""
    found: dict[str, str] = {}
    for name, spec in _characters(document).items():
        pack = _pack(spec)
        if pack is None:
            continue
        digest = _text(pack.get("asset_hash"))
        if digest:
            found[name] = digest
    return found


def _on_screen(frame: Mapping[str, object], names: Sequence[str]) -> list[str]:
    _mode, present = screen_mode(frame)
    if _mode == "absent":
        return list(names)
    return [name for name in names if name in present]


def _chained(frame: Mapping[str, object]) -> bool:
    join = frame.get("join")
    if isinstance(join, Mapping):
        return bool(_text(join.get("chain_from")))
    return False


def _start_used(frame: Mapping[str, object]) -> bool:
    if _chained(frame):
        return True
    start = _map(frame.get("start_frame"))
    if start is None:
        return False
    return any(_text(start.get(key)) for key in ("asset", "sourceFrame", "source_shot"))


def shot_mode(frame: Mapping[str, object], document: Mapping[str, object]) -> str:
    """``start_frame``, ``refs_only``, or ``first_last``."""
    for source in (frame, document):
        raw = _text(source.get("input_mode")) or _text(source.get("resolver"))
        if raw in MODES:
            return raw
    if _start_used(frame) and _map(frame.get("end_framing")) is not None:
        return "first_last"
    if _start_used(frame):
        return "start_frame"
    return "refs_only"


def _new_angle(frame: Mapping[str, object], previous: Mapping[str, object] | None) -> bool:
    if frame.get("new_angle") is True:
        return True
    raw = frame.get("cut")
    parts: list[str] = []
    if isinstance(raw, str):
        parts.append(raw)
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        parts.extend(item for item in raw if isinstance(item, str))
    blob = " ".join(parts).casefold().replace("_", "-")
    if "thirty-degree" in blob or "new-angle" in blob:
        return True
    if previous is None:
        return False
    current = _size(frame)
    prior = _size(previous)
    return bool(current and prior and current != prior)


def _size(frame: Mapping[str, object]) -> str:
    framing = _map(frame.get("framing")) or {}
    camera = _map(frame.get("camera")) or {}
    return _text(framing.get("size")) or _text(camera.get("size"))


def _entry(
    raw: Mapping[str, object],
    default_role: str,
    character: str,
) -> tuple[dict[str, str] | None, str]:
    path = _text(raw.get("path"))
    role = _text(raw.get("ref_role")) or default_role
    digest = _text(raw.get("asset_hash"))
    if not path or not digest or role not in ROLES:
        return None, f"{character} ref_pack entry is missing a path, role, or asset_hash"
    return {"path": path, "ref_role": role, "asset_hash": digest, "character": character}, ""


def _entries(pack: Mapping[str, object], character: str) -> tuple[list[dict[str, str]], list[str]]:
    found: list[dict[str, str]] = []
    errors: list[str] = []
    for key, default in _GROUPS:
        for raw in _rows(pack.get(key)):
            entry, error = _entry(raw, default, character)
            if error:
                errors.append(error)
            elif entry is not None:
                found.append(entry)
    return found, errors


def _row(
    code: str, shot: str | None, message: str, recommendation: str, character: str | None,
) -> WarningRow:
    return warning(code, shot, message, recommendation, character=character)


def _select(
    entries: Sequence[Mapping[str, str]],
    frame: Mapping[str, object],
    previous: Mapping[str, object] | None,
    shot: str,
) -> tuple[list[dict[str, str]], list[WarningRow]]:
    warnings: list[WarningRow] = []
    kept: list[dict[str, str]] = []
    fresh = _new_angle(frame, previous)
    for entry in entries:
        if fresh and entry["ref_role"] == "layout":
            warnings.append(_row(
                "LAYOUT_REF_ON_NEW_ANGLE",
                shot,
                f"layout ref {entry['path']} is excluded on a new-angle shot",
                "drop the layout ref, or cut back to the plate",
                entry["character"],
            ))
            continue
        kept.append(dict(entry))
    return kept, warnings


def resolve_shot(
    document: Mapping[str, object],
    frame: Mapping[str, object],
    *,
    previous: Mapping[str, object] | None = None,
    index: int = 1,
) -> dict[str, object]:
    """Choose a carrier mode and the refs that survive Seedance's exclusive inputs."""
    shot = frame_id(frame, index)
    mode = shot_mode(frame, document)
    names = list(_characters(document))
    entries: list[dict[str, str]] = []
    errors: list[str] = []
    for name in _on_screen(frame, names):
        pack = _pack(_characters(document)[name])
        if pack is None:
            continue
        if not _text(pack.get("asset_hash")):
            errors.append(f"{name} ref_pack has no asset_hash")
            continue
        rows, row_errors = _entries(pack, name)
        entries.extend(rows)
        errors.extend(row_errors)
    selected, warnings = _select(entries, frame, previous, shot)
    dropped: list[dict[str, str]] = []
    emitted = selected
    if mode in {"start_frame", "first_last"} and selected:
        emitted = []
        for entry in selected:
            dropped.append({**entry, "code": "REFS_DROPPED_BY_CHAIN"})
        warnings.append(_row(
            "REFS_DROPPED_BY_CHAIN",
            shot,
            "Seedance startImage and referenceImages are mutually exclusive; "
            f"references dropped on {shot}",
            "keep the start frame, or switch the shot to refs_only",
            None,
        ))
    result: dict[str, object] = {
        "shot": shot,
        "mode": mode,
        "status": "NOT_COMPUTABLE" if errors else "PROPOSED",
        "references": [item["path"] for item in emitted],
        "roles": [item["ref_role"] for item in emitted],
        "dropped": dropped,
        "errors": errors,
        "warnings": warnings,
    }
    if mode == "first_last":
        result["end_image"] = {"field": "last_frame", "supported": False, "reason": _END_REASON}
    return result


def resolve(
    document: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Resolve every shot. The same pack hash is the identity shared across movies."""
    shots: list[dict[str, object]] = []
    warnings: list[WarningRow] = []
    errors: list[str] = []
    previous: Mapping[str, object] | None = None
    for index, frame in enumerate(frames, start=1):
        shot = resolve_shot(document, frame, previous=previous, index=index)
        shots.append(shot)
        raw_warnings = shot.get("warnings")
        if isinstance(raw_warnings, list):
            warnings.extend(item for item in raw_warnings if isinstance(item, dict))
        raw_errors = shot.get("errors")
        if isinstance(raw_errors, list):
            errors.extend(str(item) for item in raw_errors)
        previous = frame
    failed = bool(errors) or any(item.get("status") == "NOT_COMPUTABLE" for item in shots)
    status = "NOT_COMPUTABLE" if failed else "PROPOSED"
    return {
        "status": status,
        "authority": "PROPOSED",
        "pack_hashes": pack_hashes(document),
        "shots": shots,
        "warnings": warnings,
        "errors": errors,
    }


def shared_pack(documents: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """One pack per character. A hash that disagrees across movies is not computable."""
    if not documents:
        return {"status": "NOT_COMPUTABLE", "errors": ["no movies"], "packs": {}}
    hashes = [pack_hashes(document) for document in documents]
    if any(item != hashes[0] for item in hashes):
        return {
            "status": "NOT_COMPUTABLE",
            "code": "PACK_SPLIT",
            "errors": ["ref_pack asset_hash differs across movies"],
            "packs": hashes,
        }
    return {"status": "PROPOSED", "authority": "PROPOSED", "packs": hashes[0], "errors": []}


def pack_warnings(
    document: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
) -> list[WarningRow]:
    """Prep warnings. Plans with no ``ref_pack`` stay quiet."""
    specs = _characters(document).values()
    if not pack_hashes(document) and not any(_pack(spec) for spec in specs):
        return []
    report = resolve(document, frames)
    warnings: list[WarningRow] = []
    raw_warnings = report.get("warnings")
    if isinstance(raw_warnings, list):
        warnings.extend(item for item in raw_warnings if isinstance(item, dict))
    raw_errors = report.get("errors")
    if isinstance(raw_errors, list):
        for error in raw_errors:
            warnings.append(_row(
                "REF_PACK_INCOMPLETE",
                None,
                str(error),
                "set path, ref_role, and asset_hash on every pack entry",
                None,
            ))
    return warnings
