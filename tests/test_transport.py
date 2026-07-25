"""Tests for transport-neutral RF command models."""

from __future__ import annotations

import pytest

from custom_components.amc_dc419.const import (
    CONF_REMOTE_ENTITY_ID,
    LearnCommand,
    TransportType,
)
from custom_components.amc_dc419.transport import (
    LearnedCommand,
    TransportConfiguration,
    TransportConfigurationError,
)

from .conftest import make_learned_command


def test_transport_configuration_round_trip() -> None:
    """Transport configuration keeps settings immutable across entry conversion."""
    configuration = TransportConfiguration(
        transport_type=TransportType.BROADLINK,
        settings={CONF_REMOTE_ENTITY_ID: "remote.office"},
    )

    restored = TransportConfiguration.from_entry_data(configuration.as_entry_data())

    assert restored == configuration
    with pytest.raises(TypeError):
        restored.settings[CONF_REMOTE_ENTITY_ID] = "remote.other"


def test_learned_command_round_trip_preserves_nested_payload() -> None:
    """Learned command serialization preserves JSON-compatible payload values."""
    command = LearnedCommand(
        command=LearnCommand.LIGHT_TOGGLE,
        transport_type=TransportType.BROADLINK,
        payload={"nested": {"retries": [1, 2, 3]}},
        learned_at="2026-07-25T00:00:00+00:00",
    )

    restored = LearnedCommand.from_storage_data(
        LearnCommand.LIGHT_TOGGLE, command.as_storage_data()
    )

    assert restored == command


def test_learned_command_rejects_non_serializable_payload() -> None:
    """Transport payloads reject objects that cannot be persisted as JSON."""
    with pytest.raises(TransportConfigurationError):
        LearnedCommand(
            command=LearnCommand.LIGHT_TOGGLE,
            transport_type=TransportType.BROADLINK,
            payload={"invalid": object()},
            learned_at="2026-07-25T00:00:00+00:00",
        )


def test_learned_command_rejects_unknown_transport_type() -> None:
    """Unknown persisted transports are ignored instead of raising during startup."""
    stored_data = make_learned_command(LearnCommand.LIGHT_TOGGLE).as_storage_data()
    stored_data["transport_type"] = "unknown"

    assert (
        LearnedCommand.from_storage_data(LearnCommand.LIGHT_TOGGLE, stored_data) is None
    )
