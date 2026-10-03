"""Per-file lint ratchet: ruff/mypy counts may only go down."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "scripts" / "lint_baseline.json"
SCHEMA_VERSION = "1.0.0"
TOOLS = ("ruff", "mypy")
MYPY_LINE = re.compile(r"^(scripts/[^:]+\.py):\d+(?::\d+)?: error:")

Counts = dict[str, dict[str, int]]


class ToolMissing(RuntimeError):
    """Raised when a lint tool is not installed."""


def _relative_key(filename: str) -> str:
    path = Path(filename)
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def ruff_counts(raw_json: str) -> dict[str, int]:
    data: object = json.loads(raw_json) if raw_json.strip() else []
    if not isinstance(data, list):
        raise ValueError("ruff output must be a JSON list")
    counter: Counter[str] = Counter()
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("filename"), str):
            counter[_relative_key(item["filename"])] += 1
    return dict(sorted(counter.items()))


def mypy_counts(text: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for line in text.splitlines():
        match = MYPY_LINE.match(line.strip())
        if match:
            counter[match.group(1)] += 1
    return dict(sorted(counter.items()))


def compare(baseline: Counts, current: Counts) -> tuple[list[str], list[str]]:
    regressions: list[str] = []
    tightenings: list[str] = []
    for tool in TOOLS:
        base = baseline.get(tool, {})
        cur = current.get(tool, {})
        for name in sorted(set(base) | set(cur)):
            now, was = cur.get(name, 0), base.get(name, 0)
            if now > was:
                regressions.append(f"RATCHET FAIL {tool} {name}: {now} > {was}")
            elif now < was:
                tightenings.append(f"RATCHET TIGHTEN {tool} {name}: {now} < {was}")
    return regressions, tightenings


def _run(module: str, args: list[str]) -> str:
    proc = subprocess.run(
        [sys.executable, "-m", module, *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = proc.stdout + proc.stderr
    if proc.returncode != 0 and f"No module named {module}" in combined:
        raise ToolMissing(f"{module} is not installed")
    return proc.stdout


def collect_ruff() -> dict[str, int]:
    out = _run("ruff", ["check", "scripts", "--output-format", "json", "--exit-zero"])
    return ruff_counts(out)


def collect_mypy() -> dict[str, int]:
    files = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "scripts").glob("*.py"))
    args = [
        "--follow-imports=skip",
        "--ignore-missing-imports",
        "--no-error-summary",
        "--hide-error-context",
        *files,
    ]
    return mypy_counts(_run("mypy", args))


def _positive(counts: dict[str, int]) -> dict[str, int]:
    return {key: counts[key] for key in sorted(counts) if counts[key] > 0}


def load_baseline(path: Path) -> Counts:
    data: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping")
    result: Counts = {}
    for tool in TOOLS:
        section = data.get(tool, {})
        if not isinstance(section, dict):
            raise ValueError(f"{path}: {tool} must be a mapping")
        result[tool] = {
            str(k): v for k, v in section.items() if isinstance(v, int) and not isinstance(v, bool)
        }
    return result


def write_baseline(path: Path, current: Counts) -> None:
    payload: dict[str, object] = {"schema_version": SCHEMA_VERSION}
    for tool in TOOLS:
        payload[tool] = _positive(current.get(tool, {}))
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true", help="rewrite the baseline")
    args = parser.parse_args(argv)
    try:
        current: Counts = {"ruff": collect_ruff(), "mypy": collect_mypy()}
    except ToolMissing as exc:
        print(f"lint ratchet: {exc}", file=sys.stderr)
        return 3
    if args.update:
        write_baseline(BASELINE, current)
        print(f"lint ratchet: baseline written to {BASELINE.relative_to(ROOT).as_posix()}")
        return 0
    if not BASELINE.is_file():
        print("lint ratchet: baseline missing; run with --update", file=sys.stderr)
        return 2
    baseline = load_baseline(BASELINE)
    regressions, tightenings = compare(baseline, current)
    for line in tightenings:
        print(line)
    if regressions:
        for line in regressions:
            print(line)
        return 1
    tracked = sum(len(baseline.get(tool, {})) for tool in TOOLS)
    print(f"lint ratchet: PASS ({tracked} files tracked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
