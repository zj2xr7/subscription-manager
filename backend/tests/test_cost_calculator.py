import asyncio
import unittest

from app.services.cost_calculator import calculate_cost


class CostCalculatorTests(unittest.TestCase):
    def test_alipay_cny_has_no_conversion(self):
        result = asyncio.run(calculate_cost(20, "CNY", "alipay", None))
        self.assertEqual(result["cny_cost"], 20)
        self.assertEqual(result["conversion_rate"], 1)

    def test_bank_card_gbp_chain(self):
        result = asyncio.run(calculate_cost(10, "GBP", "bank_card", 7.2))
        self.assertEqual(result["usdt_charge"], 13.081)
        self.assertEqual(result["required_usdt"], 13.081)
        self.assertIsNone(result["cny_cost"])


if __name__ == "__main__":
    unittest.main()
