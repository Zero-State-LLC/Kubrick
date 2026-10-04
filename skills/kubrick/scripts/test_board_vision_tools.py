#!/usr/bin/env python3
"""tools/board_vision: the provider-agnostic loopback adapter, setup, and fail-closed test.

Fake loopback servers stand in for the upstream. No network and no model.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools" / "board_vision"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import board_pixels as pixels  # noqa: E402
import board_vision as vision  # noqa: E402
from fake_vision_servers import openai_upstream, serve  # noqa: E402

from tools.board_vision import health  # noqa: E402
from tools.board_vision.vlm_proxy import (  # noqa: E402
    ProxyConfig,
    ProxyConfigError,
    chat_body,
    make_server,
)


@contextmanager
def proxy(config: ProxyConfig) -> Iterator[str]:
    server = make_server(config)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def _ask(url: str) -> str:
    image = pixels.RGBImage(2, 2, bytes([200, 0, 0]) * 4)
    return vision.LoopbackVlmJudge(url=url, model="label", timeout=10).ask(image, "", "red?")


def _get(url: str) -> tuple[int, dict[str, Any]]:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:  # nosec B310
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_profile_settings_reach_the_upstream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_VISION_KEY", "test-key-value")
    with serve(openai_upstream("Yes.")) as (upstream, seen):
        config = ProxyConfig.from_env({
            "KUBRICK_VLM_PROXY_ADDR": "127.0.0.1:0",
            "KUBRICK_VLM_UPSTREAM_URL": upstream + "/v1",
            "KUBRICK_VLM_API_KEY_ENV": "FAKE_VISION_KEY",
            "KUBRICK_VLM_EXTRA_HEADERS": '{"User-Agent": "custom-agent/2"}',
            "KUBRICK_VLM_EXTRA_BODY": '{"chat_template_kwargs": {"enable_thinking": false}}',
        })
        with proxy(config) as url:
            assert _ask(url) == "yes"
            assert _get(url + "/api/tags") == (200, {"models": [{"name": "fake-vision",
                                                                  "model": "fake-vision"}]})
    chat = [r for r in seen if r["path"] == "/v1/chat/completions"][0]
    assert chat["headers"]["User-Agent"] == "custom-agent/2"
    assert chat["headers"]["Authorization"] == "Bearer test-key-value"
    assert chat["body"]["model"] == "fake-vision"
    assert chat["body"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert chat["body"]["temperature"] == 0 and chat["body"]["max_tokens"] == 64
    image = chat["body"]["messages"][0]["content"][0]["image_url"]["url"]
    assert image.startswith("data:image/png;base64,")


def test_no_key_source_sends_no_authorization() -> None:
    with serve(openai_upstream("no")) as (upstream, seen):
        config = ProxyConfig(addr="127.0.0.1:0", upstream=upstream + "/v1", model="m")
        with proxy(config) as url:
            assert _ask(url) == "no"
            assert _get(url + "/api/version")[0] == 200
    assert all("Authorization" not in r["headers"] for r in seen)
    assert [r["path"] for r in seen] == ["/v1/chat/completions"]


@pytest.mark.parametrize("reply", [
    lambda path, body: (500, {"error": "boom"}),
    lambda path, body: (200, {"choices": []}),
    lambda path, body: (200, {"choices": [{"message": {"reasoning_content": "yes"}}]}),
])
def test_upstream_failures_fail_closed(reply: Any) -> None:
    with serve(reply) as (upstream, _seen):
        with proxy(ProxyConfig(addr="127.0.0.1:0", upstream=upstream + "/v1",
                               model="m")) as url:
            with pytest.raises(vision.BackendUnavailable):
                _ask(url)
            assert _get(url + "/api/tags")[0] in (200, 502)


@pytest.mark.parametrize("env, message", [
    ({}, "UPSTREAM_URL is not set"),
    ({"KUBRICK_VLM_UPSTREAM_URL": "http://192.0.2.1/v1"}, "must use https"),
    ({"KUBRICK_VLM_UPSTREAM_URL": "ftp://example.invalid/v1"}, "http(s) URL"),
    ({"KUBRICK_VLM_UPSTREAM_URL": "https://example.invalid/v1",
      "KUBRICK_VLM_PROXY_ADDR": "0.0.0.0:11435"}, "non-loopback"),
    ({"KUBRICK_VLM_UPSTREAM_URL": "https://example.invalid/v1",
      "KUBRICK_VLM_API_KEY_ENV": "KUBRICK_TEST_UNSET_KEY_VAR"}, "key source is empty"),
    ({"KUBRICK_VLM_UPSTREAM_URL": "https://example.invalid/v1",
      "KUBRICK_VLM_API_KEY_FILE": "/nonexistent/kubrick/key"}, "key source is empty"),
])
def test_bad_configuration_refuses_to_start(env: dict[str, str], message: str) -> None:
    with pytest.raises(ProxyConfigError, match=message.replace("(", r"\(").replace(")", r"\)")):
        make_server(ProxyConfig.from_env(env))


def test_bad_json_settings_refuse_to_start() -> None:
    with pytest.raises(ProxyConfigError, match="not valid JSON"):
        ProxyConfig.from_env({"KUBRICK_VLM_EXTRA_BODY": "{nope"})
    with pytest.raises(ProxyConfigError, match="JSON object"):
        ProxyConfig.from_env({"KUBRICK_VLM_EXTRA_HEADERS": "[1]"})


def test_key_file_is_read(tmp_path: Path) -> None:
    key = tmp_path / "key"
    key.write_text("from-file\n", encoding="utf-8")
    config = ProxyConfig(upstream="https://example.invalid/v1", key_file=str(key))
    assert config.request_headers()["Authorization"] == "Bearer from-file"


def test_chat_body_merges_extra_fields_and_chat_messages() -> None:
    config = ProxyConfig(extra_body={"top_p": 0.5, "chat_template_kwargs": {"a": 1}})
    body = chat_body("/api/chat", {"messages": [{"role": "user", "content": "hi",
                                                 "images": ["/9j/abc"]}]}, config)
    assert body["top_p"] == 0.5 and body["chat_template_kwargs"] == {"a": 1}
    parts = body["messages"][0]["content"]
    assert parts[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert parts[1] == {"type": "text", "text": "hi"}


def test_fail_closed_self_test_passes() -> None:
    result = health.fail_closed()
    assert result["ok"] is True, result


def test_health_check_needs_a_yes() -> None:
    with serve(openai_upstream("no")) as (upstream, _seen):
        with proxy(ProxyConfig(addr="127.0.0.1:0", upstream=upstream + "/v1",
                               model="m")) as url:
            assert health.check(url=url)["ok"] is False
    assert health.check(url="")["ok"] is False


def test_no_provider_is_hardcoded_in_code() -> None:
    names = ("vlm_proxy.py", "kubrick-vlm-proxy", "kubrick-vlm", "setup.sh", "health.py",
             "board-vision.env.example")
    code = [TOOLS / name for name in names]
    for path in code:
        text = path.read_text(encoding="utf-8").casefold()
        for word in ("zer0state", "spark", "qwen", "sglang"):
            assert word not in text, (path.name, word)


def test_example_profiles_parse_and_hold_no_secret() -> None:
    profiles = sorted((TOOLS / "profiles").glob("*.env.example"))
    assert {p.name for p in profiles} >= {"openai-compatible.env.example",
                                          "spark.env.example"}
    for path in profiles:
        done = subprocess.run(
            ["bash", "-c", 'set -a; . "$1"; env', "_", str(path)], capture_output=True,
            text=True, check=True, env={"HOME": "/home/example", "PATH": os.environ["PATH"]})
        env = dict(line.split("=", 1) for line in done.stdout.splitlines() if "=" in line)
        config = ProxyConfig.from_env(env)
        if "KUBRICK_VLM_UPSTREAM_URL" not in env:
            assert env.get("KUBRICK_OLLAMA_MODEL"), path.name
            continue
        assert config.upstream.startswith(("https://", "http://127.0.0.1"))
        assert "Authorization" not in config.headers
        assert not any(v.startswith(("sk-", "Bearer")) for v in env.values())


def test_setup_and_launchers_are_valid_bash() -> None:
    for name in ("setup.sh", "kubrick-vlm", "kubrick-vlm-proxy"):
        subprocess.run(["bash", "-n", str(TOOLS / name)], check=True)
    bad = subprocess.run(["bash", str(TOOLS / "setup.sh"), "nope"], capture_output=True,
                         text=True, check=False)
    assert bad.returncode == 2
    missing = subprocess.run(["bash", str(TOOLS / "setup.sh"), "proxy"], capture_output=True,
                             text=True, check=False)
    assert missing.returncode == 2 and "--profile" in missing.stderr


def test_setup_persists_the_selected_judge(tmp_path: Path) -> None:
    """setup.sh proxy writes the profile's address into board-vision.env and passes."""
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    conf, state = tmp_path / "conf", tmp_path / "state"
    with serve(openai_upstream("yes")) as (upstream, _seen):
        profile = tmp_path / "fake.env"
        profile.write_text(f"KUBRICK_VLM_PROXY_ADDR=127.0.0.1:{port}\n"
                           f"KUBRICK_VLM_UPSTREAM_URL={upstream}/v1\n"
                           "KUBRICK_VLM_UPSTREAM_MODEL=m\n", encoding="utf-8")
        env = dict(os.environ, HOME=str(tmp_path), KUBRICK_CONFIG_DIR=str(conf),
                   KUBRICK_BIN=str(tmp_path / "bin"), KUBRICK_VLM_STATE=str(state),
                   KUBRICK_PYTHON=sys.executable, KUBRICK_SETUP_SKIP_PIP="1",
                   KUBRICK_SETUP_SKIP_DOWNLOAD="1")
        try:
            done = subprocess.run(["bash", str(TOOLS / "setup.sh"), "proxy", "--profile",
                                   str(profile)], env=env, capture_output=True, text=True,
                                  timeout=120, check=False)
        finally:
            subprocess.run([str(tmp_path / "bin" / "kubrick-vlm-fake"), "stop"], env=env,
                           capture_output=True, timeout=30, check=False)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "board vision setup: PASS" in done.stdout
    settings = (conf / "board-vision.env").read_text(encoding="utf-8")
    assert f"export KUBRICK_BOARD_VLM_URL=http://127.0.0.1:{port}" in settings
    assert list(conf.glob("board-vision.env.bak-*"))
    assert (conf / "vlm-fake.env").read_text(encoding="utf-8") == profile.read_text(
        encoding="utf-8")
