"""Loopback fake servers for the board vision tool tests. No network, no model."""
from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

Reply = Callable[[str, dict[str, Any]], tuple[int, Any]]


@contextmanager
def serve(reply: Reply) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    """Run a loopback JSON server. Yields its base URL and the requests it saw."""
    seen: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            return

        def _answer(self, body: dict[str, Any]) -> None:
            seen.append({"path": self.path, "headers": dict(self.headers), "body": body})
            code, obj = reply(self.path, body)
            data = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802
            self._answer({})

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            self._answer(json.loads(self.rfile.read(length).decode() or "{}"))

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", seen
    finally:
        server.shutdown()
        server.server_close()


def openai_upstream(answer: str = "yes", model: str = "fake-vision") -> Reply:
    def reply(path: str, body: dict[str, Any]) -> tuple[int, Any]:
        if path.endswith("/models"):
            return 200, {"data": [{"id": model}]}
        if path.endswith("/chat/completions"):
            return 200, {"choices": [{"message": {"content": answer}}]}
        return 404, {"error": "not found"}

    return reply


def ollama_judge(answer_for: Callable[[str], str]) -> Reply:
    def reply(path: str, body: dict[str, Any]) -> tuple[int, Any]:
        if path == "/api/generate":
            return 200, {"response": answer_for(str(body.get("prompt", ""))), "done": True}
        return 404, {"error": "not found"}

    return reply
