import os
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
    with SessionLocal() as db:
        if db.get(models.BankCardBalance, 1) is None:
            db.add(models.BankCardBalance(id=1, balance=0))
        defaults = {
            "server_chan_key": os.getenv("SERVER_CHAN_KEY", ""),
            "exchange_rate_api_key": os.getenv("EXCHANGE_RATE_API_KEY", ""),
            "notification_days_before": "7",
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
        db.commit()
