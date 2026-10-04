# Scoped holds

A hold applies to every prompt until it names a scope. `scope.locations`,
`scope.shots`, and `scope.characters` keep it off prompts that do not match.
`views` of `front`, `rear`, or `pov` do the same for camera view.

A prop lock stops at a location change, and a prop with `locations` is absent
outside that list. The chair lock stays on the chair's location and is left
out of alley and rooftop prompts.

A rear-view frame for a back-light hold carries the explicit rear sentence
(`seen from behind there is NO visible light…`), including an object-relative
`anchor` such as the figure's right lens. A POV frame does not receive
wardrobe or asymmetry lines.

Jev can return one row per hold: `hold_id`, `present`, `located`, and
`strong`. A weak hold fails on its own. The other holds in that payload can
pass. A recorded sample whose `p` is from 0.4 through 0.6 is drawn again, up
to three times, and does not become a pass. The judge still sends the
applicable holds in one call. The HTTP timeout stays the client timeout.
