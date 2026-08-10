from calendar import monthrange
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    AlipayCharge,
    AppSettings,
    BankCardBalance,
    BankCardCharge,
    BankCardChargeAllocation,
    Subscription,
)
from ..schemas import (
    ChargeOut,
    CostBreakdown,
    SubscriptionChargeRecordOut,
    SubscriptionCreate,
    SubscriptionOut,
    SubscriptionUpdate,
)
from ..services.cost_calculator import calculate_cost
from ..services.bank_funds import allocate_fifo
from ..services.funding_queue import build_bank_funding_queue

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])


def api_key(db: Session) -> str:
    row = db.get(AppSettings, "exchange_rate_api_key")
    return row.value if row else ""


async def serialize(item: Subscription, db: Session, bank_costs: dict[int, dict] | None = None) -> SubscriptionOut:
    if item.payment_method == "bank_card":
        if bank_costs is None:
            _, bank_costs = await build_bank_funding_queue(db, api_key(db))
        cost = bank_costs[item.id]
    else:
        cost = await calculate_cost(item.price, item.currency, item.payment_method, item.c2c_rate, api_key(db))
    output = SubscriptionOut.model_validate(item)
    return output.model_copy(update={"cost": CostBreakdown.model_validate(cost)})


@router.get("", response_model=list[SubscriptionOut])
async def list_subscriptions(db: Session = Depends(get_db)):
    items = db.scalars(select(Subscription).order_by(Subscription.next_billing_date, Subscription.name)).all()
    _, bank_costs = await build_bank_funding_queue(db, api_key(db))
    return [await serialize(item, db, bank_costs) for item in items]


@router.get("/charges", response_model=list[SubscriptionChargeRecordOut])
def list_subscription_charges(
    type: str = Query("all", pattern="^(all|alipay|bank_card)$"),
    db: Session = Depends(get_db),
):
    records = []
    if type in ("all", "alipay"):
        for charge in db.scalars(select(AlipayCharge)).all():
            records.append({
                "id": f"alipay-{charge.id}",
                "payment_method": "alipay",
                "subscription_id": charge.subscription_id,
                "subscription_name": charge.subscription_name,
                "original_price": charge.original_price,
                "original_currency": charge.original_currency,
                "conversion_rate": charge.conversion_rate,
                "cny_cost": charge.actual_cny_cost,
                "charged_usdt": None,
                "billing_date": charge.billing_date,
                "next_billing_date": charge.next_billing_date,
                "created_at": charge.created_at,
                "allocations": [],
            })
    if type in ("all", "bank_card"):
        charges = db.scalars(
            select(BankCardCharge).where(BankCardCharge.kind == "subscription")
        ).all()
        for charge in charges:
            allocations = db.scalars(
                select(BankCardChargeAllocation)
                .where(BankCardChargeAllocation.charge_id == charge.id)
                .order_by(BankCardChargeAllocation.id)
            ).all()
            records.append({
                "id": f"bank-{charge.id}",
                "payment_method": "bank_card",
                "subscription_id": charge.subscription_id,
                "subscription_name": charge.subscription_name,
                "original_price": charge.original_price,
                "original_currency": charge.original_currency,
                "conversion_rate": None,
                "cny_cost": charge.actual_cny_cost,
                "charged_usdt": charge.charged_usdt,
                "billing_date": charge.billing_date,
                "next_billing_date": charge.next_billing_date,
                "created_at": charge.created_at,
                "allocations": [{
                    "deposit_id": allocation.deposit_id,
                    "usdt_amount": allocation.usdt_amount,
                    "c2c_rate": allocation.c2c_rate,
                    "cny_cost": allocation.cny_cost,
                } for allocation in allocations],
            })
    return sorted(records, key=lambda record: record["created_at"], reverse=True)


@router.post("", response_model=SubscriptionOut, status_code=201)
async def create_subscription(payload: SubscriptionCreate, db: Session = Depends(get_db)):
    item = Subscription(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    _, bank_costs = await build_bank_funding_queue(db, api_key(db))
    return await serialize(item, db, bank_costs)


@router.put("/{subscription_id}", response_model=SubscriptionOut)
async def update_subscription(subscription_id: int, payload: SubscriptionUpdate, db: Session = Depends(get_db)):
    item = db.get(Subscription, subscription_id)
    if item is None:
        raise HTTPException(404, "Subscription not found")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    _, bank_costs = await build_bank_funding_queue(db, api_key(db))
    return await serialize(item, db, bank_costs)


@router.delete("/{subscription_id}", status_code=204)
def delete_subscription(subscription_id: int, db: Session = Depends(get_db)):
    item = db.get(Subscription, subscription_id)
    if item is None:
        raise HTTPException(404, "Subscription not found")
    db.query(BankCardCharge).filter(BankCardCharge.subscription_id == subscription_id).update(
        {BankCardCharge.subscription_id: None}, synchronize_session=False
    )
    db.query(AlipayCharge).filter(AlipayCharge.subscription_id == subscription_id).update(
        {AlipayCharge.subscription_id: None}, synchronize_session=False
    )
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
    if item.payment_method == "bank_card":
        _, bank_costs = await build_bank_funding_queue(db, api_key(db))
        cost = bank_costs[item.id]
    else:
        cost = await calculate_cost(item.price, item.currency, item.payment_method, item.c2c_rate, api_key(db))
    charged = 0.0
    actual_cny_cost = 0.0
    allocation_data = []
    balance = db.get(BankCardBalance, 1)
    previous_date = item.next_billing_date
    next_date = advance_billing_date(item)
    try:
        if item.payment_method == "bank_card":
            charged = float(cost["usdt_charge"])
            if cost["coverage_status"] != "sufficient":
                raise HTTPException(
                    409,
                    f"Insufficient USDT after earlier renewals; {cost['shortfall_usdt']:.4f} more required",
                )
            allocations, _ = allocate_fifo(db, charged, consume=True)
            allocation_data = [allocation.as_dict() for allocation in allocations]
            actual_cny_cost = round(sum(a.usdt_amount * a.deposit.c2c_rate for a in allocations), 2)
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
        else:
            actual_cny_cost = float(cost["cny_cost"])
            db.add(AlipayCharge(
                subscription_id=item.id,
                subscription_name=item.name,
                original_price=item.price,
                original_currency=item.currency,
                conversion_rate=cost["conversion_rate"],
                actual_cny_cost=actual_cny_cost,
                billing_date=previous_date,
                next_billing_date=next_date,
            ))
        item.next_billing_date = next_date
        item.last_notified_date = None
        db.commit()
    except Exception:
        db.rollback()
        raise
    return ChargeOut(
        charged_usdt=charged,
        actual_cny_cost=actual_cny_cost,
        balance=balance.balance,
        next_billing_date=item.next_billing_date,
        allocations=allocation_data,
    )
