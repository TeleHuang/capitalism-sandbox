/*
 * EcoSim V0.6 · engine source — module 10: entities and production.
 *
 * Field names mirror the former Python reference (models.py / production.py).
 * A2 durable stocks / equipment vintage batches live here; legacy mode keeps
 * the old monthly cloth/housing flow behaviour unchanged for oracle replay.
 */
import {
  C, GOODS, EQUIPMENT, SECTOR_PARAMS,
  zeros,
} from "./00-core.js";

  class Worker {
    constructor(fields) {
      Object.assign(this, {
        id: "W_0",
        industry: "agriculture",
        skill: 1.0,
        cash: 0.0,
        food: 0.10,
        cloth: 1.0,
        housing: 0.2,
        service: 0.0,
        meat: 0.0,
        employerId: null,
        wage: 0.0,
        hours: 16,
        standardHours: 16,
        alive: true,
        hungerMonths: 0,
        uiMonths: 0,
        lastUiIncome: 0.0,
        isOwnerOperator: false,
        landOwned: 0.0,
        ageMonths: 0,
        sex: "F",
        isChild: false,
        retired: false,
        parentId: null,
        childrenIds: [],
        pensionIncome: 0.0,
        birthTick: 0,
        consumedFood: 0.0,
        consumedCloth: 0.0,
        consumedHousing: 0.0,
        consumedService: 0.0,
        consumedMeat: 0.0,
        livingStandard: "survival",
        demandTargets: {},
        demandBudget: 0.0,
        // A2 household durables. `cloth` is the clothing stock (pieces) and
        // `housing` the housing stock (m²) when A2 is enabled; in legacy mode
        // they keep their V0.6 monthly-flow meaning.
        durableStock: {},
        cars: 0.0,
        carBatches: [],
        scrap: 0.0,
        monthPurchases: zeros(),
        clothTargetStock: 0.0,
        housingTargetStock: 0.0,
        carTargetStock: 0.0,
        clothQuality: 1.0,
        clothQualityTarget: 1.0,
        clothWear: 0.0,
        housingWear: 0.0,
        housingPurchased: 0.0,
        housingMaintenancePaid: 0.0,
        housingNewConstruction: 0.0,
        carPurchased: 0.0,
        carScrapped: 0.0,
        scrapGenerated: 0.0,
        durableSpending: 0.0,
      });
      Object.assign(this, fields || {});
    }
    get effectiveLabor() {
      const standard = Math.max(1, Math.trunc(this.standardHours || 16));
      return Math.max(0.0, this.hours) / standard;
    }
    get employed() {
      return this.employerId !== null && !this.isChild && !this.retired;
    }
    get isWorkingAge() {
      return !this.isChild && !this.retired;
    }
    chooseHours(prices) {
      if (this.isChild || this.retired) return 0;
      const standard = Math.max(1, Math.trunc(this.standardHours || 16));
      const full = standard;
      const mid = Math.max(1, Math.round(standard * 0.75));
      const low = Math.max(1, Math.round(standard * 0.50));
      const options = [full, mid, low];
      const basket =
        C.FOOD_PER_WORKER * prices.food +
        prices.cloth +
        0.2 * prices.building;
      const current = options.indexOf(this.hours) >= 0 ? this.hours : full;
      if (this.food + 1e-9 < 0.10 ||
          this.livingStandard === "survival" ||
          this.livingStandard === "subsistence") {
        return full;
      }
      if (this.cash >= C.LEISURE_SAVINGS && current > low) return low;
      if (this.cash >= C.COMFORT_SAVINGS && current > mid) return mid;
      if (this.cash < basket * 2.0 && current !== full) return full;
      return current;
    }
  }

  class Enterprise {
    constructor(fields) {
      Object.assign(this, {
        id: "E_0",
        industry: "coal_mine",
        ownerId: "",
        isHousehold: false,
        cash: 0.0,
        debt: 0.0,
        land: 0.0,
        equipment: new Map(),
        inventory: zeros(),
        workers: [],
        active: true,
        age: 0,
        lastInvestTick: -999,
        bankruptcyMonths: 0,
        modernizationCapable: true,
        smoothedSales: 0.0,
        demandForecast: 0.0,
        planRatio: 1.0,
        markup: 0.15,
        plannedOutput: 0.0,
        targetInventoryMonths: 2.0,
        lastDemand: 0.0,
        lastUnmet: 0.0,
        lastFillRate: 1.0,
        dormantMonths: 0,
        serviceIdleMonths: 0,
        replacementMonths: 0,
        wageOffer: 0.0,
        markupInitialized: false,
        markupNormal: 0.15,
        askPrices: {},
        useFertilizer: false,
        lastOutput: 0.0,
        lastInputUsed: {},
        lastRevenue: 0.0,
        lastCosts: 0.0,
        lastWages: 0.0,
        lastInterest: 0.0,
        lastProfit: 0.0,
        lastOperatingPayout: 0.0,
        lastSales: zeros(),
        monthRevenue: 0.0,
        monthInputCost: 0.0,
        monthWages: 0.0,
        monthInterest: 0.0,
        // A2 vintage batches. Each batch is {key, quantity, monthsLeft};
        // equipment-map counts and vintage quantities are kept in lockstep by
        // addEquipment()/retireEquipmentUnits().
        vintages: [],
        replacementDemand: 0.0,
        replacementByKey: {},
        scrapGenerated: 0.0,
        idleEquipmentSold: 0.0,
        lastSteelRecipe: null,
        lastScrapUsed: 0.0,
      });
      Object.assign(this, fields || {});
    }
    inv(good) {
      return this.inventory[good] || 0.0;
    }
    addEquipment(key, quantity, ageMonths) {
      const qty = quantity === undefined ? 1 : quantity;
      this.equipment.set(key, (this.equipment.get(key) || 0) + qty);
      addEquipmentVintage(this, key, qty, ageMonths);
    }
    equipmentCount(key) {
      return this.equipment.get(key) || 0;
    }
    totalEquipment() {
      let total = 0;
      for (const count of this.equipment.values()) total += count;
      return total;
    }
    resetMonthFlows() {
      this.monthRevenue = 0.0;
      this.monthInputCost = 0.0;
      this.monthWages = 0.0;
      this.monthInterest = 0.0;
      this.lastSales = zeros();
      this.lastOutput = 0.0;
      this.lastInputUsed = {};
      this.lastOperatingPayout = 0.0;
    }
  }

  class Capitalist {
    constructor(fields) {
      Object.assign(this, {
        id: "C_0",
        cash: 0.0,
        role: "director",
        food: 0.15,
        cloth: 1.5,
        housing: 0.3,
        service: 0.0,
        meat: 0.0,
        consumedFood: 0.0,
        consumedCloth: 0.0,
        consumedHousing: 0.0,
        consumedService: 0.0,
        consumedMeat: 0.0,
        demandTargets: {},
        demandBudget: 0.0,
        durableStock: {},
        cars: 0.0,
        carBatches: [],
        scrap: 0.0,
        monthPurchases: zeros(),
        clothTargetStock: 0.0,
        housingTargetStock: 0.0,
        carTargetStock: 0.0,
        clothQuality: 1.0,
        clothQualityTarget: 1.0,
        clothWear: 0.0,
        housingWear: 0.0,
        housingPurchased: 0.0,
        housingMaintenancePaid: 0.0,
        housingNewConstruction: 0.0,
        carPurchased: 0.0,
        carScrapped: 0.0,
        scrapGenerated: 0.0,
        durableSpending: 0.0,
      });
      Object.assign(this, fields || {});
    }
    ownedCount(enterprises) {
      let count = 0;
      for (const enterprise of enterprises.values()) {
        if (enterprise.ownerId === this.id && enterprise.active) count += 1;
      }
      return count;
    }
  }

  class InvestmentProject {
    constructor(fields) {
      Object.assign(this, {
        id: "P_0",
        industry: "coal_mine",
        enterpriseId: "",
        equipmentKey: "",
        quantity: 1,
        needed: {},
        cash: 0.0,
        createdTick: 0,
        buildMonths: 0,
        isNewEnterprise: false,
        received: zeros(),
        inventory: zeros(),
        monthsLeft: 0,
        age: 0,
        active: true,
        started: false,
        isReplacement: false,
      });
      Object.assign(this, fields || {});
    }
    fullyPaid() {
      for (const good of Object.keys(this.needed)) {
        if ((this.received[good] || 0.0) + 1e-9 < this.needed[good]) return false;
      }
      return true;
    }
    remaining(good) {
      return Math.max(0.0, (this.needed[good] || 0.0) - (this.received[good] || 0.0));
    }
  }

  class FoodReserve {
    constructor(fields) {
      Object.assign(this, { cash: 0.0, food: 0.0 });
      Object.assign(this, fields || {});
    }
  }

  class AssetPool {
    constructor() {
      this.inventory = zeros();
      this.equipment = new Map();
      this.land = 0.0;
    }
  }

  class Bank {
    constructor(cash, interestRate) {
      this.cash = cash;
      this.interestRate = interestRate === undefined ? 0.01 : interestRate;
      this.loans = new Map();
      this.deposits = new Map();
      this.depositRate = 0.002;
      this.writeOffs = 0.0;
      this.frozenCash = 0.0;
    }
    deposit(agent, amount) {
      amount = Math.max(0.0, Math.min(amount, agent.cash || 0.0));
      if (amount <= 1e-9) return 0.0;
      agent.cash -= amount;
      this.cash += amount;
      this.deposits.set(agent.id, (this.deposits.get(agent.id) || 0.0) + amount);
      return amount;
    }
    payDepositInterest(agents) {
      let total = 0.0;
      for (const amount of this.deposits.values()) total += amount;
      if (total <= 1e-9 || this.cash <= 1e-9) return 0.0;
      const due = total * this.depositRate;
      const factor = due > 0 ? Math.min(1.0, this.cash / due) : 0.0;
      let credited = 0.0;
      for (const [agentId, amount] of Array.from(this.deposits.entries())) {
        const agent = agents.get(agentId);
        if (agent === undefined || (agent.alive !== undefined && !agent.alive)) continue;
        const interest = amount * this.depositRate * factor;
        if (interest <= 1e-9) continue;
        agent.cash += interest;
        credited += interest;
      }
      this.cash -= credited;
      return credited;
    }
    lend(enterprise, amount) {
      amount = Math.max(0.0, Math.min(amount, this.cash));
      if (amount <= 1e-9) return 0.0;
      this.cash -= amount;
      enterprise.cash += amount;
      enterprise.debt += amount;
      this.loans.set(enterprise.id, (this.loans.get(enterprise.id) || 0.0) + amount);
      return amount;
    }
    chargeInterest(enterprise) {
      if (enterprise.debt <= 0) return 0.0;
      const interest = enterprise.debt * this.interestRate;
      const payable = Math.min(interest, Math.max(enterprise.cash, 0.0));
      enterprise.cash -= payable;
      this.cash += payable;
      const unpaid = interest - payable;
      enterprise.debt += unpaid;
      if (unpaid > 1e-12) {
        this.loans.set(enterprise.id, (this.loans.get(enterprise.id) || 0.0) + unpaid);
      }
      enterprise.monthInterest += payable;
      return payable;
    }
    repay(enterprise, amount) {
      amount = Math.max(0.0, Math.min(amount, enterprise.debt, enterprise.cash));
      if (amount <= 1e-9) return 0.0;
      enterprise.cash -= amount;
      enterprise.debt -= amount;
      this.cash += amount;
      this.loans.set(enterprise.id, Math.max(0.0, (this.loans.get(enterprise.id) || 0.0) - amount));
      return amount;
    }
  }

  class LandMarket {
    constructor(totalLand, price) {
      this.totalLand = totalLand;
      this.price = price;
      this.owners = new Map();
      this.enterpriseByOwner = new Map();
      this.estateLand = 0.0;
    }
    get smallholderLand() {
      let total = 0.0;
      for (const mu of this.owners.values()) total += mu;
      return total;
    }
    get capitalistLand() {
      return this.totalLand - this.smallholderLand;
    }
  }

  // -------------------------------------------------------------------
  // A2 equipment vintages / scrap and steel recipe selection
  // -------------------------------------------------------------------
  function scrapYieldForEquipment(key) {
    const et = EQUIPMENT.get(key);
    if (!et || et.capitalGood === null || et.capitalCost <= 0) return 0.0;
    if (et.capitalGood === "machinery") return et.capitalCost * C.SCRAP_PER_MACHINERY_GOOD;
    if (et.capitalGood === "steel") return et.capitalCost * C.SCRAP_PER_STEEL_GOOD;
    if (et.capitalGood === "brick") return et.capitalCost * C.SCRAP_PER_BRICK_GOOD;
    return 0.0;
  }

  function addEquipmentVintage(enterprise, key, quantity, ageMonths) {
    const qty = Number(quantity) || 0.0;
    if (qty <= 1e-12) return;
    const et = EQUIPMENT.get(key);
    // Zero-cost manual workshops / hand tools are labour-based production,
    // not produced capital vintages; they neither age nor yield scrap.
    // Brick-built furnaces and kilns are structures rather than mobile
    // machinery; they stay in the equipment map until liquidation instead of
    // triggering lumpy brick replacement projects.
    if (!et || et.capitalGood === null || et.capitalCost <= 0 ||
        et.capitalGood === "brick") return;
    const age = Math.max(0.0, Math.min(
      C.EQUIPMENT_LIFETIME_MONTHS - 1.0,
      Number(ageMonths) || 0.0,
    ));
    const monthsLeft = Math.max(1.0, C.EQUIPMENT_LIFETIME_MONTHS - age);
    const last = enterprise.vintages[enterprise.vintages.length - 1];
    if (last && last.key === key && Math.abs(last.monthsLeft - monthsLeft) < 1e-9) {
      last.quantity += qty;
      return;
    }
    enterprise.vintages.push({ key, quantity: qty, monthsLeft });
  }

  /**
   * Remove physical equipment units and return their scrap metal once.
   * Oldest vintages (lowest monthsLeft) are consumed first so age statistics
   * stay meaningful. The equipment map is the authoritative count; vintage
   * quantities are reduced by the same amount.
   */
  function retireEquipmentUnits(enterprise, key, quantity) {
    const wanted = Math.max(0.0, Number(quantity) || 0.0);
    const available = enterprise.equipment.get(key) || 0.0;
    const removed = Math.min(wanted, available);
    if (removed <= 1e-12) return { units: 0.0, scrap: 0.0 };
    enterprise.equipment.set(key, available - removed);
    if (available - removed <= 1e-12) enterprise.equipment.delete(key);

    const ordered = enterprise.vintages
      .filter((batch) => batch.key === key && batch.quantity > 1e-12)
      .sort((a, b) => a.monthsLeft - b.monthsLeft);
    let remaining = removed;
    for (const batch of ordered) {
      if (remaining <= 1e-12) break;
      const take = Math.min(batch.quantity, remaining);
      batch.quantity -= take;
      remaining -= take;
    }
    enterprise.vintages = enterprise.vintages.filter((batch) => batch.quantity > 1e-12);

    const scrap = scrapYieldForEquipment(key) * removed;
    if (scrap > 1e-12) {
      enterprise.inventory.scrap = (enterprise.inventory.scrap || 0.0) + scrap;
      enterprise.scrapGenerated += scrap;
    }
    return { units: removed, scrap };
  }

  function steelRecipeCost(recipe, prices) {
    let cost = 0.0;
    for (const [good, ratio] of Object.entries(recipe.inputs)) {
      cost += ratio * (prices[good] || 0.0);
    }
    return cost;
  }

  function steelRecipes() {
    const params = SECTOR_PARAMS.get("steel_mill");
    return params && params.recipes ? params.recipes : null;
  }

  /**
   * Pick a steel recipe. `feasibleOnly=true` is used by production: among
   * recipes with inputs on hand, prefer the one that can support the most
   * output, then the cheaper one. Input planning (`feasibleOnly=false`) uses
   * relative cost, but only considers the scrap route when scrap is actually
   * available in inventories / recent market supply.
   */
  function chooseSteelRecipe(engine, enterprise, prices, feasibleOnly) {
    const recipes = steelRecipes();
    if (!recipes || !engine || !engine.durablesA2 ||
        enterprise.industry !== "steel_mill") {
      return { name: "ore", inputs: SECTOR_PARAMS.get(enterprise.industry).inputs };
    }
    const priced = recipes.map((recipe) => {
      let feasible = true;
      let maxOutput = Infinity;
      for (const [good, ratio] of Object.entries(recipe.inputs)) {
        if (ratio <= 0) continue;
        const stock = enterprise.inv(good);
        if (stock <= 1e-9) feasible = false;
        maxOutput = Math.min(maxOutput, stock / Math.max(ratio, 1e-12));
      }
      return { recipe, feasible, maxOutput, cost: steelRecipeCost(recipe, prices) };
    });
    if (feasibleOnly) {
      const feasible = priced.filter((item) => item.feasible && item.maxOutput > 1e-9);
      if (feasible.length) {
        feasible.sort((a, b) => (b.maxOutput - a.maxOutput) || (a.cost - b.cost));
        return feasible[0].recipe;
      }
    }
    const scrapMarketSupply = engine.market?.history?.scrap?.supply || 0.0;
    const scrapInStock = enterprise.inv("scrap") > 1e-9;
    const scrapGlobal = Number(engine._scrapSupplyStock) || 0.0;
    const scrapAvailable = scrapInStock || scrapMarketSupply > 1e-6 || scrapGlobal > 1e-6;
    let candidates = recipes.filter((recipe) => recipe.name !== "scrap" || scrapAvailable);
    if (!candidates.length) candidates = recipes.slice();
    candidates.sort((a, b) => steelRecipeCost(a, prices) - steelRecipeCost(b, prices));
    return candidates[0];
  }

  function plannedInputRatios(engine, enterprise, prices) {
    if (enterprise.industry === "steel_mill" && engine && engine.durablesA2) {
      return chooseSteelRecipe(engine, enterprise, prices, false).inputs;
    }
    return SECTOR_PARAMS.get(enterprise.industry).inputs;
  }

  // -------------------------------------------------------------------
  // Production helpers (src/ecosim/production.py)
  // -------------------------------------------------------------------
  function equipmentSummary(enterprise) {
    let capacity = 0.0;
    let workers = 0;
    let units = 0;
    for (const [key, count] of enterprise.equipment) {
      if (count <= 0) continue;
      const et = EQUIPMENT.get(key);
      if (!et) continue;
      capacity += et.capacity * count;
      workers += et.workers * count;
      units += count;
    }
    return { capacity, workers, units };
  }
  function farmRequirements(enterprise) {
    let power = 0.0;
    for (const [key, count] of enterprise.equipment) {
      if (count <= 0) continue;
      const et = EQUIPMENT.get(key);
      if (et) power += et.power * count;
    }
    if (enterprise.land <= 0) return { required: 0, power };
    const landPerWorker = C.LAND_PER_WORKER_BASE * (1.0 + power);
    return { required: Math.max(1, Math.ceil(enterprise.land / landPerWorker)), power };
  }
  function desiredWorkers(enterprise, plan) {
    const p = plan === undefined ? 1.0 : plan;
    let required = 0;
    if (enterprise.industry === "agriculture") {
      required = farmRequirements(enterprise).required;
    } else {
      required = equipmentSummary(enterprise).workers;
    }
    if (required <= 0) return 0;
    plan = Math.max(0.0, Math.min(1.0, p));
    if (plan <= 1e-9) return enterprise.industry === "agriculture" ? 1 : 0;
    return Math.max(1, Math.ceil(required * plan));
  }
  function capacityAtSkillOne(enterprise) {
    if (enterprise.industry === "agriculture") {
      return enterprise.land * C.BASE_GRAIN_YIELD;
    }
    return equipmentSummary(enterprise).capacity;
  }
  function averageSkill(workers) {
    if (!workers.length) return 0.0;
    let total = 0.0;
    for (const w of workers) total += w.skill;
    return total / workers.length;
  }
  function averageWage(workers) {
    if (!workers.length) return 0.0;
    let wages = 0.0;
    let labor = 0.0;
    for (const w of workers) {
      wages += w.wage * w.effectiveLabor;
      labor += w.effectiveLabor;
    }
    return wages / Math.max(labor, 1e-9);
  }
  function productivityMultiplier(engine, enterprise) {
    return Math.max(0.0, engine.productivityMultipliers.get(enterprise.industry) ?? 1.0);
  }
  function produce(engine, enterprise) {
    const workers = engine.enterpriseWorkers(enterprise);
    if (!workers.length) {
      enterprise.lastOutput = 0.0;
      enterprise.lastInputUsed = {};
      return 0.0;
    }
    let effectiveLabor = 0.0;
    for (const w of workers) effectiveLabor += w.effectiveLabor;
    const skill = averageSkill(workers);
    const plan = Math.max(0.0, Math.min(1.0, enterprise.planRatio));
    if (plan <= 1e-9) {
      enterprise.lastOutput = 0.0;
      enterprise.lastInputUsed = {};
      return 0.0;
    }
    if (enterprise.industry === "agriculture") {
      const required = farmRequirements(enterprise).required;
      if (enterprise.land <= 0 || required <= 0) {
        enterprise.lastOutput = 0.0;
        return 0.0;
      }
      const utilisation = Math.min(plan, effectiveLabor / required);
      const baseCapacity = enterprise.land * C.BASE_GRAIN_YIELD * skill *
        productivityMultiplier(engine, enterprise);
      let multiplier = 1.0;
      let fertilizerUsed = 0.0;
      if (enterprise.useFertilizer) {
        const needed = enterprise.land * C.FERTILIZER_PER_MU;
        if (enterprise.inv("fertilizer") + 1e-9 >= needed) {
          multiplier = C.FERTILIZER_YIELD_MULTIPLIER;
          fertilizerUsed = needed;
          enterprise.inventory.fertilizer -= needed;
        } else {
          enterprise.useFertilizer = false;
        }
      }
      const output = baseCapacity * utilisation * multiplier;
      enterprise.inventory.food = enterprise.inv("food") + output;
      enterprise.lastOutput = output;
      enterprise.lastInputUsed = fertilizerUsed > 0 ? { fertilizer: fertilizerUsed } : {};
      return output;
    }
    const { capacity, workers: required } = equipmentSummary(enterprise);
    if (capacity <= 0 || required <= 0) {
      enterprise.lastOutput = 0.0;
      enterprise.lastSteelRecipe = null;
      enterprise.lastScrapUsed = 0.0;
      return 0.0;
    }
    const utilisation = Math.min(plan, effectiveLabor / required);
    const theoretical = capacity * utilisation * skill * productivityMultiplier(engine, enterprise);
    const params = SECTOR_PARAMS.get(enterprise.industry);
    let inputRatios = params.inputs;
    if (enterprise.industry === "steel_mill" && engine.durablesA2) {
      const recipe = chooseSteelRecipe(engine, enterprise, engine.market.referencePrices, true);
      inputRatios = recipe.inputs;
      enterprise.lastSteelRecipe = recipe.name;
    } else {
      enterprise.lastSteelRecipe = enterprise.industry === "steel_mill" ? "ore" : null;
    }
    let maxOutput = theoretical;
    for (const good of Object.keys(inputRatios)) {
      const ratio = inputRatios[good];
      if (ratio <= 0) continue;
      maxOutput = Math.min(maxOutput, enterprise.inv(good) / ratio);
    }
    maxOutput = Math.max(0.0, maxOutput);
    const used = {};
    for (const good of Object.keys(inputRatios)) {
      const ratio = inputRatios[good];
      const consumed = maxOutput * ratio;
      enterprise.inventory[good] = Math.max(0.0, enterprise.inv(good) - consumed);
      used[good] = consumed;
    }
    enterprise.inventory[params.output] = enterprise.inv(params.output) + maxOutput;
    enterprise.lastOutput = maxOutput;
    enterprise.lastInputUsed = used;
    enterprise.lastScrapUsed = used.scrap || 0.0;
    return maxOutput;
  }
  function equipmentValue(enterprise, prices) {
    let value = 0.0;
    for (const [key, count] of enterprise.equipment) {
      if (count <= 0) continue;
      const et = EQUIPMENT.get(key);
      if (!et) continue;
      if (et.capitalGood !== null) value += count * et.capitalCost * (prices[et.capitalGood] || 0.0);
      value += count * et.buildingCost * (prices.building || 0.0);
    }
    return value;
  }
  function fullCapacityUnitCost(enterprise, prices, workers) {
    const capacity = capacityAtSkillOne(enterprise);
    const required = desiredWorkers(enterprise);
    if (capacity <= 0 || required <= 0) return 0.0;
    let effective = 0.0;
    for (const w of workers) effective += w.effectiveLabor;
    const skill = averageSkill(workers) || 1.0;
    const plan = Math.max(0.0, Math.min(1.0, enterprise.planRatio));
    const output = capacity * Math.min(plan, effective / required) * skill;
    if (output <= 1e-9) return 0.0;
    let wageBill = 0.0;
    for (const w of workers) wageBill += w.wage * w.effectiveLabor;
    const depreciation = equipmentValue(enterprise, prices) / C.DEPRECIATION_MONTHS;
    if (enterprise.industry === "agriculture") {
      const fertilizerCost = enterprise.useFertilizer
        ? enterprise.land * C.FERTILIZER_PER_MU * (prices.fertilizer || 0.0)
        : 0.0;
      return (wageBill + fertilizerCost + depreciation) / output;
    }
    const params = SECTOR_PARAMS.get(enterprise.industry);
    let inputCost = 0.0;
    for (const good of Object.keys(params.inputs)) {
      inputCost += params.inputs[good] * output * (prices[good] || 0.0);
    }
    return (wageBill + inputCost + depreciation) / output;
  }
  function unitCost(enterprise, prices, workers) {
    const output = enterprise.lastOutput;
    if (output <= 1e-9) return fullCapacityUnitCost(enterprise, prices, workers);
    let wageBill = 0.0;
    for (const w of workers) wageBill += w.wage * w.effectiveLabor;
    let inputCost = 0.0;
    for (const good of Object.keys(enterprise.lastInputUsed)) {
      inputCost += enterprise.lastInputUsed[good] * (prices[good] || 0.0);
    }
    const depreciation = equipmentValue(enterprise, prices) / C.DEPRECIATION_MONTHS;
    return (wageBill + inputCost + depreciation) / output;
  }
  function capitalValue(enterprise, prices, landPrice) {
    let value = enterprise.land * landPrice;
    for (const [key, count] of enterprise.equipment) {
      if (count <= 0) continue;
      const et = EQUIPMENT.get(key);
      if (!et) continue;
      if (et.capitalGood !== null) value += count * et.capitalCost * (prices[et.capitalGood] || 0.0);
      value += count * et.buildingCost * (prices.building || 0.0);
    }
    return value;
  }
  function inventoryValue(enterprise, prices) {
    let value = 0.0;
    for (const good of GOODS) value += enterprise.inv(good) * (prices[good] || 0.0);
    return value;
  }
  function netWorth(enterprise, prices, landPrice) {
    return enterprise.cash + inventoryValue(enterprise, prices) +
      capitalValue(enterprise, prices, landPrice) - enterprise.debt;
  }
  function equipmentCost(equipmentKey, prices) {
    const et = EQUIPMENT.get(equipmentKey);
    if (!et) return 0.0;
    let goodCost = 0.0;
    if (et.capitalGood !== null) goodCost = et.capitalCost * (prices[et.capitalGood] || 0.0);
    const buildingCost = et.buildingCost * (prices.building || 0.0);
    return goodCost + buildingCost;
  }
  function representativeRoi(industry, equipmentKey, prices, wage, landPrice, demand) {
    const et = EQUIPMENT.get(equipmentKey);
    const params = SECTOR_PARAMS.get(industry);
    const demandCap = demand === undefined ? null : demand;
    if (industry === "agriculture") {
      const land = C.TARGET_CAPITALIST_FARM_MU;
      const power = et.power;
      const required = Math.max(1, Math.ceil(land / (C.LAND_PER_WORKER_BASE * (1.0 + power))));
      let output = land * C.BASE_GRAIN_YIELD * C.FERTILIZER_YIELD_MULTIPLIER * C.SKILL_MAX;
      if (demandCap !== null) output = Math.min(output, Math.max(0.0, demandCap));
      if (output <= 1e-9) return -1.0;
      const revenue = output * (prices[params.output] || 0.0);
      const fertilizer = land * C.FERTILIZER_PER_MU * (prices.fertilizer || 0.0);
      const wages = required * wage;
      const capital = land * landPrice + equipmentCost(equipmentKey, prices);
      const profit = revenue - fertilizer - wages;
      return capital > 0 ? profit / capital : -1.0;
    }
    let output = et.capacity * C.SKILL_MAX;
    if (demandCap !== null) output = Math.min(output, Math.max(0.0, demandCap));
    if (output <= 1e-9) return -1.0;
    const revenue = output * (prices[params.output] || 0.0);
    let inputCost = 0.0;
    for (const good of Object.keys(params.inputs)) {
      inputCost += params.inputs[good] * output * (prices[good] || 0.0);
    }
    const wages = et.workers * wage;
    const capital = equipmentCost(equipmentKey, prices);
    const profit = revenue - inputCost - wages;
    return capital > 0 ? profit / capital : -1.0;
  }

export {
  Worker, Enterprise, Capitalist, InvestmentProject, FoodReserve,
  AssetPool, Bank, LandMarket,
  equipmentSummary, farmRequirements, desiredWorkers,
  capacityAtSkillOne, averageSkill, averageWage, productivityMultiplier,
  produce, equipmentValue, fullCapacityUnitCost, unitCost, capitalValue,
  inventoryValue, netWorth, equipmentCost, representativeRoi,
  scrapYieldForEquipment, addEquipmentVintage, retireEquipmentUnits,
  steelRecipeCost, steelRecipes, chooseSteelRecipe, plannedInputRatios,
};
