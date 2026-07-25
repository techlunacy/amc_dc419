"""Tests for AMC DC419 configuration and command-learning flows."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.amc_dc419.config_flow import AMCDC419ConfigFlow
from custom_components.amc_dc419.const import (
    ATTR_REMOTE_COMMAND,
    CONF_AREA_ID,
    CONF_BRIGHTNESS_STEP_COUNT,
    CONF_COLOUR_STEP_COUNT,
    CONF_FRIENDLY_NAME,
    CONF_OPTIMISTIC_TIMEOUT,
    CONF_REMOTE_DEVICE,
    CONF_REMOTE_ENTITY_ID,
    CONF_REPEAT_DELAY,
    CONF_RETRY_COUNT,
    CONF_TRANSPORT,
    CONF_TRANSPORT_TYPE,
    DOMAIN,
    LEARN_COMMANDS,
    REMOTE_DOMAIN,
    REMOTE_SERVICE_LEARN_COMMAND,
    REMOTE_SERVICE_SEND_COMMAND,
    TransportType,
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


async def test_options_flow_saves_rf_behavior_options(hass: HomeAssistant) -> None:
    """The options UI persists every command-timing and state-expiry control."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    options = {
        CONF_REPEAT_DELAY: 0.5,
        CONF_BRIGHTNESS_STEP_COUNT: 16,
        CONF_COLOUR_STEP_COUNT: 200,
        CONF_RETRY_COUNT: 2,
        CONF_OPTIMISTIC_TIMEOUT: 60,
    }

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], options
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == options


async def test_reconfigure_updates_metadata_and_transport_settings(
    hass: HomeAssistant,
) -> None:
    """A user can move a controller to another validated Broadlink remote."""

    async def handle_remote(_call: ServiceCall) -> None:
        """Expose the services needed to validate Broadlink configuration."""

    hass.states.async_set("remote.office", "on")
    hass.states.async_set("remote.lounge", "on")
    hass.services.async_register(
        REMOTE_DOMAIN, REMOTE_SERVICE_LEARN_COMMAND, handle_remote
    )
    hass.services.async_register(
        REMOTE_DOMAIN, REMOTE_SERVICE_SEND_COMMAND, handle_remote
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Office fan",
        unique_id="controller",
        data={
            "controller_id": "controller",
            CONF_FRIENDLY_NAME: "Office fan",
            CONF_AREA_ID: "office",
            CONF_TRANSPORT_TYPE: TransportType.BROADLINK.value,
            CONF_TRANSPORT: {
                CONF_REMOTE_ENTITY_ID: "remote.office",
                CONF_REMOTE_DEVICE: "amc_dc419_controller",
            },
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_FRIENDLY_NAME: "Lounge fan",
            CONF_AREA_ID: "lounge",
            CONF_REMOTE_ENTITY_ID: "remote.lounge",
        },
    )

    assert result["type"] is FlowResultType.ABORT
    assert entry.title == "Lounge fan"
    assert entry.data["controller_id"] == "controller"
    assert entry.data[CONF_AREA_ID] == "lounge"
    assert entry.data[CONF_TRANSPORT][CONF_REMOTE_ENTITY_ID] == "remote.lounge"
