# AMC DC419

Home Assistant custom integration for AMC DC419 ceiling fan and light
controllers that use one-way RF remotes.

[![Open the repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=techlunacy&repository=amc_dc419&category=integration)

The integration creates one Fan and one Light entity for each configured
controller. It uses a Broadlink RF remote to learn and replay the AMC DC419
handset commands.

## Requirements

- Home Assistant 2026.2.3 or later.
- A Broadlink remote exposed through Home Assistant as a `remote` entity.
- The remote must support RF learning and provide both
  `remote.learn_command` and `remote.send_command`.
- The original AMC DC419 handset, available during initial setup and whenever
  a command needs to be relearned.

There is no YAML configuration.

## Installation

1. In HACS, add `https://github.com/techlunacy/amc_dc419` as a custom
   **Integration** repository.
2. Download **AMC DC419**, then restart Home Assistant.
3. Go to **Settings** > **Devices & services** > **Add integration**, search
   for **AMC DC419**, and complete the learning wizard.

To install manually, copy `custom_components/amc_dc419` into your Home
Assistant configuration directory’s `custom_components` folder, then restart
Home Assistant.

## Design

The integration separates controller behavior from RF transport details:

- A controller config entry stores a transport type and transport-owned
  settings.
- Learned commands are stored in Home Assistant's private storage with
  transport-owned, JSON-safe payloads.
- `RFTransport` provides validation, learning, sending, and availability
  contracts.
- `BroadlinkTransport` is the first implementation. Additional transports
  can implement the provider contract without changing controller storage,
  command learning, or entity behavior.
- A no-poll `DataUpdateCoordinator` owns optimistic controller state,
  serializes RF command batches, and follows transport availability.

RF payloads are deliberately omitted from diagnostics.

## Configuration Flow

The current UI flow collects:

1. A friendly controller name.
2. The Home Assistant area for the controller.
3. A Broadlink remote entity.

It then requests each RF command in order:

| Group | Commands |
| --- | --- |
| Light | Light Toggle, Brightness Up, Brightness Down, Colour Cycle |
| Fan | Fan Off, Speed 1, Speed 2, Speed 3, Speed 4, Speed 5, Speed 6 |
| Direction | Direction Toggle |

The flow stores nothing until every command has been learned successfully. For
each RF command, follow the Broadlink notifications: press and hold the handset
button during the frequency sweep, then press it again when prompted to capture
the code. The integration sends one verification press after each successful
capture, so the controller may respond during setup. If learning fails, correct
the remote setup and retry the current step; an incomplete controller command
set is not persisted.

The integration can be reconfigured from the Devices & services page to
rename the controller, change its area, or select a replacement Broadlink
remote. Existing learned commands remain associated with the controller.

## Entities

Each configured controller exposes:

| Entity | Behavior |
| --- | --- |
| Fan | On/off and six discrete speed commands. A bare turn-on starts at 33% (speed 2); requested percentages are mapped to the nearest supported speed. |
| Light | On/off through one shared handset toggle and brightness. Use the `colour_cycle` raw command to advance the handset's relative colour mode by one step. |
| Button | Toggle fan direction with one relative handset command. |

The RF handset is one-way: it cannot report physical state. Entity values are
therefore optimistic and represent the last successful command sent through
Home Assistant. The inferred fan speed, light power, and brightness are restored
after a Home Assistant restart. The direction button sends a relative toggle;
the controller cannot report or retain its physical direction. State becomes
unknown when you run `amc_dc419.sync_state` or after a configured nonzero
optimistic-state timeout. Use Home Assistant to control the fan and light
consistently; commands sent from the physical handset cannot be observed by this
integration.

When light power is unknown, a brightness change sends only the relative
brightness command and does not send the shared light toggle. Use the light's
power control to explicitly change its on/off state.

## Options

Open **Configure** on the integration card to tune RF behavior per controller:

| Option | Default | Purpose |
| --- | ---: | --- |
| Delay between RF presses | 0.25 seconds | Paces command batches. |
| Brightness step size | 20 | Estimated brightness change per handset press. |
| RF send retries | 1 | Retries transient transport failures. |
| Optimistic state timeout | Disabled (0) | Retains inferred state until reset; choose a positive duration to clear it automatically. |

The physical handset’s brightness step size may differ. Adjust the brightness
step-size option until Home Assistant’s inferred state tracks the controller
acceptably.

## Actions

The integration registers three actions. Each requires the integration’s
`config_entry_id`, visible in the integration’s configuration URL or developer
tools.

| Action | Purpose |
| --- | --- |
| `amc_dc419.sync_state` | Clear inferred Fan and Light state without sending RF. |
| `amc_dc419.learn_command` | Learn and replace one named RF command. |
| `amc_dc419.send_raw` | Send a stored command, including `colour_cycle`, without changing optimistic state. |

Example script action:

```yaml
action: amc_dc419.send_raw
data:
  config_entry_id: YOUR_CONFIG_ENTRY_ID
  command: colour_cycle
```

## Troubleshooting Learning

| Symptom | Check |
| --- | --- |
| The selected remote is rejected or unavailable | Verify the entity exists, is not `unknown` or `unavailable`, and is a usable Broadlink remote. |
| Setup reports it cannot connect | Confirm both `remote.learn_command` and `remote.send_command` are registered by the selected remote integration. |
| A command cannot be learned | Confirm the remote supports RF learning, keep the handset close to it, and use the exact requested handset button. |
| `Command not found: 'light_toggle'` | The Broadlink remote did not save the RF capture. Use `amc_dc419.learn_command` for `light_toggle`, following the hold-then-press RF prompts, then retry. |
| A learning flow is abandoned | Start a new flow. Partial command sets are intentionally not retained. |
| Entities are unavailable | Confirm the selected Broadlink remote is available and both required `remote` services are registered. |
| Entity state does not match the controller | The remote is one-way. Reset the inferred state, then control the device through Home Assistant; tune the RF step sizes if levels drift. |

## Development

The project uses `uv` and Python 3.13. A local virtual environment is created
at `.venv`.

```console
uv sync --group dev
uv run --group dev pytest
uv run --group dev ruff format --check custom_components tests
uv run --group dev ruff check custom_components tests
```

To run the test suite with branch coverage:

```console
uv run --group dev pytest \
  --cov=custom_components.amc_dc419 \
  --cov-branch \
  --cov-report=term-missing
```

The suite uses `pytest-homeassistant-custom-component` and covers transport
learning and sending, configuration/options/reconfiguration flows, command
storage and migration, coordinator retries and expiry, entity behavior,
services, diagnostics redaction, and config-entry lifecycle.

## Contributing

Keep changes transport-neutral where possible. New RF backends should add an
`RFTransportProvider` and an `RFTransport` implementation rather than adding
transport-specific fields to controller state or command storage. Add focused
pytest coverage for every behavioral change and run the development checks
above before opening a pull request.