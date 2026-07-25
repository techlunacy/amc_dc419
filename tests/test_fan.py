"""Tests for the AMC DC419 fan entity."""

from __future__ import annotations

from homeassistant.components.fan import FanEntityFeature
from homeassistant.core import HomeAssistant

from custom_components.amc_dc419.const import LearnCommand
from custom_components.amc_dc419.fan import AMCDC419Fan, fan_command_for_percentage

from .conftest import create_runtime_entry, make_learned_command


def test_fan_speed_mapping_uses_all_six_discrete_commands() -> None:
    """The required Home Assistant percentages map to their RF speed commands."""
    assert [
        fan_command_for_percentage(percentage)
        for percentage in (0, 16, 33, 50, 66, 83, 100)
    ] == [
        (0, LearnCommand.FAN_OFF),
        (16, LearnCommand.FAN_SPEED_1),
        (33, LearnCommand.FAN_SPEED_2),
        (50, LearnCommand.FAN_SPEED_3),
        (66, LearnCommand.FAN_SPEED_4),
        (83, LearnCommand.FAN_SPEED_5),
        (100, LearnCommand.FAN_SPEED_6),
    ]


async def test_fan_entity_sets_speed_without_direction_selector(
    hass: HomeAssistant,
) -> None:
    """Fan speed control does not expose unsupported absolute direction state."""
    entry, transport, command_store = await create_runtime_entry(hass)
    await command_store.async_store_command(
        "controller", make_learned_command(LearnCommand.FAN_SPEED_4)
    )
    fan = AMCDC419Fan(entry)

    await fan.async_set_percentage(66)

    assert [command.command for command in transport.sent] == [
        LearnCommand.FAN_SPEED_4,
    ]
    assert fan.percentage == 66
    assert not fan.supported_features & FanEntityFeature.DIRECTION


async def test_fan_entity_supports_turn_actions(hass: HomeAssistant) -> None:
    """A bare turn-on uses the first speed that reliably starts the fan."""
    entry, transport, command_store = await create_runtime_entry(hass)
    for command in (LearnCommand.FAN_SPEED_2, LearnCommand.FAN_OFF):
        await command_store.async_store_command(
            "controller", make_learned_command(command)
        )
    fan = AMCDC419Fan(entry)

    await fan.async_turn_on(None, None)
    await fan.async_turn_off()

    assert fan.supported_features & FanEntityFeature.TURN_ON
    assert fan.supported_features & FanEntityFeature.TURN_OFF
    assert fan.speed_count == 6
    assert fan.percentage_step == 100 / 6
    assert [command.command for command in transport.sent] == [
        LearnCommand.FAN_SPEED_2,
        LearnCommand.FAN_OFF,
    ]
    assert fan.percentage == 0
