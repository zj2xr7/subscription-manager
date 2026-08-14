from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    BankCardBalance,
    BankCardCharge,
    BankCardChargeAllocation,
    BankCardDeposit,
    BankCardPurchase,
    BankCardTransfer,
    Subscription,
)


@dataclass
class Allocation:
    deposit: BankCardDeposit
    usdt_amount: float

    def as_dict(self) -> dict:
        return {
            "deposit_id": self.deposit.id,
            "usdt_amount": round(self.usdt_amount, 4),
            "c2c_rate": round(self.deposit.c2c_rate, 4),
            "cny_cost": round(self.usdt_amount * self.deposit.c2c_rate, 2),
        }


class DepositAlreadyUsedError(ValueError):
    pass


class TransferAlreadyUsedError(ValueError):
    pass


def create_pending_purchase(db: Session, cny_amount: float, c2c_rate: float) -> BankCardPurchase:
    purchased = round(cny_amount / c2c_rate, 4)
    if purchased <= 0:
        raise ValueError("Purchase amount must be greater than zero")
    purchase = BankCardPurchase(
        cny_amount=round(cny_amount, 2),
        c2c_rate=round(c2c_rate, 4),
        purchased_usdt=purchased,
        status="pending",
    )
    db.add(purchase)
    db.flush()
    return purchase


def create_combined_transfer(
    db: Session, purchase_ids: list[int], chain_fee: float
) -> tuple[BankCardTransfer, list[BankCardDeposit]]:
    purchases = db.scalars(
        select(BankCardPurchase)
        .where(BankCardPurchase.id.in_(purchase_ids))
        .order_by(BankCardPurchase.created_at, BankCardPurchase.id)
    ).all()
    by_id = {item.id: item for item in purchases}
    if len(by_id) != len(purchase_ids):
        raise LookupError("One or more C2C purchases were not found")
    if any(item.status != "pending" for item in purchases):
        raise ValueError("Only pending C2C purchases can be transferred")

    gross = round(sum(item.purchased_usdt for item in purchases), 4)
    fee = round(chain_fee, 4)
    if gross <= fee:
        raise ValueError("Selected purchases must exceed the chain fee")

    transfer = BankCardTransfer(
        gross_usdt=gross,
        chain_fee=fee,
        actual_received=round(gross - fee, 4),
    )
    db.add(transfer)
    db.flush()

    fee_left = fee
    deposits: list[BankCardDeposit] = []
    for purchase in purchases:
        allocated_fee = round(min(purchase.purchased_usdt, fee_left), 4)
        fee_left = round(fee_left - allocated_fee, 4)
        received = round(purchase.purchased_usdt - allocated_fee, 4)
        deposit = BankCardDeposit(
            usdt_amount=purchase.purchased_usdt,
            c2c_rate=purchase.c2c_rate,
            cny_cost=purchase.cny_amount,
            chain_fee=allocated_fee,
            fee_allocated=allocated_fee,
            actual_received=received,
            remaining_usdt=received,
            purchase_id=purchase.id,
            transfer_id=transfer.id,
            created_at=transfer.created_at,
        )
        purchase.status = "transferred"
        db.add(deposit)
        deposits.append(deposit)

    balance = db.get(BankCardBalance, 1)
    balance.balance = round(balance.balance + transfer.actual_received, 4)
    db.flush()
    return transfer, deposits


def transfer_details(db: Session, transfer: BankCardTransfer) -> dict:
    deposits = db.scalars(
        select(BankCardDeposit)
        .where(BankCardDeposit.transfer_id == transfer.id)
        .order_by(BankCardDeposit.created_at, BankCardDeposit.id)
    ).all()
    used = round(sum(item.actual_received - (item.remaining_usdt or 0) for item in deposits), 4)
    has_allocations = bool(db.scalar(
        select(BankCardChargeAllocation.id)
        .where(BankCardChargeAllocation.deposit_id.in_([item.id for item in deposits] or [-1]))
        .limit(1)
    ))
    return {
        "id": transfer.id,
        "gross_usdt": transfer.gross_usdt,
        "chain_fee": transfer.chain_fee,
        "actual_received": transfer.actual_received,
        "deletable": used <= 0.00005 and not has_allocations,
        "used_usdt": used,
        "created_at": transfer.created_at,
        "items": [{
            "deposit_id": item.id,
            "purchase_id": item.purchase_id,
            "cny_amount": item.cny_cost,
            "c2c_rate": item.c2c_rate,
            "purchased_usdt": item.usdt_amount,
            "fee_allocated": item.fee_allocated or 0,
            "actual_received": item.actual_received,
            "remaining_usdt": item.remaining_usdt or 0,
        } for item in deposits],
    }


def delete_unused_transfer(db: Session, transfer_id: int) -> dict | None:
    transfer = db.get(BankCardTransfer, transfer_id)
    if transfer is None:
        return None
    details = transfer_details(db, transfer)
    if not details["deletable"]:
        raise TransferAlreadyUsedError("Used transfer records are protected and cannot be deleted")

    restored: list[int] = []
    for item in db.scalars(
        select(BankCardDeposit).where(BankCardDeposit.transfer_id == transfer_id)
    ).all():
        if item.purchase_id is not None:
            purchase = db.get(BankCardPurchase, item.purchase_id)
            if purchase is not None:
                purchase.status = "pending"
                restored.append(purchase.id)
        db.delete(item)
    db.delete(transfer)
    db.flush()
    remaining_total = round(sum(
        item or 0 for item in db.scalars(select(BankCardDeposit.remaining_usdt)).all()
    ), 4)
    db.get(BankCardBalance, 1).balance = remaining_total
    db.flush()
    return {
        "deleted_transfer_id": transfer_id,
        "restored_purchase_ids": restored,
        "balance": remaining_total,
    }


def available_lots(db: Session) -> list[BankCardDeposit]:
    return db.scalars(
        select(BankCardDeposit)
        .where(BankCardDeposit.remaining_usdt > 0.00005)
        .order_by(BankCardDeposit.created_at, BankCardDeposit.id)
    ).all()


def allocate_fifo(db: Session, required_usdt: float, consume: bool = False) -> tuple[list[Allocation], float]:
    remaining = round(required_usdt, 4)
    allocations: list[Allocation] = []
    for deposit in available_lots(db):
        used = round(min(deposit.remaining_usdt or 0, remaining), 4)
        if used <= 0:
            continue
        allocations.append(Allocation(deposit=deposit, usdt_amount=used))
        if consume:
            deposit.remaining_usdt = round((deposit.remaining_usdt or 0) - used, 4)
        remaining = round(remaining - used, 4)
        if remaining <= 0.00005:
            remaining = 0
            break
    return allocations, remaining


def delete_deposit_cascade(db: Session, deposit_id: int) -> dict | None:
    deposit = db.get(BankCardDeposit, deposit_id)
    if deposit is None:
        return None

    direct_charge_ids = set(db.scalars(
        select(BankCardChargeAllocation.charge_id)
        .where(BankCardChargeAllocation.deposit_id == deposit_id)
    ).all())
    used_usdt = round(deposit.actual_received - (deposit.remaining_usdt or 0), 4)
    if used_usdt > 0.00005 or direct_charge_ids:
        raise DepositAlreadyUsedError("Used deposit records are protected and cannot be deleted")

    db.delete(deposit)
    db.flush()

    remaining_total = round(sum(db.scalars(select(BankCardDeposit.remaining_usdt)).all()), 4)
    balance = db.get(BankCardBalance, 1)
    balance.balance = remaining_total
    db.flush()
    return {
        "deleted_deposit_id": deposit_id,
        "deleted_charge_count": 0,
        "rolled_back_subscription_count": 0,
        "balance": remaining_total,
    }


def purge_historical_adjustments(db: Session) -> dict:
    adjustments = db.scalars(
        select(BankCardCharge).where(BankCardCharge.kind == "historical_adjustment")
    ).all()
    if not adjustments:
        return {"adjustments": 0, "deposits": 0, "charges": 0, "subscriptions": 0}

    adjustment_ids = {item.id for item in adjustments}
    deposit_ids = set(db.scalars(
        select(BankCardChargeAllocation.deposit_id)
        .where(BankCardChargeAllocation.charge_id.in_(adjustment_ids))
    ).all())

    removed_charge_ids = set(adjustment_ids)
    rollback_dates: dict[int, date] = {}
    if deposit_ids:
        directly_linked = db.scalars(
            select(BankCardCharge)
            .join(BankCardChargeAllocation, BankCardChargeAllocation.charge_id == BankCardCharge.id)
            .where(
                BankCardCharge.kind == "subscription",
                BankCardChargeAllocation.deposit_id.in_(deposit_ids),
            )
        ).unique().all()
        for charge in directly_linked:
            removed_charge_ids.add(charge.id)
            if charge.subscription_id is not None and charge.billing_date is not None:
                current = rollback_dates.get(charge.subscription_id)
                rollback_dates[charge.subscription_id] = min(current, charge.billing_date) if current else charge.billing_date

        for subscription_id, rollback_date in rollback_dates.items():
            subsequent = db.scalars(
                select(BankCardCharge).where(
                    BankCardCharge.kind == "subscription",
                    BankCardCharge.subscription_id == subscription_id,
                    BankCardCharge.billing_date >= rollback_date,
                )
            ).all()
            removed_charge_ids.update(item.id for item in subsequent)

    allocations = db.scalars(
        select(BankCardChargeAllocation)
        .where(BankCardChargeAllocation.charge_id.in_(removed_charge_ids))
    ).all()
    for allocation in allocations:
        if allocation.deposit_id not in deposit_ids:
            deposit = db.get(BankCardDeposit, allocation.deposit_id)
            if deposit is not None:
                restored = round((deposit.remaining_usdt or 0) + allocation.usdt_amount, 4)
                deposit.remaining_usdt = min(round(deposit.actual_received, 4), restored)
        db.delete(allocation)

    for charge in db.scalars(
        select(BankCardCharge).where(BankCardCharge.id.in_(removed_charge_ids))
    ).all():
        db.delete(charge)
    for deposit in db.scalars(
        select(BankCardDeposit).where(BankCardDeposit.id.in_(deposit_ids))
    ).all():
        db.delete(deposit)

    for subscription_id, rollback_date in rollback_dates.items():
        subscription = db.get(Subscription, subscription_id)
        if subscription is not None:
            subscription.next_billing_date = rollback_date

    db.flush()
    remaining_total = round(sum(db.scalars(select(BankCardDeposit.remaining_usdt)).all()), 4)
    balance = db.get(BankCardBalance, 1)
    if balance is not None:
        balance.balance = remaining_total
    db.flush()
    return {
        "adjustments": len(adjustment_ids),
        "deposits": len(deposit_ids),
        "charges": len(removed_charge_ids - adjustment_ids),
        "subscriptions": len(rollback_dates),
    }
