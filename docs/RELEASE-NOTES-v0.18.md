# Kubrick v0.18.0 Release Notes

v0.18.0 fixes prompt fidelity for storyboard shots and adds a Keyframe
`create_movie` adapter. The production envelope schema id stays `0.16.0`.

## Fixes

- Product version surfaces are audited together. Installers run the strict
  release audit before activation, so `VERSION` and `kubrick.manifest.yaml`
  cannot drift apart the way they did in the installed 0.17.0 skill.
- `compile` declares PyYAML and jsonschema as runtime dependencies and exits 3
  with `python3 -m pip install -r requirements.txt` when jsonschema is missing.
- The same noun may appear in more than one brief layer. A verbatim multi-word
  phrase copied across layers still fails, and the error names the phrase and
  both layers.
- Per-shot prompts are built from each storyboard frame. Observed ids render as
  evidence text. Blank and `None` values are omitted. Ownership labels render
  as `motif ownership`.
- General negatives stay in the negative field. Repeated clauses collapse in
  order. Character-lock negatives are also restated as positive identity
  constraints. Briefs pass those locks through `character_locks` or a
  `character-lock:` / `identity-lock:` production constraint.
- The `keyframe` provider emits `create_movie`. Each shot is 3–60 seconds
  inclusive. Speech is omitted when a shot has no dialogue. Grok Imagine
  remains capped at 8 seconds. Aspect ratio follows an `N:M` token in the
  brief, and optional storyboard duration, title, scene, sound, and speech
  lines pass through to each shot.
