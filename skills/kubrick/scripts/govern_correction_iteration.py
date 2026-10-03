#!/usr/bin/env python3
"""Compare fidelity reports and govern bounded correction-loop continuation."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys

import diagnostics
from io_safety import write_text_bounded

try:
    import yaml
except ImportError:
    raise SystemExit("pyyaml required")
from structured_io import load_mapping as load


def score_map(report): return {k:float(v.get("score",0)) for k,v in report.get("dimensions",{}).items() if isinstance(v,dict)}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--current",required=True); p.add_argument("--previous"); p.add_argument("--iteration",type=int,required=True); p.add_argument("--max-iterations",type=int,default=3); p.add_argument("--output",required=True); a=p.parse_args()
    current=load(a.current); previous=load(a.previous) if a.previous else None
    if current.get("overall_status")=="NOT_COMPUTABLE":
        diagnostics.abort(diagnostics.diagnostic(status="NOT_COMPUTABLE",code="FIDELITY_NOT_COMPUTABLE",exit_code=4,
            message="current fidelity report is NOT_COMPUTABLE; correction iteration cannot be governed",
            context={"current":a.current}),stream=sys.stderr)
    cur=score_map(current); prev=score_map(previous) if previous else {}
    improved=sorted(k for k,v in cur.items() if k in prev and v>prev[k]+1e-9)
    regressed=sorted(k for k,v in cur.items() if k in prev and v<prev[k]-1e-9)
    unchanged=sorted(k for k,v in cur.items() if v<0.9 and (k not in prev or abs(v-prev[k])<=1e-9))
    reasons=[]
    if current.get("overall_status")=="PASS": decision="PASS"
    elif regressed and any(k in {"state","ownership","residue","convergence","continuity"} for k in regressed): decision="STOP_REGRESSION"; reasons.append("critical passing dimension regressed")
    elif a.iteration>=a.max_iterations: decision="STOP_LIMIT"; reasons.append("maximum correction iterations reached")
    elif previous and not improved: decision="STOP_NO_PROGRESS"; reasons.append("no fidelity dimension improved")
    elif unchanged and a.iteration>=2: decision="HUMAN_REVIEW"; reasons.append("persistent failures require operator judgment")
    else: decision="CONTINUE"
    payload={"schema_version":"1.0.0","source_graph_id":current.get("source_graph_id","unknown"),"frame_id":current.get("frame_id","unknown"),"previous_report_id":previous.get("report_id") if previous else None,"current_report_id":current.get("report_id","unknown"),"iteration":a.iteration,"max_iterations":a.max_iterations,"improved":improved,"regressed":regressed,"unchanged_failures":unchanged,"decision":decision,"reason_vector":reasons}
    payload["iteration_id"]=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()[:16]
    text=yaml.safe_dump(payload,sort_keys=False); write_text_bounded(a.output, text); print(text); raise SystemExit(0 if decision in {"PASS","CONTINUE"} else 2)
if __name__=="__main__": main()
