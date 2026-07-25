"""Tests for the AMC DC419 light entity."""

from __future__ import annotations

from dataclasses import replace

from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_COLOR_TEMP_KELVIN
from homeassistant.core import HomeAssistant

from custom_components.amc_dc419.const import LearnCommand
from custom_components.amc_dc419.light import (
    AMCDC419Light,
    repeated_adjustment_commands,
)

from .conftest import create_runtime_entry, make_learned_command


def test_brightness_calculation_uses_four_presses_for_example() -> None:
    """Brightness 80 to 160 emits four 20-unit Brightness Up presses."""
    assert (
        repeated_adjustment_commands(
            80,
            160,
            20,
            LearnCommand.BRIGHTNESS_UP,
            LearnCommand.BRIGHTNESS_DOWN,
        )
        == (LearnCommand.BRIGHTNESS_UP,) * 4
    )


def test_colour_calculation_selects_direction_and_rounds_up() -> None:
    """Colour temperature changes select the right command and enough presses."""
    assert (
        repeated_adjustment_commands(
            4_000,
            4_450,
            250,
            LearnCommand.COLOUR_UP,
            LearnCommand.COLOUR_DOWN,
        )
        == (LearnCommand.COLOUR_UP,) * 2
    )
    assert (
        repeated_adjustment_commands(
            4_000,
            3_600,
            250,
            LearnCommand.COLOUR_UP,
            LearnCommand.COLOUR_DOWN,
        )
        == (LearnCommand.COLOUR_DOWN,) * 2
    )


async def test_light_entity_sends_ordered_brightness_commands(
    hass: HomeAssistant,
) -> None:
    """Turning on at a requested brightness sends a toggle then repeated presses."""
    entry, transport, command_store = await create_runtime_entry(hass)
    for command in (LearnCommand.LIGHT_TOGGLE, LearnCommand.BRIGHTNESS_UP):
        await command_store.async_store_command(
            "controller", make_learned_command(command)
        )
    entry.runtime_data.coordinator.async_set_updated_data(
        replace(entry.runtime_data.coordinator.data, brightness=80)
    )
    light = AMCDC419Light(entry)

    await light.async_turn_on(**{ATTR_BRIGHTNESS: 160})

    assert [command.command for command in transport.sent] == [
        LearnCommand.LIGHT_TOGGLE,
        LearnCommand.BRIGHTNESS_UP,
        LearnCommand.BRIGHTNESS_UP,
        LearnCommand.BRIGHTNESS_UP,
        LearnCommand.BRIGHTNESS_UP,
    ]
    assert light.is_on is True
    assert light.brightness == 160


async def test_light_entity_sends_colour_temperature_commands(
    hass: HomeAssistant,
) -> None:
    """Requested Kelvin temperature translates to repeated Colour Up commands."""
    entry, transport, command_store = await create_runtime_entry(hass)
    for command in (LearnCommand.LIGHT_TOGGLE, LearnCommand.COLOUR_UP):
        await command_store.async_store_command(
            "controller", make_learned_command(command)
        )
    entry.runtime_data.coordinator.async_set_updated_data(
        replace(entry.runtime_data.coordinator.data, colour_temperature=4_000)
    )
    light = AMCDC419Light(entry)

    await light.async_turn_on(**{ATTR_COLOR_TEMP_KELVIN: 4_500})

    assert [command.command for command in transport.sent] == [
        LearnCommand.LIGHT_TOGGLE,
        LearnCommand.COLOUR_UP,
        LearnCommand.COLOUR_UP,
    ]
    assert light.color_temp_kelvin == 4_500


async def test_light_entity_uses_toggle_command_to_turn_off(
    hass: HomeAssistant,
) -> None:
    """Turning off sends the same handset toggle used to turn the light on."""
    entry, transport, command_store = await create_runtime_entry(hass)
    await command_store.async_store_command(
        "controller", make_learned_command(LearnCommand.LIGHT_TOGGLE)
    )
    entry.runtime_data.coordinator.async_set_updated_data(
        replace(entry.runtime_data.coordinator.data, light_is_on=True, brightness=160)
    )
    light = AMCDC419Light(entry)

    await light.async_turn_off()

    assert [command.command for command in transport.sent] == [
        LearnCommand.LIGHT_TOGGLE
    ]
    assert light.is_on is False
    assert light.brightness == 160
