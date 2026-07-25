"""Fan platform for AMC DC419 controllers."""

from __future__ import annotations

from dataclasses import replace
from typing import Final

from homeassistant.components.fan import (
    DIRECTION_FORWARD,
    DIRECTION_REVERSE,
    FanEntity,
    FanEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AMCDC419ConfigEntry
from .const import LearnCommand
from .entity import AMCDC419Entity, AMCDC419EntityDescription

FAN_PERCENTAGE_COMMANDS: Final[dict[int, LearnCommand]] = {
    0: LearnCommand.FAN_OFF,
    16: LearnCommand.FAN_SPEED_1,
    33: LearnCommand.FAN_SPEED_2,
    50: LearnCommand.FAN_SPEED_3,
    66: LearnCommand.FAN_SPEED_4,
    83: LearnCommand.FAN_SPEED_5,
    100: LearnCommand.FAN_SPEED_6,
}
FAN_DESCRIPTION: Final = AMCDC419EntityDescription(
    key="fan",
    translation_key="fan",
)


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: AMCDC419ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the AMC DC419 fan entity for a config entry."""
    async_add_entities([AMCDC419Fan(entry)])


class AMCDC419Fan(AMCDC419Entity, FanEntity):
    """Optimistically control the fan portion of an AMC DC419 controller."""

    entity_description = FAN_DESCRIPTION
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.DIRECTION
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )

    def __init__(self, entry: AMCDC419ConfigEntry) -> None:
        """Initialize the fan for a controller config entry."""
        super().__init__(entry, FAN_DESCRIPTION)

    @property
    def is_on(self) -> bool | None:
        """Return whether the fan is optimistically on."""
        percentage = self.coordinator.data.fan_percentage
        return None if percentage is None else percentage > 0

    @property
    def percentage(self) -> int | None:
        """Return the nearest selected fan speed percentage."""
        return self.coordinator.data.fan_percentage

    @property
    def current_direction(self) -> str | None:
        """Return the optimistic fan direction."""
        return self.coordinator.data.fan_direction

    async def async_turn_on(
        self,
        percentage: int | None = None,
        _preset_mode: str | None = None,
        **_kwargs: object,
    ) -> None:
        """Turn on the fan at a requested, remembered, or first available speed."""
        await self.async_set_percentage(
            percentage
            if percentage is not None
            else self.coordinator.data.fan_percentage or 16
        )

    async def async_turn_off(self, **_kwargs: object) -> None:
        """Turn off the fan."""
        await self.async_set_percentage(0)

    async def async_set_percentage(self, percentage: int) -> None:
        """Set fan speed using the nearest discrete DC419 RF command."""
        selected_percentage, command = fan_command_for_percentage(percentage)
        await self.coordinator.async_send_commands(
            (command,),
            lambda state: replace(state, fan_percentage=selected_percentage),
        )

    async def async_set_direction(self, direction: str) -> None:
        """Toggle and optimistically store a requested forward or reverse direction."""
        if direction not in {DIRECTION_FORWARD, DIRECTION_REVERSE}:
            raise ValueError(f"Unsupported fan direction: {direction}")
        if self.coordinator.data.fan_direction == direction:
            return

        await self.coordinator.async_send_commands(
            (LearnCommand.DIRECTION_TOGGLE,),
            lambda state: replace(state, fan_direction=direction),
        )


def fan_command_for_percentage(percentage: int) -> tuple[int, LearnCommand]:
    """Return the nearest discrete speed and command for a requested percentage."""
    if percentage <= 0:
        return 0, LearnCommand.FAN_OFF

    clamped_percentage = min(percentage, 100)
    available_percentages = tuple(value for value in FAN_PERCENTAGE_COMMANDS if value)
    selected_percentage = min(
        available_percentages,
        key=lambda available: (abs(available - clamped_percentage), -available),
    )
    return selected_percentage, FAN_PERCENTAGE_COMMANDS[selected_percentage]
