"""Optimistic state coordination for AMC DC419 controllers."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, LearnCommand
from .storage import CommandStore
from .transport import RFTransport, TransportError, TransportUnavailableError

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OptimisticControllerState:
    """The last controller state requested by Home Assistant.

    Every state value is optional because AMC DC419 RF remotes are one-way and
    cannot report their physical state after Home Assistant restarts.
    """

    fan_percentage: int | None = None
    fan_direction: str | None = None
    light_is_on: bool | None = None
    brightness: int | None = None
    colour_temperature: int | None = None
    transport_available: bool = False

    def as_diagnostics_data(self) -> dict[str, int | str | bool | None]:
        """Return state values suitable for diagnostics output."""
        return {
            "fan_percentage": self.fan_percentage,
            "fan_direction": self.fan_direction,
            "light_is_on": self.light_is_on,
            "brightness": self.brightness,
            "colour_temperature": self.colour_temperature,
            "transport_available": self.transport_available,
        }


type StateUpdater = Callable[[OptimisticControllerState], OptimisticControllerState]


class AMCDC419Coordinator(DataUpdateCoordinator[OptimisticControllerState]):
    """Coordinate optimistic state, RF sends, and transport availability."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        controller_id: str,
        command_store: CommandStore,
        transport: RFTransport,
    ) -> None:
        """Initialize shared runtime state without network or storage I/O."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            always_update=False,
        )
        self._command_store = command_store
        self._controller_id = controller_id
        self._send_lock = asyncio.Lock()
        self._transport = transport
        self._remove_transport_listener: CALLBACK_TYPE | None = None
        self.async_set_updated_data(OptimisticControllerState())

    @property
    def transport(self) -> RFTransport:
        """Return the transport used by this controller."""
        return self._transport

    @property
    def transport_available(self) -> bool:
        """Return whether the transport is currently usable."""
        return self.data.transport_available

    async def async_initialize(self) -> None:
        """Validate the transport and begin tracking its availability."""
        try:
            await self._transport.async_validate()
        except TransportError:
            self._async_set_transport_available(False)
            raise

        self._async_set_transport_available(True)
        entity_ids = self._transport.availability_entity_ids
        if entity_ids:
            self._remove_transport_listener = async_track_state_change_event(
                self.hass,
                entity_ids,
                self._async_handle_transport_state_change,
            )

    async def async_shutdown(self) -> None:
        """Stop tracking transport availability during config-entry unload."""
        if self._remove_transport_listener is not None:
            self._remove_transport_listener()
            self._remove_transport_listener = None

    async def async_send_commands(
        self,
        commands: Sequence[LearnCommand],
        state_updater: StateUpdater | None = None,
    ) -> None:
        """Send commands in order and publish state after every send succeeds."""
        if not commands:
            raise ValueError("At least one RF command is required")

        async with self._send_lock:
            learned_commands = []
            for command in commands:
                learned_command = await self._command_store.async_get_command(
                    self._controller_id, command
                )
                if learned_command is None:
                    raise TransportError(f"Required RF command is missing: {command}")
                learned_commands.append(learned_command)

            try:
                for learned_command in learned_commands:
                    await self._transport.async_send(learned_command)
            except TransportUnavailableError:
                self._async_set_transport_available(False)
                raise

            self._async_set_transport_available(True)
            if state_updater is not None:
                self.async_set_updated_data(state_updater(self.data))

    async def async_reset_optimistic_state(self) -> None:
        """Clear state inferred from previous one-way RF transmissions."""
        async with self._send_lock:
            self.async_set_updated_data(
                OptimisticControllerState(
                    transport_available=self.data.transport_available,
                )
            )

    @callback
    def _async_handle_transport_state_change(
        self, _event: Event[dict[str, Any]]
    ) -> None:
        """Schedule an availability refresh after a transport state change."""
        self.hass.async_create_task(
            self._async_refresh_transport_availability(),
            f"{DOMAIN}_refresh_transport_availability",
        )

    async def _async_refresh_transport_availability(self) -> None:
        """Refresh availability without logging expected offline transitions."""
        try:
            await self._transport.async_validate()
        except TransportError:
            self._async_set_transport_available(False)
        else:
            self._async_set_transport_available(True)

    @callback
    def _async_set_transport_available(self, available: bool) -> None:
        """Publish a transport availability change when it differs."""
        if self.data.transport_available != available:
            self.async_set_updated_data(
                replace(self.data, transport_available=available)
            )
