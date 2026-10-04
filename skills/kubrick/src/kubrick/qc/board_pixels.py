#!/usr/bin/env python3
"""Board image pixels for the pre-spend image gate. Standard library only.

8-bit PNG files decode without any extra package. Other formats (JPEG, WebP)
need Pillow, which is part of the optional ``board-vision`` extra. Pillow is
imported only when a file needs it, never at module load.

The character crop is simple and local: an explicit normalized box from the
plan when one is set, otherwise the bounding box of pixels that differ from
the border color. A crop that finds almost nothing, or almost everything,
falls back to the full frame and says so.
"""
from __future__ import annotations

import hashlib
import importlib
import struct
import zlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
_MAX_PIXELS = 40_000_000
_SAMPLE_TARGET = 200_000
FOREGROUND_TOLERANCE = 40
_PAD_FRACTION = 0.04
_MIN_AREA = 0.005
_MAX_AREA = 0.95


class ImageUnreadable(ValueError):
    """The file is missing, not an image, or a format this build cannot decode."""


@dataclass(frozen=True)
class RGBImage:
    """Row-major 8-bit RGB pixels."""

    width: int
    height: int
    pixels: bytes

    def pixel(self, x: int, y: int) -> tuple[int, int, int]:
        offset = (y * self.width + x) * 3
        data = self.pixels
        return data[offset], data[offset + 1], data[offset + 2]


@dataclass(frozen=True)
class Crop:
    """The isolated character region and how it was chosen."""

    image: RGBImage
    box: tuple[int, int, int, int]
    method: str


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(1 << 16), b""):
                digest.update(block)
    except OSError as exc:
        raise ImageUnreadable(f"cannot read {path}: {exc}") from exc
    return digest.hexdigest()


def load_rgb(path: str | Path) -> RGBImage:
    """Decode an image file to RGB. PNG needs nothing; other formats need Pillow."""
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        raise ImageUnreadable(f"cannot read {path}: {exc}") from exc
    if data.startswith(_PNG_SIGNATURE):
        try:
            return decode_png(data)
        except ImageUnreadable:
            pillow = _pillow_load(path)
            if pillow is not None:
                return pillow
            raise
    pillow = _pillow_load(path)
    if pillow is None:
        raise ImageUnreadable(
            f"{path} is not an 8-bit PNG and Pillow is not installed; "
            "install the board-vision extra or convert the board to PNG"
        )
    return pillow


def _pillow_load(path: str | Path) -> RGBImage | None:
    try:
        module = importlib.import_module("PIL.Image")
    except ImportError:
        return None
    try:
        with module.open(path) as handle:
            converted = handle.convert("RGB")
            width, height = converted.size
            return RGBImage(int(width), int(height), converted.tobytes())
    except Exception as exc:  # Pillow raises several unrelated types.
        raise ImageUnreadable(f"cannot decode {path}: {exc}") from exc


def decode_png(data: bytes) -> RGBImage:
    """Decode a non-interlaced 8-bit PNG (gray, RGB, palette, gray-alpha, RGBA)."""
    if not data.startswith(_PNG_SIGNATURE):
        raise ImageUnreadable("not a PNG file")
    offset = len(_PNG_SIGNATURE)
    header: tuple[int, ...] | None = None
    palette = b""
    idat = bytearray()
    while offset + 8 <= len(data):
        (length,) = struct.unpack(">I", data[offset:offset + 4])
        kind = data[offset + 4:offset + 8]
        body = data[offset + 8:offset + 8 + length]
        if len(body) != length:
            raise ImageUnreadable("PNG chunk is truncated")
        offset += 12 + length
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            palette = body
        elif kind == b"IDAT":
            idat.extend(body)
        elif kind == b"IEND":
            break
    if header is None:
        raise ImageUnreadable("PNG has no IHDR chunk")
    width, height, depth, color, _compression, _filter, interlace = header
    if depth != 8 or interlace != 0 or color not in _CHANNELS:
        raise ImageUnreadable(
            f"PNG bit depth {depth}, color type {color}, interlace {interlace} is not supported"
        )
    if width <= 0 or height <= 0 or width * height > _MAX_PIXELS:
        raise ImageUnreadable("PNG dimensions are out of range")
    if color == 3 and not palette:
        raise ImageUnreadable("palette PNG has no PLTE chunk")
    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error as exc:
        raise ImageUnreadable(f"PNG data is corrupt: {exc}") from exc
    channels = _CHANNELS[color]
    stride = width * channels
    if len(raw) < height * (stride + 1):
        raise ImageUnreadable("PNG data is truncated")
    rows = _unfilter(raw, width, height, channels)
    return RGBImage(width, height, _to_rgb(rows, color, palette))


def _unfilter(raw: bytes, width: int, height: int, bpp: int) -> bytes:
    stride = width * bpp
    out = bytearray(height * stride)
    previous = bytearray(stride)
    position = 0
    for row in range(height):
        kind = raw[position]
        line = bytearray(raw[position + 1:position + 1 + stride])
        position += stride + 1
        if kind == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif kind == 2:
            for i in range(stride):
                line[i] = (line[i] + previous[i]) & 0xFF
        elif kind == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + previous[i]) >> 1)) & 0xFF
        elif kind == 4:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                corner = previous[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + _paeth(left, previous[i], corner)) & 0xFF
        elif kind != 0:
            raise ImageUnreadable(f"PNG filter type {kind} is not valid")
        out[row * stride:(row + 1) * stride] = line
        previous = line
    return bytes(out)


def _paeth(left: int, up: int, corner: int) -> int:
    estimate = left + up - corner
    to_left, to_up, to_corner = abs(estimate - left), abs(estimate - up), abs(estimate - corner)
    if to_left <= to_up and to_left <= to_corner:
        return left
    if to_up <= to_corner:
        return up
    return corner


def _to_rgb(rows: bytes, color: int, palette: bytes) -> bytes:
    if color == 2:
        return rows
    if color == 6:
        out = bytearray(len(rows) // 4 * 3)
        out[0::3] = rows[0::4]
        out[1::3] = rows[1::4]
        out[2::3] = rows[2::4]
        return bytes(out)
    if color == 0:
        out = bytearray(len(rows) * 3)
        out[0::3] = rows
        out[1::3] = rows
        out[2::3] = rows
        return bytes(out)
    if color == 4:
        gray = rows[0::2]
        out = bytearray(len(gray) * 3)
        out[0::3] = gray
        out[1::3] = gray
        out[2::3] = gray
        return bytes(out)
    out = bytearray()
    for index in rows:
        start = index * 3
        if start + 3 > len(palette):
            raise ImageUnreadable("PNG palette index is out of range")
        out.extend(palette[start:start + 3])
    return bytes(out)


def encode_png(image: RGBImage) -> bytes:
    """Encode RGB pixels as a PNG. Used for fixtures and the local judge payload."""
    stride = image.width * 3
    raw = bytearray()
    for row in range(image.height):
        raw.append(0)
        raw.extend(image.pixels[row * stride:(row + 1) * stride])

    def chunk(kind: bytes, body: bytes) -> bytes:
        crc = zlib.crc32(kind + body) & 0xFFFFFFFF
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)

    header = struct.pack(">IIBBBBB", image.width, image.height, 8, 2, 0, 0, 0)
    return b"".join([
        _PNG_SIGNATURE,
        chunk(b"IHDR", header),
        chunk(b"IDAT", zlib.compress(bytes(raw), 9)),
        chunk(b"IEND", b""),
    ])


def crop(image: RGBImage, box: tuple[int, int, int, int]) -> RGBImage:
    left, top, right, bottom = box
    width = right - left
    rows = [
        image.pixels[(y * image.width + left) * 3:(y * image.width + right) * 3]
        for y in range(top, bottom)
    ]
    return RGBImage(width, bottom - top, b"".join(rows))


def normalized_box(
    image: RGBImage, raw: Sequence[object],
) -> tuple[int, int, int, int] | None:
    """``[x0, y0, x1, y1]`` in 0..1 to pixel bounds. Invalid boxes return None."""
    if isinstance(raw, (str, bytes)) or len(raw) != 4:
        return None
    values: list[float] = []
    for item in raw:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return None
        values.append(float(item))
    x0, y0, x1, y1 = values
    if not (0.0 <= x0 < x1 <= 1.0 and 0.0 <= y0 < y1 <= 1.0):
        return None
    box = (
        int(x0 * image.width),
        int(y0 * image.height),
        max(int(x0 * image.width) + 1, round(x1 * image.width)),
        max(int(y0 * image.height) + 1, round(y1 * image.height)),
    )
    return box


def isolate_subject(
    image: RGBImage,
    box: Sequence[object] | None = None,
    tolerance: int = FOREGROUND_TOLERANCE,
) -> Crop:
    """Crop to the character. An explicit box wins over the border-color estimate."""
    if box is not None:
        explicit = normalized_box(image, box)
        if explicit is not None:
            return Crop(crop(image, explicit), explicit, "plan_box")
    found = foreground_box(image, tolerance)
    if found is None:
        full = (0, 0, image.width, image.height)
        return Crop(image, full, "full_frame")
    return Crop(crop(image, found), found, "border_contrast")


def _border_color(image: RGBImage) -> tuple[int, int, int]:
    samples: list[tuple[int, int, int]] = []
    step_x = max(1, image.width // 32)
    step_y = max(1, image.height // 32)
    for x in range(0, image.width, step_x):
        samples.append(image.pixel(x, 0))
        samples.append(image.pixel(x, image.height - 1))
    for y in range(0, image.height, step_y):
        samples.append(image.pixel(0, y))
        samples.append(image.pixel(image.width - 1, y))
    channels = list(zip(*samples))
    return (
        sorted(channels[0])[len(samples) // 2],
        sorted(channels[1])[len(samples) // 2],
        sorted(channels[2])[len(samples) // 2],
    )


def foreground_box(
    image: RGBImage, tolerance: int = FOREGROUND_TOLERANCE,
) -> tuple[int, int, int, int] | None:
    """Bounding box of pixels unlike the border color, padded. None when unusable."""
    background = _border_color(image)
    total = image.width * image.height
    step = 1
    while (total // (step * step)) > _SAMPLE_TARGET:
        step += 1
    left, top, right, bottom = image.width, image.height, -1, -1
    hits = 0
    samples = 0
    for y in range(0, image.height, step):
        for x in range(0, image.width, step):
            samples += 1
            red, green, blue = image.pixel(x, y)
            if max(
                abs(red - background[0]), abs(green - background[1]), abs(blue - background[2]),
            ) <= tolerance:
                continue
            hits += 1
            left, right = min(left, x), max(right, x)
            top, bottom = min(top, y), max(bottom, y)
    if hits == 0 or samples == 0:
        return None
    share = hits / samples
    if share < _MIN_AREA or share > _MAX_AREA:
        return None
    pad_x = max(1, int(image.width * _PAD_FRACTION))
    pad_y = max(1, int(image.height * _PAD_FRACTION))
    return (
        max(0, left - pad_x),
        max(0, top - pad_y),
        min(image.width, right + step + pad_x),
        min(image.height, bottom + step + pad_y),
    )
