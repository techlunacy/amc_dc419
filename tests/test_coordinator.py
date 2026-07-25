"""Tests for optimistic controller state coordination."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from unittest.mock import AsyncMock, call, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.amc_dc419.const import (
    CONF_BRIGHTNESS_STEP_COUNT,
    CONF_OPTIMISTIC_TIMEOUT,
    CONF_REPEAT_DELAY,
    CONF_RETRY_COUNT,
    DOMAIN,
    LearnCommand,
)
from custom_components.amc_dc419.coordinator import (
    AMCDC419Coordinator,
    ControllerOptions,
)
from custom_components.amc_dc419.state_store import (
    OptimisticStateStore,
    StoredOptimisticState,
    get_optimistic_state_store,
)
from custom_components.amc_dc419.storage import CommandStore
from custom_components.amc_dc419.transport import (
    TransportError,
    TransportUnavailableError,
)

from .conftest import FakeTransport, make_learned_command


async def test_send_commands_preserves_order_and_updates_state(
    hass: HomeAssistant,
) -> None:
    """Command batches preserve RF order and update optimistic state on success."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    store = CommandStore(hass)
    transport = FakeTransport()
    coordinator = AMCDC419Coordinator(hass, entry, "controller", store, transport)
    commands = (LearnCommand.LIGHT_TOGGLE, LearnCommand.BRIGHTNESS_UP)
    for command in commands:
        await store.async_store_command("controller", make_learned_command(command))

    await coordinator.async_initialize()
    await coordinator.async_send_commands(
        commands,
        lambda state: replace(state, light_is_on=True, brightness=96),
    )

    assert [command.command for command in transport.sent] == list(commands)
    assert coordinator.data.light_is_on is True
    assert coordinator.data.brightness == 96
    assert coordinator.transport_available is True


async def test_initialize_restores_persisted_optimistic_state(
    hass: HomeAssistant,
) -> None:
    """A recreated coordinator restores all persistable inferred state."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    command_store = CommandStore(hass)
    state_store = OptimisticStateStore(hass)
    await command_store.async_store_command(
        "controller", make_learned_command(LearnCommand.FAN_SPEED_6)
    )
    coordinator = AMCDC419Coordinator(
        hass,
        entry,
        "controller",
        command_store,
        FakeTransport(),
        ControllerOptions(repeat_delay=0, optimistic_timeout=60),
        state_store,
    )
    await coordinator.async_initialize()
    await coordinator.async_send_commands(
        (LearnCommand.FAN_SPEED_6,),
        lambda state: replace(
            state,
            fan_percentage=100,
            light_is_on=True,
            brightness=160,
        ),
    )
    await coordinator.async_shutdown()

    restored_coordinator = AMCDC419Coordinator(
        hass,
        entry,
        "controller",
        command_store,
        FakeTransport(),
        ControllerOptions(repeat_delay=0, optimistic_timeout=60),
        OptimisticStateStore(hass),
    )
    await restored_coordinator.async_initialize()

    assert restored_coordinator.data.fan_percentage == 100
    assert restored_coordinator.data.light_is_on is True
    assert restored_coordinator.data.brightness == 160


async def test_initialize_discards_expired_persisted_optimistic_state(
    hass: HomeAssistant,
) -> None:
    """A restart cannot extend the lifetime of previously inferred state."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    state_store = OptimisticStateStore(hass)
    await state_store.async_store_state(
        "controller",
        StoredOptimisticState(
            fan_percentage=66,
            light_is_on=True,
            brightness=120,
            updated_at=dt_util.utcnow() - timedelta(seconds=11),
        ),
    )
    coordinator = AMCDC419Coordinator(
        hass,
        entry,
        "controller",
        CommandStore(hass),
        FakeTransport(),
        ControllerOptions(repeat_delay=0, optimistic_timeout=10),
        state_store,
    )

    await coordinator.async_initialize()

    assert coordinator.data.fan_percentage is None
    assert coordinator.data.light_is_on is None
    assert await state_store.async_get_state("controller") is None


def test_stored_optimistic_state_ignores_legacy_direction() -> None:
    """Existing state records remain valid after direction stops being modelled."""
    stored_state = StoredOptimisticState.from_storage_data(
        {
            "fan_percentage": 66,
            "fan_direction": "reverse",
            "light_is_on": True,
            "brightness": 120,
            "updated_at": "2026-07-25T00:00:00+00:00",
        }
    )

    assert stored_state is not None
    assert stored_state.fan_percentage == 66
    assert stored_state.light_is_on is True
    assert stored_state.brightness == 120


async def test_unavailable_send_marks_transport_unavailable(
    hass: HomeAssistant,
) -> None:
    """Unavailable sends surface an error and make entities unavailable."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    store = CommandStore(hass)
    transport = FakeTransport()
    coordinator = AMCDC419Coordinator(hass, entry, "controller", store, transport)
    await store.async_store_command(
        "controller", make_learned_command(LearnCommand.FAN_OFF)
    )
    await coordinator.async_initialize()
    transport.fail_send = True

    with pytest.raises(TransportUnavailableError):
        await coordinator.async_send_commands((LearnCommand.FAN_OFF,))

    assert coordinator.transport_available is False


async def test_reset_optimistic_state_preserves_availability(
    hass: HomeAssistant,
) -> None:
    """State reset clears optimistic values without hiding an available transport."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    coordinator = AMCDC419Coordinator(
        hass, entry, "controller", CommandStore(hass), FakeTransport()
    )
    await coordinator.async_initialize()
    coordinator.async_set_updated_data(
        replace(coordinator.data, fan_percentage=50, light_is_on=True)
    )

    await coordinator.async_reset_optimistic_state()

    assert coordinator.data.fan_percentage is None
    assert coordinator.data.light_is_on is None
    assert coordinator.transport_available is True


def test_controller_options_use_defaults_for_invalid_values() -> None:
    """Invalid persisted options cannot create unsafe runtime command behavior."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        options={
            CONF_REPEAT_DELAY: -1,
            CONF_BRIGHTNESS_STEP_COUNT: 0,
            CONF_RETRY_COUNT: -1,
            CONF_OPTIMISTIC_TIMEOUT: -1,
        },
    )

    assert ControllerOptions.from_entry(entry) == ControllerOptions()


async def test_send_retries_transient_errors_then_updates_state(
    hass: HomeAssistant,
) -> None:
    """A transient send failure retries once and only publishes after success."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    store = CommandStore(hass)
    transport = FakeTransport()
    transport.transient_send_failures = 1
    coordinator = AMCDC419Coordinator(
        hass,
        entry,
        "controller",
        store,
        transport,
        ControllerOptions(repeat_delay=0, retry_count=1, optimistic_timeout=0),
    )
    await store.async_store_command(
        "controller", make_learned_command(LearnCommand.FAN_SPEED_1)
    )
    await coordinator.async_initialize()

    await coordinator.async_send_commands(
        (LearnCommand.FAN_SPEED_1,),
        lambda state: replace(state, fan_percentage=16),
    )

    assert [command.command for command in transport.send_attempts] == [
        LearnCommand.FAN_SPEED_1,
        LearnCommand.FAN_SPEED_1,
    ]
    assert coordinator.data.fan_percentage == 16


async def test_send_propagates_after_retry_exhaustion(hass: HomeAssistant) -> None:
    """An exhausted transient error does not update the optimistic state."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    store = CommandStore(hass)
    transport = FakeTransport()
    transport.transient_send_failures = 2
    coordinator = AMCDC419Coordinator(
        hass,
        entry,
        "controller",
        store,
        transport,
        ControllerOptions(repeat_delay=0, retry_count=1, optimistic_timeout=0),
    )
    await store.async_store_command(
        "controller", make_learned_command(LearnCommand.FAN_SPEED_1)
    )
    await coordinator.async_initialize()

    with pytest.raises(TransportError):
        await coordinator.async_send_commands(
            (LearnCommand.FAN_SPEED_1,),
            lambda state: replace(state, fan_percentage=16),
        )

    assert coordinator.data.fan_percentage is None
    assert await get_optimistic_state_store(hass).async_get_state("controller") is None


async def test_send_waits_between_distinct_rf_commands(hass: HomeAssistant) -> None:
    """A configured repeat delay separates commands in a single RF batch."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    store = CommandStore(hass)
    commands = (LearnCommand.LIGHT_TOGGLE, LearnCommand.BRIGHTNESS_UP)
    for command in commands:
        await store.async_store_command("controller", make_learned_command(command))
    coordinator = AMCDC419Coordinator(
        hass,
        entry,
        "controller",
        store,
        FakeTransport(),
        ControllerOptions(repeat_delay=0.25, optimistic_timeout=0),
    )
    await coordinator.async_initialize()

    with patch(
        "custom_components.amc_dc419.coordinator.asyncio.sleep", new=AsyncMock()
    ) as sleep:
        await coordinator.async_send_commands(commands)

    assert sleep.await_args_list == [call(0.25)]


async def test_optimistic_state_expires_after_configured_timeout(
    hass: HomeAssistant,
) -> None:
    """One-way controller state is cleared once its configured expiry elapses."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    store = CommandStore(hass)
    await store.async_store_command(
        "controller", make_learned_command(LearnCommand.FAN_SPEED_1)
    )
    coordinator = AMCDC419Coordinator(
        hass,
        entry,
        "controller",
        store,
        FakeTransport(),
        ControllerOptions(repeat_delay=0, optimistic_timeout=10),
    )
    await coordinator.async_initialize()

    await coordinator.async_send_commands(
        (LearnCommand.FAN_SPEED_1,),
        lambda state: replace(state, fan_percentage=16),
    )
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=10))
    await hass.async_block_till_done()

    assert coordinator.data.fan_percentage is None
    assert coordinator.transport_available is True
    assert await get_optimistic_state_store(hass).async_get_state("controller") is None
