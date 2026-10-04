#!/usr/bin/env python3
from kubrick.surfaces.production_surface import run

ACTIONS = {
    "create",
    "improve",
    "rewrite",
    "expand",
    "compress",
    "diagnose",
    "adapt",
    "continuity",
    "continuity-check",
    "handoff",
    "scene-extract",
    "beat-validate",
    "character-consistency",
    "dialog-validate",
    "genre-validate",
    "qa",
}

if __name__ == "__main__":
    raise SystemExit(run("script", ACTIONS))
