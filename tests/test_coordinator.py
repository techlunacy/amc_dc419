"""Tests for optimistic controller state coordination."""

from __future__ import annotations

from dataclasses import replace

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.amc_dc419.const import DOMAIN, LearnCommand
from custom_components.amc_dc419.coordinator import AMCDC419Coordinator
from custom_components.amc_dc419.storage import CommandStore
from custom_components.amc_dc419.transport import TransportUnavailableError

from .conftest import FakeTransport, make_learned_command


async def test_send_commands_preserves_order_and_updates_state(
    hass: HomeAssistant,
) -> None:
    """Command batches preserve RF order and update optimistic state on success."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    store = CommandStore(hass)
    transport = FakeTransport()
    coordinator = AMCDC419Coordinator(hass, entry, "controller", store, transport)
    commands = (LearnCommand.LIGHT_ON, LearnCommand.BRIGHTNESS_UP)
    for command in commands:
        await store.async_store_command("controller", make_learned_command(command))

    await coordinator.async_initialize()
    await coordinator.async_send_commands(
        commands,
        lambda state: replace(state, light_is_on=True, brightness=96),
    )

    assert [command.command for command in transport.sent] == list(commands)
    assert coordinator.data.light_is_on is True
    assert coordinator.data.brightness == 96
    assert coordinator.transport_available is True


async def test_unavailable_send_marks_transport_unavailable(
    hass: HomeAssistant,
) -> None:
    """Unavailable sends surface an error and make entities unavailable."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    store = CommandStore(hass)
    transport = FakeTransport()
    coordinator = AMCDC419Coordinator(hass, entry, "controller", store, transport)
    await store.async_store_command(
        "controller", make_learned_command(LearnCommand.FAN_OFF)
    )
    await coordinator.async_initialize()
    transport.fail_send = True

    with pytest.raises(TransportUnavailableError):
        await coordinator.async_send_commands((LearnCommand.FAN_OFF,))

    assert coordinator.transport_available is False


async def test_reset_optimistic_state_preserves_availability(
    hass: HomeAssistant,
) -> None:
    """State reset clears optimistic values without hiding an available transport."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    coordinator = AMCDC419Coordinator(
        hass, entry, "controller", CommandStore(hass), FakeTransport()
    )
    await coordinator.async_initialize()
    coordinator.async_set_updated_data(
        replace(coordinator.data, fan_percentage=50, light_is_on=True)
    )

    await coordinator.async_reset_optimistic_state()

    assert coordinator.data.fan_percentage is None
    assert coordinator.data.light_is_on is None
    assert coordinator.transport_available is True
