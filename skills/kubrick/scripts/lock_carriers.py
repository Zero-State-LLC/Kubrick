#!/usr/bin/env python3
"""Which input carries each lock. Issue #35.

Precedence is start frame, then a scoped reference, then a positive line,
then negative only. A reference carries a light or prop lock only when a
declare equals the lock id or the lock's positive text. Character locks keep
the #16 positive restatement, so they are not ``prompt_negative_only``.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from continuity_locks import frame_field, frame_id, prop_assignments, warning
from prompt_text import character_lock_feature, character_lock_positive
from provider_capabilities import capabilities_for_document
from reference_lint import (
    declares_feature,
    frame_locks,
    reference_attached,
    screen_mode,
    wardrobe_lines_for,
)
from shot_plan import chain_source


def _character_table(document: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    raw = document.get("characters")
    if not isinstance(raw, Mapping):
        return {}
    return {str(key): value for key, value in raw.items() if isinstance(value, Mapping)}


def _start_carries(frame: Mapping[str, object]) -> bool:
    if chain_source(frame) is not None:
        return True
    return isinstance(frame_field(frame, "start_frame"), Mapping)


def _refs_of(spec: Mapping[str, object]) -> list[Mapping[str, object]]:
    raw = spec.get("references")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    return [item for item in raw if isinstance(item, Mapping)]


def _scoped_identity(
    document: Mapping[str, object],
    frame: Mapping[str, object],
    character: str,
    text: str,
) -> bool:
    feature = character_lock_feature(text, from_lock=True)
    for ref in _refs_of(_character_table(document).get(character, {})):
        applies = ref.get("applies_to")
        if not isinstance(applies, Sequence) or isinstance(applies, (str, bytes)):
            continue
        names = [str(item).strip() for item in applies if str(item).strip()]
        if names != [character] or not reference_attached(frame, ref, character):
            continue
        declares = ref.get("declares")
        if isinstance(declares, Sequence) and not isinstance(declares, (str, bytes)):
            declared: Sequence[object] = declares
        else:
            declared = []
        texts = [str(item) for item in declared]
        if feature is not None and declares_feature(texts, feature):
            continue
        return True
    return False


def _all_refs(document: Mapping[str, object]) -> list[tuple[str, Mapping[str, object]]]:
    found: list[tuple[str, Mapping[str, object]]] = []
    for owner, spec in _character_table(document).items():
        for ref in _refs_of(spec):
            found.append((owner, ref))
    location = document.get("location")
    if isinstance(location, Mapping):
        raw = location.get("references")
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            for ref in raw:
                if isinstance(ref, Mapping):
                    found.append(("", ref))
    return found


def _declare_match(
    document: Mapping[str, object],
    frame: Mapping[str, object],
    targets: set[str],
) -> bool:
    if not targets:
        return False
    for owner, ref in _all_refs(document):
        if not reference_attached(frame, ref, owner):
            continue
        declares = ref.get("declares")
        if not isinstance(declares, Sequence) or isinstance(declares, (str, bytes)):
            continue
        for item in declares:
            if " ".join(str(item).casefold().split()) in targets:
                return True
    return False


def _positive_targets(lock: Mapping[str, object] | None, text: str) -> set[str]:
    targets = {" ".join(text.casefold().split())}
    if lock is None:
        return targets
    for key in ("id", "positive"):
        value = lock.get(key)
        if isinstance(value, str) and value.strip():
            targets.add(" ".join(value.casefold().split()))
    return targets


def _reference_carries(
    document: Mapping[str, object],
    frame: Mapping[str, object],
    kind: str,
    text: str,
    character: str | None,
    lock: Mapping[str, object] | None,
) -> bool:
    if kind in {"identity", "wardrobe"} and character:
        return _scoped_identity(document, frame, character, text)
    if kind in {"light", "prop"}:
        return _declare_match(document, frame, _positive_targets(lock, text))
    return False


def _is_positive(kind: str, text: str, lock: Mapping[str, object] | None) -> bool:
    if lock is not None:
        positive = lock.get("positive")
        if isinstance(positive, str) and positive.strip():
            return True
    if kind in {"wardrobe", "prop"}:
        return True
    if kind == "identity":
        return character_lock_positive(text, from_lock=True) is not None
    return False


def carrier_for(
    document: Mapping[str, object],
    frame: Mapping[str, object],
    kind: str,
    text: str,
    character: str | None = None,
    lock: Mapping[str, object] | None = None,
) -> str:
    if _start_carries(frame):
        return "start_frame"
    if _reference_carries(document, frame, kind, text, character, lock):
        return "reference"
    if _is_positive(kind, text, lock):
        return "prompt_positive"
    return "prompt_negative_only"


def _row(
    shot: str,
    lock: str,
    kind: str,
    carrier: str,
    *,
    critical: bool = False,
) -> dict[str, object]:
    row: dict[str, object] = {"shot": shot, "lock": lock, "kind": kind, "carrier": carrier}
    if critical:
        row["critical"] = True
    return row


def _identity_rows(
    document: Mapping[str, object],
    frame: Mapping[str, object],
    shot: str,
) -> list[dict[str, object]]:
    locks = document.get("character_locks")
    items = locks if isinstance(locks, Sequence) and not isinstance(locks, (str, bytes)) else []
    rows: list[dict[str, object]] = []
    for text in frame_locks(document, frame, items):
        character = _lock_character(document, text)
        kind_carrier = carrier_for(document, frame, "identity", text, character)
        rows.append(_row(shot, text, "identity", kind_carrier))
    return rows


def _lock_character(document: Mapping[str, object], text: str) -> str | None:
    folded = " ".join(text.casefold().split())
    for name, spec in _character_table(document).items():
        raw = spec.get("character_locks")
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            continue
        for item in raw:
            if " ".join(str(item).casefold().split()) == folded:
                return name
    return None


def _wardrobe_rows(
    document: Mapping[str, object],
    frame: Mapping[str, object],
    shot: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in wardrobe_lines_for(document, frame):
        character = _wardrobe_character(line)
        chosen = carrier_for(document, frame, "wardrobe", line, character)
        rows.append(_row(shot, line, "wardrobe", chosen))
    return rows


def _wardrobe_character(line: str) -> str | None:
    marker = "WARDROBE LOCK: "
    if not line.startswith(marker):
        return None
    rest = line[len(marker):]
    name, _sep, _tail = rest.partition(" wears ")
    return name.strip() or None


def _prop_rows(
    document: Mapping[str, object],
    frame: Mapping[str, object],
    shot: str,
    lines: Sequence[str],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in lines:
        prop_id = _prop_id(line)
        chosen = carrier_for(
            document, frame, "prop", prop_id or line, None, {"id": prop_id or line},
        )
        rows.append(_row(shot, prop_id or line, "prop", chosen))
    return rows


def _prop_id(line: str) -> str | None:
    if " LOCK:" not in line:
        return None
    return line.split(" LOCK:", 1)[0].strip().casefold().replace(" ", "_")


def _applies(frame: Mapping[str, object], character: str | None) -> bool:
    if not character:
        return True
    _mode, present = screen_mode(frame)
    if not present and _mode == "absent":
        return True
    return character in present


def _structured_rows(
    document: Mapping[str, object],
    frame: Mapping[str, object],
    shot: str,
) -> list[dict[str, object]]:
    raw = document.get("locks")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    rows: list[dict[str, object]] = []
    for lock in raw:
        if not isinstance(lock, Mapping):
            continue
        character = lock.get("character")
        owner = character.strip() if isinstance(character, str) and character.strip() else None
        if not _applies(frame, owner):
            continue
        kind = str(lock.get("kind") or "light").strip() or "light"
        ident = str(lock.get("id") or lock.get("negative") or kind)
        text = str(lock.get("negative") or lock.get("positive") or ident)
        chosen = carrier_for(document, frame, kind, text, owner, lock)
        rows.append(_row(shot, ident, kind, chosen, critical=lock.get("critical") is True))
    return rows


def lock_table(
    document: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Per-shot carriers. The provider does not change the carrier."""
    lines, _errors = prop_assignments(document, frames)
    rows: list[dict[str, object]] = []
    for index, frame in enumerate(frames, start=1):
        shot = frame_id(frame, index)
        rows.extend(_identity_rows(document, frame, shot))
        rows.extend(_wardrobe_rows(document, frame, shot))
        rows.extend(_prop_rows(document, frame, shot, lines.get(shot, [])))
        rows.extend(_structured_rows(document, frame, shot))
    return rows


def _recommendation(provider: str, document: Mapping[str, object] | None = None) -> str:
    base = (
        "use a start frame or a reference that already shows the locked state, "
        "and add the positive restatement"
    )
    effective = capabilities_for_document(provider, document).get("negative_prompt_effective")
    if effective is True:
        return base
    return f"{base}; {provider} negative_prompt_effective is false"


def negative_only_warnings(
    document: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
    provider: str,
) -> list[dict[str, str | None]]:
    found: list[dict[str, str | None]] = []
    for row in lock_table(document, frames):
        if row.get("carrier") != "prompt_negative_only" or row.get("critical") is not True:
            continue
        shot = str(row.get("shot") or "")
        ident = str(row.get("lock") or "")
        found.append(warning(
            "NEGATIVE_ONLY_LOCK",
            shot or None,
            f"lock {ident} on {shot} is carried only by a negative prompt",
            _recommendation(provider, document),
        ))
    return found
