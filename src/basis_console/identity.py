"""Identity & Access Explorer presentation models and SAMPLE data (Phase 8).

WHAT THIS MODULE IS
───────────────────
This module provides the *presentation-oriented* data the Identity & Access
Explorer page renders: a normalized BASIS subject, a read-only token/claims
preview, the claim→subject mapping the gateway would perform, and a clearly
labelled list of capabilities a future ``basis-identity`` repository will own.

Everything here is console-owned and display-only. The structures are named
``*Preview`` deliberately: they describe what the console *shows*, not what any
component *does*.

WHAT THIS MODULE IS NOT
───────────────────────
The console does not authenticate, authorize, evaluate policy, or implement any
identity protocol. Accordingly this module:

  - does **not** verify tokens or signatures (verification belongs to
    ``basis-gateway``);
  - does **not** implement OIDC / OAuth / SAML / SCIM / JWKS — it only *renders*
    representations of such data, hence the avoidance of names like
    ``OidcProvider`` / ``SamlService`` / ``ScimEngine`` / ``OAuthServer``;
  - does **not** import ``basis-core`` or reach the kernel;
  - does **not** call ``basis-gateway`` to populate this page. The data below is
    SAMPLE/demo data, labelled as such in the UI.

FUTURE INTEGRATION
──────────────────
The future ``basis-identity`` repository will own identity lifecycle and
federation (external IdP integration, claim mapping, subject normalization,
access review). The relationship is one-way and enforced by the gateway:

    External IdP → basis-identity → basis-gateway → basis-core

    basis-console observes and operates the flow; it owns none of it.

When ``basis-identity`` (and a future ``basis-schemas``) land, the SAMPLE
builders here should be replaced with data sourced through the gateway — the
presentation models can stay, but they must never become an identity provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Notice surfaced on the Identity & Access page so an operator is never misled
# into thinking the console is showing live, verified identity state. The console
# consumes no live identity APIs yet and never verifies tokens.
IDENTITY_SAMPLE_NOTICE = (
    "Sample identity data — illustrative only. The console does not authenticate, "
    "verify tokens, or call an identity provider. Live, verified subject context "
    "will be derived by basis-gateway (and the future basis-identity service) and "
    "rendered here in a later phase."
)

# Short statement of the identity boundary, shown near the top of the page.
IDENTITY_BOUNDARY_NOTICE = (
    "The console renders, inspects, and explains identity and access context — it "
    "does not authenticate, authorize, evaluate policy, or call basis-core. Token "
    "verification and subject normalization belong to basis-gateway; identity "
    "lifecycle and federation will belong to the future basis-identity service."
)


@dataclass(frozen=True)
class ClaimPreview:
    """A read-only view of a token's claims. The console NEVER verifies tokens.

    ``raw`` is the (possibly nested) decoded claim set shown verbatim for
    inspection. ``issuer`` / ``audience`` / ``expires_at`` are pulled out for a
    quick summary. None of this is verified by the console — verification is the
    gateway's job; these values are SAMPLE data here.
    """

    raw: dict[str, Any]
    issuer: str
    audience: str
    expires_at: str
    not_verified_note: str = (
        "Displayed unverified. The console does not check the signature, issuer, "
        "audience, or expiry — basis-gateway verifies the token."
    )


@dataclass(frozen=True)
class SubjectPreview:
    """A normalized BASIS subject as the gateway would derive it from claims.

    Presentation only. The console does not perform this normalization for live
    evaluation — the gateway derives the real subject from a verified token. This
    preview shows operators *what that normalized subject looks like*.
    """

    subject_id: str
    subject_type: str
    roles: tuple[str, ...]
    groups: tuple[str, ...]
    issuer: str


@dataclass(frozen=True)
class MappingStep:
    """One claim→subject mapping row, for the normalization preview table.

    ``source`` is where the value comes from in the token (e.g. a claim path);
    ``target`` is the BASIS subject field it maps to; ``result`` is the mapped
    value. Illustrative only — the gateway owns the real mapping.
    """

    source: str
    target: str
    result: str


@dataclass(frozen=True)
class FutureIntegration:
    """A capability the future ``basis-identity`` service is expected to provide.

    These are explicitly NOT current console functionality. The UI renders them
    as a forward-looking list so operators understand where identity features
    will plug in, without implying the console implements any protocol.
    """

    name: str
    description: str


@dataclass(frozen=True)
class AccessPreview:
    """Links the identity view to the existing decision simulator.

    The console can show how a request *for this subject* would be shaped and
    submitted, but it never sends the subject as identity: live evaluation
    derives the subject from the gateway's verified token. ``simulator_example``
    is the slug of a sample simulator scenario to deep-link into ``/simulate``.
    """

    subject_id: str
    subject_type: str
    summary: str
    simulator_example: str
    identity_note: str = (
        "Live evaluation does not send this subject. The gateway derives identity "
        "from its verified Bearer token; the subject above is preview/educational "
        "only. This link previews how the request would be shaped, not who it runs as."
    )


@dataclass(frozen=True)
class IdentityPreview:
    """Everything the Identity & Access Explorer page needs, bundled.

    ``is_sample`` is always True in this phase and drives the SAMPLE labelling in
    the UI. The console never presents this as live, verified identity state.
    """

    subject: SubjectPreview
    claims: ClaimPreview
    role_mappings: tuple[MappingStep, ...]
    group_mappings: tuple[MappingStep, ...]
    normalization_steps: tuple[str, ...]
    is_sample: bool = True


def sample_identity_preview() -> IdentityPreview:
    """Build the illustrative Identity & Access preview shown on ``/identity``.

    This is SAMPLE data: a plausible OIDC-style claim set and the BASIS subject a
    gateway subject-mapper would derive from it. It is NOT sourced from a live
    system, is never verified, and must never be presented as authoritative. The
    claim set is intentionally *nested* (``realm_access``, ``resource_access``,
    ``address``) so the claims viewer demonstrates safe rendering of nested
    payloads.
    """
    raw_claims: dict[str, Any] = {
        "iss": "https://idp.example.com/realms/basis",
        "aud": "basis-gateway",
        "sub": "9b2e7c10-0000-4a00-9c00-000000000abc",
        "exp": 1782338400,
        "iat": 1782334800,
        "preferred_username": "operator-jane",
        "email": "jane.operator@example.com",
        "email_verified": True,
        "realm_access": {"roles": ["operator", "viewer"]},
        "resource_access": {
            "basis-gateway": {"roles": ["telemetry-read"]},
        },
        "groups": ["/plant-1/operators", "/bldg-a"],
        "address": {"region": "us-west", "site": "bldg-a"},
    }

    claims = ClaimPreview(
        raw=raw_claims,
        issuer=str(raw_claims["iss"]),
        audience=str(raw_claims["aud"]),
        expires_at="2026-06-24T15:00:00Z (exp 1782338400)",
    )

    subject = SubjectPreview(
        subject_id="operator-jane",
        subject_type="user",
        roles=("operator", "viewer", "telemetry-read"),
        groups=("plant-1/operators", "bldg-a"),
        issuer=str(raw_claims["iss"]),
    )

    role_mappings = (
        MappingStep(
            source="claim: preferred_username",
            target="subject_id",
            result="operator-jane",
        ),
        MappingStep(
            source="claim: realm_access.roles",
            target="roles",
            result="operator, viewer",
        ),
        MappingStep(
            source="claim: resource_access.basis-gateway.roles",
            target="roles (appended)",
            result="telemetry-read",
        ),
    )

    group_mappings = (
        MappingStep(
            source="claim: groups",
            target="groups (leading slash stripped)",
            result="plant-1/operators, bldg-a",
        ),
    )

    normalization_steps = (
        "External IdP issues an OIDC ID/access token with claims.",
        "basis-gateway verifies the token (signature, issuer, audience, expiry).",
        "basis-gateway's subject mapper derives the BASIS subject from the claims.",
        "basis-core evaluates the canonical request against the normalized subject.",
    )

    return IdentityPreview(
        subject=subject,
        claims=claims,
        role_mappings=role_mappings,
        group_mappings=group_mappings,
        normalization_steps=normalization_steps,
    )


def sample_access_preview() -> AccessPreview:
    """Build the identity→simulator linkage shown on ``/identity``.

    The slug matches a scenario in
    :func:`basis_console.sample_data.sample_simulator_scenarios` so the link
    pre-loads a coherent request into the simulator. The subject is never sent as
    identity; the gateway derives it from its verified token.
    """
    return AccessPreview(
        subject_id="operator-jane",
        subject_type="user",
        summary=(
            "Preview how a request from this subject would be shaped and submitted "
            "to basis-gateway. The gateway, not the console, decides the outcome."
        ),
        simulator_example="operator-read-ahu-temp",
    )


def future_identity_integrations() -> tuple[FutureIntegration, ...]:
    """List the capabilities the future ``basis-identity`` service will provide.

    These are explicitly future, non-live integrations. The console will be able
    to *display* their output later; it will never implement the protocols.
    """
    return (
        FutureIntegration(
            "OIDC discovery viewer",
            "Inspect an IdP's published OIDC discovery document and endpoints.",
        ),
        FutureIntegration(
            "OAuth flow explorer",
            "Trace an OAuth authorization flow step by step for diagnostics.",
        ),
        FutureIntegration(
            "JWT inspector",
            "Decode and display token headers and claims for inspection.",
        ),
        FutureIntegration(
            "JWKS viewer",
            "View the signing keys an issuer publishes via its JWKS endpoint.",
        ),
        FutureIntegration(
            "SAML assertion viewer",
            "Render the contents of a SAML assertion in a readable form.",
        ),
        FutureIntegration(
            "SCIM event viewer",
            "Display SCIM provisioning/lifecycle events (create, update, deactivate).",
        ),
        FutureIntegration(
            "Access review workflows",
            "Support periodic review of who has access to what, and why.",
        ),
    )
