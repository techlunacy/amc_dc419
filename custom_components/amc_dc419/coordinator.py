"""Optimistic state coordination for AMC DC419 controllers."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from functools import partial
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BRIGHTNESS_STEP_COUNT,
    CONF_OPTIMISTIC_TIMEOUT,
    CONF_REPEAT_DELAY,
    CONF_RETRY_COUNT,
    DEFAULT_BRIGHTNESS_STEP_COUNT,
    DEFAULT_OPTIMISTIC_TIMEOUT,
    DEFAULT_REPEAT_DELAY,
    DEFAULT_RETRY_COUNT,
    DOMAIN,
    LearnCommand,
)
from .state_store import (
    OptimisticStateStore,
    StoredOptimisticState,
    get_optimistic_state_store,
)
from .storage import CommandStore
from .transport import (
    LearnedCommand,
    RFTransport,
    TransportError,
    TransportUnavailableError,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OptimisticControllerState:
    """The last controller state requested by Home Assistant.

    Every state value is optional because AMC DC419 RF remotes are one-way and
    cannot report their physical state after Home Assistant restarts.
    """

    fan_percentage: int | None = None
    light_is_on: bool | None = None
    brightness: int | None = None
    transport_available: bool = False

    def as_diagnostics_data(self) -> dict[str, int | bool | None]:
        """Return state values suitable for diagnostics output."""
        return {
            "fan_percentage": self.fan_percentage,
            "light_is_on": self.light_is_on,
            "brightness": self.brightness,
            "transport_available": self.transport_available,
        }


type StateUpdater = Callable[[OptimisticControllerState], OptimisticControllerState]


@dataclass(frozen=True, slots=True)
class ControllerOptions:
    """Validated runtime options that control one-way RF interactions."""

    repeat_delay: float = DEFAULT_REPEAT_DELAY
    brightness_step_count: int = DEFAULT_BRIGHTNESS_STEP_COUNT
    retry_count: int = DEFAULT_RETRY_COUNT
    optimistic_timeout: int = DEFAULT_OPTIMISTIC_TIMEOUT

    @classmethod
    def from_entry(cls, entry: ConfigEntry) -> ControllerOptions:
        """Return validated runtime options from a configuration entry."""
        options = entry.options
        return cls(
            repeat_delay=_get_float_option(
                options.get(CONF_REPEAT_DELAY), DEFAULT_REPEAT_DELAY, minimum=0
            ),
            brightness_step_count=_get_int_option(
                options.get(CONF_BRIGHTNESS_STEP_COUNT),
                DEFAULT_BRIGHTNESS_STEP_COUNT,
                minimum=1,
            ),
            retry_count=_get_int_option(
                options.get(CONF_RETRY_COUNT), DEFAULT_RETRY_COUNT, minimum=0
            ),
            optimistic_timeout=_get_int_option(
                options.get(CONF_OPTIMISTIC_TIMEOUT),
                DEFAULT_OPTIMISTIC_TIMEOUT,
                minimum=0,
            ),
        )


class AMCDC419Coordinator(DataUpdateCoordinator[OptimisticControllerState]):
    """Coordinate optimistic state, RF sends, and transport availability."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        controller_id: str,
        command_store: CommandStore,
        transport: RFTransport,
        options: ControllerOptions | None = None,
        state_store: OptimisticStateStore | None = None,
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
        self._options = options or ControllerOptions()
        self._remove_transport_listener: CALLBACK_TYPE | None = None
        self._remove_optimistic_timeout: CALLBACK_TYPE | None = None
        self._optimistic_state_expiry_generation = 0
        self._state_store = state_store or get_optimistic_state_store(hass)
        self.async_set_updated_data(OptimisticControllerState())

    @property
    def transport(self) -> RFTransport:
        """Return the transport used by this controller."""
        return self._transport

    @property
    def options(self) -> ControllerOptions:
        """Return the validated options for this controller."""
        return self._options

    @property
    def transport_available(self) -> bool:
        """Return whether the transport is currently usable."""
        return self.data.transport_available

    async def async_initialize(self) -> None:
        """Validate the transport and begin tracking its availability."""
        await self._state_store.async_load()
        try:
            await self._transport.async_validate()
        except TransportError:
            self._async_set_transport_available(False)
            raise

        self._async_set_transport_available(True)
        await self._async_restore_optimistic_state()
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
        self._async_cancel_optimistic_timeout()

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
                for index, learned_command in enumerate(learned_commands):
                    await self._async_send_with_retry(learned_command)
                    if index < len(learned_commands) - 1:
                        await asyncio.sleep(self._options.repeat_delay)
            except TransportUnavailableError:
                self._async_set_transport_available(False)
                raise

            self._async_set_transport_available(True)
            if state_updater is not None:
                await self._async_publish_optimistic_state(state_updater(self.data))

    async def async_reset_optimistic_state(self) -> None:
        """Clear state inferred from previous one-way RF transmissions."""
        async with self._send_lock:
            self._async_cancel_optimistic_timeout()
            await self._state_store.async_remove_state(self._controller_id)
            self.async_set_updated_data(
                OptimisticControllerState(
                    transport_available=self.data.transport_available,
                )
            )

    async def _async_send_with_retry(self, learned_command: LearnedCommand) -> None:
        """Send one command, retrying transient transport failures as configured."""
        for attempt in range(self._options.retry_count + 1):
            try:
                await self._transport.async_send(learned_command)
                return
            except TransportUnavailableError:
                raise
            except TransportError:
                if attempt == self._options.retry_count:
                    raise
                await asyncio.sleep(self._options.repeat_delay)

    @callback
    def _async_schedule_optimistic_timeout(self, updated_at: datetime) -> None:
        """Clear inferred state after the configured one-way RF timeout."""
        self._async_cancel_optimistic_timeout()
        if self._options.optimistic_timeout <= 0:
            return

        expires_at = updated_at + timedelta(seconds=self._options.optimistic_timeout)
        delay = max(expires_at - dt_util.utcnow(), timedelta())
        generation = self._optimistic_state_expiry_generation
        self._remove_optimistic_timeout = async_call_later(
            self.hass,
            delay,
            partial(self._async_expire_optimistic_state, generation),
        )

    @callback
    def _async_cancel_optimistic_timeout(self) -> None:
        """Cancel a pending optimistic-state expiry callback."""
        if self._remove_optimistic_timeout is not None:
            self._remove_optimistic_timeout()
            self._remove_optimistic_timeout = None
        self._optimistic_state_expiry_generation += 1

    @callback
    def _async_expire_optimistic_state(self, generation: int, _now: datetime) -> None:
        """Schedule removal of an expired optimistic state record."""
        self._remove_optimistic_timeout = None
        self.hass.async_create_task(
            self._async_clear_expired_optimistic_state(generation),
            f"{DOMAIN}_expire_optimistic_state",
        )

    async def _async_publish_optimistic_state(
        self, state: OptimisticControllerState
    ) -> None:
        """Persist and publish state requested by a completed RF command batch."""
        updated_at = dt_util.utcnow()
        await self._state_store.async_store_state(
            self._controller_id,
            StoredOptimisticState(
                fan_percentage=state.fan_percentage,
                light_is_on=state.light_is_on,
                brightness=state.brightness,
                updated_at=updated_at,
            ),
        )
        self.async_set_updated_data(state)
        self._async_schedule_optimistic_timeout(updated_at)

    async def _async_restore_optimistic_state(self) -> None:
        """Restore persisted inferred state only while its timeout remains active."""
        stored_state = await self._state_store.async_get_state(self._controller_id)
        if stored_state is None:
            return

        if self._options.optimistic_timeout > 0 and (
            stored_state.updated_at
            + timedelta(seconds=self._options.optimistic_timeout)
            <= dt_util.utcnow()
        ):
            await self._state_store.async_remove_state(self._controller_id)
            return

        self.async_set_updated_data(
            OptimisticControllerState(
                fan_percentage=stored_state.fan_percentage,
                light_is_on=stored_state.light_is_on,
                brightness=stored_state.brightness,
                transport_available=self.data.transport_available,
            )
        )
        self._async_schedule_optimistic_timeout(stored_state.updated_at)

    async def _async_clear_expired_optimistic_state(self, generation: int) -> None:
        """Clear the matching expired state without racing a new command batch."""
        async with self._send_lock:
            if generation != self._optimistic_state_expiry_generation:
                return

            await self._state_store.async_remove_state(self._controller_id)
            self._optimistic_state_expiry_generation += 1
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


def _get_float_option(value: object, default: float, minimum: float) -> float:
    """Return a finite option value or its default when invalid."""
    if isinstance(value, int | float) and value >= minimum:
        return float(value)
    return default


def _get_int_option(value: object, default: int, minimum: int) -> int:
    """Return an integer option value or its default when invalid."""
    if isinstance(value, int) and value >= minimum:
        return value
    return default
