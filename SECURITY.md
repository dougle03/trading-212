# Security Policy

## Read-Only Boundary

This integration is read-only.

It must not:

- place trades
- cancel orders
- edit pies
- rebalance pies
- invest into pies
- deposit funds
- withdraw funds
- mutate the Trading 212 account in any way

The integration must not expose Home Assistant services, buttons, switches, selects, or other controls that modify a Trading 212 account.

## API Tokens

Use a read-only Trading 212 API token only.

Enable only the read permissions needed by the integration, such as account data, metadata, and portfolio access. Leave write, trading, order execution, deposit, withdrawal, and pie write permissions disabled.

API keys and API secrets must not be logged, printed, included in diagnostics, or shared in GitHub Issues.

## Network Access

The integration should not make outbound calls except to the Trading 212 API and Home Assistant-required services.

## Reporting Token Exposure

If you suspect a Trading 212 API token or secret has been exposed:

1. Revoke the token in Trading 212 immediately.
2. Create a new read-only token if you still need the integration.
3. Remove the exposed token from logs, screenshots, diagnostics, or issue comments.
4. Report the issue through GitHub Issues without including the token or other sensitive account details.

## Reporting Security Issues

When reporting a security concern, do not include API keys, API secrets, account identifiers, balances, positions, or other sensitive financial details.
