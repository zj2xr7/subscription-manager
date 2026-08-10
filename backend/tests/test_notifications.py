import asyncio
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, init_db
from app.models import (
    AppSettings,
    BankCardBalance,
    NotificationDelivery,
    NotificationSchedulerState,
    Subscription,
)
from app.tasks.scheduler import check_due_subscriptions
from app.routers.notifications import notification_overview
from app.schemas import NotificationOverviewOut


class NotificationSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db:
            db.add_all([
                AppSettings(key="server_chan_key", value="saved-key"),
                AppSettings(key="exchange_rate_api_key", value=""),
                AppSettings(key="notification_days_before", value="[7, 3, 1]"),
                BankCardBalance(id=1, balance=0),
                NotificationSchedulerState(id=1),
                Subscription(
                    name="Local Service", price=20, currency="CNY", billing_cycle="monthly",
                    next_billing_date=date(2026, 8, 17), payment_method="alipay",
                ),
            ])
            db.commit()

    def deliveries(self):
        with Session(self.engine) as db:
            return db.query(NotificationDelivery).order_by(NotificationDelivery.id).all()

    def run_check(self, sender, today, startup=False):
        with patch("app.tasks.scheduler.SessionLocal", side_effect=lambda: Session(self.engine)), \
                patch("app.tasks.scheduler.send_server_chan", new=sender):
            asyncio.run(check_due_subscriptions(is_startup=startup, today=today))

    def test_multiple_exact_nodes_send_once_each(self):
        sender = AsyncMock(return_value=True)
        self.run_check(sender, date(2026, 8, 10))
        self.run_check(sender, date(2026, 8, 10))
        self.run_check(sender, date(2026, 8, 14))
        self.assertEqual(sender.await_count, 2)
        self.assertEqual([item.lead_days for item in self.deliveries()], [7, 3])

    def test_failed_node_is_not_retried_but_next_node_runs(self):
        sender = AsyncMock(side_effect=[False, True])
        self.run_check(sender, date(2026, 8, 10))
        self.run_check(sender, date(2026, 8, 10))
        self.run_check(sender, date(2026, 8, 14))
        self.assertEqual(sender.await_count, 2)
        self.assertEqual([item.status for item in self.deliveries()], ["failed", "sent"])

    def test_startup_uses_only_nearest_missed_node(self):
        sender = AsyncMock(return_value=True)
        self.run_check(sender, date(2026, 8, 15), startup=True)
        self.run_check(sender, date(2026, 8, 15), startup=True)
        deliveries = self.deliveries()
        self.assertEqual(len(deliveries), 1)
        self.assertEqual(deliveries[0].lead_days, 3)
        self.assertTrue(deliveries[0].is_catch_up)

    def test_startup_prefers_exact_node(self):
        sender = AsyncMock(return_value=True)
        self.run_check(sender, date(2026, 8, 14), startup=True)
        delivery = self.deliveries()[0]
        self.assertEqual(delivery.lead_days, 3)
        self.assertFalse(delivery.is_catch_up)

    def test_overview_exposes_history_and_future_unattempted_nodes(self):
        sender = AsyncMock(return_value=True)
        self.run_check(sender, date(2026, 8, 10))
        with Session(self.engine) as db:
            result = notification_overview(db)
            NotificationOverviewOut.model_validate(result)
        self.assertTrue(result["enabled"])
        self.assertEqual(result["notification_days_before"], [7, 3, 1])
        self.assertEqual(result["recent_deliveries"][0].status, "sent")
        self.assertNotIn(7, [item["lead_days"] for item in result["next_reminders"]])
        self.assertIn(3, [item["lead_days"] for item in result["next_reminders"]])


class NotificationMigrationTests(unittest.TestCase):
    def test_legacy_scalar_and_last_notified_date_are_migrated_idempotently(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "legacy.db"
            engine = create_engine(f"sqlite:///{database_path.as_posix()}")
            Base.metadata.create_all(engine)
            Factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
            with Factory() as db:
                db.add_all([
                    AppSettings(key="server_chan_key", value=""),
                    AppSettings(key="exchange_rate_api_key", value=""),
                    AppSettings(key="notification_days_before", value="7"),
                    AppSettings(key="schema_version", value="2"),
                    BankCardBalance(id=1, balance=0),
                    Subscription(
                        name="Legacy Service", price=20, currency="CNY", billing_cycle="monthly",
                        next_billing_date=date(2026, 8, 17), payment_method="alipay",
                        last_notified_date=date(2026, 8, 10),
                    ),
                ])
                db.commit()
            with patch("app.database.engine", engine), patch("app.database.SessionLocal", Factory):
                init_db()
                init_db()
            with Factory() as db:
                self.assertEqual(json.loads(db.get(AppSettings, "notification_days_before").value), [7])
                self.assertEqual(db.get(AppSettings, "schema_version").value, "3")
                deliveries = db.query(NotificationDelivery).all()
                self.assertEqual(len(deliveries), 1)
                self.assertEqual(deliveries[0].lead_days, 7)
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
