#!/usr/bin/env python3
"""EP-01 provider preflight: durations, reference aspect, board aspect, billed rates."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from adapt_keyframe import adapt_keyframe_packet  # noqa: E402
from provider_limits import (  # noqa: E402
    billed_credits,
    image_packet,
    reference_aspect_refusal,
)
from spend_plan import spend_estimate  # noqa: E402


def _packet(seconds: object) -> dict[str, object]:
    return {
        "source_graph_id": "ep01-limits",
        "provider": "keyframe",
        "validation": {"status": "VALID", "errors": []},
        "aspect_ratio": "9:16",
        "frames": [{
            "frame_id": "frame-001",
            "prompt": "a room holds still",
            "provider_parameters": {"duration_seconds": seconds},
        }],
    }


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value


def _text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    assert isinstance(value, str)
    return value


def _first_duration(movie: dict[str, object]) -> object:
    shots = movie.get("shots")
    assert isinstance(shots, list) and shots
    shot = _mapping(shots[0])
    return shot.get("durationSeconds")


def test_three_second_and_fractional_plans_fail_closed() -> None:
    """A 3s beat is generated at 4s and trimmed. 4.5s and 31s are not submitted."""
    short = adapt_keyframe_packet(_packet(3))
    assert short.get("status") != "NOT_COMPUTABLE", short
    assert _first_duration(short) == 4
    assert short.get("plannedDurationSeconds") == 3
    fraction = adapt_keyframe_packet(_packet(4.5))
    assert fraction.get("status") == "NOT_COMPUTABLE"
    assert fraction.get("code") == "DURATION_NONINTEGER"
    assert "shots" not in fraction
    over = adapt_keyframe_packet(_packet(31))
    assert over.get("code") == "DURATION_OUT_OF_RANGE"
    whole = adapt_keyframe_packet(_packet(4))
    assert whole.get("status") != "NOT_COMPUTABLE"
    assert _first_duration(whole) == 4


def test_head_lock_sheet_aspect_is_refused() -> None:
    wide = reference_aspect_refusal(2480, 800)
    assert wide is not None
    assert wide["code"] == "REF_ASPECT_OUT_OF_RANGE"
    assert wide["aspect"] == 3.1
    assert "2.5" in str(wide["suggestion"])
    assert reference_aspect_refusal(1920, 1080) is None
    assert reference_aspect_refusal(1000, 2500) is None  # 0.40
    assert reference_aspect_refusal(2500, 1000) is None  # 2.50
    low = reference_aspect_refusal(390, 1000)
    assert low is not None and low["code"] == "REF_ASPECT_OUT_OF_RANGE"
    packet = _packet(4)
    packet["reference_assets"] = [{"path": "head-lock.png", "width": 2480, "height": 800}]
    refused = adapt_keyframe_packet(packet)
    assert refused.get("status") == "NOT_COMPUTABLE"
    assert refused.get("code") == "REF_ASPECT_OUT_OF_RANGE"
    assert "2480" in _text(refused, "message")


def test_board_and_still_require_aspect() -> None:
    missing = {"frames": [{"prompt": "a board"}], "validation": {"status": "VALID"}}
    board = image_packet(missing, "board")
    assert board["code"] == "BOARD_ASPECT_MISSING"
    assert "aspectRatio" not in board
    still = image_packet(missing, "still")
    assert still["code"] == "BOARD_ASPECT_MISSING"
    stamped = image_packet({"aspect_ratio": "9:16", "frames": [{"prompt": "alley"}]}, "board")
    assert stamped["status"] == "PROPOSED"
    assert stamped["aspectRatio"] == "9:16"
    assert stamped["model"] == "nano-banana-2"


def test_billed_rates_match_observed_seconds() -> None:
    assert billed_credits(4, 15.5) == 62
    assert billed_credits(5, 15.5) == 77
    assert billed_credits(6, 15.5) == 93
    assert billed_credits(5, 15.5) != 5 * 15.5
    estimate = spend_estimate("keyframe", [
        {"shot": "04", "generated_seconds": 4},
        {"shot": "05", "generated_seconds": 5},
        {"shot": "06", "generated_seconds": 6},
    ])
    rows = estimate.get("shots")
    assert isinstance(rows, list)
    credits = [_mapping(item).get("credits") for item in rows]
    assert credits == [62, 77, 93]
    assert estimate.get("total_credits") == 62 + 77 + 93


def main() -> None:
    test_three_second_and_fractional_plans_fail_closed()
    test_head_lock_sheet_aspect_is_refused()
    test_board_and_still_require_aspect()
    test_billed_rates_match_observed_seconds()
    print("provider limits tests: PASS")


if __name__ == "__main__":
    main()
