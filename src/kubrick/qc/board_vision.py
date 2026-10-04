#!/usr/bin/env python3
"""Pluggable, local-only vision backends for the board image gate.

Two interfaces:

- ``Embedder.embed(image)`` returns a feature vector. The default is DINOv2
  (``facebook/dinov2-small``) on CPU through ``torch`` and ``transformers``,
  both in the optional ``board-vision`` extra.
- ``LockJudge.ask(image, image_sha256, question)`` answers ``yes``, ``no``, or
  ``unknown``. The default is a local vision-language model behind an
  Ollama-compatible endpoint on the loopback interface
  (``KUBRICK_BOARD_VLM_URL``). A recorded answers file replays verdicts.

Nothing here calls a paid API. A non-loopback judge URL is refused. Heavy
packages are imported on first use, never at module load, so CI without them
still imports this module. A backend that cannot run raises
``BackendUnavailable`` and the gate reports the check as UNVERIFIED.
"""
from __future__ import annotations

import base64
import importlib
import ipaddress
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from kubrick.qc.board_pixels import RGBImage, encode_png

DEFAULT_EMBED_MODEL = "facebook/dinov2-small"
DEFAULT_VLM_MODEL = "qwen2.5vl:3b"
_ANSWERS = frozenset({"yes", "no"})
_LOOPBACK_NAMES = frozenset({"localhost"})


class BackendUnavailable(RuntimeError):
    """A local model or its packages are not available. The check is UNVERIFIED."""


class Embedder(Protocol):
    name: str

    def embed(self, image: RGBImage) -> list[float]:
        """Feature vector for one crop. Raise ``BackendUnavailable`` when it cannot run."""
        ...


class LockJudge(Protocol):
    name: str

    def ask(self, image: RGBImage, image_sha256: str, question: str) -> str:
        """``yes``, ``no``, or ``unknown``. Raise ``BackendUnavailable`` when it cannot run."""
        ...


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    """Cosine similarity. Mismatched or zero vectors raise ``ValueError``."""
    if len(left) != len(right) or not left:
        raise ValueError("embedding sizes differ")
    dot = sum(a * b for a, b in zip(left, right))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    if norm == 0.0:
        raise ValueError("embedding has zero length")
    return dot / norm


class Dinov2Embedder:
    """DINOv2 CLS features on CPU. Loaded once, on first use."""

    def __init__(self, model_id: str | None = None) -> None:
        self.model_id = model_id or os.environ.get("KUBRICK_BOARD_EMBED_MODEL", "").strip() \
            or DEFAULT_EMBED_MODEL
        self.name = f"dinov2:{self.model_id}"
        self._loaded: tuple[Any, Any, Any, Any] | None = None

    def _load(self) -> tuple[Any, Any, Any, Any]:
        if self._loaded is not None:
            return self._loaded
        try:
            torch = importlib.import_module("torch")
            transformers = importlib.import_module("transformers")
            pil = importlib.import_module("PIL.Image")
        except ImportError as exc:
            raise BackendUnavailable(
                f"DINOv2 needs torch, transformers, and Pillow ({exc.name} is missing); "
                "install the board-vision extra"
            ) from exc
        try:
            processor = transformers.AutoImageProcessor.from_pretrained(self.model_id)
            model = transformers.AutoModel.from_pretrained(self.model_id)
            model.eval()
        except Exception as exc:  # download, cache, or config failures
            raise BackendUnavailable(f"cannot load {self.model_id}: {exc}") from exc
        self._loaded = (torch, pil, processor, model)
        return self._loaded

    def embed(self, image: RGBImage) -> list[float]:
        torch, pil, processor, model = self._load()
        try:
            picture = pil.frombytes("RGB", (image.width, image.height), image.pixels)
            inputs = processor(images=picture, return_tensors="pt")
            with torch.no_grad():
                output = model(**inputs)
            pooled = getattr(output, "pooler_output", None)
            if pooled is None:
                pooled = output.last_hidden_state[:, 0]
            return [float(value) for value in pooled[0].tolist()]
        except Exception as exc:  # preprocessing, inference, or memory failures
            raise BackendUnavailable(f"{self.model_id} inference failed: {exc}") from exc


def _loopback(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    host = parsed.hostname
    if host in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def parse_answer(text: object) -> str:
    """First word of a reply, as ``yes``, ``no``, or ``unknown``."""
    if not isinstance(text, str):
        return "unknown"
    words = text.strip().casefold().replace(".", " ").replace(",", " ").split()
    if not words:
        return "unknown"
    first = words[0].strip("\"'*")
    return first if first in _ANSWERS else "unknown"


class LoopbackVlmJudge:
    """Local vision-language model behind an Ollama-compatible ``/api/generate``.

    Free and local only: the endpoint must resolve to the loopback interface.
    """

    def __init__(
        self, url: str | None = None, model: str | None = None, timeout: float = 120.0,
    ) -> None:
        self.url = (url if url is not None else os.environ.get("KUBRICK_BOARD_VLM_URL", "")).strip()
        self.model = (
            model or os.environ.get("KUBRICK_BOARD_VLM_MODEL", "").strip() or DEFAULT_VLM_MODEL
        )
        self.timeout = timeout
        self.name = f"local-vlm:{self.model}"

    def ask(self, image: RGBImage, image_sha256: str, question: str) -> str:
        if not self.url:
            raise BackendUnavailable(
                "no local vision-language model is configured (KUBRICK_BOARD_VLM_URL)"
            )
        if not _loopback(self.url):
            raise BackendUnavailable(
                "KUBRICK_BOARD_VLM_URL must be a loopback http(s) URL; remote judges are refused"
            )
        body = {
            "model": self.model,
            "prompt": question,
            "images": [base64.b64encode(encode_png(image)).decode("ascii")],
            "stream": False,
            "options": {"temperature": 0},
        }
        endpoint = self.url.rstrip("/") + "/api/generate"
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # nosec B310
                raw = response.read(1_000_000)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise BackendUnavailable(f"local judge request failed: {exc}") from exc
        try:
            reply = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise BackendUnavailable("local judge response is not JSON") from exc
        if not isinstance(reply, Mapping):
            raise BackendUnavailable("local judge response is not an object")
        return parse_answer(reply.get("response"))


class RecordedJudge:
    """Replay answers from ``{"answers": {"<image sha256>": {"<question>": "yes"}}}``."""

    name = "recorded"

    def __init__(self, answers: Mapping[str, Mapping[str, str]]) -> None:
        self.answers = answers

    @classmethod
    def from_file(cls, path: str) -> RecordedJudge:
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise BackendUnavailable(f"cannot load recorded judge answers: {exc}") from exc
        table = raw.get("answers") if isinstance(raw, Mapping) else None
        if not isinstance(table, Mapping):
            raise BackendUnavailable("recorded judge answers need an 'answers' object")
        answers: dict[str, dict[str, str]] = {}
        for digest, rows in table.items():
            if isinstance(rows, Mapping):
                answers[str(digest)] = {str(q): str(a) for q, a in rows.items()}
        return cls(answers)

    def ask(self, image: RGBImage, image_sha256: str, question: str) -> str:
        rows = self.answers.get(image_sha256)
        if rows is None or question not in rows:
            raise BackendUnavailable("no recorded answer for this board and question")
        return parse_answer(rows[question])


def resolve_judge(answers_path: str | None = None) -> LockJudge:
    """Recorded answers when given (flag or ``KUBRICK_BOARD_JUDGE_ANSWERS``), else local VLM."""
    path = answers_path or os.environ.get("KUBRICK_BOARD_JUDGE_ANSWERS", "").strip()
    if path:
        return RecordedJudge.from_file(path)
    return LoopbackVlmJudge()


def resolve_embedder() -> Embedder:
    return Dinov2Embedder()
