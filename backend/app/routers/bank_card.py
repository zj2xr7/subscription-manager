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
    BankCardPurchase,
    BankCardTransfer,
    Subscription,
)
from ..schemas import (
    BalanceOut,
    DepositCreate,
    DepositDeleteOut,
    DepositOut,
    LotOut,
    PurchaseCreate,
    PurchaseOut,
    PurchaseUpdate,
    TopUpQuoteItem,
    TopUpQuoteOut,
    TopUpQuoteRequest,
    TransferCreate,
    TransferDeleteOut,
    TransferOut,
)
from ..services.bank_funds import (
    DepositAlreadyUsedError,
    TransferAlreadyUsedError,
    create_combined_transfer,
    create_pending_purchase,
    delete_deposit_cascade,
    delete_unused_transfer,
    transfer_details,
)
from ..services.funding_queue import build_bank_funding_queue

router = APIRouter(prefix="/api/bank-card", tags=["bank-card"])


@router.get("/balance", response_model=BalanceOut)
def get_balance(db: Session = Depends(get_db)):
    return db.get(BankCardBalance, 1)


@router.post("/purchases", response_model=PurchaseOut, status_code=201)
def create_purchase(payload: PurchaseCreate, db: Session = Depends(get_db)):
    try:
        purchase = create_pending_purchase(db, payload.cny_amount, payload.c2c_rate)
        db.commit()
        db.refresh(purchase)
        return purchase
    except Exception:
        db.rollback()
        raise


@router.get("/purchases", response_model=list[PurchaseOut])
def list_purchases(
    status: str = Query("pending", pattern="^(pending|transferred|all)$"),
    db: Session = Depends(get_db),
):
    statement = select(BankCardPurchase)
    if status != "all":
        statement = statement.where(BankCardPurchase.status == status)
    return db.scalars(statement.order_by(BankCardPurchase.created_at, BankCardPurchase.id)).all()


@router.put("/purchases/{purchase_id}", response_model=PurchaseOut)
def update_purchase(purchase_id: int, payload: PurchaseUpdate, db: Session = Depends(get_db)):
    purchase = db.get(BankCardPurchase, purchase_id)
    if purchase is None:
        raise HTTPException(404, "C2C purchase not found")
    if purchase.status != "pending":
        raise HTTPException(409, "Transferred C2C purchases cannot be edited")
    purchase.cny_amount = round(payload.cny_amount, 2)
    purchase.c2c_rate = round(payload.c2c_rate, 4)
    purchase.purchased_usdt = round(payload.cny_amount / payload.c2c_rate, 4)
    db.commit()
    db.refresh(purchase)
    return purchase


@router.delete("/purchases/{purchase_id}", status_code=204)
def delete_purchase(purchase_id: int, db: Session = Depends(get_db)):
    purchase = db.get(BankCardPurchase, purchase_id)
    if purchase is None:
        raise HTTPException(404, "C2C purchase not found")
    if purchase.status != "pending":
        raise HTTPException(409, "Transferred C2C purchases cannot be deleted")
    db.delete(purchase)
    db.commit()


@router.post("/transfers", response_model=TransferOut, status_code=201)
def create_transfer(payload: TransferCreate, db: Session = Depends(get_db)):
    try:
        transfer, _deposits = create_combined_transfer(db, payload.purchase_ids, payload.chain_fee)
        result = transfer_details(db, transfer)
        db.commit()
        return result
    except LookupError as exc:
        db.rollback()
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get("/transfers", response_model=list[TransferOut])
def list_transfers(db: Session = Depends(get_db)):
    transfers = db.scalars(
        select(BankCardTransfer).order_by(BankCardTransfer.created_at.desc(), BankCardTransfer.id.desc())
    ).all()
    return [transfer_details(db, item) for item in transfers]


@router.delete("/transfers/{transfer_id}", response_model=TransferDeleteOut)
def delete_transfer(transfer_id: int, db: Session = Depends(get_db)):
    try:
        result = delete_unused_transfer(db, transfer_id)
        if result is None:
            raise HTTPException(404, "Transfer not found")
        db.commit()
        return result
    except HTTPException:
        db.rollback()
        raise
    except TransferAlreadyUsedError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.post("/deposit", response_model=DepositOut, status_code=201)
def create_deposit(payload: DepositCreate, db: Session = Depends(get_db)):
    """Compatibility endpoint: create one purchase and withdraw it immediately."""
    try:
        purchase = create_pending_purchase(db, payload.cny_amount, payload.c2c_rate)
        if purchase.purchased_usdt <= 0.01:
            raise ValueError("CNY amount must purchase more than the 0.01 USDT chain fee")
        _transfer, deposits = create_combined_transfer(db, [purchase.id], 0.01)
        db.commit()
        db.refresh(deposits[0])
        return deposits[0]
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get("/deposits", response_model=list[DepositOut])
def list_deposits(db: Session = Depends(get_db)):
    return db.scalars(select(BankCardDeposit).order_by(BankCardDeposit.created_at.desc())).all()


@router.delete("/deposits/{deposit_id}", response_model=DepositDeleteOut)
def delete_deposit(deposit_id: int, db: Session = Depends(get_db)):
    try:
        deposit = db.get(BankCardDeposit, deposit_id)
        if deposit is not None and deposit.transfer_id is not None:
            raise HTTPException(409, "Delete the complete transfer instead of an individual transfer lot")
        result = delete_deposit_cascade(db, deposit_id)
        if result is None:
            raise HTTPException(404, "Deposit not found")
        db.commit()
        return result
    except HTTPException:
        db.rollback()
        raise
    except DepositAlreadyUsedError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get("/lots", response_model=list[LotOut])
def list_lots(db: Session = Depends(get_db)):
    return db.scalars(
        select(BankCardDeposit)
        .where(BankCardDeposit.remaining_usdt > 0.00005)
        .order_by(BankCardDeposit.created_at, BankCardDeposit.id)
    ).all()


@router.post("/top-up-quote", response_model=TopUpQuoteOut)
async def top_up_quote(payload: TopUpQuoteRequest, db: Session = Depends(get_db)):
    selected_ids = set(payload.subscription_ids)
    for subscription_id in selected_ids:
        subscription = db.get(Subscription, subscription_id)
        if subscription is None:
            raise HTTPException(404, f"Subscription {subscription_id} not found")
        if subscription.payment_method != "bank_card":
            raise HTTPException(422, f"Subscription {subscription_id} is not a bank-card subscription")

    key = db.get(AppSettings, "exchange_rate_api_key")
    ordered, funding = await build_bank_funding_queue(db, key.value if key else "")
    selected = [item for item in ordered if item.id in selected_ids]
    items = [TopUpQuoteItem(
        subscription_id=item.id,
        name=item.name,
        required_usdt=float(funding[item.id]["required_usdt"]),
    ) for item in selected]
    required = round(sum(item.required_usdt for item in items), 4)
    covered = round(sum(funding[item.id]["covered_usdt"] for item in selected), 4)
    shortfall = round(sum(funding[item.id]["shortfall_usdt"] for item in selected), 4)
    last_position = max((funding[item.id]["queue_position"] for item in selected), default=0)
    reserved = round(sum(
        funding[item.id]["covered_usdt"] for item in ordered
        if item.id not in selected_ids and funding[item.id]["queue_position"] <= last_position
    ), 4)
    balance = db.get(BankCardBalance, 1).balance
    pending = round(sum(db.scalars(
        select(BankCardPurchase.purchased_usdt).where(BankCardPurchase.status == "pending")
    ).all()), 4)
    fee = round(payload.chain_fee, 4) if shortfall > 0 else 0
    gross_needed = round(shortfall + fee, 4) if shortfall > 0 else 0
    additional = round(max(gross_needed - pending, 0), 4)
    suggested_cny = math.ceil(additional * payload.c2c_rate * 100 - 1e-9) / 100 if additional else 0
    return TopUpQuoteOut(
        items=items,
        required_usdt=required,
        available_usdt=balance,
        reserved_usdt=reserved,
        covered_usdt=covered,
        shortfall_usdt=shortfall,
        pending_usdt=pending,
        transfer_fee=fee,
        additional_purchase_usdt=additional,
        suggested_purchase_usdt=additional,
        suggested_cny_amount=suggested_cny,
    )


@router.get("/transactions")
def list_transactions(
    type: str = Query("all", pattern="^(all|deposit|charge)$"),
    db: Session = Depends(get_db),
):
    transactions: list[dict] = []
    if type in ("all", "deposit"):
        transfers = db.scalars(select(BankCardTransfer)).all()
        for transfer in transfers:
            details = transfer_details(db, transfer)
            transactions.append({
                "id": f"transfer-{transfer.id}",
                "transfer_id": transfer.id,
                "type": "deposit",
                "title": "USDT 提链到账",
                "usdt_delta": transfer.actual_received,
                "cny_amount": round(sum(item["cny_amount"] for item in details["items"]), 2),
                "c2c_rate": None,
                "balance_after": None,
                "created_at": transfer.created_at,
                "used_usdt": details["used_usdt"],
                "related_charge_count": 0 if details["deletable"] else 1,
                "deletable": details["deletable"],
                "details": {
                    "purchased_usdt": transfer.gross_usdt,
                    "chain_fee": transfer.chain_fee,
                    "actual_received": transfer.actual_received,
                    "remaining_usdt": round(sum(item["remaining_usdt"] for item in details["items"]), 4),
                    "items": details["items"],
                },
                "allocations": [],
            })
    if type in ("all", "charge"):
        charges = db.scalars(
            select(BankCardCharge).where(BankCardCharge.kind == "subscription")
        ).all()
        for item in charges:
            allocations = db.scalars(
                select(BankCardChargeAllocation)
                .where(BankCardChargeAllocation.charge_id == item.id)
                .order_by(BankCardChargeAllocation.id)
            ).all()
            transactions.append({
                "id": f"charge-{item.id}",
                "type": "charge",
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
