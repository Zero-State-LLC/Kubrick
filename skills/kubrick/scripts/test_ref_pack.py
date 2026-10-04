#!/usr/bin/env python3
"""Reference packs. Paths and hashes only. No image generation and no spend."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from ref_pack import (  # noqa: E402
    resolve,
    resolve_shot,
    shared_pack,
    shot_mode,
)
from shot_plan import collect_prep  # noqa: E402

PACK = {
    "asset_hash": "pack-myslef",
    "views": [{"path": "front.png", "ref_role": "identity", "asset_hash": "view-1"}],
    "head_lock": {"path": "head.png", "ref_role": "identity", "asset_hash": "head-1"},
    "material_inserts": [
        {"path": "hands.png", "ref_role": "material", "asset_hash": "hands-1"},
    ],
    "refs": [
        {"path": "coat.png", "ref_role": "costume_prop", "asset_hash": "coat-1"},
        {"path": "aisle.png", "ref_role": "location", "asset_hash": "room-1"},
        {"path": "plate.png", "ref_role": "layout", "asset_hash": "layout-1"},
    ],
}


def _doc() -> dict[str, object]:
    return {"characters": {"myslef": {"ref_pack": PACK}}}


def _codes(report: dict[str, object]) -> list[str]:
    warnings = report["warnings"]
    assert isinstance(warnings, list)
    return [str(item["code"]) for item in warnings if isinstance(item, dict)]


def test_modes_and_seedance_exclusive_inputs() -> None:
    document = _doc()
    refs_only = {"frame_id": "refs", "characters": ["myslef"]}
    assert shot_mode(refs_only, document) == "refs_only"
    resolved = resolve_shot(document, refs_only)
    assert resolved["status"] == "PROPOSED"
    assert resolved["references"] == [
        "front.png", "head.png", "hands.png", "coat.png", "aisle.png", "plate.png",
    ]
    assert resolved["roles"] == [
        "identity", "identity", "material", "costume_prop", "location", "layout",
    ]
    chained = {
        "frame_id": "chain",
        "characters": ["myslef"],
        "join": {"chain_from": "refs"},
        "start_frame": {"asset": "board.png"},
    }
    assert shot_mode(chained, document) == "start_frame"
    dropped = resolve_shot(document, chained)
    assert dropped["references"] == []
    assert "REFS_DROPPED_BY_CHAIN" in _codes(dropped)
    gone = dropped["dropped"]
    assert isinstance(gone, list) and gone and all(
        isinstance(item, dict) and item["code"] == "REFS_DROPPED_BY_CHAIN" for item in gone
    )
    assert "startImage" not in dropped or dropped.get("references") == []
    anchored = {
        "frame_id": "ends",
        "characters": ["myslef"],
        "input_mode": "first_last",
        "start_frame": {"asset": "board.png"},
        "end_framing": {"head_ratio": [0.40, 0.45]},
    }
    assert shot_mode(anchored, document) == "first_last"
    last = resolve_shot(document, anchored)
    end = last["end_image"]
    assert isinstance(end, dict) and end["supported"] is False
    assert "startImage" in str(end["reason"]) and "no end-image" in str(end["reason"])
    assert last["references"] == []


def test_layout_refs_drop_on_a_new_angle() -> None:
    frame = {"frame_id": "angle", "characters": ["myslef"], "cut": "thirty-degree"}
    report = resolve_shot(_doc(), frame, previous={"camera": {"size": "ws"}})
    assert report["mode"] == "refs_only"
    assert "plate.png" not in report["references"]
    assert "front.png" in report["references"]
    assert "LAYOUT_REF_ON_NEW_ANGLE" in _codes(report)
    same = resolve_shot(_doc(), {"frame_id": "hold", "characters": ["myslef"], "cut": "hard-cut"})
    assert "plate.png" in same["references"]
    assert "LAYOUT_REF_ON_NEW_ANGLE" not in _codes(same)


def test_one_pack_is_shared_and_a_split_is_not_computable() -> None:
    first = _doc()
    second = {"characters": {"myslef": {"ref_pack": PACK}}}
    shared = shared_pack([first, second])
    assert shared["status"] == "PROPOSED"
    assert shared["packs"] == {"myslef": "pack-myslef"}
    left = resolve(first, [{"frame_id": "a", "characters": ["myslef"]}])
    right = resolve(second, [{"frame_id": "b", "characters": ["myslef"]}])
    assert left["pack_hashes"] == right["pack_hashes"]
    assert left["shots"][0]["references"] == right["shots"][0]["references"]
    other = {
        "characters": {
            "myslef": {"ref_pack": {**PACK, "asset_hash": "other-pack"}},
        },
    }
    split = shared_pack([first, other])
    assert split["status"] == "NOT_COMPUTABLE"
    assert split["code"] == "PACK_SPLIT"


def test_missing_hash_fails_closed_and_prep_sees_the_chain() -> None:
    broken = {
        "characters": {
            "myslef": {
                "ref_pack": {
                    "asset_hash": "pack-myslef",
                    "views": [{"path": "front.png", "ref_role": "identity"}],
                },
            },
        },
    }
    report = resolve(broken, [{"frame_id": "a", "characters": ["myslef"]}])
    assert report["status"] == "NOT_COMPUTABLE"
    assert report["shots"][0]["references"] == []
    frame = {
        "frame_id": "chain",
        "characters": ["myslef"],
        "join": {"chain_from": "a"},
    }
    prep = collect_prep(_doc(), [frame], "keyframe")
    assert any(item.get("code") == "REFS_DROPPED_BY_CHAIN" for item in prep.warnings)
    quiet = collect_prep({}, [frame], "keyframe")
    assert all(item.get("code") != "REFS_DROPPED_BY_CHAIN" for item in quiet.warnings)
    source = (ROOT / "src" / "kubrick" / "plan" / "ref_pack.py").read_text(encoding="utf-8")
    assert "requests" not in source and "urllib" not in source
