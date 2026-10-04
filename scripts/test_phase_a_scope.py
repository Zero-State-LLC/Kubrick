#!/usr/bin/env python3
"""Reference scope, location locks, counts, and cast. Issues #33 and #34."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from adapt_keyframe import adapt_keyframe_packet  # noqa: E402
from adapt_provider import adapt  # noqa: E402
from reference_lint import (  # noqa: E402
    bleed_warnings,
    bound_positive,
    count_phrase,
    location_warnings,
    prompt_lines,
)
from storyboard_prompts import adapter_packet_from_document  # noqa: E402

PY = sys.executable
EXAMPLE = ROOT / "examples/myslef-minder"
REF = "head-lock-short-flush.png"
BINDING = (
    f"reference {REF} defines myslef only; ignore its background; "
    "it does not apply to the minder"
)
NOSE = "smooth featureless skin where a nose would be"
SCHEMA = yaml.safe_load(
    (ROOT / "schemas/storyboard-symbolic-state.schema.yaml").read_text(encoding="utf-8")
)


def _load(path: Path) -> dict[str, object]:
    return _as_dict(yaml.safe_load(path.read_text(encoding="utf-8")))


def _as_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AssertionError("expected a mapping")
    return {str(key): item for key, item in value.items()}


def _rows(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise AssertionError("expected a list")
    return [_as_dict(item) for item in value]


def _codes(payload: object, code: str) -> list[dict[str, object]]:
    raw = _as_dict(payload).get("prep_warnings")
    if not isinstance(raw, list):
        return []
    return [item for item in _rows(raw) if item.get("code") == code]


def _frame(frame_id: str, **extra: object) -> dict[str, object]:
    base: dict[str, object] = {
        "frame_id": frame_id,
        "duration_seconds": 4,
        "node_states": {"observed_1": "present"},
        "action": "stands",
    }
    base.update(extra)
    return base


def _board(frames: list[dict[str, object]], **root: object) -> dict[str, object]:
    document: dict[str, object] = {
        "storyboard_id": "phase-a",
        "title": "phase a",
        "brief": "two people in one room",
        "node_labels": {"observed_1": "chair"},
        "frames": frames,
    }
    document.update(root)
    return document


def _people(ref: dict[str, object] | None = None) -> dict[str, object]:
    myslef: dict[str, object] = {"character_locks": ["no nose"]}
    if ref is not None:
        myslef["references"] = [ref]
    return {
        "minder": {"wardrobe": "plain solid black pullover hoodie, no logo"},
        "myslef": myslef,
    }


def _ref(**extra: object) -> dict[str, object]:
    found: dict[str, object] = {"path": REF, "role": "character"}
    found.update(extra)
    return found


def _prompts(document: dict[str, object], provider: str) -> list[list[str]]:
    """One list of prompt fields per shot. Keyframe checks image and video."""
    packet = adapter_packet_from_document(document, provider)
    if provider == "keyframe":
        movie = adapt_keyframe_packet(packet)
        return [
            [str(shot["imagePrompt"]), str(shot["videoPrompt"])] for shot in _rows(movie["shots"])
        ]
    adapted = adapt(packet, provider)
    return [[str(frame["prompt"])] for frame in _rows(adapted["frames"])]


def _compile(
    brief: Path, plan: Path, out: Path, *, strict: bool,
) -> subprocess.CompletedProcess[str]:
    command = [
        PY, str(ROOT / "scripts/kubrick.py"), "compile",
        "--brief", str(brief), "--mode", "storyboard", "--storyboard-plan", str(plan),
        "--provider", "generic", "--out", str(out),
    ]
    if strict:
        command.append("--strict")
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)


def _mutate_refs(document: dict[str, object], **changes: object) -> None:
    characters = document.get("characters")
    myslef = characters.get("myslef") if isinstance(characters, dict) else None
    refs = myslef.get("references") if isinstance(myslef, dict) else None
    if not isinstance(refs, list):
        raise AssertionError("myslef references")
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        for key, value in changes.items():
            if value is None:
                ref.pop(key, None)
            else:
                ref[key] = value


def test_unscoped_two_person_bleed_is_on_the_receipt_and_adapter() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        brief, plan = _load(EXAMPLE / "brief.yaml"), _load(EXAMPLE / "storyboard-plan.yaml")
        _mutate_refs(brief, applies_to=None)
        _mutate_refs(plan, applies_to=None)
        brief_path, plan_path = root / "brief.yaml", root / "plan.yaml"
        brief_path.write_text(yaml.safe_dump(brief, sort_keys=False), encoding="utf-8")
        plan_path.write_text(yaml.safe_dump(plan, sort_keys=False), encoding="utf-8")
        result = _compile(brief_path, plan_path, root / "out", strict=False)
        assert result.returncode == 0, result.stdout + result.stderr
        receipt = json.loads(result.stdout)
        found = _codes(receipt, "REFERENCE_BLEED_RISK")
        assert found and found[0]["shot"] == "frame-001"
        message = str(found[0]["message"])
        assert REF in message and "minder" in message and "myslef" in message
        packet = yaml.safe_load((root / "out" / "generic-prompt-packet.yaml").read_text("utf-8"))
        assert _codes(packet, "REFERENCE_BLEED_RISK")


def test_scoped_and_one_person_do_not_warn() -> None:
    two = _frame(
        "frame-002",
        characters=["minder", "myslef"],
        reference_images=[REF],
    )
    scoped = _board([two, _frame("frame-003", characters=["myslef"])], characters=_people(
        _ref(applies_to=["myslef"], scope="subject"),
    ))
    assert bleed_warnings(scoped, _rows(scoped["frames"])) == []
    lone = _board(
        [_frame("frame-003", characters=["myslef"], reference_images=[REF])],
        characters=_people(_ref()),
    )
    assert bleed_warnings(lone, _rows(lone["frames"])) == []
    wide = _board([two], characters=_people(_ref(applies_to=["myslef", "minder"])))
    assert bleed_warnings(wide, _rows(wide["frames"]))
    meta = _board([two], characters=_people(_ref(scope="subject")))
    assert bleed_warnings(meta, _rows(meta["frames"]))
    off = _board(
        [_frame("frame-002", characters=["minder", "extra"], reference_images=[REF])],
        characters=_people(_ref(applies_to=["myslef"])),
    )
    assert bleed_warnings(off, _rows(off["frames"]))
    hidden = _board(
        [_frame("frame-002", characters=["minder", "extra"])],
        characters=_people(_ref()),
    )
    assert bleed_warnings(hidden, _rows(hidden["frames"])) == []
    other = _board(
        [_frame("frame-002", characters=["minder", "myslef"], reference_images=["other.png"])],
        characters=_people(_ref()),
    )
    assert bleed_warnings(other, _rows(other["frames"])) == []
    placed = _board(
        [_frame("frame-002", characters=["minder", "myslef"], reference_images=[REF])],
        characters=_people(_ref(role="location")),
    )
    assert bleed_warnings(placed, _rows(placed["frames"])) == []


def test_binding_line_is_once_in_generic_and_keyframe() -> None:
    document = _board(
        [
            _frame("frame-001", characters=["minder", "myslef"], reference_images=[REF]),
            _frame("frame-009", characters=["myslef", "minder", "extra"], reference_images=[REF]),
            _frame("frame-003", characters=["myslef"], reference_images=[REF]),
        ],
        characters=_people(_ref(applies_to=["myslef"])),
        character_locks=["no nose"],
    )
    for provider in ("generic", "keyframe"):
        prompts = _prompts(document, provider)
        assert all(text.count("defines myslef only") == 1 for text in prompts[0])
        assert all(BINDING in text for text in prompts[0])
        assert all("the minder or the extra" in text for text in prompts[1])
        assert all("anyone else" in text for text in prompts[2])
    example = _load(EXAMPLE / "storyboard-plan.yaml")
    for provider in ("generic", "keyframe"):
        opening = _prompts(example, provider)[0]
        assert all(text.count("defines myslef only") == 1 for text in opening)
    assert bleed_warnings(example, _rows(example["frames"])) == []


def test_references_without_scope_still_validate() -> None:
    frame = {
        "frame_id": "frame-001",
        "ordinal": 1,
        "node_states": {"observed_1": "present"},
        "motif_ownership": {"observed_1": None},
        "residue": [],
        "convergence_sites": ["primary"],
        "prohibited_resets": [],
    }
    second = dict(frame)
    second["frame_id"] = "frame-002"
    second["ordinal"] = 2
    board = {
        "schema_version": "1.0.0",
        "storyboard_id": "unscoped",
        "graph_id": "unscoped",
        "frames": [frame, second],
        "characters": {"myslef": {"references": [{"path": REF, "declares": ["nose"]}]}},
        "validation": {"status": "VALID", "errors": [], "warnings": [], "frame_count": 2},
    }
    jsonschema.validate(board, SCHEMA)
    unscoped = _board(
        [_frame("frame-002", characters=["minder", "myslef"], reference_images=[REF])],
        characters=_people(_ref(declares=["nose"])),
    )
    assert bleed_warnings(unscoped, _rows(unscoped["frames"]))


def test_location_contradiction_names_both_and_strict_exits() -> None:
    warned = _board([], location={
        "locks": ["no lit doorway"],
        "references": [{"path": "location-ref-v1", "declares": ["lit doorway", "laptop x4"]}],
    }, counts={"laptop": 1})
    found = location_warnings(warned)
    assert len(found) == 2 and all(item["shot"] is None for item in found)
    text = " ".join(str(item["message"]) for item in found)
    assert "location-ref-v1" in text and "lit doorway" in text and "no lit doorway" in text
    assert "laptop x4" in text and "laptop: 1" in text
    quiet = _board([], location={"locks": ["no lit doorway"], "references": []})
    assert location_warnings(quiet) == []
    assert location_warnings(_board([])) == []
    matched = _board([], location={
        "locks": ["no lit doorway"],
        "references": [{"path": "location-ref-v2", "declares": ["dim racks", "one laptop"]}],
    }, counts={"laptop": 1})
    assert location_warnings(matched) == []
    stemmed = location_warnings(_board([], location={
        "locks": [],
        "references": [{"path": "location-ref-v1", "declares": ["4 laptops"]}],
    }, counts={"laptop": 1}))
    assert stemmed and "4 laptops" in str(stemmed[0]["message"])
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        brief, plan = _load(EXAMPLE / "brief.yaml"), _load(EXAMPLE / "storyboard-plan.yaml")
        _mutate_refs(brief, declares=["hairless scalp"])
        _mutate_refs(plan, declares=["hairless scalp"])
        brief_path, plan_path = root / "brief.yaml", root / "plan.yaml"
        brief_path.write_text(yaml.safe_dump(brief, sort_keys=False), encoding="utf-8")
        plan_path.write_text(yaml.safe_dump(plan, sort_keys=False), encoding="utf-8")
        strict = _compile(brief_path, plan_path, root / "strict", strict=True)
        assert strict.returncode != 0, strict.stdout + strict.stderr
        failed = json.loads(strict.stdout)
        assert failed["reason_vector"] == ["LOCATION_REFERENCE_CONTRADICTION"]
        open_run = _compile(brief_path, plan_path, root / "open", strict=False)
        assert open_run.returncode == 0, open_run.stdout + open_run.stderr


def test_counts_override_and_empty_cast() -> None:
    assert count_phrase("laptop", 1) == "exactly one laptop"
    assert count_phrase("laptop", 0) == "exactly zero laptops"
    assert count_phrase("laptop", 11) == "exactly 11 laptops"
    assert count_phrase("glass", 2) == "exactly two glass"
    document = _board(
        [
            _frame("frame-001", characters=["minder", "myslef"]),
            _frame("frame-002", characters=["myslef"], counts={"laptop": 2, "glass": 2}),
        ],
        counts={"laptop": 1},
        characters=_people(),
    )
    for provider in ("generic", "keyframe"):
        first, second = _prompts(document, provider)
        assert all(
            "exactly one laptop" in text and "exactly two laptops" not in text for text in first
        )
        assert all(
            "exactly two laptops" in text and "exactly two glass" in text for text in second
        )
    example = _load(EXAMPLE / "storyboard-plan.yaml")
    motion = "the minder walks out of frame right as push-in"
    for provider in ("generic", "keyframe"):
        prompts = _prompts(example, provider)
        for index, shot in enumerate(prompts):
            assert "exactly one laptop" in shot[0]
            if provider == "keyframe" and index == 3:
                assert shot[1] == motion
                assert "exactly one laptop" not in shot[1]
                assert "nobody is in frame" in shot[0]
                assert "nobody is in frame" not in shot[1]
            else:
                assert all("exactly one laptop" in text for text in shot)
                if index == 3:
                    assert all("nobody is in frame" in text for text in shot)
        last = prompts[3]
        assert all(
            "WARDROBE LOCK" not in text and NOSE not in text and "no nose" not in text
            for text in last
        )
    cast = _frame("frame-004", cast=[], characters=["myslef", "minder"])
    lines = prompt_lines(_board([], characters=_people(), character_locks=["no nose"]), cast, [])
    assert lines[0] == "nobody is in frame"
    positive = bound_positive("empty", [], ["no nose"], ["no nose"], _people_doc(), cast)
    assert NOSE not in positive and "WARDROBE" not in positive
    nested = {"provider_parameters": {"cast": []}, "characters": ["myslef"]}
    assert prompt_lines(_people_doc(), nested, [])[0] == "nobody is in frame"
    only = _frame("frame-003", cast=["myslef"], characters=["minder", "myslef"])
    wardrobe = " ".join(prompt_lines(_people_doc(), only, ["CHAIR LOCK: tipped"]))
    assert "minder wears" not in wardrobe and "CHAIR LOCK" in wardrobe
    assert NOSE in bound_positive("seated", [], ["no nose"], ["no nose"], _people_doc(), only)
    bare = _frame("frame-004", characters=[])
    assert "nobody is in frame" not in " ".join(prompt_lines(_people_doc(), bare, []))
    assert NOSE in bound_positive("empty", [], ["no nose"], ["no nose"], _people_doc(), bare)


def _people_doc() -> dict[str, object]:
    return _board([], characters=_people(), character_locks=["no nose"])


def main() -> None:
    test_unscoped_two_person_bleed_is_on_the_receipt_and_adapter()
    test_scoped_and_one_person_do_not_warn()
    test_binding_line_is_once_in_generic_and_keyframe()
    test_references_without_scope_still_validate()
    test_location_contradiction_names_both_and_strict_exits()
    test_counts_override_and_empty_cast()
    print("phase A scope tests: PASS")


if __name__ == "__main__":
    main()
