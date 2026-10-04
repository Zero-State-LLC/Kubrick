#!/usr/bin/env python3
"""Board image pixels and local vision backends. Fixture PNGs only, no model.

The only HTTP call is to a throwaway server on 127.0.0.1 that stands in for a
local vision-language model. No paid API is called.
"""
from __future__ import annotations

import json
import struct
import sys
import threading
import zlib
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "evals" / "fixtures" / "board_images"
sys.path.insert(0, str(SCRIPTS))

import board_pixels as pixels  # noqa: E402
import board_vision as vision  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("KUBRICK_BOARD_JUDGE_ANSWERS", "KUBRICK_BOARD_VLM_URL", "KUBRICK_BOARD_VLM_MODEL"):
        monkeypatch.delenv(key, raising=False)


# --------------------------------------------------------------- pixels ---

def _png(width: int, height: int, color: int, rows: list[bytes], filters: list[int],
         bpp: int, palette: bytes = b"", depth: int = 8) -> bytes:
    raw = bytearray()
    previous = bytes(len(rows[0]))
    for kind, row in zip(filters, rows):
        raw.append(kind)
        out = bytearray()
        for i, value in enumerate(row):
            left = row[i - bpp] if i >= bpp else 0
            up = previous[i]
            corner = previous[i - bpp] if i >= bpp else 0
            predictor = {
                0: 0,
                1: left,
                2: up,
                3: (left + up) >> 1,
                4: pixels._paeth(left, up, corner),
            }[kind]
            out.append((value - predictor) & 0xFF)
        raw.extend(out)
        previous = row

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + kind + body
                + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))

    parts = [b"\x89PNG\r\n\x1a\n",
             chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, depth, color, 0, 0, 0))]
    if palette:
        parts.append(chunk(b"PLTE", palette))
    parts.append(chunk(b"IDAT", zlib.compress(bytes(raw))))
    parts.append(chunk(b"IEND", b""))
    return b"".join(parts)


def test_png_decoder_reverses_every_filter_and_color_type() -> None:
    rgb_rows = [bytes((x * 40 + y * 7) % 256 for x in range(12)) for y in range(5)]
    decoded = pixels.decode_png(_png(4, 5, 2, rgb_rows, [0, 1, 2, 3, 4], 3))
    assert decoded.pixels == b"".join(rgb_rows)
    rgba_rows = [bytes((x * 13 + y) % 256 for x in range(8)) for y in range(2)]
    rgba = pixels.decode_png(_png(2, 2, 6, rgba_rows, [4, 1], 4))
    assert rgba.pixel(1, 1) == (rgba_rows[1][4], rgba_rows[1][5], rgba_rows[1][6])
    gray = pixels.decode_png(_png(3, 1, 0, [bytes([0, 128, 255])], [3], 1))
    assert gray.pixel(1, 0) == (128, 128, 128)
    gray_alpha = pixels.decode_png(_png(2, 1, 4, [bytes([10, 255, 20, 255])], [0], 2))
    assert gray_alpha.pixel(1, 0) == (20, 20, 20)
    palette = bytes([255, 0, 0, 0, 0, 255])
    indexed = pixels.decode_png(_png(2, 1, 3, [bytes([1, 0])], [0], 1, palette))
    assert indexed.pixel(0, 0) == (0, 0, 255)
    assert indexed.pixel(1, 0) == (255, 0, 0)


def test_png_decoder_refuses_what_it_cannot_read(tmp_path: Path) -> None:
    with pytest.raises(pixels.ImageUnreadable):
        pixels.decode_png(b"not a png")
    with pytest.raises(pixels.ImageUnreadable, match="bit depth 16"):
        pixels.decode_png(_png(1, 1, 2, [bytes(6)], [0], 6, depth=16))
    with pytest.raises(pixels.ImageUnreadable, match="filter type"):
        pixels.decode_png(_png(1, 1, 0, [bytes([1])], [0], 1).replace(
            zlib.compress(bytes([0, 1])), zlib.compress(bytes([9, 1]))))
    with pytest.raises(pixels.ImageUnreadable, match="PLTE"):
        pixels.decode_png(_png(1, 1, 3, [bytes([0])], [0], 1))
    with pytest.raises(pixels.ImageUnreadable, match="out of range"):
        pixels.decode_png(_png(1, 1, 3, [bytes([5])], [0], 1, bytes(3)))
    jpeg = tmp_path / "board.jpg"
    jpeg.write_bytes(b"\xff\xd8\xff\xe0 not really a jpeg")
    with pytest.raises(pixels.ImageUnreadable):
        pixels.load_rgb(jpeg)
    with pytest.raises(pixels.ImageUnreadable):
        pixels.load_rgb(tmp_path / "missing.png")
    with pytest.raises(pixels.ImageUnreadable):
        pixels.file_sha256(tmp_path / "missing.png")


def test_png_round_trip_matches_the_fixture_bytes() -> None:
    image = pixels.load_rgb(FIXTURES / "myslef-front.png")
    assert (image.width, image.height) == (24, 32)
    again = pixels.decode_png(pixels.encode_png(image))
    assert again == image


def test_subject_isolation_prefers_a_plan_box_then_border_contrast() -> None:
    image = pixels.load_rgb(FIXTURES / "board-match.png")
    auto = pixels.isolate_subject(image)
    assert auto.method == "border_contrast"
    left, top, right, bottom = auto.box
    assert 0 <= left < 6 and top <= 4 and right >= 18 and bottom >= 26
    boxed = pixels.isolate_subject(image, [0.25, 0.0, 0.75, 0.5])
    assert boxed.method == "plan_box"
    assert (boxed.image.width, boxed.image.height) == (12, 16)
    bad_box = pixels.isolate_subject(image, [0.9, 0.0, 0.1, 1.0])
    assert bad_box.method == "border_contrast"
    flat = pixels.RGBImage(8, 8, bytes([50, 60, 70]) * 64)
    assert pixels.isolate_subject(flat).method == "full_frame"
    assert pixels.normalized_box(flat, ["a", 0, 1, 1]) is None
    assert pixels.normalized_box(flat, [0, 0, 1]) is None


# --------------------------------------------------------------- vision ---

def test_cosine_and_answer_parsing() -> None:
    assert vision.cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert vision.cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    with pytest.raises(ValueError):
        vision.cosine([1.0], [1.0, 2.0])
    with pytest.raises(ValueError):
        vision.cosine([0.0, 0.0], [1.0, 1.0])
    assert vision.parse_answer("Yes.") == "yes"
    assert vision.parse_answer("  no, the hands have nails") == "no"
    assert vision.parse_answer("**yes**") == "yes"
    assert vision.parse_answer("maybe") == "unknown"
    assert vision.parse_answer("") == "unknown"
    assert vision.parse_answer(None) == "unknown"


def test_dinov2_reports_unverified_without_its_packages(monkeypatch: pytest.MonkeyPatch) -> None:
    real = vision.importlib.import_module

    def blocked(name: str, package: str | None = None) -> object:
        if name in {"torch", "transformers", "PIL.Image"}:
            raise ImportError(f"No module named {name!r}", name=name)
        return real(name, package)

    monkeypatch.setattr(vision.importlib, "import_module", blocked)
    embedder = vision.resolve_embedder()
    assert embedder.name == f"dinov2:{vision.DEFAULT_EMBED_MODEL}"
    with pytest.raises(vision.BackendUnavailable, match="board-vision extra"):
        embedder.embed(pixels.RGBImage(1, 1, b"\x00\x00\x00"))


def test_local_judge_is_loopback_only() -> None:
    image = pixels.RGBImage(1, 1, b"\x00\x00\x00")
    with pytest.raises(vision.BackendUnavailable, match="KUBRICK_BOARD_VLM_URL"):
        vision.LoopbackVlmJudge(url="").ask(image, "sha", "q")
    for remote in ("https://api.example.com", "http://10.0.0.5:11434", "ftp://127.0.0.1"):
        with pytest.raises(vision.BackendUnavailable, match="loopback"):
            vision.LoopbackVlmJudge(url=remote).ask(image, "sha", "q")
    assert isinstance(vision.resolve_judge(), vision.LoopbackVlmJudge)


@contextmanager
def _local_vlm(reply: object, status: int = 200) -> Iterator[tuple[str, list[dict[str, object]]]]:
    seen: list[dict[str, object]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            seen.append(json.loads(self.rfile.read(length)))
            body = reply if isinstance(reply, bytes) else json.dumps(reply).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", seen
    finally:
        server.shutdown()
        server.server_close()


def test_local_judge_asks_a_loopback_model() -> None:
    image = pixels.load_rgb(FIXTURES / "board-match.png")
    with _local_vlm({"response": "Yes"}) as (url, seen):
        judge = vision.LoopbackVlmJudge(url=url, model="tiny-vlm", timeout=5)
        assert judge.ask(image, "sha", "Are the hands silicon?") == "yes"
    assert seen[0]["model"] == "tiny-vlm"
    assert seen[0]["prompt"] == "Are the hands silicon?"
    images = seen[0]["images"]
    assert isinstance(images, list) and len(images) == 1
    with _local_vlm(b"not json") as (url, _seen):
        with pytest.raises(vision.BackendUnavailable, match="not JSON"):
            vision.LoopbackVlmJudge(url=url, timeout=5).ask(image, "sha", "q")
    with _local_vlm(["list"]) as (url, _seen):
        with pytest.raises(vision.BackendUnavailable, match="not an object"):
            vision.LoopbackVlmJudge(url=url, timeout=5).ask(image, "sha", "q")
    with _local_vlm({"error": "down"}, status=500) as (url, _seen):
        with pytest.raises(vision.BackendUnavailable, match="request failed"):
            vision.LoopbackVlmJudge(url=url, timeout=5).ask(image, "sha", "q")


def test_recorded_judge_replays_and_fails_closed(tmp_path: Path) -> None:
    judge = vision.resolve_judge(str(FIXTURES / "judge-answers.json"))
    assert isinstance(judge, vision.RecordedJudge)
    image = pixels.RGBImage(1, 1, b"\x00\x00\x00")
    with pytest.raises(vision.BackendUnavailable, match="no recorded answer"):
        judge.ask(image, "unknown-sha", "q")
    broken = tmp_path / "answers.json"
    broken.write_text("{}", encoding="utf-8")
    with pytest.raises(vision.BackendUnavailable, match="answers"):
        vision.RecordedJudge.from_file(str(broken))
    with pytest.raises(vision.BackendUnavailable, match="cannot load"):
        vision.RecordedJudge.from_file(str(tmp_path / "missing.json"))


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
