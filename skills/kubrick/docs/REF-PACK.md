# Reference pack

`src/kubrick/plan/ref_pack.py` reads `characters.<id>.ref_pack`. It returns
paths and hashes. It does not generate, fetch, or upload an image.

The pack has `asset_hash`, `views`, `head_lock`, and `material_inserts`.
Further stills live on `refs`. Each entry has `path`, `ref_role`, and
`asset_hash`. Roles are `identity`, `material`, `costume_prop`, `location`,
and `layout`. A missing hash or role is `NOT_COMPUTABLE` and the entry is
not emitted.

The resolver picks one mode:

- `refs_only`: no start frame. The pack paths are the references.
- `start_frame`: a start image or a `join.chain_from`. Seedance
  `startImage` and `referenceImages` are mutually exclusive, so the
  references are dropped with `REFS_DROPPED_BY_CHAIN`.
- `first_last`: a start and an end framing. Keyframe `create_movie` has
  `startImage` and no end-image field, so `end_image.supported` is false.
  References are still dropped.

A layout ref on a new angle (`cut: thirty-degree`, `new_angle: true`, or a
changed shot size) warns `LAYOUT_REF_ON_NEW_ANGLE` and is left off the list.

`shared_pack` accepts the same `asset_hash` across movies. A different hash
for the same character is `PACK_SPLIT` / `NOT_COMPUTABLE`. Plans that do not
set `ref_pack` keep the previous reference behavior.
