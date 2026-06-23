# Trading 212 Home Assistant Integration

A Home Assistant custom integration for monitoring Trading 212 account and portfolio summary data.

## Status

Early development. Initial Home Assistant smoke test has passed with read-only API key and secret authentication.

Version `0.1.0` is intended to be strictly read-only.

## Safety boundary

This integration is designed to be read-only for the initial release.

It must not include:

- order placement
- order cancellation
- pie editing
- deposits or withdrawals
- write/mutation API calls
- Home Assistant services that alter a Trading 212 account
- Home Assistant buttons, selects, switches, or controls that change account state
- generic raw API endpoint helpers

Users should create a Trading 212 API key and API secret with read-only permissions, but this integration also enforces read-only behaviour by architecture.

## Planned v0.1 scope

- HACS-compatible custom integration
- Home Assistant config flow
- Shared `DataUpdateCoordinator`
- Compact account summary sensors
- Open-position count only
- Redacted diagnostics

## Initial sensors

- Account value
- Cash
- Free funds
- Invested
- Result
- Result percent
- Open positions
- Last update

Per-position entities are intentionally not created by default in v0.1 to avoid entity explosion.

## Installation during development

See [docs/DEVELOPMENT_INSTALL.md](docs/DEVELOPMENT_INSTALL.md) for the current manual development install steps.

Manual summary: copy `custom_components/trading212` into your Home Assistant `custom_components` directory, then restart Home Assistant.

HACS support will be hardened before public beta.
