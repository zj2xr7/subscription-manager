import unittest
from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import (
    BankCardBalance,
    BankCardCharge,
    BankCardChargeAllocation,
    BankCardDeposit,
    Subscription,
)
from app.services.bank_funds import DepositAlreadyUsedError, allocate_fifo, delete_deposit_cascade


class BankFundsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add_all([
            BankCardDeposit(usdt_amount=10.01, c2c_rate=6.5, cny_cost=65.07, chain_fee=.01, actual_received=10, remaining_usdt=10),
            BankCardDeposit(usdt_amount=10.01, c2c_rate=7, cny_cost=70.07, chain_fee=.01, actual_received=10, remaining_usdt=10),
            BankCardBalance(id=1, balance=20),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_fifo_preview_crosses_lots_without_mutating(self):
        allocations, shortfall = allocate_fifo(self.db, 11)
        self.assertEqual([item.usdt_amount for item in allocations], [10, 1])
        self.assertEqual(shortfall, 0)
        self.assertEqual(round(sum(item.usdt_amount * item.deposit.c2c_rate for item in allocations), 2), 72)
        self.assertEqual(self.db.get(BankCardDeposit, 1).remaining_usdt, 10)

    def test_fifo_consume_and_partial_coverage(self):
        allocations, shortfall = allocate_fifo(self.db, 25, consume=True)
        self.assertEqual(len(allocations), 2)
        self.assertEqual(shortfall, 5)
        self.assertEqual(self.db.get(BankCardDeposit, 1).remaining_usdt, 0)
        self.assertEqual(self.db.get(BankCardDeposit, 2).remaining_usdt, 0)

    def test_delete_unused_deposit_recomputes_balance(self):
        result = delete_deposit_cascade(self.db, 1)
        self.db.commit()
        self.assertEqual(result["deleted_charge_count"], 0)
        self.assertIsNone(self.db.get(BankCardDeposit, 1))
        self.assertEqual(self.db.get(BankCardBalance, 1).balance, 10)

    def test_delete_used_deposit_is_rejected_without_changing_history(self):
        subscription = Subscription(
            name="Service",
            price=10,
            currency="USD",
            billing_cycle="monthly",
            next_billing_date=date(2026, 3, 1),
            payment_method="bank_card",
        )
        self.db.add(subscription)
        self.db.flush()
        first = BankCardCharge(
            kind="subscription", subscription_id=subscription.id, subscription_name=subscription.name,
            original_price=10, original_currency="USD", converted_usd=10, charged_usdt=8,
            actual_cny_cost=52.5, balance_before=20, balance_after=12,
            billing_date=date(2026, 1, 1), next_billing_date=date(2026, 2, 1),
            created_at=datetime(2026, 1, 1),
        )
        second = BankCardCharge(
            kind="subscription", subscription_id=subscription.id, subscription_name=subscription.name,
            original_price=10, original_currency="USD", converted_usd=10, charged_usdt=4,
            actual_cny_cost=28, balance_before=12, balance_after=8,
            billing_date=date(2026, 2, 1), next_billing_date=date(2026, 3, 1),
            created_at=datetime(2026, 2, 1),
        )
        self.db.add_all([first, second])
        self.db.flush()
        self.db.add_all([
            BankCardChargeAllocation(charge_id=first.id, deposit_id=1, usdt_amount=7, c2c_rate=6.5, cny_cost=45.5),
            BankCardChargeAllocation(charge_id=first.id, deposit_id=2, usdt_amount=1, c2c_rate=7, cny_cost=7),
            BankCardChargeAllocation(charge_id=second.id, deposit_id=2, usdt_amount=4, c2c_rate=7, cny_cost=28),
        ])
        self.db.get(BankCardDeposit, 1).remaining_usdt = 3
        self.db.get(BankCardDeposit, 2).remaining_usdt = 5
        self.db.get(BankCardBalance, 1).balance = 8
        self.db.commit()

        with self.assertRaises(DepositAlreadyUsedError):
            delete_deposit_cascade(self.db, 1)
        self.db.rollback()
        self.assertIsNotNone(self.db.get(BankCardDeposit, 1))
        self.assertEqual(self.db.get(BankCardDeposit, 2).remaining_usdt, 5)
        self.assertEqual(self.db.get(BankCardBalance, 1).balance, 8)
        self.assertEqual(self.db.get(Subscription, subscription.id).next_billing_date, date(2026, 3, 1))
        self.assertEqual(self.db.query(BankCardCharge).count(), 2)
        self.assertEqual(self.db.query(BankCardChargeAllocation).count(), 3)

    def test_partially_used_deposit_without_allocation_is_protected(self):
        self.db.get(BankCardDeposit, 1).remaining_usdt = 9
        self.db.commit()
        with self.assertRaises(DepositAlreadyUsedError):
            delete_deposit_cascade(self.db, 1)
        self.db.rollback()
        self.assertIsNotNone(self.db.get(BankCardDeposit, 1))

    def test_historical_adjustment_allocation_protects_deposit(self):
        charge = BankCardCharge(
            kind="historical_adjustment", subscription_name="Historical balance adjustment",
            charged_usdt=1, actual_cny_cost=6.5, balance_before=20, balance_after=19,
        )
        self.db.add(charge)
        self.db.flush()
        self.db.add(BankCardChargeAllocation(
            charge_id=charge.id, deposit_id=1, usdt_amount=1, c2c_rate=6.5, cny_cost=6.5,
        ))
        self.db.commit()
        with self.assertRaises(DepositAlreadyUsedError):
            delete_deposit_cascade(self.db, 1)


if __name__ == "__main__":
    unittest.main()
