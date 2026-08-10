from dataclasses import dataclass

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
    affected_charges = [db.get(BankCardCharge, charge_id) for charge_id in direct_charge_ids]
    affected_charges = [charge for charge in affected_charges if charge is not None]

    subscription_cutoffs: dict[int, object] = {}
    for charge in affected_charges:
        if charge.kind == "subscription" and charge.subscription_id is not None:
            current = subscription_cutoffs.get(charge.subscription_id)
            if current is None or charge.created_at < current:
                subscription_cutoffs[charge.subscription_id] = charge.created_at

    affected_ids = set(direct_charge_ids)
    for subscription_id, cutoff in subscription_cutoffs.items():
        affected_ids.update(db.scalars(
            select(BankCardCharge.id).where(
                BankCardCharge.subscription_id == subscription_id,
                BankCardCharge.kind == "subscription",
                BankCardCharge.created_at >= cutoff,
            )
        ).all())

    charges = db.scalars(
        select(BankCardCharge)
        .where(BankCardCharge.id.in_(affected_ids))
        .order_by(BankCardCharge.created_at)
    ).all() if affected_ids else []
    allocations = db.scalars(
        select(BankCardChargeAllocation)
        .where(BankCardChargeAllocation.charge_id.in_(affected_ids))
        .order_by(BankCardChargeAllocation.id)
    ).all() if affected_ids else []

    for allocation in allocations:
        source = db.get(BankCardDeposit, allocation.deposit_id)
        if source is not None and source.id != deposit_id:
            source.remaining_usdt = round((source.remaining_usdt or 0) + allocation.usdt_amount, 4)

    rolled_back = 0
    for subscription_id in subscription_cutoffs:
        subscription = db.get(Subscription, subscription_id)
        related = [charge for charge in charges if charge.subscription_id == subscription_id and charge.billing_date]
        if subscription is not None and related:
            subscription.next_billing_date = min(charge.billing_date for charge in related)
            subscription.last_notified_date = None
            rolled_back += 1

    for allocation in allocations:
        db.delete(allocation)
    db.flush()
    for charge in charges:
        db.delete(charge)
    db.delete(deposit)
    db.flush()

    remaining_total = round(sum(db.scalars(select(BankCardDeposit.remaining_usdt)).all()), 4)
    balance = db.get(BankCardBalance, 1)
    balance.balance = remaining_total
    db.flush()
    return {
        "deleted_deposit_id": deposit_id,
        "deleted_charge_count": len(charges),
        "rolled_back_subscription_count": rolled_back,
        "balance": remaining_total,
    }
