#!/usr/bin/env python3
"""Validate one Kubrick YAML/JSON artifact against a repository schema."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from io_safety import write_text_bounded

_INSTALL = "python3 -m pip install -r requirements.txt"
try:
    from jsonschema import Draft202012Validator
except ImportError:
    raise SystemExit(f"jsonschema required. Install runtime dependencies: {_INSTALL}")
from structured_io import load_mapping as load


def render_path(path) -> str:
    parts=[]
    for item in path:
        parts.append(f"[{item}]" if isinstance(item,int) else (("." if parts else "")+str(item)))
    return "".join(parts) or "$"


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--artifact",required=True)
    p.add_argument("--schema",required=True)
    p.add_argument("--output")
    a=p.parse_args()
    artifact=load(Path(a.artifact)); schema=load(Path(a.schema))
    validator=Draft202012Validator(schema)
    errors=[]
    for error in sorted(validator.iter_errors(artifact), key=lambda e:list(e.absolute_path)):
        errors.append({"path":render_path(error.absolute_path),"message":error.message,"validator":error.validator})
    result={"status":"VALID" if not errors else "INVALID","artifact":a.artifact,"schema":a.schema,"error_count":len(errors),"errors":errors}
    text=json.dumps(result,indent=2)
    if a.output: write_text_bounded(a.output, text)
    print(text)
    raise SystemExit(0 if not errors else 1)

if __name__=="__main__": main()
