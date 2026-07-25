"""Light platform for AMC DC419 controllers."""

from __future__ import annotations

from dataclasses import replace
from math import ceil
from typing import Any, Final

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AMCDC419ConfigEntry
from .const import (
    DEFAULT_BRIGHTNESS,
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
    _attr_supported_color_modes = frozenset({ColorMode.BRIGHTNESS})

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
        return ColorMode.BRIGHTNESS

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light and apply a requested brightness."""
        requested_brightness = _validated_brightness(kwargs.get(ATTR_BRIGHTNESS))
        current_brightness = (
            self.coordinator.data.brightness
            if self.coordinator.data.brightness is not None
            else DEFAULT_BRIGHTNESS
        )
        target_brightness = requested_brightness or current_brightness

        should_toggle = self.coordinator.data.light_is_on is False or (
            requested_brightness is None and self.coordinator.data.light_is_on is None
        )
        commands = [LearnCommand.LIGHT_TOGGLE] if should_toggle else []
        commands.extend(
            repeated_adjustment_commands(
                current_brightness,
                target_brightness,
                self.coordinator.options.brightness_step_count,
                LearnCommand.BRIGHTNESS_UP,
                LearnCommand.BRIGHTNESS_DOWN,
            )
        )
        if not commands:
            return

        await self.coordinator.async_send_commands(
            commands,
            lambda state: replace(
                state,
                light_is_on=True if should_toggle else state.light_is_on,
                brightness=target_brightness,
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
