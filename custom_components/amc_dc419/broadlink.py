"""Broadlink-backed RF transport implementation."""

from __future__ import annotations

import logging
from typing import Final

from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_COMMAND_TYPE,
    ATTR_REMOTE_COMMAND,
    ATTR_REMOTE_DEVICE,
    ATTR_TIMEOUT,
    CONF_REMOTE_DEVICE,
    CONF_REMOTE_ENTITY_ID,
    DEFAULT_LEARN_TIMEOUT,
    LearnCommand,
    REMOTE_DOMAIN,
    REMOTE_SERVICE_LEARN_COMMAND,
    REMOTE_SERVICE_SEND_COMMAND,
    TransportType,
)
from .transport import (
    LearnedCommand,
    RFTransport,
    TransportConfiguration,
    TransportConfigurationError,
    TransportError,
    TransportUnavailableError,
)

_LOGGER = logging.getLogger(__name__)
_REQUIRED_SERVICES: Final = (
    REMOTE_SERVICE_LEARN_COMMAND,
    REMOTE_SERVICE_SEND_COMMAND,
)


class BroadlinkTransport(RFTransport):
    """Learn and send RF commands through a Broadlink remote entity."""

    def __init__(self, hass: HomeAssistant, configuration: TransportConfiguration) -> None:
        """Initialize the transport from serialized controller settings."""
        if configuration.transport_type is not TransportType.BROADLINK:
            raise TransportConfigurationError("Broadlink transport type is required")

        remote_entity_id = configuration.settings.get(CONF_REMOTE_ENTITY_ID)
        remote_device = configuration.settings.get(CONF_REMOTE_DEVICE)
        if not remote_entity_id or not remote_device:
            raise TransportConfigurationError("Broadlink settings are incomplete")

        self._hass = hass
        self._remote_entity_id = remote_entity_id
        self._remote_device = remote_device

    @property
    def transport_type(self) -> TransportType:
        """Return the persistent transport identifier."""
        return TransportType.BROADLINK

    async def async_validate(self) -> None:
        """Ensure the selected remote entity and services are available."""
        remote_state = self._hass.states.get(self._remote_entity_id)
        if remote_state is None or remote_state.state in {
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        }:
            raise TransportUnavailableError("The configured Broadlink remote is unavailable")

        if any(
            not self._hass.services.has_service(REMOTE_DOMAIN, service)
            for service in _REQUIRED_SERVICES
        ):
            raise TransportUnavailableError(
                "Required remote services are unavailable for the Broadlink transport"
            )

    async def async_learn(self, command: LearnCommand) -> LearnedCommand:
        """Learn one named RF command through the selected Broadlink remote."""
        await self.async_validate()
        _LOGGER.debug(
            "Learning AMC DC419 RF command via Broadlink",
            extra={
                "command": command.value,
                "remote_entity_id": self._remote_entity_id,
            },
        )
        await self._async_call(
            REMOTE_SERVICE_LEARN_COMMAND,
            {
                ATTR_REMOTE_DEVICE: self._remote_device,
                ATTR_REMOTE_COMMAND: command.value,
                ATTR_COMMAND_TYPE: "rf",
                ATTR_TIMEOUT: DEFAULT_LEARN_TIMEOUT,
            },
        )
        return LearnedCommand(
            command=command,
            transport_type=self.transport_type,
            payload={
                ATTR_REMOTE_DEVICE: self._remote_device,
                ATTR_REMOTE_COMMAND: command.value,
            },
            learned_at=dt_util.utcnow().isoformat(),
        )

    async def async_send(self, command: LearnedCommand) -> None:
        """Send a command whose payload was learned by this transport."""
        if command.transport_type is not self.transport_type:
            raise TransportConfigurationError("Command belongs to another transport")

        remote_device = command.payload.get(ATTR_REMOTE_DEVICE)
        remote_command = command.payload.get(ATTR_REMOTE_COMMAND)
        if not isinstance(remote_device, str) or not isinstance(remote_command, str):
            raise TransportConfigurationError("Broadlink command payload is incomplete")

        await self.async_validate()
        _LOGGER.debug(
            "Sending AMC DC419 RF command via Broadlink",
            extra={
                "command": command.command.value,
                "remote_entity_id": self._remote_entity_id,
            },
        )
        await self._async_call(
            REMOTE_SERVICE_SEND_COMMAND,
            {
                ATTR_REMOTE_DEVICE: remote_device,
                ATTR_REMOTE_COMMAND: remote_command,
            },
        )

    async def _async_call(self, service: str, service_data: dict[str, object]) -> None:
        """Call a remote service and normalize Home Assistant errors."""
        try:
            await self._hass.services.async_call(
                REMOTE_DOMAIN,
                service,
                service_data,
                target={ATTR_ENTITY_ID: self._remote_entity_id},
                blocking=True,
            )
        except HomeAssistantError as err:
            raise TransportError("Broadlink RF operation failed") from err