import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AppSettings, NotificationDelivery
from ..schemas import (
    ExchangeRateSettingsUpdate,
    NotificationSettingsUpdate,
    SettingsOut,
    SettingsUpdate,
    TestNotificationRequest,
)
from ..services.exchange_rate import exchange_rate_service
from ..services.notification import parse_notification_days, sanitize_notification_error, send_server_chan

router = APIRouter(prefix="/api/settings", tags=["settings"])
KEYS = ("server_chan_key", "exchange_rate_api_key", "notification_days_before")


def as_output(db: Session) -> SettingsOut:
    values = {key: (db.get(AppSettings, key).value if db.get(AppSettings, key) else "") for key in KEYS}
    return SettingsOut(
        server_chan_key=values["server_chan_key"],
        exchange_rate_api_key=values["exchange_rate_api_key"],
        notification_days_before=parse_notification_days(values["notification_days_before"]),
    )


@router.get("", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db)):
    return as_output(db)


@router.put("", response_model=SettingsOut)
def update_settings(payload: SettingsUpdate, db: Session = Depends(get_db)):
    for key, value in payload.model_dump(exclude_none=True).items():
        row = db.get(AppSettings, key)
        if row is None:
            row = AppSettings(key=key)
            db.add(row)
        row.value = json.dumps(value) if key == "notification_days_before" else str(value)
    db.commit()
    return as_output(db)


@router.put("/notification", response_model=SettingsOut)
def update_notification_settings(payload: NotificationSettingsUpdate, db: Session = Depends(get_db)):
    values = {
        "server_chan_key": payload.server_chan_key.strip(),
        "notification_days_before": json.dumps(payload.notification_days_before),
    }
    for key, value in values.items():
        row = db.get(AppSettings, key)
        if row is None:
            row = AppSettings(key=key)
            db.add(row)
        row.value = value
    db.commit()
    return as_output(db)


@router.put("/exchange-rate")
async def update_exchange_rate_settings(payload: ExchangeRateSettingsUpdate, db: Session = Depends(get_db)):
    api_key = payload.exchange_rate_api_key.strip()
    quotes = await exchange_rate_service.cny_quotes(api_key, refresh=True)
    if api_key and quotes["source"] != "api":
        raise HTTPException(422, "ExchangeRate API Key validation failed; the saved key was not changed")

    row = db.get(AppSettings, "exchange_rate_api_key")
    if row is None:
        row = AppSettings(key="exchange_rate_api_key")
        db.add(row)
    row.value = api_key
    db.commit()
    return {"settings": as_output(db), "quotes": quotes}


@router.post("/test-notification")
async def test_notification(_payload: TestNotificationRequest, db: Session = Depends(get_db)):
    stored = db.get(AppSettings, "server_chan_key")
    key = stored.value if stored else ""
    if not key:
        raise HTTPException(400, "ServerChan SendKey is required")
    delivery = NotificationDelivery(
        kind="test", subscription_name="通知通道测试", status="sending"
    )
    db.add(delivery)
    db.commit()
    try:
        sent = await send_server_chan(key, "SubManager 通知测试", "配置成功，订阅到期提醒已启用。")
        delivery.status = "sent" if sent else "failed"
        delivery.error_message = None if sent else "通知服务拒绝了本次请求"
    except Exception as exc:
        delivery.status = "failed"
        delivery.error_message = sanitize_notification_error(exc)
        db.commit()
        raise HTTPException(502, delivery.error_message) from exc
    db.commit()
    if not sent:
        raise HTTPException(502, delivery.error_message)
    return {"sent": True, "delivery_id": delivery.id, "status": delivery.status}
