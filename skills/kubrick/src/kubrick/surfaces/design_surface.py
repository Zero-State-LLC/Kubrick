#!/usr/bin/env python3
from kubrick.surfaces.production_surface import run

ACTIONS = {
    "build",
    "create",
    "improve",
    "audit",
    "reconcile",
    "drift",
    "update",
    "validate",
    "expand",
    "summarize",
    "qa",
}

if __name__ == "__main__":
    raise SystemExit(run("design", ACTIONS))
