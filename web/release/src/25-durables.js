/*
 * EcoSim V0.6 · A2 module 25: household durable stocks, wear and car vintages.
 *
 * Durable purchases are cash transfers in the goods market and add to physical
 * stocks. Wear / scrapping is physical consumption or retirement, never money
 * creation. In legacy mode (engine.durablesA2 === false) these helpers are not
 * called and the V0.6 monthly cloth/housing flows are preserved exactly.
 */
import {
  C, GOODS, clamp, subsistenceCost, zeros,
} from "./00-core.js";

function durableRealIncome(engine, budget, prices) {
  const base = Math.max(subsistenceCost(prices, engine.demandConfig), 1e-9);
  return Math.max(0.0, Math.max(0.0, Number(budget) || 0.0) / base);
}

/**
 * Soft, income-dependent stock targets. Clothes have no hard "fully clothed"
 * cutoff: both quantity (pieces) and quality grow with real income. Housing
 * targets also grow with productivity. Cars are a rich-household durable.
 */
function durableTargetsFor(engine, agent, prices, budget) {
  const isChild = !!agent.isChild;
  if (isChild) {
    return {
      cloth: C.INITIAL_CLOTH_STOCK_CHILD,
      housing: C.INITIAL_HOUSING_STOCK_CHILD,
      car: 0.0,
      quality: 1.0,
      realIncome: 0.0,
    };
  }
  const realIncome = durableRealIncome(engine, budget, prices);
  const incomeLift = Math.sqrt(Math.max(0.0, realIncome - 1.0));
  const quality = clamp(
    C.CLOTH_QUALITY_BASE + C.CLOTH_QUALITY_GAIN * Math.log2(Math.max(1.0, realIncome)),
    C.CLOTH_QUALITY_MIN,
    C.CLOTH_QUALITY_MAX,
  );
  const cloth = quality * (C.CLOTH_STOCK_BASE + C.CLOTH_STOCK_INCOME_GAIN * incomeLift);
  const productivity = clamp(Number(engine.productivityIndex) || 1.0, 0.5, 3.0);
  const productivityFactor = 1.0 + C.HOUSING_PRODUCTIVITY_WEIGHT * (productivity - 1.0);
  const housing = productivityFactor *
    (C.HOUSING_STOCK_BASE + C.HOUSING_STOCK_INCOME_GAIN * incomeLift);
  const car = clamp(
    Math.max(0.0, realIncome - C.CAR_INCOME_THRESHOLD) * C.CAR_INCOME_SLOPE,
    0.0,
    C.CAR_TARGET_MAX,
  );
  return { cloth, housing, car, quality, realIncome };
}

function assignDurableTargets(engine, agent, prices, budget) {
  const targets = durableTargetsFor(engine, agent, prices, budget);
  agent.clothTargetStock = targets.cloth;
  agent.housingTargetStock = targets.housing;
  agent.carTargetStock = targets.car;
  agent.clothQualityTarget = targets.quality;
  return targets;
}

/**
 * Physical replacement / growth purchases for this month. Clothes and
 * housing replace wear (stock / lifetime) and close the gap to the desired
 * stock over a multi-year catch-up horizon. Cars replace at target/120 plus
 * a gap catch-up term. Values are quantities of cloth, building and car.
 */
function durablePurchaseNeeds(agent, prices) {
  const clothStock = Math.max(0.0, Number(agent.cloth) || 0.0);
  const housingStock = Math.max(0.0, Number(agent.housing) || 0.0);
  const cars = Math.max(0.0, Number(agent.cars) || 0.0);
  const clothWear = clothStock * C.CLOTH_WEAR_RATE;
  const housingWear = housingStock * C.HOUSING_WEAR_RATE;
  const clothGap = Math.max(0.0, (Number(agent.clothTargetStock) || 0.0) - clothStock);
  const housingGap = Math.max(0.0, (Number(agent.housingTargetStock) || 0.0) - housingStock);
  const carTarget = Math.max(0.0, Number(agent.carTargetStock) || 0.0);
  const carGap = Math.max(0.0, carTarget - cars);
  return {
    cloth: clothWear + clothGap / C.CLOTH_STOCK_CATCHUP_MONTHS,
    building: housingWear + housingGap / C.HOUSING_STOCK_CATCHUP_MONTHS,
    car: carTarget / C.CAR_LIFETIME_MONTHS + carGap / C.CAR_CATCHUP_MONTHS,
    clothWear,
    housingWear,
  };
}

/**
 * Spendable cash for durable orders. Workers mostly use current consumption
 * budget; rich households can draw a small share of savings so cars and
 * housing upgrades are possible without creating money.
 */
function durableSpendingCap(agent) {
  const cash = Math.max(0.0, Number(agent.cash) || 0.0);
  const budget = Math.max(0.0, Number(agent.demandBudget) || 0.0);
  const drawdown = C.DURABLE_SAVINGS_DRAWDOWN *
    Math.max(0.0, cash - C.DURABLE_SAVINGS_FLOOR);
  return Math.min(cash, budget + drawdown);
}

function resetHouseholdMonth(agent) {
  if (!agent.monthPurchases) agent.monthPurchases = zeros();
  for (const good of GOODS) agent.monthPurchases[good] = 0.0;
  agent.clothWear = 0.0;
  agent.housingWear = 0.0;
  agent.housingPurchased = 0.0;
  agent.housingMaintenancePaid = 0.0;
  agent.housingNewConstruction = 0.0;
  agent.carPurchased = 0.0;
  agent.carScrapped = 0.0;
  agent.scrapGenerated = 0.0;
  agent.durableSpending = 0.0;
}

/**
 * End-of-month physical wear / car retirement. Purchases were already added
 * to stocks by Market._receiveGood, so wear is computed on pre-purchase stock
 * to avoid charging wear on goods bought in the current month. This is the
 * only place cloth/housing stock is consumed; budget shares use purchases, so
 * the same flow is never counted as both stock wear and a purchase.
 */
function applyDurableWear(engine, agent, prices) {
  const purchasedCloth = Math.max(0.0, Number(agent.monthPurchases.cloth) || 0.0);
  const purchasedHousing = Math.max(0.0, Number(agent.monthPurchases.building) || 0.0);
  const preCloth = Math.max(0.0, (Number(agent.cloth) || 0.0) - purchasedCloth);
  const preHousing = Math.max(0.0, (Number(agent.housing) || 0.0) - purchasedHousing);

  const clothWear = preCloth * C.CLOTH_WEAR_RATE;
  const housingWear = preHousing * C.HOUSING_WEAR_RATE;
  agent.cloth = Math.max(0.0, (Number(agent.cloth) || 0.0) - clothWear);
  agent.housing = Math.max(0.0, (Number(agent.housing) || 0.0) - housingWear);
  agent.clothWear = clothWear;
  agent.housingWear = housingWear;
  agent.housingPurchased = purchasedHousing;
  agent.housingMaintenancePaid = Math.min(purchasedHousing, housingWear) *
    (prices.building || 0.0);
  agent.housingNewConstruction = Math.max(0.0, purchasedHousing - housingWear);
  agent.consumedCloth = clothWear;
  agent.consumedHousing = housingWear;
  // Average quality drifts toward the income-dependent target as new clothes
  // are bought; it is a quality index, not a second physical quantity.
  const qualityTarget = Number(agent.clothQualityTarget) || 1.0;
  const totalCloth = Math.max(1e-9, (Number(agent.cloth) || 0.0) + purchasedCloth);
  const replacementShare = Math.min(1.0, purchasedCloth / totalCloth);
  agent.clothQuality = clamp(
    (Number(agent.clothQuality) || 1.0) * (1.0 - replacementShare) +
      qualityTarget * replacementShare,
    C.CLOTH_QUALITY_MIN,
    C.CLOTH_QUALITY_MAX,
  );

  // Cars retire with exact vintage age. Each retired car yields scrap steel
  // once; the household can sell that scrap on the market.
  let carScrapped = 0.0;
  let scrapGenerated = 0.0;
  if (!Array.isArray(agent.carBatches)) agent.carBatches = [];
  for (const batch of agent.carBatches) {
    batch.monthsLeft -= 1;
    if (batch.monthsLeft > 0) continue;
    const quantity = Math.max(0.0, batch.quantity || 0.0);
    if (quantity <= 1e-12) continue;
    batch.quantity = 0.0;
    carScrapped += quantity;
    scrapGenerated += quantity * C.SCRAP_PER_CAR;
  }
  agent.carBatches = agent.carBatches.filter((batch) => batch.quantity > 1e-12);
  agent.cars = agent.carBatches.reduce((sum, batch) => sum + batch.quantity, 0.0);
  agent.carScrapped = carScrapped;
  if (scrapGenerated > 1e-12) {
    agent.scrap = (Number(agent.scrap) || 0.0) + scrapGenerated;
    agent.scrapGenerated += scrapGenerated;
    engine._carRetiredThisMonth += carScrapped;
    engine._scrapGeneratedCarThisMonth += scrapGenerated;
  }
  return { clothWear, housingWear, carScrapped, scrapGenerated };
}

/**
 * Seed initial durable endowments for the historical scenarios. These are
 * physical stocks, not money; they are intentionally absent in legacy mode so
 * the Python-oracle replay is unchanged.
 */
function seedHouseholdDurables(engine) {
  const workers = Array.from(engine.workers.values())
    .sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  for (const worker of workers) {
    if (!worker.alive) continue;
    if (worker.isChild) {
      worker.cloth = C.INITIAL_CLOTH_STOCK_CHILD;
      worker.housing = C.INITIAL_HOUSING_STOCK_CHILD;
    } else {
      worker.cloth = C.INITIAL_CLOTH_STOCK_ADULT;
      worker.housing = C.INITIAL_HOUSING_STOCK_ADULT;
    }
    worker.cars = 0.0;
    worker.carBatches = [];
    worker.scrap = 0.0;
    worker.monthPurchases = zeros();
    worker.clothQuality = 1.0;
  }
  const capitalists = Array.from(engine.capitalists.values())
    .sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  let carIndex = 0;
  for (const capitalist of capitalists) {
    capitalist.cloth = C.INITIAL_CLOTH_STOCK_CAPITALIST;
    capitalist.housing = C.INITIAL_HOUSING_STOCK_CAPITALIST;
    capitalist.cars = 0.0;
    capitalist.carBatches = [];
    capitalist.scrap = 0.0;
    capitalist.monthPurchases = zeros();
    capitalist.clothQuality = 1.0;
    if (carIndex < C.INITIAL_CAR_OWNERS) {
      const age = C.INITIAL_CAR_AGE_MIN +
        ((carIndex * 37) % Math.max(1, C.INITIAL_CAR_AGE_SPAN));
      capitalist.cars = 1.0;
      capitalist.carBatches.push({
        quantity: 1.0,
        monthsLeft: Math.max(1.0, C.CAR_LIFETIME_MONTHS - age),
      });
      carIndex += 1;
    }
  }
}

export {
  durableRealIncome, durableTargetsFor, assignDurableTargets,
  durablePurchaseNeeds, durableSpendingCap, resetHouseholdMonth,
  applyDurableWear, seedHouseholdDurables,
};
