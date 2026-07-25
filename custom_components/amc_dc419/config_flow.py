"""Configuration flow for AMC DC419 controllers."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any
from uuid import uuid4

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector
from homeassistant.util import slugify

from .const import (
    ATTR_COMMAND_TYPE,
    ATTR_REMOTE_COMMAND,
    ATTR_REMOTE_DEVICE,
    ATTR_TIMEOUT,
    CONF_AREA_ID,
    CONF_CONTROLLER_ID,
    CONF_FRIENDLY_NAME,
    CONF_REMOTE_DEVICE,
    CONF_REMOTE_ENTITY_ID,
    DEFAULT_LEARN_TIMEOUT,
    DOMAIN,
    LEARN_COMMAND_LABELS,
    LEARN_COMMANDS,
    LearnCommand,
    REMOTE_DOMAIN,
    REMOTE_SERVICE_LEARN_COMMAND,
)
from .storage import get_command_store

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ControllerConfiguration:
    """Controller metadata collected before command learning begins."""

    controller_id: str
    friendly_name: str
    area_id: str
    remote_entity_id: str
    remote_device: str

    def as_entry_data(self) -> dict[str, str]:
        """Return the serializable configuration-entry data."""
        return {
            CONF_CONTROLLER_ID: self.controller_id,
            CONF_FRIENDLY_NAME: self.friendly_name,
            CONF_AREA_ID: self.area_id,
            CONF_REMOTE_ENTITY_ID: self.remote_entity_id,
            CONF_REMOTE_DEVICE: self.remote_device,
        }


class AMCDC419ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Manage configuration and RF command learning for AMC DC419 controllers."""

    VERSION = 1
    MINOR_VERSION = 1

    _controller: ControllerConfiguration | None = None
    _learn_command_index = 0

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the controller metadata step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            friendly_name = str(user_input[CONF_FRIENDLY_NAME]).strip()
            remote_entity_id = str(user_input[CONF_REMOTE_ENTITY_ID])

            if not friendly_name or len(friendly_name) > 255:
                errors[CONF_FRIENDLY_NAME] = "invalid_name"
            elif not self._is_configured_remote(self.hass, remote_entity_id):
                errors[CONF_REMOTE_ENTITY_ID] = "invalid_remote"
            else:
                controller_id = uuid4().hex
                await self.async_set_unique_id(controller_id)
                self._abort_if_unique_id_configured()

                self._controller = ControllerConfiguration(
                    controller_id=controller_id,
                    friendly_name=friendly_name,
                    area_id=str(user_input[CONF_AREA_ID]),
                    remote_entity_id=remote_entity_id,
                    remote_device=(
                        f"{DOMAIN}_{slugify(friendly_name)}_{controller_id[:8]}"
                    ),
                )
                self._learn_command_index = 0
                return await self.async_step_learn_command()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_FRIENDLY_NAME): selector.TextSelector(),
                    vol.Required(CONF_AREA_ID): selector.AreaSelector(),
                    vol.Required(CONF_REMOTE_ENTITY_ID): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=REMOTE_DOMAIN)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_learn_command(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Learn each required RF command through the selected Broadlink remote."""
        if self._controller is None:
            return self.async_abort(reason="invalid_flow_state")

        command = LEARN_COMMANDS[self._learn_command_index]
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await self._async_learn_command(command)
            except HomeAssistantError:
                _LOGGER.warning(
                    "Unable to learn AMC DC419 RF command",
                    extra={
                        "command": command.value,
                        "controller_id": self._controller.controller_id,
                        "remote_entity_id": self._controller.remote_entity_id,
                    },
                )
                errors["base"] = "unable_to_learn"
            else:
                await get_command_store(self.hass).async_store_command(
                    controller_id=self._controller.controller_id,
                    command=command,
                    remote_entity_id=self._controller.remote_entity_id,
                    remote_device=self._controller.remote_device,
                )
                self._learn_command_index += 1

                if self._learn_command_index == len(LEARN_COMMANDS):
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

    async def _async_learn_command(self, command: LearnCommand) -> None:
        """Ask the selected Broadlink remote to learn one RF command."""
        assert self._controller is not None
        _LOGGER.debug(
            "Starting AMC DC419 RF command learning",
            extra={
                "command": command.value,
                "controller_id": self._controller.controller_id,
                "remote_entity_id": self._controller.remote_entity_id,
            },
        )
        await self.hass.services.async_call(
            REMOTE_DOMAIN,
            REMOTE_SERVICE_LEARN_COMMAND,
            {
                ATTR_REMOTE_DEVICE: self._controller.remote_device,
                ATTR_REMOTE_COMMAND: command.value,
                ATTR_COMMAND_TYPE: "rf",
                ATTR_TIMEOUT: DEFAULT_LEARN_TIMEOUT,
            },
            target={ATTR_ENTITY_ID: self._controller.remote_entity_id},
            blocking=True,
        )

    @staticmethod
    def _is_configured_remote(hass: HomeAssistant, entity_id: str) -> bool:
        """Return whether an existing entity is a remote entity."""
        return entity_id.startswith(f"{REMOTE_DOMAIN}.") and hass.states.get(entity_id) is not None