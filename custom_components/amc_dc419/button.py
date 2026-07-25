"""Button platform for AMC DC419 controllers."""

from __future__ import annotations

from typing import Final

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AMCDC419ConfigEntry
from .const import LearnCommand
from .entity import AMCDC419Entity, AMCDC419EntityDescription

DIRECTION_TOGGLE_DESCRIPTION: Final = AMCDC419EntityDescription(
    key="direction_toggle",
    translation_key="direction_toggle",
)


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: AMCDC419ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the AMC DC419 direction-toggle button for a config entry."""
    async_add_entities([AMCDC419DirectionToggleButton(entry)])


class AMCDC419DirectionToggleButton(AMCDC419Entity, ButtonEntity):
    """Send the controller's relative direction-toggle command."""

    entity_description = DIRECTION_TOGGLE_DESCRIPTION

    def __init__(self, entry: AMCDC419ConfigEntry) -> None:
        """Initialize the direction-toggle button for a controller."""
        super().__init__(entry, DIRECTION_TOGGLE_DESCRIPTION)

    async def async_press(self) -> None:
        """Toggle the physical fan direction without inferring its result."""
        await self.coordinator.async_send_commands((LearnCommand.DIRECTION_TOGGLE,))
