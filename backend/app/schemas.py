from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    notification_days_before: int = 7


class SettingsUpdate(BaseModel):
    server_chan_key: str | None = None
    exchange_rate_api_key: str | None = None
    notification_days_before: int | None = Field(default=None, ge=0, le=90)


class NotificationSettingsUpdate(BaseModel):
    server_chan_key: str = ""
    notification_days_before: int = Field(default=7, ge=0, le=90)


class ExchangeRateSettingsUpdate(BaseModel):
    exchange_rate_api_key: str = ""


class TestNotificationRequest(BaseModel):
    server_chan_key: str | None = None


class ExchangeQuoteRequest(BaseModel):
    api_key: str = ""
    refresh: bool = True


CostBreakdown.model_rebuild()
