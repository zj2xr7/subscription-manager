from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    billing_cycle: Mapped[str] = mapped_column(String(16), nullable=False)
    custom_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_billing_date: Mapped[date] = mapped_column(Date, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(16), nullable=False)
    c2c_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_notified_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class BankCardDeposit(Base):
    __tablename__ = "bank_card_deposits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usdt_amount: Mapped[float] = mapped_column(Float, nullable=False)
    c2c_rate: Mapped[float] = mapped_column(Float, nullable=False)
    cny_cost: Mapped[float] = mapped_column(Float, nullable=False)
    chain_fee: Mapped[float] = mapped_column(Float, default=0.01)
    actual_received: Mapped[float] = mapped_column(Float, nullable=False)
    remaining_usdt: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class BankCardCharge(Base):
    __tablename__ = "bank_card_charges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(24), default="subscription")
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    subscription_name: Mapped[str] = mapped_column(String(120), nullable=False)
    original_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    original_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    converted_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    charged_usdt: Mapped[float] = mapped_column(Float, nullable=False)
    actual_cny_cost: Mapped[float] = mapped_column(Float, nullable=False)
    balance_before: Mapped[float] = mapped_column(Float, nullable=False)
    balance_after: Mapped[float] = mapped_column(Float, nullable=False)
    billing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_billing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class BankCardChargeAllocation(Base):
    __tablename__ = "bank_card_charge_allocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    charge_id: Mapped[int] = mapped_column(
        ForeignKey("bank_card_charges.id", ondelete="CASCADE"), nullable=False
    )
    deposit_id: Mapped[int] = mapped_column(
        ForeignKey("bank_card_deposits.id"), nullable=False
    )
    usdt_amount: Mapped[float] = mapped_column(Float, nullable=False)
    c2c_rate: Mapped[float] = mapped_column(Float, nullable=False)
    cny_cost: Mapped[float] = mapped_column(Float, nullable=False)


class AlipayCharge(Base):
    __tablename__ = "alipay_charges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    subscription_name: Mapped[str] = mapped_column(String(120), nullable=False)
    original_price: Mapped[float] = mapped_column(Float, nullable=False)
    original_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    conversion_rate: Mapped[float] = mapped_column(Float, nullable=False)
    actual_cny_cost: Mapped[float] = mapped_column(Float, nullable=False)
    billing_date: Mapped[date] = mapped_column(Date, nullable=False)
    next_billing_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class BankCardBalance(Base):
    __tablename__ = "bank_card_balance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    balance: Mapped[float] = mapped_column(Float, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AppSettings(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(String(500), default="")


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "subscription_id", "billing_date", "lead_days", "kind",
            name="uq_notification_subscription_billing_lead_kind",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), default="scheduled")
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    subscription_name: Mapped[str] = mapped_column(String(120), nullable=False)
    billing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    lead_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_catch_up: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class NotificationSchedulerState(Base):
    __tablename__ = "notification_scheduler_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="never")
    due_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
