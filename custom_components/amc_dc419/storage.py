"""Persistent command bindings for AMC DC419 controllers."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DATA_COMMAND_STORE, DOMAIN, LearnCommand

STORAGE_KEY: Final = f"{DOMAIN}.commands"
STORAGE_VERSION: Final = 1


@dataclass(frozen=True, slots=True)
class LearnedCommand:
    """A durable binding to an RF command stored by a Broadlink remote."""

    remote_entity_id: str
    remote_device: str
    learned_at: str

    def as_storage_data(self) -> dict[str, str]:
        """Return a JSON-serializable representation of the command binding."""
        return {
            "remote_entity_id": self.remote_entity_id,
            "remote_device": self.remote_device,
            "learned_at": self.learned_at,
        }

    @classmethod
    def from_storage_data(cls, data: object) -> LearnedCommand | None:
        """Create a command binding from validated persisted data."""
        if not isinstance(data, Mapping):
            return None

        remote_entity_id = data.get("remote_entity_id")
        remote_device = data.get("remote_device")
        learned_at = data.get("learned_at")
        if not all(isinstance(value, str) for value in (remote_entity_id, remote_device, learned_at)):
            return None

        return cls(
            remote_entity_id=remote_entity_id,
            remote_device=remote_device,
            learned_at=learned_at,
        )


class CommandStore:
    """Manage versioned command-binding storage for all AMC DC419 controllers."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the store without performing disk I/O."""
        self._store: Store[dict[str, object]] = Store(
            hass,
            STORAGE_VERSION,
            STORAGE_KEY,
            private=True,
        )
        self._commands: dict[str, dict[LearnCommand, LearnedCommand]] = {}
        self._loaded = False
        self._lock = asyncio.Lock()

    async def async_load(self) -> None:
        """Load persisted command bindings once for this Home Assistant instance."""
        async with self._lock:
            if self._loaded:
                return

            stored_data = await self._store.async_load()
            self._commands = self._deserialize(stored_data)
            self._loaded = True

    async def async_store_command(
        self,
        controller_id: str,
        command: LearnCommand,
        remote_entity_id: str,
        remote_device: str,
    ) -> LearnedCommand:
        """Persist the binding for a command learned by a Broadlink remote."""
        await self.async_load()
        learned_command = LearnedCommand(
            remote_entity_id=remote_entity_id,
            remote_device=remote_device,
            learned_at=dt_util.utcnow().isoformat(),
        )

        async with self._lock:
            self._commands.setdefault(controller_id, {})[command] = learned_command
            await self._store.async_save(self._serialize())

        return learned_command

    async def async_get_command(
        self, controller_id: str, command: LearnCommand
    ) -> LearnedCommand | None:
        """Return one learned command binding, if it exists."""
        await self.async_load()
        return self._commands.get(controller_id, {}).get(command)

    async def async_get_commands(
        self, controller_id: str
    ) -> dict[LearnCommand, LearnedCommand]:
        """Return a copy of all learned command bindings for a controller."""
        await self.async_load()
        return self._commands.get(controller_id, {}).copy()

    async def async_remove_controller(self, controller_id: str) -> None:
        """Remove every command binding associated with a controller."""
        await self.async_load()
        async with self._lock:
            if self._commands.pop(controller_id, None) is not None:
                await self._store.async_save(self._serialize())

    @staticmethod
    def _deserialize(
        stored_data: Mapping[str, object] | None,
    ) -> dict[str, dict[LearnCommand, LearnedCommand]]:
        """Deserialize valid persisted bindings and discard malformed records."""
        if stored_data is None:
            return {}

        stored_controllers = stored_data.get("controllers")
        if not isinstance(stored_controllers, Mapping):
            return {}

        controllers: dict[str, dict[LearnCommand, LearnedCommand]] = {}
        for controller_id, stored_commands in stored_controllers.items():
            if not isinstance(controller_id, str) or not isinstance(stored_commands, Mapping):
                continue

            commands: dict[LearnCommand, LearnedCommand] = {}
            for command_value, stored_command in stored_commands.items():
                if not isinstance(command_value, str):
                    continue
                try:
                    command = LearnCommand(command_value)
                except ValueError:
                    continue

                learned_command = LearnedCommand.from_storage_data(stored_command)
                if learned_command is not None:
                    commands[command] = learned_command

            if commands:
                controllers[controller_id] = commands

        return controllers

    def _serialize(self) -> dict[str, object]:
        """Serialize command bindings into the versioned storage schema."""
        return {
            "controllers": {
                controller_id: {
                    command.value: learned_command.as_storage_data()
                    for command, learned_command in commands.items()
                }
                for controller_id, commands in self._commands.items()
            }
        }


def get_command_store(hass: HomeAssistant) -> CommandStore:
    """Return the singleton command store for the Home Assistant instance."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if not isinstance(domain_data, dict):
        raise RuntimeError("AMC DC419 domain data has an invalid runtime type")

    command_store = domain_data.get(DATA_COMMAND_STORE)
    if command_store is None:
        command_store = CommandStore(hass)
        domain_data[DATA_COMMAND_STORE] = command_store

    if not isinstance(command_store, CommandStore):
        raise RuntimeError("AMC DC419 command store has an invalid runtime type")

    return command_store