"""Shared fixtures and test doubles for AMC DC419 tests."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.amc_dc419 import AMCDC419RuntimeData
from custom_components.amc_dc419.const import (
    CONF_CONTROLLER_ID,
    DOMAIN,
    LearnCommand,
    TransportType,
)
from custom_components.amc_dc419.coordinator import (
    AMCDC419Coordinator,
    ControllerOptions,
)
from custom_components.amc_dc419.storage import CommandStore
from custom_components.amc_dc419.transport import (
    LearnedCommand,
    RFTransport,
    TransportError,
    TransportUnavailableError,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom integrations in every test."""


def make_learned_command(command: LearnCommand) -> LearnedCommand:
    """Return a deterministic transport-neutral learned command."""
    return LearnedCommand(
        command=command,
        transport_type=TransportType.BROADLINK,
        payload={"command": command.value},
        learned_at="2026-07-25T00:00:00+00:00",
    )


class FakeTransport(RFTransport):
    """In-memory RF transport that records commands without external I/O."""

    def __init__(self) -> None:
        """Initialize the transport in its available state."""
        self.fail_send = False
        self.fail_validate = False
        self.learned: list[LearnCommand] = []
        self.sent: list[LearnedCommand] = []
        self.send_attempts: list[LearnedCommand] = []
        self.transient_send_failures = 0

    @property
    def transport_type(self) -> TransportType:
        """Return the Broadlink type used by deterministic test commands."""
        return TransportType.BROADLINK

    async def async_validate(self) -> None:
        """Raise when the test has marked the transport unavailable."""
        if self.fail_validate:
            raise TransportUnavailableError("Test transport is unavailable")

    async def async_learn(self, command: LearnCommand) -> LearnedCommand:
        """Record and return a deterministic learned command."""
        await self.async_validate()
        self.learned.append(command)
        return make_learned_command(command)

    async def async_send(self, command: LearnedCommand) -> None:
        """Record a sent command or simulate an unavailable transport."""
        await self.async_validate()
        self.send_attempts.append(command)
        if self.fail_send:
            raise TransportUnavailableError("Test transport is unavailable")
        if self.transient_send_failures:
            self.transient_send_failures -= 1
            raise TransportError("Test transport failed transiently")
        self.sent.append(command)


async def create_runtime_entry(
    hass: HomeAssistant,
    options: ControllerOptions | None = None,
) -> tuple[MockConfigEntry, FakeTransport, CommandStore]:
    """Create one loaded-in-memory entry runtime for entity and service tests."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_CONTROLLER_ID: "controller"},
    )
    entry.add_to_hass(hass)
    command_store = CommandStore(hass)
    transport = FakeTransport()
    coordinator = AMCDC419Coordinator(
        hass,
        entry,
        "controller",
        command_store,
        transport,
        options,
    )
    await coordinator.async_initialize()
    entry.runtime_data = AMCDC419RuntimeData(
        command_store=command_store,
        coordinator=coordinator,
        transport=transport,
    )
    return entry, transport, command_store
