#!/usr/bin/env python3
"""Loopback adapter from Ollama ``/api/generate`` to any OpenAI-compatible vision endpoint.

The board image lock judge (``LoopbackVlmJudge``) only talks to a loopback URL
and speaks Ollama's ``/api/generate``. This proxy listens on loopback only and
forwards each request as ``POST {upstream}/chat/completions`` with the image as
a ``data:`` URL. The provider is configuration, not code: upstream URL, model
id, key source, extra headers, and extra request fields all come from the
environment (usually a profile file). Contract: docs/BOARD-VISION-SETUP.md.

Fail closed: no upstream URL, a key source that is configured but empty, a
plain-http upstream that is not loopback, a non-loopback listen address, or
bad JSON in the extra settings stops the proxy at start. Any upstream error,
timeout, or reply without ``choices[0].message.content`` is HTTP 502, which the
judge treats as ``BackendUnavailable``, so the lock check is UNVERIFIED and
blocks. The key is never logged or returned.

Env:
  KUBRICK_VLM_PROXY_ADDR       listen address, default 127.0.0.1:11435 (loopback only)
  KUBRICK_VLM_UPSTREAM_URL     OpenAI-compatible base URL ending in /v1 (required)
  KUBRICK_VLM_UPSTREAM_MODEL   model id; default: first id from GET {upstream}/models
  KUBRICK_VLM_API_KEY_ENV      name of the env var that holds the key (optional)
  KUBRICK_VLM_API_KEY_FILE     file that holds the key, read when the env var is empty
  KUBRICK_VLM_EXTRA_HEADERS    JSON object of extra request headers (e.g. User-Agent)
  KUBRICK_VLM_EXTRA_BODY       JSON object merged into each chat request (e.g. to turn
                               off a model's thinking mode)
  KUBRICK_VLM_MAX_TOKENS       default 64 (the judge needs one word)
  KUBRICK_VLM_TIMEOUT          upstream timeout in seconds, default 120
With neither key setting, no Authorization header is sent (local servers).
"""
from __future__ import annotations

import ipaddress
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

DEFAULT_ADDR = "127.0.0.1:11435"
DEFAULT_USER_AGENT = "kubrick-vlm-proxy/1"
VERSION = "0.27.0-vlm-proxy"


class ProxyConfigError(RuntimeError):
    """The proxy cannot start with this configuration."""


def _is_loopback(host: str) -> bool:
    if host.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def _json_object(raw: str, name: str) -> dict[str, Any]:
    if not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProxyConfigError(f"{name} is not valid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ProxyConfigError(f"{name} must be a JSON object")
    return value


def _merge(base: dict[str, Any], extra: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in extra.items():
        if isinstance(value, Mapping) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


@dataclass
class ProxyConfig:
    upstream: str = ""
    addr: str = DEFAULT_ADDR
    model: str | None = None
    key_env: str = ""
    key_file: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    extra_body: dict[str, Any] = field(default_factory=dict)
    max_tokens: int = 64
    timeout: float = 120.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> ProxyConfig:
        env = os.environ if env is None else env
        headers = _json_object(env.get("KUBRICK_VLM_EXTRA_HEADERS", ""),
                               "KUBRICK_VLM_EXTRA_HEADERS")
        try:
            max_tokens = int(env.get("KUBRICK_VLM_MAX_TOKENS", "64") or 64)
            timeout = float(env.get("KUBRICK_VLM_TIMEOUT", "120") or 120)
        except ValueError as exc:
            raise ProxyConfigError(f"bad number: {exc}") from exc
        return cls(
            upstream=env.get("KUBRICK_VLM_UPSTREAM_URL", "").strip().rstrip("/"),
            addr=env.get("KUBRICK_VLM_PROXY_ADDR", "").strip() or DEFAULT_ADDR,
            model=env.get("KUBRICK_VLM_UPSTREAM_MODEL", "").strip() or None,
            key_env=env.get("KUBRICK_VLM_API_KEY_ENV", "").strip(),
            key_file=env.get("KUBRICK_VLM_API_KEY_FILE", "").strip(),
            headers={str(k): str(v) for k, v in headers.items()},
            extra_body=_json_object(env.get("KUBRICK_VLM_EXTRA_BODY", ""),
                                    "KUBRICK_VLM_EXTRA_BODY"),
            max_tokens=max_tokens, timeout=timeout,
        )

    def host_port(self) -> tuple[str, int]:
        host, _, port = self.addr.rpartition(":")
        if not _is_loopback(host):
            raise ProxyConfigError(f"refusing to bind non-loopback address {host!r}")
        try:
            return host, int(port)
        except ValueError as exc:
            raise ProxyConfigError(f"bad listen port in {self.addr!r}") from exc

    def validate(self) -> None:
        """Fail closed at start. Raises ``ProxyConfigError``."""
        self.host_port()
        if not self.upstream:
            raise ProxyConfigError("KUBRICK_VLM_UPSTREAM_URL is not set")
        parts = urllib.parse.urlsplit(self.upstream)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ProxyConfigError("KUBRICK_VLM_UPSTREAM_URL must be an http(s) URL")
        if parts.scheme == "http" and not _is_loopback(parts.hostname):
            raise ProxyConfigError("a non-loopback upstream must use https")
        self.key()

    def key(self) -> str | None:
        """The key, ``None`` when no key source is configured. Empty configured source raises."""
        if not self.key_env and not self.key_file:
            return None
        value = os.environ.get(self.key_env, "").strip() if self.key_env else ""
        if not value and self.key_file:
            path = Path(self.key_file).expanduser()
            value = path.read_text(encoding="utf-8").strip() if path.is_file() else ""
        if not value:
            raise ProxyConfigError("the configured API key source is empty "
                                   "(KUBRICK_VLM_API_KEY_ENV / KUBRICK_VLM_API_KEY_FILE)")
        return value

    def request_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "User-Agent": DEFAULT_USER_AGENT}
        headers.update(self.headers)
        key = self.key()
        if key is not None:
            headers["Authorization"] = "Bearer " + key
        return headers

    def call(self, path: str, body: dict[str, Any] | None = None,
             timeout: float | None = None) -> dict[str, Any]:
        request = urllib.request.Request(
            self.upstream + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers=self.request_headers(),
            method="POST" if body is not None else "GET",
        )
        wait = self.timeout if timeout is None else timeout
        with urllib.request.urlopen(request, timeout=wait) as response:  # nosec B310
            reply = json.loads(response.read(5_000_000).decode())
        if not isinstance(reply, dict):
            raise ValueError("upstream reply is not an object")
        return reply

    def upstream_model(self) -> str:
        with self._lock:
            if self.model is None:
                self.model = str(self.call("/models", timeout=min(self.timeout, 15))
                                 ["data"][0]["id"])
            return self.model


def sniff_mime(b64: str) -> str:
    head = b64[:12]
    if head.startswith("/9j/"):
        return "image/jpeg"
    if head.startswith("UklGR"):
        return "image/webp"
    return "image/png"


def _image_parts(images: object) -> list[dict[str, Any]]:
    return [{"type": "image_url", "image_url": {"url": f"data:{sniff_mime(str(i))};base64,{i}"}}
            for i in (images if isinstance(images, list) else [])]


def chat_body(path: str, req: Mapping[str, Any], config: ProxyConfig) -> dict[str, Any]:
    """The upstream ``/chat/completions`` body for an Ollama request. Model filled later."""
    messages: list[dict[str, Any]] = []
    if path == "/api/generate":
        if req.get("system"):
            messages.append({"role": "system", "content": str(req["system"])})
        content = _image_parts(req.get("images"))
        content.append({"type": "text", "text": str(req.get("prompt", ""))})
        messages.append({"role": "user", "content": content})
    else:
        for message in req.get("messages") or []:
            parts = _image_parts(message.get("images"))
            parts.append({"type": "text", "text": str(message.get("content", ""))})
            messages.append({"role": message.get("role", "user"), "content": parts})
    options = req.get("options") or {}
    body = {
        "model": None,
        "messages": messages,
        "temperature": float(options.get("temperature", 0)),
        "max_tokens": int(options.get("num_predict", config.max_tokens)),
    }
    return _merge(body, config.extra_body)


class Handler(BaseHTTPRequestHandler):
    server_version = DEFAULT_USER_AGENT

    @property
    def config(self) -> ProxyConfig:
        return self.server.config  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        sys.stderr.write("%s %s\n" % (time.strftime("%Y-%m-%dT%H:%M:%S%z"), format % args))

    def _send(self, code: int, obj: dict[str, Any]) -> None:
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/version":
            return self._send(200, {"version": VERSION})
        if self.path in ("/api/tags", "/health"):
            try:
                model = self.config.upstream_model()
            except Exception as exc:  # upstream down: report it, do not pretend
                return self._send(502, {"error": f"upstream unreachable: {type(exc).__name__}"})
            return self._send(200, {"models": [{"name": model, "model": model}]})
        return self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in ("/api/generate", "/api/chat"):
            return self._send(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            req = json.loads(self.rfile.read(length).decode())
            if not isinstance(req, dict):
                raise ValueError("body is not an object")
        except Exception:
            return self._send(400, {"error": "bad request body"})
        if req.get("stream"):
            return self._send(400, {"error": "streaming is not supported by this proxy"})
        body = chat_body(self.path, req, self.config)
        started = time.time()
        try:
            body["model"] = self.config.upstream_model()
            reply = self.config.call("/chat/completions", body)
            text = reply["choices"][0]["message"]["content"]
            if not isinstance(text, str):
                raise ValueError("choices[0].message.content is not a string")
        except urllib.error.HTTPError as exc:
            return self._send(502, {"error": f"upstream HTTP {exc.code}"})
        except Exception as exc:  # network, timeout, key, or shape errors: fail closed
            return self._send(502, {"error": f"upstream request failed: {type(exc).__name__}"})
        took = int((time.time() - started) * 1e9)
        model = str(req.get("model") or body["model"])
        if self.path == "/api/generate":
            return self._send(200, {"model": model, "response": text.strip(), "done": True,
                                    "total_duration": took})
        return self._send(200, {"model": model, "done": True, "total_duration": took,
                                "message": {"role": "assistant", "content": text.strip()}})


def make_server(config: ProxyConfig) -> ThreadingHTTPServer:
    """Validate and bind. Raises ``ProxyConfigError`` (fail closed)."""
    config.validate()
    server = ThreadingHTTPServer(config.host_port(), Handler)
    server.config = config  # type: ignore[attr-defined]
    return server


def main() -> int:
    try:
        config = ProxyConfig.from_env()
        server = make_server(config)
    except ProxyConfigError as exc:
        sys.stderr.write(f"kubrick vlm proxy: {exc}\n")
        return 2
    sys.stderr.write(f"kubrick vlm proxy on http://{config.addr} -> {config.upstream}\n")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
