# Jev fit recording request (0.27.10)

One live Jev text call per fixture brief. `state`:

```json
{
  "brief": "<dramatic_problem, desired_state_change, character_pressure, symbolic_intent when present>",
  "task": "Second-opinion dramatic fit for a film-pattern retrieval system. One verdict per pattern."
}
```

One `choice` question per pattern id, keyed by the id:

```json
{
  "type": "choice",
  "instructions": "Does the pattern '<id>' fit the dramatic situation of this brief? Judge the story itself, not shared words. Pattern: {title, transferable_structure, first 4 dramatic_operations}",
  "criteria": {
    "fit": "the pattern's structure is what happens in this brief",
    "weak": "partly related, or only one element matches",
    "none": "unrelated, or only shares vocabulary"
  }
}
```
