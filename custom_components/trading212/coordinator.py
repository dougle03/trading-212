"""Data update coordinator for the Trading 212 integration."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, timedelta
import hashlib
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS,
    MAX_RATE_LIMIT_COOLDOWN_SECONDS,
    MAX_PIE_DETAIL_FETCHES_PER_REFRESH,
    MIN_RATE_LIMIT_COOLDOWN_SECONDS,
    PIE_HYDRATION_CYCLE_SECONDS,
    RATE_LIMIT_SAFETY_BUFFER_SECONDS,
    Trading212AuthError,
    Trading212Client,
    Trading212ConnectionError,
    Trading212Error,
    Trading212RateLimitError,
    fallback_rate_limit_cooldown_seconds_for_group,
    normalise_rate_limit_retry,
)
from .const import (
    CONF_POSITION_DISPLAY_FORMAT,
    DEFAULT_FEATURE_OPTIONS,
    DEFAULT_MAX_POSITION_ENTITIES,
    DEFAULT_POSITION_DISPLAY_FORMAT,
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
    MAX_POSITION_ENTITIES,
    MIN_POSITION_ENTITIES,
    POSITION_DISPLAY_FORMAT_NAME_TICKER,
    POSITION_DISPLAY_FORMAT_TICKER,
    POSITION_DISPLAY_FORMATS,
    STORAGE_KEY_PREFIX,
    STORAGE_VERSION,
)
from .options import get_entry_options

_LOGGER = logging.getLogger(__name__)


@dataclass
class EndpointGroupState:
    """Runtime state for one read-only endpoint group."""

    data: Any = None
    last_success: str | None = None
    last_failure: str | None = None
    last_failure_reason: str | None = None
    next_refresh: str | None = None
    cooldown_until: str | None = None
    retry_after_seconds: int | None = None
    last_error_category: str | None = None
    _logged_cooldown_until: str | None = None
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
        feature_options: dict[str, Any] | None = None,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Trading 212",
            update_interval=timedelta(seconds=update_interval_seconds),
        )
        self.client = client
        self.feature_options = get_entry_options(feature_options)
        self.max_position_entities = _normalise_max_position_entities(
            self.feature_options
        )
        self.position_display_format = _normalise_position_display_format(
            self.feature_options
        )
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
        self._pie_hydrator_task: asyncio.Task | None = None
        self._pie_hydrator_phase = "disabled"
        self._pie_hydrator_enabled = False
        self._pie_hydrator_last_cycle_started: str | None = None
        self._pie_hydrator_last_cycle_completed: str | None = None
        self._pie_hydrator_current_pie_id: str | None = None

    async def async_initialize(self) -> None:
        """Load the persisted daily baseline, if present."""
        stored = await self._store.async_load()
        if isinstance(stored, dict):
            self._daily_baseline = stored

    async def async_start_pie_hydrator(self) -> None:
        """Start the independent pie hydration task when pie features need it."""
        self._pie_hydrator_enabled = self._pie_features_enabled()
        if not self._pie_hydrator_enabled:
            self._pie_hydrator_phase = "disabled"
            return
        if self._pie_hydrator_task is not None and not self._pie_hydrator_task.done():
            return

        self._pie_hydrator_phase = "idle"
        self._pie_hydrator_task = asyncio.create_task(
            self._async_run_pie_hydrator(),
            name=f"trading212-pies-{id(self)}",
        )
        _LOGGER.info("Trading 212 pie hydrator started")

    async def async_stop_pie_hydrator(self) -> None:
        """Stop the independent pie hydration task cleanly."""
        self._pie_hydrator_enabled = False
        task = self._pie_hydrator_task
        if task is None:
            self._pie_hydrator_phase = "disabled"
            return

        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        self._pie_hydrator_task = None
        self._pie_hydrator_phase = "stopped"
        self._pie_hydrator_current_pie_id = None
        _LOGGER.info("Trading 212 pie hydrator stopped")

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
                group_data = await self._async_get_endpoint_group(group)
                if group_data is None and _is_core_endpoint_group(group):
                    raise UpdateFailed(
                        f"Trading 212 endpoint group {group} is cooling down"
                    )
                raw_data[group] = group_data
            except Trading212AuthError as err:
                raise UpdateFailed("Trading 212 API token was rejected") from err
            except Trading212RateLimitError as err:
                if state.data is None and _is_core_endpoint_group(group):
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

        return await self._compose_coordinator_data(
            summary=raw_data.get(ENDPOINT_GROUP_ACCOUNT_SUMMARY, {}),
            positions=raw_data.get(ENDPOINT_GROUP_POSITIONS, []),
            pie_group=raw_data.get(ENDPOINT_GROUP_PIES, {}),
        )

    async def _async_get_endpoint_group(self, group: str) -> Any:
        """Return endpoint group data using cooldown-aware last-good caching."""
        state = self._endpoint_groups[group]
        now = dt_util.utcnow()

        cooldown_until = _parse_state_datetime(state.cooldown_until)
        if cooldown_until is not None and now < cooldown_until:
            state.status = "cooling_down" if state.data is None else "using_last_good"
            return state.data

        if state.data is not None and state.next_refresh is not None:
            next_refresh = dt_util.parse_datetime(state.next_refresh)
            if next_refresh is not None and now < next_refresh:
                state.status = "cooldown"
                return state.data

        try:
            if group == ENDPOINT_GROUP_PIES:
                cached = self.client.current_pies_payload()
                state.data = cached
                state.count = _payload_count(cached)
                state.status = self._pie_endpoint_group_status()
                return cached
            data = await self.client.fetch_endpoint_group(group)
        except Trading212RateLimitError as err:
            if group == ENDPOINT_GROUP_PIES and err.partial_data is not None:
                state.data = _merge_pie_group_data(state.data, err.partial_data)
            retry_after_seconds, retry_at = _rate_limit_retry_window(err, now, group)
            state.last_failure = now.isoformat()
            state.last_failure_reason = type(err).__name__
            state.last_error_category = "rate_limited"
            state.retry_after_seconds = retry_after_seconds
            state.cooldown_until = retry_at.isoformat()
            state.next_refresh = retry_at.isoformat()
            state.status = "rate_limited" if state.data is None else "using_last_good"
            self._log_rate_limit_once(group, state)
            raise
        except (Trading212ConnectionError, Trading212Error) as err:
            state.last_failure = now.isoformat()
            state.last_failure_reason = type(err).__name__
            state.last_error_category = "api_error"
            state.status = "using_last_good" if state.data is not None else "failed"
            raise

        state.data = data
        state.last_success = now.isoformat()
        state.last_failure = None
        state.last_failure_reason = None
        state.last_error_category = None
        state.retry_after_seconds = None
        state.cooldown_until = None
        state.next_refresh = (
            now + timedelta(seconds=ENDPOINT_GROUP_MIN_REFRESH_SECONDS[group])
        ).isoformat()
        state.count = _payload_count(data)
        state.status = "ok"
        return data

    async def _compose_coordinator_data(
        self,
        *,
        summary: Any,
        positions: Any,
        pie_group: Any,
    ) -> dict[str, Any]:
        """Build the coordinator payload from current cached group data."""
        pies = _pies_from_group_payload(pie_group)
        if not isinstance(summary, dict):
            summary = {}
        if not isinstance(positions, list):
            positions = []

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
            display_format=self.position_display_format,
        )
        positions_summary = _build_positions_summary(
            positions=positions,
            account_value=_first_number(summary, "totalValue"),
            currency=_first_string(summary, "currency") or "GBP",
            last_update=now_utc,
            max_position_entities=self.max_position_entities,
            display_format=self.position_display_format,
        )
        pies_summary = _build_pies_summary(
            pies=pies,
            pie_group=pie_group if isinstance(pie_group, dict) else {},
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

    def _pie_endpoint_group_status(self) -> str:
        """Return the current pies endpoint-group status from hydrator state."""
        if not self._pie_hydrator_enabled:
            return "disabled"
        if self._pie_hydrator_phase == "cooling_down":
            return "cooling_down"
        if self._pie_hydrator_phase in {"list_fetch", "detail_fetch"}:
            return "hydrating"
        if self._pie_hydrator_phase == "error":
            return "failed"
        payload = self.client.current_pies_payload()
        if payload.get("list_loaded"):
            return "ok"
        return "pending"

    async def _async_run_pie_hydrator(self) -> None:
        """Run the independent pie hydration cycle."""
        state = self._endpoint_groups[ENDPOINT_GROUP_PIES]
        try:
            while self._pie_hydrator_enabled:
                cycle_started = dt_util.utcnow()
                self._pie_hydrator_last_cycle_started = cycle_started.isoformat()
                self._pie_hydrator_phase = "list_fetch"
                try:
                    payload = await self.client.refresh_pie_list_for_cycle()
                except Trading212RateLimitError as err:
                    await self._async_handle_pies_rate_limit(err)
                    await self._async_sleep_until_pies_retry()
                    continue
                except Exception:
                    self._pie_hydrator_phase = "error"
                    state.last_error_category = "error"
                    _LOGGER.exception("Trading 212 pie hydrator list fetch failed")
                    await asyncio.sleep(PIE_HYDRATION_CYCLE_SECONDS)
                    continue

                await self._async_publish_pie_payload(payload, phase="detail_fetch")

                while self._pie_hydrator_enabled:
                    next_pie_id = self.client._next_pending_pie_detail_id()
                    self._pie_hydrator_current_pie_id = next_pie_id
                    if next_pie_id is None:
                        break
                    if not self.client._pie_detail_request_ready():
                        wait_seconds = self.client.seconds_until_next_pie_detail_request()
                        self._pie_hydrator_phase = "detail_fetch"
                        _LOGGER.debug(
                            "Trading 212 pie detail hydration paused; waiting for learned pacing window"
                        )
                        await self._async_publish_pie_payload(
                            self.client.current_pies_payload(
                                detail_skipped_due_to_pacing=1
                            ),
                            phase="detail_fetch",
                        )
                        await asyncio.sleep(max(wait_seconds, 1))
                        continue

                    self._pie_hydrator_phase = "detail_fetch"
                    try:
                        payload = await self.client.hydrate_next_pie_detail()
                    except Trading212RateLimitError as err:
                        self.client._learn_request_pacing_from_rate_limit(err)
                        await self._async_handle_pies_rate_limit(err)
                        await self._async_sleep_until_pies_retry()
                        break
                    except Exception:
                        self._pie_hydrator_phase = "error"
                        state.last_error_category = "error"
                        _LOGGER.exception("Trading 212 pie hydrator detail fetch failed")
                        await asyncio.sleep(PIE_HYDRATION_CYCLE_SECONDS)
                        break

                    await self._async_publish_pie_payload(payload, phase="detail_fetch")
                    _LOGGER.debug(
                        "Trading 212 pie detail fetched for %s",
                        self._pie_hydrator_current_pie_id,
                    )

                if not self._pie_hydrator_enabled:
                    break
                if self._pie_hydrator_phase == "cooling_down":
                    continue

                self._pie_hydrator_current_pie_id = None
                self._pie_hydrator_phase = "complete"
                self._pie_hydrator_last_cycle_completed = dt_util.utcnow().isoformat()
                await self._async_publish_pie_payload(
                    self.client.current_pies_payload(),
                    phase="complete",
                )
                _LOGGER.debug("Trading 212 pie hydration cycle completed")
                await asyncio.sleep(PIE_HYDRATION_CYCLE_SECONDS)
        except asyncio.CancelledError:
            raise
        finally:
            self._pie_hydrator_task = None
            self._pie_hydrator_current_pie_id = None
            if not self._pie_hydrator_enabled:
                self._pie_hydrator_phase = "disabled"

    async def _async_handle_pies_rate_limit(self, err: Trading212RateLimitError) -> None:
        """Apply pies cooldown state after a rate limit from the hydrator."""
        state = self._endpoint_groups[ENDPOINT_GROUP_PIES]
        now = dt_util.utcnow()
        payload = err.partial_data if isinstance(err.partial_data, dict) else self.client.current_pies_payload(detail_rate_limited=True)
        retry_after_seconds, retry_at = _rate_limit_retry_window(
            err,
            now,
            ENDPOINT_GROUP_PIES,
        )
        state.data = _merge_pie_group_data(state.data, payload)
        state.last_failure = now.isoformat()
        state.last_failure_reason = type(err).__name__
        state.last_error_category = "rate_limited"
        state.retry_after_seconds = retry_after_seconds
        state.cooldown_until = retry_at.isoformat()
        state.next_refresh = retry_at.isoformat()
        state.count = _payload_count(state.data)
        state.status = "using_last_good" if state.data is not None else "rate_limited"
        self._pie_hydrator_phase = "cooling_down"
        self._log_rate_limit_once(ENDPOINT_GROUP_PIES, state)
        await self._async_publish_pie_payload(state.data, phase="cooling_down")

    async def _async_sleep_until_pies_retry(self) -> None:
        """Sleep until the pies cooldown expires."""
        state = self._endpoint_groups[ENDPOINT_GROUP_PIES]
        cooldown_until = _parse_state_datetime(state.cooldown_until)
        if cooldown_until is None:
            await asyncio.sleep(PIE_HYDRATION_CYCLE_SECONDS)
            return
        remaining = (cooldown_until - dt_util.utcnow()).total_seconds()
        await asyncio.sleep(max(int(remaining), 1))

    async def _async_publish_pie_payload(self, payload: Any, *, phase: str) -> None:
        """Publish updated pie payload to coordinator state and listeners."""
        state = self._endpoint_groups[ENDPOINT_GROUP_PIES]
        now = dt_util.utcnow().isoformat()
        state.data = payload
        state.count = _payload_count(payload)
        state.last_success = now
        state.last_failure = None if phase != "cooling_down" else state.last_failure
        if phase != "cooling_down":
            state.last_failure_reason = None
            state.last_error_category = None
            state.retry_after_seconds = None
            state.cooldown_until = None
            state.next_refresh = now
        state.status = self._pie_endpoint_group_status()
        self._pie_hydrator_phase = phase

        if self.data is None:
            return
        composed = await self._compose_coordinator_data(
            summary=self.data.get("summary", {}),
            positions=self.data.get("positions", []),
            pie_group=payload,
        )
        self.async_set_updated_data(composed)

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
        status = {
            group: {
                "status": state.status,
                "last_success": state.last_success,
                "last_failure": state.last_failure,
                "last_failure_reason": state.last_failure_reason,
                "next_refresh": state.next_refresh,
                "cooldown_until": state.cooldown_until,
                "retry_after_seconds": state.retry_after_seconds,
                "last_error_category": state.last_error_category,
                "count": state.count,
                "has_last_good_data": state.data is not None,
                "min_refresh_seconds": ENDPOINT_GROUP_MIN_REFRESH_SECONDS[group],
                "endpoint_group": group,
            }
            for group, state in self._endpoint_groups.items()
        }
        if ENDPOINT_GROUP_PIES in status:
            status[ENDPOINT_GROUP_PIES].update(
                {
                    "hydrator_enabled": self._pie_hydrator_enabled,
                    "hydrator_running": self._pie_hydrator_task is not None
                    and not self._pie_hydrator_task.done(),
                    "hydrator_phase": self._pie_hydrator_phase,
                    "hydrator_last_cycle_started": self._pie_hydrator_last_cycle_started,
                    "hydrator_last_cycle_completed": self._pie_hydrator_last_cycle_completed,
                    "hydrator_current_pie_id": self._pie_hydrator_current_pie_id,
                }
            )
        return status

    def _log_rate_limit_once(self, group: str, state: EndpointGroupState) -> None:
        """Log a rate-limit cooldown once per cooldown window."""
        if state.cooldown_until == state._logged_cooldown_until:
            return
        state._logged_cooldown_until = state.cooldown_until
        _LOGGER.warning(
            "Trading 212 endpoint group %s is rate limited; cooling down for %s seconds",
            group,
            state.retry_after_seconds,
        )

    def _pie_features_enabled(self) -> bool:
        """Return whether any pie-backed feature currently needs hydration."""
        return bool(
            self.feature_options.get(FEATURE_PIES_SUMMARY)
            or self.feature_options.get(FEATURE_PER_PIE_ENTITIES)
        )

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


def _normalise_feature_options(options: dict[str, Any] | None) -> dict[str, Any]:
    """Return feature options with safe defaults for missing keys."""
    normalised = dict(DEFAULT_FEATURE_OPTIONS)
    if isinstance(options, dict):
        for key in normalised:
            if key in options:
                normalised[key] = bool(options[key])
    normalised["account_summary"] = True
    return normalised


def _normalise_max_position_entities(options: dict[str, Any] | None) -> int:
    """Return a bounded per-position entity limit."""
    value = DEFAULT_MAX_POSITION_ENTITIES
    if isinstance(options, dict) and "max_position_entities" in options:
        try:
            value = int(options["max_position_entities"])
        except (TypeError, ValueError):
            value = DEFAULT_MAX_POSITION_ENTITIES
    return min(max(value, MIN_POSITION_ENTITIES), MAX_POSITION_ENTITIES)


def _normalise_position_display_format(options: dict[str, Any] | None) -> str:
    """Return the preferred position display format."""
    if isinstance(options, dict):
        value = options.get(CONF_POSITION_DISPLAY_FORMAT)
        if isinstance(value, str) and value in POSITION_DISPLAY_FORMATS:
            return value
    return DEFAULT_POSITION_DISPLAY_FORMAT


def _payload_count(data: Any) -> int | None:
    """Return a safe payload count for diagnostics without exposing payload data."""
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        pies = data.get("pies")
        if isinstance(pies, list):
            return len(pies)
        return len(data)
    return None


def _pies_from_group_payload(data: Any) -> list[dict[str, Any]]:
    """Return pie items from the cached pies endpoint-group payload."""
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        pies = data.get("pies")
        if isinstance(pies, list):
            return [item for item in pies if isinstance(item, dict)]
    return []


def _merge_pie_group_data(existing: Any, partial: Any) -> Any:
    """Merge a partial detail refresh with previous last-good pie data."""
    if not isinstance(partial, dict):
        return existing

    previous_pies = {
        pie_id: pie
        for pie in _pies_from_group_payload(existing)
        if (pie_id := _pie_id(pie)) is not None
    }
    merged = []
    seen_ids: set[str] = set()
    for pie in _pies_from_group_payload(partial):
        pie_id = _pie_id(pie)
        if pie_id is not None and pie_id in previous_pies:
            merged.append({**previous_pies[pie_id], **pie})
            seen_ids.add(pie_id)
        else:
            merged.append(pie)
            if pie_id is not None:
                seen_ids.add(pie_id)

    for pie_id, previous_pie in previous_pies.items():
        if pie_id not in seen_ids:
            merged.append(previous_pie)

    if not merged and existing is not None:
        return existing

    existing_group = existing if isinstance(existing, dict) else {}
    return {
        **existing_group,
        **partial,
        "pies": merged,
        "complete": False,
    }


def _is_core_endpoint_group(group: str) -> bool:
    """Return whether missing data should block setup/update."""
    return group in {
        ENDPOINT_GROUP_ACCOUNT_SUMMARY,
        ENDPOINT_GROUP_POSITIONS,
    }


def _parse_state_datetime(value: str | None):
    """Parse stored endpoint-group timestamps."""
    if value is None:
        return None
    return dt_util.parse_datetime(value)


def _rate_limit_retry_window(
    err: Trading212RateLimitError,
    now,
    group: str,
) -> tuple[int, Any]:
    """Return retry-after seconds and absolute retry time for a rate limit."""
    fallback_seconds = fallback_rate_limit_cooldown_seconds_for_group(group)
    retry_after_seconds, retry_at, _used_fallback = normalise_rate_limit_retry(
        retry_after_seconds=err.retry_after_seconds,
        retry_at=err.retry_at,
        now=now,
        fallback_seconds=max(fallback_seconds, DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS),
        minimum_seconds=max(
            ENDPOINT_GROUP_MIN_REFRESH_SECONDS.get(group, MIN_RATE_LIMIT_COOLDOWN_SECONDS),
            MIN_RATE_LIMIT_COOLDOWN_SECONDS,
        ),
        safety_buffer_seconds=RATE_LIMIT_SAFETY_BUFFER_SECONDS,
        maximum_seconds=MAX_RATE_LIMIT_COOLDOWN_SECONDS,
    )
    return retry_after_seconds, retry_at


def _build_pies_summary(
    *,
    pies: list[dict[str, Any]],
    pie_group: dict[str, Any],
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
        "pie_list_count": _safe_int(pie_group.get("list_count")),
        "pie_detail_count": _safe_int(pie_group.get("detail_count")),
        "pie_detail_pending_count": _safe_int(pie_group.get("detail_pending_count")),
        "pie_detail_attempted_this_refresh": _safe_int(
            pie_group.get("detail_attempted_this_refresh")
        ),
        "pie_detail_skipped_count": _safe_int(
            pie_group.get("detail_skipped_count")
        ),
        "pie_detail_skipped_due_to_pacing": _safe_int(
            pie_group.get("detail_skipped_due_to_pacing")
        ),
        "pie_detail_rate_limited": bool(pie_group.get("detail_rate_limited")),
        "pie_detail_complete": bool(pie_group.get("complete")),
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
        _first_nested_number(
            pie,
            "value",
            "currentValue",
            "totalValue",
            "marketValue",
        )
    )
    cash = _round_money(
        _first_nested_number(pie, "cash", "availableCash", "cashValue")
    )
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
        "source": _first_string(pie, "detail_status") or "list",
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
        "source": entry.get("source"),
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
    result = _first_nested_number(
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
    max_position_entities: int,
    display_format: str,
) -> dict[str, Any]:
    """Build bounded summary-only portfolio insight data."""
    entries = [
        entry
        for position in positions
        if (
            entry := _position_summary_entry(
                position,
                currency,
                last_update,
                display_format,
            )
        )
        is not None
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
    entity_entries = sorted(
        (entry for entry in entries if entry.get("entity_id") is not None),
        key=_position_entity_sort_key,
    )
    exposed_entity_entries = entity_entries[:max_position_entities]

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
        "position_entities": exposed_entity_entries,
        "position_entities_by_id": {
            str(entry["entity_id"]): entry for entry in exposed_entity_entries
        },
        "position_entities_limit": max_position_entities,
        "position_entities_available": len(entity_entries),
        "position_entities_exposed": len(exposed_entity_entries),
        "position_entities_truncated": len(entity_entries) > len(exposed_entity_entries),
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
    display_format: str,
) -> dict[str, Any] | None:
    """Build bounded summary data for one position."""
    label = _position_label(position, display_format)
    if label is None:
        return None

    entity_id = _position_entity_id(position)
    value = _round_money(_position_current_value(position))
    result = _round_money(_position_result(position))
    result_percent = None
    cost = _position_cost(position)
    if result is not None and cost not in (None, 0):
        result_percent = round((result / cost) * 100, 2)

    return {
        "entity_id": entity_id,
        "state": label,
        "ticker": _position_ticker(position),
        "name": _position_name(position),
        "isin": _position_isin(position),
        "instrument_id": _position_instrument_id(position),
        "exchange": _position_exchange(position),
        "type": _position_type(position),
        "value": value,
        "result": result,
        "result_percent": result_percent,
        "quantity": _position_quantity(position),
        "average_price": _position_average_price(position),
        "current_price": _position_current_price(position),
        "currency": currency,
        "last_update": last_update.isoformat(),
    }


def _position_entity_sort_key(entry: dict[str, Any]) -> tuple[Any, ...]:
    """Return deterministic ordering for per-position entity creation."""
    value = entry.get("value")
    sortable_value = float(value) if isinstance(value, int | float) else 0.0
    return (-sortable_value, str(entry.get("ticker") or ""), str(entry.get("entity_id")))


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
        "isin": entry.get("isin"),
        "instrument_id": entry.get("instrument_id"),
        "value": entry.get("value"),
        "result": entry.get("result"),
        "result_percent": entry.get("result_percent"),
        "quantity": entry.get("quantity"),
        "average_price": entry.get("average_price"),
        "current_price": entry.get("current_price"),
        "currency": entry.get("currency"),
        "exchange": entry.get("exchange"),
        "type": entry.get("type"),
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
    display_format: str,
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
                display_format=display_format,
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
    display_format: str,
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
        "state": _position_label(position, display_format),
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


def _position_entity_id(position: dict[str, Any]) -> str | None:
    """Return a stable per-position entity identifier."""
    isin = _position_isin(position)
    if isin:
        return f"isin_{_stable_token(isin)}"

    ticker = _position_ticker(position)
    if ticker:
        return f"ticker_{_stable_token(ticker)}"

    position_id = _position_instrument_id(position) or _first_string(
        position,
        "id",
        "positionId",
    )
    if position_id:
        return f"id_{_stable_token(position_id)}"

    parts = [
        _position_name(position) or "",
        _first_string(position, "currency") or "",
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"hash_{digest}"


def _stable_token(value: str) -> str:
    """Return a Home Assistant-safe stable token."""
    token = "".join(
        character.lower() if character.isalnum() else "_"
        for character in value.strip()
    ).strip("_")
    return token or hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _position_ticker(position: dict[str, Any]) -> str | None:
    """Return the position ticker if available."""
    instrument = position.get("instrument")
    if isinstance(instrument, dict):
        ticker = _first_string(instrument, "ticker")
        if ticker:
            return ticker
    return _first_string(position, "ticker")


def _position_isin(position: dict[str, Any]) -> str | None:
    """Return the instrument ISIN if available."""
    instrument = position.get("instrument")
    if isinstance(instrument, dict):
        isin = _first_string(instrument, "isin")
        if isin:
            return isin
    return _first_string(position, "isin")


def _position_instrument_id(position: dict[str, Any]) -> str | None:
    """Return a stable instrument or position identifier when available."""
    instrument = position.get("instrument")
    if isinstance(instrument, dict):
        for key in ("id", "instrumentId", "ticker"):
            value = instrument.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, int):
                return str(value)
    for key in ("instrumentId", "positionId", "id"):
        value = position.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int):
            return str(value)
    return None


def _position_name(position: dict[str, Any]) -> str | None:
    """Return the position display name if available."""
    instrument = position.get("instrument")
    if isinstance(instrument, dict):
        return _first_string(instrument, "name")
    return _first_string(position, "name")


def _position_exchange(position: dict[str, Any]) -> str | None:
    """Return exchange information if already present in the position payload."""
    instrument = position.get("instrument")
    if isinstance(instrument, dict):
        exchange = _first_string(instrument, "exchange", "exchangeCode")
        if exchange:
            return exchange
    return _first_string(position, "exchange", "exchangeCode")


def _position_type(position: dict[str, Any]) -> str | None:
    """Return instrument type if already present in the position payload."""
    instrument = position.get("instrument")
    if isinstance(instrument, dict):
        instrument_type = _first_string(instrument, "type", "instrumentType")
        if instrument_type:
            return instrument_type
    return _first_string(position, "type", "instrumentType")


def _position_label(
    position: dict[str, Any],
    display_format: str = DEFAULT_POSITION_DISPLAY_FORMAT,
) -> str | None:
    """Return the preferred state label for a position summary sensor."""
    name = _position_name(position)
    ticker = _position_ticker(position)
    if display_format == POSITION_DISPLAY_FORMAT_TICKER:
        return ticker or name
    if display_format == POSITION_DISPLAY_FORMAT_NAME_TICKER:
        if name and ticker and name != ticker:
            return f"{name} ({ticker})"
        return name or ticker
    return name or ticker


def _position_quantity(position: dict[str, Any]) -> float | None:
    """Return the position quantity."""
    return _round_quantity(_first_number(position, "quantity"))


def _position_average_price(position: dict[str, Any]) -> float | None:
    """Return average price if already present in the position payload."""
    return _round_money(
        _first_number(
            position,
            "averagePrice",
            "avgPrice",
            "averageOpeningPrice",
            "priceAvg",
        )
    )


def _position_current_price(position: dict[str, Any]) -> float | None:
    """Return current price if already present in the position payload."""
    return _round_money(
        _first_number(
            position,
            "currentPrice",
            "price",
            "marketPrice",
        )
    )


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


def _safe_int(value: Any) -> int | None:
    """Return an int from a stored numeric value."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
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


def _first_nested_number(source: dict[str, Any], *keys: str) -> float | None:
    """Return the first numeric value found at top level or common detail containers."""
    value = _first_number(source, *keys)
    if value is not None:
        return value
    for container_key in ("summary", "overview", "result", "investmentResult"):
        container = source.get(container_key)
        if isinstance(container, dict):
            value = _first_number(container, *keys)
            if value is not None:
                return value
    return None


def _first_string(source: dict[str, Any], *keys: str) -> str | None:
    """Return the first non-empty string value found for the supplied keys."""
    for key in keys:
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
