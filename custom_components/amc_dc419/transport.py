"""Transport-neutral RF command contracts and factory."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import CONF_TRANSPORT, CONF_TRANSPORT_TYPE, LearnCommand, TransportType

type PayloadValue = (
    str | int | float | bool | list[PayloadValue] | dict[str, PayloadValue] | None
)


class TransportConfigurationError(ValueError):
    """Raised when persisted transport configuration is invalid."""


class TransportError(HomeAssistantError):
    """Raised when an RF transport cannot perform an operation."""


class TransportUnavailableError(TransportError):
    """Raised when an RF transport is not currently available."""


@dataclass(frozen=True, slots=True)
class TransportConfiguration:
    """A transport type and its serializable, transport-owned settings."""

    transport_type: TransportType
    settings: Mapping[str, str]

    def __post_init__(self) -> None:
        """Validate settings and prevent accidental mutation of entry data."""
        if not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in self.settings.items()
        ):
            raise TransportConfigurationError("Transport settings must be strings")

        object.__setattr__(self, "settings", MappingProxyType(dict(self.settings)))

    @classmethod
    def from_entry_data(
        cls, entry_data: Mapping[str, object]
    ) -> TransportConfiguration:
        """Create a transport configuration from config-entry data."""
        raw_transport_type = entry_data.get(CONF_TRANSPORT_TYPE)
        raw_settings = entry_data.get(CONF_TRANSPORT)
        if not isinstance(raw_transport_type, str) or not isinstance(
            raw_settings, Mapping
        ):
            raise TransportConfigurationError("Transport configuration is missing")

        try:
            transport_type = TransportType(raw_transport_type)
        except ValueError as err:
            raise TransportConfigurationError("Unsupported transport type") from err

        if not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in raw_settings.items()
        ):
            raise TransportConfigurationError("Transport settings must be strings")

        return cls(transport_type=transport_type, settings=dict(raw_settings))

    def as_entry_data(self) -> dict[str, object]:
        """Return the JSON-serializable config-entry representation."""
        return {
            CONF_TRANSPORT_TYPE: self.transport_type.value,
            CONF_TRANSPORT: dict(self.settings),
        }


@dataclass(frozen=True, slots=True)
class LearnedCommand:
    """A learned RF command with transport-owned serialized payload data."""

    command: LearnCommand
    transport_type: TransportType
    payload: Mapping[str, PayloadValue]
    learned_at: str

    def __post_init__(self) -> None:
        """Validate and protect the serialized payload."""
        if not all(
            isinstance(key, str) and _is_payload_value(value)
            for key, value in self.payload.items()
        ):
            raise TransportConfigurationError(
                "Command payload is not JSON serializable"
            )

        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))

    def as_storage_data(self) -> dict[str, object]:
        """Return a JSON-serializable representation of this command."""
        return {
            "transport_type": self.transport_type.value,
            "payload": dict(self.payload),
            "learned_at": self.learned_at,
        }

    @classmethod
    def from_storage_data(
        cls, command: LearnCommand, data: object
    ) -> LearnedCommand | None:
        """Create a command from validated persisted storage data."""
        if not isinstance(data, Mapping):
            return None

        raw_transport_type = data.get("transport_type")
        raw_payload = data.get("payload")
        learned_at = data.get("learned_at")
        if (
            not isinstance(raw_transport_type, str)
            or not isinstance(raw_payload, Mapping)
            or not isinstance(learned_at, str)
            or not learned_at
            or not all(
                isinstance(key, str) and _is_payload_value(value)
                for key, value in raw_payload.items()
            )
        ):
            return None

        try:
            transport_type = TransportType(raw_transport_type)
        except ValueError:
            return None

        payload = {key: cast(PayloadValue, value) for key, value in raw_payload.items()}
        return cls(
            command=command,
            transport_type=transport_type,
            payload=payload,
            learned_at=learned_at,
        )


class RFTransport(ABC):
    """Define the transport operations needed by an AMC DC419 controller."""

    @property
    @abstractmethod
    def transport_type(self) -> TransportType:
        """Return the persistent type identifier for this transport."""

    @property
    def availability_entity_ids(self) -> tuple[str, ...]:
        """Return Home Assistant entities that determine transport availability."""
        return ()

    @abstractmethod
    async def async_validate(self) -> None:
        """Raise an error when the transport is not ready for use."""

    @abstractmethod
    async def async_learn(self, command: LearnCommand) -> LearnedCommand:
        """Learn one command and return its durable transport payload."""

    @abstractmethod
    async def async_send(self, command: LearnedCommand) -> None:
        """Send one learned command through this transport."""


class RFTransportProvider(ABC):
    """Create and configure one concrete RF transport implementation."""

    @property
    @abstractmethod
    def transport_type(self) -> TransportType:
        """Return the persistent identifier for this transport."""

    @abstractmethod
    def config_flow_schema(self) -> Mapping[object, object]:
        """Return the configuration fields needed by this transport."""

    @abstractmethod
    async def async_create_configuration(
        self,
        hass: HomeAssistant,
        controller_id: str,
        user_input: Mapping[str, object],
    ) -> TransportConfiguration:
        """Validate setup input and return durable transport settings."""

    @abstractmethod
    def create_transport(
        self, hass: HomeAssistant, configuration: TransportConfiguration
    ) -> RFTransport:
        """Create a runtime transport from durable settings."""


def create_transport(
    hass: HomeAssistant, configuration: TransportConfiguration
) -> RFTransport:
    """Create the RF transport declared by a controller configuration."""
    return get_transport_provider(configuration.transport_type).create_transport(
        hass, configuration
    )


def get_transport_provider(transport_type: TransportType) -> RFTransportProvider:
    """Return the provider that owns a supported transport type."""
    if transport_type is TransportType.BROADLINK:
        from .broadlink import BROADLINK_TRANSPORT_PROVIDER

        return BROADLINK_TRANSPORT_PROVIDER

    raise TransportConfigurationError("Unsupported transport type")


def _is_payload_value(value: object) -> bool:
    """Return whether a value is recursively JSON-serializable."""
    if value is None or isinstance(value, str | int | float | bool):
        return True
    if isinstance(value, list):
        return all(_is_payload_value(item) for item in value)
    if isinstance(value, Mapping):
        return all(
            isinstance(key, str) and _is_payload_value(item)
            for key, item in value.items()
        )
    return False
