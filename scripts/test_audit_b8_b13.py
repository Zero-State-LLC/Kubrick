#!/usr/bin/env python3
"""Regression tests for audit bugs B6 and B8–B13 (#53, #55–#60)."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

PY = sys.executable
WRITERS = (
    "propagate_graph_state.py",
    "compare_frame_state.py",
    "build_model_adapter_packet.py",
    "symbolic_ledger.py",
    "graph_operators.py",
    "normalize_visual_observation.py",
    "compare_visual_observation.py",
    "build_visual_correction_packet.py",
    "govern_correction_iteration.py",
    "record_pattern_outcome.py",
    "propose_pattern_evolution.py",
    "extract_forge_signals.py",
    "closed_loop_visual_qa.py",
    "build_motif_graph.py",
    "translate_motif_graph.py",
    "audit_symbolic_structure.py",
    "validate_artifact.py",
    "build_grok_review_bundle.py",
    "generate_design_spec.py",
)


def test_b6_mcp_jsonrpc_errors_keep_serving() -> None:
    requests = "\n".join(
        [
            "{not json",
            json.dumps({"id": 2, "method": "ping"}),
            json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": ["x"]}),
            json.dumps({
                "jsonrpc": "2.0", "id": 4, "method": "tools/call",
                "params": {"name": "kubrick_do", "arguments": "x"},
            }),
            json.dumps({"jsonrpc": "2.0", "id": 5, "method": "ping"}),
            "[]",
        ]
    ) + "\n"
    proc = subprocess.run(
        [PY, str(SCRIPTS / "mcp_kubrick_server.py")],
        input=requests, cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    rows = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    by_id = {row.get("id"): row for row in rows}
    assert by_id[None]["error"]["code"] in {-32700, -32600}
    assert any(row["error"]["code"] == -32700 for row in rows if "error" in row)
    assert by_id[2]["error"]["code"] == -32600
    assert by_id[3]["error"]["code"] == -32602
    assert by_id[4]["error"]["code"] == -32602
    assert by_id[5]["result"] == {}


def test_b8_wizard_action_plan_and_refusal() -> None:
    ok = subprocess.run(
        [
            PY,
            str(SCRIPTS / "kubrick.py"),
            "do",
            "wizard",
            "--action",
            "plan",
            "--preset",
            "verify",
            "--print-only",
        ],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert ok.returncode == 0, ok.stderr
    assert "check" in ok.stdout
    bad = subprocess.run(
        [PY, str(SCRIPTS / "kubrick.py"), "do", "wizard", "--action", "explode"],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert bad.returncode != 0
    assert "unrecognized arguments" not in bad.stderr
    assert "explode" in bad.stderr
    assert "plan" in bad.stderr


def test_b9_observation_missing_and_take_ambiguous() -> None:
    import copy

    from take_ledger import impact

    board = {
        "frames": [
            {"frame_id": "frame-001", "shot_id": "04"},
            {"frame_id": "frame-002", "shot_id": "06"},
        ]
    }
    original = copy.deepcopy(board)
    empty = impact(board, [{"shot": "04", "take_id": "v8"}], "04")
    assert empty["status"] == "NOT_COMPUTABLE"
    assert empty["code"] == "OBSERVATION_MISSING"
    assert board == original
    ambiguous = impact(
        board,
        [
            {"shot": "04", "observed_end_state": {"props": {"chair": "C3"}}},
            {"shot": "04", "observed_end_state": {"props": {"chair": "C4"}}},
        ],
        "04",
    )
    assert ambiguous["code"] == "TAKE_AMBIGUOUS"
    assert ambiguous["status"] == "NOT_COMPUTABLE"
    selected = impact(
        board,
        [
            {
                "shot": "04",
                "selected": False,
                "observed_end_state": {"wardrobe": {"minder": "black"}},
            },
            {
                "shot": "04",
                "selected": True,
                "observed_end_state": {"wardrobe": {"minder": "black"}},
            },
            {"shot": "06", "observed_start_state": {"wardrobe": {"minder": "black"}}},
        ],
        "04",
    )
    assert selected["status"] == "PROPOSED"


def test_b10_budget_cap_unverifiable_when_estimate_missing() -> None:
    from spend_plan import budget_error, stamp_closed

    missing = {"status": "NOT_COMPUTABLE", "total_credits": None}
    assert budget_error(missing, None) is None
    assert budget_error(missing, True) is None
    unverifiable = budget_error(missing, 10)
    assert isinstance(unverifiable, str) and unverifiable.startswith("BUDGET_CAP_UNVERIFIABLE")
    inferred = {"status": "INFERRED", "total_credits": 5}
    assert budget_error(inferred, 10) is None
    exceeded = budget_error(inferred, 4)
    assert isinstance(exceeded, str) and exceeded.startswith("BUDGET_CAP_EXCEEDED")
    stamped = stamp_closed({"status": "NOT_COMPUTABLE"}, unverifiable, {"spend_estimate": missing})
    assert stamped["code"] == "BUDGET_CAP_UNVERIFIABLE"


def test_b11_planned_duration_default_and_warning() -> None:
    from retime_plan import retime
    from shot_plan import collect_prep, duration_warnings, planned_duration

    assert planned_duration({}) == 8.0
    assert planned_duration({"duration_seconds": 6}) == 6.0
    warnings = duration_warnings([{}])
    assert warnings and warnings[0]["code"] == "DURATION_MISSING"
    result = retime({"frames": [{}, {}]}, "generic")
    assert result["script_clock"] == 16 and result["final_clock"] == 16
    raw_warnings = result.get("prep_warnings")
    assert isinstance(raw_warnings, list)
    codes: list[object] = []
    for item in raw_warnings:
        assert isinstance(item, dict)
        codes.append(item.get("code"))
    assert codes == ["DURATION_MISSING", "DURATION_MISSING"]
    prep = collect_prep({}, [{}], "generic")
    assert any(item["code"] == "DURATION_MISSING" for item in prep.warnings)
    drift = (SCRIPTS / "drift_registry.py").read_text(encoding="utf-8")
    assert "planned_duration" in drift
    retime_source = (SCRIPTS / "retime_plan.py").read_text(encoding="utf-8")
    assert "_DEFAULT_SECONDS = 4.0" not in retime_source


def test_b12_takes_answers_and_bounded_writers() -> None:
    from io_safety import (
        PATH_FLAG_NAMES,
        PathSafetyError,
        validate_mcp_tool_args,
        write_text_bounded,
    )
    from manifest_contract import load_manifest

    assert "--takes" in PATH_FLAG_NAMES and "--answers" in PATH_FLAG_NAMES
    intents = load_manifest()["intents"]
    for flag in ("--takes", "--answers"):
        try:
            validate_mcp_tool_args(
                "storyboard",
                "impact",
                [flag, "/etc/passwd"],
                intents=intents,
                root=ROOT,
            )
        except PathSafetyError:
            continue
        raise AssertionError(flag)
    try:
        write_text_bounded(ROOT / "references" / "b12-forbidden.yaml", "nope\n")
    except PathSafetyError:
        pass
    else:
        raise AssertionError("protected write was accepted")
    for name in WRITERS:
        text = (SCRIPTS / name).read_text(encoding="utf-8")
        assert ".write_text(" not in text, name
        assert "write_text_bounded" in text, name
    with tempfile.TemporaryDirectory() as directory:
        board = Path(directory) / "board.json"
        board.write_text('{"frames":[]}', encoding="utf-8")
        target = ROOT / "references" / "b12-forbidden.json"
        proc = subprocess.run(
            [
                PY,
                str(SCRIPTS / "compare_frame_state.py"),
                "--storyboard",
                str(board),
                "--output",
                str(target),
            ],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
    assert proc.returncode != 0
    assert not target.exists()


def test_b13_no_noema_workflows() -> None:
    workflows = ROOT / ".github" / "workflows"
    assert not (workflows / "pin-currency.yml").exists()
    assert not (workflows / "deploy-worker-pin-pr.yml").exists()
    banned = ("spec-compat.json", "workers/noema", "wrangler")
    found = list(workflows.glob("*"))
    assert found
    for path in found:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in banned:
            assert token not in text, (path.name, token)


def test_b12_coverage_output_is_bounded() -> None:
    forbidden = ROOT / "references" / "b12-coverage-forbidden.json"
    if forbidden.exists():
        forbidden.unlink()
    result = subprocess.run(
        [PY, str(SCRIPTS / "audit_corpus_coverage.py"), "--output", str(forbidden)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    try:
        assert result.returncode != 0, result.stdout + result.stderr
        assert not forbidden.exists()
    finally:
        if forbidden.exists():
            forbidden.unlink()
    with tempfile.TemporaryDirectory() as tmp:
        allowed = Path(tmp) / "coverage.json"
        subprocess.run(
            [PY, str(SCRIPTS / "audit_corpus_coverage.py"), "--output", str(allowed)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert allowed.exists()


def test_b12_review_bundle_validates_out_before_copy() -> None:
    import shutil

    import yaml

    forbidden = ROOT / "references" / "b12-bundle-forbidden"
    if forbidden.exists():
        shutil.rmtree(forbidden)
    with tempfile.TemporaryDirectory() as tmp:
        grok = Path(tmp) / "grok.yaml"
        expected = Path(tmp) / "expected.yaml"
        grok.write_text(
            yaml.safe_dump({"validation": {"status": "VALID"}, "source_graph_id": "g1"}),
            encoding="utf-8",
        )
        expected.write_text(
            yaml.safe_dump({"graph_id": "g1", "frames": [{"frame_id": "f1"}]}),
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                PY,
                str(SCRIPTS / "build_grok_review_bundle.py"),
                "--grok-packet",
                str(grok),
                "--expected-state",
                str(expected),
                "--out",
                str(forbidden),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
    try:
        assert result.returncode != 0, result.stdout + result.stderr
        assert not forbidden.exists()
    finally:
        if forbidden.exists():
            shutil.rmtree(forbidden)


def main() -> None:
    test_b6_mcp_jsonrpc_errors_keep_serving()
    test_b8_wizard_action_plan_and_refusal()
    test_b9_observation_missing_and_take_ambiguous()
    test_b10_budget_cap_unverifiable_when_estimate_missing()
    test_b11_planned_duration_default_and_warning()
    test_b12_takes_answers_and_bounded_writers()
    test_b12_coverage_output_is_bounded()
    test_b12_review_bundle_validates_out_before_copy()
    test_b13_no_noema_workflows()
    print("audit B8-B13 tests: PASS")


if __name__ == "__main__":
    main()
