import threading
import time
from typing import Protocol

import httpx

VIES_CHECK_VAT_URL = "https://ec.europa.eu/taxation_customs/vies/rest-api/ms/{country_code}/vat/{vat_number}"


class ViesClient(Protocol):
    def is_valid(self, country_code: str, vat_number: str) -> bool | None:
        """True/False if VIES answered definitively, None if VIES could not be reached."""
        ...


class ViesHttpClient:
    """Cached, rate-limited, failure-tolerant VIES client. A VIES outage returns None."""

    def __init__(
        self,
        *,
        cache_ttl_seconds: float = 3600.0,
        min_interval_seconds: float = 1.0,
        request_timeout_seconds: float = 5.0,
    ) -> None:
        self._cache_ttl_seconds = cache_ttl_seconds
        self._min_interval_seconds = min_interval_seconds
        self._request_timeout_seconds = request_timeout_seconds
        self._cache: dict[tuple[str, str], tuple[float, bool]] = {}
        self._last_call_monotonic = 0.0
        self._lock = threading.Lock()

    def is_valid(self, country_code: str, vat_number: str) -> bool | None:
        key = (country_code, vat_number)
        now = time.monotonic()

        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                cached_at, result = cached
                if now - cached_at < self._cache_ttl_seconds:
                    return result

            wait = self._min_interval_seconds - (now - self._last_call_monotonic)
            if wait > 0:
                time.sleep(wait)
            self._last_call_monotonic = time.monotonic()

        try:
            response = httpx.get(
                VIES_CHECK_VAT_URL.format(country_code=country_code, vat_number=vat_number),
                timeout=self._request_timeout_seconds,
            )
            response.raise_for_status()
            result = bool(response.json().get("isValid"))
        except (httpx.HTTPError, ValueError):
            return None

        with self._lock:
            self._cache[key] = (time.monotonic(), result)
        return result
