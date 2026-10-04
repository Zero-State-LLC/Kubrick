#!/usr/bin/env python3
"""Jev judge clients. Recorded verdicts keep CI off the network.

A live client posts to ``KUBRICK_JEV_URL``. Anything incomplete, contradictory,
or unreachable raises ``JevUnreachable`` so the gate can fail closed.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from typing import Protocol

from hold_scope import choose_sample, per_hold_verdict

_VERDICTS = frozenset({"pass", "fail"})
_SCHEMES = frozenset({"http", "https"})
Transport = Callable[[str, Mapping[str, object], float], object]


class JevUnreachable(Exception):
    """Jev returned nothing the gate can trust."""

    def __init__(self, reason: str, *, retryable: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retryable = retryable


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


def judged_body(
    prompt: Mapping[str, object], holds: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """The request live Jev sees: prompt context plus the hold list."""
    return {
        "prompt": judge_prompt(prompt),
        "holds": [dict(item) for item in holds],
    }


def verdict_key(
    prompt: Mapping[str, object], holds: Sequence[Mapping[str, object]],
) -> str:
    """Sha256 of the judged prompt and the holds. Either change misses the cache."""
    try:
        encoded = json.dumps(
            judged_body(prompt, holds),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    except (TypeError, ValueError) as exc:
        raise JevUnreachable("recorded verdict key is not computable") from exc
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


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
    per_hold = per_hold_verdict(payload)
    if per_hold is not None:
        if "error" in per_hold:
            raise JevUnreachable(str(per_hold["error"]))
        return per_hold
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
        raise JevUnreachable(f"Jev request failed: {exc}", retryable=True) from exc
    if status != 200:
        raise JevUnreachable(f"Jev returned HTTP {status}")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise JevUnreachable("Jev response is not JSON") from exc


_ATTEMPTS = 3
_BACKOFF_SECONDS = (0.25, 0.5)
Sleeper = Callable[[float], None]


def configured_timeout(explicit: float | None = None) -> float:
    """``KUBRICK_JEV_TIMEOUT`` when set, otherwise 10 seconds. Fail closed."""
    if explicit is not None:
        value: object = explicit
    else:
        raw = os.environ.get("KUBRICK_JEV_TIMEOUT", "").strip()
        if not raw:
            value = 10.0
        else:
            try:
                value = float(raw)
            except ValueError as exc:
                raise JevUnreachable("KUBRICK_JEV_TIMEOUT is not a positive number") from exc
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise JevUnreachable("Jev timeout is not positive")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise JevUnreachable("Jev timeout is not positive")
    return number


class HttpJevClient:
    """Live Jev. The endpoint is ``KUBRICK_JEV_URL`` or the constructor argument."""

    def __init__(
        self,
        url: str,
        timeout: float | None = None,
        transport: Transport | None = None,
        *,
        sleeper: Sleeper | None = None,
        attempts: int = _ATTEMPTS,
    ) -> None:
        if attempts < 1:
            raise JevUnreachable("Jev retry count is not positive")
        self._url = url
        self._timeout = configured_timeout(timeout)
        self.timeout = self._timeout
        self._transport = transport or post_json
        self._sleep = sleeper or _sleep
        self._attempts = attempts

    def judge(
        self,
        prompt: Mapping[str, object],
        holds: Sequence[Mapping[str, object]],
    ) -> Mapping[str, object]:
        body = judged_body(prompt, holds)
        last = JevUnreachable("Jev request failed", retryable=True)
        for attempt in range(self._attempts):
            try:
                return parse_verdict(self._transport(self._url, body, self._timeout))
            except JevUnreachable as exc:
                last = exc
                if not exc.retryable or attempt + 1 >= self._attempts:
                    raise
            except (TimeoutError, OSError) as exc:
                last = JevUnreachable(f"Jev request failed: {exc}", retryable=True)
                if attempt + 1 >= self._attempts:
                    raise last from exc
            self._sleep(_BACKOFF_SECONDS[min(attempt, len(_BACKOFF_SECONDS) - 1)])
        raise last


def _sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)


class RecordedJev:
    """Verdicts keyed by ``verdict_key``. CI uses this, not the network."""

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
        key = verdict_key(prompt, holds)
        found = self._verdicts.get(key)
        if found is None:
            raise JevUnreachable(f"no recorded verdict for {key}")
        return parse_verdict(choose_sample(found))


def load_recorded(path: str) -> RecordedJev:
    """Load ``{"verdicts": {verdict_key: {verdict, findings}}}``."""
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
