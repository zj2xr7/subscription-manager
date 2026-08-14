import os
import json
from datetime import datetime, time
from pathlib import Path

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB = (BASE_DIR / "data" / "submanager.db").as_posix()
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB}")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from . import models

    Path(BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    columns = {column["name"] for column in inspect(engine).get_columns("bank_card_deposits")}
    if "remaining_usdt" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE bank_card_deposits ADD COLUMN remaining_usdt FLOAT"))
    deposit_columns = {column["name"] for column in inspect(engine).get_columns("bank_card_deposits")}
    with engine.begin() as connection:
        if "purchase_id" not in deposit_columns:
            connection.execute(text("ALTER TABLE bank_card_deposits ADD COLUMN purchase_id INTEGER"))
        if "transfer_id" not in deposit_columns:
            connection.execute(text("ALTER TABLE bank_card_deposits ADD COLUMN transfer_id INTEGER"))
        if "fee_allocated" not in deposit_columns:
            connection.execute(text("ALTER TABLE bank_card_deposits ADD COLUMN fee_allocated FLOAT DEFAULT 0"))
    with SessionLocal() as db:
        if db.get(models.BankCardBalance, 1) is None:
            db.add(models.BankCardBalance(id=1, balance=0))
        if db.get(models.NotificationSchedulerState, 1) is None:
            db.add(models.NotificationSchedulerState(id=1))
        defaults = {
            "server_chan_key": os.getenv("SERVER_CHAN_KEY", ""),
            "exchange_rate_api_key": os.getenv("EXCHANGE_RATE_API_KEY", ""),
            "notification_days_before": "[7]",
        }
        for key, value in defaults.items():
            if db.get(models.AppSettings, key) is None:
                db.add(models.AppSettings(key=key, value=value))
        db.flush()
        version = db.get(models.AppSettings, "schema_version")
        if version is None or int(version.value or 0) < 2:
            deposits = db.scalars(
                select(models.BankCardDeposit).order_by(models.BankCardDeposit.created_at, models.BankCardDeposit.id)
            ).all()
            for deposit in deposits:
                deposit.remaining_usdt = round(deposit.actual_received, 4)

            balance = db.get(models.BankCardBalance, 1)
            deposited_total = round(sum(item.actual_received for item in deposits), 4)
            historical_gap = round(max(deposited_total - balance.balance, 0), 4)
            if historical_gap > 0.00005:
                remaining = historical_gap
                allocations: list[tuple[models.BankCardDeposit, float]] = []
                for deposit in deposits:
                    used = round(min(deposit.remaining_usdt or 0, remaining), 4)
                    if used <= 0:
                        continue
                    deposit.remaining_usdt = round((deposit.remaining_usdt or 0) - used, 4)
                    allocations.append((deposit, used))
                    remaining = round(remaining - used, 4)
                    if remaining <= 0.00005:
                        break
                actual_cost = round(sum(amount * deposit.c2c_rate for deposit, amount in allocations), 2)
                charge = models.BankCardCharge(
                    kind="historical_adjustment",
                    subscription_name="历史余额调整",
                    charged_usdt=historical_gap,
                    actual_cny_cost=actual_cost,
                    balance_before=deposited_total,
                    balance_after=balance.balance,
                )
                db.add(charge)
                db.flush()
                for deposit, amount in allocations:
                    db.add(models.BankCardChargeAllocation(
                        charge_id=charge.id,
                        deposit_id=deposit.id,
                        usdt_amount=amount,
                        c2c_rate=deposit.c2c_rate,
                        cny_cost=round(amount * deposit.c2c_rate, 2),
                    ))
            if version is None:
                db.add(models.AppSettings(key="schema_version", value="2"))
            else:
                version.value = "2"
        db.flush()
        version = db.get(models.AppSettings, "schema_version")
        if version is None or int(version.value or 0) < 3:
            notification_days = db.get(models.AppSettings, "notification_days_before")
            try:
                raw_days = json.loads(notification_days.value or "7")
            except (TypeError, ValueError):
                raw_days = int(notification_days.value or 7)
            if isinstance(raw_days, int):
                raw_days = [raw_days]
            normalized_days = sorted({int(day) for day in raw_days if 0 <= int(day) <= 90}, reverse=True) or [7]
            notification_days.value = json.dumps(normalized_days)
            for item in db.scalars(
                select(models.Subscription).where(models.Subscription.last_notified_date.is_not(None))
            ).all():
                lead_days = (item.next_billing_date - item.last_notified_date).days
                if not 0 <= lead_days <= 90:
                    continue
                exists = db.scalar(select(models.NotificationDelivery.id).where(
                    models.NotificationDelivery.kind == "scheduled",
                    models.NotificationDelivery.subscription_id == item.id,
                    models.NotificationDelivery.billing_date == item.next_billing_date,
                    models.NotificationDelivery.lead_days == lead_days,
                ))
                if exists is None:
                    db.add(models.NotificationDelivery(
                        kind="scheduled",
                        subscription_id=item.id,
                        subscription_name=item.name,
                        billing_date=item.next_billing_date,
                        lead_days=lead_days,
                        status="sent",
                        attempted_at=datetime.combine(item.last_notified_date, time(hour=1)),
                    ))
            version.value = "3"
        db.flush()
        version = db.get(models.AppSettings, "schema_version")
        if version is None or int(version.value or 0) < 4:
            from .services.notification import sanitize_notification_error

            state = db.get(models.NotificationSchedulerState, 1)
            if state and state.error_message:
                lowered = state.error_message.lower()
                if "different event loop" in lowered or "asyncio" in lowered:
                    state.status = "never"
                    state.error_message = None
                    state.due_count = state.sent_count = state.failed_count = 0
                else:
                    state.error_message = sanitize_notification_error(state.error_message, scheduler=True)
            for delivery in db.scalars(
                select(models.NotificationDelivery).where(models.NotificationDelivery.error_message.is_not(None))
            ).all():
                delivery.error_message = sanitize_notification_error(delivery.error_message)
            version.value = "4"
        db.flush()
        version = db.get(models.AppSettings, "schema_version")
        if version is None or int(version.value or 0) < 5:
            from .services.bank_funds import purge_historical_adjustments

            purge_historical_adjustments(db)
            version.value = "5"
        db.flush()
        version = db.get(models.AppSettings, "schema_version")
        if version is None or int(version.value or 0) < 6:
            legacy = db.scalars(
                select(models.BankCardDeposit)
                .where(models.BankCardDeposit.transfer_id.is_(None))
                .order_by(models.BankCardDeposit.created_at, models.BankCardDeposit.id)
            ).all()

            # This private deployment had four historical rows: the first was one
            # withdrawal and the following three were one combined withdrawal.
            groups: list[list[models.BankCardDeposit]] = []
            if len(legacy) == 4:
                groups = [[legacy[0]], legacy[1:]]
            else:
                groups = [[item] for item in legacy]

            for group in groups:
                purchases: list[tuple[models.BankCardDeposit, models.BankCardPurchase]] = []
                for deposit in group:
                    purchase = models.BankCardPurchase(
                        cny_amount=deposit.cny_cost,
                        c2c_rate=deposit.c2c_rate,
                        purchased_usdt=deposit.usdt_amount,
                        status="transferred",
                        created_at=deposit.created_at,
                        updated_at=deposit.created_at,
                    )
                    db.add(purchase)
                    db.flush()
                    deposit.purchase_id = purchase.id
                    purchases.append((deposit, purchase))

                combined = len(group) == 3
                transfer_fee = 0.01 if combined else round(sum(item.chain_fee or 0 for item in group), 4)
                gross = round(sum(item.usdt_amount for item in group), 4)
                transfer = models.BankCardTransfer(
                    gross_usdt=gross,
                    chain_fee=transfer_fee,
                    actual_received=round(gross - transfer_fee, 4),
                    created_at=min(item.created_at for item in group),
                )
                db.add(transfer)
                db.flush()

                fee_left = transfer_fee
                for deposit, _purchase in purchases:
                    old_actual = round(deposit.actual_received, 4)
                    allocated_fee = round(min(deposit.usdt_amount, fee_left), 4)
                    fee_left = round(fee_left - allocated_fee, 4)
                    new_actual = round(deposit.usdt_amount - allocated_fee, 4)
                    deposit.transfer_id = transfer.id
                    deposit.chain_fee = allocated_fee
                    deposit.fee_allocated = allocated_fee
                    deposit.actual_received = new_actual
                    deposit.remaining_usdt = round((deposit.remaining_usdt or 0) + (new_actual - old_actual), 4)

            if legacy:
                db.flush()
                balance = db.get(models.BankCardBalance, 1)
                balance.balance = round(sum(
                    item or 0 for item in db.scalars(select(models.BankCardDeposit.remaining_usdt)).all()
                ), 4)
            version.value = "6"
        db.commit()
