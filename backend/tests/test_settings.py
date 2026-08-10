import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import AppSettings, NotificationDelivery
from app.routers.settings import (
    test_notification,
    update_exchange_rate_settings,
    update_notification_settings,
)
from app.schemas import (
    ExchangeRateSettingsUpdate,
    NotificationSettingsUpdate,
    TestNotificationRequest,
)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add_all([
            AppSettings(key="server_chan_key", value="saved-send-key"),
            AppSettings(key="exchange_rate_api_key", value="old-rate-key"),
            AppSettings(key="notification_days_before", value="7"),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_notification_settings_save_is_independent(self):
        saved = update_notification_settings(
            NotificationSettingsUpdate(server_chan_key=" new-send-key ", notification_days_before=[12, 3, 12]),
            self.db,
        )
        self.assertEqual(saved.server_chan_key, "new-send-key")
        self.assertEqual(saved.notification_days_before, [12, 3])
        self.assertEqual(saved.exchange_rate_api_key, "old-rate-key")

    def test_exchange_key_is_saved_only_after_api_validation(self):
        quotes = {"source": "api", "quotes": {"USD": 7.1, "GBP": 9.0, "CAD": 5.2}}
        with patch("app.routers.settings.exchange_rate_service.cny_quotes", new=AsyncMock(return_value=quotes)):
            result = asyncio.run(update_exchange_rate_settings(
                ExchangeRateSettingsUpdate(exchange_rate_api_key=" new-rate-key "), self.db
            ))
        self.assertEqual(result["settings"].exchange_rate_api_key, "new-rate-key")
        self.assertEqual(result["quotes"], quotes)
        self.assertEqual(self.db.get(AppSettings, "exchange_rate_api_key").value, "new-rate-key")

    def test_invalid_exchange_key_does_not_replace_saved_key(self):
        quotes = {"source": "reference", "quotes": {"USD": 7.2, "GBP": 9.14, "CAD": 5.32}}
        with patch("app.routers.settings.exchange_rate_service.cny_quotes", new=AsyncMock(return_value=quotes)):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(update_exchange_rate_settings(
                    ExchangeRateSettingsUpdate(exchange_rate_api_key="invalid-key"), self.db
                ))
        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(self.db.get(AppSettings, "exchange_rate_api_key").value, "old-rate-key")

    def test_empty_exchange_key_switches_to_reference_rates(self):
        quotes = {"source": "reference", "quotes": {"USD": 7.2, "GBP": 9.14, "CAD": 5.32}}
        with patch("app.routers.settings.exchange_rate_service.cny_quotes", new=AsyncMock(return_value=quotes)):
            result = asyncio.run(update_exchange_rate_settings(
                ExchangeRateSettingsUpdate(exchange_rate_api_key=""), self.db
            ))
        self.assertEqual(result["settings"].exchange_rate_api_key, "")
        self.assertEqual(result["quotes"]["source"], "reference")

    def test_notification_test_uses_stored_key_instead_of_payload(self):
        sender = AsyncMock(return_value=True)
        with patch("app.routers.settings.send_server_chan", new=sender):
            result = asyncio.run(test_notification(TestNotificationRequest(server_chan_key="draft-key"), self.db))
        self.assertEqual(result["sent"], True)
        self.assertEqual(result["status"], "sent")
        delivery = self.db.get(NotificationDelivery, result["delivery_id"])
        self.assertEqual(delivery.kind, "test")
        self.assertEqual(delivery.status, "sent")
        self.assertEqual(sender.await_args.args[0], "saved-send-key")

    def test_notification_test_sanitizes_provider_failure(self):
        raw_error = Exception("400 Bad Request https://sctapi.ftqq.com/SECRET.send")
        with patch("app.routers.settings.send_server_chan", new=AsyncMock(side_effect=raw_error)):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(test_notification(TestNotificationRequest(), self.db))
        self.assertEqual(raised.exception.status_code, 502)
        self.assertNotIn("http", str(raised.exception.detail).lower())
        self.assertNotIn("SECRET", str(raised.exception.detail))
        delivery = self.db.query(NotificationDelivery).order_by(NotificationDelivery.id.desc()).first()
        self.assertNotIn("http", delivery.error_message.lower())
        self.assertNotIn("SECRET", delivery.error_message)


if __name__ == "__main__":
    unittest.main()
