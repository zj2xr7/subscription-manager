from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Subscription
from .bank_funds import Allocation, available_lots
from .cost_calculator import calculate_cost
from .exchange_rate import exchange_rate_service


@dataclass
class QueueFunding:
    queue_position: int
    reserved_before_usdt: float
    available_for_charge_usdt: float
    covered_usdt: float
    shortfall_usdt: float
    allocations: list[Allocation]


def simulate_funding_queue(lots, ordered_requirements: list[tuple[int, float]]) -> dict[int, QueueFunding]:
    remaining_by_lot = {lot.id: round(lot.remaining_usdt or 0, 4) for lot in lots}
    initial_balance = round(sum(remaining_by_lot.values()), 4)
    results: dict[int, QueueFunding] = {}

    for position, (subscription_id, required_usdt) in enumerate(ordered_requirements, start=1):
        reserved_before = round(initial_balance - sum(remaining_by_lot.values()), 4)
        available_before = round(sum(remaining_by_lot.values()), 4)
        remaining = round(required_usdt, 4)
        allocations: list[Allocation] = []
        for lot in lots:
            used = round(min(remaining_by_lot[lot.id], remaining), 4)
            if used <= 0:
                continue
            allocations.append(Allocation(deposit=lot, usdt_amount=used))
            remaining_by_lot[lot.id] = round(remaining_by_lot[lot.id] - used, 4)
            remaining = round(remaining - used, 4)
            if remaining <= 0.00005:
                remaining = 0
                break
        covered = round(required_usdt - remaining, 4)
        results[subscription_id] = QueueFunding(
            queue_position=position,
            reserved_before_usdt=reserved_before,
            available_for_charge_usdt=available_before,
            covered_usdt=covered,
            shortfall_usdt=remaining,
            allocations=allocations,
        )
    return results


async def build_bank_funding_queue(db: Session, api_key: str = "") -> tuple[list[Subscription], dict[int, dict]]:
    subscriptions = db.scalars(
        select(Subscription)
        .where(Subscription.payment_method == "bank_card")
        .order_by(Subscription.next_billing_date, Subscription.id)
    ).all()
    costs = {}
    requirements = []
    for item in subscriptions:
        cost = await calculate_cost(item.price, item.currency, item.payment_method, item.c2c_rate, api_key)
        costs[item.id] = cost
        requirements.append((item.id, float(cost["required_usdt"])))

    if not subscriptions:
        return subscriptions, {}

    funding = simulate_funding_queue(available_lots(db), requirements)
    estimate_quotes = await exchange_rate_service.cny_quotes(api_key)
    estimate_rate = float(estimate_quotes["quotes"]["USD"])
    results = {}
    for item in subscriptions:
        cost = costs[item.id]
        queued = funding[item.id]
        allocations = [allocation.as_dict() for allocation in queued.allocations]
        covered_cost = round(sum(allocation.usdt_amount * allocation.deposit.c2c_rate for allocation in queued.allocations), 2)
        status = "sufficient" if queued.shortfall_usdt == 0 else ("partial" if queued.covered_usdt > 0 else "empty")
        estimated_cost = covered_cost if status == "sufficient" else round(
            covered_cost + queued.shortfall_usdt * estimate_rate, 2
        )
        results[item.id] = {
            **cost,
            "queue_position": queued.queue_position,
            "reserved_before_usdt": queued.reserved_before_usdt,
            "available_for_charge_usdt": queued.available_for_charge_usdt,
            "covered_usdt": queued.covered_usdt,
            "covered_cny_cost": covered_cost,
            "shortfall_usdt": queued.shortfall_usdt,
            "coverage_status": status,
            "allocations": allocations,
            "cny_cost": covered_cost if status == "sufficient" else None,
            "estimated_cny_cost": estimated_cost,
            "estimate_cny_rate": None if status == "sufficient" else estimate_rate,
            "estimate_source": "fifo" if status == "sufficient" else estimate_quotes["source"],
            "formula": " + ".join(
                f"{allocation.usdt_amount:.4f} × ¥{allocation.deposit.c2c_rate:.4f}"
                for allocation in queued.allocations
            ) or f"需要 {cost['required_usdt']:.4f} USDT",
        }
    return subscriptions, results
