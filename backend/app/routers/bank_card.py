import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    AppSettings,
    BankCardBalance,
    BankCardCharge,
    BankCardChargeAllocation,
    BankCardDeposit,
    Subscription,
)
from ..schemas import (
    BalanceOut,
    DepositCreate,
    DepositOut,
    LotOut,
    TopUpQuoteItem,
    TopUpQuoteOut,
    TopUpQuoteRequest,
)
from ..services.cost_calculator import calculate_cost

router = APIRouter(prefix="/api/bank-card", tags=["bank-card"])


@router.get("/balance", response_model=BalanceOut)
def get_balance(db: Session = Depends(get_db)):
    return db.get(BankCardBalance, 1)


@router.post("/deposit", response_model=DepositOut, status_code=201)
def create_deposit(payload: DepositCreate, db: Session = Depends(get_db)):
    purchased = round(payload.cny_amount / payload.c2c_rate, 4)
    if purchased <= 0.01:
        raise HTTPException(422, "CNY amount must purchase more than the 0.01 USDT chain fee")
    actual_received = round(purchased - 0.01, 4)
    deposit = BankCardDeposit(
        usdt_amount=purchased,
        c2c_rate=payload.c2c_rate,
        cny_cost=round(payload.cny_amount, 2),
        chain_fee=0.01,
        actual_received=actual_received,
        remaining_usdt=actual_received,
    )
    balance = db.get(BankCardBalance, 1)
    balance.balance = round(balance.balance + actual_received, 4)
    db.add(deposit)
    db.commit()
    db.refresh(deposit)
    return deposit


@router.get("/deposits", response_model=list[DepositOut])
def list_deposits(db: Session = Depends(get_db)):
    return db.scalars(select(BankCardDeposit).order_by(BankCardDeposit.created_at.desc())).all()


@router.get("/lots", response_model=list[LotOut])
def list_lots(db: Session = Depends(get_db)):
    return db.scalars(
        select(BankCardDeposit)
        .where(BankCardDeposit.remaining_usdt > 0.00005)
        .order_by(BankCardDeposit.created_at, BankCardDeposit.id)
    ).all()


@router.post("/top-up-quote", response_model=TopUpQuoteOut)
async def top_up_quote(payload: TopUpQuoteRequest, db: Session = Depends(get_db)):
    key = db.get(AppSettings, "exchange_rate_api_key")
    api_key = key.value if key else ""
    items: list[TopUpQuoteItem] = []
    for subscription_id in payload.subscription_ids:
        subscription = db.get(Subscription, subscription_id)
        if subscription is None:
            raise HTTPException(404, f"Subscription {subscription_id} not found")
        if subscription.payment_method != "bank_card":
            raise HTTPException(422, f"Subscription {subscription_id} is not a bank-card subscription")
        cost = await calculate_cost(
            subscription.price,
            subscription.currency,
            subscription.payment_method,
            None,
            api_key,
        )
        items.append(TopUpQuoteItem(
            subscription_id=subscription.id,
            name=subscription.name,
            required_usdt=float(cost["required_usdt"]),
        ))
    required = round(sum(item.required_usdt for item in items), 4)
    balance = db.get(BankCardBalance, 1).balance
    shortfall = round(max(required - balance, 0), 4)
    purchase = round(shortfall + 0.01, 4) if shortfall > 0 else 0
    suggested_cny = math.ceil(purchase * payload.c2c_rate * 100 - 1e-9) / 100 if purchase else 0
    return TopUpQuoteOut(
        items=items,
        required_usdt=required,
        available_usdt=balance,
        shortfall_usdt=shortfall,
        suggested_purchase_usdt=purchase,
        suggested_cny_amount=suggested_cny,
    )


@router.get("/transactions")
def list_transactions(
    type: str = Query("all", pattern="^(all|deposit|charge|adjustment)$"),
    db: Session = Depends(get_db),
):
    transactions: list[dict] = []
    if type in ("all", "deposit"):
        deposits = db.scalars(select(BankCardDeposit)).all()
        transactions.extend({
            "id": f"deposit-{item.id}",
            "type": "deposit",
            "title": "C2C 充值",
            "usdt_delta": item.actual_received,
            "cny_amount": item.cny_cost,
            "c2c_rate": item.c2c_rate,
            "balance_after": None,
            "created_at": item.created_at,
            "details": {
                "purchased_usdt": item.usdt_amount,
                "chain_fee": item.chain_fee,
                "actual_received": item.actual_received,
                "remaining_usdt": item.remaining_usdt,
            },
            "allocations": [],
        } for item in deposits)
    charge_kinds = []
    if type in ("all", "charge"):
        charge_kinds.append("subscription")
    if type in ("all", "adjustment"):
        charge_kinds.append("historical_adjustment")
    if charge_kinds:
        charges = db.scalars(
            select(BankCardCharge).where(BankCardCharge.kind.in_(charge_kinds))
        ).all()
        for item in charges:
            allocations = db.scalars(
                select(BankCardChargeAllocation)
                .where(BankCardChargeAllocation.charge_id == item.id)
                .order_by(BankCardChargeAllocation.id)
            ).all()
            transactions.append({
                "id": f"charge-{item.id}",
                "type": "charge" if item.kind == "subscription" else "adjustment",
                "title": item.subscription_name,
                "usdt_delta": -item.charged_usdt,
                "cny_amount": item.actual_cny_cost,
                "c2c_rate": None,
                "balance_after": item.balance_after,
                "created_at": item.created_at,
                "details": {
                    "original_price": item.original_price,
                    "original_currency": item.original_currency,
                    "billing_date": item.billing_date,
                    "next_billing_date": item.next_billing_date,
                },
                "allocations": [{
                    "deposit_id": allocation.deposit_id,
                    "usdt_amount": allocation.usdt_amount,
                    "c2c_rate": allocation.c2c_rate,
                    "cny_cost": allocation.cny_cost,
                } for allocation in allocations],
            })
    return sorted(transactions, key=lambda item: item["created_at"], reverse=True)
