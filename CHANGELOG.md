# Changelog

User-facing changes for released versions.

## 2026.06.19

- Fixed Trading 212 config-entry option merging so saved options now persist across reloads and future version updates.
- Ensured defaults are applied only for missing option keys and that the options form pre-fills from current saved values.

## 2026.06.18

- Moved pie detail hydration onto its own background cycle so setup stays fast while pie details refresh independently of the main coordinator interval.
- Refreshed the pie list at the start of each hydration cycle and walked pie details sequentially with adaptive pacing and cooldown handling.
- Added diagnostics for pie hydrator lifecycle state, pending detail work, and adaptive pacing visibility.

## 2026.06.17

- Changed pie detail hydration to incremental refresh-by-refresh fetching so Home Assistant setup does not wait on full pie detail walks.
- Limited pie detail hydration to a small bounded amount of work per refresh while preserving adaptive rate-limit learning and cooldown handling.
- Added non-sensitive diagnostics for pending pie detail hydration and pacing skips.

## 2026.06.16

- Added adaptive Trading 212 rate-limit learning so parsed 429 cooldowns can raise future pie detail pacing.
- Separated learned request pacing from endpoint-group cooldowns and minimum refresh intervals.
- Added cooldown safety buffer and maximum cap guardrails while keeping conservative fallbacks for invalid rate-limit responses.

## 2026.06.15

- Fixed Trading 212 endpoint-group cooldown handling so 429 responses never apply or log an immediate zero-second retry.
- Normalised invalid, zero, negative, tiny, non-finite, and past retry values to conservative applied cooldown windows.
- Kept pie detail pacing separate from rate-limit cooldown handling.

## 2026.06.14

- Added explicit read-only sequential pie detail fetching for pies summary sensors.
- Applied pie-detail rate-limit cooldowns to the pies endpoint group while preserving cached last-good data.
- Added safe pie detail diagnostics counts without raw pie or slice payloads.
- Added a position display-format option and defaulted position labels to friendly instrument names when available.

## 2026.06.13

- Improved Trading 212 API rate-limit handling.
- Parsed retry/cooldown timing from 429 response headers and safe response fields.
- Applied dynamic endpoint-group cooldowns so optional groups can cool down without breaking unrelated sensors.
- Added non-sensitive cooldown and last-good-data status to diagnostics.

## 2026.06.12

- Added optional read-only per-position entities.
- Kept per-position entities disabled by default.
- Added a configurable maximum per-position entity limit, defaulting to 50.
- Made disappeared position entities unavailable instead of reporting stale values.
- Kept the integration read-only and avoided per-position entities unless explicitly enabled.

## 2026.06.11

- Added optional read-only pies summary sensors.
- Kept pies summary disabled by default.
- Added endpoint throttling and cached last-good data for cooldown-limited pies data.
- Kept per-pie entities and pie-slice entities disabled by default.

## 2026.06.10

- Added positions summary and portfolio insight sensors.
- Kept per-position entities disabled by default.
- Added bounded sensor attributes for useful position summary details.

## 2026.06.9

- Added feature options for read-only data groups.
- Added endpoint-group status and cooldown handling.
- Kept high-volume entity groups disabled by default.

## 2026.06.8

- Improved multi-account setup.
- Kept the first/default account naming pattern.
- Required labels for additional accounts to avoid confusing entity names.

## 2026.06.7

- Added HACS and Home Assistant validation workflows.

## 2026.06.6

- Adjusted monetary sensor state classes for Home Assistant compatibility.

## 2026.06.3

- Added daily movement summary sensors based on a local Home Assistant day baseline.

## 2026.06.2

- Updated public release wording and installation guidance.

## 2026.06.1

- Prepared the initial public release package.
