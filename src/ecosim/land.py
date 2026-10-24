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
    """中央土地市场。

    资本主义农场竞价买地；自耕农在地价高于保留价时出售整块 10 亩地。
    这是让农业企业出现并整合土地的机制。没有它，农业会停留在糊口部门，
    农机也没有买家。
    """
    land = engine.land
    if land.total_land <= 0:
        return

    demand: list[tuple[object, float, bool]] = []  # （买方，亩数，是否新进入者）

    # 现有资本主义农场扩张。
    for ent in engine.enterprises.values():
        if not ent.active or ent.industry != Industry.AGRICULTURE:
            continue
        if ent.is_household or not ent.modernization_capable:
            continue
        if ent.land >= TARGET_CAPITALIST_FARM_MU:
            continue
        key, roi = best_equipment_choice(engine, Industry.AGRICULTURE) or ("farm_t0", -1.0)
        if roi < INVESTMENT_HURDLE:
            continue
        want = min(TARGET_CAPITALIST_FARM_MU - ent.land, 50.0)
        owner = engine.capitalists.get(ent.owner_id)
        available = ent.cash + (owner.cash if owner is not None else 0.0)
        if available >= want * land.price * 0.5:
            demand.append((ent, want, False))

    # 新进入者。限制每月数量，避免土地需求一次性
    # 形成协调冲击。
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

    # 供给：自耕农整块出售，但每月只卖一小部分。
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

    # 按顺序把土地分配给买方。
    remaining_supply = traded
    for buyer, want, is_new in demand:
        if remaining_supply <= 0:
            break
        mu = min(want, remaining_supply)
        if is_new and mu < MIN_CAPITALIST_FARM_MU:
            continue
        if mu <= 0:
            continue
        # 按顺序向最先的卖方付款。卖方只卖整块地。
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
                # 新进入者先获得一块地，之后作为现有农场
                # 继续扩张。
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
    """关闭已卖光的自耕农农场，把所有者变成无地工人。"""
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
    # 家庭资产归还所有者；粮食留在工人的存粮里。
    worker.cash += max(0.0, ent.cash)
    worker.food += max(0.0, ent.inv(SECTOR_PARAMS[ent.industry].output))
    ent.cash = 0.0
    ent.active = False
    ent.workers.clear()
