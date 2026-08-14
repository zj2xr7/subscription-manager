import unittest
from datetime import date, datetime
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db, init_db
from app.models import (
    AppSettings,
    BankCardBalance,
    BankCardCharge,
    BankCardChargeAllocation,
    BankCardDeposit,
    BankCardPurchase,
    BankCardTransfer,
    Subscription,
)
from app.services.bank_funds import (
    DepositAlreadyUsedError,
    TransferAlreadyUsedError,
    allocate_fifo,
    create_combined_transfer,
    create_pending_purchase,
    delete_deposit_cascade,
    delete_unused_transfer,
)
from app.routers.bank_card import router as bank_card_router


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


class HistoricalAdjustmentCleanupTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(self.engine)
        self.Factory = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        with self.Factory() as db:
            db.add_all([
                AppSettings(key="schema_version", value="4"),
                BankCardBalance(id=1, balance=10),
                BankCardDeposit(id=1, usdt_amount=10.01, c2c_rate=6.5, cny_cost=65.07, chain_fee=.01, actual_received=10, remaining_usdt=7),
                BankCardDeposit(id=2, usdt_amount=10.01, c2c_rate=7, cny_cost=70.07, chain_fee=.01, actual_received=10, remaining_usdt=3),
            ])
            subscription = Subscription(
                name="Service", price=5, currency="USD", billing_cycle="monthly",
                next_billing_date=date(2026, 3, 1), payment_method="bank_card",
            )
            db.add(subscription)
            db.flush()
            adjustment = BankCardCharge(
                kind="historical_adjustment", subscription_name="Historical adjustment",
                charged_usdt=1, actual_cny_cost=6.5, balance_before=20, balance_after=19,
            )
            first = BankCardCharge(
                kind="subscription", subscription_id=subscription.id, subscription_name="Service",
                charged_usdt=5, actual_cny_cost=34, balance_before=19, balance_after=14,
                billing_date=date(2026, 1, 1), next_billing_date=date(2026, 2, 1),
            )
            second = BankCardCharge(
                kind="subscription", subscription_id=subscription.id, subscription_name="Service",
                charged_usdt=4, actual_cny_cost=28, balance_before=14, balance_after=10,
                billing_date=date(2026, 2, 1), next_billing_date=date(2026, 3, 1),
            )
            db.add_all([adjustment, first, second])
            db.flush()
            db.add_all([
                BankCardChargeAllocation(charge_id=adjustment.id, deposit_id=1, usdt_amount=1, c2c_rate=6.5, cny_cost=6.5),
                BankCardChargeAllocation(charge_id=first.id, deposit_id=1, usdt_amount=2, c2c_rate=6.5, cny_cost=13),
                BankCardChargeAllocation(charge_id=first.id, deposit_id=2, usdt_amount=3, c2c_rate=7, cny_cost=21),
                BankCardChargeAllocation(charge_id=second.id, deposit_id=2, usdt_amount=4, c2c_rate=7, cny_cost=28),
            ])
            db.commit()

    def tearDown(self):
        self.engine.dispose()

    def test_v5_migration_removes_adjustment_batches_and_linked_charges_idempotently(self):
        with patch("app.database.engine", self.engine), patch("app.database.SessionLocal", self.Factory):
            init_db()
            init_db()
        with self.Factory() as db:
            self.assertEqual(db.get(AppSettings, "schema_version").value, "6")
            self.assertIsNone(db.get(BankCardDeposit, 1))
            self.assertEqual(db.get(BankCardDeposit, 2).remaining_usdt, 10)
            self.assertEqual(db.get(BankCardBalance, 1).balance, 10)
            self.assertEqual(db.query(BankCardCharge).count(), 0)
            self.assertEqual(db.query(BankCardChargeAllocation).count(), 0)
            subscription = db.query(Subscription).one()
            self.assertEqual(subscription.next_billing_date, date(2026, 1, 1))

    def test_transactions_exclude_adjustments_and_reject_adjustment_filter(self):
        app = FastAPI()
        app.include_router(bank_card_router)

        def override_db():
            with self.Factory() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        client = TestClient(app)
        response = client.get("/api/bank-card/transactions")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("adjustment", [item["type"] for item in response.json()])
        rejected = client.get("/api/bank-card/transactions?type=adjustment")
        self.assertEqual(rejected.status_code, 422)


class CombinedTransferTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add(BankCardBalance(id=1, balance=0))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_pending_purchases_do_not_change_balance_and_share_one_fee(self):
        first = create_pending_purchase(self.db, 65, 6.5)
        second = create_pending_purchase(self.db, 70, 7)
        self.assertEqual(self.db.get(BankCardBalance, 1).balance, 0)

        transfer, deposits = create_combined_transfer(self.db, [first.id, second.id], .01)
        self.db.commit()

        self.assertEqual(transfer.gross_usdt, 20)
        self.assertEqual(transfer.actual_received, 19.99)
        self.assertEqual([item.fee_allocated for item in deposits], [.01, 0])
        self.assertEqual(self.db.get(BankCardBalance, 1).balance, 19.99)
        self.assertEqual([first.status, second.status], ["transferred", "transferred"])

    def test_fee_allocation_can_cross_small_purchase_lots(self):
        first = create_pending_purchase(self.db, .035, 7)
        second = create_pending_purchase(self.db, 7, 7)
        _transfer, deposits = create_combined_transfer(self.db, [first.id, second.id], .01)
        self.db.commit()
        self.assertEqual([item.fee_allocated for item in deposits], [.005, .005])
        self.assertEqual([item.actual_received for item in deposits], [0, .995])

    def test_deleting_unused_transfer_returns_purchases_to_pending(self):
        first = create_pending_purchase(self.db, 65, 6.5)
        second = create_pending_purchase(self.db, 70, 7)
        transfer, _deposits = create_combined_transfer(self.db, [first.id, second.id], .01)
        self.db.commit()

        result = delete_unused_transfer(self.db, transfer.id)
        self.db.commit()

        self.assertEqual(result["restored_purchase_ids"], [first.id, second.id])
        self.assertEqual(self.db.get(BankCardBalance, 1).balance, 0)
        self.assertEqual(self.db.get(BankCardPurchase, first.id).status, "pending")
        self.assertEqual(self.db.query(BankCardDeposit).count(), 0)

    def test_used_lot_protects_complete_transfer(self):
        purchase = create_pending_purchase(self.db, 65, 6.5)
        transfer, deposits = create_combined_transfer(self.db, [purchase.id], .01)
        charge = BankCardCharge(
            kind="subscription", subscription_name="Service", charged_usdt=1,
            actual_cny_cost=6.5, balance_before=9.99, balance_after=8.99,
        )
        self.db.add(charge)
        self.db.flush()
        self.db.add(BankCardChargeAllocation(
            charge_id=charge.id, deposit_id=deposits[0].id,
            usdt_amount=1, c2c_rate=6.5, cny_cost=6.5,
        ))
        deposits[0].remaining_usdt -= 1
        self.db.commit()

        with self.assertRaises(TransferAlreadyUsedError):
            delete_unused_transfer(self.db, transfer.id)


class CombinedTransferMigrationTests(unittest.TestCase):
    def test_four_legacy_rows_become_two_transfers_and_restore_duplicate_fees(self):
        engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        Base.metadata.create_all(engine)
        with Factory() as db:
            db.add_all([
                AppSettings(key="schema_version", value="5"),
                BankCardBalance(id=1, balance=39.96),
                *[
                    BankCardDeposit(
                        id=index, usdt_amount=10, c2c_rate=7, cny_cost=70,
                        chain_fee=.01, actual_received=9.99, remaining_usdt=9.99,
                    ) for index in range(1, 5)
                ],
            ])
            db.commit()
        with patch("app.database.engine", engine), patch("app.database.SessionLocal", Factory):
            init_db()
            init_db()
        with Factory() as db:
            self.assertEqual(db.get(AppSettings, "schema_version").value, "6")
            transfers = db.query(BankCardTransfer).order_by(BankCardTransfer.id).all()
            self.assertEqual(len(transfers), 2)
            self.assertEqual([transfers[0].actual_received, transfers[1].actual_received], [9.99, 29.99])
            self.assertEqual(db.get(BankCardBalance, 1).balance, 39.98)
            second_lots = db.query(BankCardDeposit).filter_by(transfer_id=transfers[1].id).order_by(BankCardDeposit.id).all()
            self.assertEqual([item.fee_allocated for item in second_lots], [.01, 0, 0])
        engine.dispose()


class CombinedTransferApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(self.engine)
        self.Factory = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        with self.Factory() as db:
            db.add(BankCardBalance(id=1, balance=0))
            db.commit()
        app = FastAPI()
        app.include_router(bank_card_router)

        def override_db():
            with self.Factory() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)

    def tearDown(self):
        self.engine.dispose()

    def test_purchase_transfer_grouped_ledger_and_restore(self):
        first = self.client.post("/api/bank-card/purchases", json={"cny_amount": 65, "c2c_rate": 6.5}).json()
        second = self.client.post("/api/bank-card/purchases", json={"cny_amount": 70, "c2c_rate": 7}).json()
        self.assertEqual(self.client.get("/api/bank-card/balance").json()["balance"], 0)

        response = self.client.post("/api/bank-card/transfers", json={
            "purchase_ids": [first["id"], second["id"]], "chain_fee": .01,
        })
        self.assertEqual(response.status_code, 201)
        transfer = response.json()
        self.assertEqual(transfer["actual_received"], 19.99)
        self.assertEqual([item["fee_allocated"] for item in transfer["items"]], [.01, 0])

        ledger = self.client.get("/api/bank-card/transactions?type=deposit").json()
        self.assertEqual(len(ledger), 1)
        self.assertEqual(len(ledger[0]["details"]["items"]), 2)

        deleted = self.client.delete(f'/api/bank-card/transfers/{transfer["id"]}')
        self.assertEqual(deleted.status_code, 200)
        pending = self.client.get("/api/bank-card/purchases?status=pending").json()
        self.assertEqual([item["id"] for item in pending], [first["id"], second["id"]])
        self.assertEqual(self.client.get("/api/bank-card/balance").json()["balance"], 0)


if __name__ == "__main__":
    unittest.main()
