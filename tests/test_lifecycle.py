"""Tests for config-entry migration and runtime lifecycle handling."""

from __future__ import annotations

from typing import cast

from homeassistant.core import HomeAssistant, ServiceCall
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.amc_dc419 import (
    AMCDC419ConfigEntry,
    async_migrate_entry,
)
from custom_components.amc_dc419.const import (
    CONF_AREA_ID,
    CONF_CONTROLLER_ID,
    CONF_FRIENDLY_NAME,
    CONF_REMOTE_DEVICE,
    CONF_REMOTE_ENTITY_ID,
    CONF_TRANSPORT,
    CONF_TRANSPORT_TYPE,
    DOMAIN,
    REMOTE_DOMAIN,
    REMOTE_SERVICE_LEARN_COMMAND,
    REMOTE_SERVICE_SEND_COMMAND,
    LearnCommand,
    TransportType,
)
from custom_components.amc_dc419.storage import get_command_store

from .conftest import make_learned_command


async def test_migrate_entry_wraps_legacy_broadlink_settings(
    hass: HomeAssistant,
) -> None:
    """Minor-version migration moves old remote fields into transport settings."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        minor_version=1,
        data={
            CONF_CONTROLLER_ID: "controller",
            CONF_FRIENDLY_NAME: "Office fan",
            CONF_AREA_ID: "office",
            CONF_REMOTE_ENTITY_ID: "remote.office",
            CONF_REMOTE_DEVICE: "amc_dc419_controller",
        },
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True
    assert entry.minor_version == 2
    assert entry.data[CONF_TRANSPORT_TYPE] == TransportType.BROADLINK.value
    assert entry.data[CONF_TRANSPORT] == {
        CONF_REMOTE_ENTITY_ID: "remote.office",
        CONF_REMOTE_DEVICE: "amc_dc419_controller",
    }


async def test_entry_lifecycle_initializes_and_removes_commands(
    hass: HomeAssistant,
) -> None:
    """Entry setup exposes runtime data and removal clears its learned commands."""

    async def handle_remote(_call: ServiceCall) -> None:
        """Provide required Broadlink remote services for entry validation."""

    hass.states.async_set("remote.office", "on")
    hass.services.async_register(
        REMOTE_DOMAIN, REMOTE_SERVICE_LEARN_COMMAND, handle_remote
    )
    hass.services.async_register(
        REMOTE_DOMAIN, REMOTE_SERVICE_SEND_COMMAND, handle_remote
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        minor_version=2,
        data={
            CONF_CONTROLLER_ID: "controller",
            CONF_FRIENDLY_NAME: "Office fan",
            CONF_AREA_ID: "office",
            CONF_TRANSPORT_TYPE: TransportType.BROADLINK.value,
            CONF_TRANSPORT: {
                CONF_REMOTE_ENTITY_ID: "remote.office",
                CONF_REMOTE_DEVICE: "amc_dc419_controller",
            },
        },
    )
    entry.add_to_hass(hass)
    await get_command_store(hass).async_store_command(
        "controller", make_learned_command(LearnCommand.FAN_OFF)
    )

    assert await hass.config_entries.async_setup(entry.entry_id) is True
    await hass.async_block_till_done()
    typed_entry = cast(AMCDC419ConfigEntry, entry)
    assert typed_entry.runtime_data.coordinator.transport_available is True
    assert await hass.config_entries.async_unload(entry.entry_id) is True

    await hass.config_entries.async_remove(entry.entry_id)

    assert await get_command_store(hass).async_get_commands("controller") == {}
