from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AppSettings
from ..schemas import SettingsOut, SettingsUpdate, TestNotificationRequest
from ..services.notification import send_server_chan

router = APIRouter(prefix="/api/settings", tags=["settings"])
KEYS = ("server_chan_key", "exchange_rate_api_key", "notification_days_before")


def as_output(db: Session) -> SettingsOut:
    values = {key: (db.get(AppSettings, key).value if db.get(AppSettings, key) else "") for key in KEYS}
    return SettingsOut(
        server_chan_key=values["server_chan_key"],
        exchange_rate_api_key=values["exchange_rate_api_key"],
        notification_days_before=int(values["notification_days_before"] or 7),
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
        row.value = str(value)
    db.commit()
    return as_output(db)


@router.post("/test-notification")
async def test_notification(payload: TestNotificationRequest, db: Session = Depends(get_db)):
    stored = db.get(AppSettings, "server_chan_key")
    key = payload.server_chan_key or (stored.value if stored else "")
    if not key:
        raise HTTPException(400, "ServerChan SendKey is required")
    try:
        sent = await send_server_chan(key, "SubManager 通知测试", "配置成功，订阅到期提醒已启用。")
    except Exception as exc:
        raise HTTPException(502, f"Notification provider error: {exc}") from exc
    if not sent:
        raise HTTPException(502, "Notification provider rejected the request")
    return {"sent": True}
