"""Constants for the AMC DC419 integration."""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "amc_dc419"
NAME: Final = "AMC DC419"
PLATFORMS: Final = (Platform.FAN, Platform.LIGHT)

CONF_AREA_ID: Final = "area_id"
CONF_CONTROLLER_ID: Final = "controller_id"
CONF_FRIENDLY_NAME: Final = "friendly_name"
CONF_REMOTE_DEVICE: Final = "remote_device"
CONF_REMOTE_ENTITY_ID: Final = "remote_entity_id"
CONF_TRANSPORT: Final = "transport"
CONF_TRANSPORT_TYPE: Final = "transport_type"
CONF_REPEAT_DELAY: Final = "repeat_delay"
CONF_BRIGHTNESS_STEP_COUNT: Final = "brightness_step_count"
CONF_COLOUR_STEP_COUNT: Final = "colour_step_count"
CONF_RETRY_COUNT: Final = "retry_count"
CONF_OPTIMISTIC_TIMEOUT: Final = "optimistic_timeout"

DATA_COMMAND_STORE: Final = "command_store"

REMOTE_DOMAIN: Final = "remote"
REMOTE_SERVICE_LEARN_COMMAND: Final = "learn_command"
REMOTE_SERVICE_SEND_COMMAND: Final = "send_command"
ATTR_COMMAND_TYPE: Final = "command_type"
ATTR_REMOTE_COMMAND: Final = "command"
ATTR_REMOTE_DEVICE: Final = "device"
ATTR_TIMEOUT: Final = "timeout"

DEFAULT_LEARN_TIMEOUT: Final = 30
DEFAULT_REPEAT_DELAY: Final = 0.25
DEFAULT_BRIGHTNESS_STEP_COUNT: Final = 20
DEFAULT_COLOUR_STEP_COUNT: Final = 250
DEFAULT_RETRY_COUNT: Final = 1
DEFAULT_OPTIMISTIC_TIMEOUT: Final = 30

DEFAULT_BRIGHTNESS: Final = 255
MIN_COLOR_TEMP_KELVIN: Final = 2_000
MAX_COLOR_TEMP_KELVIN: Final = 6_500
DEFAULT_COLOR_TEMP_KELVIN: Final = 4_000


class TransportType(StrEnum):
    """Supported RF transport implementations."""

    BROADLINK = "broadlink"


class LearnCommand(StrEnum):
    """RF commands that must be learned for each AMC DC419 controller."""

    LIGHT_TOGGLE = "light_toggle"
    BRIGHTNESS_UP = "brightness_up"
    BRIGHTNESS_DOWN = "brightness_down"
    COLOUR_CYCLE = "colour_cycle"
    FAN_OFF = "fan_off"
    FAN_SPEED_1 = "fan_speed_1"
    FAN_SPEED_2 = "fan_speed_2"
    FAN_SPEED_3 = "fan_speed_3"
    FAN_SPEED_4 = "fan_speed_4"
    FAN_SPEED_5 = "fan_speed_5"
    FAN_SPEED_6 = "fan_speed_6"
    DIRECTION_TOGGLE = "direction_toggle"


LEARN_COMMANDS: Final[tuple[LearnCommand, ...]] = tuple(LearnCommand)

LEARN_COMMAND_LABELS: Final[dict[LearnCommand, str]] = {
    LearnCommand.LIGHT_TOGGLE: "Light Toggle",
    LearnCommand.BRIGHTNESS_UP: "Brightness Up",
    LearnCommand.BRIGHTNESS_DOWN: "Brightness Down",
    LearnCommand.COLOUR_CYCLE: "Colour Cycle",
    LearnCommand.FAN_OFF: "Fan Off",
    LearnCommand.FAN_SPEED_1: "Speed 1",
    LearnCommand.FAN_SPEED_2: "Speed 2",
    LearnCommand.FAN_SPEED_3: "Speed 3",
    LearnCommand.FAN_SPEED_4: "Speed 4",
    LearnCommand.FAN_SPEED_5: "Speed 5",
    LearnCommand.FAN_SPEED_6: "Speed 6",
    LearnCommand.DIRECTION_TOGGLE: "Direction Toggle",
}
