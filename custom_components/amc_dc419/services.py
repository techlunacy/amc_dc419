"""Service handlers for AMC DC419 controllers."""

from __future__ import annotations

from typing import Final, cast

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from . import AMCDC419ConfigEntry, AMCDC419RuntimeData
from .const import CONF_CONTROLLER_ID, DOMAIN, LearnCommand
from .transport import TransportError

ATTR_COMMAND: Final = "command"
ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
SERVICE_LEARN_COMMAND: Final = "learn_command"
SERVICE_SEND_RAW: Final = "send_raw"
SERVICE_SYNC_STATE: Final = "sync_state"

_ENTRY_SCHEMA: Final = vol.Schema({vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string})
_COMMAND_SCHEMA: Final = _ENTRY_SCHEMA.extend(
    {vol.Required(ATTR_COMMAND): vol.In([command.value for command in LearnCommand])}
)


async def async_register_services(hass: HomeAssistant) -> None:
    """Register AMC DC419 services once for the Home Assistant instance."""
    if hass.services.has_service(DOMAIN, SERVICE_SYNC_STATE):
        return

    async def async_handle_sync_state(call: ServiceCall) -> None:
        """Dispatch a state-reset service call for this Home Assistant instance."""
        await _async_handle_sync_state(hass, call)

    async def async_handle_learn_command(call: ServiceCall) -> None:
        """Dispatch a relearn service call for this Home Assistant instance."""
        await _async_handle_learn_command(hass, call)

    async def async_handle_send_raw(call: ServiceCall) -> None:
        """Dispatch a raw-send service call for this Home Assistant instance."""
        await _async_handle_send_raw(hass, call)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SYNC_STATE,
        async_handle_sync_state,
        schema=_ENTRY_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LEARN_COMMAND,
        async_handle_learn_command,
        schema=_COMMAND_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_RAW,
        async_handle_send_raw,
        schema=_COMMAND_SCHEMA,
    )


async def _async_handle_sync_state(hass: HomeAssistant, call: ServiceCall) -> None:
    """Clear inferred state for a configured controller."""
    entry = _get_loaded_entry(hass, call)
    await entry.runtime_data.coordinator.async_reset_optimistic_state()


async def _async_handle_learn_command(hass: HomeAssistant, call: ServiceCall) -> None:
    """Relearn and replace one named command for a configured controller."""
    entry = _get_loaded_entry(hass, call)
    command = LearnCommand(cast(str, call.data[ATTR_COMMAND]))
    try:
        learned_command = await entry.runtime_data.transport.async_learn(command)
    except TransportError as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="unable_to_learn",
        ) from err

    controller_id = entry.data[CONF_CONTROLLER_ID]
    assert isinstance(controller_id, str)
    await entry.runtime_data.command_store.async_store_command(
        controller_id, learned_command
    )


async def _async_handle_send_raw(hass: HomeAssistant, call: ServiceCall) -> None:
    """Send one stored command without changing optimistic controller state."""
    entry = _get_loaded_entry(hass, call)
    command = LearnCommand(cast(str, call.data[ATTR_COMMAND]))
    await entry.runtime_data.coordinator.async_send_commands((command,))


def _get_loaded_entry(hass: HomeAssistant, call: ServiceCall) -> AMCDC419ConfigEntry:
    """Return the loaded AMC DC419 entry requested by a service call."""
    entry_id = call.data[ATTR_CONFIG_ENTRY_ID]
    assert isinstance(entry_id, str)
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError("AMC DC419 config entry was not found")

    runtime_data = entry.runtime_data
    if not isinstance(runtime_data, AMCDC419RuntimeData):
        raise ServiceValidationError("AMC DC419 config entry is not loaded")

    return cast(AMCDC419ConfigEntry, entry)
