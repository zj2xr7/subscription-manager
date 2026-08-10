from calendar import monthrange
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    AppSettings,
    BankCardBalance,
    BankCardCharge,
    BankCardChargeAllocation,
    Subscription,
)
from ..schemas import ChargeOut, CostBreakdown, SubscriptionCreate, SubscriptionOut, SubscriptionUpdate
from ..services.cost_calculator import calculate_cost
from ..services.bank_funds import allocate_fifo

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])


def api_key(db: Session) -> str:
    row = db.get(AppSettings, "exchange_rate_api_key")
    return row.value if row else ""


async def serialize(item: Subscription, db: Session) -> SubscriptionOut:
    cost = await calculate_cost(item.price, item.currency, item.payment_method, item.c2c_rate, api_key(db))
    if item.payment_method == "bank_card":
        required = float(cost["required_usdt"])
        allocations, shortfall = allocate_fifo(db, required)
        allocation_data = [allocation.as_dict() for allocation in allocations]
        covered = round(required - shortfall, 4)
        covered_cost = round(sum(a.usdt_amount * a.deposit.c2c_rate for a in allocations), 2)
        status = "sufficient" if shortfall == 0 else ("partial" if covered > 0 else "empty")
        cost.update({
            "covered_usdt": covered,
            "covered_cny_cost": covered_cost,
            "shortfall_usdt": shortfall,
            "coverage_status": status,
            "allocations": allocation_data,
            "cny_cost": covered_cost if status == "sufficient" else None,
            "formula": " + ".join(
                f"{a.usdt_amount:.4f} × ¥{a.deposit.c2c_rate:.4f}" for a in allocations
            ) or f"需要 {required:.4f} USDT",
        })
    output = SubscriptionOut.model_validate(item)
    return output.model_copy(update={"cost": CostBreakdown.model_validate(cost)})


@router.get("", response_model=list[SubscriptionOut])
async def list_subscriptions(db: Session = Depends(get_db)):
    items = db.scalars(select(Subscription).order_by(Subscription.next_billing_date, Subscription.name)).all()
    return [await serialize(item, db) for item in items]


@router.post("", response_model=SubscriptionOut, status_code=201)
async def create_subscription(payload: SubscriptionCreate, db: Session = Depends(get_db)):
    item = Subscription(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return await serialize(item, db)


@router.put("/{subscription_id}", response_model=SubscriptionOut)
async def update_subscription(subscription_id: int, payload: SubscriptionUpdate, db: Session = Depends(get_db)):
    item = db.get(Subscription, subscription_id)
    if item is None:
        raise HTTPException(404, "Subscription not found")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return await serialize(item, db)


@router.delete("/{subscription_id}", status_code=204)
def delete_subscription(subscription_id: int, db: Session = Depends(get_db)):
    item = db.get(Subscription, subscription_id)
    if item is None:
        raise HTTPException(404, "Subscription not found")
    db.delete(item)
    db.commit()
    return Response(status_code=204)


def advance_billing_date(item: Subscription) -> date:
    current = item.next_billing_date
    if item.billing_cycle == "monthly":
        year = current.year + (1 if current.month == 12 else 0)
        month = 1 if current.month == 12 else current.month + 1
        return current.replace(year=year, month=month, day=min(current.day, monthrange(year, month)[1]))
    if item.billing_cycle == "yearly":
        try:
            return current.replace(year=current.year + 1)
        except ValueError:
            return current.replace(year=current.year + 1, day=28)
    return current + timedelta(days=item.custom_days or 1)


@router.post("/{subscription_id}/charge", response_model=ChargeOut)
async def charge_subscription(subscription_id: int, db: Session = Depends(get_db)):
    item = db.get(Subscription, subscription_id)
    if item is None:
        raise HTTPException(404, "Subscription not found")
    cost = await calculate_cost(item.price, item.currency, item.payment_method, item.c2c_rate, api_key(db))
    charged = 0.0
    actual_cny_cost = 0.0
    allocation_data = []
    balance = db.get(BankCardBalance, 1)
    if item.payment_method == "bank_card":
        charged = float(cost["usdt_charge"])
        preview, shortfall = allocate_fifo(db, charged)
        if balance.balance + 1e-9 < charged or shortfall > 0.00005:
            raise HTTPException(409, f"Insufficient USDT balance; {charged:.4f} required")
        allocations, _ = allocate_fifo(db, charged, consume=True)
        allocation_data = [allocation.as_dict() for allocation in allocations]
        actual_cny_cost = round(sum(a.usdt_amount * a.deposit.c2c_rate for a in allocations), 2)
        previous_date = item.next_billing_date
        next_date = advance_billing_date(item)
        charge = BankCardCharge(
            kind="subscription",
            subscription_id=item.id,
            subscription_name=item.name,
            original_price=item.price,
            original_currency=item.currency,
            converted_usd=cost["converted_amount"],
            charged_usdt=charged,
            actual_cny_cost=actual_cny_cost,
            balance_before=balance.balance,
            balance_after=round(balance.balance - charged, 4),
            billing_date=previous_date,
            next_billing_date=next_date,
        )
        db.add(charge)
        db.flush()
        for allocation in allocations:
            values = allocation.as_dict()
            db.add(BankCardChargeAllocation(charge_id=charge.id, **values))
        balance.balance = round(balance.balance - charged, 4)
    item.next_billing_date = advance_billing_date(item)
    item.last_notified_date = None
    db.commit()
    return ChargeOut(
        charged_usdt=charged,
        actual_cny_cost=actual_cny_cost,
        balance=balance.balance,
        next_billing_date=item.next_billing_date,
        allocations=allocation_data,
    )
