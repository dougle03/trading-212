# Changelog

## 2026.06.22

- Fixed daily market P/L fallback to use holdings-value baseline deltas when explicit daily position fields are unavailable.
- Fixed bounded pie `top_slices` population after successful pie detail hydration.

## 2026.06.21

- Separated holdings-only portfolio movement from cash-inclusive account change.
- Clarified pie holding value versus pie total value including cash.
- Added bounded pie slice summaries without mixing pie instruments into global holdings data.

## 2026.06.20

- Added a first-release-candidate custom Lovelace Trading 212 dashboard card
  under `cards/`.

## 2026.06.19

- Fixed saved option handling across reloads and version updates.

## 2026.06.18

- Improved optional pies summary refresh handling.

## 2026.06.17

- Improved setup behaviour when optional pie details are enabled.

## 2026.06.16

- Improved Trading 212 rate-limit handling.

## 2026.06.15

- Fixed cooldown handling for rate-limited Trading 212 API responses.
