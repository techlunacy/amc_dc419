"""Tests for the AMC DC419 button entities."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from custom_components.amc_dc419.button import AMCDC419DirectionToggleButton
from custom_components.amc_dc419.const import LearnCommand

from .conftest import create_runtime_entry, make_learned_command


async def test_direction_toggle_button_sends_relative_rf_command(
    hass: HomeAssistant,
) -> None:
    """The button sends the learned relative direction command once."""
    entry, transport, command_store = await create_runtime_entry(hass)
    await command_store.async_store_command(
        "controller", make_learned_command(LearnCommand.DIRECTION_TOGGLE)
    )
    button = AMCDC419DirectionToggleButton(entry)

    await button.async_press()

    assert [command.command for command in transport.sent] == [
        LearnCommand.DIRECTION_TOGGLE
    ]
