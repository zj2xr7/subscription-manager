from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AppSettings, NotificationDelivery, NotificationSchedulerState, Subscription
from ..schemas import NotificationOverviewOut
from ..services.notification import parse_notification_days, sanitize_notification_error
from ..tasks.scheduler import scheduler

router = APIRouter(prefix="/api/notifications", tags=["notifications"])
TIMEZONE = ZoneInfo("Asia/Shanghai")


def notification_health(enabled: bool, running: bool, status: str) -> tuple[str, str]:
    if not enabled:
        return "disabled", "未配置 SendKey"
    if not running:
        return "stopped", "通知调度未运行"
    if status == "running":
        return "checking", "正在检查到期订阅"
    if status == "failed":
        return "degraded", "最近一次通知检查异常"
    if status in ("never", "disabled"):
        return "waiting", "等待首次通知检查"
    return "healthy", "通知调度运行正常"


@router.get("/overview", response_model=NotificationOverviewOut)
def notification_overview(db: Session = Depends(get_db)):
    send_key = db.get(AppSettings, "server_chan_key")
    days_row = db.get(AppSettings, "notification_days_before")
    days = parse_notification_days(days_row.value if days_row else "7")
    state = db.get(NotificationSchedulerState, 1)
    job = scheduler.get_job("due-subscriptions")
    delivery_rows = db.scalars(
        select(NotificationDelivery).order_by(NotificationDelivery.attempted_at.desc()).limit(12)
    ).all()
    deliveries = [{
        "id": item.id,
        "kind": item.kind,
        "subscription_id": item.subscription_id,
        "subscription_name": item.subscription_name,
        "billing_date": item.billing_date,
        "lead_days": item.lead_days,
        "is_catch_up": item.is_catch_up,
        "status": item.status,
        "error_message": sanitize_notification_error(item.error_message),
        "attempted_at": item.attempted_at,
    } for item in delivery_rows]
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
    reminders.sort(key=lambda item: (
        -item["lead_days"], item["scheduled_for"], item["billing_date"], item["subscription_id"]
    ))
    enabled = bool(send_key and send_key.value)
    state_status = state.status if state else "never"
    health, health_message = notification_health(enabled, scheduler.running, state_status)
    scheduler_data = {
        "running": scheduler.running,
        "next_run_at": job.next_run_time if job else None,
        "last_started_at": state.last_started_at if state else None,
        "last_completed_at": state.last_completed_at if state else None,
        "status": state.status if state else "never",
        "due_count": state.due_count if state else 0,
        "sent_count": state.sent_count if state else 0,
        "failed_count": state.failed_count if state else 0,
        "error_message": sanitize_notification_error(state.error_message, scheduler=True) if state else None,
    }
    return {
        "enabled": enabled,
        "health": health,
        "health_message": health_message,
        "notification_days_before": days,
        "scheduler": scheduler_data,
        "next_reminders": reminders[:12],
        "recent_deliveries": deliveries,
    }
