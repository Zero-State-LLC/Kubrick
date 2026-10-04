#!/usr/bin/env python3
"""Health check and fail-closed test for the board image gate judge.

  python tools/board_vision/health.py check        # ask the configured judge one question
  python tools/board_vision/health.py fail-closed  # no network: a dead upstream must block

``check`` reads ``KUBRICK_BOARD_VLM_URL`` and ``KUBRICK_BOARD_VLM_MODEL`` (source
``board-vision.env`` first), asks one yes-or-no question about a plain red
image, and passes only on ``yes``. ``fail-closed`` starts ``vlm_proxy`` in
process on a free loopback port with a dummy key and an upstream that refuses
connections, then requires that the judge raises ``BackendUnavailable`` (the
gate's UNVERIFIED, which blocks), that a dead loopback URL does the same, and
that a non-loopback judge URL and a non-loopback proxy address are refused.
Exit 0 on pass, 1 on fail.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_SRC = str(ROOT / "src")
if sys.path[:1] != [_SRC]:
    while _SRC in sys.path:
        sys.path.remove(_SRC)
    sys.path.insert(0, _SRC)
if str(ROOT) not in sys.path:
    sys.path.insert(1, str(ROOT))

from kubrick.qc.board_pixels import RGBImage  # noqa: E402
from kubrick.qc.board_vision import BackendUnavailable, LoopbackVlmJudge  # noqa: E402
from tools.board_vision.vlm_proxy import (  # noqa: E402
    ProxyConfig,
    ProxyConfigError,
    make_server,
)

QUESTION = "Answer only yes or no. Is this image mostly red?"


def red_image(size: int = 32) -> RGBImage:
    return RGBImage(size, size, bytes([220, 20, 20]) * (size * size))


def check(url: str | None = None, model: str | None = None) -> dict[str, object]:
    judge = LoopbackVlmJudge(url=url, model=model, timeout=120)
    try:
        answer = judge.ask(red_image(), "", QUESTION)
    except BackendUnavailable as exc:
        return {"ok": False, "judge": judge.name, "url": judge.url, "reason": str(exc)}
    return {"ok": answer == "yes", "judge": judge.name, "url": judge.url, "answer": answer}


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def fail_closed() -> dict[str, object]:
    """Every failure path must raise ``BackendUnavailable``. No network is used."""
    results: dict[str, object] = {}
    dead = _free_port()
    config = ProxyConfig(addr=f"127.0.0.1:{_free_port()}", upstream=f"http://127.0.0.1:{dead}/v1",
                         model="dead-upstream", timeout=5)
    key_var = "KUBRICK_VLM_HEALTH_DUMMY_KEY"
    os.environ[key_var] = "dummy-not-a-real-key"  # nosec B105: test value only
    config.key_env = key_var
    try:
        server = make_server(config)
    finally:
        os.environ.pop(key_var, None)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for name, url in (("proxy_dead_upstream", f"http://{config.addr}"),
                          ("dead_loopback_url", f"http://127.0.0.1:{dead}"),
                          ("remote_url_refused", "http://192.0.2.10:11434")):
            try:
                answer = LoopbackVlmJudge(url=url, model="x", timeout=10).ask(red_image(), "",
                                                                             QUESTION)
                results[name] = f"FAIL: judge answered {answer!r}"
            except BackendUnavailable:
                results[name] = "PASS"
    finally:
        server.shutdown()
        server.server_close()
    refused = {
        "proxy_refuses_public_bind": ProxyConfig(addr="0.0.0.0:11499",  # nosec B104
                                                 upstream="https://vision.invalid/v1"),
        "proxy_refuses_missing_upstream": ProxyConfig(addr="127.0.0.1:11499"),
        "proxy_refuses_plain_http_remote": ProxyConfig(addr="127.0.0.1:11499",
                                                       upstream="http://192.0.2.10/v1"),
        "proxy_refuses_empty_key_source": ProxyConfig(
            addr="127.0.0.1:11499", upstream="https://vision.invalid/v1",
            key_env="KUBRICK_VLM_HEALTH_UNSET_KEY"),
    }
    for name, bad in refused.items():
        try:
            make_server(bad).server_close()
            results[name] = "FAIL: proxy started"
        except ProxyConfigError:
            results[name] = "PASS"
    results["ok"] = all(value == "PASS" for value in results.values())
    return results


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    mode = args[0] if args else "check"
    if mode == "check":
        result = check()
    elif mode == "fail-closed":
        result = fail_closed()
    else:
        print("usage: health.py check|fail-closed", file=sys.stderr)
        return 2
    for key, value in result.items():
        print(f"{key}: {value}")
    print("PASS" if result["ok"] else "FAIL")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
