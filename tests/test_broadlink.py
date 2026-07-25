"""Tests for the Broadlink RF transport implementation."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant, ServiceCall

from custom_components.amc_dc419.broadlink import BroadlinkTransport
from custom_components.amc_dc419.const import (
    ATTR_REMOTE_COMMAND,
    ATTR_REMOTE_DEVICE,
    CONF_REMOTE_DEVICE,
    CONF_REMOTE_ENTITY_ID,
    REMOTE_DOMAIN,
    REMOTE_SERVICE_LEARN_COMMAND,
    REMOTE_SERVICE_SEND_COMMAND,
    LearnCommand,
    TransportType,
)
from custom_components.amc_dc419.transport import (
    LearnedCommand,
    TransportConfiguration,
    TransportError,
    TransportUnavailableError,
)


async def test_broadlink_transport_learns_and_sends_command(
    hass: HomeAssistant,
) -> None:
    """Broadlink verifies a learned command before later sending it."""
    learned_calls: list[ServiceCall] = []
    sent_calls: list[ServiceCall] = []

    async def handle_learn(call: ServiceCall) -> None:
        """Record the remote learning request."""
        learned_calls.append(call)

    async def handle_send(call: ServiceCall) -> None:
        """Record the remote send request."""
        sent_calls.append(call)

    hass.states.async_set("remote.office", "on")
    hass.services.async_register(
        REMOTE_DOMAIN, REMOTE_SERVICE_LEARN_COMMAND, handle_learn
    )
    hass.services.async_register(
        REMOTE_DOMAIN, REMOTE_SERVICE_SEND_COMMAND, handle_send
    )
    transport = BroadlinkTransport(
        hass,
        TransportConfiguration(
            transport_type=TransportType.BROADLINK,
            settings={
                CONF_REMOTE_ENTITY_ID: "remote.office",
                CONF_REMOTE_DEVICE: "amc_dc419_office",
            },
        ),
    )

    learned_command = await transport.async_learn(LearnCommand.FAN_SPEED_4)

    assert learned_command.payload == {
        ATTR_REMOTE_DEVICE: "amc_dc419_office",
        ATTR_REMOTE_COMMAND: LearnCommand.FAN_SPEED_4.value,
    }
    assert learned_calls[0].data[ATTR_REMOTE_COMMAND] == LearnCommand.FAN_SPEED_4.value
    assert sent_calls[0].data[ATTR_REMOTE_DEVICE] == "amc_dc419_office"
    assert sent_calls[0].data[ATTR_REMOTE_COMMAND] == LearnCommand.FAN_SPEED_4.value


async def test_broadlink_transport_is_unavailable_without_remote_state(
    hass: HomeAssistant,
) -> None:
    """Transport validation rejects a remote that Home Assistant cannot resolve."""
    transport = BroadlinkTransport(
        hass,
        TransportConfiguration(
            transport_type=TransportType.BROADLINK,
            settings={
                CONF_REMOTE_ENTITY_ID: "remote.missing",
                CONF_REMOTE_DEVICE: "amc_dc419_missing",
            },
        ),
    )

    with pytest.raises(TransportUnavailableError, match="unavailable"):
        await transport.async_validate()


async def test_broadlink_transport_explains_missing_learned_command(
    hass: HomeAssistant,
) -> None:
    """A missing Broadlink code instructs the user to relearn the RF command."""

    async def handle_learn(_call: ServiceCall) -> None:
        """Expose the learning service required by transport validation."""

    async def handle_send(_call: ServiceCall) -> None:
        """Simulate Broadlink's error for a code it did not store."""
        raise ValueError("Command not found: 'light_toggle'")

    hass.states.async_set("remote.office", "on")
    hass.services.async_register(
        REMOTE_DOMAIN, REMOTE_SERVICE_LEARN_COMMAND, handle_learn
    )
    hass.services.async_register(
        REMOTE_DOMAIN, REMOTE_SERVICE_SEND_COMMAND, handle_send
    )
    transport = BroadlinkTransport(
        hass,
        TransportConfiguration(
            transport_type=TransportType.BROADLINK,
            settings={
                CONF_REMOTE_ENTITY_ID: "remote.office",
                CONF_REMOTE_DEVICE: "amc_dc419_office",
            },
        ),
    )

    learned_command = LearnedCommand(
        command=LearnCommand.LIGHT_TOGGLE,
        transport_type=TransportType.BROADLINK,
        payload={
            ATTR_REMOTE_DEVICE: "amc_dc419_office",
            ATTR_REMOTE_COMMAND: LearnCommand.LIGHT_TOGGLE.value,
        },
        learned_at="2026-07-25T00:00:00+00:00",
    )

    with pytest.raises(TransportError, match="Relearn the command"):
        await transport.async_send(learned_command)


async def test_broadlink_transport_rejects_unverified_learned_command(
    hass: HomeAssistant,
) -> None:
    """A silent Broadlink RF capture failure does not produce a learned command."""

    async def handle_learn(_call: ServiceCall) -> None:
        """Simulate a Broadlink learning action that reports no error."""

    async def handle_send(_call: ServiceCall) -> None:
        """Report that Broadlink did not persist the requested code."""
        raise ValueError("Command not found: 'light_toggle'")

    hass.states.async_set("remote.office", "on")
    hass.services.async_register(
        REMOTE_DOMAIN, REMOTE_SERVICE_LEARN_COMMAND, handle_learn
    )
    hass.services.async_register(
        REMOTE_DOMAIN, REMOTE_SERVICE_SEND_COMMAND, handle_send
    )
    transport = BroadlinkTransport(
        hass,
        TransportConfiguration(
            transport_type=TransportType.BROADLINK,
            settings={
                CONF_REMOTE_ENTITY_ID: "remote.office",
                CONF_REMOTE_DEVICE: "amc_dc419_office",
            },
        ),
    )

    with pytest.raises(TransportError, match="Relearn the command"):
        await transport.async_learn(LearnCommand.LIGHT_TOGGLE)
