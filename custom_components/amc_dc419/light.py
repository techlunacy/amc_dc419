"""Light platform for AMC DC419 controllers."""

from __future__ import annotations

from dataclasses import replace
from math import ceil
from typing import Any, Final

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode,
    LightEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AMCDC419ConfigEntry
from .const import (
    DEFAULT_BRIGHTNESS,
    DEFAULT_COLOR_TEMP_KELVIN,
    MAX_COLOR_TEMP_KELVIN,
    MIN_COLOR_TEMP_KELVIN,
    LearnCommand,
)
from .entity import AMCDC419Entity, AMCDC419EntityDescription

LIGHT_DESCRIPTION: Final = AMCDC419EntityDescription(
    key="light",
    translation_key="light",
)


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: AMCDC419ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the AMC DC419 light entity for a config entry."""
    async_add_entities([AMCDC419Light(entry)])


class AMCDC419Light(AMCDC419Entity, LightEntity):
    """Optimistically control the light portion of an AMC DC419 controller."""

    entity_description = LIGHT_DESCRIPTION
    _attr_supported_color_modes = frozenset({ColorMode.COLOR_TEMP})
    _attr_min_color_temp_kelvin = MIN_COLOR_TEMP_KELVIN
    _attr_max_color_temp_kelvin = MAX_COLOR_TEMP_KELVIN

    def __init__(self, entry: AMCDC419ConfigEntry) -> None:
        """Initialize the light for a controller config entry."""
        super().__init__(entry, LIGHT_DESCRIPTION)

    @property
    def is_on(self) -> bool | None:
        """Return whether the light is optimistically on."""
        return self.coordinator.data.light_is_on

    @property
    def brightness(self) -> int | None:
        """Return the optimistic Home Assistant brightness value."""
        return self.coordinator.data.brightness

    @property
    def color_mode(self) -> ColorMode:
        """Return the only supported color mode."""
        return ColorMode.COLOR_TEMP

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return the optimistic color temperature in Kelvin."""
        return self.coordinator.data.colour_temperature

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light and apply requested brightness or color temperature."""
        requested_brightness = _validated_brightness(kwargs.get(ATTR_BRIGHTNESS))
        requested_color_temp = _validated_color_temp(kwargs.get(ATTR_COLOR_TEMP_KELVIN))
        current_brightness = (
            self.coordinator.data.brightness
            if self.coordinator.data.brightness is not None
            else DEFAULT_BRIGHTNESS
        )
        current_color_temp = (
            self.coordinator.data.colour_temperature
            if self.coordinator.data.colour_temperature is not None
            else DEFAULT_COLOR_TEMP_KELVIN
        )
        target_brightness = requested_brightness or current_brightness
        target_color_temp = requested_color_temp or current_color_temp

        commands = [LearnCommand.LIGHT_TOGGLE]
        commands.extend(
            repeated_adjustment_commands(
                current_brightness,
                target_brightness,
                self.coordinator.options.brightness_step_count,
                LearnCommand.BRIGHTNESS_UP,
                LearnCommand.BRIGHTNESS_DOWN,
            )
        )
        commands.extend(
            repeated_adjustment_commands(
                current_color_temp,
                target_color_temp,
                self.coordinator.options.colour_step_count,
                LearnCommand.COLOUR_UP,
                LearnCommand.COLOUR_DOWN,
            )
        )

        await self.coordinator.async_send_commands(
            commands,
            lambda state: replace(
                state,
                light_is_on=True,
                brightness=target_brightness,
                colour_temperature=target_color_temp,
            ),
        )

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Turn off the light while retaining its last optimistic levels."""
        await self.coordinator.async_send_commands(
            (LearnCommand.LIGHT_TOGGLE,),
            lambda state: replace(state, light_is_on=False),
        )


def repeated_adjustment_commands(
    current: int,
    requested: int,
    step_size: int,
    increase_command: LearnCommand,
    decrease_command: LearnCommand,
) -> tuple[LearnCommand, ...]:
    """Return the RF presses needed to move one optimistic value toward another."""
    if step_size <= 0:
        raise ValueError("RF adjustment step size must be greater than zero")

    difference = requested - current
    if difference == 0:
        return ()

    command = increase_command if difference > 0 else decrease_command
    return (command,) * ceil(abs(difference) / step_size)


def _validated_brightness(value: object) -> int | None:
    """Return a Home Assistant brightness value when one was requested."""
    if not isinstance(value, int):
        return None
    return min(max(value, 1), DEFAULT_BRIGHTNESS)


def _validated_color_temp(value: object) -> int | None:
    """Return a supported Kelvin color temperature when one was requested."""
    if not isinstance(value, int):
        return None
    return min(max(value, MIN_COLOR_TEMP_KELVIN), MAX_COLOR_TEMP_KELVIN)
