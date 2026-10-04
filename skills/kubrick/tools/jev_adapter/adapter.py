"""Reference Jev. Replays one local fixture. No network and no provider spend."""
from __future__ import annotations

from collections.abc import Mapping, Sequence

_VERDICTS = frozenset({"pass", "fail"})


def _fail(code: str, message: str) -> dict[str, object]:
    return {"verdict": "fail", "findings": [{"code": code, "message": message}]}


def judge_fixture(
    prompt: Mapping[str, object],
    holds: Sequence[Mapping[str, object]],
    fixture: Mapping[str, object],
) -> dict[str, object]:
    """Return the fixture verdict when the prompt matches. Otherwise fail closed."""
    del holds
    expected = fixture.get("expect")
    fixture_prompt = fixture.get("prompt")
    if not isinstance(expected, Mapping) or not isinstance(fixture_prompt, Mapping):
        return _fail("FIXTURE_INVALID", "reference fixture is incomplete")
    verdict = expected.get("verdict")
    findings = expected.get("findings")
    if verdict not in _VERDICTS or not isinstance(findings, list):
        return _fail("FIXTURE_INVALID", "reference fixture verdict is incomplete")
    asked = prompt.get("prompt")
    wanted = fixture_prompt.get("prompt")
    if not isinstance(asked, str) or asked != wanted:
        return _fail("FIXTURE_MISS", "prompt does not match the reference fixture")
    cleaned: list[dict[str, object]] = []
    for item in findings:
        if isinstance(item, Mapping):
            cleaned.append(dict(item))
    return {"verdict": verdict, "findings": cleaned}
