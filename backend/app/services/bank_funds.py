from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    BankCardBalance,
    BankCardChargeAllocation,
    BankCardDeposit,
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
