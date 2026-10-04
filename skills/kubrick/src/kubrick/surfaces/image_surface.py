#!/usr/bin/env python3
from kubrick.surfaces.production_surface import run

ACTIONS = {
    "prompt",
    "generate",
    "improve",
    "sequence",
    "batch",
    "reference",
    "negative",
    "adapt",
    "composition",
    "lighting",
    "camera",
    "symbol-extract",
    "qa",
}

if __name__ == "__main__":
    raise SystemExit(run("image", ACTIONS))
