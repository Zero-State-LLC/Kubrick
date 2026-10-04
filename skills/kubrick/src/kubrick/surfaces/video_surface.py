#!/usr/bin/env python3
from kubrick.surfaces.production_surface import run

ACTIONS = {
    "shot",
    "prompt",
    "motion",
    "blocking",
    "sequence",
    "transition",
    "animation",
    "timeline",
    "continuity",
    "adapt",
    "qa",
}

if __name__ == "__main__":
    raise SystemExit(run("video", ACTIONS))
