"""Broadlink-backed RF transport implementation."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Final

import voluptuous as vol
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_COMMAND_TYPE,
    ATTR_REMOTE_COMMAND,
    ATTR_REMOTE_DEVICE,
    ATTR_TIMEOUT,
    CONF_REMOTE_DEVICE,
    CONF_REMOTE_ENTITY_ID,
    DEFAULT_LEARN_TIMEOUT,
    DOMAIN,
    REMOTE_DOMAIN,
    REMOTE_SERVICE_LEARN_COMMAND,
    REMOTE_SERVICE_SEND_COMMAND,
    LearnCommand,
    TransportType,
)
from .transport import (
    LearnedCommand,
    RFTransport,
    RFTransportProvider,
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

    def __init__(
        self, hass: HomeAssistant, configuration: TransportConfiguration
    ) -> None:
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

    @property
    def availability_entity_ids(self) -> tuple[str, ...]:
        """Return the selected Broadlink remote entity."""
        return (self._remote_entity_id,)

    async def async_validate(self) -> None:
        """Ensure the selected remote entity and services are available."""
        remote_state = self._hass.states.get(self._remote_entity_id)
        if remote_state is None or remote_state.state in {
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        }:
            raise TransportUnavailableError(
                "The configured Broadlink remote is unavailable"
            )

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
        await self._async_call(
            REMOTE_SERVICE_SEND_COMMAND,
            {
                ATTR_REMOTE_DEVICE: self._remote_device,
                ATTR_REMOTE_COMMAND: command.value,
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
        except (HomeAssistantError, ValueError) as err:
            if service == REMOTE_SERVICE_SEND_COMMAND and str(err).startswith(
                "Command not found:"
            ):
                raise TransportError(
                    "Broadlink is missing a learned RF command. Relearn the "
                    "command through the AMC DC419 integration before trying again."
                ) from err
            raise TransportError("Broadlink RF operation failed") from err


class BroadlinkTransportProvider(RFTransportProvider):
    """Provide configuration and runtime transports for Broadlink remotes."""

    @property
    def transport_type(self) -> TransportType:
        """Return the persistent Broadlink transport identifier."""
        return TransportType.BROADLINK

    def config_flow_schema(self) -> Mapping[object, object]:
        """Return fields required to configure a Broadlink remote."""
        return {
            vol.Required(CONF_REMOTE_ENTITY_ID): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=REMOTE_DOMAIN)
            )
        }

    def reconfigure_flow_schema(
        self, configuration: TransportConfiguration
    ) -> Mapping[object, object]:
        """Return the selected Broadlink remote as the editable default."""
        remote_entity_id = configuration.settings.get(CONF_REMOTE_ENTITY_ID)
        if not isinstance(remote_entity_id, str):
            raise TransportConfigurationError("Broadlink settings are incomplete")
        return {
            vol.Required(
                CONF_REMOTE_ENTITY_ID, default=remote_entity_id
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=REMOTE_DOMAIN)
            )
        }

    async def async_create_configuration(
        self,
        hass: HomeAssistant,
        controller_id: str,
        user_input: Mapping[str, object],
    ) -> TransportConfiguration:
        """Validate Broadlink setup input and return durable settings."""
        remote_entity_id = user_input.get(CONF_REMOTE_ENTITY_ID)
        if not isinstance(remote_entity_id, str) or not remote_entity_id:
            raise TransportConfigurationError("A Broadlink remote is required")

        configuration = TransportConfiguration(
            transport_type=self.transport_type,
            settings={
                CONF_REMOTE_ENTITY_ID: remote_entity_id,
                CONF_REMOTE_DEVICE: f"{DOMAIN}_{controller_id}",
            },
        )
        await BroadlinkTransport(hass, configuration).async_validate()
        return configuration

    def create_transport(
        self, hass: HomeAssistant, configuration: TransportConfiguration
    ) -> BroadlinkTransport:
        """Create a Broadlink transport from durable settings."""
        return BroadlinkTransport(hass, configuration)


BROADLINK_TRANSPORT_PROVIDER: Final = BroadlinkTransportProvider()
