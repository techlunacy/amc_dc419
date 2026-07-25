"""AMC DC419 Home Assistant integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_AREA_ID,
    CONF_CONTROLLER_ID,
    CONF_FRIENDLY_NAME,
    CONF_REMOTE_DEVICE,
    CONF_REMOTE_ENTITY_ID,
    PLATFORMS,
    TransportType,
)
from .coordinator import AMCDC419Coordinator, ControllerOptions
from .state_store import get_optimistic_state_store
from .storage import CommandStore, get_command_store
from .transport import (
    RFTransport,
    TransportConfiguration,
    TransportConfigurationError,
    TransportError,
    create_transport,
)


@dataclass(slots=True)
class AMCDC419RuntimeData:
    """Runtime resources shared by an AMC DC419 config entry."""

    command_store: CommandStore
    coordinator: AMCDC419Coordinator
    transport: RFTransport


type AMCDC419ConfigEntry = ConfigEntry[AMCDC419RuntimeData]


async def async_setup(hass: HomeAssistant, _config: ConfigType) -> bool:
    """Set up the AMC DC419 integration domain."""
    from .services import async_register_services

    await async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: AMCDC419ConfigEntry) -> bool:
    """Set up an AMC DC419 controller config entry."""
    command_store = get_command_store(hass)
    await command_store.async_load()
    state_store = get_optimistic_state_store(hass)
    await state_store.async_load()
    controller_id = _get_controller_id(entry)
    try:
        transport_configuration = TransportConfiguration.from_entry_data(entry.data)
        transport = create_transport(hass, transport_configuration)
        coordinator = AMCDC419Coordinator(
            hass,
            entry,
            controller_id,
            command_store,
            transport,
            ControllerOptions.from_entry(entry),
            state_store,
        )
        await coordinator.async_initialize()
    except TransportConfigurationError as err:
        raise ConfigEntryError("Stored RF transport configuration is invalid") from err
    except TransportError as err:
        raise ConfigEntryNotReady("RF transport is unavailable") from err

    entry.runtime_data = AMCDC419RuntimeData(
        command_store=command_store,
        coordinator=coordinator,
        transport=transport,
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate earlier Broadlink-specific entry data to transport-neutral data."""
    if entry.version > 1:
        return False
    if entry.minor_version >= 2:
        return True

    controller_id = entry.data.get(CONF_CONTROLLER_ID)
    friendly_name = entry.data.get(CONF_FRIENDLY_NAME)
    area_id = entry.data.get(CONF_AREA_ID)
    remote_entity_id = entry.data.get(CONF_REMOTE_ENTITY_ID)
    remote_device = entry.data.get(CONF_REMOTE_DEVICE)
    if (
        not isinstance(controller_id, str)
        or not isinstance(friendly_name, str)
        or not isinstance(area_id, str)
        or not isinstance(remote_entity_id, str)
        or not isinstance(remote_device, str)
    ):
        return False

    transport_configuration = TransportConfiguration(
        transport_type=TransportType.BROADLINK,
        settings={
            CONF_REMOTE_ENTITY_ID: remote_entity_id,
            CONF_REMOTE_DEVICE: remote_device,
        },
    )
    hass.config_entries.async_update_entry(
        entry,
        data={
            CONF_CONTROLLER_ID: controller_id,
            CONF_FRIENDLY_NAME: friendly_name,
            CONF_AREA_ID: area_id,
            **transport_configuration.as_entry_data(),
        },
        minor_version=2,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AMCDC419ConfigEntry) -> bool:
    """Unload an AMC DC419 controller config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.coordinator.async_shutdown()
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: AMCDC419ConfigEntry) -> None:
    """Remove durable controller data when an AMC DC419 controller is removed."""
    await get_command_store(hass).async_remove_controller(_get_controller_id(entry))
    await get_optimistic_state_store(hass).async_remove_state(_get_controller_id(entry))


def _get_controller_id(entry: AMCDC419ConfigEntry) -> str:
    """Return the validated controller identifier stored in a config entry."""
    controller_id = entry.data.get(CONF_CONTROLLER_ID)
    if not isinstance(controller_id, str) or not controller_id:
        raise ConfigEntryError("Config entry has no valid controller identifier")
    return controller_id
