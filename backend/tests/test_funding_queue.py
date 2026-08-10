import asyncio
import unittest
from datetime import date
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import BankCardBalance, BankCardDeposit, Subscription
from app.routers.bank_card import top_up_quote
from app.routers.subscriptions import charge_subscription
from app.schemas import TopUpQuoteRequest
from app.services.funding_queue import build_bank_funding_queue, simulate_funding_queue


class FundingQueueTests(unittest.TestCase):
    def test_seven_usdt_is_shared_as_two_then_five(self):
        lot = SimpleNamespace(id=1, remaining_usdt=7, c2c_rate=7.0)
        result = simulate_funding_queue([lot], [(1, 2), (2, 10)])
        self.assertEqual(result[1].covered_usdt, 2)
        self.assertEqual(result[1].shortfall_usdt, 0)
        self.assertEqual(result[2].reserved_before_usdt, 2)
        self.assertEqual(result[2].available_for_charge_usdt, 5)
        self.assertEqual(result[2].covered_usdt, 5)
        self.assertEqual(result[2].shortfall_usdt, 5)

    def test_uncovered_earlier_bill_leaves_later_bill_empty(self):
        lot = SimpleNamespace(id=1, remaining_usdt=7, c2c_rate=7.0)
        result = simulate_funding_queue([lot], [(1, 10), (2, 2)])
        self.assertEqual(result[1].covered_usdt, 7)
        self.assertEqual(result[1].shortfall_usdt, 3)
        self.assertEqual(result[2].covered_usdt, 0)
        self.assertEqual(result[2].shortfall_usdt, 2)

    def test_queue_fifo_crosses_lots(self):
        lots = [
            SimpleNamespace(id=1, remaining_usdt=3, c2c_rate=6.5),
            SimpleNamespace(id=2, remaining_usdt=6, c2c_rate=7.0),
        ]
        result = simulate_funding_queue(lots, [(1, 2), (2, 5)])
        self.assertEqual([(a.deposit.id, a.usdt_amount) for a in result[2].allocations], [(1, 1), (2, 4)])


class FundingQueueIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add_all([
            BankCardDeposit(
                usdt_amount=7.01, c2c_rate=7, cny_cost=49.07, chain_fee=.01,
                actual_received=7, remaining_usdt=7,
            ),
            BankCardBalance(id=1, balance=7),
        ])
        self.webshare = Subscription(
            name="WebShare", price=2, currency="USD", billing_cycle="monthly",
            next_billing_date=date(2026, 8, 12), payment_method="bank_card",
        )
        self.chatgpt = Subscription(
            name="ChatGPT", price=6, currency="USD", billing_cycle="monthly",
            next_billing_date=date(2026, 8, 18), payment_method="bank_card",
        )
        self.db.add_all([self.webshare, self.chatgpt])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_later_charge_cannot_use_balance_reserved_for_earlier_bill(self):
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(charge_subscription(self.chatgpt.id, self.db))
        self.assertEqual(raised.exception.status_code, 409)
        self.assertAlmostEqual(self.db.get(BankCardBalance, 1).balance, 7)

    def test_top_up_quote_includes_earlier_unselected_reservation(self):
        quote = asyncio.run(top_up_quote(
            TopUpQuoteRequest(subscription_ids=[self.chatgpt.id], c2c_rate=7), self.db
        ))
        self.assertEqual(quote.reserved_usdt, 2.06)
        self.assertEqual(quote.covered_usdt, 4.94)
        self.assertEqual(quote.shortfall_usdt, 1.24)

    def test_paid_subscription_reenters_queue_at_its_new_date(self):
        self.db.get(BankCardDeposit, 1).remaining_usdt = 20
        self.db.get(BankCardDeposit, 1).actual_received = 20
        self.db.get(BankCardBalance, 1).balance = 20
        self.db.commit()
        asyncio.run(charge_subscription(self.webshare.id, self.db))
        ordered, funding = asyncio.run(build_bank_funding_queue(self.db))
        self.assertEqual([item.id for item in ordered], [self.chatgpt.id, self.webshare.id])
        self.assertEqual(funding[self.chatgpt.id]["queue_position"], 1)
        self.assertEqual(funding[self.webshare.id]["queue_position"], 2)
        self.assertEqual(self.db.get(Subscription, self.webshare.id).next_billing_date, date(2026, 9, 12))

    def test_same_billing_date_uses_subscription_id_order(self):
        self.chatgpt.next_billing_date = self.webshare.next_billing_date
        self.db.commit()
        ordered, funding = asyncio.run(build_bank_funding_queue(self.db))
        self.assertEqual([item.id for item in ordered], sorted([self.webshare.id, self.chatgpt.id]))
        self.assertEqual(funding[min(self.webshare.id, self.chatgpt.id)]["queue_position"], 1)


if __name__ == "__main__":
    unittest.main()
