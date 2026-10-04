#!/usr/bin/env python3
"""Verbatim multi-word phrase copies across disentangled brief layers.

A noun that appears in more than one layer is allowed. A repeated multi-word
phrase is rejected, and the finding names the phrase and both layers. The
legacy prefix is kept so older eval text still matches.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

LAYER_KEYS = ("layout_geometry", "semantics_function", "attributes_states")
_SPACE = re.compile(r"\s+")
_PREFIX = "attribute leakage detected across disentangled layers"


def normalize_phrase(text: str) -> str:
    return _SPACE.sub(" ", text.strip().lower())


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        found: list[str] = []
        for item in value:
            found.extend(_strings(item))
        return found
    return []


def leakage_findings(layers: Mapping[str, object]) -> list[str]:
    owners: dict[str, list[str]] = {}
    for key in LAYER_KEYS:
        seen: set[str] = set()
        for raw in _strings(layers.get(key, [])):
            phrase = normalize_phrase(raw)
            if len(phrase.split(" ")) < 2 or phrase in seen:
                continue
            seen.add(phrase)
            owners.setdefault(phrase, []).append(key)
    findings: list[str] = []
    for phrase in sorted(owners):
        layers_used = owners[phrase]
        if len(layers_used) < 2:
            continue
        for index, left in enumerate(layers_used):
            for right in layers_used[index + 1 :]:
                findings.append(
                    f"{_PREFIX}: phrase {phrase!r} is repeated in {left} and {right}"
                )
    return findings
