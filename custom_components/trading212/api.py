"""Read-only Trading 212 API client."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
import json
import logging
import math
import re
from typing import Any
from urllib.parse import quote

from aiohttp import BasicAuth, ClientError, ClientResponse, ClientSession

from .const import ENDPOINT_GROUP_MIN_REFRESH_SECONDS, ENVIRONMENT_URLS

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS = 300
MIN_RATE_LIMIT_COOLDOWN_SECONDS = 1
MAX_RATE_LIMIT_COOLDOWN_SECONDS = 3600
RATE_LIMIT_SAFETY_BUFFER_SECONDS = 1
PIE_DETAIL_PACING_SECONDS = 7
MAX_PIE_DETAIL_FETCHES_PER_REFRESH = 1
PIE_HYDRATION_CYCLE_SECONDS = 300

ENDPOINT_GROUP_ACCOUNT_SUMMARY = "account_summary"
ENDPOINT_GROUP_POSITIONS = "positions"
ENDPOINT_GROUP_PIES = "pies"

REQUEST_KIND_ACCOUNT_SUMMARY = "account_summary"
REQUEST_KIND_POSITIONS = "positions"
REQUEST_KIND_PIE_LIST = "pie_list"
REQUEST_KIND_PIE_DETAIL = "pie_detail"


class Trading212Error(Exception):
    """Base Trading 212 API error."""


class Trading212AuthError(Trading212Error):
    """Trading 212 authentication or authorisation error."""


class Trading212RateLimitError(Trading212Error):
    """Trading 212 rate limit error."""

    def __init__(
        self,
        message: str = "Trading 212 API rate limit reached",
        *,
        path: str | None = None,
        retry_after_seconds: int | None = None,
        retry_at: datetime | None = None,
        endpoint_group: str | None = None,
        request_kind: str | None = None,
        cooldown_source: str | None = None,
        partial_data: Any = None,
    ) -> None:
        """Initialise the rate-limit error."""
        super().__init__(message)
        self.path = path
        self.retry_after_seconds = retry_after_seconds
        self.retry_at = retry_at
        self.endpoint_group = endpoint_group
        self.request_kind = request_kind
        self.cooldown_source = cooldown_source
        self.partial_data = partial_data


class Trading212ConnectionError(Trading212Error):
    """Trading 212 connection error."""


class Trading212Client:
    """Small read-only Trading 212 API client.

    This client intentionally exposes only read methods.
    Do not add order placement, cancellation, pie editing, withdrawal,
    deposit, or generic raw endpoint methods for v0.1.
    """

    def __init__(
        self,
        session: ClientSession,
        api_key: str,
        api_secret: str,
        environment: str,
    ) -> None:
        """Initialise the client."""
        if environment not in ENVIRONMENT_URLS:
            raise ValueError(f"Unsupported Trading 212 environment: {environment}")

        self._session = session
        self._auth = BasicAuth(api_key, api_secret)
        self._base_url = ENVIRONMENT_URLS[environment].rstrip("/")
        self._learned_request_pacing_seconds: dict[str, int] = {
            REQUEST_KIND_PIE_LIST: ENDPOINT_GROUP_MIN_REFRESH_SECONDS[ENDPOINT_GROUP_PIES],
            REQUEST_KIND_PIE_DETAIL: PIE_DETAIL_PACING_SECONDS,
        }
        self._last_rate_limit_headers: dict[str, dict[str, int | str | None]] = {}
        self._last_request_at: dict[str, datetime] = {}
        self._next_allowed_request_at: dict[str, datetime] = {}
        self._latest_pies: list[dict[str, Any]] = []
        self._pie_list_loaded = False
        self._pie_detail_cache: dict[str, dict[str, Any]] = {}
        self._pending_pie_detail_ids: list[str] = []

    async def get_account_summary(self) -> dict[str, Any]:
        """Return Trading 212 account cash and equity summary."""
        data = await self._get_json("/equity/account/summary")
        if not isinstance(data, dict):
            raise Trading212Error("Unexpected account summary response")
        return data

    async def get_positions(self) -> list[dict[str, Any]]:
        """Return open positions."""
        data = await self._get_json("/equity/positions")
        if not isinstance(data, list):
            raise Trading212Error("Unexpected positions response")
        return [item for item in data if isinstance(item, dict)]

    async def get_pies(self) -> list[dict[str, Any]]:
        """Return Trading 212 pies from the read-only pies endpoint."""
        self._raise_if_request_locked(
            REQUEST_KIND_PIE_LIST,
            "/equity/pies",
            partial_data=self.current_pies_payload(),
        )
        data = await self._get_json("/equity/pies")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in ("pies", "items", "data", "results"):
                items = data.get(key)
                if isinstance(items, list):
                    return [item for item in items if isinstance(item, dict)]
        raise Trading212Error("Unexpected pies response")

    async def get_pie_detail(self, pie_id: str) -> dict[str, Any]:
        """Return one Trading 212 pie detail from the read-only detail endpoint."""
        detail_path_id = _format_pie_detail_path_id(pie_id)
        path = f"/equity/pies/{quote(detail_path_id, safe='')}"
        self._raise_if_request_locked(
            REQUEST_KIND_PIE_DETAIL,
            path,
            partial_data=self.current_pies_payload(detail_rate_limited=True),
        )
        data = await self._get_json(path)
        if not isinstance(data, dict):
            raise Trading212Error("Unexpected pie detail response")
        return data

    async def get_pies_with_details(self) -> dict[str, Any]:
        """Return the current cached pies payload without blocking hydration."""
        return self.current_pies_payload()

    async def refresh_pie_list_for_cycle(self) -> dict[str, Any]:
        """Refresh the pie list at the start of a hydration cycle."""
        pies = await self.get_pies()
        self._latest_pies = pies
        self._pie_list_loaded = True
        self._refresh_pending_pie_detail_ids(pies)
        return self.current_pies_payload()

    async def hydrate_next_pie_detail(self) -> dict[str, Any]:
        """Fetch the next pending pie detail."""
        next_pie_id = self._next_pending_pie_detail_id()
        if next_pie_id is None:
            return self.current_pies_payload()

        detail = await self.get_pie_detail(next_pie_id)
        self._pie_detail_cache[next_pie_id] = detail
        self._remove_pending_pie_detail_id(next_pie_id)
        return self.current_pies_payload(detail_attempted_this_refresh=1)

    def current_pies_payload(
        self,
        *,
        detail_attempted_this_refresh: int = 0,
        detail_skipped_due_to_pacing: int = 0,
        detail_rate_limited: bool = False,
    ) -> dict[str, Any]:
        """Return the best available current pies payload from cached state."""
        skipped_missing_id = sum(
            1 for pie in self._latest_pies if _pie_id(pie) is None
        )
        return self._build_pies_payload(
            self._latest_pies,
            attempted_this_refresh=detail_attempted_this_refresh,
            skipped_due_to_pacing=detail_skipped_due_to_pacing,
            skipped_missing_id=skipped_missing_id,
            rate_limited=detail_rate_limited,
        )

    async def fetch_account_data(self) -> dict[str, Any]:
        """Fetch all data needed by the coordinator in one shared update."""
        summary, positions = await asyncio.gather(
            self.get_account_summary(),
            self.get_positions(),
        )

        return {
            "summary": summary,
            "positions": positions,
        }

    async def fetch_endpoint_group(self, group: str) -> Any:
        """Fetch a known read-only endpoint group."""
        if group == "account_summary":
            return await self.get_account_summary()
        if group == "positions":
            return await self.get_positions()
        if group == "pies":
            return await self.get_pies_with_details()

        raise Trading212Error(f"Unsupported Trading 212 endpoint group: {group}")

    def request_pacing_seconds(self, request_kind: str) -> int:
        """Return the current learned pacing for a request kind."""
        if request_kind in {REQUEST_KIND_PIE_LIST, REQUEST_KIND_PIE_DETAIL}:
            return self._learned_request_pacing_seconds.get(
                request_kind,
                ENDPOINT_GROUP_MIN_REFRESH_SECONDS[ENDPOINT_GROUP_PIES]
                if request_kind == REQUEST_KIND_PIE_LIST
                else PIE_DETAIL_PACING_SECONDS,
            )
        return MIN_RATE_LIMIT_COOLDOWN_SECONDS

    @property
    def rate_limit_state(self) -> dict[str, Any]:
        """Return non-sensitive adaptive rate-limit state."""
        return {
            "request_pacing_seconds": dict(self._learned_request_pacing_seconds),
            "request_next_allowed_at": {
                kind: retry_at.isoformat()
                for kind, retry_at in self._next_allowed_request_at.items()
            },
            "request_last_rate_limit_headers": dict(self._last_rate_limit_headers),
            "pie_detail_pending_count": len(self._pending_pie_detail_ids),
            "pie_detail_hydrated_count": len(self._pie_detail_cache),
            "pie_list_count": len(self._latest_pies),
            "pie_list_loaded": self._pie_list_loaded,
        }

    def _minimum_rate_limit_cooldown_seconds(self, request_kind: str) -> int:
        """Return the minimum cooldown to apply after a 429."""
        if request_kind in {REQUEST_KIND_PIE_LIST, REQUEST_KIND_PIE_DETAIL}:
            return self.request_pacing_seconds(request_kind)
        return _minimum_rate_limit_cooldown_seconds(request_kind)

    def _fallback_rate_limit_cooldown_seconds(self, request_kind: str) -> int:
        """Return the fallback cooldown to apply after a 429."""
        if request_kind == REQUEST_KIND_PIE_DETAIL:
            return max(PIE_DETAIL_PACING_SECONDS, self.request_pacing_seconds(request_kind))
        if request_kind == REQUEST_KIND_PIE_LIST:
            return max(
                ENDPOINT_GROUP_MIN_REFRESH_SECONDS[ENDPOINT_GROUP_PIES],
                self.request_pacing_seconds(request_kind),
            )
        return _fallback_rate_limit_cooldown_seconds_for_request_kind(request_kind)

    def _learn_request_pacing_from_rate_limit(self, err: Trading212RateLimitError) -> None:
        """Increase learned request pacing when the API provides a stronger signal."""
        if err.request_kind != REQUEST_KIND_PIE_DETAIL:
            return
        if err.cooldown_source != "parsed":
            return
        if err.retry_after_seconds is None:
            return

        self._learn_request_pacing_seconds(
            REQUEST_KIND_PIE_DETAIL,
            err.retry_after_seconds,
            source="rate limit response",
        )

    def learn_request_pacing_from_cooldown(
        self,
        request_kind: str,
        cooldown_seconds: int | None,
        *,
        source: str,
    ) -> None:
        """Increase learned pacing from an applied safe cooldown window."""
        self._learn_request_pacing_seconds(request_kind, cooldown_seconds, source=source)

    def pie_hydration_status(self) -> dict[str, int | bool]:
        """Return non-sensitive pie hydration counts for logging and diagnostics."""
        return {
            "list_loaded": self._pie_list_loaded,
            "list_count": len(self._latest_pies),
            "hydrated_count": len(self._pie_detail_cache),
            "pending_count": len(self._pending_pie_detail_ids),
            "pacing_seconds": self.request_pacing_seconds(REQUEST_KIND_PIE_DETAIL),
        }

    def _learn_request_pacing_seconds(
        self,
        request_kind: str,
        seconds: int | None,
        *,
        source: str,
    ) -> None:
        """Raise learned pacing conservatively for one request kind."""
        if request_kind not in {REQUEST_KIND_PIE_LIST, REQUEST_KIND_PIE_DETAIL}:
            return
        if seconds is None:
            return
        minimum_seconds = (
            ENDPOINT_GROUP_MIN_REFRESH_SECONDS[ENDPOINT_GROUP_PIES]
            if request_kind == REQUEST_KIND_PIE_LIST
            else PIE_DETAIL_PACING_SECONDS
        )
        learned = max(
            self.request_pacing_seconds(request_kind),
            int(seconds),
            minimum_seconds,
        )
        current = self.request_pacing_seconds(request_kind)
        if learned == current:
            return
        self._learned_request_pacing_seconds[request_kind] = learned
        _LOGGER.warning(
            "Trading 212 %s pacing increased to %s seconds from %s",
            request_kind.replace("_", " "),
            learned,
            source,
        )

    def _pie_detail_request_ready(self) -> bool:
        """Return whether the learned pacing window allows another detail request."""
        return self._request_ready(REQUEST_KIND_PIE_DETAIL)

    def seconds_until_next_pie_detail_request(self) -> int:
        """Return seconds until the next learned pacing window opens."""
        return self.seconds_until_next_request(REQUEST_KIND_PIE_DETAIL)

    def seconds_until_next_request(self, request_kind: str) -> int:
        """Return seconds until the next request-kind window opens."""
        now = datetime.now(UTC)
        remaining_windows: list[float] = []

        last_request_at = self._last_request_at.get(request_kind)
        if last_request_at is not None:
            remaining_windows.append(
                (
                    last_request_at
                    + timedelta(seconds=self.request_pacing_seconds(request_kind))
                    - now
                ).total_seconds()
            )

        next_allowed_at = self._next_allowed_request_at.get(request_kind)
        if next_allowed_at is not None:
            remaining_windows.append((next_allowed_at - now).total_seconds())

        if not remaining_windows:
            return 0
        return max(int(math.ceil(max(remaining_windows))), 0)

    def _request_ready(self, request_kind: str) -> bool:
        """Return whether a request kind is outside both pacing and lockout windows."""
        return self.seconds_until_next_request(request_kind) <= 0

    def _raise_if_request_locked(
        self,
        request_kind: str,
        path: str,
        *,
        partial_data: Any,
    ) -> None:
        """Raise a local cooldown error when prior headers already told us to wait."""
        retry_after_seconds = self.seconds_until_next_request(request_kind)
        if retry_after_seconds <= 0:
            return
        retry_at = datetime.now(UTC) + timedelta(seconds=retry_after_seconds)
        raise Trading212RateLimitError(
            "Trading 212 API rate limit cooling down",
            path=path,
            retry_after_seconds=retry_after_seconds,
            retry_at=retry_at,
            endpoint_group=_endpoint_group_for_request_kind(request_kind),
            request_kind=request_kind,
            cooldown_source="cached_headers",
            partial_data=partial_data,
        )

    def _refresh_pending_pie_detail_ids(self, pies: list[dict[str, Any]]) -> None:
        """Refresh the pending pie detail queue from the latest list response."""
        latest_ids = []
        for pie in pies:
            pie_id = _pie_id(pie)
            if pie_id is None:
                continue
            latest_ids.append(pie_id)

        latest_id_set = set(latest_ids)
        self._pie_detail_cache = {
            pie_id: detail
            for pie_id, detail in self._pie_detail_cache.items()
            if pie_id in latest_id_set
        }

        pending = [
            pie_id
            for pie_id in self._pending_pie_detail_ids
            if pie_id in latest_id_set and pie_id not in self._pie_detail_cache
        ]
        for pie_id in latest_ids:
            if pie_id in self._pie_detail_cache or pie_id in pending:
                continue
            pending.append(pie_id)
        self._pending_pie_detail_ids = pending

    def _next_pending_pie_detail_id(self) -> str | None:
        """Return the next pie detail still needing hydration."""
        for pie_id in self._pending_pie_detail_ids:
            if pie_id not in self._pie_detail_cache:
                return pie_id
        return None

    def _remove_pending_pie_detail_id(self, pie_id: str) -> None:
        """Remove a hydrated pie ID from the pending queue."""
        self._pending_pie_detail_ids = [
            pending_id for pending_id in self._pending_pie_detail_ids if pending_id != pie_id
        ]

    def _build_pies_payload(
        self,
        pies: list[dict[str, Any]] | None = None,
        *,
        attempted_this_refresh: int = 0,
        skipped_due_to_pacing: int = 0,
        skipped_missing_id: int = 0,
        rate_limited: bool = False,
    ) -> dict[str, Any]:
        """Return the best available pies payload from list and cached detail data."""
        if pies is None:
            pies = self._latest_pies
        merged_pies: list[dict[str, Any]] = []
        for pie in pies:
            pie_id = _pie_id(pie)
            if pie_id is None:
                merged_pies.append(dict(pie, detail_status="missing_id"))
                continue
            detail = self._pie_detail_cache.get(pie_id)
            if detail is None:
                merged_pies.append(dict(pie, detail_status="pending"))
                continue
            merged_pies.append(_merge_pie_list_and_detail(pie, detail))

        return {
            "pies": merged_pies,
            "list_count": len(pies),
            "list_loaded": self._pie_list_loaded,
            "detail_count": len(self._pie_detail_cache),
            "detail_pending_count": len(self._pending_pie_detail_ids),
            "detail_attempted_this_refresh": attempted_this_refresh,
            "detail_skipped_count": skipped_due_to_pacing + skipped_missing_id,
            "detail_skipped_due_to_pacing": skipped_due_to_pacing,
            "detail_rate_limited": rate_limited,
            "complete": len(self._pending_pie_detail_ids) == 0,
        }

    async def _get_json(self, path: str) -> Any:
        """GET JSON from a known read-only Trading 212 endpoint."""
        url = f"{self._base_url}{path}"
        request_kind = _request_kind_for_path(path)

        try:
            async with self._session.get(
                url,
                auth=self._auth,
                headers={"Accept": "application/json"},
                timeout=REQUEST_TIMEOUT_SECONDS,
            ) as response:
                await self._raise_for_status(response, path)
                data = await response.json(content_type=None)
                self._record_request_success(request_kind, response)
                return data
        except Trading212Error:
            raise
        except (ClientError, TimeoutError, asyncio.TimeoutError) as err:
            raise Trading212ConnectionError("Unable to connect to Trading 212 API") from err

    async def _raise_for_status(self, response: ClientResponse, path: str) -> None:
        """Convert HTTP errors into integration errors."""
        if response.status < 400:
            return

        if response.status in (401, 403):
            raise Trading212AuthError("Trading 212 API credentials were rejected")

        if response.status == 429:
            body = await response.text()
            request_kind = _request_kind_for_path(path)
            endpoint_group = _endpoint_group_for_request_kind(request_kind)
            retry_after_seconds, retry_at, cooldown_source = _parse_rate_limit_retry(
                response,
                body,
                minimum_seconds=self._minimum_rate_limit_cooldown_seconds(request_kind),
                fallback_seconds=self._fallback_rate_limit_cooldown_seconds(request_kind),
            )
            self._record_rate_limit_response(
                request_kind,
                response,
                retry_after_seconds=retry_after_seconds,
                retry_at=retry_at,
            )
            raise Trading212RateLimitError(
                "Trading 212 API rate limit reached",
                path=path,
                retry_after_seconds=retry_after_seconds,
                retry_at=retry_at,
                endpoint_group=endpoint_group,
                request_kind=request_kind,
                cooldown_source=cooldown_source,
            )

        body = await response.text()
        safe_body = body[:250] if body else ""
        _LOGGER.debug(
            "Trading 212 API returned HTTP %s: %s",
            response.status,
            safe_body,
        )
        raise Trading212Error(f"Trading 212 API returned HTTP {response.status}")

    def _record_request_success(
        self,
        request_kind: str,
        response: ClientResponse,
    ) -> None:
        """Record a successful response for steady pacing and temporary lockout."""
        now = datetime.now(UTC)
        self._last_request_at[request_kind] = now
        self._last_rate_limit_headers[request_kind] = _rate_limit_header_snapshot(
            response,
            now=now,
        )
        steady_pacing_seconds = _header_pacing_seconds(response)
        if steady_pacing_seconds is not None:
            self._learn_request_pacing_seconds(
                request_kind,
                steady_pacing_seconds,
                source="response rate-limit headers",
            )
        remaining = _header_integer(
            response,
            "X-RateLimit-Remaining",
            "RateLimit-Remaining",
        )
        retry_after_seconds = _header_retry_window_seconds(response, now=now)
        if remaining is not None and remaining > 0 and retry_after_seconds is None:
            return
        if retry_after_seconds is not None:
            self._set_next_allowed_request_at(
                request_kind,
                now + timedelta(seconds=retry_after_seconds),
            )

    def _record_rate_limit_response(
        self,
        request_kind: str,
        response: ClientResponse,
        *,
        retry_after_seconds: int,
        retry_at: datetime,
    ) -> None:
        """Record a 429 response without clearing existing cached data."""
        now = datetime.now(UTC)
        self._last_request_at[request_kind] = now
        self._last_rate_limit_headers[request_kind] = _rate_limit_header_snapshot(
            response,
            now=now,
        )
        steady_pacing_seconds = _header_pacing_seconds(response)
        if steady_pacing_seconds is not None:
            self._learn_request_pacing_seconds(
                request_kind,
                steady_pacing_seconds,
                source="429 rate-limit headers",
            )
        self._set_next_allowed_request_at(request_kind, retry_at)

    def _set_next_allowed_request_at(
        self,
        request_kind: str,
        retry_at: datetime,
    ) -> None:
        """Store the farthest known lockout time for one request kind."""
        existing = self._next_allowed_request_at.get(request_kind)
        if existing is None or retry_at > existing:
            self._next_allowed_request_at[request_kind] = retry_at


def _parse_rate_limit_retry(
    response: ClientResponse,
    body: str,
    *,
    minimum_seconds: int,
    fallback_seconds: int,
) -> tuple[int, datetime, str]:
    """Parse cooldown timing from headers or a safe subset of the body."""
    now = datetime.now(UTC)
    retry_at: datetime | None = None
    retry_after_seconds = _parse_retry_after_header(
        response.headers.get("Retry-After"),
        now=now,
    )
    if retry_after_seconds is None:
        retry_after_seconds = _first_header_seconds(response, now=now)

    body_data = _safe_json_body(body)
    if retry_after_seconds is None and body_data is not None:
        retry_after_seconds = _find_seconds(body_data)
    if body_data is not None:
        retry_at = _find_retry_at(body_data)

    if retry_after_seconds is None:
        retry_after_seconds = _parse_seconds_from_text(body)

    retry_after_seconds, retry_at, used_fallback = normalise_rate_limit_retry(
        retry_after_seconds=retry_after_seconds,
        retry_at=retry_at,
        now=now,
        fallback_seconds=fallback_seconds,
        minimum_seconds=minimum_seconds,
        safety_buffer_seconds=RATE_LIMIT_SAFETY_BUFFER_SECONDS,
        maximum_seconds=MAX_RATE_LIMIT_COOLDOWN_SECONDS,
    )

    return (
        retry_after_seconds,
        retry_at,
        "fallback" if used_fallback else "parsed",
    )


def _parse_retry_after_header(
    value: str | None,
    *,
    now: datetime | None = None,
) -> int | None:
    """Parse a Retry-After header as seconds or HTTP date."""
    if value is None or not value.strip():
        return None
    stripped = value.strip()
    try:
        number = float(stripped)
        if not math.isfinite(number):
            return None
        return int(number)
    except ValueError:
        pass

    try:
        retry_at = parsedate_to_datetime(stripped)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    if now is None:
        now = datetime.now(UTC)
    seconds = int((retry_at.astimezone(UTC) - now).total_seconds())
    return seconds


def _first_header_seconds(response_headers, *, now: datetime | None = None) -> int | None:
    """Parse common rate-limit reset headers defensively."""
    for key in (
        "X-RateLimit-Reset-After",
        "RateLimit-Reset-After",
        "X-RateLimit-Retry-After",
        "X-RateLimit-Cooldown",
        "RateLimit-Reset",
        "X-RateLimit-Reset",
    ):
        value = response_headers.get(key)
        if value is None:
            continue
        parsed = _parse_seconds_or_epoch(value, now=now)
        if parsed is not None:
            return parsed
    return None


def _header_integer(response: ClientResponse, *keys: str) -> int | None:
    """Return the first integer header value from the provided keys."""
    for key in keys:
        value = response.headers.get(key)
        if value is None:
            continue
        try:
            return int(float(value.strip()))
        except (AttributeError, TypeError, ValueError):
            continue
    return None


def _header_retry_window_seconds(
    response: ClientResponse,
    *,
    now: datetime | None = None,
) -> int | None:
    """Return a temporary lockout window from response headers."""
    retry_after_seconds = _parse_retry_after_header(
        response.headers.get("Retry-After"),
        now=now,
    )
    header_seconds = _first_header_seconds(response.headers, now=now)
    candidates = [value for value in (retry_after_seconds, header_seconds) if value is not None]
    if not candidates:
        return None
    return max(candidates) + RATE_LIMIT_SAFETY_BUFFER_SECONDS


def _header_pacing_seconds(response: ClientResponse) -> int | None:
    """Return steady pacing derived from limit/period headers."""
    limit = _header_integer(response, "X-RateLimit-Limit", "RateLimit-Limit")
    period = _header_integer(response, "X-RateLimit-Period", "RateLimit-Period")
    if limit is None or period is None or limit <= 0 or period <= 0:
        return None
    return int(math.ceil(period / limit)) + RATE_LIMIT_SAFETY_BUFFER_SECONDS


def _rate_limit_header_snapshot(
    response: ClientResponse,
    *,
    now: datetime | None = None,
) -> dict[str, int | str | None]:
    """Return a bounded snapshot of response rate-limit headers."""
    return {
        "retry_after_seconds": _parse_retry_after_header(
            response.headers.get("Retry-After"),
            now=now,
        ),
        "limit": _header_integer(response, "X-RateLimit-Limit", "RateLimit-Limit"),
        "period_seconds": _header_integer(
            response,
            "X-RateLimit-Period",
            "RateLimit-Period",
        ),
        "remaining": _header_integer(
            response,
            "X-RateLimit-Remaining",
            "RateLimit-Remaining",
        ),
        "reset_seconds": _first_header_seconds(response.headers, now=now),
        "used": _header_integer(response, "X-RateLimit-Used", "RateLimit-Used"),
    }


def _parse_seconds_or_epoch(value: str, *, now: datetime | None = None) -> int | None:
    """Parse seconds, milliseconds, or epoch timestamp values."""
    try:
        number = float(value.strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if now is None:
        now = datetime.now(UTC)
    if number > 10_000_000_000:
        return int((datetime.fromtimestamp(number / 1000, UTC) - now).total_seconds())
    if number > 1_000_000_000:
        return int((datetime.fromtimestamp(number, UTC) - now).total_seconds())
    return int(number)


def _safe_json_body(body: str) -> Any:
    """Return parsed JSON body only when it is small and valid."""
    if not body or len(body) > 4096:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def _find_seconds(data: Any) -> int | None:
    """Find cooldown seconds in common response fields."""
    if isinstance(data, dict):
        for key, value in data.items():
            key_lower = str(key).lower()
            if key_lower in {
                "cooldown",
                "cooldownseconds",
                "retryafter",
                "retryafterseconds",
                "timetoreset",
                "resetafter",
            }:
                parsed = _number_to_seconds(value)
                if parsed is not None:
                    return parsed
            if key_lower in {"cooldownms", "retryafterms"}:
                parsed = _number_to_seconds(value, milliseconds=True)
                if parsed is not None:
                    return parsed
            nested = _find_seconds(value)
            if nested is not None:
                return nested
    if isinstance(data, list):
        for item in data:
            nested = _find_seconds(item)
            if nested is not None:
                return nested
    return None


def _find_retry_at(data: Any) -> datetime | None:
    """Find an absolute retry/reset timestamp in common response fields."""
    if isinstance(data, dict):
        for key, value in data.items():
            key_lower = str(key).lower()
            if key_lower in {"reset", "resetat", "retryat", "retryafterdate"}:
                parsed = _parse_datetime_value(value)
                if parsed is not None:
                    return parsed
            nested = _find_retry_at(value)
            if nested is not None:
                return nested
    if isinstance(data, list):
        for item in data:
            nested = _find_retry_at(item)
            if nested is not None:
                return nested
    return None


def _number_to_seconds(value: Any, *, milliseconds: bool = False) -> int | None:
    """Convert numeric cooldown values to seconds."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if milliseconds:
        number = number / 1000
    return int(number)


def _parse_datetime_value(value: Any) -> datetime | None:
    """Parse ISO, epoch seconds, or epoch milliseconds into UTC datetime."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp = timestamp / 1000
        return datetime.fromtimestamp(timestamp, UTC)
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError, OverflowError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_seconds_from_text(body: str) -> int | None:
    """Parse a simple cooldown duration from a small text body."""
    if not body or len(body) > 512:
        return None
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(ms|milliseconds|seconds|second|secs|sec|s)\b",
        body,
        re.IGNORECASE,
    )
    if match is None:
        return None
    value = float(match.group(1))
    unit = match.group(2).lower()
    if not math.isfinite(value):
        return None
    if unit in {"ms", "milliseconds"}:
        value = value / 1000
    return int(value)


def normalise_rate_limit_retry(
    *,
    retry_after_seconds: int | float | None,
    retry_at: datetime | None,
    now: datetime | None,
    fallback_seconds: int,
    minimum_seconds: int,
    safety_buffer_seconds: int,
    maximum_seconds: int,
) -> tuple[int, datetime, bool]:
    """Return a safe applied cooldown window for a 429 response."""
    if now is None:
        now = datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    now = now.astimezone(UTC)

    candidates: list[int] = []
    candidate_seconds = _normalise_retry_seconds_value(
        retry_after_seconds,
        minimum_seconds=minimum_seconds,
    )
    if candidate_seconds is not None:
        candidates.append(candidate_seconds)

    if retry_at is not None:
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        retry_at = retry_at.astimezone(UTC)
        retry_at_seconds = _normalise_retry_seconds_value(
            (retry_at - now).total_seconds(),
            minimum_seconds=minimum_seconds,
        )
        if retry_at_seconds is not None:
            candidates.append(retry_at_seconds)

    used_fallback = not candidates
    if candidates:
        candidate_seconds = max(candidates)
    else:
        candidate_seconds = max(fallback_seconds, minimum_seconds)

    candidate_seconds = min(
        candidate_seconds + max(safety_buffer_seconds, 0),
        maximum_seconds,
    )
    candidate_seconds = max(candidate_seconds, minimum_seconds)

    applied_retry_at = now + timedelta(seconds=candidate_seconds)
    return candidate_seconds, applied_retry_at, used_fallback


def _normalise_retry_seconds_value(
    value: int | float | None,
    *,
    minimum_seconds: int,
) -> int | None:
    """Return a positive integer cooldown or None when invalid."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return max(int(math.ceil(number)), minimum_seconds)


def fallback_rate_limit_cooldown_seconds_for_group(group: str) -> int:
    """Return the conservative fallback cooldown for one endpoint group."""
    fallback_seconds = DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS
    group_minimum = ENDPOINT_GROUP_MIN_REFRESH_SECONDS.get(group, MIN_RATE_LIMIT_COOLDOWN_SECONDS)
    return max(fallback_seconds, group_minimum, MIN_RATE_LIMIT_COOLDOWN_SECONDS)


def _request_kind_for_path(path: str) -> str:
    """Return the request kind for a known read-only endpoint path."""
    if path == "/equity/account/summary":
        return REQUEST_KIND_ACCOUNT_SUMMARY
    if path == "/equity/positions":
        return REQUEST_KIND_POSITIONS
    if path == "/equity/pies":
        return REQUEST_KIND_PIE_LIST
    if path.startswith("/equity/pies/"):
        return REQUEST_KIND_PIE_DETAIL
    return path


def _endpoint_group_for_request_kind(request_kind: str) -> str:
    """Return the endpoint group for a request kind."""
    if request_kind in {REQUEST_KIND_PIE_LIST, REQUEST_KIND_PIE_DETAIL}:
        return ENDPOINT_GROUP_PIES
    if request_kind == REQUEST_KIND_ACCOUNT_SUMMARY:
        return ENDPOINT_GROUP_ACCOUNT_SUMMARY
    if request_kind == REQUEST_KIND_POSITIONS:
        return ENDPOINT_GROUP_POSITIONS
    return request_kind


def _minimum_rate_limit_cooldown_seconds(request_kind: str) -> int:
    """Return the minimum cooldown to apply after a 429."""
    if request_kind == REQUEST_KIND_PIE_DETAIL:
        return PIE_DETAIL_PACING_SECONDS
    endpoint_group = _endpoint_group_for_request_kind(request_kind)
    return max(
        ENDPOINT_GROUP_MIN_REFRESH_SECONDS.get(
            endpoint_group,
            MIN_RATE_LIMIT_COOLDOWN_SECONDS,
        ),
        MIN_RATE_LIMIT_COOLDOWN_SECONDS,
    )


def _fallback_rate_limit_cooldown_seconds_for_request_kind(request_kind: str) -> int:
    """Return the conservative fallback cooldown for a request kind."""
    endpoint_group = _endpoint_group_for_request_kind(request_kind)
    fallback_seconds = fallback_rate_limit_cooldown_seconds_for_group(endpoint_group)
    if request_kind == REQUEST_KIND_PIE_DETAIL:
        return max(fallback_seconds, PIE_DETAIL_PACING_SECONDS)
    return fallback_seconds


def _pie_id(pie: dict[str, Any]) -> str | None:
    """Return a stable pie identifier when exposed by the API."""
    for key in ("id", "pieId", "instrumentId"):
        value = pie.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int):
            return str(value)
    settings = pie.get("settings")
    if isinstance(settings, dict):
        for key in ("id", "pieId"):
            value = settings.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, int):
                return str(value)
    return None


def _format_pie_detail_path_id(pie_id: str | int) -> str:
    """Return the API path identifier for one pie detail request."""
    if isinstance(pie_id, int):
        return f"0x{pie_id:x}"
    pie_id_text = str(pie_id).strip()
    if not pie_id_text:
        return pie_id_text
    if pie_id_text.lower().startswith("0x"):
        return f"0x{pie_id_text[2:].lower()}"
    if pie_id_text.isdigit():
        return f"0x{int(pie_id_text):x}"
    return pie_id_text


def _merge_pie_list_and_detail(
    list_item: dict[str, Any],
    detail: dict[str, Any],
) -> dict[str, Any]:
    """Merge list and detail payloads for internal summary building."""
    merged = dict(list_item)
    for key, value in detail.items():
        if key in {"instruments", "slices", "holdings"} and isinstance(value, list):
            merged[f"{key}Count"] = len(value)
            merged[key] = value
            continue
        merged[key] = value
    if "id" not in merged:
        pie_id = _pie_id(detail)
        if pie_id is not None:
            merged["id"] = pie_id
    merged["detail_status"] = "fetched"
    return merged
