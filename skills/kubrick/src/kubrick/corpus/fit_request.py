"""Request a judge sees when recording retrieval fit verdicts (#91, 0.27.10).

The question asks about dramatic structure, with generic counter-examples of
briefs that share a pattern's words but not its structure. Nothing here names
a tenant, a fixture brief, or a specific pattern.
"""

from __future__ import annotations

from collections.abc import Mapping

STORY_FIELDS = ("dramatic_problem", "desired_state_change", "character_pressure", "symbolic_intent")

TASK = (
    "Second-opinion dramatic fit for a film-pattern retrieval system. For each pattern, "
    "decide whether its dramatic structure is what happens in the brief. Most briefs fit "
    "only a few patterns; many briefs fit none."
)

COUNTER_EXAMPLES = (
    "Shared words are not fit. These are NONE even though the words overlap: "
    "(1) a weather report that says 'pressure builds and the front collapses' does not fit a "
    "pattern about social pressure collapsing a group; "
    "(2) a product manual that says 'transfer access to the new owner' does not fit a pattern "
    "about power passing between people; "
    "(3) a list of abstract nouns or genre terms with no people, action, or change of state "
    "fits nothing; "
    "(4) a brief about an everyday mishap that borrows dramatic words ('hidden cause', "
    "'consequence') fits only if the pattern's structure, not its vocabulary, is present."
)

CRITERIA = {
    "fit": (
        "the brief has people or agents, an action, and a change of state, and the pattern's "
        "structure is how that change happens"
    ),
    "weak": "one structural element matches but the core mechanism does not",
    "none": "unrelated, only shares words or theme, or the brief has no dramatic situation",
}


def _summary(pattern: Mapping[str, object]) -> dict[str, object]:
    operations = pattern.get("dramatic_operations")
    ops = list(operations)[:4] if isinstance(operations, list) else []
    return {
        "title": pattern.get("title"),
        "transferable_structure": pattern.get("transferable_structure"),
        "dramatic_operations": ops,
    }


def build_fit_request(
    brief: Mapping[str, object], patterns: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    """``{state, questions}`` for one brief: one fit/weak/none choice per pattern id."""
    import json

    story = {field: brief[field] for field in STORY_FIELDS if brief.get(field)}
    questions: dict[str, object] = {}
    for pattern_id in sorted(patterns):
        summary = json.dumps(_summary(patterns[pattern_id]), sort_keys=True)
        questions[pattern_id] = {
            "type": "choice",
            "instructions": (
                f"Does the dramatic structure of pattern '{pattern_id}' happen in this brief? "
                f"Apply the counter_examples in the state. Pattern: {summary}"
            ),
            "criteria": dict(CRITERIA),
        }
    state = {"brief": story, "task": TASK, "counter_examples": COUNTER_EXAMPLES}
    return {"state": state, "questions": questions}
