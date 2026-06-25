"""Resource Explorer presentation models and SAMPLE data (Phase 11).

WHAT THIS MODULE IS
───────────────────
This module provides the *presentation-oriented* data the Resource Explorer
(``/resources``) renders: sample normalized resources across the BASIS adapter
families, the identifiers they expose (local vs. canonical), the adapter source
that would normalize them, their supported actions, and the gateway request
shape an operator would submit to authorize an action against them.

The goal is operational *visibility*: to make visible what BASIS is reasoning
about — resources, actions, resource identifiers, adapter sources, and gateway
request shapes — so operators and contributors can see how OT/platform resources
become normalized authorization targets.

The structures are named ``*Preview`` deliberately: they describe what the
console *displays*, not what any component *owns*. The console renders and
explains resource *concepts* and authorization *targets*; it is **not** a
resource inventory, a device-discovery service, or a topology map, and it does
**not** own canonical resource contracts.

WHAT THIS MODULE IS NOT
───────────────────────
The console does not discover devices, connect to OT protocols, build protocol
stacks, call adapters directly, mutate resources, or own a resource inventory.
Accordingly this module:

  - holds only **sample/demo** resources (clearly labelled), because
    ``basis-adapters`` does not yet expose a live resource-inventory service and
    ``basis-gateway`` does not yet expose a resource-catalog endpoint — the
    console must not invent those APIs here;
  - composes canonical identifiers only as a **preview mirror** of the gateway's
    composition (see :mod:`basis_console.vocabulary`); the gateway owns the
    authoritative composition;
  - redacts sensitive fields defensively before any raw payload is rendered
    (see :mod:`basis_console.gateway.redaction`).

FUTURE INTEGRATION
──────────────────
Live resource data will eventually be sourced from ``basis-adapters`` resource
outputs and a ``basis-gateway`` resource-catalog endpoint, governed by future
``basis-schemas`` resource contracts, and related to subjects by
``basis-identity``. This module's sample builders should then be replaced with
data sourced through the gateway; the presentation models can stay — but they
must never become a resource store.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from basis_console.gateway.redaction import redact_json
from basis_console.vocabulary import compose_action, compose_resource_id

# Notice surfaced on the Resource Explorer so an operator is never misled into
# thinking the console is showing a live resource inventory.
RESOURCE_SAMPLE_NOTICE = (
    "Sample resource data — illustrative only. basis-adapters does not yet expose "
    "a live resource-inventory service and basis-gateway does not yet expose a "
    "resource-catalog endpoint, so these resources are demo concepts. The console "
    "displays resource concepts and authorization targets; it does not discover "
    "devices or own resource inventory."
)

# Short statement of the resource boundary, shown near the top of the page.
RESOURCE_BOUNDARY_NOTICE = (
    "The console displays resource concepts and authorization targets and explains "
    "gateway request shapes. It does not discover devices, connect to OT protocols, "
    "call adapters directly, mutate resources, edit policies, call basis-core, or "
    "own a resource inventory."
)

# Explanation of the identifier model, shown in the identifier-explanation area.
IDENTIFIER_EXPLANATION_NOTICE = (
    "A resource has a local identifier (meaningful within an adapter's source "
    "system), a resource type, and a canonical identifier the gateway composes "
    "from the two. The console previews this composition; the gateway owns it."
)


@dataclass(frozen=True)
class AdapterSourcePreview:
    """The adapter/source that would normalize a resource. Display only.

    ``name`` identifies the normalizing adapter (e.g. ``basis-adapters: bacnet``);
    ``protocol_family`` is the human-facing protocol/platform family; ``description``
    explains how that adapter represents the resource. The console never calls the
    adapter — this only labels *where the concept comes from*.
    """

    name: str
    protocol_family: str
    description: str


@dataclass(frozen=True)
class ResourceIdentifierPreview:
    """A resource's identifiers: local, type, and the composed canonical id.

    ``canonical_resource_id`` is a **preview mirror** of what the gateway composes
    from ``resource_type`` + ``local_resource_id`` (``{type}:{local}``). The console
    does not own canonical identifiers — it previews them for legibility.
    """

    resource_type: str
    local_resource_id: str
    canonical_resource_id: str


@dataclass(frozen=True)
class ResourceActionPreview:
    """One action supported against a resource, with its previewed canonical form.

    ``verb`` is the bare, adapter-normalized verb (e.g. ``read``); ``canonical_action``
    is the ``{verb}:{resource_type}`` form the gateway would compose (e.g. ``read:ahu``).
    Composition is previewed only — the gateway owns it.
    """

    verb: str
    canonical_action: str
    description: str


@dataclass(frozen=True)
class GatewayRequestPreview:
    """An example gateway request shape for a resource. Display/educational only.

    ``normalized_json`` is the preferred normalized body the console would submit
    (bare ``action`` verb + ``resource_type`` + local ``resource_id``).
    ``canonical_action`` / ``canonical_resource_id`` show what the gateway composes
    from it. The console never evaluates — this previews the request shape only.
    """

    normalized_json: str
    canonical_action: str
    canonical_resource_id: str


@dataclass(frozen=True)
class ResourcePreview:
    """One sample normalized resource shaped for display.

    ``source`` records where the resource came from — ``"sample"`` for the demo
    data in this module. A future live integration would set ``"adapter"`` /
    ``"gateway"`` so the UI can keep distinguishing live from sample data.
    ``raw_json`` is the full resource payload, already **redacted** and
    pretty-printed for safe display.
    """

    display_name: str
    description: str
    protocol_family: str
    adapter_source: AdapterSourcePreview
    identifier: ResourceIdentifierPreview
    supported_actions: tuple[ResourceActionPreview, ...]
    gateway_request: GatewayRequestPreview
    raw_json: str
    simulator_example: str | None
    source: str = "sample"

    @property
    def resource_type(self) -> str:
        return self.identifier.resource_type

    @property
    def local_resource_id(self) -> str:
        return self.identifier.local_resource_id

    @property
    def canonical_resource_id(self) -> str:
        return self.identifier.canonical_resource_id

    @property
    def is_sample(self) -> bool:
        return self.source == "sample"

    @property
    def slug(self) -> str:
        """A stable anchor id for this resource (canonical id, ``:`` → ``-``)."""
        return self.canonical_resource_id.replace(":", "-")


@dataclass(frozen=True)
class FutureResourceIntegration:
    """A future source that will populate live resource data. Not implemented here."""

    name: str
    description: str


def _resource(
    *,
    display_name: str,
    description: str,
    protocol_family: str,
    adapter_name: str,
    adapter_description: str,
    resource_type: str,
    local_resource_id: str,
    actions: tuple[tuple[str, str], ...],
    source_attributes: dict[str, Any],
    simulator_example: str | None = None,
    extra_raw: dict[str, Any] | None = None,
) -> ResourcePreview:
    """Assemble one sample resource, previewing composition and redacting raw payload.

    ``actions`` is a tuple of ``(verb, description)`` pairs. ``source_attributes``
    carries protocol-specific detail rendered in the raw payload; it is redacted
    defensively so a credential-shaped attribute can never reach the page.
    """
    canonical_resource_id = compose_resource_id(resource_type, local_resource_id)
    identifier = ResourceIdentifierPreview(
        resource_type=resource_type,
        local_resource_id=local_resource_id,
        canonical_resource_id=canonical_resource_id,
    )

    supported_actions = tuple(
        ResourceActionPreview(
            verb=verb,
            canonical_action=compose_action(verb, resource_type),
            description=action_description,
        )
        for verb, action_description in actions
    )

    # The example gateway request uses the first supported verb (the preferred
    # normalized shape: bare verb + resource_type + local resource_id).
    primary_verb = supported_actions[0].verb
    normalized_body = {
        "action": primary_verb,
        "resource_type": resource_type,
        "resource_id": local_resource_id,
    }
    gateway_request = GatewayRequestPreview(
        normalized_json=json.dumps(normalized_body, indent=2, sort_keys=False),
        canonical_action=compose_action(primary_verb, resource_type),
        canonical_resource_id=canonical_resource_id,
    )

    raw: dict[str, Any] = {
        "display_name": display_name,
        "resource_type": resource_type,
        "local_resource_id": local_resource_id,
        "canonical_resource_id": canonical_resource_id,
        "protocol_family": protocol_family,
        "adapter": adapter_name,
        "supported_actions": [verb for verb, _ in actions],
        "description": description,
        "source_attributes": source_attributes,
    }
    if extra_raw:
        raw.update(extra_raw)

    # Defensive redaction: a resource payload should never carry credentials, but if
    # one ever does (e.g. an adapter connection secret), it must not reach the page.
    redacted = redact_json(raw)
    raw_json = json.dumps(redacted, indent=2, sort_keys=False)

    return ResourcePreview(
        display_name=display_name,
        description=description,
        protocol_family=protocol_family,
        adapter_source=AdapterSourcePreview(
            name=adapter_name,
            protocol_family=protocol_family,
            description=adapter_description,
        ),
        identifier=identifier,
        supported_actions=supported_actions,
        gateway_request=gateway_request,
        raw_json=raw_json,
        simulator_example=simulator_example,
        source="sample",
    )


def sample_resources() -> tuple[ResourcePreview, ...]:
    """Illustrative normalized resources for the Resource Explorer.

    SAMPLE data only — never sourced from a live system and never authoritative.
    The set spans every current ``basis-adapters`` protocol/platform family
    (BACnet, Modbus, OPC UA, MQTT, DNP3, IEC 61850, KNX, Niagara) plus the REST
    adapter, so an operator can see how each family's resources become normalized
    authorization targets with local and canonical identifiers.
    """
    return (
        _resource(
            display_name="Rooftop AHU",
            description=(
                "A rooftop air-handling unit exposed as a BACnet device with "
                "analog/binary objects for status and setpoints."
            ),
            protocol_family="BACnet",
            adapter_name="basis-adapters: bacnet",
            adapter_description=(
                "Normalizes BACnet objects/properties into BASIS resources; reads "
                "present-value and writes commandable properties."
            ),
            resource_type="ahu",
            local_resource_id="rooftop-1",
            actions=(
                ("read", "Read present-value of AHU objects (status, temperatures)."),
                ("write", "Write a commandable property (e.g. occupancy command)."),
            ),
            source_attributes={
                "device_instance": 200100,
                "objects": [
                    {"object_type": "analog-input", "instance": 1, "name": "SupplyAirTemp"},
                    {"object_type": "binary-value", "instance": 3, "name": "OccupancyCmd"},
                ],
                "segmentation_supported": True,
                # Defensive redaction demonstration — must never render.
                "connection_secret": "SAMPLE-bacnet-bbmd-secret-do-not-use",
            },
            simulator_example="operator-read-ahu-temp",
        ),
        _resource(
            display_name="Boiler Controller",
            description=(
                "A boiler controller exposed over Modbus TCP; holding registers "
                "carry setpoints and coils carry control commands."
            ),
            protocol_family="Modbus",
            adapter_name="basis-adapters: modbus",
            adapter_description=(
                "Normalizes Modbus registers/coils into BASIS resources; reads "
                "input/holding registers and executes coil writes as control."
            ),
            resource_type="controller",
            local_resource_id="boiler-1",
            actions=(
                ("read", "Read holding/input registers (temperatures, status)."),
                ("execute", "Execute a control command via a coil write."),
            ),
            source_attributes={
                "unit_id": 5,
                "registers": [
                    {"type": "holding", "address": 40001, "name": "SupplySetpoint"},
                    {"type": "input", "address": 30002, "name": "FlueTemp"},
                ],
                "coils": [{"address": 1, "name": "BurnerEnable"}],
                "byte_order": "big-endian",
            },
        ),
        _resource(
            display_name="Supply Air Temperature",
            description=(
                "A supply-air temperature sensor exposed as an OPC UA variable node "
                "supporting reads and monitored-item subscriptions."
            ),
            protocol_family="OPC UA",
            adapter_name="basis-adapters: opcua",
            adapter_description=(
                "Normalizes OPC UA nodes into BASIS resources; reads node values and "
                "subscribes to monitored items for telemetry."
            ),
            resource_type="sensor",
            local_resource_id="supply-air-temp",
            actions=(
                ("read", "Read the current value of the variable node."),
                ("subscribe", "Subscribe to value changes via a monitored item."),
            ),
            source_attributes={
                "node_id": "ns=2;s=AHU.Rooftop1.SupplyAirTemp",
                "data_type": "Double",
                "engineering_units": "degC",
                "access_level": "CurrentRead",
            },
        ),
        _resource(
            display_name="Zone Setpoint Topic",
            description=(
                "A zone temperature setpoint published on an MQTT topic; writes "
                "publish a new setpoint and subscriptions observe updates."
            ),
            protocol_family="MQTT",
            adapter_name="basis-adapters: mqtt",
            adapter_description=(
                "Normalizes MQTT topics into BASIS resources; PUBLISH maps to write "
                "and SUBSCRIBE maps to subscribe, preserving topic wildcards verbatim."
            ),
            resource_type="setpoint",
            local_resource_id="zone-3",
            actions=(
                ("write", "Publish a new setpoint value to the topic."),
                ("subscribe", "Subscribe to setpoint updates on the topic."),
            ),
            source_attributes={
                "topic": "site/bldg-a/zone-3/setpoint",
                "qos": 1,
                "retain": True,
                "payload_format": "application/json",
            },
        ),
        _resource(
            display_name="Feeder Breaker",
            description=(
                "A distribution feeder breaker exposed over DNP3; binary inputs "
                "carry status and a binary output point carries select-before-operate "
                "control."
            ),
            protocol_family="DNP3",
            adapter_name="basis-adapters: dnp3",
            adapter_description=(
                "Normalizes DNP3 points into BASIS resources; READ maps to read, "
                "control operations map to execute, and unsolicited enable maps to "
                "subscribe (stateless select-before-operate)."
            ),
            resource_type="breaker",
            local_resource_id="feeder-2",
            actions=(
                ("read", "Read binary/analog input points (breaker status)."),
                ("execute", "Operate the breaker via a control-relay output block."),
                ("subscribe", "Enable unsolicited responses for status changes."),
            ),
            source_attributes={
                "outstation_address": 10,
                "points": [
                    {"group": "binary-input", "index": 0, "name": "BreakerClosed"},
                    {"group": "binary-output", "index": 0, "name": "TripClose"},
                ],
                "control_model": "select-before-operate",
            },
        ),
        _resource(
            display_name="Protection Relay",
            description=(
                "A bay protection relay modeled per IEC 61850; logical nodes expose "
                "measurements and a control block exposes switch control."
            ),
            protocol_family="IEC 61850",
            adapter_name="basis-adapters: iec61850",
            adapter_description=(
                "Normalizes IEC 61850 logical nodes / data objects into BASIS "
                "resources; read/write/execute map to MMS services and report "
                "control blocks map to subscribe (ctlModel consistency checked)."
            ),
            resource_type="relay",
            local_resource_id="bay-1",
            actions=(
                ("read", "Read data-object values from logical nodes (e.g. MMXU)."),
                ("execute", "Operate a controllable object via its control block."),
                ("subscribe", "Subscribe to a report control block for events."),
            ),
            source_attributes={
                "ied_name": "BAY1_RELAY",
                "logical_device": "PROT",
                "logical_nodes": ["MMXU1", "CSWI1", "XCBR1"],
                "ctl_model": "sbo-with-enhanced-security",
            },
        ),
        _resource(
            display_name="Lighting Group",
            description=(
                "A floor lighting circuit exposed as a KNX group address; group "
                "value writes switch the circuit and reads/observes report state."
            ),
            protocol_family="KNX",
            adapter_name="basis-adapters: knx",
            adapter_description=(
                "Normalizes KNX group addresses into BASIS resources; group value "
                "read/write/response map to read/write and observe maps to "
                "subscribe, preserving group addresses verbatim."
            ),
            resource_type="lighting",
            local_resource_id="floor-2-east",
            actions=(
                ("read", "Read the current group value (lighting state)."),
                ("write", "Write a group value to switch the circuit."),
                ("subscribe", "Observe group value changes on the bus."),
            ),
            source_attributes={
                "group_address": "2/1/15",
                "dpt": "1.001",
                "dpt_meaning": "DPT_Switch (on/off)",
                "flags": ["read", "write", "transmit"],
            },
        ),
        _resource(
            display_name="Chiller Plant Point",
            description=(
                "A chiller plant status point surfaced through the Niagara platform "
                "and addressed by ORD; supports read/write and station browse."
            ),
            protocol_family="Niagara",
            adapter_name="basis-adapters: niagara",
            adapter_description=(
                "Platform adapter that normalizes Niagara station points into BASIS "
                "resources; read/write/execute/browse map to station services and "
                "ORDs are preserved verbatim (niagara_user/role are evidence-only)."
            ),
            resource_type="point",
            local_resource_id="chiller-1-status",
            actions=(
                ("read", "Read the point's present value from the station."),
                ("write", "Write the point's value (where writable)."),
                ("browse", "Browse the station component tree under this point."),
            ),
            source_attributes={
                "ord": "station:|slot:/Drivers/BacnetNetwork/Chiller1/points/Status",
                "facets": {"units": "bool", "trueText": "Running", "falseText": "Stopped"},
                "niagara_user": "svc-basis",
            },
        ),
        _resource(
            display_name="Building API Resource",
            description=(
                "A building represented by an upstream REST API; the REST adapter "
                "exposes it as a BASIS resource for read and collection browse."
            ),
            protocol_family="REST",
            adapter_name="basis-adapters: rest",
            adapter_description=(
                "Normalizes REST endpoints into BASIS resources; GET maps to read "
                "and collection traversal maps to browse. The reference adapter "
                "skeleton for HTTP/JSON sources."
            ),
            resource_type="building",
            local_resource_id="hq-campus",
            actions=(
                ("read", "Read the building resource representation (GET)."),
                ("browse", "Browse the building's sub-resources/collection."),
            ),
            source_attributes={
                "base_url": "https://buildings.example.com/api/v1",
                "path": "/buildings/hq-campus",
                "media_type": "application/json",
                # Defensive redaction demonstration — must never render.
                "api_key": "SAMPLE-rest-api-key-do-not-use",
            },
        ),
    )


def future_resource_integrations() -> tuple[FutureResourceIntegration, ...]:
    """Future sources that will populate live resource data. Not implemented here."""
    return (
        FutureResourceIntegration(
            "basis-adapters resource outputs",
            "Normalized resource descriptions emitted by the protocol/platform adapters.",
        ),
        FutureResourceIntegration(
            "basis-gateway resource catalog",
            "A gateway-exposed catalog endpoint for discoverable authorization targets.",
        ),
        FutureResourceIntegration(
            "basis-schemas resource contracts",
            "Shared cross-component resource/identifier contracts the console will consume.",
        ),
        FutureResourceIntegration(
            "basis-identity subject/resource mapping",
            "Relating subjects to the resources they may act on, for access context.",
        ),
        FutureResourceIntegration(
            "basis-deploy site inventory",
            "Per-site deployment inventory describing which resources exist where.",
        ),
        FutureResourceIntegration(
            "External CMDB or OT inventory",
            "Federating an existing CMDB/OT asset inventory — the console never replaces it.",
        ),
    )


__all__ = [
    "IDENTIFIER_EXPLANATION_NOTICE",
    "RESOURCE_BOUNDARY_NOTICE",
    "RESOURCE_SAMPLE_NOTICE",
    "AdapterSourcePreview",
    "FutureResourceIntegration",
    "GatewayRequestPreview",
    "ResourceActionPreview",
    "ResourceIdentifierPreview",
    "ResourcePreview",
    "future_resource_integrations",
    "sample_resources",
]
