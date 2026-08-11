import asyncio
import unittest
from concurrent.futures import ThreadPoolExecutor

from app.services.exchange_rate import ExchangeRateService


class FakeExchangeRateService(ExchangeRateService):
    def __init__(self):
        super().__init__()
        self.calls = []

    async def _fetch(self, base: str, api_key: str):
        self.calls.append((base, api_key))
        marker = 7.1 if api_key == "key-a" else 7.9
        return {"CNY": marker}, "api"


class SlowExchangeRateService(ExchangeRateService):
    async def _fetch(self, base: str, api_key: str):
        await asyncio.sleep(0.02)
        return {"CNY": 7.1}, "api"


class ExchangeRateCacheTests(unittest.TestCase):
    def test_cache_is_isolated_by_api_key(self):
        service = FakeExchangeRateService()
        first = asyncio.run(service.rates("USD", "key-a"))
        second = asyncio.run(service.rates("USD", "key-b"))
        cached = asyncio.run(service.rates("USD", "key-a"))
        self.assertEqual(first["CNY"], 7.1)
        self.assertEqual(second["CNY"], 7.9)
        self.assertEqual(cached["CNY"], 7.1)
        self.assertEqual(service.calls, [("USD", "key-a"), ("USD", "key-b")])

    def test_key_specific_invalidation_preserves_other_cache(self):
        service = FakeExchangeRateService()
        asyncio.run(service.rates("USD", "key-a"))
        asyncio.run(service.rates("USD", "key-b"))
        service.invalidate("key-a")
        asyncio.run(service.rates("USD", "key-a"))
        asyncio.run(service.rates("USD", "key-b"))
        self.assertEqual(service.calls.count(("USD", "key-a")), 2)
        self.assertEqual(service.calls.count(("USD", "key-b")), 1)

    def test_cache_can_be_used_from_multiple_event_loops(self):
        service = SlowExchangeRateService()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(asyncio.run, service.rates("USD", "shared-key")) for _ in range(2)]
            results = [future.result(timeout=2) for future in futures]
        self.assertEqual([result["CNY"] for result in results], [7.1, 7.1])


if __name__ == "__main__":
    unittest.main()
