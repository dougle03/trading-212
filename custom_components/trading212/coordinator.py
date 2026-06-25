"""Data update coordinator for the Trading 212 integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    Trading212AuthError,
    Trading212Client,
    Trading212ConnectionError,
    Trading212Error,
    Trading212RateLimitError,
)
from .const import STORAGE_KEY_PREFIX, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)


class Trading212DataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that fetches all Trading 212 data once per refresh."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: Trading212Client,
        entry_id: str,
        update_interval_seconds: int,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Trading 212",
            update_interval=timedelta(seconds=update_interval_seconds),
        )
        self.client = client
        self._store = Store[dict[str, Any]](
            hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY_PREFIX}_{entry_id}",
        )
        self._daily_baseline: dict[str, Any] | None = None

    async def async_initialize(self) -> None:
        """Load the persisted daily baseline, if present."""
        stored = await self._store.async_load()
        if isinstance(stored, dict):
            self._daily_baseline = stored

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Trading 212."""
        try:
            raw_data = await self.client.fetch_account_data()
        except Trading212AuthError as err:
            raise UpdateFailed("Trading 212 API token was rejected") from err
        except Trading212RateLimitError as err:
            raise UpdateFailed("Trading 212 API rate limit reached") from err
        except Trading212ConnectionError as err:
            raise UpdateFailed("Unable to connect to Trading 212 API") from err
        except Trading212Error as err:
            raise UpdateFailed(f"Trading 212 API error: {err}") from err

        summary = raw_data.get("summary", {})
        positions = raw_data.get("positions", [])

        cash = summary.get("cash", {})
        if not isinstance(cash, dict):
            cash = {}

        investments = summary.get("investments", {})
        if not isinstance(investments, dict):
            investments = {}

        cash_available = _first_number(cash, "availableToTrade")
        cash_in_pies = _first_number(cash, "inPies") or 0
        cash_reserved = _first_number(cash, "reservedForOrders") or 0

        cash_total = None
        if cash_available is not None:
            cash_total = cash_available + cash_in_pies + cash_reserved

        invested = _first_number(investments, "totalCost")
        result = _first_number(investments, "unrealizedProfitLoss")

        result_percent = None
        if invested not in (None, 0) and result is not None:
            result_percent = round((result / invested) * 100, 2)

        if cash_total is not None:
            cash_total = round(cash_total, 2)
        if cash_available is not None:
            cash_available = round(cash_available, 2)
        if invested is not None:
            invested = round(invested, 2)
        if result is not None:
            result = round(result, 2)

        now_utc = dt_util.utcnow()
        now_local = dt_util.as_local(now_utc)
        baseline = await self._async_ensure_daily_baseline(
            summary=summary,
            positions=positions,
            local_date=now_local.date().isoformat(),
            baseline_time=now_local.isoformat(),
        )
        daily_summary = _build_daily_summary(
            baseline=baseline,
            positions=positions,
            current_account_value=_first_number(summary, "totalValue"),
            currency=_first_string(summary, "currency") or "GBP",
            last_update=now_utc,
        )

        return {
            "summary": summary,
            "positions": positions,
            "account_value": _first_number(summary, "totalValue"),
            "cash": cash_total,
            "free_funds": cash_available,
            "invested": invested,
            "result": result,
            "result_percent": result_percent,
            "open_positions": len(positions),
            "currency": _first_string(summary, "currency") or "GBP",
            "last_update": now_utc,
            **daily_summary,
        }

    async def _async_ensure_daily_baseline(
        self,
        *,
        summary: dict[str, Any],
        positions: list[dict[str, Any]],
        local_date: str,
        baseline_time: str,
    ) -> dict[str, Any]:
        """Return the current local-day baseline, creating it if needed."""
        if self._daily_baseline and self._daily_baseline.get("date") == local_date:
            return self._daily_baseline

        baseline = {
            "date": local_date,
            "baseline_time": baseline_time,
            "account_value": _round_money(_first_number(summary, "totalValue")),
            "positions": _build_position_baseline(positions),
        }
        self._daily_baseline = baseline
        await self._store.async_save(baseline)
        return baseline


def _build_position_baseline(positions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Capture opening values for positions that have a stable key and value."""
    baseline_positions: dict[str, dict[str, Any]] = {}
    for position in positions:
        key = _position_key(position)
        current_value = _position_current_value(position)
        if key is None or current_value is None:
            continue
        baseline_positions[key] = {
            "value": _round_money(current_value),
            "ticker": _position_ticker(position),
            "name": _position_name(position),
            "quantity": _position_quantity(position),
        }
    return baseline_positions


def _build_daily_summary(
    *,
    baseline: dict[str, Any],
    positions: list[dict[str, Any]],
    current_account_value: float | None,
    currency: str,
    last_update,
) -> dict[str, Any]:
    """Build summary-only daily movement data for the sensors."""
    opening_value = _safe_number(baseline.get("account_value"))
    current_value = _round_money(current_account_value)
    change_value = None
    change_percent = None
    if opening_value is not None and current_value is not None:
        change_value = round(current_value - opening_value, 2)
        if opening_value != 0:
            change_percent = round((change_value / opening_value) * 100, 2)

    mover_entries: list[dict[str, Any]] = []
    baseline_positions = baseline.get("positions", {})
    if isinstance(baseline_positions, dict):
        for position in positions:
            entry = _position_movement_entry(
                position=position,
                baseline_positions=baseline_positions,
                opening_portfolio_value=opening_value,
                currency=currency,
                baseline_time=baseline.get("baseline_time"),
                last_update=last_update,
            )
            if entry is not None:
                mover_entries.append(entry)

    top_mover = max(
        (entry for entry in mover_entries if entry.get("change_percent") is not None),
        key=lambda entry: float(entry["change_percent"]),
        default=None,
    )
    bottom_mover = min(
        (entry for entry in mover_entries if entry.get("change_percent") is not None),
        key=lambda entry: float(entry["change_percent"]),
        default=None,
    )
    biggest_gain = max(
        (
            entry
            for entry in mover_entries
            if entry.get("change_value") is not None and float(entry["change_value"]) > 0
        ),
        key=lambda entry: float(entry["change_value"]),
        default=None,
    )
    biggest_loss = min(
        (
            entry
            for entry in mover_entries
            if entry.get("change_value") is not None and float(entry["change_value"]) < 0
        ),
        key=lambda entry: float(entry["change_value"]),
        default=None,
    )

    return {
        "daily_gain_loss": change_value,
        "daily_gain_loss_percent": change_percent,
        "top_daily_mover": _entity_state(top_mover),
        "bottom_daily_mover": _entity_state(bottom_mover),
        "biggest_daily_gain_value": _entity_state(biggest_gain),
        "biggest_daily_loss_value": _entity_state(biggest_loss),
        "daily_gain_loss_attrs": _account_daily_attributes(
            opening_value, current_value, change_value, change_percent, currency, baseline, last_update
        ),
        "daily_gain_loss_percent_attrs": _account_daily_attributes(
            opening_value, current_value, change_value, change_percent, currency, baseline, last_update
        ),
        "top_daily_mover_attrs": _mover_attributes(top_mover),
        "bottom_daily_mover_attrs": _mover_attributes(bottom_mover),
        "biggest_daily_gain_value_attrs": _mover_attributes(biggest_gain),
        "biggest_daily_loss_value_attrs": _mover_attributes(biggest_loss),
    }


def _position_movement_entry(
    *,
    position: dict[str, Any],
    baseline_positions: dict[str, Any],
    opening_portfolio_value: float | None,
    currency: str,
    baseline_time: str | None,
    last_update,
) -> dict[str, Any] | None:
    """Build movement data for one position when a same-day baseline exists."""
    key = _position_key(position)
    if key is None:
        return None

    opening = baseline_positions.get(key)
    if not isinstance(opening, dict):
        return None

    opening_value = _safe_number(opening.get("value"))
    current_value = _position_current_value(position)
    if opening_value is None or current_value is None:
        return None

    change_value = round(current_value - opening_value, 2)
    change_percent = None
    if opening_value != 0:
        change_percent = round((change_value / opening_value) * 100, 2)

    portfolio_impact_percent = None
    if opening_portfolio_value not in (None, 0):
        portfolio_impact_percent = round((change_value / opening_portfolio_value) * 100, 2)

    return {
        "state": _position_label(position),
        "ticker": _position_ticker(position),
        "name": _position_name(position),
        "change_value": change_value,
        "change_percent": change_percent,
        "position_value": _round_money(current_value),
        "currency": currency,
        "quantity": _position_quantity(position),
        "portfolio_impact_percent": portfolio_impact_percent,
        "baseline_time": baseline_time,
        "last_update": last_update.isoformat(),
    }


def _account_daily_attributes(
    opening_value: float | None,
    current_value: float | None,
    change_value: float | None,
    change_percent: float | None,
    currency: str,
    baseline: dict[str, Any],
    last_update,
) -> dict[str, Any]:
    """Build shared account-level daily movement attributes."""
    return {
        "opening_value": opening_value,
        "current_value": current_value,
        "change_value": change_value,
        "change_percent": change_percent,
        "currency": currency,
        "baseline_time": baseline.get("baseline_time"),
        "last_update": last_update.isoformat(),
    }


def _mover_attributes(entry: dict[str, Any] | None) -> dict[str, Any]:
    """Build mover sensor attributes."""
    if entry is None:
        return {}
    return {
        "ticker": entry.get("ticker"),
        "name": entry.get("name"),
        "change_value": entry.get("change_value"),
        "change_percent": entry.get("change_percent"),
        "position_value": entry.get("position_value"),
        "currency": entry.get("currency"),
        "quantity": entry.get("quantity"),
        "portfolio_impact_percent": entry.get("portfolio_impact_percent"),
        "baseline_time": entry.get("baseline_time"),
        "last_update": entry.get("last_update"),
    }


def _entity_state(entry: dict[str, Any] | None) -> str | None:
    """Return the string sensor state for a mover entry."""
    if entry is None:
        return None
    value = entry.get("state")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _position_key(position: dict[str, Any]) -> str | None:
    """Return a stable key for a position."""
    instrument = position.get("instrument")
    if isinstance(instrument, dict):
        ticker = _first_string(instrument, "ticker")
        if ticker:
            return ticker
        isin = _first_string(instrument, "isin")
        if isin:
            return isin
    return _first_string(position, "ticker")


def _position_ticker(position: dict[str, Any]) -> str | None:
    """Return the position ticker if available."""
    instrument = position.get("instrument")
    if isinstance(instrument, dict):
        ticker = _first_string(instrument, "ticker")
        if ticker:
            return ticker
    return _first_string(position, "ticker")


def _position_name(position: dict[str, Any]) -> str | None:
    """Return the position display name if available."""
    instrument = position.get("instrument")
    if isinstance(instrument, dict):
        return _first_string(instrument, "name")
    return _first_string(position, "name")


def _position_label(position: dict[str, Any]) -> str | None:
    """Return the preferred state label for a position summary sensor."""
    return _position_name(position) or _position_ticker(position)


def _position_quantity(position: dict[str, Any]) -> float | None:
    """Return the position quantity."""
    return _round_quantity(_first_number(position, "quantity"))


def _position_current_value(position: dict[str, Any]) -> float | None:
    """Return the current position market value in account currency."""
    wallet_impact = position.get("walletImpact")
    if isinstance(wallet_impact, dict):
        value = _first_number(wallet_impact, "currentValue")
        if value is not None:
            return value
    return None


def _round_money(value: float | None) -> float | None:
    """Round money values consistently."""
    if value is None:
        return None
    return round(value, 2)


def _round_quantity(value: float | None) -> float | None:
    """Round quantities for display without over-formatting."""
    if value is None:
        return None
    return round(value, 6)


def _safe_number(value: Any) -> float | None:
    """Return a float from a stored numeric value."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _first_number(source: dict[str, Any], *keys: str) -> float | None:
    """Return the first numeric value found for the supplied keys."""
    for key in keys:
        value = source.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int | float):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue
    return None


def _first_string(source: dict[str, Any], *keys: str) -> str | None:
    """Return the first non-empty string value found for the supplied keys."""
    for key in keys:
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
