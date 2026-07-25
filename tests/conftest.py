"""Shared fixtures and test doubles for AMC DC419 tests."""

from __future__ import annotations

import pytest

from custom_components.amc_dc419.const import LearnCommand, TransportType
from custom_components.amc_dc419.transport import (
    LearnedCommand,
    RFTransport,
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
        if self.fail_send:
            raise TransportUnavailableError("Test transport is unavailable")
        self.sent.append(command)
