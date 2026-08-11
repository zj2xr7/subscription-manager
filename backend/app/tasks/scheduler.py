import asyncio
import threading
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..database import SessionLocal
from ..models import (
    AppSettings,
    NotificationDelivery,
    NotificationSchedulerState,
    Subscription,
    utcnow,
)
from ..services.cost_calculator import calculate_cost
from ..services.funding_queue import build_bank_funding_queue
from ..services.notification import parse_notification_days, sanitize_notification_error, send_server_chan

TIMEZONE = ZoneInfo("Asia/Shanghai")
scheduler = BackgroundScheduler(timezone=TIMEZONE)
run_lock = threading.Lock()


def _setting(db, key: str, default: str = "") -> str:
    row = db.get(AppSettings, key)
    return row.value if row else default


def _candidate(item: Subscription, today: date, days: list[int], is_startup: bool):
    remaining = (item.next_billing_date - today).days
    if remaining < 0:
        return None
    if remaining in days:
        return remaining, False
    if is_startup:
        missed = sorted(day for day in days if day > remaining)
        if missed:
            return missed[0], True
    return None


def _already_attempted(db, item: Subscription, lead_days: int) -> bool:
    return db.scalar(select(NotificationDelivery.id).where(
        NotificationDelivery.kind == "scheduled",
        NotificationDelivery.subscription_id == item.id,
        NotificationDelivery.billing_date == item.next_billing_date,
        NotificationDelivery.lead_days == lead_days,
    )) is not None


async def _cost_text(item: Subscription, db, api_key: str, bank_costs: dict[int, dict]) -> str:
    if item.payment_method == "bank_card":
        cost = bank_costs[item.id]
        estimate = cost.get("estimated_cny_cost") or 0
        if cost["coverage_status"] == "sufficient":
            return f"预计成本：¥{estimate:.2f}（FIFO 批次成本）"
        return (
            f"预计成本：¥{estimate:.2f}\n\n"
            f"USDT 余额缺口：{cost['shortfall_usdt']:.4f} USDT"
        )
    cost = await calculate_cost(item.price, item.currency, item.payment_method, item.c2c_rate, api_key)
    return f"预计成本：¥{cost['cny_cost']:.2f}"


async def check_due_subscriptions(is_startup: bool = False, today: date | None = None):
    today = today or datetime.now(TIMEZONE).date()
    with SessionLocal() as db:
        state = db.get(NotificationSchedulerState, 1)
        if state is None:
            state = NotificationSchedulerState(id=1)
            db.add(state)
        state.last_started_at = utcnow()
        state.status = "running"
        state.due_count = state.sent_count = state.failed_count = 0
        state.error_message = None
        db.commit()

        try:
            days = parse_notification_days(_setting(db, "notification_days_before", "7"))
            send_key = _setting(db, "server_chan_key")
            api_key = _setting(db, "exchange_rate_api_key")
            items = db.scalars(
                select(Subscription)
                .where(Subscription.next_billing_date >= today)
                .order_by(Subscription.next_billing_date, Subscription.id)
            ).all()
            candidates = []
            for item in items:
                candidate = _candidate(item, today, days, is_startup)
                if candidate and not _already_attempted(db, item, candidate[0]):
                    candidates.append((item, *candidate))
            state.due_count = len(candidates)
            if not send_key:
                state.status = "disabled"
                state.last_completed_at = utcnow()
                db.commit()
                return

            _, bank_costs = await build_bank_funding_queue(db, api_key)
            for item, lead_days, is_catch_up in candidates:
                delivery = NotificationDelivery(
                    kind="scheduled",
                    subscription_id=item.id,
                    subscription_name=item.name,
                    billing_date=item.next_billing_date,
                    lead_days=lead_days,
                    is_catch_up=is_catch_up,
                    status="sending",
                )
                db.add(delivery)
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    continue
                days_remaining = (item.next_billing_date - today).days
                prefix = "延迟提醒 · " if is_catch_up else ""
                try:
                    sent = await send_server_chan(
                        send_key,
                        f"{prefix}{item.name} 将在 {days_remaining} 天后续费",
                        (
                            f"续费日期：{item.next_billing_date.isoformat()}\n\n"
                            f"{await _cost_text(item, db, api_key, bank_costs)}"
                        ),
                    )
                    delivery.status = "sent" if sent else "failed"
                    delivery.error_message = None if sent else "通知服务拒绝了本次请求"
                except Exception as exc:
                    delivery.status = "failed"
                    delivery.error_message = sanitize_notification_error(exc)
                if delivery.status == "sent":
                    state.sent_count += 1
                    item.last_notified_date = today
                else:
                    state.failed_count += 1
                db.commit()

            state.status = "failed" if state.failed_count else "success"
            state.last_completed_at = utcnow()
            db.commit()
        except Exception as exc:
            db.rollback()
            state = db.get(NotificationSchedulerState, 1) or NotificationSchedulerState(id=1)
            state.status = "failed"
            state.error_message = sanitize_notification_error(exc, scheduler=True)
            state.last_completed_at = utcnow()
            db.add(state)
            db.commit()


def run_check(is_startup: bool = False):
    if not run_lock.acquire(blocking=False):
        return
    try:
        asyncio.run(check_due_subscriptions(is_startup=is_startup))
    finally:
        run_lock.release()


def start_scheduler():
    if not scheduler.running:
        scheduler.add_job(
            run_check, "cron", hour=9, minute=0, id="due-subscriptions",
            replace_existing=True, coalesce=True, max_instances=1,
        )
        scheduler.start()
        scheduler.add_job(
            run_check, "date", run_date=datetime.now(TIMEZONE) + timedelta(seconds=1),
            args=[True], id="startup-due-subscriptions", replace_existing=True,
        )


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
