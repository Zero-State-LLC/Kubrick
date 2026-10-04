#!/usr/bin/env python3
"""Jev judge clients. Recorded verdicts keep CI off the network.

A live client posts to ``KUBRICK_JEV_URL``. Anything incomplete, contradictory,
or unreachable raises ``JevUnreachable`` so the gate can fail closed.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from typing import Protocol

_VERDICTS = frozenset({"pass", "fail"})
_SCHEMES = frozenset({"http", "https"})
Transport = Callable[[str, Mapping[str, object], float], object]


class JevUnreachable(Exception):
    """Jev returned nothing the gate can trust."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class JevClient(Protocol):
    """One judge call per prompt. Implementations raise ``JevUnreachable``."""

    def judge(
        self,
        prompt: Mapping[str, object],
        holds: Sequence[Mapping[str, object]],
    ) -> Mapping[str, object]:
        """Return ``verdict`` of pass or fail, plus ``findings``."""


def prompt_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def judge_prompt(prompt: Mapping[str, object]) -> dict[str, object]:
    raw_surfaces = prompt.get("surfaces")
    surfaces = list(raw_surfaces) if isinstance(raw_surfaces, list) else []
    return {
        "shot": prompt.get("shot"),
        "channel": prompt.get("channel"),
        "surfaces": surfaces,
        "location": prompt.get("location"),
        "prompt": prompt.get("prompt"),
    }


def _finding(raw: object) -> dict[str, str] | None:
    if not isinstance(raw, Mapping):
        return None
    code = raw.get("code")
    message = raw.get("message")
    if not isinstance(code, str) or not code.strip():
        return None
    if not isinstance(message, str) or not message.strip():
        return None
    found = {"code": code.strip(), "message": message.strip()}
    hold_id = raw.get("hold_id")
    if isinstance(hold_id, str) and hold_id.strip():
        found["hold_id"] = hold_id.strip()
    return found


def parse_verdict(payload: object) -> dict[str, object]:
    """Accept a Jev object. Contradictory or incomplete payloads are unreachable."""
    if not isinstance(payload, Mapping):
        raise JevUnreachable("Jev response is not an object")
    verdict = payload.get("verdict")
    if not isinstance(verdict, str) or verdict not in _VERDICTS:
        raise JevUnreachable("Jev verdict is missing")
    raw_findings = payload.get("findings", [])
    if raw_findings is None:
        raw_findings = []
    if not isinstance(raw_findings, list):
        raise JevUnreachable("Jev findings are not a list")
    findings: list[dict[str, str]] = []
    for item in raw_findings:
        parsed = _finding(item)
        if parsed is None:
            raise JevUnreachable("Jev finding is incomplete")
        findings.append(parsed)
    if verdict == "pass" and findings:
        raise JevUnreachable("Jev returned a pass verdict with findings")
    if verdict == "fail" and not findings:
        findings.append({
            "code": "JEV_HOLD",
            "message": "Jev failed the prompt and did not name the hold",
        })
    return {"verdict": verdict, "findings": findings}


def post_json(url: str, body: Mapping[str, object], timeout: float) -> object:
    """POST one judge request. Any transport failure is ``JevUnreachable``."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in _SCHEMES or not parsed.netloc:
        raise JevUnreachable("Jev URL is not an http(s) endpoint")
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            raw = response.read(1_000_000)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise JevUnreachable(f"Jev request failed: {exc}") from exc
    if status != 200:
        raise JevUnreachable(f"Jev returned HTTP {status}")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise JevUnreachable("Jev response is not JSON") from exc


class HttpJevClient:
    """Live Jev. The endpoint is ``KUBRICK_JEV_URL`` or the constructor argument."""

    def __init__(
        self,
        url: str,
        timeout: float = 10.0,
        transport: Transport | None = None,
    ) -> None:
        self._url = url
        self._timeout = timeout
        self._transport = transport or post_json

    def judge(
        self,
        prompt: Mapping[str, object],
        holds: Sequence[Mapping[str, object]],
    ) -> Mapping[str, object]:
        if self._timeout <= 0:
            raise JevUnreachable("Jev timeout is not positive")
        body = {"prompt": judge_prompt(prompt), "holds": [dict(item) for item in holds]}
        return parse_verdict(self._transport(self._url, body, self._timeout))


class RecordedJev:
    """Verdicts keyed by the sha256 of the prompt text. CI uses this, not the network."""

    def __init__(self, verdicts: Mapping[str, Mapping[str, object]]) -> None:
        self._verdicts = verdicts
        self.seen_hold_ids: list[list[str]] = []

    def judge(
        self,
        prompt: Mapping[str, object],
        holds: Sequence[Mapping[str, object]],
    ) -> Mapping[str, object]:
        self.seen_hold_ids.append([
            str(item.get("id")) for item in holds if item.get("id") is not None
        ])
        text = prompt.get("prompt")
        key = prompt_sha256(text if isinstance(text, str) else "")
        found = self._verdicts.get(key)
        if found is None:
            raise JevUnreachable(f"no recorded verdict for {key}")
        return parse_verdict(found)


def load_recorded(path: str) -> RecordedJev:
    """Load ``{"verdicts": {sha256: {verdict, findings}}}``."""
    from io_safety import load_structured

    try:
        raw = load_structured(path)
    except (OSError, ValueError) as exc:
        raise JevUnreachable(f"recorded verdicts could not be read: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise JevUnreachable("recorded verdicts must be an object")
    verdicts = raw.get("verdicts")
    if not isinstance(verdicts, Mapping):
        raise JevUnreachable("recorded verdicts are missing the verdicts object")
    cleaned: dict[str, Mapping[str, object]] = {}
    for key, value in verdicts.items():
        if not isinstance(value, Mapping):
            raise JevUnreachable(f"recorded verdict {key} is not an object")
        cleaned[str(key)] = value
    return RecordedJev(cleaned)


def resolve_client(
    verdicts_path: str | None = None,
    client: JevClient | None = None,
) -> JevClient:
    """Recorded file, then ``KUBRICK_JEV_VERDICTS``, then ``KUBRICK_JEV_URL``."""
    if client is not None:
        return client
    configured = verdicts_path or os.environ.get("KUBRICK_JEV_VERDICTS", "")
    path = configured.strip() if isinstance(configured, str) else ""
    if path:
        return load_recorded(path)
    url = os.environ.get("KUBRICK_JEV_URL", "").strip()
    if url:
        return HttpJevClient(url)
    raise JevUnreachable("Jev is not configured")
