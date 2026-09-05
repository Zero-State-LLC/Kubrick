# Source identity and upgrades

This distribution is `Zero-State-LLC/Kubrick`, version `0.17.1`, based on commit
`4caeecc5f6bf2692f756d09c7771af7b46916cdf` before the local audit-fix commit. Record the actual installed commit
with `git rev-parse HEAD` before installation; do not use a version string alone
as a source identity. Root and hub packaging are distribution surfaces, not a
claim that organizational, personal, or legacy embedded variants are identical.
No personal version is deprecated by this change.

Before switching sources, stop runtime writers, record current source/commit,
review the destination under `${HERMES_HOME:-$HOME/.hermes}`, compare contracts,
and retain a separate backup of outputs, sessions, and local customization.
Do not install two different contracts with the same skill name into one profile.
A successful compatibility check does not grant deployment/publication authority.

The bundled LICENSE controls this distribution. No license grant is changed by
these fixes; earlier grants and third-party notices remain intact.
