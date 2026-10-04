#!/usr/bin/env python3
"""Normalize manual or generic observer JSON into Kubrick visual-observation format."""
from __future__ import annotations

import argparse
import hashlib
import json

from kubrick.runtime.io_safety import write_text_bounded

try:
    import yaml
except ImportError:
    raise SystemExit("pyyaml required")
from kubrick.runtime.structured_io import load_mapping


def load(path):
    """Shared loader; untyped legacy callers keep their contract."""
    return load_mapping(path)


def main():
    p=argparse.ArgumentParser(); p.add_argument("--input",required=True); p.add_argument("--source-graph-id",required=True); p.add_argument("--frame-id",required=True); p.add_argument("--observer",default="human"); p.add_argument("--method",choices=["manual","generic-json","grok-vision"],default="manual"); p.add_argument("--model"); p.add_argument("--confidence",type=float,default=1.0); p.add_argument("--output",required=True); a=p.parse_args()
    raw=load(a.input); observed=raw.get("observed",raw)
    normalized={"geometry":list(observed.get("geometry",[])),"node_states":dict(observed.get("node_states",observed.get("states",{}))),"motif_ownership":dict(observed.get("motif_ownership",observed.get("ownership",{}))),"object_states":dict(observed.get("object_states",observed.get("objects",{}))),"light_states":dict(observed.get("light_states",observed.get("lighting",{}))),"material_states":dict(observed.get("material_states",observed.get("materials",{}))),"residue":list(observed.get("residue",[])),"convergence_sites":list(observed.get("convergence_sites",observed.get("convergence",[])))}
    payload={"schema_version":"1.0.0","source_graph_id":a.source_graph_id,"frame_id":a.frame_id,"observed":normalized,"confidence":max(0,min(1,a.confidence)),"ambiguities":list(raw.get("ambiguities",[])),"provenance":{"observer":a.observer,"method":a.method,"model":a.model}}
    payload["observation_id"]=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()[:16]
    text=yaml.safe_dump(payload,sort_keys=False); write_text_bounded(a.output, text); print(text)
if __name__=="__main__": main()
