"""Data update coordinator for the Trading 212 integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    Trading212AuthError,
    Trading212Client,
    Trading212ConnectionError,
    Trading212Error,
    Trading212RateLimitError,
)

_LOGGER = logging.getLogger(__name__)


class Trading212DataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that fetches all Trading 212 data once per refresh."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: Trading212Client,
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
            result_percent = (result / invested) * 100

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
            "last_update": dt_util.utcnow(),
        }


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
