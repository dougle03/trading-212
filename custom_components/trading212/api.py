"""Read-only Trading 212 API client."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiohttp import BasicAuth, ClientError, ClientResponse, ClientSession

from .const import ENVIRONMENT_URLS

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 30


class Trading212Error(Exception):
    """Base Trading 212 API error."""


class Trading212AuthError(Trading212Error):
    """Trading 212 authentication or authorisation error."""


class Trading212RateLimitError(Trading212Error):
    """Trading 212 rate limit error."""


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

    async def _get_json(self, path: str) -> Any:
        """GET JSON from a known read-only Trading 212 endpoint."""
        url = f"{self._base_url}{path}"

        try:
            async with self._session.get(
                url,
                auth=self._auth,
                headers={"Accept": "application/json"},
                timeout=REQUEST_TIMEOUT_SECONDS,
            ) as response:
                await self._raise_for_status(response)
                return await response.json(content_type=None)
        except Trading212Error:
            raise
        except (ClientError, TimeoutError, asyncio.TimeoutError) as err:
            raise Trading212ConnectionError("Unable to connect to Trading 212 API") from err

    async def _raise_for_status(self, response: ClientResponse) -> None:
        """Convert HTTP errors into integration errors."""
        if response.status < 400:
            return

        if response.status in (401, 403):
            raise Trading212AuthError("Trading 212 API credentials were rejected")

        if response.status == 429:
            raise Trading212RateLimitError("Trading 212 API rate limit reached")

        body = await response.text()
        safe_body = body[:250] if body else ""
        _LOGGER.debug(
            "Trading 212 API returned HTTP %s: %s",
            response.status,
            safe_body,
        )
        raise Trading212Error(f"Trading 212 API returned HTTP {response.status}")
