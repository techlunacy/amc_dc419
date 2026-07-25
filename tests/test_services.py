"""Tests for AMC DC419 integration services."""

from __future__ import annotations

from dataclasses import replace

from homeassistant.core import HomeAssistant

from custom_components.amc_dc419.const import LearnCommand
from custom_components.amc_dc419.services import (
    ATTR_COMMAND,
    ATTR_CONFIG_ENTRY_ID,
    SERVICE_LEARN_COMMAND,
    SERVICE_SEND_RAW,
    SERVICE_SYNC_STATE,
    async_register_services,
)

from .conftest import create_runtime_entry, make_learned_command


async def test_services_send_raw_relearn_and_reset_state(hass: HomeAssistant) -> None:
    """Services delegate to one entry's runtime without leaking state across entries."""
    entry, transport, command_store = await create_runtime_entry(hass)
    await command_store.async_store_command(
        "controller", make_learned_command(LearnCommand.FAN_OFF)
    )
    await async_register_services(hass)

    await hass.services.async_call(
        "amc_dc419",
        SERVICE_SEND_RAW,
        {
            ATTR_CONFIG_ENTRY_ID: entry.entry_id,
            ATTR_COMMAND: LearnCommand.FAN_OFF.value,
        },
        blocking=True,
    )
    await hass.services.async_call(
        "amc_dc419",
        SERVICE_LEARN_COMMAND,
        {
            ATTR_CONFIG_ENTRY_ID: entry.entry_id,
            ATTR_COMMAND: LearnCommand.LIGHT_TOGGLE.value,
        },
        blocking=True,
    )
    entry.runtime_data.coordinator.async_set_updated_data(
        replace(entry.runtime_data.coordinator.data, fan_percentage=50)
    )
    await hass.services.async_call(
        "amc_dc419",
        SERVICE_SYNC_STATE,
        {ATTR_CONFIG_ENTRY_ID: entry.entry_id},
        blocking=True,
    )

    assert [command.command for command in transport.sent] == [LearnCommand.FAN_OFF]
    assert transport.learned == [LearnCommand.LIGHT_TOGGLE]
    assert await command_store.async_get_command(
        "controller", LearnCommand.LIGHT_TOGGLE
    )
    assert entry.runtime_data.coordinator.data.fan_percentage is None
