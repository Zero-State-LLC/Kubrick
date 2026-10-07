"""Second-opinion dramatic fit for retrieval (#91).

Lexical scoring finds shared words, so vocabulary soup can pass and a plain
brief can fail. A judge (Jev) gives each pattern a verdict: ``fit``, ``weak``
or ``none``. Selection needs both signals:

- ``fit`` and a lexical total at or above ``STRUCTURAL_FLOOR``. The floor keeps
  hard collisions (score 0) and heavy cost, ledger or collision penalties out.
- ``weak``, ``none`` or no verdict is never selected (0.27.10). Lexical
  eligibility alone let vocabulary-matched briefs through on ``weak``.

CI uses recorded verdicts keyed by the brief's SHA-256. A brief with no
recorded verdict fails closed (``JEV_FIT_UNAVAILABLE``).

0.27.10 screens verdicts first: a ``fit`` with fit probability under
``FIT_PROBABILITY_FLOOR`` counts as ``weak``, and a brief judged ``fit`` for more
than ``MAX_FIT_SHARE`` of the corpus is refused (``JEV_FIT_TOO_BROAD``). A
brief that fits many unrelated patterns is matching vocabulary, not structure.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

STRUCTURAL_FLOOR = 0.40
FIT_PROBABILITY_FLOOR = 0.6
MAX_FIT_SHARE = 0.2
VERDICTS = frozenset({"fit", "weak", "none"})


def brief_sha256(brief: Mapping[str, object]) -> str:
    """Stable key for a brief: SHA-256 of its canonical JSON."""
    text = json.dumps(brief, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_recorded(path: Path) -> dict[str, dict[str, object]]:
    """Recorded sets by brief SHA-256: ``{"verdicts": ..., "probabilities": ...}``.

    Unknown verdict words are an error. ``fit_probability`` is optional.
    """
    from kubrick.runtime.runtime_deps import yaml_load

    loaded = yaml_load(path.read_text(encoding="utf-8"))
    rows = loaded.get("recordings") if isinstance(loaded, Mapping) else None
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise ValueError(f"{path} has no recordings list")
    found: dict[str, dict[str, object]] = {}
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
        probs: dict[str, float] = {}
        raw_probs = row.get("fit_probability")
        if isinstance(raw_probs, Mapping):
            for pattern_id, value in raw_probs.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    probs[str(pattern_id)] = float(value)
        found[key] = {"verdicts": clean, "probabilities": probs}
    return found


def fit_select(
    ranked: Sequence[Mapping[str, object]],
    verdicts: Mapping[str, str],
    *,
    floor: float,
    threshold: float,
    min_dramatic_fit: float,
    max_supporting: int,
    probabilities: Mapping[str, float] | None = None,
) -> tuple[list[Mapping[str, object]], str | None]:
    """Patterns judged ``fit`` with a lexical total at least ``floor``, best first.

    ``weak`` never selects (0.27.10). ``threshold`` and ``min_dramatic_fit`` are kept
    for callers; they no longer open a path on their own. Ranking is lexical; equal
    lexical totals are broken by Jev fit probability (higher first), then by the
    incoming order (0.27.10).
    """
    del threshold, min_dramatic_fit

    def as_float(value: object) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return 0.0
        return float(value)

    eligible: list[Mapping[str, object]] = []
    any_fit = False
    for item in ranked:
        pattern_id = item.get("pattern_id")
        verdict = verdicts.get(pattern_id, "none") if isinstance(pattern_id, str) else "none"
        if verdict.strip().casefold() != "fit":
            continue
        any_fit = True
        if as_float(item.get("total_score")) >= floor:
            eligible.append(item)
    if not eligible:
        return [], "JEV_FIT_BELOW_FLOOR" if any_fit else "JEV_FIT_NONE"
    probs = probabilities or {}

    def rank_key(item: Mapping[str, object]) -> tuple[float, float]:
        pattern_id = item.get("pattern_id")
        prob = probs.get(pattern_id, 0.0) if isinstance(pattern_id, str) else 0.0
        return (-as_float(item.get("total_score")), -float(prob))

    eligible.sort(key=rank_key)  # stable: still-tied items keep the incoming order
    return eligible[: max(0, max_supporting) + 1], None


def screen_verdicts(
    verdicts: Mapping[str, str],
    probabilities: Mapping[str, float],
    *,
    fit_floor: float,
    max_fit_share: float,
    corpus_size: int,
) -> tuple[dict[str, str], str | None]:
    screened: dict[str, str] = {}
    fit_count = 0

    for pattern_id, verdict in verdicts.items():
        normalized = verdict.strip().casefold()
        if normalized == "fit" and pattern_id in probabilities:
            if probabilities[pattern_id] < fit_floor:
                screened[pattern_id] = "weak"
                continue
        screened[pattern_id] = verdict
        if normalized == "fit":
            fit_count += 1

    cap = max(1, int(corpus_size * max_fit_share))
    if fit_count > cap:
        return screened, "JEV_FIT_TOO_BROAD"
    return screened, None


def _unpack(recording: Mapping[str, object]) -> tuple[dict[str, str], dict[str, float]]:
    verdicts = recording.get("verdicts")
    if not isinstance(verdicts, Mapping):
        return {str(k): str(v) for k, v in recording.items()}, {}
    probs = recording.get("probabilities")
    clean = {str(k): float(v) for k, v in probs.items()} if isinstance(probs, Mapping) else {}
    return {str(k): str(v) for k, v in verdicts.items()}, clean


def apply_fit(
    receipt: dict[str, object],
    ranked: Sequence[Mapping[str, object]],
    recording: Mapping[str, object] | None,
    *,
    threshold: float,
    min_dramatic_fit: float,
    max_supporting: int,
    source: str,
) -> dict[str, object]:
    """Re-select a lexical receipt with fit verdicts. No recording fails closed.

    ``recording`` is ``{"verdicts", "probabilities"}`` or a plain verdict map.
    """
    from kubrick.corpus.retrieve_symbolic_patterns import receipt_ranking

    chosen: list[Mapping[str, object]] = []
    reason: str | None = "JEV_FIT_UNAVAILABLE"
    verdicts: dict[str, str] | None = None
    probs: dict[str, float] = {}
    if recording is not None:
        raw, probs = _unpack(recording)
        verdicts, reason = screen_verdicts(
            raw, probs, fit_floor=FIT_PROBABILITY_FLOOR, max_fit_share=MAX_FIT_SHARE,
            corpus_size=len(ranked),
        )
    if verdicts is not None and reason is None:
        chosen, reason = fit_select(
            ranked, verdicts, floor=STRUCTURAL_FLOOR, threshold=threshold,
            min_dramatic_fit=min_dramatic_fit, max_supporting=max_supporting,
            probabilities=probs,
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
        "fit_probability_floor": FIT_PROBABILITY_FLOOR,
        "max_fit_share": MAX_FIT_SHARE,
        "fit_count": sum(1 for v in (verdicts or {}).values() if v.strip().casefold() == "fit"),
        "lexical_primary": lexical,
        "primary_verdict": (verdicts or {}).get(str(primary["pattern_id"])) if primary else None,
    }
    return receipt
