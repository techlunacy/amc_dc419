"""Configuration flow for AMC DC419 controllers."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_AREA_ID,
    CONF_CONTROLLER_ID,
    CONF_FRIENDLY_NAME,
    DOMAIN,
    LEARN_COMMAND_LABELS,
    LEARN_COMMANDS,
    LearnCommand,
    TransportType,
)
from .storage import get_command_store
from .transport import (
    LearnedCommand,
    RFTransport,
    TransportConfiguration,
    TransportConfigurationError,
    TransportError,
    create_transport,
    get_transport_provider,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ControllerConfiguration:
    """Controller metadata collected before command learning begins."""

    controller_id: str
    friendly_name: str
    area_id: str
    transport_configuration: TransportConfiguration

    def as_entry_data(self) -> dict[str, object]:
        """Return the serializable configuration-entry data."""
        entry_data: dict[str, object] = {
            CONF_CONTROLLER_ID: self.controller_id,
            CONF_FRIENDLY_NAME: self.friendly_name,
            CONF_AREA_ID: self.area_id,
        }
        entry_data.update(self.transport_configuration.as_entry_data())
        return entry_data


class AMCDC419ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Manage configuration and RF command learning for AMC DC419 controllers."""

    VERSION = 1
    MINOR_VERSION = 2

    def __init__(self) -> None:
        """Initialize state for one configuration-flow session."""
        super().__init__()
        self._controller: ControllerConfiguration | None = None
        self._learn_command_index = 0
        self._learned_commands: dict[LearnCommand, LearnedCommand] = {}
        self._transport: RFTransport | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the controller metadata step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            friendly_name = str(user_input[CONF_FRIENDLY_NAME]).strip()

            if not friendly_name or len(friendly_name) > 255:
                errors[CONF_FRIENDLY_NAME] = "invalid_name"
            else:
                transport_provider = get_transport_provider(TransportType.BROADLINK)
                controller_id = self._create_controller_id(friendly_name, user_input)
                try:
                    transport_configuration = (
                        await transport_provider.async_create_configuration(
                            self.hass,
                            controller_id,
                            user_input,
                        )
                    )
                except (TransportConfigurationError, TransportError):
                    _LOGGER.warning(
                        "Unable to configure AMC DC419 RF transport",
                        extra={"transport": transport_provider.transport_type.value},
                    )
                    errors["base"] = "cannot_connect"
                else:
                    await self.async_set_unique_id(controller_id)
                    self._abort_if_unique_id_configured()

                    self._controller = ControllerConfiguration(
                        controller_id=controller_id,
                        friendly_name=friendly_name,
                        area_id=str(user_input[CONF_AREA_ID]),
                        transport_configuration=transport_configuration,
                    )
                    self._learn_command_index = 0
                    self._learned_commands = {}
                    self._transport = create_transport(
                        self.hass, transport_configuration
                    )
                    return await self.async_step_learn_command()

        schema: dict[object, object] = {
            vol.Required(CONF_FRIENDLY_NAME): selector.TextSelector(),
            vol.Required(CONF_AREA_ID): selector.AreaSelector(),
        }
        schema.update(
            get_transport_provider(TransportType.BROADLINK).config_flow_schema()
        )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(schema),
            errors=errors,
        )

    async def async_step_learn_command(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Learn each required RF command through the selected Broadlink remote."""
        if self._controller is None or self._transport is None:
            return self.async_abort(reason="invalid_flow_state")

        command = LEARN_COMMANDS[self._learn_command_index]
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                learned_command = await self._transport.async_learn(command)
            except TransportError:
                _LOGGER.warning(
                    "Unable to learn AMC DC419 RF command",
                    extra={
                        "command": command.value,
                        "controller_id": self._controller.controller_id,
                        "transport": self._transport.transport_type.value,
                    },
                )
                errors["base"] = "unable_to_learn"
            else:
                self._learned_commands[command] = learned_command
                self._learn_command_index += 1

                if self._learn_command_index == len(LEARN_COMMANDS):
                    await get_command_store(self.hass).async_store_commands(
                        self._controller.controller_id,
                        self._learned_commands,
                    )
                    return self.async_create_entry(
                        title=self._controller.friendly_name,
                        data=self._controller.as_entry_data(),
                    )

                return await self.async_step_learn_command()

        return self.async_show_form(
            step_id="learn_command",
            description_placeholders={"command": LEARN_COMMAND_LABELS[command]},
            errors=errors,
        )

    @staticmethod
    def _create_controller_id(
        friendly_name: str, transport_data: Mapping[str, object]
    ) -> str:
        """Return a stable local identifier for a user-configured controller."""
        identity = json.dumps(
            {
                "friendly_name": friendly_name,
                "transport": {
                    key: value
                    for key, value in transport_data.items()
                    if key not in {CONF_AREA_ID, CONF_FRIENDLY_NAME}
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(identity.encode()).hexdigest()
