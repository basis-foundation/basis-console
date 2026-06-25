"""Operator Workspace / Overview presentation models and content (Phase 12).

WHAT THIS MODULE IS
───────────────────
This module provides the *presentation-oriented* content the Operator Workspace
page renders: an explanation of the BASIS operational flow, capability cards for
the existing console areas, an operational-questions panel, a data-maturity
breakdown (live vs sample vs future), and a recommended operator path.

The Operator Workspace is an **orientation** layer. It brings the existing
console areas — Identity & Access, Resources, Decision Simulator, Gateway
Diagnostics, Audit Explorer — together into a single landing page organized
around operational questions rather than repository names. It links to the
existing pages; it does not re-implement them.

Everything here is console-owned and display-only. The structures are named for
what the console *shows* (``WorkspaceCard``, ``OperationalQuestion``,
``DataMaturityItem``, ``OperatorPathStep``) — deliberately avoiding names that
would imply backend authority (no ``SystemState`` / ``CanonicalWorkspace`` /
``OperationalControlPlane``).

WHAT THIS MODULE IS NOT
───────────────────────
The Operator Workspace adds no backend responsibility. Accordingly this module:

  - does **not** evaluate authorization, authenticate, or verify tokens;
  - does **not** own identity, audit, or resource inventory;
  - does **not** import ``basis-core`` or reach the kernel;
  - does **not** turn any sample data into live data. The only live datum the
    workspace surfaces is the gateway connection/readiness state, reused from the
    existing Gateway Diagnostics path (``basis_console.diagnostics``).

The workspace reflects the current data maturity honestly: gateway
health/readiness and gateway-backed evaluation are live/configurable; identity,
resource catalog, and audit history are sample/explanatory until
``basis-identity``, a live resource catalog, and live audit history land.
"""

from __future__ import annotations

from dataclasses import dataclass

# Header copy that states the purpose of the workspace and that it summarizes and
# links existing console capabilities rather than adding new ones.
WORKSPACE_INTRO = (
    "The Operator Workspace brings together identity, resources, gateway state, "
    "authorization simulation, and audit evidence into a single operational view."
)

WORKSPACE_SUMMARY_NOTICE = (
    "This page summarizes and links existing console capabilities. It adds no "
    "backend authority: it does not evaluate authorization, authenticate users, "
    "own identity, audit, or resource inventory, or call basis-core. The only "
    "live data it surfaces is the gateway connection/readiness state already "
    "shown on the Gateway Diagnostics page."
)


@dataclass(frozen=True)
class FlowStep:
    """One stage of the BASIS operational model, mapped to a console area.

    ``label`` is the operational stage (Identity, Resource, Gateway, Decision,
    Audit). ``path`` links to the console area that makes that stage inspectable.
    """

    label: str
    path: str
    blurb: str


@dataclass(frozen=True)
class WorkspaceCard:
    """A capability card for one major console area.

    Console-owned presentation only: it describes what the area helps an operator
    answer and where it lives. ``status`` states the current data maturity
    (live/configurable vs sample/explanatory) so the operator is never misled.
    """

    title: str
    question: str
    purpose: str
    path: str
    status: str


@dataclass(frozen=True)
class OperationalQuestion:
    """An operator-facing question mapped to the console area that answers it.

    The workspace orients humans around tasks ("Who is the subject?") rather than
    repository names, so each question links to the relevant page.
    """

    question: str
    answer_hint: str
    path: str
    link_label: str


@dataclass(frozen=True)
class DataMaturityItem:
    """One row of the data-maturity breakdown.

    ``tier`` is one of ``"live"``, ``"sample"``, or ``"future"``. This honesty is
    important: the workspace must distinguish live/configurable data from
    sample/explanatory data and from not-yet-built integrations.
    """

    tier: str
    label: str
    detail: str


@dataclass(frozen=True)
class OperatorPathStep:
    """One step of the recommended operator path, linked to a console area."""

    order: int
    title: str
    detail: str
    path: str


def operational_flow() -> tuple[FlowStep, ...]:
    """The BASIS operational model, each stage mapped to an existing console area.

    Identity → Resource → Gateway → Decision → Audit.
    """
    return (
        FlowStep(
            label="Identity",
            path="/identity",
            blurb="Who is requesting access — the normalized subject and claims.",
        ),
        FlowStep(
            label="Resource",
            path="/resources",
            blurb="What is being acted on — the normalized authorization target.",
        ),
        FlowStep(
            label="Gateway",
            path="/gateway",
            blurb="The enforcement boundary — is it reachable and ready?",
        ),
        FlowStep(
            label="Decision",
            path="/simulate",
            blurb="Can the action be performed — preview or gateway-backed evaluation.",
        ),
        FlowStep(
            label="Audit",
            path="/audit",
            blurb="What was recorded — decision events and gateway evidence.",
        ),
    )


def capability_cards() -> tuple[WorkspaceCard, ...]:
    """Capability cards for each major console area."""
    return (
        WorkspaceCard(
            title="Identity & Access",
            question="Who is requesting access?",
            purpose=(
                "Inspect a normalized subject, an unverified claims preview, and the "
                "claim-to-subject mapping the gateway would perform."
            ),
            path="/identity",
            status="Sample identity context; future basis-identity integration.",
        ),
        WorkspaceCard(
            title="Resources",
            question="What resource is being targeted?",
            purpose=(
                "See how OT/platform resources become normalized authorization "
                "targets — identifiers, actions, and gateway request shapes."
            ),
            path="/resources",
            status="Sample resource catalog; future live resource catalog.",
        ),
        WorkspaceCard(
            title="Decision Simulator",
            question="Can this action be performed?",
            purpose=(
                "Build a normalized decision request and preview its shape, or — when "
                "configured — submit it to the gateway and view the decision verbatim."
            ),
            path="/simulate",
            status="Preview always; gateway-backed evaluation when configured.",
        ),
        WorkspaceCard(
            title="Gateway Diagnostics",
            question="Is the enforcement boundary healthy?",
            purpose=(
                "Probe the gateway's real /health and /ready endpoints and review "
                "connection, readiness components, and capability."
            ),
            path="/gateway",
            status="Live gateway health/readiness when configured.",
        ),
        WorkspaceCard(
            title="Audit Explorer",
            question="What evidence was recorded?",
            purpose=(
                "Review decision events with subject, action, resource, policy, and "
                "gateway composition evidence and correlation IDs."
            ),
            path="/audit",
            status="Sample audit history; future live audit history.",
        ),
    )


def operational_questions() -> tuple[OperationalQuestion, ...]:
    """Operator-facing questions, each linked to the area that answers it."""
    return (
        OperationalQuestion(
            question="Who is the subject?",
            answer_hint="Inspect the normalized subject context and claims.",
            path="/identity",
            link_label="Identity & Access",
        ),
        OperationalQuestion(
            question="What resource is targeted?",
            answer_hint="See the normalized resource, identifiers, and request shape.",
            path="/resources",
            link_label="Resources",
        ),
        OperationalQuestion(
            question="Can this action be performed?",
            answer_hint="Build a request and preview or evaluate the decision.",
            path="/simulate",
            link_label="Decision Simulator",
        ),
        OperationalQuestion(
            question="Is the enforcement boundary healthy?",
            answer_hint="Check the gateway's health, readiness, and capability.",
            path="/gateway",
            link_label="Gateway Diagnostics",
        ),
        OperationalQuestion(
            question="What evidence was recorded?",
            answer_hint="Review decision events and gateway composition evidence.",
            path="/audit",
            link_label="Audit Explorer",
        ),
    )


def data_maturity() -> tuple[DataMaturityItem, ...]:
    """What is live/configurable vs sample/explanatory vs future.

    The console surfaces only one live datum (gateway health/readiness, plus
    gateway-backed evaluations when configured). Everything else is clearly
    labelled sample/explanatory or future.
    """
    return (
        DataMaturityItem(
            tier="live",
            label="Gateway health / readiness",
            detail="Probed live from the gateway's /health and /ready endpoints.",
        ),
        DataMaturityItem(
            tier="live",
            label="Gateway-backed evaluations",
            detail=(
                "When a base URL and Bearer token are configured, the simulator "
                "submits to the gateway and shows the decision verbatim."
            ),
        ),
        DataMaturityItem(
            tier="sample",
            label="Identity previews",
            detail="Illustrative subject/claims context; not verified, not live.",
        ),
        DataMaturityItem(
            tier="sample",
            label="Resource catalog",
            detail="Illustrative normalized resources; not a live inventory.",
        ),
        DataMaturityItem(
            tier="sample",
            label="Audit event history",
            detail="Illustrative decision events; the console owns no audit store.",
        ),
        DataMaturityItem(
            tier="future",
            label="basis-identity integration",
            detail="Live, verified subject context derived through the gateway.",
        ),
        DataMaturityItem(
            tier="future",
            label="Live resource catalog",
            detail="A live, gateway-exposed inventory of normalized resources.",
        ),
        DataMaturityItem(
            tier="future",
            label="Live audit history",
            detail="A live, gateway-exposed history of decision evidence.",
        ),
    )


def operator_path() -> tuple[OperatorPathStep, ...]:
    """A simple recommended operator path, each step linked to a console area."""
    return (
        OperatorPathStep(
            order=1,
            title="Check Gateway",
            detail="Confirm the enforcement boundary is reachable and ready.",
            path="/gateway",
        ),
        OperatorPathStep(
            order=2,
            title="Inspect Identity",
            detail="Review who is requesting access and the claims involved.",
            path="/identity",
        ),
        OperatorPathStep(
            order=3,
            title="Inspect Resources",
            detail="Review what is being acted on and how it is normalized.",
            path="/resources",
        ),
        OperatorPathStep(
            order=4,
            title="Run Evaluation",
            detail="Build a request and preview or evaluate the decision.",
            path="/simulate",
        ),
        OperatorPathStep(
            order=5,
            title="Review Audit Evidence",
            detail="Inspect the evidence recorded for the decision.",
            path="/audit",
        ),
    )
