/*
 * EcoSim V0.6 · engine source — module 20: firm decisions, wage rule and the
 * free cost-plus price regime.
 */
import {
  C, EQUIPMENT, SECTOR_PARAMS, INITIAL_PRICES, round2,
} from "./00-core.js";
import {
  equipmentValue, capacityAtSkillOne, desiredWorkers, farmRequirements,
  unitCost, equipmentCost, representativeRoi, averageSkill,
  plannedInputRatios,
} from "./10-models.js";

  // Python decisions.subsistence_cost is the legacy *fixed* basket:
  // 0.1 t food + 1 cloth + 0.2 m2 housing. The V0.6 demand module has its own
  // Stone-Geary subsistence cost; keep both under distinct names.
  function wageSubsistenceCost(prices) {
    return 0.1 * (prices.food || 100.0) +
      (prices.cloth || 1.0) +
      0.2 * (prices.building || 10.0);
  }
  function wageFloor(prices) {
    const raw = Math.max(C.WAGE_BASE, wageSubsistenceCost(prices) * 1.1);
    return Math.min(raw, C.WAGE_BASE * 5.0);
  }
  function shouldSwitch(currentWage, bestOffer, threshold) {
    const limit = threshold === undefined ? C.WAGE_SWITCH_THRESHOLD : threshold;
    return bestOffer > currentWage * (1.0 + limit);
  }

  function normalUnitCost(engine, enterprise, prices, workers) {
    prices = prices || engine.market.referencePrices;
    workers = workers || engine.enterpriseWorkers(enterprise);
    const params = SECTOR_PARAMS.get(enterprise.industry);
    const skill = workers.length ? Math.max(1.0, averageSkill(workers)) : 1.0;

    if (enterprise.industry === "agriculture") {
      if (enterprise.land <= 0) return 0.0;
      let output = enterprise.land * C.BASE_GRAIN_YIELD * skill;
      if (enterprise.useFertilizer) output *= C.FERTILIZER_YIELD_MULTIPLIER;
      if (output <= 1e-9) return 0.0;
      const required = Math.max(1, farmRequirements(enterprise).required);
      let ownerCount = 0;
      if (enterprise.isHousehold) {
        for (const worker of workers) {
          if (engine._isHouseholdFarmOwner(enterprise, worker)) ownerCount += 1;
        }
      }
      const employeeCount = Math.max(0, required - ownerCount);
      const employeeWages = workers.filter((worker) => worker.wage > 0).map((worker) => worker.wage);
      const employeeRate = employeeWages.length
        ? employeeWages.reduce((a, b) => a + b, 0) / employeeWages.length
        : engine.averageWage();
      const wageBill = ownerCount * C.WAGE_BASE + employeeCount * employeeRate;
      let inputCost = 0.0;
      if (enterprise.useFertilizer) {
        inputCost = enterprise.land * C.FERTILIZER_PER_MU * (prices.fertilizer || 0.0);
      }
      const depreciation = equipmentValue(enterprise, prices) / C.DEPRECIATION_MONTHS;
      return (wageBill + inputCost + depreciation) / output;
    }

    const capacity = capacityAtSkillOne(enterprise);
    if (capacity <= 0) return 0.0;
    const output = capacity * skill;
    const required = desiredWorkers(enterprise, 1.0);
    if (required <= 0 || output <= 1e-9) return 0.0;
    const employeeWages = workers.filter((worker) => worker.wage > 0).map((worker) => worker.wage);
    const wageRate = employeeWages.length
      ? employeeWages.reduce((a, b) => a + b, 0) / employeeWages.length
      : engine.averageWage();
    const wageBill = required * wageRate;
    let inputCost = 0.0;
    const inputRatios = plannedInputRatios(engine, enterprise, prices);
    for (const good of Object.keys(inputRatios)) {
      inputCost += inputRatios[good] * output * (prices[good] || 0.0);
    }
    const depreciation = equipmentValue(enterprise, prices) / C.DEPRECIATION_MONTHS;
    return (wageBill + inputCost + depreciation) / output;
  }

  function pricingUnitCost(engine, enterprise, prices, workers) {
    prices = prices || engine.market.referencePrices;
    workers = workers || engine.enterpriseWorkers(enterprise);
    let cost = unitCost(enterprise, prices, workers);
    if (enterprise.isHousehold && enterprise.industry === "agriculture" &&
        enterprise.lastOutput > 1e-9) {
      let ownerLabor = 0.0;
      for (const worker of workers) {
        if (engine._isHouseholdFarmOwner(enterprise, worker)) ownerLabor += worker.effectiveLabor;
      }
      if (ownerLabor > 0) cost += ownerLabor * C.WAGE_BASE / enterprise.lastOutput;
    }
    return cost;
  }

  function wageTarget(engine, enterprise) {
    const productivity = Math.max(1e-9, engine.productivityIndex ?? 1.0);
    const share = Math.max(0.0, engine.wageProductivityShare ?? 0.5);
    const expectedInflation = engine.inflationExpectations ?? 0.0;
    const passThrough = engine.wageInflationPassThrough ?? C.WAGE_INFLATION_PASS_THROUGH;

    let unemployment = engine._wageUnemployment;
    if (unemployment === null || unemployment === undefined) {
      const laborForce = engine.laborForceWorkers();
      const employed = laborForce.filter((worker) => worker.employed).length;
      unemployment = 1.0 - employed / Math.max(1, laborForce.length);
    }
    let tightness = C.WAGE_TIGHTNESS_SLOPE * (0.07 - unemployment);
    if (enterprise.lastRevenue > 0 && enterprise.lastProfit > 0) {
      const margin = Math.max(0.0, Math.min(0.35, enterprise.lastProfit / enterprise.lastRevenue));
      tightness += C.WAGE_PROFIT_SLOPE * margin;
    }

    const cpi = Math.max(1e-6, engine.cpi ?? 1.0);
    const wageIndex = Math.max(0.0, engine.wageIndex ?? 1.0);
    const realWageIndex = wageIndex / cpi;
    const catchUp = Math.max(0.0, Math.min(C.WAGE_CATCHUP_CAP, productivity - realWageIndex));
    const costOfLivingPressure = Math.max(0.0, Math.min(1.0, cpi / Math.max(wageIndex, 1e-9) - 1.0));
    const bargain = Math.max(0.0, engine.wageBargainPower ?? 0.0);
    let institutional = bargain * (
      C.WAGE_CATCHUP_WEIGHT * catchUp + C.WAGE_COST_OF_LIVING_WEIGHT * costOfLivingPressure
    );
    institutional = Math.min(C.WAGE_INSTITUTIONAL_CAP, institutional);

    const scale = engine.wageFloorScale ?? 1.0;
    const base = C.WAGE_BASE * scale *
      Math.pow(productivity, share) *
      Math.pow(Math.max(0.0, 1.0 + expectedInflation), passThrough);
    return base * Math.max(0.0, 1.0 + tightness + institutional);
  }

  function enterpriseWageOffer(engine, enterprise) {
    const workers = engine.enterpriseWorkers(enterprise);
    const scale = engine.wageFloorScale ?? 1.0;
    const floor = wageFloor(engine.market.referencePrices) * scale;
    const cap = C.WAGE_BASE * C.WAGE_CAP_MULT;
    const target = wageTarget(engine, enterprise);

    const speed = Math.max(0.0, Math.min(1.0, engine.wageAdjustmentSpeed ?? 0.15));
    let state = enterprise.wageOffer || 0.0;
    if (state <= 0.0) {
      state = target;
    } else {
      let stepSpeed = speed;
      if (target < state) stepSpeed = Math.min(1.0, speed * C.WAGE_DOWNWARD_SPEED_MULT);
      state += stepSpeed * (target - state);
    }
    state = Math.min(Math.max(state, floor), cap);
    enterprise.wageOffer = state;

    let offer = state;
    if (workers.length < desiredWorkers(enterprise)) offer *= C.WAGE_HIRING_PREMIUM;
    let wageBill = 0.0;
    for (const w of workers) wageBill += w.wage * w.effectiveLabor;
    if (enterprise.cash < Math.max(wageBill * 2.0, offer * 2.0)) offer *= C.WAGE_CASH_DISCOUNT;
    return Math.min(Math.max(floor, round2(offer)), cap);
  }

  function inventoryMonths(enterprise, good) {
    const inventory = enterprise.inv(good);
    const sales = enterprise.smoothedSales;
    const target = enterprise.targetInventoryMonths;
    if (sales > 1e-6) return inventory / sales;
    if (inventory <= 1e-9) return 0.0;
    return Math.max(target, 0.5) * 2.0;
  }

  function ensureFreeMarkup(engine, enterprise, cost, ref) {
    if (enterprise.markupInitialized || cost <= 1e-9) return;
    const normal = Math.min(
      C.FREE_MARKUP_INIT_MAX,
      Math.max(C.FREE_MARKUP_INIT_MIN, ref / cost - 1.0),
    );
    enterprise.markup = normal;
    enterprise.markupNormal = normal;
    enterprise.markupInitialized = true;
  }

  function freePriceTarget(engine, enterprise, cost) {
    const out = SECTOR_PARAMS.get(enterprise.industry).output;
    if (cost === undefined || cost <= 0) {
      cost = normalUnitCost(engine, enterprise);
      if (cost <= 1e-9) cost = pricingUnitCost(engine, enterprise);
    }
    const ref = engine.market.referencePrices[out] ?? 1.0;
    ensureFreeMarkup(engine, enterprise, cost, ref);

    const targetMonths = enterprise.targetInventoryMonths;
    let gap = 0.0;
    if (targetMonths > 0) {
      const months = inventoryMonths(enterprise, out);
      gap = (targetMonths - months) / Math.max(targetMonths, 1.0);
    }

    const history = engine.market.history[out] || {};
    const demand = Math.max(0.0, history.demand || 0.0);
    const unmetRatio = demand > 1e-9
      ? Math.min(1.0, Math.max(0.0, (history.unmet || 0.0) / demand))
      : 0.0;
    const volume = Math.max(0.0, history.volume || 0.0);
    const unsold = Math.max(0.0, history.unsold || 0.0);
    const unsoldRatio = volume + unsold > 1e-9 ? Math.min(1.0, unsold / (volume + unsold)) : 0.0;

    const adjustment = gap + 0.5 * unmetRatio - 0.25 * unsoldRatio;
    const normal = Math.max(C.FREE_MARKUP_MIN, enterprise.markupNormal);
    let desiredMarkup = normal * Math.min(2.0, Math.max(0.5, 1.0 + adjustment));
    desiredMarkup = Math.min(C.FREE_MARKUP_MAX, Math.max(C.FREE_MARKUP_MIN, desiredMarkup));
    enterprise.markup += C.FREE_MARKUP_SPEED * (desiredMarkup - enterprise.markup);
    enterprise.markup = Math.min(C.FREE_MARKUP_MAX, Math.max(C.FREE_MARKUP_MIN, enterprise.markup));

    let demandFactor = 1.0 + (C.FREE_DEMAND_SLOPE * unmetRatio - C.FREE_GLUT_SLOPE * unsoldRatio);
    demandFactor = Math.min(C.FREE_DEMAND_FACTOR_MAX, Math.max(C.FREE_DEMAND_FACTOR_MIN, demandFactor));
    let target = cost * (1.0 + enterprise.markup) * demandFactor;

    const observed = history.observed || 0.0;
    if (observed > 0) {
      target = (1.0 - C.FREE_OBSERVED_WEIGHT) * target + C.FREE_OBSERVED_WEIGHT * observed;
    }
    return Math.max(C.PRICE_FLOOR, target);
  }

  function enterpriseAskPrice(engine, enterprise) {
    const params = SECTOR_PARAMS.get(enterprise.industry);
    const out = params.output;
    const ref = engine.market.referencePrices[out] ?? 1.0;
    const workers = engine.enterpriseWorkers(enterprise);
    const cost = unitCost(enterprise, engine.market.referencePrices, workers);
    const inventory = enterprise.inv(out);
    const skillSum = workers.reduce((sum, worker) => sum + worker.skill, 0);
    const capacity = capacityAtSkillOne(enterprise) * Math.max(skillSum / Math.max(workers.length, 1), 1.0);
    const sales = enterprise.smoothedSales;
    let months;
    if (sales <= 1e-6) months = inventory > 0 ? 3.0 : 0.0;
    else months = inventory / sales;

    const regime = engine.priceRegime || "band";
    if (regime === "free") {
      let pricingCost = normalUnitCost(engine, enterprise, engine.market.referencePrices, workers);
      if (pricingCost <= 1e-9) {
        pricingCost = pricingUnitCost(engine, enterprise, engine.market.referencePrices, workers);
      }
      let target;
      if (pricingCost > 1e-9) {
        target = freePriceTarget(engine, enterprise, pricingCost);
      } else {
        const observed = (engine.market.history[out] || {}).observed || 0.0;
        target = observed > 0 ? observed : ref;
      }
      let price = Math.min(
        Math.max(target, ref * (1.0 - C.FREE_REF_CORRIDOR)),
        ref * (1.0 + C.FREE_REF_CORRIDOR),
      );
      price = Math.min(price, INITIAL_PRICES[out] * C.FREE_PRICE_CAP_MULT);
      return Math.max(C.PRICE_FLOOR, price);
    }

    if (regime === "markup" && cost > 0) {
      const targetMonths = Math.max(enterprise.targetInventoryMonths, 0.5);
      const gap = (targetMonths - months) / Math.max(targetMonths, 1.0);
      enterprise.markup = Math.min(0.60, Math.max(0.02, enterprise.markup + 0.03 * gap));
      let price = cost * (1.0 + enterprise.markup);
      price = Math.max(price, cost * 0.5);
      price = Math.min(price, cost * 2.5);
      price = Math.min(price, ref * 1.30);
      return Math.max(0.01, price);
    }

    if (regime === "markup_soft") {
      if (cost <= 0) return Math.max(0.01, ref);
      const targetMonths = Math.max(enterprise.targetInventoryMonths, 0.5);
      const gap = (targetMonths - months) / targetMonths;
      enterprise.markup = Math.min(0.40, Math.max(0.02, enterprise.markup + 0.01 * gap));
      const desired = cost * (1.0 + enterprise.markup);
      let price = Math.min(Math.max(desired, cost * 0.80), cost * 2.0);
      price = Math.min(Math.max(price, ref * 0.85), ref * 1.15);
      let lo;
      let hi;
      if (months > 3.0) {
        lo = ref * 0.90;
        hi = ref * 0.98;
      } else if (months < 0.5 && sales > 1e-6) {
        lo = ref * 1.00;
        hi = ref * (out === "food" ? 1.05 : 1.04);
      } else {
        lo = ref * 0.98;
        hi = ref * 1.02;
      }
      price = Math.min(Math.max(price, lo), hi);
      price = Math.max(price, Math.min(cost * 0.80, ref * 1.15));
      return Math.max(0.01, price);
    }

    let price;
    if (months > 3.0) price = Math.min(ref * 0.90, cost > 0 ? cost * 1.05 : ref * 0.90);
    else if (months < 0.5) price = ref * 1.02;
    else price = ref * 0.98;
    if (cost > 0) price = Math.max(price, cost * 0.85);
    price = Math.min(price, ref * 1.02);
    return Math.max(0.01, price);
  }

  function productionPlan(engine, enterprise) {
    if (enterprise.industry === "agriculture") {
      return enterprise.land > 0 && enterprise.workers.length ? 1.0 : 0.0;
    }
    const params = SECTOR_PARAMS.get(enterprise.industry);
    const out = params.output;
    const capacity = capacityAtSkillOne(enterprise);
    if (capacity <= 0) return 0.0;
    const inventory = enterprise.inv(out);
    const sales = Math.max(enterprise.smoothedSales, 0.0);
    let target;
    if (sales <= 1e-6) target = Math.max(capacity * 0.5, 1.0);
    else target = Math.max(sales * 1.2, capacity * 0.1);
    const desired = Math.max(0.0, target - inventory);
    let plan = desired / capacity;
    if (plan < 0.1 && inventory < target) plan = 0.1;
    return Math.max(0.0, Math.min(1.0, plan));
  }

  function wantsFertilizer(engine, enterprise) {
    if (enterprise.industry !== "agriculture" || enterprise.land <= 0) return false;
    if (!enterprise.modernizationCapable) return false;
    const foodPrice = engine.market.referencePrices.food || 0.0;
    const fertilizerPrice = engine.market.referencePrices.fertilizer || 0.0;
    const extraYield = enterprise.land * C.BASE_GRAIN_YIELD * (C.FERTILIZER_YIELD_MULTIPLIER - 1.0);
    const benefit = extraYield * foodPrice * C.SKILL_MAX;
    const cost = enterprise.land * C.FERTILIZER_PER_MU * fertilizerPrice;
    return benefit > cost * 1.15;
  }

  function inputNeeds(engine, enterprise) {
    const params = SECTOR_PARAMS.get(enterprise.industry);
    const needs = {};
    if (enterprise.industry === "agriculture") {
      if (wantsFertilizer(engine, enterprise)) {
        const target = enterprise.land * C.FERTILIZER_PER_MU * 1.5;
        const needed = target - enterprise.inv("fertilizer");
        if (needed > 1e-9) needs.fertilizer = needed;
      }
      return needs;
    }
    const plan = Math.max(0.0, Math.min(1.0, enterprise.planRatio));
    const workers = engine.enterpriseWorkers(enterprise);
    let skillSum = 0.0;
    for (const worker of workers) skillSum += worker.skill;
    const skill = skillSum / Math.max(workers.length, 1);
    const expectedOutput = capacityAtSkillOne(enterprise) * plan * skill;
    const inputRatios = plannedInputRatios(engine, enterprise, engine.market.referencePrices);
    for (const good of Object.keys(inputRatios)) {
      const ratio = inputRatios[good];
      const target = expectedOutput * ratio;
      const safetyMonths = enterprise.industry === "fertilizer_factory"
        ? C.FERTILIZER_COAL_BUFFER_MONTHS : 0.5;
      const safety = safetyMonths * target;
      const needed = target + safety - enterprise.inv(good);
      if (needed > 1e-9) needs[good] = needed;
    }
    return needs;
  }

  function bestEquipmentChoice(engine, industry, budget, demandOverride, enterprise) {
    const prices = engine.market.referencePrices;
    const wage = engine.averageWage();
    const landPrice = engine.land.price;
    const params = SECTOR_PARAMS.get(industry);
    const totalDemand = (engine.market.history[params.output] || {}).demand || 0.0;
    let demand;
    if (industry === "agriculture") demand = totalDemand;
    else demand = totalDemand / Math.max(1, engine.activeEnterprises(industry).length);
    if (demandOverride !== undefined && demandOverride !== null) demand = demandOverride;
    const candidates = [];
    for (const key of params.equipment) {
      const et = EQUIPMENT.get(key);
      if (!et || et.capitalGood === null || et.buildMonths <= 0) continue;
      const cost = equipmentCost(key, prices);
      if (budget !== undefined && budget !== null && cost > budget) continue;
      const roi = representativeRoi(industry, key, prices, wage, landPrice, demand);
      candidates.push({ cost, key, roi, power: et.power });
    }
    if (!candidates.length) return null;

    // A2: once a capitalist farm is already powerful enough for its land,
    // additional farm machines mostly idle. Target one worker per farm and
    // choose the smallest 2^N tier that reaches that power, not the cheapest
    // t0 unit. This is what makes land consolidation and super-large
    // machinery possible without changing the 2^N production law.
    if (industry === "agriculture" && engine.durablesA2 && enterprise) {
      let currentPower = 0.0;
      for (const [key, count] of enterprise.equipment) {
        if (count <= 0 || !key.startsWith("farm_")) continue;
        const et = EQUIPMENT.get(key);
        if (et) currentPower += et.power * count;
      }
      const land = Math.max(0.0, enterprise.land || 0.0);
      const targetPower = land > 0
        ? Math.max(0.0, land / (C.LAND_PER_WORKER_BASE *
            Math.max(1.0, C.CONSOLIDATION_TARGET_WORKERS)) - 1.0)
        : 0.0;
      if (currentPower + 1e-9 >= targetPower && currentPower > 0) return null;
      const viable = candidates.filter((candidate) => candidate.roi >= C.INVESTMENT_HURDLE);
      if (!viable.length) return null;
      const above = viable
        .filter((candidate) => candidate.power + 1e-9 >= targetPower)
        .sort((a, b) => (a.power - b.power) || (b.roi - a.roi) || (a.cost - b.cost));
      if (above.length) return { key: above[0].key, roi: above[0].roi };
      viable.sort((a, b) => (b.power - a.power) || (b.roi - a.roi) || (a.cost - b.cost));
      return { key: viable[0].key, roi: viable[0].roi };
    }

    candidates.sort((a, b) => (a.cost - b.cost) || (b.roi - a.roi));
    return { key: candidates[0].key, roi: candidates[0].roi };
  }

  function shouldInvest(engine, enterprise) {
    if (!enterprise.active) return null;
    if (enterprise.industry === "agriculture" && !enterprise.modernizationCapable) return null;
    if (enterprise.industry === "fertilizer_factory") {
      let pending = 0;
      for (const project of engine.projects.values()) {
        if (project.active && project.enterpriseId === enterprise.id &&
            project.industry === "fertilizer_factory") pending += project.quantity;
      }
      if (enterprise.totalEquipment() + pending >= 2) return null;
    }
    const workers = engine.enterpriseWorkers(enterprise);
    let wageBill = 0.0;
    for (const w of workers) wageBill += w.wage * w.effectiveLabor;
    const reserve = Math.max(wageBill * 3.0, 100.0);
    const available = enterprise.cash - reserve;
    if (available <= 0) return null;
    const choice = bestEquipmentChoice(
      engine, enterprise.industry, available / 1.10, undefined, enterprise,
    );
    if (choice === null) return null;
    const cost = equipmentCost(choice.key, engine.market.referencePrices);
    if (choice.roi < C.INVESTMENT_HURDLE) return null;
    if (enterprise.cash < cost * 1.10 + reserve) return null;
    if (engine.tick - enterprise.lastInvestTick < 6) return null;
    return choice;
  }

  function agriculturalEntryRoi(engine) {
    return bestEquipmentChoice(engine, "agriculture") || { key: "farm_t0", roi: -1.0 };
  }

export {
  wageSubsistenceCost, wageFloor, shouldSwitch, normalUnitCost,
  pricingUnitCost, wageTarget, enterpriseWageOffer, inventoryMonths,
  ensureFreeMarkup, freePriceTarget, enterpriseAskPrice, productionPlan,
  wantsFertilizer, inputNeeds, bestEquipmentChoice, shouldInvest,
  agriculturalEntryRoi,
};
