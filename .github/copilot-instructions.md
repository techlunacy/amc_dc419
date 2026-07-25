# AMC DC419 Project Instructions

## Scope

- This is a Home Assistant custom integration for one-way AMC DC419 RF fan and
  light controllers. Support Home Assistant 2026.2.3+ and Python 3.13.
- Use `uv` for development commands. Do not add another package manager or
  dependency definition.
- Keep changes scoped to the integration, its tests, and directly affected
  release artifacts.

## Architecture

- Preserve transport neutrality. `RFTransport` and `RFTransportProvider` own
  transport configuration, learning, sending, and opaque payloads. New RF
  backends must implement those contracts instead of adding Broadlink-specific
  fields or branches to controller, entity, coordinator, or storage code.
- The controller is one-way RF. Treat Fan and Light values as optimistic state:
  publish state only after a complete command batch succeeds, clear inferred
  state at the configured timeout, and never claim to observe handset changes.
- Send controller commands through `AMCDC419Coordinator`; keep batching,
  retries, RF pacing, availability, and state expiry centralized there.
- Learned command payloads are private, transport-owned JSON data. Never log
  them, expose them in diagnostics, or add real controller identifiers to tests
  or documentation.

## Home Assistant Conventions

- Use async Home Assistant APIs and do not perform blocking I/O in the event
  loop. Follow config-entry setup, unload, migration, options, and
  reconfiguration patterns already used in the integration.
- Preserve stable controller IDs, entity unique IDs, and learned commands when
  reconfiguring metadata or a transport.
- Add UI text to `translations/en.json`; update `services.yaml` for service
  changes, `manifest.json` for integration metadata changes, and `README.md`
  for user-visible behavior or requirements.
- Maintain diagnostics redaction for transport settings and learned payloads.

## Testing And Validation

- Add focused `pytest-homeassistant-custom-component` coverage for every
  behavior change, including success and failed RF-send paths where relevant.
- Before every commit, increment the `[project].version` in `pyproject.toml`
  with the appropriate semantic-version bump and include it in that commit.
- Run the full project checks before completing work:

  ```console
  uv run --group dev pytest
  uv run --group dev ruff format --check custom_components tests
  uv run --group dev ruff check custom_components tests
  .venv/bin/python -m compileall -q custom_components/amc_dc419 tests
  ```

- Keep GitHub Actions and Dependabot configuration valid when changing Python
  dependencies, `uv.lock`, or workflow actions.