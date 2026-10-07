"""Plan lock text must match the canon lock file the plan names.

A plan may set ``canon_locks: <path>``. A relative path is looked up from the
plan's folder, then each parent folder, then the working directory. Each plan
lock is matched to the canon lock with the same id, or with its ``canon_id``.
A different ``positive`` or ``negative`` line, or a different ``critical`` flag,
is ``LOCK_CANON_DRIFT``. ``kind`` is not compared. No
canon is built in; the plan names its own file.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

FIELDS = ("positive", "negative")


def _finding(code: str, message: str, **extra: str) -> dict[str, str]:
    return {"code": code, "message": message, **extra}


def _line(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return " ".join(value.split())
    return None


def _critical(value: object) -> bool:
    return value is True


def _canon_by_id(raw: object) -> dict[str, Mapping[str, object]] | None:
    locks = raw.get("locks") if isinstance(raw, Mapping) else None
    if not isinstance(locks, Sequence) or isinstance(locks, (str, bytes)):
        return None
    found: dict[str, Mapping[str, object]] = {}
    for lock in locks:
        if isinstance(lock, Mapping) and isinstance(lock.get("id"), str):
            found[str(lock["id"]).strip()] = lock
    return found


def _lock_drift(
    lock: Mapping[str, object], canon: Mapping[str, Mapping[str, object]],
) -> list[dict[str, str]]:
    ident = str(lock.get("id") or "").strip()
    named = lock.get("canon_id")
    canon_id = named.strip() if isinstance(named, str) and named.strip() else ident
    if not canon_id:
        return []
    source = canon.get(canon_id)
    if source is None:
        if canon_id != ident:
            return [_finding(
                "LOCK_CANON_MISSING", f"lock {ident} names canon_id {canon_id}, not in canon",
                lock=ident, canon_id=canon_id,
            )]
        return []
    found: list[dict[str, str]] = []
    for field in FIELDS:
        mine, theirs = _line(lock.get(field)), _line(source.get(field))
        if mine == theirs:
            continue
        found.append(_finding(
            "LOCK_CANON_DRIFT",
            f"lock {ident} {field} differs from canon {canon_id}",
            lock=ident, canon_id=canon_id, field=field,
            plan_text=mine or "", canon_text=theirs or "",
        ))
    mine_flag, canon_flag = _critical(lock.get("critical")), _critical(source.get("critical"))
    if mine_flag != canon_flag:
        found.append(_finding(
            "LOCK_CANON_DRIFT",
            f"lock {ident} critical differs from canon {canon_id}",
            lock=ident, canon_id=canon_id, field="critical",
            plan_text=str(mine_flag).lower(), canon_text=str(canon_flag).lower(),
        ))
    return found


def _resolve(path: Path, base_dir: Path) -> Path:
    if path.is_absolute():
        return path
    for folder in (base_dir, *base_dir.parents, Path.cwd()):
        candidate = folder / path
        if candidate.is_file():
            return candidate
    return base_dir / path


def canon_lock_drift(
    document: Mapping[str, object],
    base_dir: Path,
    load: Callable[[Path], object],
) -> list[dict[str, str]]:
    """Findings for plan locks whose text differs from the named canon lock file."""
    if "canon_locks" not in document:
        return []
    raw_path = document.get("canon_locks")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return [_finding("LOCK_CANON_UNREADABLE", "canon_locks must be a file path")]
    path = _resolve(Path(raw_path.strip()), base_dir)
    try:
        canon = _canon_by_id(load(path))
    except (OSError, ValueError) as exc:
        return [_finding("LOCK_CANON_UNREADABLE", f"cannot load canon locks {path}: {exc}")]
    if canon is None:
        return [_finding("LOCK_CANON_UNREADABLE", f"canon locks {path} has no locks list")]
    locks = document.get("locks")
    if not isinstance(locks, Sequence) or isinstance(locks, (str, bytes)):
        return []
    found: list[dict[str, str]] = []
    for lock in locks:
        if isinstance(lock, Mapping):
            found.extend(_lock_drift(lock, canon))
    return found


def canon_block(document: Mapping[str, object], plan_path: str | Path) -> str | None:
    """``LOCK_CANON_* message`` when the plan's locks drift from its canon, else None."""
    from kubrick.runtime.io_safety import load_structured

    found = canon_lock_drift(document, Path(plan_path).resolve().parent, load_structured)
    if not found:
        return None
    first = found[0]
    rest = f" (+{len(found) - 1} more)" if len(found) > 1 else ""
    return f"{first['code']} {first['message']}{rest}"
