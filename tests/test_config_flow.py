"""Tests for AMC DC419 configuration and command-learning flows."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError

from custom_components.amc_dc419.config_flow import AMCDC419ConfigFlow
from custom_components.amc_dc419.const import (
    ATTR_REMOTE_COMMAND,
    CONF_AREA_ID,
    CONF_FRIENDLY_NAME,
    CONF_REMOTE_ENTITY_ID,
    DOMAIN,
    LEARN_COMMANDS,
    REMOTE_DOMAIN,
    REMOTE_SERVICE_LEARN_COMMAND,
    REMOTE_SERVICE_SEND_COMMAND,
)
from custom_components.amc_dc419.storage import get_command_store


async def test_full_config_flow_learns_and_persists_every_command(
    hass: HomeAssistant,
) -> None:
    """The wizard persists a complete command set only after all steps succeed."""
    learn_calls: list[ServiceCall] = []

    async def handle_learn(call: ServiceCall) -> None:
        """Record each learned remote command."""
        learn_calls.append(call)

    async def handle_send(_call: ServiceCall) -> None:
        """Expose the required remote send service during setup validation."""

    hass.states.async_set("remote.office", "on")
    hass.services.async_register(
        REMOTE_DOMAIN, REMOTE_SERVICE_LEARN_COMMAND, handle_learn
    )
    hass.services.async_register(
        REMOTE_DOMAIN, REMOTE_SERVICE_SEND_COMMAND, handle_send
    )
    user_input = {
        CONF_FRIENDLY_NAME: "Office fan",
        CONF_AREA_ID: "office",
        CONF_REMOTE_ENTITY_ID: "remote.office",
    }

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "learn_command"

    for _command in LEARN_COMMANDS:
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Office fan"
    controller_id = result["data"]["controller_id"]
    assert isinstance(controller_id, str)
    assert [call.data[ATTR_REMOTE_COMMAND] for call in learn_calls] == [
        command.value for command in LEARN_COMMANDS
    ]
    assert set(await get_command_store(hass).async_get_commands(controller_id)) == set(
        LEARN_COMMANDS
    )


async def test_learning_error_keeps_store_empty(hass: HomeAssistant) -> None:
    """A failed learning request does not persist a partial command set."""

    async def handle_learn(_call: ServiceCall) -> None:
        """Simulate a Broadlink learning failure."""
        raise HomeAssistantError("RF learning failed")

    async def handle_send(_call: ServiceCall) -> None:
        """Expose the required remote send service during setup validation."""

    hass.states.async_set("remote.office", "on")
    hass.services.async_register(
        REMOTE_DOMAIN, REMOTE_SERVICE_LEARN_COMMAND, handle_learn
    )
    hass.services.async_register(
        REMOTE_DOMAIN, REMOTE_SERVICE_SEND_COMMAND, handle_send
    )
    user_input = {
        CONF_FRIENDLY_NAME: "Office fan",
        CONF_AREA_ID: "office",
        CONF_REMOTE_ENTITY_ID: "remote.office",
    }
    controller_id = AMCDC419ConfigFlow._create_controller_id(
        user_input[CONF_FRIENDLY_NAME], user_input
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unable_to_learn"}
    assert await get_command_store(hass).async_get_commands(controller_id) == {}


def test_controller_identity_ignores_area() -> None:
    """Moving a controller to another area does not change its stable identity."""
    base_input = {
        CONF_FRIENDLY_NAME: "Office fan",
        CONF_REMOTE_ENTITY_ID: "remote.office",
    }

    office_id = AMCDC419ConfigFlow._create_controller_id(
        "Office fan", {**base_input, CONF_AREA_ID: "office"}
    )
    upstairs_id = AMCDC419ConfigFlow._create_controller_id(
        "Office fan", {**base_input, CONF_AREA_ID: "upstairs"}
    )

    assert office_id == upstairs_id
