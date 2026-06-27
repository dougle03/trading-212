"""Data update coordinator for the Trading 212 integration."""

from __future__ import annotations

from dataclasses import dataclass
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
from .const import (
    DEFAULT_FEATURE_OPTIONS,
    ENDPOINT_GROUP_ACCOUNT_SUMMARY,
    ENDPOINT_GROUP_DIVIDENDS,
    ENDPOINT_GROUP_MIN_REFRESH_SECONDS,
    ENDPOINT_GROUP_ORDERS,
    ENDPOINT_GROUP_PIES,
    ENDPOINT_GROUP_POSITIONS,
    FEATURE_DIVIDENDS_SUMMARY,
    FEATURE_MOVERS_DAILY,
    FEATURE_ORDERS_SUMMARY,
    FEATURE_PER_PIE_ENTITIES,
    FEATURE_PER_POSITION_ENTITIES,
    FEATURE_PIES_SUMMARY,
    FEATURE_POSITIONS_SUMMARY,
    IMPLEMENTED_ENDPOINT_GROUPS,
    STORAGE_KEY_PREFIX,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class EndpointGroupState:
    """Runtime state for one read-only endpoint group."""

    data: Any = None
    last_success: str | None = None
    last_failure: str | None = None
    last_failure_reason: str | None = None
    next_refresh: str | None = None
    count: int | None = None
    status: str = "pending"


class Trading212DataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that fetches all Trading 212 data once per refresh."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: Trading212Client,
        entry_id: str,
        update_interval_seconds: int,
        feature_options: dict[str, bool] | None = None,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Trading 212",
            update_interval=timedelta(seconds=update_interval_seconds),
        )
        self.client = client
        self.feature_options = _normalise_feature_options(feature_options)
        self._store = Store[dict[str, Any]](
            hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY_PREFIX}_{entry_id}",
        )
        self._daily_baseline: dict[str, Any] | None = None
        self._endpoint_groups: dict[str, EndpointGroupState] = {
            group: EndpointGroupState(status="disabled")
            for group in ENDPOINT_GROUP_MIN_REFRESH_SECONDS
        }

    async def async_initialize(self) -> None:
        """Load the persisted daily baseline, if present."""
        stored = await self._store.async_load()
        if isinstance(stored, dict):
            self._daily_baseline = stored

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Trading 212."""
        enabled_groups = self._enabled_endpoint_groups()
        raw_data: dict[str, Any] = {}
        for group in ENDPOINT_GROUP_MIN_REFRESH_SECONDS:
            state = self._endpoint_groups[group]
            if group not in enabled_groups:
                state.status = "disabled"
                continue
            if group not in IMPLEMENTED_ENDPOINT_GROUPS:
                state.status = "not_implemented"
                continue

            try:
                raw_data[group] = await self._async_get_endpoint_group(group)
            except Trading212AuthError as err:
                raise UpdateFailed("Trading 212 API token was rejected") from err
            except Trading212RateLimitError as err:
                if state.data is None:
                    raise UpdateFailed("Trading 212 API rate limit reached") from err
                raw_data[group] = state.data
            except Trading212ConnectionError as err:
                if state.data is None:
                    raise UpdateFailed("Unable to connect to Trading 212 API") from err
                raw_data[group] = state.data
            except Trading212Error as err:
                if state.data is None:
                    raise UpdateFailed(f"Trading 212 API error: {err}") from err
                raw_data[group] = state.data

        summary = raw_data.get(ENDPOINT_GROUP_ACCOUNT_SUMMARY, {})
        positions = raw_data.get(ENDPOINT_GROUP_POSITIONS, [])
        pies = raw_data.get(ENDPOINT_GROUP_PIES, [])
        if not isinstance(summary, dict):
            summary = {}
        if not isinstance(positions, list):
            positions = []
        if not isinstance(pies, list):
            pies = []

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
        positions_summary = _build_positions_summary(
            positions=positions,
            account_value=_first_number(summary, "totalValue"),
            currency=_first_string(summary, "currency") or "GBP",
            last_update=now_utc,
        )
        pies_summary = _build_pies_summary(
            pies=pies,
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
            **positions_summary,
            **pies_summary,
            **daily_summary,
        }

    async def _async_get_endpoint_group(self, group: str) -> Any:
        """Return endpoint group data using cooldown-aware last-good caching."""
        state = self._endpoint_groups[group]
        now = dt_util.utcnow()

        if state.data is not None and state.next_refresh is not None:
            next_refresh = dt_util.parse_datetime(state.next_refresh)
            if next_refresh is not None and now < next_refresh:
                state.status = "cooldown"
                return state.data

        try:
            data = await self.client.fetch_endpoint_group(group)
        except (Trading212RateLimitError, Trading212ConnectionError, Trading212Error) as err:
            state.last_failure = now.isoformat()
            state.last_failure_reason = type(err).__name__
            state.status = "using_last_good" if state.data is not None else "failed"
            raise

        state.data = data
        state.last_success = now.isoformat()
        state.last_failure = None
        state.last_failure_reason = None
        state.next_refresh = (
            now + timedelta(seconds=ENDPOINT_GROUP_MIN_REFRESH_SECONDS[group])
        ).isoformat()
        state.count = _payload_count(data)
        state.status = "ok"
        return data

    def _enabled_endpoint_groups(self) -> set[str]:
        """Return endpoint groups required by enabled feature options."""
        groups = {ENDPOINT_GROUP_ACCOUNT_SUMMARY}
        if (
            self.feature_options[FEATURE_POSITIONS_SUMMARY]
            or self.feature_options[FEATURE_PER_POSITION_ENTITIES]
            or self.feature_options[FEATURE_MOVERS_DAILY]
        ):
            groups.add(ENDPOINT_GROUP_POSITIONS)
        if (
            self.feature_options[FEATURE_PIES_SUMMARY]
            or self.feature_options[FEATURE_PER_PIE_ENTITIES]
        ):
            groups.add(ENDPOINT_GROUP_PIES)
        if self.feature_options[FEATURE_DIVIDENDS_SUMMARY]:
            groups.add(ENDPOINT_GROUP_DIVIDENDS)
        if self.feature_options[FEATURE_ORDERS_SUMMARY]:
            groups.add(ENDPOINT_GROUP_ORDERS)
        return groups

    @property
    def endpoint_group_status(self) -> dict[str, dict[str, Any]]:
        """Return redacted endpoint group status for diagnostics."""
        return {
            group: {
                "status": state.status,
                "last_success": state.last_success,
                "last_failure": state.last_failure,
                "last_failure_reason": state.last_failure_reason,
                "next_refresh": state.next_refresh,
                "count": state.count,
                "min_refresh_seconds": ENDPOINT_GROUP_MIN_REFRESH_SECONDS[group],
            }
            for group, state in self._endpoint_groups.items()
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


def _normalise_feature_options(options: dict[str, bool] | None) -> dict[str, bool]:
    """Return feature options with safe defaults for missing keys."""
    normalised = dict(DEFAULT_FEATURE_OPTIONS)
    if isinstance(options, dict):
        for key in normalised:
            if key in options:
                normalised[key] = bool(options[key])
    normalised["account_summary"] = True
    return normalised


def _payload_count(data: Any) -> int | None:
    """Return a safe payload count for diagnostics without exposing payload data."""
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        return len(data)
    return None


def _build_pies_summary(
    *,
    pies: list[dict[str, Any]],
    currency: str,
    last_update,
) -> dict[str, Any]:
    """Build bounded summary-only pie data."""
    entries = [
        entry
        for pie in pies
        if (entry := _pie_summary_entry(pie, currency, last_update)) is not None
    ]
    value_entries = [entry for entry in entries if entry.get("value") is not None]
    cash_entries = [entry for entry in entries if entry.get("cash") is not None]
    result_entries = [entry for entry in entries if entry.get("result") is not None]

    total_value = (
        _round_money(sum(float(entry["value"]) for entry in value_entries))
        if value_entries
        else None
    )
    total_cash = (
        _round_money(sum(float(entry["cash"]) for entry in cash_entries))
        if cash_entries
        else None
    )
    total_result = (
        _round_money(sum(float(entry["result"]) for entry in result_entries))
        if result_entries
        else None
    )
    largest_pie = max(
        value_entries,
        key=lambda entry: float(entry["value"]),
        default=None,
    )

    last_pie_update = _latest_pie_update(entries)
    aggregate_attrs = {
        "pies_with_value": len(value_entries),
        "pies_with_cash": len(cash_entries),
        "pies_with_result": len(result_entries),
        "currency": currency,
        "last_update": last_update.isoformat(),
    }

    return {
        "pies_count": len(entries),
        "total_pies_value": total_value,
        "total_pies_cash": total_cash,
        "total_pies_result": total_result,
        "largest_pie": _entity_state(largest_pie),
        "largest_pie_value": _entry_number(largest_pie, "value"),
        "last_pie_update_time": last_pie_update,
        "pies_count_attrs": aggregate_attrs,
        "total_pies_value_attrs": aggregate_attrs,
        "total_pies_cash_attrs": aggregate_attrs,
        "total_pies_result_attrs": aggregate_attrs,
        "largest_pie_attrs": _pie_summary_attributes(largest_pie),
        "largest_pie_value_attrs": _pie_summary_attributes(largest_pie),
        "last_pie_update_time_attrs": aggregate_attrs,
    }


def _pie_summary_entry(
    pie: dict[str, Any],
    currency: str,
    last_update,
) -> dict[str, Any] | None:
    """Build bounded summary data for one pie."""
    label = _pie_label(pie)
    if label is None:
        return None

    value = _round_money(
        _first_number(
            pie,
            "value",
            "currentValue",
            "totalValue",
            "marketValue",
        )
    )
    cash = _round_money(_first_number(pie, "cash", "availableCash", "cashValue"))
    result = _round_money(_pie_result(pie))
    updated_at = _first_string(
        pie,
        "lastUpdated",
        "lastUpdateTime",
        "updatedAt",
        "lastModified",
    )

    return {
        "state": label,
        "pie_id": _pie_id(pie),
        "value": value,
        "cash": cash,
        "result": result,
        "currency": _first_string(pie, "currency") or currency,
        "created_at": _first_string(pie, "createdAt", "creationDate"),
        "updated_at": updated_at,
        "last_update": last_update.isoformat(),
    }


def _pie_summary_attributes(entry: dict[str, Any] | None) -> dict[str, Any]:
    """Build bounded attributes for a pie summary sensor."""
    if entry is None:
        return {}
    return {
        "pie_id": entry.get("pie_id"),
        "value": entry.get("value"),
        "cash": entry.get("cash"),
        "result": entry.get("result"),
        "currency": entry.get("currency"),
        "created_at": entry.get("created_at"),
        "updated_at": entry.get("updated_at"),
        "last_update": entry.get("last_update"),
    }


def _pie_label(pie: dict[str, Any]) -> str | None:
    """Return the preferred state label for a pie summary sensor."""
    label = _first_string(pie, "name", "title", "pieName")
    if label is not None:
        return label

    settings = pie.get("settings")
    if isinstance(settings, dict):
        label = _first_string(settings, "name", "title", "pieName")
        if label is not None:
            return label

    pie_id = _pie_id(pie)
    if pie_id is not None:
        return f"Pie {pie_id}"
    return None


def _pie_id(pie: dict[str, Any]) -> str | None:
    """Return a stable pie identifier when exposed by the API."""
    for key in ("id", "pieId", "instrumentId"):
        value = pie.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int):
            return str(value)
    return None


def _pie_result(pie: dict[str, Any]) -> float | None:
    """Return a bounded numeric pie result when directly available."""
    result = _first_number(
        pie,
        "result",
        "profitLoss",
        "unrealizedProfitLoss",
        "unrealisedProfitLoss",
    )
    if result is not None:
        return result

    result_data = pie.get("result")
    if isinstance(result_data, dict):
        return _first_number(
            result_data,
            "value",
            "absolute",
            "profitLoss",
            "unrealizedProfitLoss",
            "unrealisedProfitLoss",
        )
    return None


def _latest_pie_update(entries: list[dict[str, Any]]) -> Any:
    """Return the latest directly exposed pie update timestamp."""
    values = []
    for entry in entries:
        value = entry.get("updated_at")
        if not isinstance(value, str) or not value:
            continue
        parsed = dt_util.parse_datetime(value)
        if parsed is not None:
            values.append(parsed)
    return max(values, default=None)


def _build_positions_summary(
    *,
    positions: list[dict[str, Any]],
    account_value: float | None,
    currency: str,
    last_update,
) -> dict[str, Any]:
    """Build bounded summary-only portfolio insight data."""
    entries = [
        entry
        for position in positions
        if (entry := _position_summary_entry(position, currency, last_update)) is not None
    ]

    value_entries = [entry for entry in entries if entry.get("value") is not None]
    result_entries = [entry for entry in entries if entry.get("result") is not None]

    total_position_value = round(
        sum(float(entry["value"]) for entry in value_entries),
        2,
    )
    portfolio_value = account_value
    if portfolio_value in (None, 0) and total_position_value != 0:
        portfolio_value = total_position_value

    largest_position = max(
        value_entries,
        key=lambda entry: float(entry["value"]),
        default=None,
    )
    largest_position_value = _entry_number(largest_position, "value")

    largest_position_percent = None
    if largest_position_value is not None and portfolio_value not in (None, 0):
        largest_position_percent = round((largest_position_value / portfolio_value) * 100, 2)

    top_five_value = sum(
        float(entry["value"])
        for entry in sorted(
            value_entries,
            key=lambda entry: float(entry["value"]),
            reverse=True,
        )[:5]
    )
    top_five_concentration_percent = None
    if portfolio_value not in (None, 0):
        top_five_concentration_percent = round((top_five_value / portfolio_value) * 100, 2)

    total_unrealised_result = None
    if result_entries:
        total_unrealised_result = round(
            sum(float(entry["result"]) for entry in result_entries),
            2,
        )

    best_position = _best_result_entry(result_entries)
    worst_position = _worst_result_entry(result_entries)

    return {
        "largest_position": _entity_state(largest_position),
        "largest_position_value": largest_position_value,
        "largest_position_percentage": largest_position_percent,
        "top_5_position_concentration_percentage": top_five_concentration_percent,
        "positions_in_profit": sum(
            1 for entry in result_entries if float(entry["result"]) > 0
        ),
        "positions_in_loss": sum(
            1 for entry in result_entries if float(entry["result"]) < 0
        ),
        "total_unrealised_result": total_unrealised_result,
        "best_position": _entity_state(best_position),
        "best_position_result": _entry_number(best_position, "result"),
        "worst_position": _entity_state(worst_position),
        "worst_position_result": _entry_number(worst_position, "result"),
        "largest_position_attrs": _position_summary_attributes(largest_position),
        "largest_position_value_attrs": _position_summary_attributes(largest_position),
        "largest_position_percentage_attrs": _position_summary_attributes(
            largest_position
        ),
        "top_5_position_concentration_percentage_attrs": {
            "positions_counted": min(len(value_entries), 5),
            "total_positions_with_value": len(value_entries),
            "top_5_value": _round_money(top_five_value) if value_entries else None,
            "portfolio_value": _round_money(portfolio_value),
            "currency": currency,
            "last_update": last_update.isoformat(),
        },
        "positions_in_profit_attrs": _position_count_attributes(
            result_entries,
            currency,
            last_update,
        ),
        "positions_in_loss_attrs": _position_count_attributes(
            result_entries,
            currency,
            last_update,
        ),
        "total_unrealised_result_attrs": _position_count_attributes(
            result_entries,
            currency,
            last_update,
        ),
        "best_position_attrs": _position_summary_attributes(best_position),
        "best_position_result_attrs": _position_summary_attributes(best_position),
        "worst_position_attrs": _position_summary_attributes(worst_position),
        "worst_position_result_attrs": _position_summary_attributes(worst_position),
    }


def _position_summary_entry(
    position: dict[str, Any],
    currency: str,
    last_update,
) -> dict[str, Any] | None:
    """Build bounded summary data for one position."""
    label = _position_label(position)
    if label is None:
        return None

    value = _round_money(_position_current_value(position))
    result = _round_money(_position_result(position))
    result_percent = None
    cost = _position_cost(position)
    if result is not None and cost not in (None, 0):
        result_percent = round((result / cost) * 100, 2)

    return {
        "state": label,
        "ticker": _position_ticker(position),
        "name": _position_name(position),
        "value": value,
        "result": result,
        "result_percent": result_percent,
        "quantity": _position_quantity(position),
        "currency": currency,
        "last_update": last_update.isoformat(),
    }


def _best_result_entry(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the best position by result percentage, then result value."""
    return max(
        entries,
        key=lambda entry: (
            float(entry["result_percent"])
            if entry.get("result_percent") is not None
            else float("-inf"),
            float(entry["result"]),
        ),
        default=None,
    )


def _worst_result_entry(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the worst position by result percentage, then result value."""
    return min(
        entries,
        key=lambda entry: (
            float(entry["result_percent"])
            if entry.get("result_percent") is not None
            else float("inf"),
            float(entry["result"]),
        ),
        default=None,
    )


def _entry_number(entry: dict[str, Any] | None, key: str) -> float | None:
    """Return a numeric value from a summary entry."""
    if entry is None:
        return None
    return _safe_number(entry.get(key))


def _position_summary_attributes(entry: dict[str, Any] | None) -> dict[str, Any]:
    """Build bounded attributes for a position summary sensor."""
    if entry is None:
        return {}
    return {
        "ticker": entry.get("ticker"),
        "name": entry.get("name"),
        "value": entry.get("value"),
        "result": entry.get("result"),
        "result_percent": entry.get("result_percent"),
        "quantity": entry.get("quantity"),
        "currency": entry.get("currency"),
        "last_update": entry.get("last_update"),
    }


def _position_count_attributes(
    entries: list[dict[str, Any]],
    currency: str,
    last_update,
) -> dict[str, Any]:
    """Build bounded aggregate attributes for position count/result sensors."""
    return {
        "positions_with_result": len(entries),
        "positions_in_profit": sum(
            1 for entry in entries if float(entry["result"]) > 0
        ),
        "positions_in_loss": sum(
            1 for entry in entries if float(entry["result"]) < 0
        ),
        "currency": currency,
        "last_update": last_update.isoformat(),
    }


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


def _position_cost(position: dict[str, Any]) -> float | None:
    """Return the position cost basis when available."""
    wallet_impact = position.get("walletImpact")
    if isinstance(wallet_impact, dict):
        value = _first_number(wallet_impact, "totalCost", "cost")
        if value is not None:
            return value
    return _first_number(position, "totalCost", "cost")


def _position_result(position: dict[str, Any]) -> float | None:
    """Return the current unrealised position result."""
    wallet_impact = position.get("walletImpact")
    if isinstance(wallet_impact, dict):
        result = _first_number(
            wallet_impact,
            "unrealizedProfitLoss",
            "unrealisedProfitLoss",
            "result",
            "profitLoss",
        )
        if result is not None:
            return result

    result = _first_number(
        position,
        "unrealizedProfitLoss",
        "unrealisedProfitLoss",
        "result",
        "profitLoss",
    )
    if result is not None:
        return result

    current_value = _position_current_value(position)
    cost = _position_cost(position)
    if current_value is not None and cost is not None:
        return current_value - cost
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
