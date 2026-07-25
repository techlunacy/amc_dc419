"""Persistent optimistic controller state for AMC DC419 controllers."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DATA_OPTIMISTIC_STATE_STORE, DOMAIN

STORAGE_KEY: Final = f"{DOMAIN}.optimistic_state"
STORAGE_VERSION: Final = 1


@dataclass(frozen=True, slots=True)
class StoredOptimisticState:
    """One controller's persisted, inferred state and its update time."""

    fan_percentage: int | None
    light_is_on: bool | None
    brightness: int | None
    updated_at: datetime

    @classmethod
    def from_storage_data(cls, data: object) -> StoredOptimisticState | None:
        """Deserialize a valid state record and discard malformed data."""
        if not isinstance(data, Mapping):
            return None

        fan_percentage = data.get("fan_percentage")
        light_is_on = data.get("light_is_on")
        brightness = data.get("brightness")
        updated_at = data.get("updated_at")
        if (
            not isinstance(fan_percentage, int | None)
            or isinstance(fan_percentage, bool)
            or not isinstance(light_is_on, bool | None)
            or not isinstance(brightness, int | None)
            or isinstance(brightness, bool)
            or not isinstance(updated_at, str)
        ):
            return None

        try:
            timestamp = datetime.fromisoformat(updated_at)
        except ValueError:
            return None
        if timestamp.tzinfo is None:
            return None

        return cls(
            fan_percentage=fan_percentage,
            light_is_on=light_is_on,
            brightness=brightness,
            updated_at=timestamp,
        )

    def as_storage_data(self) -> dict[str, int | str | bool | None]:
        """Serialize this state record for Home Assistant storage."""
        return {
            "fan_percentage": self.fan_percentage,
            "light_is_on": self.light_is_on,
            "brightness": self.brightness,
            "updated_at": self.updated_at.isoformat(),
        }


class OptimisticStateStore:
    """Manage durable inferred controller state for all AMC DC419 controllers."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the store without performing disk I/O."""
        self._store: Store[dict[str, object]] = Store(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY,
            private=True,
        )
        self._states: dict[str, StoredOptimisticState] = {}
        self._loaded = False
        self._lock = asyncio.Lock()

    async def async_load(self) -> None:
        """Load persisted controller state once for this Home Assistant instance."""
        async with self._lock:
            if self._loaded:
                return

            stored_data = await self._store.async_load()
            self._states = self._deserialize(stored_data)
            self._loaded = True

    async def async_store_state(
        self, controller_id: str, state: StoredOptimisticState
    ) -> None:
        """Persist inferred state after a complete RF command batch succeeds."""
        await self.async_load()
        async with self._lock:
            self._states[controller_id] = state
            await self._store.async_save(self._serialize())

    async def async_get_state(self, controller_id: str) -> StoredOptimisticState | None:
        """Return the inferred state for a controller, if one was stored."""
        await self.async_load()
        return self._states.get(controller_id)

    async def async_remove_state(self, controller_id: str) -> None:
        """Remove persisted inferred state for a controller."""
        await self.async_load()
        async with self._lock:
            if self._states.pop(controller_id, None) is not None:
                await self._store.async_save(self._serialize())

    @staticmethod
    def _deserialize(
        stored_data: Mapping[str, object] | None,
    ) -> dict[str, StoredOptimisticState]:
        """Deserialize valid controller records and discard malformed ones."""
        if stored_data is None:
            return {}

        stored_controllers = stored_data.get("controllers")
        if not isinstance(stored_controllers, Mapping):
            return {}

        return {
            controller_id: state
            for controller_id, stored_state in stored_controllers.items()
            if isinstance(controller_id, str)
            and (state := StoredOptimisticState.from_storage_data(stored_state))
            is not None
        }

    def _serialize(self) -> dict[str, object]:
        """Serialize optimistic state into the versioned storage schema."""
        return {
            "controllers": {
                controller_id: state.as_storage_data()
                for controller_id, state in self._states.items()
            }
        }


def get_optimistic_state_store(hass: HomeAssistant) -> OptimisticStateStore:
    """Return the singleton inferred-state store for this Home Assistant instance."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if not isinstance(domain_data, dict):
        raise RuntimeError("AMC DC419 domain data has an invalid runtime type")

    state_store = domain_data.get(DATA_OPTIMISTIC_STATE_STORE)
    if state_store is None:
        state_store = OptimisticStateStore(hass)
        domain_data[DATA_OPTIMISTIC_STATE_STORE] = state_store

    if not isinstance(state_store, OptimisticStateStore):
        raise RuntimeError("AMC DC419 state store has an invalid runtime type")

    return state_store
