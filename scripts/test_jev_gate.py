#!/usr/bin/env python3
"""Jev pre-spend gate. Issue #90. Recorded verdicts only; no live Jev call."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "evals" / "fixtures" / "jev"
sys.path.insert(0, str(SCRIPTS))

from io_safety import load_structured  # noqa: E402
from jev_client import (  # noqa: E402
    HttpJevClient,
    JevUnreachable,
    RecordedJev,
    post_json,
    verdict_key,
)
from jev_gate import append_run_ledger, check_before_spend  # noqa: E402
from jev_holds import compiled_prompts, hold_list  # noqa: E402

MYSLEF = ROOT / "examples" / "myslef-minder" / "storyboard-plan.yaml"
_JEV_ENV = ("KUBRICK_JEV_URL", "KUBRICK_JEV_VERDICTS", "KUBRICK_JEV_OVERRIDE")


def _load(name: str) -> dict[str, object]:
    raw = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def _map(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value


def _rows(value: object) -> list[dict[str, object]]:
    assert isinstance(value, list)
    rows: list[dict[str, object]] = []
    for item in value:
        assert isinstance(item, dict)
        rows.append(item)
    return rows


def _prompt(raw: Mapping[str, object]) -> dict[str, object]:
    return {
        "shot": raw["shot"],
        "channel": raw.get("channel", "keyframe"),
        "surfaces": raw.get("surfaces", ["image", "video"]),
        "location": raw.get("location", "plan"),
        "prompt": raw["prompt"],
    }


def _recorded(
    prompts: Sequence[Mapping[str, object]],
    holds: Sequence[Mapping[str, object]],
    verdicts: Sequence[Mapping[str, object]],
) -> RecordedJev:
    stored: dict[str, Mapping[str, object]] = {}
    assert len(prompts) == len(verdicts)
    for prompt, spec in zip(prompts, verdicts):
        stored[verdict_key(prompt, holds)] = {
            "verdict": spec["verdict"],
            "findings": spec.get("findings") or [],
        }
    return RecordedJev(stored)


def _holds(raw: object) -> list[dict[str, object]]:
    return _rows(raw)


class _Down:
    def judge(
        self, prompt: Mapping[str, object], holds: Sequence[Mapping[str, object]],
    ) -> Mapping[str, object]:
        raise JevUnreachable("connection refused")


def test_hold_hit_blocks_and_reports_why() -> None:
    fixture = _load("hold-hit.json")
    assert isinstance(fixture["prompt"], dict)
    holds = _holds(fixture["holds"])
    prompt = _prompt(fixture["prompt"])
    client = _recorded([prompt], holds, [{
        "verdict": fixture["verdict"],
        "findings": fixture["findings"],
    }])
    gate = check_before_spend(holds, [prompt], client=client)
    assert gate["blocks_spend"] is True
    assert gate["code"] == "JEV_HOLD"
    assert gate["checked_before_spend"] is True
    assert "BRAND_PRONE" in str(gate["message"])
    assert "Nike swoosh" in str(gate["message"])
    assert "spend_estimate" not in gate
    assert client.seen_hold_ids == [["brand"]]


def test_clean_prompt_allows_spend() -> None:
    fixture = _load("clean-prompt.json")
    assert isinstance(fixture["prompt"], dict)
    holds = _holds(fixture["holds"])
    prompt = _prompt(fixture["prompt"])
    client = _recorded([prompt], holds, [{
        "verdict": fixture["verdict"],
        "findings": fixture["findings"],
    }])
    gate = check_before_spend(holds, [prompt], client=client)
    assert gate["blocks_spend"] is False
    assert gate["code"] == "CLEAR"
    assert gate["status"] == "PASS"


def test_jev_down_fails_closed_unless_override_is_logged() -> None:
    fixture = _load("jev-down.json")
    assert isinstance(fixture["prompt"], dict)
    holds = _holds(fixture["holds"])
    prompts = [_prompt(fixture["prompt"])]
    blocked = check_before_spend(holds, prompts, client=_Down())
    assert blocked["blocks_spend"] is True
    assert blocked["code"] == "JEV_UNREACHABLE"
    assert blocked["override_logged"] is False
    assert "connection refused" in str(blocked["message"])
    logged: list[dict[str, object]] = []
    allowed = check_before_spend(
        holds, prompts, client=_Down(), override=True, override_source="flag",
        log=lambda record: logged.append(dict(record)),
    )
    assert allowed["blocks_spend"] is False
    assert allowed["code"] == "JEV_OVERRIDE"
    assert allowed["override_logged"] is True
    assert logged and logged[0]["event"] == "JEV_OVERRIDE"
    assert logged[0]["source"] == "flag"
    still = check_before_spend(
        holds, prompts, client=_recorded(prompts, holds, [{
            "verdict": "fail",
            "findings": [{
                "code": "MISSING_LOCK",
                "hold_id": "red-chest-light",
                "message": "red chest LED lock is missing",
            }],
        }]),
        override=True,
        override_source="flag",
    )
    assert still["blocks_spend"] is True
    assert still["code"] == "JEV_HOLD"
    assert still["override_logged"] is False
    assert "does not bypass" in str(still["message"])


def test_myslef_v023_fails_and_hand_fixed_passes() -> None:
    plan = load_structured(MYSLEF)
    assert isinstance(plan, dict)
    holds = hold_list(plan)
    assert isinstance(holds, list)
    assert "red-chest-light" in {item["id"] for item in holds}
    assert any(item["kind"] == "location" for item in holds)
    assert any(str(item["id"]).startswith("prop-chair-") for item in holds)
    compiled = compiled_prompts(plan, "keyframe")
    assert isinstance(compiled, list)
    recorded = _load("myslef-v023.json")
    shots = _rows(recorded["shots"])
    assert [item["shot"] for item in compiled] == [item["shot"] for item in shots]
    for live, saved in zip(compiled, shots):
        assert live["prompt"] == saved["prompt"]
        assert "no red light on the head or chest" not in str(live["prompt"])
        assert live["surfaces"] == ["image", "video"]
    client = _recorded(compiled, holds, shots)
    failed = check_before_spend(holds, compiled, client=client)
    assert failed["blocks_spend"] is True
    assert failed["code"] == "JEV_HOLD"
    assert failed["checks"] and all(
        item["verdict"] == "fail" for item in _rows(failed["checks"])
    )
    assert "red-chest-light" in client.seen_hold_ids[0]
    fixed = _rows(_load("myslef-hand-fixed.json")["shots"])
    for shot in fixed:
        if shot["location"] == "alley":
            assert "CHAIR LOCK" not in str(shot["prompt"])
        else:
            assert str(shot["prompt"]).startswith("no red light on the head or chest")
    fixed_prompts = [_prompt(shot) for shot in fixed]
    passed = check_before_spend(
        holds, fixed_prompts, client=_recorded(fixed_prompts, holds, fixed),
    )
    assert passed["blocks_spend"] is False
    assert passed["code"] == "CLEAR"


def test_run_ledger_records_the_gate_before_spend() -> None:
    fixture = _load("clean-prompt.json")
    assert isinstance(fixture["prompt"], dict)
    holds = _holds(fixture["holds"])
    prompt = _prompt(fixture["prompt"])
    gate = check_before_spend(
        holds,
        [prompt],
        client=_recorded([prompt], holds, [{"verdict": "pass", "findings": []}]),
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "run-ledger.json")
        append_run_ledger(path, {"kind": "jev_gate", "checked_before_spend": True, "result": gate})
        saved = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = _rows(saved["entries"])
    assert entries[0]["kind"] == "jev_gate"
    assert entries[0]["checked_before_spend"] is True
    assert _map(entries[0]["result"])["code"] == "CLEAR"


def test_http_client_reports_a_hold_and_a_down_endpoint() -> None:
    seen: dict[str, object] = {}

    def transport(url: str, body: Mapping[str, object], timeout: float) -> object:
        seen["url"] = url
        seen["holds"] = body["holds"]
        return {
            "verdict": "fail",
            "findings": [{
                "code": "BRAND_PRONE",
                "hold_id": "brand",
                "message": "Nike swoosh is brand-prone wording",
            }],
        }

    client = HttpJevClient("https://jev.example/judge", transport=transport)
    verdict = client.judge(
        {
            "shot": "still-01",
            "channel": "keyframe",
            "surfaces": ["image"],
            "location": "alley",
            "prompt": "swoosh",
        },
        [{"id": "brand"}],
    )
    assert verdict["verdict"] == "fail"
    assert seen["url"] == "https://jev.example/judge"
    try:
        post_json("file:///tmp/jev", {}, 1.0)
    except JevUnreachable as exc:
        assert "http" in exc.reason
    else:
        raise AssertionError("file URL must fail closed")


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in _JEV_ENV:
        env.pop(key, None)
    return env


def _run(
    script: str, plan: Mapping[str, object], *extra: str,
) -> tuple[int, dict[str, object], str]:
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        source = folder / "plan.json"
        out = folder / "out.json"
        source.write_text(json.dumps(plan), encoding="utf-8")
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / script),
                "--input",
                str(source),
                "--provider",
                "keyframe",
                "--output",
                str(out),
                *extra,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            env=_clean_env(),
        )
        data = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        return proc.returncode, data, proc.stderr


def _locked_plan() -> dict[str, object]:
    return {
        "frames": [
            {
                "frame_id": "f1",
                "shot_id": "01",
                "duration_seconds": 4,
                "speech_lines": ["minder: Hi there"],
            },
            {"frame_id": "f2", "shot_id": "02", "duration_seconds": 4},
        ],
        "characters": {"minder": {"voice": {"speaks": True, "library_id": "lib-1"}}},
        "locks": [{
            "id": "red-chest-light",
            "kind": "light",
            "critical": True,
            "negative": "no red light on the head or chest",
        }],
    }


def _verdict_file(plan: Mapping[str, object], verdict: str) -> str:
    compiled = compiled_prompts(plan, "keyframe")
    holds = hold_list(plan)
    assert isinstance(compiled, list)
    assert isinstance(holds, list)
    payload = {
        "verdicts": {
            verdict_key(item, holds): {
                "verdict": verdict,
                "findings": [] if verdict == "pass" else [{
                    "code": "MISSING_LOCK",
                    "hold_id": "red-chest-light",
                    "message": "red chest LED lock is missing from the compiled prompt",
                }],
            }
            for item in compiled
        }
    }
    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(payload, handle)
    handle.close()
    return handle.name


def test_runbook_and_cues_block_before_spend() -> None:
    plan = _locked_plan()
    code, data, _err = _run("video_runbook.py", plan)
    assert code == 4
    assert data["code"] == "JEV_UNREACHABLE"
    assert "ops" not in data
    assert "spend_estimate" not in data
    assert _map(data["jev_gate"])["checked_before_spend"] is True
    assert _rows(data["run_ledger"])[0]["kind"] == "jev_gate"
    code, data, err = _run("video_runbook.py", plan, "--jev-override")
    assert code == 0, err
    assert data["status"] == "PROPOSED"
    assert _rows(data["ops"])[0]["op"] == "regenerate"
    assert _map(data["jev_gate"])["code"] == "JEV_OVERRIDE"
    assert "JEV_OVERRIDE" in err
    failing = _verdict_file(plan, "fail")
    try:
        code, data, err = _run(
            "video_runbook.py", plan, "--jev-verdicts", failing, "--jev-override",
        )
    finally:
        Path(failing).unlink(missing_ok=True)
    assert code == 4
    assert data["code"] == "JEV_HOLD"
    assert "ops" not in data
    assert "JEV_OVERRIDE" not in err
    passing = _verdict_file(plan, "pass")
    try:
        code, passed, _err = _run("video_runbook.py", plan, "--jev-verdicts", passing)
    finally:
        Path(passing).unlink(missing_ok=True)
    assert code == 0
    assert _map(passed["jev_gate"])["code"] == "CLEAR"
    assert "spend_estimate" in passed
    cue_code, cues, _err = _run("video_cues.py", plan)
    assert cue_code == 4
    assert cues["code"] == "JEV_UNREACHABLE"
    assert "elevenlabs_estimate" not in cues
    allowed_code, allowed, err = _run("video_cues.py", plan, "--jev-override")
    assert allowed_code == 0, err
    assert _map(allowed["elevenlabs_estimate"])["label"] == "INFERRED"
    assert _rows(allowed["run_ledger"])[0]["checked_before_spend"] is True


def main() -> None:
    test_hold_hit_blocks_and_reports_why()
    test_clean_prompt_allows_spend()
    test_jev_down_fails_closed_unless_override_is_logged()
    test_myslef_v023_fails_and_hand_fixed_passes()
    test_run_ledger_records_the_gate_before_spend()
    test_http_client_reports_a_hold_and_a_down_endpoint()
    test_runbook_and_cues_block_before_spend()
    print("jev pre-spend gate tests: PASS")


if __name__ == "__main__":
    main()
