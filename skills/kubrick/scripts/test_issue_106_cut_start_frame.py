#!/usr/bin/env python3
"""Issue #106: cut must not inherit a previous start_frame lock carrier.

Offline. No paid call. Authored by qwen/qwen3-coder via OpenRouter.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from lock_carriers import carrier_for  # noqa: E402

HANDS = {"id": "silicon-hands", "kind": "material", "text": "silicon hands", "critical": True}

def test_join_cut_with_source_shot_inherited_start_frame_no_carrier() -> None:
    """Issue #106 Acceptance 1: join: 'cut' with start_frame that has source_shot 
    (inherited from previous) does NOT get carrier == 'start_frame'."""
    document = {"locks": [HANDS]}
    frame = {
        "frame_id": "test-frame",
        "join": "cut",
        "start_frame": {"asset": "prev_asset.png", "source_shot": "previous_shot"}
    }
    result = carrier_for(document, frame, "material", "silicon hands", None, HANDS)
    assert result["carrier"] != "start_frame"

def test_join_cut_with_inherited_true_start_frame_no_carrier() -> None:
    """Issue #106 Acceptance 2: join: 'cut' with start_frame inherited: true 
    does NOT get carrier == 'start_frame'."""
    document = {"locks": [HANDS]}
    frame = {
        "frame_id": "test-frame",
        "join": "cut",
        "start_frame": {"asset": "prev_asset.png", "inherited": True}
    }
    result = carrier_for(document, frame, "material", "silicon hands", None, HANDS)
    assert result["carrier"] != "start_frame"

def test_join_cut_with_source_shot_inherited_no_carrier() -> None:
    """Issue #106 Acceptance 3: join: {type: 'cut'} with source_shot inherited 
    start does NOT get carrier == 'start_frame'."""
    document = {"locks": [HANDS]}
    frame = {
        "frame_id": "test-frame",
        "join": {"type": "cut"},
        "start_frame": {"asset": "prev_asset.png", "source_shot": "previous_shot"}
    }
    result = carrier_for(document, frame, "material", "silicon hands", None, HANDS)
    assert result["carrier"] != "start_frame"

def test_join_chain_with_board_evidence_still_can_carrier() -> None:
    """Issue #106 Acceptance 4: join: {chain_from: 'prev'} with verified board_evidence 
    STILL can get carrier == 'start_frame'."""
    document = {"locks": [HANDS]}
    frame = {
        "frame_id": "test-frame",
        "join": {"chain_from": "prev"},
        "board_evidence": [{"lock_id": "silicon-hands", "status": "verified"}],
        "start_frame": {"asset": "prev_asset.png", "source_shot": "previous_shot"}
    }
    result = carrier_for(document, frame, "material", "silicon hands", None, HANDS)
    assert result["carrier"] == "start_frame"
    assert result["status"] == "verified"

def test_cut_vs_chain_same_lock_distinct_carriers() -> None:
    """Issue #106 Acceptance 5: The cut case and the chain case have distinct 
    carrier values for the same lock."""
    document = {"locks": [HANDS]}
    
    cut_frame = {
        "frame_id": "cut-frame",
        "join": "cut",
        "board_evidence": [{"lock_id": "silicon-hands", "status": "verified"}],
        "start_frame": {"asset": "prev_asset.png", "source_shot": "previous_shot"}
    }
    
    chain_frame = {
        "frame_id": "chain-frame",
        "join": {"chain_from": "prev"},
        "board_evidence": [{"lock_id": "silicon-hands", "status": "verified"}],
        "start_frame": {"asset": "prev_asset.png", "source_shot": "previous_shot"}
    }
    
    cut_result = carrier_for(document, cut_frame, "material", "silicon hands", None, HANDS)
    chain_result = carrier_for(document, chain_frame, "material", "silicon hands", None, HANDS)
    
    assert cut_result["carrier"] != chain_result["carrier"]

def test_cut_non_inherited_start_frame_may_use_carrier() -> None:
    """Issue #106 Acceptance 6: A cut with its own non-inherited start_frame 
    (asset only, no source_shot, inherited not true) MAY still use start_frame 
    as carrier when board_evidence verifies the lock."""
    document = {"locks": [HANDS]}
    frame = {
        "frame_id": "test-frame",
        "join": "cut",
        "start_frame": {"asset": "own_asset.png"},
        "board_evidence": [{"lock_id": "silicon-hands", "status": "verified"}]
    }
    result = carrier_for(document, frame, "material", "silicon hands", None, HANDS)
    assert result["carrier"] == "start_frame"
    assert result["status"] == "verified"

if __name__ == "__main__":
    test_join_cut_with_source_shot_inherited_start_frame_no_carrier()
    test_join_cut_with_inherited_true_start_frame_no_carrier()
    test_join_cut_with_source_shot_inherited_no_carrier()
    test_join_chain_with_board_evidence_still_can_carrier()
    test_cut_vs_chain_same_lock_distinct_carriers()
    test_cut_non_inherited_start_frame_may_use_carrier()
    print("PASS")
