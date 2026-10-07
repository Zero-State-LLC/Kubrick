#!/usr/bin/env python3
"""Which input carries each lock. Issue #35.

Precedence is start frame, then a scoped reference, then a positive line,
then negative only. A reference carries a light or prop lock only when a
declare equals the lock id or the lock's positive text. Character locks keep
the #16 positive restatement, so they are not ``prompt_negative_only``.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from kubrick.plan.continuity_locks import frame_field, frame_id, prop_assignments, warning
from kubrick.plan.lock_prompt_text import compiled_prompt_text, positive_omitted
from kubrick.plan.shot_plan import chain_source
from kubrick.prompts.prompt_text import character_lock_feature, character_lock_positive
from kubrick.prompts.reference_lint import (
    declares_feature,
    frame_locks,
    reference_attached,
    screen_mode,
    wardrobe_lines_for,
)
from kubrick.providers.provider_capabilities import capabilities_for_document


def _character_table(document: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    raw = document.get("characters")
    if not isinstance(raw, Mapping):
        return {}
    return {str(key): value for key, value in raw.items() if isinstance(value, Mapping)}


def _join_is_cut(frame: Mapping[str, object]) -> bool:
    raw = frame_field(frame, "join")
    if raw == "cut":
        return True
    if not isinstance(raw, Mapping):
        return False
    kind = raw.get("type") if raw.get("type") is not None else raw.get("join")
    return kind == "cut"


def _inherited_start(frame: Mapping[str, object]) -> bool:
    """A start frame copied from an earlier shot. A cut must not keep it."""
    raw = frame_field(frame, "start_frame")
    if not isinstance(raw, Mapping):
        return False
    if raw.get("inherited") is True:
        return True
    source = raw.get("source_shot")
    return isinstance(source, str) and bool(source.strip())


def _start_carries(frame: Mapping[str, object]) -> bool:
    if chain_source(frame) is not None:
        return True
    if _join_is_cut(frame) and _inherited_start(frame):
        return False
    return isinstance(frame_field(frame, "start_frame"), Mapping)


def _measurements(frame: Mapping[str, object]) -> Mapping[str, object]:
    raw = frame_field(frame, "board_measurements")
    if isinstance(raw, Mapping):
        return raw
    return {}


def _explicit_status(frame: Mapping[str, object], lock_id: str) -> str | None:
    raw = frame_field(frame, "board_evidence")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return None
    for item in raw:
        if not isinstance(item, Mapping) or str(item.get("lock_id") or "") != lock_id:
            continue
        status = item.get("status")
        if status in {"verified", "contradicted", "unverified"}:
            return str(status)
    return None


def _hands_status(
    frame: Mapping[str, object],
    text: str,
    lock: Mapping[str, object] | None,
) -> str | None:
    measured = _measurements(frame).get("hands")
    if not isinstance(measured, str):
        return None
    parts = [text]
    if lock is not None:
        for key in ("id", "text", "positive", "negative"):
            value = lock.get(key)
            if isinstance(value, str):
                parts.append(value)
    blob = " ".join(parts).casefold()
    if "hand" not in blob and "silicon" not in blob:
        return None
    if measured.strip() == "human":
        return "contradicted"
    if measured.strip() == "silicon":
        return "verified"
    return None


def _image_status(
    frame: Mapping[str, object],
    lock_id: str,
    text: str,
    lock: Mapping[str, object] | None,
) -> tuple[str, str | None, str | None, str | None]:
    """Return status, evidence, code, and detail for a start-frame candidate."""
    explicit = _explicit_status(frame, lock_id)
    if explicit == "verified":
        return "verified", "board_evidence", None, None
    if explicit == "contradicted":
        return "contradicted", "board_evidence", "BOARD_LOCK_CONTRADICTED", None
    if explicit == "unverified":
        return "unverified", None, "BOARD_LOCK_UNVERIFIED", None
    hands = _hands_status(frame, text, lock)
    if hands == "contradicted":
        return (
            "contradicted",
            "hands",
            "BOARD_LOCK_CONTRADICTED",
            "HUMAN_HAND_ON_SILICON_LOCK",
        )
    if hands == "verified":
        return "verified", "hands", None, None
    return "unverified", None, "BOARD_LOCK_UNVERIFIED", None


def _carrier_record(
    lock_id: str,
    carrier: str,
    evidence: str | None,
    status: str,
    code: str | None = None,
    detail: str | None = None,
) -> dict[str, object]:
    record: dict[str, object] = {
        "lock_id": lock_id,
        "carrier": carrier,
        "evidence": evidence,
        "status": status,
    }
    if code:
        record["code"] = code
    if detail:
        record["detail"] = detail
    if status == "contradicted" and "hand" in lock_id.casefold():
        record["recommendation"] = (
            "refs-only with a material insert plus an identity ref"
        )
    return record


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
    prompt_text: str | None = None,
) -> dict[str, object]:
    """Carrier plus image status. A start frame with no evidence is unverified."""
    lock_id = text
    if lock is not None:
        ident = lock.get("id")
        if isinstance(ident, str) and ident.strip():
            lock_id = ident.strip()
    if _start_carries(frame):
        status, evidence, code, detail = _image_status(frame, lock_id, text, lock)
        if status == "verified":
            return _carrier_record(lock_id, "start_frame", evidence, "verified")
        if status == "contradicted":
            return _carrier_record(
                lock_id, "contradicted", evidence, "contradicted", code, detail,
            )
        return _carrier_record(
            lock_id, "unverified", evidence, "unverified", "BOARD_LOCK_UNVERIFIED",
        )
    if _reference_carries(document, frame, kind, text, character, lock):
        return _carrier_record(lock_id, "reference", "reference", "verified")
    if positive_omitted(lock, prompt_text):
        return _carrier_record(
            lock_id, "unverified", None, "unverified", "LOCK_POSITIVE_NOT_IN_PROMPT",
        )
    if _is_positive(kind, text, lock):
        return _carrier_record(lock_id, "prompt_positive", "prompt", "verified")
    return _carrier_record(lock_id, "prompt_negative_only", None, "unverified")


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


def _recorded(
    shot: str,
    lock: str,
    kind: str,
    record: Mapping[str, object],
    *,
    critical: bool = False,
) -> dict[str, object]:
    row = _row(shot, lock, kind, str(record.get("carrier") or ""), critical=critical)
    if record.get("code") == "LOCK_POSITIVE_NOT_IN_PROMPT":
        row["code"] = "LOCK_POSITIVE_NOT_IN_PROMPT"
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
        rows.append(_recorded(shot, text, "identity", kind_carrier))
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
        rows.append(_recorded(shot, line, "wardrobe", chosen))
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
        rows.append(_recorded(shot, prop_id or line, "prop", chosen))
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
    prompt_text: str | None = None,
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
        chosen = carrier_for(document, frame, kind, text, owner, lock, prompt_text)
        rows.append(_recorded(
            shot, ident, kind, chosen, critical=lock.get("critical") is True,
        ))
    return rows


def lock_table(
    document: Mapping[str, object],
    frames: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Per-shot carriers. The provider does not change the carrier."""
    lines, _errors = prop_assignments(document, frames)
    prompts = compiled_prompt_text(document)
    rows: list[dict[str, object]] = []
    for index, frame in enumerate(frames, start=1):
        shot = frame_id(frame, index)
        rows.extend(_identity_rows(document, frame, shot))
        rows.extend(_wardrobe_rows(document, frame, shot))
        rows.extend(_prop_rows(document, frame, shot, lines.get(shot, [])))
        rows.extend(_structured_rows(
            document, frame, shot, None if prompts is None else prompts.get(shot, ""),
        ))
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
