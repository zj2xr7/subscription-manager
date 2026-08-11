from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    BankCardBalance,
    BankCardCharge,
    BankCardChargeAllocation,
    BankCardDeposit,
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
