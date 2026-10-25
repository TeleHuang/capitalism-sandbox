/*
 * EcoSim V0.6 · engine source — module 35: central land market and the
 * smallholder exit path. A2 adds consolidated 200-mu farms and surplus small-
 * machinery scrapping while keeping the land market / estate path intact.
 */
import { C, EQUIPMENT, SECTOR_PARAMS } from "./00-core.js";
import { retireEquipmentUnits } from "./10-models.js";
import { bestEquipmentChoice, agriculturalEntryRoi } from "./20-decisions.js";

function farmMaxPower(enterprise) {
  let maxPower = 0.0;
  for (const [key, count] of enterprise.equipment) {
    if (count <= 1e-9 || !key.startsWith("farm_")) continue;
    const et = EQUIPMENT.get(key);
    if (et) maxPower = Math.max(maxPower, et.power);
  }
  return maxPower;
}

/**
 * Mechanised capitalist farms may consolidate up to 200 mu once they own a
 * super-large (>=4x power) machine. The 2^N law is unchanged: larger machines
 * still only raise land managed per worker, not yield per mu.
 */
function farmTargetLand(enterprise) {
  if (farmMaxPower(enterprise) + 1e-9 >= C.CONSOLIDATION_MIN_POWER) {
    return Math.max(C.TARGET_CAPITALIST_FARM_MU, C.CONSOLIDATED_FARM_MU);
  }
  return C.TARGET_CAPITALIST_FARM_MU;
}

function sellIdleFarmEquipment(engine) {
  if (!engine.durablesA2) return;
  for (const enterprise of engine.enterprises.values()) {
    if (!enterprise.active || enterprise.industry !== "agriculture" ||
        enterprise.isHousehold || enterprise.land < C.FARM_IDLE_MIN_LAND) continue;
    const units = [];
    let totalPower = 0.0;
    let maxPower = 0.0;
    for (const [key, count] of enterprise.equipment) {
      if (count <= 1e-9 || !key.startsWith("farm_")) continue;
      const et = EQUIPMENT.get(key);
      if (!et) continue;
      units.push({ key, count, power: et.power });
      totalPower += et.power * count;
      maxPower = Math.max(maxPower, et.power);
    }
    if (units.length <= 1 || maxPower + 1e-9 < C.CONSOLIDATION_MIN_POWER) continue;
    units.sort((a, b) => (a.power - b.power) || (a.key < b.key ? -1 : a.key > b.key ? 1 : 0));
    const smallest = units[0];
    if (smallest.power + 1e-9 >= maxPower) continue;
    // Keep enough power to remain a consolidated farm; retire one surplus
    // small machine per month and sell its scrap through the market.
    if (totalPower - smallest.power + 1e-9 < C.CONSOLIDATION_MIN_POWER) continue;
    const result = retireEquipmentUnits(enterprise, smallest.key, 1.0);
    if (result.units > 0) {
      enterprise.idleEquipmentSold += result.units;
      engine._idleEquipmentScrappedThisMonth += result.units;
      engine._equipmentRetiredThisMonth += result.units;
      engine._scrapGeneratedEquipmentThisMonth += result.scrap;
    }
  }
}

function runLandMarket(engine) {
  const land = engine.land;
  if (land.totalLand <= 0) return;

  const demand = []; // { buyer, want, isNew }
  for (const enterprise of engine.enterprises.values()) {
    if (!enterprise.active || enterprise.industry !== "agriculture") continue;
    if (enterprise.isHousehold || !enterprise.modernizationCapable) continue;
    const targetLand = farmTargetLand(enterprise);
    if (enterprise.land >= targetLand) continue;
    const choice = bestEquipmentChoice(engine, "agriculture") || { key: "farm_t0", roi: -1.0 };
    if (choice.roi < C.INVESTMENT_HURDLE) continue;
    const want = Math.min(targetLand - enterprise.land, 50.0);
    const owner = engine.capitalists.get(enterprise.ownerId);
    const available = enterprise.cash + (owner ? owner.cash : 0.0);
    if (available >= want * land.price * 0.5) {
      demand.push({ buyer: enterprise, want, isNew: false });
    }
  }

  const agRoi = agriculturalEntryRoi(engine).roi;
  if (agRoi >= C.INVESTMENT_HURDLE) {
    const entrants = [];
    for (const capitalist of engine.capitalists.values()) {
      if (capitalist.cash < C.MIN_CAPITALIST_FARM_MU * land.price) continue;
      let ownsFarm = false;
      for (const enterprise of engine.enterprises.values()) {
        if (enterprise.active && enterprise.ownerId === capitalist.id &&
            enterprise.industry === "agriculture") {
          ownsFarm = true;
          break;
        }
      }
      if (!ownsFarm) entrants.push(capitalist);
    }
    entrants.sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
    for (const capitalist of entrants.slice(0, 2)) {
      demand.push({ buyer: capitalist, want: C.TARGET_CAPITALIST_FARM_MU, isNew: true });
    }
  }

  if (!demand.length) {
    land.price = Math.max(20.0, land.price * 0.98);
    sellIdleFarmEquipment(engine);
    return;
  }

  let supply = 0.0;
  const sellers = [];
  if (land.price >= C.LAND_RESERVATION_PRICE) {
    let maxSupply = land.smallholderLand * C.LAND_SALES_PER_TICK;
    const ownerIds = Array.from(land.owners.keys()).sort();
    for (const workerId of ownerIds) {
      if (maxSupply <= 0) break;
      const mu = land.owners.get(workerId) || 0.0;
      if (mu <= 0) continue;
      supply += mu;
      sellers.push(workerId);
      maxSupply -= mu;
    }
  }

  const totalDemand = demand.reduce((sum, entry) => sum + entry.want, 0.0);
  const traded = Math.min(totalDemand, supply);
  let remainingSupply = traded;

  for (const entry of demand) {
    if (remainingSupply <= 0) break;
    let { buyer, isNew } = entry;
    let mu = Math.min(entry.want, remainingSupply);
    if (isNew && mu < C.MIN_CAPITALIST_FARM_MU) continue;
    if (mu <= 0) continue;
    while (mu > 1e-9 && sellers.length) {
      const sellerId = sellers[0];
      const sellerMu = land.owners.get(sellerId) || 0.0;
      if (sellerMu <= 0) { sellers.shift(); continue; }
      const price = land.price;
      if (isNew) {
        const capitalist = buyer;
        if (capitalist.cash < sellerMu * price) break;
        capitalist.cash -= sellerMu * price;
        engine.workers.get(sellerId).cash += sellerMu * price;
        land.owners.set(sellerId, 0.0);
        sellers.shift();
        removeSmallholder(engine, sellerId);
        engine.createAgriculturalEnterprise(capitalist, sellerMu, price);
        mu -= sellerMu;
        remainingSupply -= sellerMu;
        isNew = false;
        for (const enterprise of engine.enterprises.values()) {
          if (enterprise.ownerId === capitalist.id &&
              enterprise.industry === "agriculture" && enterprise.active) {
            buyer = enterprise;
            break;
          }
        }
      } else {
        const enterprise = buyer;
        const owner = engine.capitalists.get(enterprise.ownerId);
        const payerCash = owner ? owner.cash : enterprise.cash;
        if (payerCash < sellerMu * price) break;
        if (owner) owner.cash -= sellerMu * price;
        else enterprise.cash -= sellerMu * price;
        engine.workers.get(sellerId).cash += sellerMu * price;
        enterprise.land += sellerMu;
        land.owners.set(sellerId, 0.0);
        sellers.shift();
        removeSmallholder(engine, sellerId);
        mu -= sellerMu;
        remainingSupply -= sellerMu;
      }
    }
  }

  let imbalance = (totalDemand - supply) / Math.max(totalDemand, supply, 1.0);
  imbalance = Math.max(-1.0, Math.min(1.0, imbalance));
  land.price = Math.max(20.0, land.price * (1.0 + C.LAND_PRICE_STEP * imbalance));
  sellIdleFarmEquipment(engine);
}

function removeSmallholder(engine, workerId) {
  const worker = engine.workers.get(workerId);
  worker.landOwned = 0.0;
  worker.isOwnerOperator = false;
  worker.employerId = null;
  const entId = landEnterpriseByOwner(engine, workerId);
  if (!entId) return;
  const enterprise = engine.enterprises.get(entId);
  if (!enterprise) return;
  worker.cash += Math.max(0.0, enterprise.cash);
  worker.food += Math.max(0.0, enterprise.inv(SECTOR_PARAMS.get(enterprise.industry).output));
  enterprise.cash = 0.0;
  enterprise.active = false;
  enterprise.workers.length = 0;
}

function landEnterpriseByOwner(engine, workerId) {
  const entId = engine.land.enterpriseByOwner.get(workerId);
  engine.land.enterpriseByOwner.delete(workerId);
  return entId;
}

export {
  runLandMarket, removeSmallholder, farmMaxPower, farmTargetLand,
  sellIdleFarmEquipment,
};
