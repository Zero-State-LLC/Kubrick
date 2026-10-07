#!/usr/bin/env python3
"""Lock carriers and the start-frame gate. Issues #35 and #38."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from adapt_keyframe import adapt_keyframe_packet  # noqa: E402
from adapt_provider import adapt  # noqa: E402
from continuity_locks import set_strict  # noqa: E402
from lock_carriers import carrier_for, lock_table, negative_only_warnings  # noqa: E402
from provider_capabilities import capabilities_for  # noqa: E402
from start_frame_gate import (  # noqa: E402
    format_seconds,
    grab,
    handoff,
    stamp_asset,
    start_warnings,
)
from storyboard_prompts import adapter_packet_from_document  # noqa: E402

from kubrick.paths import implementation_of  # noqa: E402

PY = sys.executable
EXAMPLE = ROOT / "examples/myslef-minder"
MOVIE = json.loads(
    (ROOT / "schemas/keyframe-create-movie.schema.json").read_text(encoding="utf-8")
)
LIGHT = {
    "id": "red-chest-light",
    "kind": "light",
    "critical": True,
    "character": "myslef",
    "negative": "no red light on the head or chest",
}
GRAB = "ffmpeg -ss 3.583 -i shot-04-v8.mp4 -frames:v 1 06-start.png"


def _as_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AssertionError("expected a mapping")
    return {str(key): item for key, item in value.items()}


def _rows(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [_as_dict(item) for item in value if isinstance(item, dict)]


def _load(path: Path) -> dict[str, object]:
    return _as_dict(yaml.safe_load(path.read_text(encoding="utf-8")))


def _frame(frame_id: str, **extra: object) -> dict[str, object]:
    base: dict[str, object] = {
        "frame_id": frame_id,
        "duration_seconds": 4,
        "node_states": {"observed_1": "present"},
        "action": "stands still",
        "characters": ["myslef"],
    }
    base.update(extra)
    return base


def _board(frames: list[dict[str, object]], **root: object) -> dict[str, object]:
    document: dict[str, object] = {
        "storyboard_id": "carriers",
        "title": "carriers",
        "brief": "a lock needs a carrier",
        "node_labels": {"observed_1": "chair"},
        "characters": {
            "myslef": {"character_locks": ["no nose"], "wardrobe": "plain top"},
            "minder": {"wardrobe": "plain solid black pullover hoodie, no logo"},
        },
        "character_locks": ["no nose"],
        "frames": frames,
    }
    document.update(root)
    return document


def _by(rows: list[dict[str, object]], shot: str, lock: str) -> dict[str, object]:
    found = [row for row in rows if row.get("shot") == shot and row.get("lock") == lock]
    assert len(found) == 1, (shot, lock, found)
    return found[0]


def _codes(payload: dict[str, object], code: str) -> list[dict[str, object]]:
    return [item for item in _rows(payload.get("prep_warnings")) if item.get("code") == code]


def test_negative_prompt_effective_is_provider_data() -> None:
    for name in ("generic", "flux", "sd3", "midjourney", "grok-imagine"):
        assert capabilities_for(name)["negative_prompt_effective"] is True
    assert capabilities_for("keyframe")["negative_prompt_effective"] is False
    assert capabilities_for("unknown-lab")["negative_prompt_effective"] is False


def _carrier_case() -> tuple[dict[str, object], list[dict[str, object]]]:
    frames = [
        _frame(
            "frame-001",
            reference_images=["scalp.png"],
            characters=["myslef"],
        ),
        _frame("frame-002", characters=["minder"], prop_states={"chair": "C0"}),
        _frame(
            "frame-003",
            characters=["myslef"],
            join={"chain_from": "frame-001", "at_seconds": 2},
        ),
        _frame("frame-004", characters=["myslef"]),
        _frame("frame-005", characters=["myslef"]),
        _frame("frame-006", characters=["myslef"], residue=["soft fill from the left"]),
    ]
    document = _board(
        frames,
        props={"chair": {"states": {"C0": "upright"}}},
        locks=[
            LIGHT,
            {"id": "glow", "kind": "light", "critical": False, "negative": "no glow"},
            {"id": "fill", "kind": "light", "positive": "soft fill from the left"},
        ],
        characters={
            "myslef": {
                "character_locks": ["no nose"],
                "wardrobe": "plain top",
                "references": [{
                    "path": "scalp.png",
                    "role": "character",
                    "applies_to": ["myslef"],
                    "declares": ["hairless scalp"],
                }],
            },
            "minder": {"wardrobe": "plain solid black pullover hoodie, no logo"},
        },
    )
    return document, frames


def test_each_carrier_and_negative_only_lock() -> None:
    document, frames = _carrier_case()
    rows = lock_table(document, frames)
    assert _by(rows, "frame-001", "no nose")["carrier"] == "reference"
    wardrobe = [
        row for row in rows if row.get("shot") == "frame-002" and row.get("kind") == "wardrobe"
    ]
    assert len(wardrobe) == 1 and wardrobe[0]["carrier"] == "prompt_positive"
    assert _by(rows, "frame-002", "chair")["carrier"] == "prompt_positive"
    assert _by(rows, "frame-003", "red-chest-light")["carrier"] == "unverified"
    red = _by(rows, "frame-004", "red-chest-light")
    assert red["carrier"] == "prompt_negative_only" and red["critical"] is True
    fill = _by(rows, "frame-005", "fill")
    assert fill["carrier"] == "unverified"
    assert fill["code"] == "LOCK_POSITIVE_NOT_IN_PROMPT"
    said = _by(rows, "frame-006", "fill")
    assert said["carrier"] == "prompt_positive" and "code" not in said
    dim = [row for row in rows if row.get("lock") == "glow"]
    assert dim
    assert all(
        row["carrier"] == "prompt_negative_only"
        for row in dim
        if row["shot"] != "frame-003"
    )


def test_negative_only_warning_names_the_lock() -> None:
    document, frames = _carrier_case()
    warnings = negative_only_warnings(document, frames, "keyframe")
    named = [item for item in warnings if item["shot"] == "frame-004"]
    assert len(named) == 1
    assert "red-chest-light" in str(named[0]["message"]) and "frame-004" in str(named[0]["message"])
    assert "negative_prompt_effective is false" in str(named[0]["recommendation"])
    assert all(item["shot"] != "frame-003" for item in warnings)
    assert "glow" not in " ".join(str(item["message"]) for item in warnings)
    generic = negative_only_warnings(document, frames, "generic")
    assert "negative_prompt_effective is false" not in str(generic[0]["recommendation"])


def test_start_frame_object_and_empty_cast_carriers() -> None:
    document = _board([], characters={"myslef": {"character_locks": ["no nose"]}})
    loose = _frame("frame-007", start_frame={"asset": "still.png"})
    bare = carrier_for(
        document, loose, "light", "no glow", "myslef", {"id": "glow"},
    )
    assert bare["carrier"] == "unverified"
    assert bare["status"] == "unverified"
    assert bare["lock_id"] == "glow"
    empty = _frame("frame-008", cast=[])
    rows = lock_table(_board([empty], locks=[LIGHT]), [empty])
    assert rows == [] or all(row["kind"] != "light" for row in rows)


def test_example_carriers_are_on_generic_and_keyframe() -> None:
    document = _load(EXAMPLE / "storyboard-plan.yaml")
    packet = adapter_packet_from_document(document, "generic")
    generic = adapt(packet, "generic")
    movie = adapt_keyframe_packet(adapter_packet_from_document(document, "keyframe"))
    jsonschema.validate(movie, MOVIE)
    for payload in (generic, movie):
        rows = _rows(payload.get("lock_carriers"))
        assert {str(row["carrier"]) for row in rows} >= {"unverified", "prompt_positive"}
        red = [row for row in rows if row.get("lock") == "red-chest-light"]
        by_shot = {str(row["shot"]): str(row["carrier"]) for row in red}
        # #133 review: the lock defines a positive, but the compiled prompts omit it.
        assert by_shot["frame-001"] == "unverified"
        assert by_shot["frame-002"] == "unverified"
        assert by_shot["frame-003"] == "unverified"
        assert "frame-004" not in by_shot
        omitted = [row for row in red if row.get("code") == "LOCK_POSITIVE_NOT_IN_PROMPT"]
        assert {str(row["shot"]) for row in omitted} == {"frame-001", "frame-003"}
    assert _codes(movie, "NEGATIVE_ONLY_LOCK") == []
    bare = copy.deepcopy(document)
    locks = bare["locks"]
    assert isinstance(locks, list)
    for lock in locks:
        if isinstance(lock, dict) and lock.get("id") == "red-chest-light":
            lock.pop("positive")
    stripped = adapt_keyframe_packet(adapter_packet_from_document(bare, "keyframe"))
    only = _codes(stripped, "NEGATIVE_ONLY_LOCK")
    assert {str(item["shot"]) for item in only} == {"frame-001", "frame-003"}
    assert all("red-chest-light" in str(item["message"]) for item in only)
    shots = _rows(movie["shots"])
    assert "negative" not in shots[0]
    image = shots[1]["startImage"]
    assert isinstance(image, dict)
    assert image["sourceFrame"] == "frame-001" and image["atSeconds"] == 2
    assert image["asset"] == "starts/shot-04.png"
    assert shots[3]["startImage"] == {"sourceFrame": "frame-002"}


def test_start_frame_gate_and_strict_exit() -> None:
    assert format_seconds(2.0) == "2"
    assert format_seconds(2.958) == "2.958"
    assert format_seconds(3.583) == "3.583"
    assert format_seconds(0.0) == "0"
    chained = _frame(
        "frame-002",
        shot_id="06",
        join={"chain_from": "frame-001"},
        start_frame={"source_take": "shot-04-v8.mp4", "at_seconds": 3.583},
    )
    missing = start_warnings([_frame("frame-001"), chained], "keyframe")
    assert len(missing) == 1 and missing[0]["code"] == "START_FRAME_MISSING"
    assert missing[0]["shot"] == "frame-002"
    assert "BLOCKED_PRE_SPEND" in str(missing[0]["message"])
    assert GRAB in str(missing[0]["message"])
    assert "START_FRAME_UNVERIFIED" not in str(missing)
    unverified = dict(chained)
    unverified["start_frame"] = {
        "asset": "starts/shot-06.png", "verified": False, "at_seconds": 3.583,
    }
    flagged = start_warnings([unverified], "keyframe")
    assert [item["code"] for item in flagged] == ["START_FRAME_UNVERIFIED"]
    verified = dict(chained)
    verified["start_frame"] = {"asset": "starts/shot-06.png", "verified": True}
    assert start_warnings([verified], "keyframe") == []
    assert start_warnings([chained], "generic") == []
    assert start_warnings([_frame("frame-001", start_frame={"at_seconds": 1})], "keyframe") == []
    _strict_cli()


def test_grab_string_and_asset_stamp() -> None:
    verified = {"start_frame": {"asset": "starts/shot-06.png", "verified": True}}
    joined = _frame("frame-002", join={"chain_from": "frame-001", "at_seconds": 2.5})
    at, source = grab(joined)
    assert (at, source) == (2.5, "<source>")
    assert handoff("frame-002", 2.0, "<source>") == (
        "ffmpeg -ss 2 -i <source> -frames:v 1 frame-002-start.png"
    )
    image = {"sourceFrame": "frame-001", "atSeconds": 2}
    shot: dict[str, object] = {"startImage": image}
    stamp_asset(shot, verified)
    assert image == {"sourceFrame": "frame-001", "atSeconds": 2}
    stamped = shot["startImage"]
    assert isinstance(stamped, dict)
    assert stamped["asset"] == "starts/shot-06.png" and stamped is not image
    stamp_asset({"title": "plain"}, verified)
    blank: dict[str, object] = {"startImage": dict(image)}
    stamp_asset(blank, {"start_frame": {"asset": "  "}})
    assert blank["startImage"] == image
    source_text = implementation_of(ROOT / "scripts/start_frame_gate.py").read_text(
        encoding="utf-8"
    )
    assert "subprocess" not in source_text and "os.system" not in source_text
    assert not Path("06-start.png").exists()


def _story(verified: object, asset: str | None) -> dict[str, object]:
    start: dict[str, object] = {"source_take": "shot-04-v8.mp4", "at_seconds": 3.583}
    if asset is not None:
        start["asset"] = asset
    if verified is not None:
        start["verified"] = verified
    return {
        "storyboard_id": "start-gate",
        "title": "start gate",
        "brief": "a chained shot needs a grabbed still",
        "node_labels": {"observed_1": "chair"},
        "frames": [
            _frame("frame-001", characters=["minder"], duration_seconds=4),
            _frame(
                "frame-002",
                shot_id="06",
                characters=["minder"],
                duration_seconds=4,
                join={"chain_from": "frame-001", "at_seconds": 2.0},
                start_frame=start,
            ),
        ],
    }


def _video(plan: Path, output: Path, *, strict: bool) -> subprocess.CompletedProcess[str]:
    command = [
        PY, str(ROOT / "scripts/kubrick.py"), "video", "--action", "adapt",
        "--provider", "keyframe", "--input", str(plan), "--output", str(output),
    ]
    if strict:
        command.append("--strict")
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)


def _strict_cli() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        plan = root / "plan.yaml"
        plan.write_text(yaml.safe_dump(_story(None, None), sort_keys=False), encoding="utf-8")
        opened = _video(plan, root / "open.yaml", strict=False)
        assert opened.returncode == 0, opened.stdout + opened.stderr
        body = _as_dict(yaml.safe_load((root / "open.yaml").read_text(encoding="utf-8")))
        assert body.get("status") == "PROPOSED"
        movie = _as_dict(_as_dict(body["result"])["adapted_packet"])
        assert "validation" not in movie
        missing = _codes(movie, "START_FRAME_MISSING")
        assert missing and GRAB in str(missing[0]["message"])
        shots = _rows(movie["shots"])
        assert shots[1]["startImage"] == {"sourceFrame": "frame-001", "atSeconds": 2.0}
        closed = _video(plan, root / "strict.yaml", strict=True)
        assert closed.returncode != 0, closed.stdout + closed.stderr
        failed = _as_dict(yaml.safe_load((root / "strict.yaml").read_text(encoding="utf-8")))
        assert failed.get("status") == "NOT_COMPUTABLE"
        failed_movie = _as_dict(_as_dict(failed["result"])["adapted_packet"])
        assert _as_dict(failed_movie["validation"])["status"] == "INVALID"
        assert _codes(failed_movie, "START_FRAME_MISSING")
        plan.write_text(
            yaml.safe_dump(_story(False, "starts/shot-06.png"), sort_keys=False),
            encoding="utf-8",
        )
        soft = _video(plan, root / "soft.yaml", strict=False)
        assert soft.returncode == 0, soft.stdout + soft.stderr
        soft_movie = _as_dict(_as_dict(_as_dict(yaml.safe_load(
            (root / "soft.yaml").read_text(encoding="utf-8")
        ))["result"])["adapted_packet"])
        assert _codes(soft_movie, "START_FRAME_UNVERIFIED")
        assert _codes(soft_movie, "START_FRAME_MISSING") == []
        shot_image = _as_dict(_rows(soft_movie["shots"])[1]["startImage"])
        assert shot_image["asset"] == "starts/shot-06.png"
        plan.write_text(
            yaml.safe_dump(_story(True, "starts/shot-06.png"), sort_keys=False),
            encoding="utf-8",
        )
        ready = _video(plan, root / "ready.yaml", strict=True)
        assert ready.returncode == 0, ready.stdout + ready.stderr
    set_strict(False)


def main() -> None:
    test_negative_prompt_effective_is_provider_data()
    test_each_carrier_and_negative_only_lock()
    test_example_carriers_are_on_generic_and_keyframe()
    test_start_frame_gate_and_strict_exit()
    print("phase A lock tests: PASS")


if __name__ == "__main__":
    main()
