#!/usr/bin/env python3
"""Retake impact against observed takes. Issue #37."""

from __future__ import annotations

import copy
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import intent_router as ir  # noqa: E402
from take_ledger import impact  # noqa: E402
from take_ledger import main as impact_main  # noqa: E402

PY = sys.executable
EXAMPLE = ROOT / "examples/myslef-minder"
STALE = (
    "shot 06 prop chair observed 'beside the desk' does not continue "
    "retake 04 observed end 'C3 far end'"
)


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


def _board() -> dict[str, object]:
    return {
        "props": {"chair": {"states": {
            "C0": "beside the desk",
            "C3": "tipped on its side at the far end",
            "C4": "still at the far end",
        }}},
        "frames": [
            {"frame_id": "frame-001", "shot_id": "03", "prop_states": {"chair": "C0"}},
            {"frame_id": "frame-002", "shot_id": "04", "prop_states": {"chair": "C0->C3"}},
            {"frame_id": "frame-003", "shot_id": "05", "prop_states": {"chair": "C3"}},
            {"frame_id": "frame-004", "shot_id": "06", "prop_states": {"chair": "C3->C4"}},
        ],
    }


def _takes() -> list[dict[str, object]]:
    loaded = yaml.safe_load((EXAMPLE / "takes.yaml").read_text(encoding="utf-8"))
    return _rows(loaded)


def _warnings(result: dict[str, object]) -> list[dict[str, object]]:
    return _rows(result.get("prep_warnings"))


def _set_chair(take: dict[str, object], key: str, value: str) -> None:
    state = take.get(key)
    props = state.get("props") if isinstance(state, dict) else None
    if not isinstance(props, dict):
        raise AssertionError("take props")
    props["chair"] = value


def test_router_sends_impact_to_the_ledger() -> None:
    call = ir.resolve([
        "do", "storyboard", "--action", "impact", "--takes", "takes.yaml", "--retake", "04",
    ])
    assert call.script.name == "take_ledger.py"
    assert "--surface-action" not in call.argv


def test_stale_take_names_the_prop_and_a_match_is_silent() -> None:
    board = _load(EXAMPLE / "storyboard-plan.yaml")
    before = copy.deepcopy(board)
    result = impact(board, _takes(), "04")
    assert board == before
    assert result["status"] == "PROPOSED" and result["label"] == "OBSERVATION"
    found = _warnings(result)
    assert len(found) == 1
    assert found[0]["code"] == "STALE_TAKE" and found[0]["shot"] == "06"
    assert found[0]["message"] == STALE
    assert found[0]["recommendation"] == "chain_from 04 so this take starts from the observed end"
    assert "03" not in str(found[0]["shot"])
    same = impact(board, _takes(), "frame-002")
    assert _warnings(same)[0]["message"] == STALE
    matched = _takes()
    _set_chair(matched[1], "observed_start_state", "C3")
    assert _warnings(impact(board, matched, "04")) == []
    prefix = _takes()
    _set_chair(prefix[1], "observed_start_state", "C3 tipped")
    assert _warnings(impact(_board(), prefix, "04")) == []
    declared = _board()
    assert _warnings(impact(declared, [_takes()[0]], "04")) == []
    drifted = _board()
    frames = drifted["frames"]
    assert isinstance(frames, list)
    last = frames[3]
    assert isinstance(last, dict)
    last["prop_states"] = {"chair": "C4"}
    stale = _warnings(impact(drifted, [_takes()[0]], "04"))
    assert stale and stale[0]["shot"] == "06" and "C4" in str(stale[0]["message"])
    bare = _board()
    bare_frames = bare["frames"]
    assert isinstance(bare_frames, list) and isinstance(bare_frames[3], dict)
    bare_frames[3].pop("prop_states")
    assert _warnings(impact(bare, [_takes()[0]], "04")) == []


def test_observations_do_not_overwrite_and_edges_fail_closed() -> None:
    board = _board()
    original = copy.deepcopy(board)
    empty = [{"shot": "04", "take_id": "v8"}]
    quiet = impact(board, empty, "04")
    assert quiet["status"] == "NOT_COMPUTABLE"
    assert quiet["code"] == "OBSERVATION_MISSING"
    assert any(item.get("code") == "OBSERVATION_MISSING" for item in _warnings(quiet))
    assert board == original
    wardrobe = {
        "frames": [
            {"frame_id": "frame-001", "shot_id": "04"},
            {"frame_id": "frame-002", "shot_id": "06"},
        ],
    }
    takes = [
        {"shot": "04", "observed_end_state": {"wardrobe": {"minder": "black hoodie"}}},
        {"shot": "06", "observed_start_state": {"wardrobe": {"minder": "red hoodie"}}},
    ]
    found = _warnings(impact(wardrobe, takes, "04"))
    assert len(found) == 1 and "wardrobe minder" in str(found[0]["message"])
    takes[1] = {"shot": "06", "observed_start_state": {"wardrobe": {"minder": "Black Hoodie"}}}
    assert _warnings(impact(wardrobe, takes, "04")) == []
    takes[1] = {"shot": "06"}
    missing_start = impact(wardrobe, takes, "04")
    assert missing_start["status"] == "NOT_COMPUTABLE"
    assert missing_start["code"] == "OBSERVATION_MISSING"
    assert any(item.get("code") == "OBSERVATION_MISSING" for item in _warnings(missing_start))
    both = [
        {"shot": "04", "observed_end_state": {
            "props": {"chair": "C3 far end"}, "wardrobe": {"minder": "black hoodie"},
        }},
        {"shot": "06", "observed_start_state": {
            "props": {"chair": "beside the desk"}, "wardrobe": {"minder": "red hoodie"},
        }},
    ]
    kinds = {str(item["message"]).split()[2] for item in _warnings(impact(_board(), both, "04"))}
    assert kinds == {"prop", "wardrobe"}
    ambiguous = {
        "props": {"chair": {"states": {"C3": "tipped", "C3 far": "farther"}}},
        "frames": [
            {"frame_id": "frame-002", "shot_id": "04", "prop_states": {"chair": "C3"}},
            {"frame_id": "frame-004", "shot_id": "06", "prop_states": {"chair": "C3"}},
        ],
    }
    clash = [{"shot": "04", "observed_end_state": {"props": {"chair": "C3 far end"}}},
             {"shot": "06", "observed_start_state": {"props": {"chair": "C3"}}}]
    assert _warnings(impact(ambiguous, clash, "04"))
    broken = {
        "props": {"chair": {"states": {"C0": "beside the desk", "C3": "tipped"}}},
        "frames": [
            {"frame_id": "frame-002", "shot_id": "04", "prop_states": {"chair": "C3"}},
            {"frame_id": "frame-004", "shot_id": "06", "prop_states": {"chair": "C0"}},
        ],
    }
    refused = impact(broken, _takes(), "04")
    assert refused["status"] == "NOT_COMPUTABLE" and "not reachable" in str(refused["message"])
    assert refused["prep_warnings"] == []
    assert impact(board, _takes(), "99")["status"] == "NOT_COMPUTABLE"
    assert "no take" in str(impact(board, [{"shot": "06"}], "04")["message"])


def test_cli_leaves_the_storyboard_unchanged() -> None:
    plan = EXAMPLE / "storyboard-plan.yaml"
    before = plan.read_bytes()
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "impact.yaml"
        command = [
            PY, str(ROOT / "scripts/kubrick.py"), "storyboard", "--action", "impact",
            "--plan", str(plan), "--takes", str(EXAMPLE / "takes.yaml"),
            "--retake", "04", "--output", str(output),
        ]
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
        assert result.returncode == 0, result.stdout + result.stderr
        written = _as_dict(yaml.safe_load(output.read_text(encoding="utf-8")))
        assert written["status"] == "PROPOSED" and _warnings(written)[0]["message"] == STALE
        missing = subprocess.run(
            [PY, str(ROOT / "scripts/kubrick.py"), "storyboard", "--action", "impact",
             "--storyboard", str(plan), "--takes", str(EXAMPLE / "takes.yaml"), "--retake", "99"],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        assert missing.returncode == 4
        printed = subprocess.run(
            [PY, str(ROOT / "scripts/take_ledger.py"), "--storyboard", str(plan),
             "--takes", str(EXAMPLE / "takes.yaml"), "--retake", "04"],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        assert printed.returncode == 0 and "OBSERVATION" in printed.stdout
    assert plan.read_bytes() == before
    assert impact_main(["--takes", str(EXAMPLE / "takes.yaml"), "--retake", "04"]) == 4
    with tempfile.TemporaryDirectory() as directory:
        bad = Path(directory) / "bad.yaml"
        bad.write_text("[]\n", encoding="utf-8")
        assert impact_main([
            "--plan", str(bad), "--takes", str(EXAMPLE / "takes.yaml"), "--retake", "04",
        ]) == 4


def main() -> None:
    test_router_sends_impact_to_the_ledger()
    test_stale_take_names_the_prop_and_a_match_is_silent()
    test_observations_do_not_overwrite_and_edges_fail_closed()
    test_cli_leaves_the_storyboard_unchanged()
    print("take ledger tests: PASS")


if __name__ == "__main__":
    main()
