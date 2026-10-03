#!/usr/bin/env python3
"""Voice, dialogue, asymmetry, and screen direction. Issues #43 and #44."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from adapt_provider import adapt  # noqa: E402
from audio_screen_locks import asymmetry_lines, guide_sound, lint  # noqa: E402
from reference_lint import prompt_lines  # noqa: E402
from storyboard_prompts import adapter_packet_from_document  # noqa: E402

EXAMPLE = ROOT / "examples/myslef-minder"
LINE = "cracked optic on the figure's right (viewer's left); never swap sides"
TWENTY = " ".join(["word"] * 20)


def _myslef_on_screen(frame: dict[str, object]) -> bool:
    cast = frame.get("cast")
    people = cast if isinstance(cast, list) else frame.get("characters")
    return isinstance(people, list) and "myslef" in people


def _load(path: Path) -> dict[str, object]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _frame(frame_id: str, **fields: object) -> dict[str, object]:
    frame: dict[str, object] = {"frame_id": frame_id}
    frame.update(fields)
    return frame


def _codes(items: list[dict[str, str | None]], code: str) -> list[dict[str, str | None]]:
    return [item for item in items if item.get("code") == code]


def test_voice_lock_fails_closed() -> None:
    document = {"characters": {"myslef": {"voice": {"speaks": False}}}}
    frames = [_frame(
        "frame-002",
        characters=["myslef"],
        speech_lines=["myslef: I can speak"],
        duration_seconds=2,
    )]
    _warnings, errors = lint(document, frames)
    assert len(errors) == 1
    assert "VOICE_LOCK_VIOLATION" in errors[0]
    assert "myslef" in errors[0]
    assert "frame-002" in errors[0]
    story = _load(EXAMPLE / "storyboard-plan.yaml")
    characters = story["characters"]
    assert isinstance(characters, dict)
    myslef = dict(characters["myslef"])
    myslef["voice"] = {"speaks": False}
    characters["myslef"] = myslef
    frames_raw = story["frames"]
    assert isinstance(frames_raw, list)
    second = dict(frames_raw[1])
    second["speech_lines"] = ["myslef: hello there"]
    frames_raw[1] = second
    packet = adapter_packet_from_document(story)
    validation = packet["validation"]
    assert isinstance(validation, dict)
    assert validation["status"] == "INVALID"
    packet_errors = validation["errors"]
    assert isinstance(packet_errors, list)
    assert any(
        "VOICE_LOCK_VIOLATION" in str(item) and "myslef" in str(item) and "frame-002" in str(item)
        for item in packet_errors
    )
    refused = adapt(packet, "keyframe")
    assert refused["status"] == "NOT_COMPUTABLE"


def test_never_clone_fails_closed() -> None:
    document = {"characters": {"minder": {"voice": {
        "library_id": "danny",
        "never_clone_of": ["danny"],
        "speaks": True,
    }}}}
    frames = [_frame("frame-002", characters=["minder"], duration_seconds=1)]
    _warnings, errors = lint(document, frames)
    assert errors and "VOICE_LOCK_VIOLATION" in errors[0]
    assert "danny" in errors[0]
    named = {"characters": {"minder": {"voice": {
        "name": "Danny",
        "never_clone_of": ["danny"],
    }}}}
    _warnings, named_errors = lint(named, frames)
    assert named_errors and "Danny" in named_errors[0]
    safe = {"characters": {"minder": {"voice": {
        "library_id": "ibrahim-talkative-friend",
        "never_clone_of": ["danny"],
        "speaks": True,
    }}}}
    _warnings, safe_errors = lint(safe, frames)
    assert safe_errors == []


def test_dialogue_length() -> None:
    document = {"characters": {"minder": {"voice": {
        "library_id": "ibrahim-talkative-friend",
        "never_clone_of": ["danny"],
        "speaks": True,
    }}}}
    short = [_frame(
        "frame-002", characters=["minder"], duration_seconds=1.0, speech_lines=["minder: Wha—"],
    )]
    warnings, errors = lint(document, short)
    assert errors == []
    assert _codes(warnings, "DIALOGUE_TOO_LONG") == []
    boundary = [_frame(
        "frame-003",
        characters=["minder"],
        duration_seconds=2,
        speech_lines=["minder: one two three four five"],
    )]
    assert _codes(lint(document, boundary)[0], "DIALOGUE_TOO_LONG") == []
    over = [_frame(
        "frame-003",
        characters=["minder"],
        duration_seconds=2,
        speech_lines=[f"minder: {TWENTY}"],
    )]
    found = _codes(lint(document, over)[0], "DIALOGUE_TOO_LONG")
    assert found and found[0]["shot"] == "frame-003"
    assert "minder" in str(found[0]["message"])
    capped = {"characters": {"minder": {"voice": {"speaks": True, "max_words": 2}}}}
    slow = [_frame(
        "frame-004",
        characters=["minder"],
        duration_seconds=10,
        speech_lines=["minder: one two three"],
    )]
    capped_hit = _codes(lint(capped, slow)[0], "DIALOGUE_TOO_LONG")
    assert capped_hit and capped_hit[0]["shot"] == "frame-004"
    at_cap = [_frame(
        "frame-004",
        characters=["minder"],
        duration_seconds=10,
        speech_lines=["minder: one two"],
    )]
    assert _codes(lint(capped, at_cap)[0], "DIALOGUE_TOO_LONG") == []
    flagged = {"characters": {"minder": {"voice": {"speaks": True, "max_words": True}}}}
    assert _codes(lint(flagged, slow)[0], "DIALOGUE_TOO_LONG") == []


def test_muted_native_and_example_line() -> None:
    story = _load(EXAMPLE / "storyboard-plan.yaml")
    packet = adapter_packet_from_document(story)
    movie = adapt(packet, "keyframe")
    shots = movie["shots"]
    assert isinstance(shots, list)
    note = "native audio is a guide track only"
    for shot in shots:
        assert isinstance(shot, dict)
        audio = shot["audio"]
        assert isinstance(audio, dict)
        assert note in str(audio["sound"])
    second = shots[1]
    assert isinstance(second, dict)
    audio = second["audio"]
    assert isinstance(audio, dict)
    speech = audio["speech"]
    assert isinstance(speech, dict)
    assert "Wha—" in " ".join(str(item) for item in speech["lines"])
    assert guide_sound("room tone", "native") == "room tone"
    assert guide_sound("room tone", None) == "room tone"
    assert note in guide_sound("room tone", "external")
    assert movie.get("status") != "NOT_COMPUTABLE"
    assert isinstance(movie.get("shots"), list)


def test_asymmetry_once_on_generic_and_keyframe() -> None:
    story = _load(EXAMPLE / "storyboard-plan.yaml")
    packet = adapter_packet_from_document(story)
    generic = adapt(packet, "generic")
    movie = adapt(packet, "keyframe")
    frames = packet["frames"]
    generic_frames = generic["frames"]
    shots = movie["shots"]
    sources = story["frames"]
    assert isinstance(frames, list)
    assert isinstance(generic_frames, list)
    assert isinstance(shots, list)
    assert isinstance(sources, list)
    on_screen = 0
    for source, frame, rendered, shot in zip(sources, frames, generic_frames, shots):
        assert isinstance(source, dict) and isinstance(frame, dict)
        assert isinstance(rendered, dict) and isinstance(shot, dict)
        texts = (
            str(frame["prompt"]),
            str(rendered["prompt"]),
            str(shot["imagePrompt"]),
            str(shot["videoPrompt"]),
        )
        if _myslef_on_screen(source):
            on_screen += 1
            assert [text.count(LINE) for text in texts] == [1, 1, 1, 1]
        else:
            assert all(LINE not in text for text in texts)
            assert "nobody is in frame" in texts[0]
    assert on_screen == 3
    present = prompt_lines(
        story,
        _frame("frame-003", characters=["myslef"]),
        [],
    )
    assert present.count(LINE) == 1
    empty = asymmetry_lines(story, _frame("frame-004", characters=[], cast=[]))
    assert empty == []


def test_screen_direction_and_mirrored_reference() -> None:
    left = _frame("frame-001", screen_side={"minder": "left"})
    right = _frame("frame-002", screen_side={"minder": "right"})
    warnings, errors = lint({}, [left, right])
    assert errors == []
    found = _codes(warnings, "SCREEN_DIRECTION_FLIP")
    assert len(found) == 1
    assert "frame-001" in str(found[0]["message"])
    assert "frame-002" in str(found[0]["message"])
    assert "minder" in str(found[0]["message"])
    turned = _frame("frame-002", screen_side={"minder": "right"}, axis_change=True)
    assert _codes(lint({}, [left, turned])[0], "SCREEN_DIRECTION_FLIP") == []
    centered = _frame("frame-002", screen_side={"minder": "center"})
    assert _codes(lint({}, [left, centered])[0], "SCREEN_DIRECTION_FLIP") == []
    mirrored = {"characters": {"myslef": {"references": [{
        "path": "head-lock-short-flush.png",
        "role": "character",
        "mirrored": True,
    }]}}}
    mirror_warnings, _mirror_errors = lint(mirrored, [left])
    message = str(_codes(mirror_warnings, "MIRRORED_REFERENCE")[0]["message"])
    assert "head-lock-short-flush.png" in message
    assert "inverted" in message
    text_true = {"references": [{"path": "head.png", "mirrored": "true"}]}
    assert _codes(lint(text_true, [left])[0], "MIRRORED_REFERENCE") == []


def main() -> None:
    test_voice_lock_fails_closed()
    test_never_clone_fails_closed()
    test_dialogue_length()
    test_muted_native_and_example_line()
    test_asymmetry_once_on_generic_and_keyframe()
    test_screen_direction_and_mirrored_reference()
    print("phase B lock tests: PASS")


if __name__ == "__main__":
    main()
