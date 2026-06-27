# Trading 212 Lovelace Card

This folder contains a custom Lovelace card prototype for the Trading 212
integration.

## Files

- `trading212-portfolio-card.js`: custom element implementation

## Manual install

1. Copy the `cards/` folder to a location Home Assistant can serve as a frontend
   resource.
2. Add `trading212-portfolio-card.js` as a Lovelace module resource.
3. Use the card as:

```yaml
type: custom:trading212-portfolio-card
entity_prefix: trading_212
```

You can also pass explicit entity IDs:

```yaml
type: custom:trading212-portfolio-card
entities:
  account_value: sensor.trading_212_account_value
  cash: sensor.trading_212_cash
  free_funds: sensor.trading_212_free_funds
  invested: sensor.trading_212_invested
  open_positions: sensor.trading_212_open_positions
  result: sensor.trading_212_result
  daily_gain_loss: sensor.trading_212_daily_gain_loss
  total_unrealised_result: sensor.trading_212_total_unrealised_result
  top_5_position_concentration_percentage: sensor.trading_212_top_5_position_concentration_percentage
  top_daily_mover: sensor.trading_212_top_daily_mover
  bottom_daily_mover: sensor.trading_212_bottom_daily_mover
  biggest_daily_gain_value: sensor.trading_212_biggest_daily_gain_value
  biggest_daily_loss_value: sensor.trading_212_biggest_daily_loss_value
  last_update: sensor.trading_212_last_update
```

If the integration exposes optional per-position entities, the card will use
them automatically for richer mover and allocation sections.
