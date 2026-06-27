# Trading 212 Home Assistant Integration

A Home Assistant custom integration for monitoring Trading 212 account and portfolio summary data.

This integration is read-only. It does not place trades, cancel orders, edit pies, deposit, withdraw, or provide Home Assistant controls that mutate a Trading 212 account.

This project is not affiliated with, endorsed by, or supported by Trading 212.

## Features

- Home Assistant config flow and options flow
- HACS-compatible custom integration
- Account summary sensors
- Positions summary and portfolio insight sensors
- Daily movement summary sensors based on a local Home Assistant day baseline
- Optional per-position entities, disabled by default
- Optional pies summary sensors with paced read-only pie detail fetching, disabled by default
- Redacted diagnostics
- Multi-account setup with labels for additional accounts

## Sensors

Core sensors include:

- Account value
- Cash
- Free funds
- Invested
- Result
- Result percent
- Open positions
- Last update

Positions and daily movement sensors include:

- Daily gain/loss
- Daily gain/loss percent
- Top daily mover
- Bottom daily mover
- Biggest daily gain value
- Biggest daily loss value
- Largest position
- Largest position value
- Largest position percentage
- Top 5 position concentration
- Positions in profit
- Positions in loss
- Total unrealised result
- Best position
- Best position result
- Worst position
- Worst position result

Optional pies summary sensors include:

- Pies count
- Total pies value
- Total pies cash
- Total pies result
- Largest pie
- Largest pie value
- Last pie update time, when the API provides one

Per-position entities, per-pie entities, and pie-slice entities are not created by default.

## Install With HACS

Until this integration is available through the default HACS store, add it as a custom repository:

1. Open Home Assistant.
2. Open HACS.
3. Select the three-dot menu in the top-right corner.
4. Select **Custom repositories**.
5. Add this repository URL:

   `https://github.com/dougle03/trading-212`

6. Select category **Integration**.
7. Select **Add**.
8. Install **Trading 212** from HACS.
9. Restart Home Assistant.
10. Go to **Settings -> Devices & services -> Add integration** and search for **Trading 212**.

## Manual Installation

If you prefer not to use HACS:

1. Copy `custom_components/trading212` into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.
3. Go to **Settings -> Devices & services -> Add integration** and search for **Trading 212**.

## Configuration

When adding the integration, provide:

- API key
- API secret
- Environment, usually `live`
- Update interval in seconds
- Account label, required for additional accounts

The first/default account keeps the normal Trading 212 entity naming pattern. Additional accounts should use labels so their entities remain distinct.

## Creating API Credentials

Create a Trading 212 API key and secret in the Trading 212 web app before adding the integration:

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

Screenshots for the credential flow are in [docs/DEVELOPMENT_INSTALL.md](docs/DEVELOPMENT_INSTALL.md).

## Feature Options

The options flow controls read-only feature groups.

Account summary, positions summary, and daily movement are enabled by default. Pies summary is available but disabled by default. Per-position and per-pie entity groups are disabled by default to avoid creating a large number of entities.

Per-position entities are optional. When enabled, the integration creates one sensor per open position up to the configured maximum, which defaults to `50` and can be set from `1` to `250`. Users with many holdings may get many entities. Position entity names and position summary text use the selected display format where the API provides enough data, defaulting to instrument names with ticker/code retained in attributes. If there are more open positions than the configured limit, the integration exposes a deterministic first set and reports truncation in diagnostics. Reloading the integration may be required after changing optional entity groups so entities can appear or become unavailable cleanly.

Pies summary refreshes the Trading 212 pie list first, then hydrates pie details on its own safe background cycle with adaptive pacing. It does not fetch pie details once per sensor or block normal setup/reload. Pie data may temporarily show unavailable or unknown while detail hydration is still pending or while the integration waits out Trading 212 cooldowns.

Optional endpoints may be cooldown-limited by Trading 212. When the API returns a rate-limit response, the integration reads the retry timing where available, adapts future pacing where practical, marks only that endpoint group as cooling down, keeps unrelated groups working, and waits for the cooldown before retrying. Cached last-good data is reused where available, and diagnostics report the endpoint group status without raw financial payloads.

## Dashboard Examples

Example dashboard YAML files are included at the repository root:

- [simple-dashboard-card.yaml](simple-dashboard-card.yaml)
- [advanced_dashboard_card.yaml](advanced_dashboard_card.yaml)
- [daily_movement_dashboard_card.yaml](daily_movement_dashboard_card.yaml)

The simple example uses standard Home Assistant cards only. The advanced examples may require custom Lovelace cards noted in each file.

## Known Limitations

- Daily movement is calculated from the integration's local Home Assistant day baseline, not Trading 212's official market-day performance figures.
- Pies summary is optional and depends on the Trading 212 pies list and pie detail endpoints being available for the API token.
- Optional endpoint groups may temporarily show unavailable or cooling down if Trading 212 rate limits are hit.
- Per-position, per-pie, and pie-slice entities are not created by default.
- Per-position entities are opt-in and limited by the configured maximum.
- The integration only reads Trading 212 API data; it does not manage accounts or execute actions.

## Security

Use a read-only Trading 212 API token only. Do not enable write, trading, deposit, withdrawal, order execution, or pie write permissions for this integration.

See [SECURITY.md](SECURITY.md) for the security policy and reporting guidance.

## Support

Use [GitHub Issues](https://github.com/dougle03/trading-212/issues) for bug reports, read-only API data requests, dashboard examples, and feature requests.

Do not paste API keys, API secrets, account identifiers, or sensitive financial details into issues, logs, screenshots, or diagnostics.
