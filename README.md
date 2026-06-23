# Trading 212 Home Assistant Integration

A Home Assistant custom integration for monitoring Trading 212 account and portfolio summary data.

Active development: ## Roadmap | See [docs/ROADMAP.md](docs/ROADMAP.md) for planned read-only feature ideas and areas where community feedback is welcome.

## Status

Current public release `2026.06.2`. Initial Home Assistant smoke test has passed with read-only API key and secret authentication.

This integration is intended to remain strictly read-only.

## Safety boundary

This integration is designed to be read-only for the public release.

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

This project is not affiliated with, endorsed by, or supported by Trading 212.

Use read-only API permissions only.

API credentials are stored by Home Assistant as config entry data and are redacted from diagnostics.

## Public release scope

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

Per-position entities are intentionally not created by default to avoid entity explosion.

## Installation during development

See [docs/DEVELOPMENT_INSTALL.md](docs/DEVELOPMENT_INSTALL.md) for the current manual development install steps.

Manual summary: copy `custom_components/trading212` into your Home Assistant `custom_components` directory, then restart Home Assistant.

## Creating Trading 212 API credentials

Before setting up the integration, create a Trading 212 API key and secret in the Trading 212 web app:

1. Sign in at [https://app.trading212.com](https://app.trading212.com).
2. Open `Settings` -> `API (Beta)` -> `Generate API key`.
3. Choose a key name that identifies this Home Assistant installation.
4. Select `Unrestricted IP access` unless you have a fixed public IP and want to restrict the key to trusted outbound IPs.
5. Enable only the read permissions needed by the integration:
   - `Account data`
   - `Metadata`
   - `Portfolio`
6. Leave all write or trading permissions disabled, including:
   - `Orders - Execute`
   - `Pies - Write`
   - any other mutation or trading permission
7. Save the generated API key and secret for use in Home Assistant.

If you want screenshots, see the walkthrough in [docs/DEVELOPMENT_INSTALL.md](docs/DEVELOPMENT_INSTALL.md).

HACS support is included for the public release.

## Dashboard examples

Example dashboard YAML files are included at the repository root:

- [simple-dashboard-card.yaml](simple-dashboard-card.yaml)
- [advanced_dashboard_card.yaml](advanced_dashboard_card.yaml)

The simple example uses standard Home Assistant cards only.

The advanced example expects Mushroom, stack-in-card, ApexCharts Card, and the Trading 212 logo at `/local/images/212.png`.
