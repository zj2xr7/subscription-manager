import asyncio
import time
from datetime import datetime, timezone

import httpx


FALLBACK_RATES = {
    "USD": {"USD": 1.0, "GBP": 1 / 1.27, "CAD": 1 / 0.74, "CNY": 7.2},
    "GBP": {"USD": 1.27, "GBP": 1.0, "CAD": 1.27 / 0.74, "CNY": 9.14},
    "CAD": {"USD": 0.74, "GBP": 0.74 / 1.27, "CAD": 1.0, "CNY": 5.32},
    "CNY": {"USD": 1 / 7.2, "GBP": 1 / 9.14, "CAD": 1 / 5.32, "CNY": 1.0},
}


class ExchangeRateService:
    def __init__(self):
        self._cache: dict[str, tuple[float, dict[str, float]]] = {}
        self._sources: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def rates(self, base: str, api_key: str = "") -> dict[str, float]:
        base = base.upper()
        cached = self._cache.get(base)
        if cached and time.time() - cached[0] < 3600:
            return cached[1]
        async with self._lock:
            cached = self._cache.get(base)
            if cached and time.time() - cached[0] < 3600:
                return cached[1]
            rates, source = await self._fetch(base, api_key)
            self._cache[base] = (time.time(), rates)
            self._sources[base] = source
            return rates

    async def _fetch(self, base: str, api_key: str) -> dict[str, float]:
        if not api_key:
            return FALLBACK_RATES[base].copy(), "reference"
        url = f"https://v6.exchangerate-api.com/v6/{api_key}/latest/{base}"
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
            values = data.get("conversion_rates", {})
            if data.get("result") != "success" or not values:
                raise ValueError("exchange-rate provider returned an invalid response")
            return {key: float(value) for key, value in values.items()}, "api"
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            return FALLBACK_RATES[base].copy(), "reference"

    def invalidate(self):
        self._cache.clear()
        self._sources.clear()

    async def cny_quotes(self, api_key: str = "", refresh: bool = False) -> dict:
        if refresh:
            self.invalidate()
        quotes = {}
        timestamps = []
        sources = []
        for currency in ("USD", "GBP", "CAD"):
            rates = await self.rates(currency, api_key)
            quotes[currency] = round(rates["CNY"], 4)
            timestamps.append(self._cache[currency][0])
            sources.append(self._sources.get(currency, "reference"))
        updated = datetime.fromtimestamp(max(timestamps), tz=timezone.utc).isoformat()
        return {
            "base": "CNY",
            "quotes": quotes,
            "source": "api" if all(source == "api" for source in sources) else "reference",
            "updated_at": updated,
            "cache_seconds": 3600,
        }


exchange_rate_service = ExchangeRateService()
