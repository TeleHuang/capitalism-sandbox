from __future__ import annotations

from typing import TYPE_CHECKING

from .config import (
    INVESTMENT_HURDLE,
    LAND_PRICE_STEP,
    LAND_RESERVATION_PRICE,
    LAND_SALES_PER_TICK,
    MIN_CAPITALIST_FARM_MU,
    SECTOR_PARAMS,
    TARGET_CAPITALIST_FARM_MU,
)
from .decisions import agricultural_entry_roi, best_equipment_choice
from .enums import Industry

if TYPE_CHECKING:
    from .engine import Engine


def run_land_market(engine: "Engine") -> None:
    """Central land market.

    Capitalist farms bid for land; smallholders sell whole 10-mu plots when the
    price is above their reservation price.  This is the mechanism that lets
    agricultural enterprises appear and consolidate land.  Without it,
    agriculture remains a subsistence sector and farm machinery has no buyer.
    """
    land = engine.land
    if land.total_land <= 0:
        return

    demand: list[tuple[object, float, bool]] = []  # (buyer, mu, is_new_entrant)

    # Existing capitalist farms expand.
    for ent in engine.enterprises.values():
        if not ent.active or ent.industry != Industry.AGRICULTURE:
            continue
        if ent.is_household or not ent.modernization_capable:
            continue
        if ent.land >= TARGET_CAPITALIST_FARM_MU:
            continue
        key, roi = best_equipment_choice(engine, Industry.AGRICULTURE) or ("farm_machinery", -1.0)
        if roi < INVESTMENT_HURDLE:
            continue
        want = min(TARGET_CAPITALIST_FARM_MU - ent.land, 50.0)
        owner = engine.capitalists.get(ent.owner_id)
        available = ent.cash + (owner.cash if owner is not None else 0.0)
        if available >= want * land.price * 0.5:
            demand.append((ent, want, False))

    # New entrants.  Limit the number per month so land demand is not a single
    # coordinated shock.
    ag_roi = agricultural_entry_roi(engine)[1]
    if ag_roi >= INVESTMENT_HURDLE:
        entrants = [
            c
            for c in engine.capitalists.values()
            if c.cash >= MIN_CAPITALIST_FARM_MU * land.price
            and not any(
                e.active and e.owner_id == c.id and e.industry == Industry.AGRICULTURE
                for e in engine.enterprises.values()
            )
        ]
        entrants.sort(key=lambda c: c.id)
        for capitalist in entrants[:2]:
            demand.append((capitalist, TARGET_CAPITALIST_FARM_MU, True))

    if not demand:
        land.price = max(20.0, land.price * (1.0 - 0.02))
        return

    # Supply: smallholders sell whole plots, but only a fraction per month.
    supply = 0.0
    sellers: list[str] = []
    if land.price >= LAND_RESERVATION_PRICE:
        max_supply = land.smallholder_land * LAND_SALES_PER_TICK
        for worker_id in sorted(land.owners):
            if max_supply <= 0:
                break
            mu = land.owners[worker_id]
            if mu <= 0:
                continue
            supply += mu
            sellers.append(worker_id)
            max_supply -= mu

    total_demand = sum(mu for _, mu, _ in demand)
    traded = min(total_demand, supply)

    # Allocate land to buyers in order.
    remaining_supply = traded
    for buyer, want, is_new in demand:
        if remaining_supply <= 0:
            break
        mu = min(want, remaining_supply)
        if is_new and mu < MIN_CAPITALIST_FARM_MU:
            continue
        if mu <= 0:
            continue
        # Pay the first sellers in order.  A seller is whole-plot only.
        paid = 0.0
        while mu > 1e-9 and sellers:
            seller_id = sellers[0]
            seller_mu = land.owners[seller_id]
            if seller_mu <= 0:
                sellers.pop(0)
                continue
            seller_ent = engine.enterprises.get(land.enterprise_by_owner.get(seller_id, ""))
            price = land.price

            if is_new:
                capitalist = buyer
                if capitalist.cash < seller_mu * price:
                    break
                capitalist.cash -= seller_mu * price
                engine.workers[seller_id].cash += seller_mu * price
                land.owners[seller_id] = 0.0
                sellers.pop(0)
                _remove_smallholder(engine, seller_id)
                engine.create_agricultural_enterprise(capitalist, seller_mu, price)
                mu -= seller_mu
                remaining_supply -= seller_mu
                paid += seller_mu
                # A new entrant gets one plot and then becomes an existing farm
                # for future expansions.
                is_new = False
                buyer = next(
                    e
                    for e in engine.enterprises.values()
                    if e.owner_id == capitalist.id
                    and e.industry == Industry.AGRICULTURE
                    and e.active
                )
            else:
                ent = buyer
                owner = engine.capitalists.get(ent.owner_id)
                payer_cash = owner.cash if owner is not None else ent.cash
                if payer_cash < seller_mu * price:
                    break
                if owner is not None:
                    owner.cash -= seller_mu * price
                else:
                    ent.cash -= seller_mu * price
                engine.workers[seller_id].cash += seller_mu * price
                ent.land += seller_mu
                land.owners[seller_id] = 0.0
                sellers.pop(0)
                _remove_smallholder(engine, seller_id)
                mu -= seller_mu
                remaining_supply -= seller_mu
                paid += seller_mu

    imbalance = (total_demand - supply) / max(total_demand, supply, 1.0)
    imbalance = max(-1.0, min(1.0, imbalance))
    land.price = max(20.0, land.price * (1.0 + LAND_PRICE_STEP * imbalance))


def _remove_smallholder(engine: "Engine", worker_id: str) -> None:
    """Close a sold-out smallholding and turn the owner into a landless worker."""
    worker = engine.workers[worker_id]
    worker.land_owned = 0.0
    worker.is_owner_operator = False
    worker.employer_id = None
    ent_id = engine.land.enterprise_by_owner.pop(worker_id, None)
    if not ent_id:
        return
    ent = engine.enterprises.get(ent_id)
    if not ent:
        return
    # Household assets return to the owner; goods stay in the worker's pantry.
    worker.cash += max(0.0, ent.cash)
    worker.food += max(0.0, ent.inv(SECTOR_PARAMS[ent.industry].output))
    ent.cash = 0.0
    ent.active = False
    ent.workers.clear()
