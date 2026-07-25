"""Diagnostics support for the AMC DC419 integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import AMCDC419ConfigEntry
from .const import CONF_TRANSPORT


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: AMCDC419ConfigEntry
) -> dict[str, Any]:
    """Return redacted configuration, command metadata, and runtime state."""
    del hass
    runtime_data = entry.runtime_data
    controller_id = entry.data.get("controller_id")
    commands = (
        await runtime_data.command_store.async_get_commands(controller_id)
        if isinstance(controller_id, str)
        else {}
    )

    return {
        "entry_data": async_redact_data(entry.data, {CONF_TRANSPORT}),
        "transport": {
            "type": runtime_data.transport.transport_type.value,
            "available": runtime_data.coordinator.transport_available,
            "availability_entity_ids": list(
                runtime_data.transport.availability_entity_ids
            ),
        },
        "commands": {
            command.value: {
                "transport_type": learned_command.transport_type.value,
                "learned_at": learned_command.learned_at,
            }
            for command, learned_command in commands.items()
        },
        "optimistic_state": runtime_data.coordinator.data.as_diagnostics_data(),
    }
