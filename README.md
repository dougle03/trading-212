# Trading 212 Home Assistant Integration

A read-only Home Assistant custom integration for basic Trading 212 account and portfolio monitoring.

This project is not affiliated with, endorsed by, or supported by Trading 212.

## Install

Add this repository to HACS as a custom repository:

1. Open Home Assistant.
2. Open HACS.
3. Open the three-dot menu and select **Custom repositories**.
4. Add `https://github.com/dougle03/trading-212` as an **Integration**.
5. Install **Trading 212** from HACS.
6. Restart Home Assistant.

## Setup

In Home Assistant, go to **Settings -> Devices & services -> Add integration** and search for **Trading 212**.

Use a read-only Trading 212 API token only. Enable only read permissions such as account data, metadata, and portfolio access. Do not enable trading, order execution, pie write, deposit, withdrawal, or other mutation permissions.

## Features

- Account summary sensors
- Position and portfolio summary sensors
- Daily movement summary sensors
- Optional pies summary sensors
- Optional per-position sensors
- Redacted diagnostics
- Multiple accounts

## Support

Use GitHub Issues for bug reports. Do not include API keys, API secrets, account identifiers, balances, positions, screenshots, logs, or diagnostics containing private account data.

## Licence

See [LICENSE](LICENSE).
