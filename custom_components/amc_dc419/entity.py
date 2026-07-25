"""Shared entity support for AMC DC419 controllers."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import AMCDC419ConfigEntry
from .const import CONF_CONTROLLER_ID, DOMAIN
from .coordinator import AMCDC419Coordinator


@dataclass(frozen=True, kw_only=True)
class AMCDC419EntityDescription(EntityDescription):
    """Describe an AMC DC419 entity."""


class AMCDC419Entity(CoordinatorEntity[AMCDC419Coordinator]):
    """Base entity backed by one AMC DC419 controller coordinator."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: AMCDC419ConfigEntry,
        description: AMCDC419EntityDescription,
    ) -> None:
        """Initialize entity metadata from its controller config entry."""
        super().__init__(entry.runtime_data.coordinator)
        controller_id = entry.data[CONF_CONTROLLER_ID]
        assert isinstance(controller_id, str)
        self.entity_description = description
        self._attr_unique_id = f"{controller_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, controller_id)},
            manufacturer="AMC",
            model="DC419",
            name=entry.title,
        )

    @property
    def available(self) -> bool:
        """Return whether the controller RF transport is available."""
        return super().available and self.coordinator.transport_available
