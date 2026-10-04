#!/usr/bin/env python3
"""Claim-level provenance labels and collision taxonomy for Kubrick.

Shared by retrieval, production surfaces, and learn/evolve receipts so collision
and provenance vocabulary stays stable across the operator surface.
"""
from __future__ import annotations

from typing import Any

# Stable collision taxonomy (extend only with regression coverage).
COLLISION_TYPES = frozenset(
    {
        "PROHIBITED",
        "REDUNDANT",
        "CONTRADICTORY",
        "CULTURALLY_INCOMPATIBLE",
        "RHYTHMICALLY_OVERLAPPING",
        "PAYOFF_COMPETITION",
        "OWNERSHIP_CONFLICT",
        "GEOMETRY_RESET",
        "RESIDUE_ERASURE",
        "AUTHORITY_PROMOTION",
        "PROVIDER_SEMANTIC_DROP",
    }
)

HARD_FAIL_COLLISIONS = frozenset(
    {
        "PROHIBITED",
        "CONTRADICTORY",
        "CULTURALLY_INCOMPATIBLE",
        "OWNERSHIP_CONFLICT",
        "AUTHORITY_PROMOTION",
        "PROVIDER_SEMANTIC_DROP",
    }
)

PROVENANCE_LABELS = frozenset({"observed", "inferred", "speculative", "external_authoritative"})


def provenance_bucket(
    *,
    observed: list[str] | None = None,
    inferred: list[str] | None = None,
    speculative: list[str] | None = None,
    external_authoritative: list[str] | None = None,
) -> dict[str, list[str]]:
    return {
        "observed": list(observed or []),
        "inferred": list(inferred or []),
        "speculative": list(speculative or []),
        "external_authoritative": list(external_authoritative or []),
    }


def claim(
    claim_id: str,
    text: str,
    *,
    label: str = "observed",
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    if label not in PROVENANCE_LABELS:
        raise ValueError(f"unknown provenance label: {label}")
    return {
        "claim_id": claim_id,
        "text": text,
        "label": label,
        "evidence_refs": list(evidence_refs or []),
    }
