"""AMC DC419 Home Assistant integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .storage import CommandStore, get_command_store


@dataclass(slots=True)
class AMCDC419RuntimeData:
    """Runtime resources shared by an AMC DC419 config entry."""

    command_store: CommandStore


type AMCDC419ConfigEntry = ConfigEntry[AMCDC419RuntimeData]


async def async_setup(hass: HomeAssistant, _config: Mapping[str, Any]) -> bool:
    """Set up the AMC DC419 integration domain."""
    get_command_store(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: AMCDC419ConfigEntry) -> bool:
    """Set up an AMC DC419 controller config entry."""
    command_store = get_command_store(hass)
    await command_store.async_load()
    entry.runtime_data = AMCDC419RuntimeData(command_store=command_store)
    return True