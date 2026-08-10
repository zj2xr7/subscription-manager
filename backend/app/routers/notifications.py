from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AppSettings, NotificationDelivery, NotificationSchedulerState, Subscription
from ..schemas import NotificationOverviewOut
from ..services.notification import parse_notification_days
from ..tasks.scheduler import scheduler

router = APIRouter(prefix="/api/notifications", tags=["notifications"])
TIMEZONE = ZoneInfo("Asia/Shanghai")


@router.get("/overview", response_model=NotificationOverviewOut)
def notification_overview(db: Session = Depends(get_db)):
    send_key = db.get(AppSettings, "server_chan_key")
    days_row = db.get(AppSettings, "notification_days_before")
    days = parse_notification_days(days_row.value if days_row else "7")
    state = db.get(NotificationSchedulerState, 1)
    job = scheduler.get_job("due-subscriptions")
    deliveries = db.scalars(
        select(NotificationDelivery).order_by(NotificationDelivery.attempted_at.desc()).limit(12)
    ).all()
    attempted = {
        (item.subscription_id, item.billing_date, item.lead_days)
        for item in db.scalars(
            select(NotificationDelivery).where(NotificationDelivery.kind == "scheduled")
        ).all()
    }
    today = datetime.now(TIMEZONE).date()
    reminders = []
    subscriptions = db.scalars(
        select(Subscription)
        .where(Subscription.next_billing_date >= today)
        .order_by(Subscription.next_billing_date, Subscription.id)
    ).all()
    for item in subscriptions:
        for lead_days in days:
            scheduled_for = item.next_billing_date - timedelta(days=lead_days)
            if scheduled_for < today or (item.id, item.next_billing_date, lead_days) in attempted:
                continue
            reminders.append({
                "subscription_id": item.id,
                "subscription_name": item.name,
                "billing_date": item.next_billing_date,
                "lead_days": lead_days,
                "scheduled_for": scheduled_for,
            })
    reminders.sort(key=lambda item: (item["scheduled_for"], item["billing_date"], item["subscription_id"]))
    scheduler_data = {
        "running": scheduler.running,
        "next_run_at": job.next_run_time if job else None,
        "last_started_at": state.last_started_at if state else None,
        "last_completed_at": state.last_completed_at if state else None,
        "status": state.status if state else "never",
        "due_count": state.due_count if state else 0,
        "sent_count": state.sent_count if state else 0,
        "failed_count": state.failed_count if state else 0,
        "error_message": state.error_message if state else None,
    }
    return {
        "enabled": bool(send_key and send_key.value),
        "notification_days_before": days,
        "scheduler": scheduler_data,
        "next_reminders": reminders[:12],
        "recent_deliveries": deliveries,
    }
