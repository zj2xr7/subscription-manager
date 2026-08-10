import asyncio
import unittest
from datetime import date
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import AlipayCharge, BankCardBalance, Subscription
from app.routers.subscriptions import charge_subscription, delete_subscription, list_subscription_charges


class SubscriptionChargeHistoryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.subscription = Subscription(
            name="Local Service", price=20, currency="CNY", billing_cycle="monthly",
            next_billing_date=date(2026, 8, 15), payment_method="alipay",
        )
        self.db.add_all([self.subscription, BankCardBalance(id=1, balance=0)])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_alipay_charge_is_recorded_with_billing_snapshot(self):
        result = asyncio.run(charge_subscription(self.subscription.id, self.db))
        record = self.db.query(AlipayCharge).one()
        self.assertEqual(result.actual_cny_cost, 20)
        self.assertEqual(record.subscription_name, "Local Service")
        self.assertEqual(record.billing_date, date(2026, 8, 15))
        self.assertEqual(record.next_billing_date, date(2026, 9, 15))
        self.assertEqual(self.subscription.next_billing_date, date(2026, 9, 15))

    def test_unified_history_filters_alipay_and_keeps_snapshot_after_deletion(self):
        asyncio.run(charge_subscription(self.subscription.id, self.db))
        records = list_subscription_charges(type="alipay", db=self.db)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["payment_method"], "alipay")
        delete_subscription(self.subscription.id, self.db)
        record = self.db.query(AlipayCharge).one()
        self.assertIsNone(record.subscription_id)
        self.assertEqual(record.subscription_name, "Local Service")

    def test_commit_failure_rolls_back_charge_and_billing_date(self):
        original_date = self.subscription.next_billing_date
        with patch.object(self.db, "commit", side_effect=RuntimeError("write failed")):
            with self.assertRaises(RuntimeError):
                asyncio.run(charge_subscription(self.subscription.id, self.db))
        self.assertEqual(self.db.query(AlipayCharge).count(), 0)
        self.assertEqual(self.db.get(Subscription, self.subscription.id).next_billing_date, original_date)


if __name__ == "__main__":
    unittest.main()
