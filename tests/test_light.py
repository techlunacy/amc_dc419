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


async def test_light_entity_sends_ordered_brightness_commands(
    hass: HomeAssistant,
) -> None:
    """A known-off light toggles on before applying the requested brightness."""
    entry, transport, command_store = await create_runtime_entry(hass)
    for command in (LearnCommand.LIGHT_TOGGLE, LearnCommand.BRIGHTNESS_UP):
        await command_store.async_store_command(
            "controller", make_learned_command(command)
        )
    entry.runtime_data.coordinator.async_set_updated_data(
        replace(
            entry.runtime_data.coordinator.data,
            light_is_on=False,
            brightness=80,
        )
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


async def test_light_entity_unchanged_brightness_is_a_no_op(
    hass: HomeAssistant,
) -> None:
    """An already-applied brightness value does not send an RF command."""
    entry, transport, _command_store = await create_runtime_entry(hass)
    entry.runtime_data.coordinator.async_set_updated_data(
        replace(
            entry.runtime_data.coordinator.data,
            light_is_on=True,
            brightness=160,
        )
    )
    light = AMCDC419Light(entry)

    await light.async_turn_on(**{ATTR_BRIGHTNESS: 160})

    assert transport.sent == []
    assert light.is_on is True
    assert light.brightness == 160


async def test_light_entity_brightness_change_preserves_unknown_power_state(
    hass: HomeAssistant,
) -> None:
    """A brightness adjustment does not toggle a light with an unknown power state."""
    entry, transport, command_store = await create_runtime_entry(hass)
    await command_store.async_store_command(
        "controller", make_learned_command(LearnCommand.BRIGHTNESS_UP)
    )
    entry.runtime_data.coordinator.async_set_updated_data(
        replace(entry.runtime_data.coordinator.data, brightness=80)
    )
    light = AMCDC419Light(entry)

    await light.async_turn_on(**{ATTR_BRIGHTNESS: 160})

    assert [command.command for command in transport.sent] == [
        LearnCommand.BRIGHTNESS_UP,
        LearnCommand.BRIGHTNESS_UP,
        LearnCommand.BRIGHTNESS_UP,
        LearnCommand.BRIGHTNESS_UP,
    ]
    assert light.is_on is None
    assert light.brightness == 160


async def test_light_entity_brightness_change_does_not_toggle_light(
    hass: HomeAssistant,
) -> None:
    """A brightness adjustment does not toggle a light already known to be on."""
    entry, transport, command_store = await create_runtime_entry(hass)
    await command_store.async_store_command(
        "controller", make_learned_command(LearnCommand.BRIGHTNESS_UP)
    )
    entry.runtime_data.coordinator.async_set_updated_data(
        replace(
            entry.runtime_data.coordinator.data,
            light_is_on=True,
            brightness=80,
        )
    )
    light = AMCDC419Light(entry)

    await light.async_turn_on(**{ATTR_BRIGHTNESS: 160})

    assert [command.command for command in transport.sent] == [
        LearnCommand.BRIGHTNESS_UP,
        LearnCommand.BRIGHTNESS_UP,
        LearnCommand.BRIGHTNESS_UP,
        LearnCommand.BRIGHTNESS_UP,
    ]
    assert light.is_on is True
    assert light.brightness == 160


async def test_light_entity_turn_on_never_sends_colour_cycle(
    hass: HomeAssistant,
) -> None:
    """A turn-on only sends the handset toggle."""
    entry, transport, command_store = await create_runtime_entry(hass)
    await command_store.async_store_command(
        "controller", make_learned_command(LearnCommand.LIGHT_TOGGLE)
    )
    light = AMCDC419Light(entry)

    await light.async_turn_on(**{ATTR_COLOR_TEMP_KELVIN: 4_500})

    assert [command.command for command in transport.sent] == [
        LearnCommand.LIGHT_TOGGLE,
    ]


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
