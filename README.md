# AMC DC419

Home Assistant custom integration for AMC DC419 ceiling fan and light
controllers that use one-way RF remotes.

The integration is designed around optimistic state: RF remotes do not report
the actual fan or light state back to Home Assistant, so state reflects the
last successful command sent by Home Assistant.

## Status

This repository is under active development and is **not ready for production
installation or HACS publication**. The command-learning, persistence,
transport, coordinator, diagnostics, and config-entry lifecycle foundations
are implemented and tested. Fan and Light entities, integration services,
an options flow, release documentation, and HACS release metadata are still
pending.

Do not rely on the current version to control a fan or light: configuration
can learn and store RF commands, but no entities are created yet.

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

## Current Prerequisites

- Home Assistant 2026.2.3. This is the version currently used for automated
  testing; the supported-version policy will be defined before release.
- A configured Broadlink remote exposed as a Home Assistant `remote` entity.
- The selected remote must provide the `remote.learn_command` and
  `remote.send_command` services and support RF learning.
- The original AMC DC419 handheld remote, available during configuration.

There is no YAML configuration.

## Configuration Flow

The current UI flow collects:

1. A friendly controller name.
2. The Home Assistant area for the controller.
3. A Broadlink remote entity.

It then requests each RF command in order:

| Group | Commands |
| --- | --- |
| Light | Light On, Light Off, Brightness Up, Brightness Down, Colour Up, Colour Down |
| Fan | Fan Off, Speed 1, Speed 2, Speed 3, Speed 4, Speed 5, Speed 6 |
| Direction | Direction Toggle |

The flow stores nothing until every command has been learned successfully. If
learning fails, correct the remote setup and retry the current step; an
incomplete controller command set is not persisted.

## Troubleshooting Learning

| Symptom | Check |
| --- | --- |
| The selected remote is rejected or unavailable | Verify the entity exists, is not `unknown` or `unavailable`, and is a usable Broadlink remote. |
| Setup reports it cannot connect | Confirm both `remote.learn_command` and `remote.send_command` are registered by the selected remote integration. |
| A command cannot be learned | Confirm the remote supports RF learning, keep the handset close to it, and use the exact requested handset button. |
| A learning flow is abandoned | Start a new flow. Partial command sets are intentionally not retained. |

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

The suite uses `pytest-homeassistant-custom-component` and currently covers
the Broadlink transport, configuration flow, command storage and legacy-data
migration, optimistic coordinator, diagnostics redaction, and config-entry
lifecycle.

## Release Checklist

Before publishing to HACS, the project needs:

- Fan and Light platforms with entity descriptions and optimistic behavior.
- `sync_state`, `learn_command`, and `send_raw` services.
- An options flow for repeat delay, brightness/colour step counts, retry
  count, and optimistic timeout.
- Reconfiguration support, translations, icons, end-user screenshots, and
  release documentation.
- HACS metadata, an Apache-2.0 license, CI for Ruff, pytest, and Hassfest,
  plus a documented supported Home Assistant version policy.

## Contributing

Keep changes transport-neutral where possible. New RF backends should add an
`RFTransportProvider` and an `RFTransport` implementation rather than adding
transport-specific fields to controller state or command storage. Add focused
pytest coverage for every behavioral change and run the development checks
above before opening a pull request.