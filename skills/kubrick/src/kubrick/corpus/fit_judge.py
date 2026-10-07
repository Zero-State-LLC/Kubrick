"""Second-opinion dramatic fit for retrieval (#91).

Lexical scoring finds shared words, so vocabulary soup can pass and a plain
brief can fail. A judge (Jev) gives each pattern a verdict: ``fit``, ``weak``
or ``none``. Selection needs both signals:

- ``fit`` and a lexical total at or above ``STRUCTURAL_FLOOR``. The floor keeps
  hard collisions (score 0) and heavy cost, ledger or collision penalties out.
- ``weak`` and full lexical eligibility (threshold and dramatic-fit floor).
- ``none`` (or no verdict) is never selected.

CI uses recorded verdicts keyed by the brief's SHA-256. A brief with no
recorded verdict fails closed (``JEV_FIT_UNAVAILABLE``).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

STRUCTURAL_FLOOR = 0.40
VERDICTS = frozenset({"fit", "weak", "none"})


def brief_sha256(brief: Mapping[str, object]) -> str:
    """Stable key for a brief: SHA-256 of its canonical JSON."""
    text = json.dumps(brief, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_recorded(path: Path) -> dict[str, dict[str, str]]:
    """Recorded verdict sets by brief SHA-256. Unknown verdict words are an error."""
    from kubrick.runtime.runtime_deps import yaml_load

    loaded = yaml_load(path.read_text(encoding="utf-8"))
    rows = loaded.get("recordings") if isinstance(loaded, Mapping) else None
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise ValueError(f"{path} has no recordings list")
    found: dict[str, dict[str, str]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError(f"{path} has a recording that is not a mapping")
        key = str(row.get("brief_sha256") or "").strip()
        verdicts = row.get("verdicts")
        if not key or not isinstance(verdicts, Mapping):
            raise ValueError(f"{path} recording needs brief_sha256 and verdicts")
        clean: dict[str, str] = {}
        for pattern_id, verdict in verdicts.items():
            word = str(verdict).strip().casefold()
            if word not in VERDICTS:
                raise ValueError(f"{path}: {pattern_id} verdict {verdict!r} is not fit/weak/none")
            clean[str(pattern_id)] = word
        found[key] = clean
    return found


def fit_select(
    ranked: Sequence[Mapping[str, object]],
    verdicts: Mapping[str, str],
    *,
    floor: float,
    threshold: float,
    min_dramatic_fit: float,
    max_supporting: int,
) -> tuple[list[Mapping[str, object]], str | None]:
    def as_float(value: object) -> float:
        if isinstance(value, bool):
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        return 0.0

    fit_items: list[Mapping[str, object]] = []
    weak_items: list[Mapping[str, object]] = []
    has_fit_or_weak = False

    for item in ranked:
        pattern_id_obj = item.get("pattern_id")
        if isinstance(pattern_id_obj, str):
            verdict = verdicts.get(pattern_id_obj, "none")
        else:
            verdict = "none"
        verdict = verdict.strip().casefold()
        if verdict in {"fit", "weak"}:
            has_fit_or_weak = True

        total_score = as_float(item.get("total_score"))
        components_obj = item.get("score_components")
        dramatic_fit = 0.0
        if isinstance(components_obj, Mapping):
            dramatic_fit = as_float(components_obj.get("dramatic_fit"))

        if verdict == "fit" and total_score >= floor:
            fit_items.append(item)
        elif verdict == "weak" and total_score >= threshold and dramatic_fit >= min_dramatic_fit:
            weak_items.append(item)

    eligible = fit_items + weak_items
    if not eligible:
        reason = "JEV_FIT_BELOW_FLOOR" if has_fit_or_weak else "JEV_FIT_NONE"
        return [], reason

    limit = max_supporting + 1
    chosen: list[Mapping[str, object]]
    if limit > 0:
        chosen = eligible[:limit]
    else:
        chosen = []
    return chosen, None


def apply_fit(
    receipt: dict[str, object],
    ranked: Sequence[Mapping[str, object]],
    verdicts: Mapping[str, str] | None,
    *,
    threshold: float,
    min_dramatic_fit: float,
    max_supporting: int,
    source: str,
) -> dict[str, object]:
    """Re-select a lexical receipt with fit verdicts. ``None`` verdicts fail closed."""
    from kubrick.corpus.retrieve_symbolic_patterns import receipt_ranking

    chosen: list[Mapping[str, object]] = []
    reason: str | None = "JEV_FIT_UNAVAILABLE"
    if verdicts is not None:
        chosen, reason = fit_select(
            ranked, verdicts, floor=STRUCTURAL_FLOOR, threshold=threshold,
            min_dramatic_fit=min_dramatic_fit, max_supporting=max_supporting,
        )
    primary = dict(chosen[0]) if chosen else None
    supporting = [dict(item) for item in chosen[1:]]
    lexical = receipt.get("selected_primary_grammar")
    receipt["selected_primary_grammar"] = primary["pattern_id"] if primary else None
    receipt["selected_supporting_grammars"] = [item["pattern_id"] for item in supporting]
    receipt["ranked_patterns"] = receipt_ranking([dict(i) for i in ranked], primary, supporting)
    receipt["confidence"] = primary["total_score"] if primary else 0.0
    receipt["status"] = "SELECTED" if primary else "NOT_COMPUTABLE"
    if primary:
        receipt["reason_vector"] = []
    else:
        prior = receipt.get("reason_vector")
        kept = [str(x) for x in prior] if isinstance(prior, list) else []
        receipt["reason_vector"] = [str(reason), *kept]
    receipt["fit_judge"] = {
        "source": source,
        "structural_floor": STRUCTURAL_FLOOR,
        "lexical_primary": lexical,
        "primary_verdict": (verdicts or {}).get(str(primary["pattern_id"])) if primary else None,
    }
    return receipt
