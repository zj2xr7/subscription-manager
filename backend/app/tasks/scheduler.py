import asyncio
from datetime import date, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from ..database import SessionLocal
from ..models import AppSettings, Subscription
from ..services.cost_calculator import calculate_cost
from ..services.bank_funds import allocate_fifo
from ..services.notification import send_server_chan

scheduler = BackgroundScheduler(timezone="Asia/Shanghai")


async def check_due_subscriptions():
    today = date.today()
    with SessionLocal() as db:
        notify_days = int((db.get(AppSettings, "notification_days_before") or AppSettings(value="7")).value)
        send_key = (db.get(AppSettings, "server_chan_key") or AppSettings(value="")).value
        api_key = (db.get(AppSettings, "exchange_rate_api_key") or AppSettings(value="")).value
        if not send_key:
            return
        items = db.scalars(
            select(Subscription).where(
                Subscription.next_billing_date >= today,
                Subscription.next_billing_date <= today + timedelta(days=notify_days),
            )
        ).all()
        for item in items:
            if item.last_notified_date == today:
                continue
            cost = await calculate_cost(item.price, item.currency, item.payment_method, item.c2c_rate, api_key)
            days = (item.next_billing_date - today).days
            if item.payment_method == "bank_card":
                allocations, shortfall = allocate_fifo(db, float(cost["required_usdt"]))
                covered_cost = round(sum(a.usdt_amount * a.deposit.c2c_rate for a in allocations), 2)
                cost_text = (
                    f"预计成本：¥{covered_cost:.2f}"
                    if shortfall == 0
                    else f"USDT 余额不足，缺口：{shortfall:.4f} USDT"
                )
            else:
                cost_text = f"预计成本：¥{cost['cny_cost']:.2f}"
            sent = await send_server_chan(
                send_key,
                f"{item.name} 将在 {days} 天后续费",
                f"续费日期：{item.next_billing_date.isoformat()}\n\n{cost_text}\n\n{cost['formula']}",
            )
            if sent:
                item.last_notified_date = today
                db.commit()


def run_check():
    asyncio.run(check_due_subscriptions())


def start_scheduler():
    if not scheduler.running:
        scheduler.add_job(run_check, "cron", hour=9, minute=0, id="due-subscriptions", replace_existing=True)
        scheduler.start()


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
