from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Currency = Literal["USD", "GBP", "CAD", "CNY"]
BillingCycle = Literal["monthly", "yearly", "custom"]
PaymentMethod = Literal["alipay", "bank_card"]


class SubscriptionBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    price: float = Field(gt=0)
    currency: Currency
    billing_cycle: BillingCycle
    custom_days: int | None = Field(default=None, ge=1)
    next_billing_date: date
    payment_method: PaymentMethod
    c2c_rate: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_combinations(self):
        if self.billing_cycle == "custom" and not self.custom_days:
            raise ValueError("custom_days is required for a custom billing cycle")
        if self.payment_method == "bank_card" and self.currency == "CNY":
            raise ValueError("CNY subscriptions must use Alipay")
        return self


class SubscriptionCreate(SubscriptionBase):
    pass


class SubscriptionUpdate(SubscriptionBase):
    pass


class CostBreakdown(BaseModel):
    payment_method: PaymentMethod
    original_price: float
    original_currency: Currency
    conversion_rate: float
    converted_amount: float
    fee_rate: float
    usdt_charge: float | None = None
    c2c_rate: float | None = None
    cny_cost: float | None
    formula: str
    required_usdt: float | None = None
    covered_usdt: float | None = None
    covered_cny_cost: float | None = None
    shortfall_usdt: float | None = None
    coverage_status: Literal["not_applicable", "sufficient", "partial", "empty"] = "not_applicable"
    allocations: list["AllocationOut"] = Field(default_factory=list)
    queue_position: int | None = None
    reserved_before_usdt: float | None = None
    available_for_charge_usdt: float | None = None
    estimated_cny_cost: float | None = None
    estimate_cny_rate: float | None = None
    estimate_source: Literal["fifo", "api", "reference"] | None = None


class SubscriptionOut(SubscriptionBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime
    cost: CostBreakdown | None = None


class DepositCreate(BaseModel):
    cny_amount: float = Field(gt=0)
    c2c_rate: float = Field(gt=0)


class DepositOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    usdt_amount: float
    c2c_rate: float
    cny_cost: float
    chain_fee: float
    actual_received: float
    remaining_usdt: float
    created_at: datetime


class DepositDeleteOut(BaseModel):
    deleted_deposit_id: int
    deleted_charge_count: int
    rolled_back_subscription_count: int
    balance: float


class AllocationOut(BaseModel):
    deposit_id: int
    usdt_amount: float
    c2c_rate: float
    cny_cost: float


class LotOut(DepositOut):
    pass


class BalanceOut(BaseModel):
    balance: float
    updated_at: datetime


class ChargeOut(BaseModel):
    charged_usdt: float
    actual_cny_cost: float
    balance: float
    next_billing_date: date
    allocations: list[AllocationOut]


class SubscriptionChargeRecordOut(BaseModel):
    id: str
    payment_method: PaymentMethod
    subscription_id: int | None
    subscription_name: str
    original_price: float
    original_currency: Currency
    conversion_rate: float | None = None
    cny_cost: float
    charged_usdt: float | None = None
    billing_date: date
    next_billing_date: date
    created_at: datetime
    allocations: list[AllocationOut] = Field(default_factory=list)


class TopUpQuoteRequest(BaseModel):
    subscription_ids: list[int] = Field(default_factory=list)
    c2c_rate: float = Field(gt=0)


class TopUpQuoteItem(BaseModel):
    subscription_id: int
    name: str
    required_usdt: float


class TopUpQuoteOut(BaseModel):
    items: list[TopUpQuoteItem]
    required_usdt: float
    available_usdt: float
    reserved_usdt: float = 0
    covered_usdt: float = 0
    shortfall_usdt: float
    suggested_purchase_usdt: float
    suggested_cny_amount: float


class SettingsOut(BaseModel):
    server_chan_key: str = ""
    exchange_rate_api_key: str = ""
    notification_days_before: list[int] = Field(default_factory=lambda: [7])


class SettingsUpdate(BaseModel):
    server_chan_key: str | None = None
    exchange_rate_api_key: str | None = None
    notification_days_before: list[int] | None = None

    @field_validator("notification_days_before", mode="before")
    @classmethod
    def coerce_notification_days(cls, value):
        if value is None:
            return value
        return [value] if isinstance(value, int) else value

    @field_validator("notification_days_before")
    @classmethod
    def validate_notification_days(cls, value):
        if value is None:
            return value
        return normalize_notification_days(value)


class NotificationSettingsUpdate(BaseModel):
    server_chan_key: str = ""
    notification_days_before: list[int] = Field(default_factory=lambda: [7])

    @field_validator("notification_days_before", mode="before")
    @classmethod
    def coerce_notification_days(cls, value):
        return [value] if isinstance(value, int) else value

    @field_validator("notification_days_before")
    @classmethod
    def validate_notification_days(cls, value):
        return normalize_notification_days(value)


class ExchangeRateSettingsUpdate(BaseModel):
    exchange_rate_api_key: str = ""


class TestNotificationRequest(BaseModel):
    server_chan_key: str | None = None


class ExchangeQuoteRequest(BaseModel):
    api_key: str = ""
    refresh: bool = True


def normalize_notification_days(values: list[int]) -> list[int]:
    if not values:
        raise ValueError("At least one notification day is required")
    if any(isinstance(value, bool) or value < 0 or value > 90 for value in values):
        raise ValueError("Notification days must be integers between 0 and 90")
    return sorted(set(values), reverse=True)


class NotificationDeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: Literal["scheduled", "test"]
    subscription_id: int | None
    subscription_name: str
    billing_date: date | None
    lead_days: int | None
    is_catch_up: bool
    status: Literal["sending", "sent", "failed"]
    error_message: str | None
    attempted_at: datetime


class NotificationNextOut(BaseModel):
    subscription_id: int
    subscription_name: str
    billing_date: date
    lead_days: int
    scheduled_for: date


class NotificationSchedulerStateOut(BaseModel):
    running: bool
    timezone: str = "Asia/Shanghai"
    daily_time: str = "09:00"
    next_run_at: datetime | None = None
    last_started_at: datetime | None = None
    last_completed_at: datetime | None = None
    status: str = "never"
    due_count: int = 0
    sent_count: int = 0
    failed_count: int = 0
    error_message: str | None = None


class NotificationOverviewOut(BaseModel):
    enabled: bool
    notification_days_before: list[int]
    scheduler: NotificationSchedulerStateOut
    next_reminders: list[NotificationNextOut]
    recent_deliveries: list[NotificationDeliveryOut]


CostBreakdown.model_rebuild()
