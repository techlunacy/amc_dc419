"""Tests for AMC DC419 diagnostics redaction."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.amc_dc419 import AMCDC419RuntimeData
from custom_components.amc_dc419.const import (
    CONF_CONTROLLER_ID,
    CONF_TRANSPORT,
    CONF_TRANSPORT_TYPE,
    DOMAIN,
    LearnCommand,
    TransportType,
)
from custom_components.amc_dc419.coordinator import AMCDC419Coordinator
from custom_components.amc_dc419.diagnostics import async_get_config_entry_diagnostics
from custom_components.amc_dc419.storage import CommandStore

from .conftest import FakeTransport, make_learned_command


async def test_diagnostics_redacts_transport_settings_and_command_payloads(
    hass: HomeAssistant,
) -> None:
    """Diagnostics retain useful metadata without exposing RF command payloads."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CONTROLLER_ID: "controller",
            CONF_TRANSPORT_TYPE: TransportType.BROADLINK.value,
            CONF_TRANSPORT: {"remote_entity_id": "remote.office"},
        },
    )
    entry.add_to_hass(hass)
    store = CommandStore(hass)
    await store.async_store_command(
        "controller", make_learned_command(LearnCommand.LIGHT_TOGGLE)
    )
    transport = FakeTransport()
    coordinator = AMCDC419Coordinator(hass, entry, "controller", store, transport)
    await coordinator.async_initialize()
    entry.runtime_data = AMCDC419RuntimeData(
        command_store=store,
        coordinator=coordinator,
        transport=transport,
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry_data"][CONF_TRANSPORT] == "**REDACTED**"
    assert diagnostics["commands"] == {
        LearnCommand.LIGHT_TOGGLE.value: {
            "transport_type": TransportType.BROADLINK.value,
            "learned_at": "2026-07-25T00:00:00+00:00",
        }
    }
    assert "payload" not in str(diagnostics)
