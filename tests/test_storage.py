"""Tests for durable AMC DC419 learned-command storage."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant

from custom_components.amc_dc419.const import (
    ATTR_REMOTE_COMMAND,
    CONF_REMOTE_DEVICE,
    CONF_REMOTE_ENTITY_ID,
    LearnCommand,
    TransportType,
)
from custom_components.amc_dc419.storage import CommandStore

from .conftest import make_learned_command


async def test_store_command_round_trip_and_removal(hass: HomeAssistant) -> None:
    """A command remains available until its controller is removed."""
    store = CommandStore(hass)
    command = make_learned_command(LearnCommand.FAN_SPEED_3)

    await store.async_store_command("controller", command)

    assert (
        await store.async_get_command("controller", LearnCommand.FAN_SPEED_3) == command
    )

    await store.async_remove_controller("controller")

    assert await store.async_get_commands("controller") == {}


async def test_store_commands_requires_complete_command_set(
    hass: HomeAssistant,
) -> None:
    """The learning flow cannot persist a partial controller command set."""
    store = CommandStore(hass)

    with pytest.raises(ValueError, match="complete AMC DC419 command set"):
        await store.async_store_commands(
            "controller",
            {
                LearnCommand.LIGHT_TOGGLE: make_learned_command(
                    LearnCommand.LIGHT_TOGGLE
                )
            },
        )

    assert await store.async_get_commands("controller") == {}


async def test_store_commands_replaces_all_bindings_atomically(
    hass: HomeAssistant,
) -> None:
    """A completed learning session replaces the entire previous command set."""
    store = CommandStore(hass)
    commands = {command: make_learned_command(command) for command in LearnCommand}
    await store.async_store_command(
        "controller", make_learned_command(LearnCommand.LIGHT_TOGGLE)
    )

    await store.async_store_commands("controller", commands)

    assert await store.async_get_commands("controller") == commands


def test_deserialize_migrates_light_on_to_light_toggle() -> None:
    """An existing Light On binding remains usable as the shared toggle."""
    commands = CommandStore._deserialize(
        {
            "controllers": {
                "controller": {
                    "light_on": {
                        CONF_REMOTE_ENTITY_ID: "remote.office",
                        CONF_REMOTE_DEVICE: "amc_dc419_controller",
                        "learned_at": "2026-07-25T00:00:00+00:00",
                    },
                    "light_off": {
                        CONF_REMOTE_ENTITY_ID: "remote.office",
                        CONF_REMOTE_DEVICE: "amc_dc419_controller",
                        "learned_at": "2026-07-25T00:00:00+00:00",
                    },
                }
            }
        }
    )

    migrated = commands["controller"][LearnCommand.LIGHT_TOGGLE]
    assert migrated.transport_type is TransportType.BROADLINK
    assert migrated.payload == {
        CONF_REMOTE_DEVICE: "amc_dc419_controller",
        ATTR_REMOTE_COMMAND: "light_on",
    }
