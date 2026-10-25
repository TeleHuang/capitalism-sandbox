/*
 * EcoSim V0.6 · engine source — module 40: the monthly Engine.
 *
 * This is the authoritative implementation. The former Python engine is kept
 * only as a migration oracle (scripts/export_golden_v06.py); nothing here
 * imports or executes Python. A2 durables are implemented in the same loop;
 * credit-regime extensions will add methods/fields rather than rewriting it.
 */
import {
  C, GOODS, INDUSTRIES, GOOD_LABELS, INITIAL_PRICES, SECTOR_PARAMS,
  EQUIPMENT, MANUAL_EQUIPMENT, BUNDLE, DEFAULT_DEMAND,
  zeros, clamp, PythonRandom,
  demandTargets, demandShares, consumptionBudget,
  capitalistConsumptionBudget, consumerPriceIndex, realWageProxy,
} from "./00-core.js";
import {
  Worker, Enterprise, Capitalist, InvestmentProject, FoodReserve,
  AssetPool, Bank, LandMarket,
  capacityAtSkillOne, desiredWorkers, equipmentCost, equipmentValue,
  inventoryValue, capitalValue, netWorth, produce, averageSkill,
  retireEquipmentUnits,
} from "./10-models.js";
import { Government, POLICY_REGIMES, MONEY_REGIMES } from "./15-government.js";
import {
  wageSubsistenceCost, wageFloor, shouldSwitch, normalUnitCost,
  pricingUnitCost, enterpriseWageOffer, enterpriseAskPrice, productionPlan,
  wantsFertilizer, inputNeeds, bestEquipmentChoice, shouldInvest,
  agriculturalEntryRoi,
} from "./20-decisions.js";
import { Market } from "./30-market.js";
import {
  assignDurableTargets, durablePurchaseNeeds, durableSpendingCap,
  resetHouseholdMonth, applyDurableWear,
} from "./25-durables.js";
import { runLandMarket, farmMaxPower } from "./35-land.js";

function makeDemographics(overrides) {
  return Object.assign({
    workingAgeMonths: 14 * 12,
    retirementAgeMonths: 0,
    fertilityMonthly: 0.024,
    fertilityAgeMinMonths: 20 * 12,
    fertilityAgeMaxMonths: 40 * 12,
    fertilityMultiplier: 1.0,
    mortalityA: 0.0015,
    mortalityB: 0.0001,
    mortalityC: 0.085,
    infantMortalityAnnual: 0.18,
    childMortalityAnnual: 0.02,
    maxAgeMonths: 110 * 12,
    initialAgeMinMonths: 18 * 12,
    initialAgeMaxMonths: 60 * 12,
    initialFemaleShare: 0.5,
    childFood: 0.05,
    childCloth: 0.5,
    childHousing: 0.1,
    pensionTaxRate: 0.0,
    pensionReplacement: 0.0,
    pensionFundInitial: 0.0,
  }, overrides || {});
}

class Engine {
  constructor(seed, options) {
    this.seed = seed === undefined ? 1 : seed;
    const opts = options || {};
    this.durablesA2 = opts.durables === undefined ? true : !!opts.durables;
    this.rng = new PythonRandom(this.seed);
    this.demographicRng = new PythonRandom(this.seed + 1000003);
    this.tick = 0;
    this.workers = new Map();
    this.enterprises = new Map();
    this.capitalists = new Map();
    this.projects = new Map();
    this.market = new Market(INITIAL_PRICES);
    this.land = new LandMarket(C.TOTAL_LAND_MU, C.INITIAL_LAND_PRICE);
    this.bank = new Bank(C.BANK_CASH, C.BANK_INTEREST_RATE);
    this.assetPool = new AssetPool();
    this.foodReserve = new FoodReserve();
    this.government = null;
    this.wageFloorScale = 1.0;
    this.priceRegime = "band";
    this.demandRegime = "geary";
    this.demandConfig = DEFAULT_DEMAND;
    this.bankIntermediation = false;
    this.workHours = 16;
    this.wageProductivityShare = 0.5;
    this.wageAdjustmentSpeed = 0.10;
    this.wageBargainPower = 0.10;
    this.wageInflationPassThrough = 1.0;
    this.inflationExpectations = 0.0;
    this.productivityIndex = 1.0;
    this._productivityBaseline = null;
    this._productivitySmoothed = null;
    this._productivityRaw = 0.0;
    this.cpi = 1.0;
    this._cpiBaseline = Math.max(1e-9, wageSubsistenceCost(INITIAL_PRICES));
    this.observedInflation = 0.0;
    this.wageIndex = 1.0;
    this.unitLaborCost = 0.0;
    this.realValueAdded = 0.0;
    this.productivityMultipliers = new Map();
    this.workerDemandScale = 1.0;
    this.capitalistDemandScale = 1.0;
    this.lendingScale = 1.0;
    this.stats = [];
    this.moneyInitial = 0.0;
    this.deadThisMonth = 0;
    this.demographics = makeDemographics();
    this.birthsThisMonth = 0;
    this._orphanedThisMonth = 0;
    this._ageDeathsThisMonth = 0;
    this._hungerDeathsThisMonth = 0;
    this._pensionShortfall = 0.0;
    this._foodReliefThisMonth = 0.0;
    this._foodReliefShortfall = 0.0;
    this._foodLevyThisMonth = 0.0;
    this._householdSelfConsumptionThisMonth = 0.0;
    this._householdFarmLiquidationsThisMonth = 0;
    this.householdFarmLiquidationsTotal = 0;
    this.productionMonth = zeros();
    this._nextWorker = 0;
    this._nextEnterprise = 0;
    this._nextProject = 0;
    this._zeroOutputStreak = new Map();
    this._lastManualEntry = new Map();
    this._warnings = [];
    this._wageUnemployment = null;
    this._averageWageCache = null;
    // A2 monthly accumulators.
    this._equipmentRetiredThisMonth = 0.0;
    this._scrapGeneratedEquipmentThisMonth = 0.0;
    this._carRetiredThisMonth = 0.0;
    this._scrapGeneratedCarThisMonth = 0.0;
    this._idleEquipmentScrappedThisMonth = 0.0;
    this._replacementDemandThisMonth = 0.0;
    this._replacementProjectsStarted = 0;
    this._scrapSupplyStock = 0.0;
    // Feature flags are exposed to the UI so the release never silently
    // claims parity for mechanics that are not shipped.
    this.features = Object.freeze({
      coreV04: true,
      demandV06: true,
      wagePriceV06: true,
      demographyV05: true,
      pensionV05: true,
      durablesA2: this.durablesA2,
      creditRegimeC: false,
    });
  }

  // ------------------------------------------------------------------
  // Identity / queries
  // ------------------------------------------------------------------
  newWorkerId() {
    this._nextWorker += 1;
    return `W_${this._nextWorker - 1}`;
  }
  newEnterpriseId() {
    this._nextEnterprise += 1;
    return `E_${this._nextEnterprise - 1}`;
  }
  newProjectId() {
    this._nextProject += 1;
    return `P_${this._nextProject - 1}`;
  }
  enterpriseWorkers(enterprise) {
    const result = [];
    for (const workerId of enterprise.workers) {
      const worker = this.workers.get(workerId);
      if (worker && worker.alive && !worker.isChild && !worker.retired) result.push(worker);
    }
    return result;
  }
  _isHouseholdFarm(enterprise) {
    return enterprise.isHousehold && enterprise.industry === "agriculture";
  }
  _isHouseholdFarmOwner(enterprise, worker) {
    return this._isHouseholdFarm(enterprise) &&
      (worker.isOwnerOperator || worker.id === enterprise.ownerId);
  }
  sectorParams(industry) {
    return SECTOR_PARAMS.get(industry);
  }
  activeEnterprises(industry) {
    const result = [];
    for (const enterprise of this.enterprises.values()) {
      if (enterprise.active && (industry === undefined || enterprise.industry === industry)) {
        result.push(enterprise);
      }
    }
    return result;
  }
  averageWage() {
    if (this._averageWageCache !== null) return this._averageWageCache;
    let total = 0.0;
    let count = 0;
    for (const worker of this.workers.values()) {
      if (worker.alive && worker.employed && !worker.isChild && !worker.retired && worker.wage > 0) {
        total += worker.wage;
        count += 1;
      }
    }
    const value = count ? total / count : C.WAGE_BASE;
    this._averageWageCache = value;
    return value;
  }
  feedingUnits() {
    let units = 0.0;
    for (const worker of this.workers.values()) {
      if (worker.alive) units += worker.isChild ? 0.5 : 1.0;
    }
    return Math.max(1.0, units);
  }
  laborForceWorkers() {
    const result = [];
    for (const worker of this.workers.values()) {
      if (worker.alive && worker.isWorkingAge) result.push(worker);
    }
    return result;
  }
  totalMoney() {
    let total = 0.0;
    for (const worker of this.workers.values()) if (worker.alive) total += worker.cash;
    for (const capitalist of this.capitalists.values()) total += capitalist.cash;
    for (const enterprise of this.enterprises.values()) if (enterprise.active) total += enterprise.cash;
    for (const project of this.projects.values()) if (project.active) total += project.cash;
    total += this.bank.cash + this.bank.frozenCash + this.foodReserve.cash;
    if (this.government !== null) total += this.government.cash;
    return total;
  }
  fertilizerSupplyShort() {
    if ((this._zeroOutputStreak.get("fertilizer") || 0) > 0) return true;
    let stock = 0.0;
    for (const enterprise of this.activeEnterprises("fertilizer_factory")) stock += enterprise.inv("fertilizer");
    let potential = 0.0;
    for (const farm of this.activeEnterprises("agriculture")) {
      if (farm.modernizationCapable) potential += farm.land * C.FERTILIZER_PER_MU;
    }
    return potential > 1e-9 && stock < potential;
  }
  fertilizerCoalReserve(enterprise, capacity) {
    if (enterprise.industry !== "fertilizer_factory") return 0.0;
    const params = SECTOR_PARAMS.get("fertilizer_factory");
    const coalRatio = params.inputs.coal || 0.0;
    if (coalRatio <= 0) return 0.0;
    if (capacity === undefined || capacity === null) capacity = capacityAtSkillOne(enterprise);
    const coalPrice = this.market.referencePrices.coal || 0.0;
    return capacity * coalRatio * C.FERTILIZER_COAL_BUFFER_MONTHS * coalPrice;
  }

  // ------------------------------------------------------------------
  // Entity creation
  // ------------------------------------------------------------------
  createWorker(fields) {
    fields = fields || {};
    let ageMonths = fields.ageMonths;
    if (ageMonths === undefined || ageMonths === null) {
      ageMonths = this.demographics.workingAgeMonths + 10 * 12;
    }
    const sex = fields.sex || "F";
    const isChild = fields.isChild === undefined ? ageMonths < this.demographics.workingAgeMonths : fields.isChild;
    const birthTick = fields.birthTick === undefined ? this.tick - ageMonths : fields.birthTick;
    const standardHours = Math.max(1, Math.trunc(this.workHours || 16));
    const retired = !!fields.retired;
    const worker = new Worker({
      id: this.newWorkerId(),
      industry: fields.industry || "agriculture",
      skill: fields.skill === undefined ? 1.0 : fields.skill,
      cash: fields.cash === undefined ? 0.0 : fields.cash,
      food: fields.food === undefined ? C.FOOD_PER_WORKER : fields.food,
      ageMonths,
      sex,
      isChild,
      retired,
      parentId: fields.parentId === undefined ? null : fields.parentId,
      birthTick,
      standardHours,
      hours: isChild || retired ? 0 : standardHours,
    });
    this.workers.set(worker.id, worker);
    return worker;
  }
  createEnterprise(fields) {
    fields = fields || {};
    const enterprise = new Enterprise({
      id: this.newEnterpriseId(),
      industry: fields.industry,
      ownerId: fields.ownerId,
      cash: fields.cash === undefined ? 0.0 : fields.cash,
      land: fields.land === undefined ? 0.0 : fields.land,
      isHousehold: !!fields.isHousehold,
      modernizationCapable: fields.modernizationCapable === undefined
        ? true : fields.modernizationCapable,
    });
    this.enterprises.set(enterprise.id, enterprise);
    return enterprise;
  }
  createAgriculturalEnterprise(capitalist, landMu, price) {
    const injection = Math.min(capitalist.cash * 0.5, 20000.0);
    capitalist.cash -= injection;
    const enterprise = this.createEnterprise({
      industry: "agriculture",
      ownerId: capitalist.id,
      cash: injection,
      land: landMu,
      isHousehold: false,
      modernizationCapable: true,
    });
    enterprise.demandForecast = landMu * C.BASE_GRAIN_YIELD * 2.0;
    enterprise.targetInventoryMonths = 6.0;
    return enterprise;
  }
  _bootstrapManualEntry(industry, key) {
    if (this.tick - (this._lastManualEntry.get(industry) ?? -999) < 12) return false;
    const candidates = [];
    for (const capitalist of this.capitalists.values()) {
      if (capitalist.cash >= 500.0) candidates.push(capitalist);
    }
    if (!candidates.length) return false;
    candidates.sort((a, b) => {
      const owned = a.ownedCount(this.enterprises) - b.ownedCount(this.enterprises);
      if (owned !== 0) return owned;
      if (b.cash !== a.cash) return b.cash - a.cash;
      return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
    });
    const owner = candidates[0];
    const setupCost = 300.0;
    owner.cash -= setupCost;
    const enterprise = this.createEnterprise({
      industry, ownerId: owner.id, cash: setupCost, modernizationCapable: true,
    });
    enterprise.addEquipment(key, 1);
    enterprise.demandForecast = 1.0;
    enterprise.targetInventoryMonths = 1.0;
    this._lastManualEntry.set(industry, this.tick);
    return true;
  }
  _startProject(enterprise, equipmentKey, isNew, priority, isReplacement) {
    isNew = !!isNew;
    priority = !!priority;
    isReplacement = !!isReplacement;
    let activeProjects = 0;
    for (const project of this.projects.values()) if (project.active) activeProjects += 1;
    if (!priority && activeProjects >= C.MAX_ACTIVE_PROJECTS) return false;
    const et = EQUIPMENT.get(equipmentKey);
    if (et.industry === "fertilizer_factory") {
      let pending = 0;
      for (const project of this.projects.values()) {
        if (project.active && project.enterpriseId === enterprise.id &&
            project.industry === "fertilizer_factory") pending += project.quantity;
      }
      if (enterprise.totalEquipment() + pending >= 2) return false;
    }
    const needed = {};
    if (et.capitalGood !== null && et.capitalCost > 0) needed[et.capitalGood] = et.capitalCost;
    if (et.buildingCost > 0) needed.building = et.buildingCost;
    if (!Object.keys(needed).length) return false;
    let estimate = 0.0;
    for (const good of Object.keys(needed)) {
      estimate += needed[good] * (this.market.referencePrices[good] ?? 1.0);
    }
    const workers = this.enterpriseWorkers(enterprise);
    let wageBill = 0.0;
    for (const worker of workers) wageBill += worker.wage * worker.effectiveLabor;
    let reserve = Math.max(wageBill * 3.0, 100.0);
    if (et.industry === "fertilizer_factory") {
      reserve += this.fertilizerCoalReserve(
        enterprise, capacityAtSkillOne(enterprise) + et.capacity,
      );
    }
    if (enterprise.cash < estimate * 1.10 + reserve) return false;
    const available = enterprise.cash - reserve;
    const projectCash = Math.min(available, estimate * 1.25);
    if (projectCash < estimate * 0.90) return false;
    enterprise.cash -= projectCash;
    const project = new InvestmentProject({
      id: this.newProjectId(),
      industry: enterprise.industry,
      enterpriseId: enterprise.id,
      equipmentKey,
      quantity: 1,
      needed,
      cash: projectCash,
      createdTick: this.tick,
      buildMonths: et.buildMonths,
      isNewEnterprise: isNew,
      isReplacement,
    });
    this.projects.set(project.id, project);
    enterprise.lastInvestTick = this.tick;
    return true;
  }

  // ------------------------------------------------------------------
  // Main loop
  // ------------------------------------------------------------------
  step() {
    this.tick += 1;
    this.deadThisMonth = 0;
    this.birthsThisMonth = 0;
    this._orphanedThisMonth = 0;
    this._ageDeathsThisMonth = 0;
    this._hungerDeathsThisMonth = 0;
    this._pensionShortfall = 0.0;
    this._foodReliefThisMonth = 0.0;
    this._foodReliefShortfall = 0.0;
    this._foodLevyThisMonth = 0.0;
    this._householdSelfConsumptionThisMonth = 0.0;
    this._householdFarmLiquidationsThisMonth = 0;
    this._warnings = [];
    this._wageUnemployment = null;
    this._averageWageCache = null;
    this._equipmentRetiredThisMonth = 0.0;
    this._scrapGeneratedEquipmentThisMonth = 0.0;
    this._carRetiredThisMonth = 0.0;
    this._scrapGeneratedCarThisMonth = 0.0;
    this._idleEquipmentScrappedThisMonth = 0.0;
    this._replacementDemandThisMonth = 0.0;
    this._replacementProjectsStarted = 0;
    this.productionMonth = zeros();
    for (const enterprise of this.enterprises.values()) enterprise.resetMonthFlows();
    if (this.government !== null) this.government.resetMonth();
    if (this.durablesA2) this._resetHouseholdFlows();
    this._updateSkills();
    this._demographyPre();
    if (this.durablesA2) this._ageEquipmentAndScrap();
    this._updateExpectationsAndPlans();
    if (this.bankIntermediation) this._bankIntermediation();
    this._laborMarket();
    this._payWages();
    this._payGovernmentWages();
    this._produceAll();
    this._produceGovernment();
    this._collectFoodReliefLevy();
    this._updatePriceBands();
    if (this.durablesA2) this._updateScrapAnchor();
    runLandMarket(this);
    if (this.durablesA2) this._scrapSupplyStock = this._sumScrapStock();
    this._investmentDecisions();

    this._submitSellOrders();
    this._submitHouseholdOrders();
    this._submitFoodReserveOrders();
    this._submitGovernmentOrders();
    this._submitInputOrders();
    this._submitProjectOrders();

    this.market.match();
    for (const enterprise of this.enterprises.values()) {
      if (enterprise.active) {
        const out = SECTOR_PARAMS.get(enterprise.industry).output;
        const sold = enterprise.lastSales[out] || 0.0;
        enterprise.smoothedSales = 0.7 * enterprise.smoothedSales + 0.3 * sold;
      }
    }
    for (const enterprise of this.enterprises.values()) {
      if (enterprise.active && enterprise.industry === "service") {
        enterprise.inventory.service = 0.0;
      }
    }

    this._progressProjects();
    this._finance();
    this._governmentSettlement();
    this._cleanupDormant();
    this._distributeFoodRelief();
    this._consumeAndDemographics();
    const stat = this._recordStats();
    this.market.consumptionSpending = 0.0;
    this.market.investmentSpending = 0.0;
    this.market.governmentSpending = 0.0;
    return stat;
  }

  _updateSkills() {
    for (const worker of this.workers.values()) {
      if (!worker.alive || !worker.employed) continue;
      worker.skill = Math.min(C.SKILL_MAX, worker.skill + C.SKILL_GROWTH_PER_MONTH);
    }
  }

  _resetHouseholdFlows() {
    for (const worker of this.workers.values()) {
      if (worker.alive) resetHouseholdMonth(worker);
    }
    for (const capitalist of this.capitalists.values()) resetHouseholdMonth(capitalist);
  }

  /**
   * Age every equipment vintage by one month. Expired units leave the
   * equipment map exactly once and become scrap in the owning enterprise's
   * inventory; replacement demand is recorded for the investment pass.
   */
  _ageEquipmentAndScrap() {
    for (const enterprise of this.enterprises.values()) {
      if (!enterprise.active || !enterprise.vintages.length) continue;
      const expired = new Map();
      for (const batch of enterprise.vintages) {
        if (batch.quantity <= 1e-12) continue;
        batch.monthsLeft -= 1;
        if (batch.monthsLeft <= 1e-9) {
          expired.set(batch.key, (expired.get(batch.key) || 0.0) + batch.quantity);
        }
      }
      for (const [key, quantity] of expired) {
        const result = retireEquipmentUnits(enterprise, key, quantity);
        if (result.units <= 1e-12) continue;
        enterprise.replacementDemand += result.units;
        enterprise.replacementByKey[key] = (enterprise.replacementByKey[key] || 0.0) +
          result.units;
        this._equipmentRetiredThisMonth += result.units;
        this._scrapGeneratedEquipmentThisMonth += result.scrap;
        this._replacementDemandThisMonth += result.units;
      }
      enterprise.vintages = enterprise.vintages.filter((batch) => batch.quantity > 1e-12);
    }
  }

  _updateScrapAnchor() {
    const orePrice = this.market.referencePrices.iron_ore || 0.0;
    this.market.priceAnchors.scrap = Math.max(C.PRICE_FLOOR, orePrice * C.SCRAP_PRICE_RATIO);
  }

  _sumScrapStock() {
    let total = this.assetPool.inventory.scrap || 0.0;
    for (const enterprise of this.enterprises.values()) {
      if (enterprise.active) total += enterprise.inv("scrap");
    }
    for (const worker of this.workers.values()) {
      if (worker.alive) total += Math.max(0.0, worker.scrap || 0.0);
    }
    for (const capitalist of this.capitalists.values()) {
      total += Math.max(0.0, capitalist.scrap || 0.0);
    }
    return total;
  }

  // ------------------------------------------------------------------
  // Demography / aging / mortality / births
  // ------------------------------------------------------------------
  _monthlyMortality(worker) {
    const demo = this.demographics;
    const age = Math.max(0, worker.ageMonths);
    if (age >= demo.maxAgeMonths) return 1.0;
    let annual;
    if (age < 12) annual = demo.infantMortalityAnnual;
    else if (age < 60) annual = demo.childMortalityAnnual;
    else {
      const mu = demo.mortalityA + demo.mortalityB * Math.exp(demo.mortalityC * age / 12.0);
      annual = 1.0 - Math.exp(-Math.max(0.0, mu));
    }
    const monthly = 1.0 - Math.pow(1.0 - Math.max(0.0, Math.min(1.0, annual)), 1.0 / 12.0);
    return Math.max(0.0, Math.min(1.0, monthly));
  }
  _fertilityAgeShape(ageMonths) {
    const years = ageMonths / 12.0;
    if (years < 20 || years > 40) return 0.0;
    let weight;
    if (years < 25) weight = 0.7;
    else if (years < 30) weight = 1.2;
    else if (years < 35) weight = 1.1;
    else if (years < 40) weight = 0.8;
    else weight = 0.2;
    return weight / 0.9469;
  }
  _birthProbability(mother) {
    const demo = this.demographics;
    if (mother.sex !== "F" || mother.isChild || mother.retired) return 0.0;
    if (mother.ageMonths < demo.fertilityAgeMinMonths || mother.ageMonths > demo.fertilityAgeMaxMonths) {
      return 0.0;
    }
    const shape = this._fertilityAgeShape(mother.ageMonths);
    if (shape <= 0) return 0.0;
    const score = {
      survival: 0.0, subsistence: 0.5, comfort: 1.0, leisure: 1.2, child: 0.0,
    }[mother.livingStandard] ?? 0.5;
    const yRatio = Math.max(0.1, 0.5 + score);
    let foodRatio;
    if (mother.hungerMonths > 0) foodRatio = 0.3;
    else foodRatio = Math.max(0.05, Math.min(1.5, mother.consumedFood / Math.max(C.FOOD_PER_WORKER, 1e-9)));
    let multiplier = Math.pow(yRatio, 0.1) * Math.pow(foodRatio, 0.3);
    multiplier = Math.max(0.3, Math.min(1.5, multiplier));
    let livingChildren = 0;
    for (const childId of mother.childrenIds) {
      const child = this.workers.get(childId);
      if (child && child.alive && child.isChild) livingChildren += 1;
    }
    const parityFactor = 1.0 / (1.0 + 0.10 * livingChildren);
    const probability = demo.fertilityMonthly * demo.fertilityMultiplier *
      shape * multiplier * parityFactor;
    return Math.max(0.0, Math.min(0.2, probability));
  }
  _giveBirth(mother) {
    const sex = this.demographicRng.random() < 0.5 ? "F" : "M";
    const child = this.createWorker({
      industry: mother.industry,
      skill: 0.0,
      cash: 0.0,
      food: 0.0,
      ageMonths: 0,
      sex,
      isChild: true,
      parentId: mother.id,
      birthTick: this.tick,
    });
    child.cloth = 0.0;
    child.housing = 0.0;
    child.service = 0.0;
    child.hours = 0;
    child.livingStandard = "child";
    mother.childrenIds.push(child.id);
    this.birthsThisMonth += 1;
    return child;
  }
  _retireWorker(worker) {
    const employer = this.enterprises.get(worker.employerId || "");
    if (employer && employer.workers.includes(worker.id)) {
      employer.workers = employer.workers.filter((id) => id !== worker.id);
    }
    if (this.government !== null && this.government.jgWorkers.includes(worker.id)) {
      this.government.jgWorkers = this.government.jgWorkers.filter((id) => id !== worker.id);
    }
    worker.employerId = null;
    worker.wage = 0.0;
    worker.hours = 0;
    worker.uiMonths = 0;
    worker.retired = true;
  }
  _demographyPre() {
    const demo = this.demographics;
    for (const worker of Array.from(this.workers.values())) {
      if (!worker.alive) continue;
      worker.ageMonths += 1;
      if (worker.isChild && worker.ageMonths >= demo.workingAgeMonths) {
        worker.isChild = false;
        worker.skill = Math.max(1.0, worker.skill);
        const parent = this.workers.get(worker.parentId || "");
        worker.industry = parent && parent.alive ? parent.industry : "service";
        worker.standardHours = Math.max(1, Math.trunc(this.workHours || 16));
        worker.hours = worker.standardHours;
      }
      if (!worker.isChild && !worker.retired && demo.retirementAgeMonths > 0 &&
          worker.ageMonths >= demo.retirementAgeMonths && !worker.isOwnerOperator) {
        this._retireWorker(worker);
      }
    }
    for (const worker of Array.from(this.workers.values())) {
      if (!worker.alive) continue;
      if (this.demographicRng.random() < this._monthlyMortality(worker)) {
        this._killWorker(worker, "age");
      }
    }
    for (const mother of Array.from(this.workers.values())) {
      if (!mother.alive) continue;
      const probability = this._birthProbability(mother);
      if (probability > 0 && this.demographicRng.random() < probability) {
        this._giveBirth(mother);
      }
    }
  }
  _killWorker(worker, cause) {
    cause = cause || "age";
    if (!worker.alive) return;
    worker.alive = false;
    this.deadThisMonth += 1;
    if (cause === "hunger") this._hungerDeathsThisMonth += 1;
    else this._ageDeathsThisMonth += 1;
    this.bank.cash += Math.max(0.0, worker.cash);
    worker.cash = 0.0;
    this.bank.deposits.delete(worker.id);
    const employer = this.enterprises.get(worker.employerId || "");
    if (employer && employer.workers.includes(worker.id)) {
      employer.workers = employer.workers.filter((id) => id !== worker.id);
    }
    worker.employerId = null;
    worker.wage = 0.0;
    worker.hours = 0;
    if (this.government !== null && this.government.jgWorkers.includes(worker.id)) {
      this.government.jgWorkers = this.government.jgWorkers.filter((id) => id !== worker.id);
    }
    const parent = this.workers.get(worker.parentId || "");
    if (parent && parent.childrenIds.includes(worker.id)) {
      parent.childrenIds = parent.childrenIds.filter((id) => id !== worker.id);
    }
    const heir = this._chooseHeir(worker);
    if (worker.childrenIds.length) {
      for (const childId of worker.childrenIds.slice()) {
        const child = this.workers.get(childId);
        if (child && child.alive) {
          child.parentId = null;
          if (child.isChild) this._orphanedThisMonth += 1;
        }
      }
      worker.childrenIds.length = 0;
    }
    worker.parentId = null;
    this._settleEstate(worker, heir);
  }
  _payChildAllowances(prices) {
    const demo = this.demographics;
    const childBasket =
      demo.childFood * (prices.food || 0.0) +
      demo.childCloth * (prices.cloth || 0.0) +
      demo.childHousing * (prices.building || 0.0);
    if (childBasket <= 0) return;
    const adultReserve = C.FOOD_PER_WORKER * (prices.food || 0.0);
    for (const parent of Array.from(this.workers.values())) {
      if (!parent.alive || parent.isChild) continue;
      const children = [];
      for (const childId of parent.childrenIds) {
        const child = this.workers.get(childId);
        if (child && child.alive && child.isChild) children.push(child);
      }
      if (!children.length) continue;
      const available = Math.max(0.0, parent.cash - adultReserve);
      if (available <= 1e-9) continue;
      const required = childBasket * children.length;
      const pool = Math.min(required, available);
      if (pool <= 1e-9) continue;
      const share = pool / children.length;
      for (const child of children) {
        parent.cash -= share;
        child.cash += share;
      }
    }
  }
  _submitChildOrders(child, prices) {
    const demo = this.demographics;
    if (this.durablesA2) {
      assignDurableTargets(this, child, prices, Math.max(0.0, child.cash));
      const durableNeeds = durablePurchaseNeeds(child, prices);
      const targets = {
        food: demo.childFood,
        cloth: 0.0,
        building: 0.0,
        meat: 0.0,
        service: 0.0,
      };
      this._submitBundleOrders(child, targets, prices, this.workerDemandScale, {
        durableNeeds,
        cashCap: Math.max(0.0, child.cash),
      });
      return;
    }
    const targets = [
      ["food", demo.childFood, 1.05],
      ["cloth", demo.childCloth, 1.04],
      ["building", demo.childHousing, 1.04],
    ];
    const stock = { food: child.food, cloth: child.cloth, building: child.housing };
    let cashLeft = Math.max(0.0, child.cash);
    for (const [good, target, bidMultiplier] of targets) {
      let gap = Math.max(0.0, target - stock[good]);
      if (gap <= 1e-9 || cashLeft <= 1e-9) continue;
      const bid = (prices[good] ?? 1.0) * bidMultiplier;
      if (good !== "food") gap *= Math.max(0.0, this.workerDemandScale);
      const quantity = Math.min(gap, cashLeft / Math.max(bid, 1e-9));
      if (quantity <= 1e-9) continue;
      this.market.submitBuy(child, good, quantity, bid);
      cashLeft -= quantity * bid;
    }
  }

  // ------------------------------------------------------------------
  // Expectations / plans
  // ------------------------------------------------------------------
  _updateExpectationsAndPlans() {
    const activeByIndustry = {};
    const capacityByIndustry = {};
    for (const industry of INDUSTRIES) {
      activeByIndustry[industry] = this.activeEnterprises(industry).length;
      capacityByIndustry[industry] = 0.0;
    }
    for (const enterprise of this.activeEnterprises()) {
      const workers = this.enterpriseWorkers(enterprise);
      const skill = workers.length ? Math.max(1.0, averageSkill(workers)) : 1.0;
      capacityByIndustry[enterprise.industry] += capacityAtSkillOne(enterprise) * skill;
    }
    let foodStock = 0.0;
    for (const enterprise of this.activeEnterprises("agriculture")) foodStock += enterprise.inv("food");
    const monthlyFoodNeed = Math.max(1.0, this.feedingUnits() * C.FOOD_PER_WORKER);
    const essential = new Set(["coal", "iron_ore", "steel", "brick", "machinery", "building", "fertilizer"]);

    for (const enterprise of this.activeEnterprises()) {
      const params = SECTOR_PARAMS.get(enterprise.industry);
      const out = params.output;
      const history = this.market.history[out];
      const lastSales = enterprise.lastSales[out] || 0.0;
      const workers = this.enterpriseWorkers(enterprise);
      const skill = workers.length ? Math.max(1.0, averageSkill(workers)) : 1.0;
      const capacity = capacityAtSkillOne(enterprise) * skill;
      const totalCapacity = capacityByIndustry[enterprise.industry];
      const share = totalCapacity > 1e-9
        ? capacity / totalCapacity
        : 1.0 / Math.max(1, activeByIndustry[enterprise.industry]);
      const observed = ((history.demand || 0.0) + (history.unmet || 0.0)) * share;
      if (enterprise.demandForecast <= 1e-9) {
        enterprise.demandForecast = Math.max(observed, capacity * 0.1);
      } else {
        enterprise.demandForecast = 0.7 * enterprise.demandForecast + 0.3 * observed;
      }
      enterprise.lastDemand = observed;
      enterprise.lastUnmet = Math.max(0.0, observed - lastSales);
      enterprise.lastFillRate = observed > 1e-9 ? lastSales / observed : 1.0;

      if (capacity <= 1e-9) {
        enterprise.planRatio = 0.0;
        enterprise.plannedOutput = 0.0;
        continue;
      }
      const inventory = enterprise.inv(out);
      const target = enterprise.targetInventoryMonths * enterprise.demandForecast;
      const desired = enterprise.demandForecast + Math.max(0.0, target - inventory) / 6.0;
      let plan = desired / capacity;
      const demandRatio = enterprise.demandForecast / Math.max(capacity, 1e-9);
      if (inventory > 12.0 * Math.max(enterprise.demandForecast, capacity * 0.02)) {
        plan = essential.has(out) ? Math.min(plan, 0.02) : 0.0;
      } else if (essential.has(out)) {
        plan = Math.max(plan, Math.min(0.1, Math.max(0.0, 0.9 * demandRatio)));
      }
      if (out === "food" && foodStock < 3.0 * monthlyFoodNeed) plan = Math.max(plan, 1.0);
      enterprise.planRatio = Math.max(0.0, Math.min(1.0, plan));
      enterprise.plannedOutput = capacity * enterprise.planRatio;
    }
  }

  // ------------------------------------------------------------------
  // Labor market / wages
  // ------------------------------------------------------------------
  _laborMarket() {
    const prices = this.market.referencePrices;
    const floor = wageFloor(prices) * (this.wageFloorScale ?? 1.0);
    const laborForce = this.laborForceWorkers();
    let employedCount = 0;
    for (const worker of laborForce) if (worker.employed) employedCount += 1;
    this._wageUnemployment = 1.0 - employedCount / Math.max(1, laborForce.length);

    const vacancies = {};
    const offers = {};
    let foodStock = 0.0;
    for (const enterprise of this.activeEnterprises("agriculture")) foodStock += enterprise.inv("food");
    const foodNeed = Math.max(1.0, this.feedingUnits() * C.FOOD_PER_WORKER);
    const foodSecurity = foodStock < 3.0 * foodNeed;
    const fertilizerShort = C.FERTILIZER_HIRING_PRIORITY && this.fertilizerSupplyShort();

    const hiringOrder = (enterpriseId) => {
      const enterprise = this.enterprises.get(enterpriseId);
      const critical = fertilizerShort && enterprise.industry === "fertilizer_factory" ? 0 : 1;
      return [critical, -(offers[enterpriseId] || 0.0)];
    };
    const compareHiring = (a, b) => {
      const oa = hiringOrder(a);
      const ob = hiringOrder(b);
      return (oa[0] - ob[0]) || (oa[1] - ob[1]);
    };

    for (const enterprise of this.activeEnterprises()) {
      let workers = this.enterpriseWorkers(enterprise);
      if (enterprise.isHousehold && enterprise.industry === "service") {
        for (const worker of workers) {
          worker.wage = 0.0;
          worker.hours = worker.chooseHours(prices);
        }
        offers[enterprise.id] = 0.0;
        vacancies[enterprise.id] = 0;
        continue;
      }
      const required = desiredWorkers(enterprise, enterprise.planRatio);
      let effective = 0.0;
      for (const worker of workers) effective += worker.effectiveLabor;
      let target;
      if (required <= 0) target = 0;
      else {
        const avgEff = workers.length ? effective / workers.length : 1.0;
        target = Math.max(1, Math.ceil(required / Math.max(avgEff, 0.5)));
      }
      if (enterprise.industry === "agriculture" && enterprise.isHousehold) target = Math.max(1, target);

      if (workers.length > target) {
        const removable = workers
          .filter((worker) => !worker.isOwnerOperator)
          .slice()
          .sort((a, b) => (Number(a.isOwnerOperator) - Number(b.isOwnerOperator)) || (a.skill - b.skill));
        const excess = workers.length - target;
        let fired = 0;
        for (const worker of removable.slice(0, excess)) {
          if (worker.employerId === enterprise.id) fired += 1;
          worker.employerId = null;
          worker.wage = 0.0;
          enterprise.workers = enterprise.workers.filter((id) => id !== worker.id);
        }
        workers = this.enterpriseWorkers(enterprise);
        if (fired) {
          employedCount = Math.max(0, employedCount - fired);
          this._wageUnemployment = 1.0 - employedCount / Math.max(1, laborForce.length);
        }
      }
      let offer = enterpriseWageOffer(this, enterprise);
      if (foodSecurity && enterprise.industry === "agriculture") {
        offer = Math.min(offer * 1.30, C.WAGE_BASE * 5.0);
      }
      offers[enterprise.id] = offer;
      for (const worker of workers) {
        if (this._isHouseholdFarmOwner(enterprise, worker)) worker.wage = 0.0;
        else worker.wage = offer;
        worker.hours = worker.chooseHours(prices);
        worker.industry = enterprise.industry;
      }
      vacancies[enterprise.id] = Math.max(0, target - workers.length);
    }

    const unemployed = [];
    for (const worker of this.workers.values()) {
      if (worker.alive && worker.isWorkingAge && !worker.employed && !worker.isOwnerOperator) {
        unemployed.push(worker);
      }
    }
    unemployed.sort((a, b) => (a.cash - b.cash) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
    let hiring = Object.keys(vacancies).filter((id) => vacancies[id] > 0).sort(compareHiring);
    for (const enterpriseId of hiring) {
      const enterprise = this.enterprises.get(enterpriseId);
      let remaining = vacancies[enterpriseId];
      for (const worker of unemployed.slice()) {
        if (remaining <= 0) break;
        const reservation = floor * (worker.cash < 5.0 ? 0.70 : 1.0);
        if (offers[enterpriseId] + 1e-9 < reservation) continue;
        this._hire(enterprise, worker, offers[enterpriseId], prices);
        unemployed.splice(unemployed.indexOf(worker), 1);
        remaining -= 1;
      }
      vacancies[enterpriseId] = remaining;
    }

    hiring = Object.keys(vacancies).filter((id) => vacancies[id] > 0).sort(compareHiring);
    let switches = 0;
    if (hiring.length) {
      for (const worker of this.workers.values()) {
        if (switches >= 20 || !hiring.length) break;
        if (!worker.alive || !worker.isWorkingAge || !worker.employed || worker.isOwnerOperator) continue;
        const bestId = hiring[0];
        const bestOffer = offers[bestId];
        if (!shouldSwitch(worker.wage, bestOffer)) continue;
        const oldEnterprise = this.enterprises.get(worker.employerId || "");
        if (!oldEnterprise) continue;
        if (oldEnterprise.id === bestId) continue;
        if (oldEnterprise.workers.includes(worker.id)) {
          oldEnterprise.workers = oldEnterprise.workers.filter((id) => id !== worker.id);
        }
        this._hire(this.enterprises.get(bestId), worker, bestOffer, prices);
        vacancies[bestId] -= 1;
        switches += 1;
        if (vacancies[bestId] <= 0) {
          hiring.shift();
          if (!hiring.length) break;
        }
      }
    }

    this._serviceSelfEmployment(prices);
    if (this.government !== null && this.government.jobGuarantee) this._jobGuarantee();
    this._averageWageCache = null;
    this._wageUnemployment = null;
  }
  _hire(enterprise, worker, offer, prices) {
    if (worker.industry !== enterprise.industry) worker.skill = Math.max(1.0, worker.skill * 0.75);
    if (this.government !== null && this.government.jgWorkers.includes(worker.id)) {
      this.government.jgWorkers = this.government.jgWorkers.filter((id) => id !== worker.id);
    }
    worker.industry = enterprise.industry;
    worker.employerId = enterprise.id;
    worker.wage = offer;
    worker.hours = worker.chooseHours(prices);
    if (!enterprise.workers.includes(worker.id)) enterprise.workers.push(worker.id);
  }
  _serviceSelfEmployment(prices) {
    let serviceFirms = this.activeEnterprises("service");
    const params = SECTOR_PARAMS.get("service");
    if (serviceFirms.length >= params.maxFirms) return;
    const history = this.market.history.service;
    const demand = history.demand || 0.0;
    const supply = history.supply || 0.0;
    const unmet = history.unmet || 0.0;
    const price = prices.service || 0.0;
    const capacity = EQUIPMENT.get("service_t0").capacity;
    if (price * capacity < C.SERVICE_ENTRY_MIN_REVENUE) return;
    const candidates = [];
    for (const worker of this.workers.values()) {
      if (worker.alive && worker.isWorkingAge && !worker.employed && !worker.isOwnerOperator) {
        candidates.push(worker);
      }
    }
    if (!candidates.length) return;
    // A2 releases labour from agriculture/textiles/construction. When the
    // service market is already supplied, allow a gradual low-wage self-
    // employment buffer as long as service revenue is viable; otherwise the
    // demand-deficient unemployed have no absorption path.
    const slackEntry = this.durablesA2 && demand > 1e-9 &&
      (this._wageUnemployment || 0.0) > 0.04;
    if (!slackEntry && (demand <= 1e-9 || supply + 1e-9 >= demand || unmet <= 0.25)) return;
    candidates.sort((a, b) => (a.cash - b.cash) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
    const target = slackEntry
      ? Math.min(10, Math.max(1, Math.ceil(candidates.length * 0.03)))
      : Math.min(C.MAX_SERVICE_ENTRIES_PER_MONTH, Math.max(1, Math.ceil(unmet / Math.max(capacity, 1e-9))));
    let created = 0;
    for (const worker of candidates) {
      if (created >= target || serviceFirms.length >= params.maxFirms) break;
      const enterprise = this.createEnterprise({
        industry: "service", ownerId: worker.id, cash: 0.0,
        isHousehold: true, modernizationCapable: false,
      });
      enterprise.addEquipment("service_t0", 1);
      enterprise.demandForecast = capacity;
      enterprise.targetInventoryMonths = 0.0;
      worker.skill = Math.max(1.0, worker.skill * 0.75);
      worker.industry = "service";
      worker.employerId = enterprise.id;
      worker.wage = 0.0;
      worker.hours = worker.chooseHours(prices);
      worker.isOwnerOperator = true;
      enterprise.workers.push(worker.id);
      serviceFirms.push(enterprise);
      created += 1;
    }
  }

  // ------------------------------------------------------------------
  // Price bands / banking / wages / government
  // ------------------------------------------------------------------
  _updatePriceBands() {
    const prices = this.market.referencePrices;
    this.market.priceRegime = this.priceRegime;
    if (this.priceRegime === "free") {
      for (const good of GOODS) {
        delete this.market.floors[good];
        delete this.market.ceilings[good];
      }
      const costs = {};
      const markups = {};
      for (const good of GOODS) { costs[good] = []; markups[good] = []; }
      for (const enterprise of this.activeEnterprises()) {
        const good = SECTOR_PARAMS.get(enterprise.industry).output;
        const workers = this.enterpriseWorkers(enterprise);
        let cost = normalUnitCost(this, enterprise, prices, workers);
        if (cost <= 1e-9) cost = pricingUnitCost(this, enterprise, prices, workers);
        if (cost > 1e-6) costs[good].push(cost);
        if (!enterprise.markupInitialized && cost > 1e-9) {
          const normal = Math.min(
            C.FREE_MARKUP_INIT_MAX,
            Math.max(C.FREE_MARKUP_INIT_MIN, INITIAL_PRICES[good] / cost - 1.0),
          );
          enterprise.markup = normal;
          enterprise.markupNormal = normal;
          enterprise.markupInitialized = true;
        }
        markups[good].push(Math.min(C.FREE_MARKUP_MAX, Math.max(C.FREE_MARKUP_MIN, enterprise.markup)));
      }
      for (const good of GOODS) {
        if (costs[good].length) {
          costs[good].sort((a, b) => a - b);
          this.market.costAnchors[good] = costs[good][Math.floor(costs[good].length / 2)];
        } else delete this.market.costAnchors[good];
        if (markups[good].length) {
          markups[good].sort((a, b) => a - b);
          this.market.markupAnchors[good] = markups[good][Math.floor(markups[good].length / 2)];
        } else delete this.market.markupAnchors[good];
      }
      return;
    }
    const byGood = {};
    for (const good of GOODS) byGood[good] = [];
    for (const enterprise of this.activeEnterprises()) {
      const good = SECTOR_PARAMS.get(enterprise.industry).output;
      const workers = this.enterpriseWorkers(enterprise);
      const cost = pricingUnitCost(this, enterprise, prices, workers);
      if (cost > 1e-6) byGood[good].push(cost);
    }
    for (const good of GOODS) {
      const list = byGood[good];
      if (!list.length) continue;
      list.sort((a, b) => a - b);
      const median = list[Math.floor(list.length / 2)];
      const initial = INITIAL_PRICES[good];
      this.market.ceilings[good] = Math.min(Math.max(median * 2.5, initial * 1.5), initial * 4.0);
      this.market.floors[good] = Math.min(Math.max(median * 0.90, initial * 0.60), initial * 2.0);
    }
  }
  _bankIntermediation() {
    for (const capitalist of this.capitalists.values()) {
      if (capitalist.cash > 10000.0) this.bank.deposit(capitalist, (capitalist.cash - 10000.0) * 0.10);
    }
    for (const worker of this.workers.values()) {
      if (worker.alive && worker.isWorkingAge && worker.cash > 1000.0) {
        this.bank.deposit(worker, (worker.cash - 1000.0) * 0.02);
      }
    }
    const agents = new Map();
    for (const [id, worker] of this.workers) agents.set(id, worker);
    for (const [id, capitalist] of this.capitalists) agents.set(id, capitalist);
    this.bank.payDepositInterest(agents);
  }
  _payWages() {
    const gov = this.government;
    const pensionRate = gov ? gov.pensionTaxRate : 0.0;
    for (const enterprise of this.activeEnterprises()) {
      const workers = this.enterpriseWorkers(enterprise)
        .filter((worker) => !this._isHouseholdFarmOwner(enterprise, worker));
      let bill = 0.0;
      for (const worker of workers) bill += worker.wage * worker.effectiveLabor;
      if (bill <= 1e-9) continue;
      if (enterprise.cash < bill) {
        let owner = this.capitalists.get(enterprise.ownerId);
        if (!owner) owner = this.workers.get(enterprise.ownerId);
        if (owner && owner.cash > 0) {
          const injection = Math.min(bill - enterprise.cash, owner.cash);
          owner.cash -= injection;
          enterprise.cash += injection;
        }
      }
      if (enterprise.cash < bill) {
        const shortfall = bill - enterprise.cash;
        this.bank.lend(enterprise, shortfall * Math.max(0.0, this.lendingScale));
      }
      let factor = 1.0;
      if (enterprise.cash < bill) factor = Math.max(0.0, enterprise.cash / bill);
      for (const worker of workers) {
        const gross = worker.wage * worker.effectiveLabor * factor;
        let contribution = 0.0;
        if (pensionRate > 0 && gov) {
          contribution = gross * pensionRate;
          gov.cash += contribution;
          gov.pensionFund += contribution;
          gov.pensionContributions += contribution;
          gov.pensionRevenue += contribution;
        }
        enterprise.cash -= gross;
        worker.cash += gross - contribution;
        enterprise.monthWages += gross;
      }
    }
  }
  _jobGuarantee() {
    const gov = this.government;
    if (!gov || !gov.jobGuarantee) return;
    if (gov.jgMaxWorkers > 0 && gov.jgWorkers.length >= gov.jgMaxWorkers) return;
    const unemployed = [];
    for (const worker of this.workers.values()) {
      if (worker.alive && worker.isWorkingAge && !worker.employed && !worker.isOwnerOperator) {
        unemployed.push(worker);
      }
    }
    unemployed.sort((a, b) => (a.cash - b.cash) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
    for (const worker of unemployed) {
      if (gov.jgMaxWorkers > 0 && gov.jgWorkers.length >= gov.jgMaxWorkers) break;
      worker.employerId = "GOV";
      worker.wage = gov.jgWage;
      worker.standardHours = Math.max(1, Math.trunc(this.workHours || 16));
      worker.hours = worker.standardHours;
      worker.industry = "construction";
      worker.uiMonths = 0;
      gov.jgWorkers.push(worker.id);
    }
  }
  _payGovernmentWages() {
    const gov = this.government;
    if (!gov || !gov.jgWorkers.length) return;
    const alive = [];
    let bill = 0.0;
    for (const workerId of gov.jgWorkers) {
      const worker = this.workers.get(workerId);
      if (!worker || !worker.alive) continue;
      alive.push(workerId);
      bill += worker.wage * worker.effectiveLabor;
    }
    gov.jgWorkers = alive;
    if (bill <= 1e-9) return;
    this._governmentFinance(Math.max(0.0, bill - gov.cash), "wages");
    const factor = bill > 0 ? Math.min(1.0, gov.cash / bill) : 0.0;
    const pensionRate = gov.pensionTaxRate;
    for (const workerId of gov.jgWorkers) {
      const worker = this.workers.get(workerId);
      const gross = worker.wage * worker.effectiveLabor * factor;
      const contribution = pensionRate > 0 ? gross * pensionRate : 0.0;
      gov.cash -= gross - contribution;
      worker.cash += gross - contribution;
      gov.pensionFund += contribution;
      gov.pensionContributions += contribution;
      gov.pensionRevenue += contribution;
    }
    gov.spending += bill * factor;
  }
  _produceGovernment() {
    const gov = this.government;
    if (!gov || !gov.jgWorkers.length) return;
    let labor = 0.0;
    for (const workerId of gov.jgWorkers) {
      const worker = this.workers.get(workerId);
      if (worker && worker.alive) labor += worker.effectiveLabor;
    }
    const output = 0.4 * labor;
    gov.inventory.building += output;
    gov.publicCapital += output;
  }
  _governmentFinance(amount, purpose) {
    const gov = this.government;
    if (!gov || amount <= 1e-9) return 0.0;
    const need = Math.max(0.0, amount);
    if (need <= 1e-9) return 0.0;
    if (gov.fiatMoney) {
      gov.cash += need;
      gov.centralBankMoney += need;
      gov.debt += need;
      gov.bondHolders.set("CENTRAL_BANK", (gov.bondHolders.get("CENTRAL_BANK") || 0.0) + need);
      return need;
    }
    const buyers = [];
    for (const capitalist of this.capitalists.values()) {
      if (capitalist.cash > 0) buyers.push({ id: capitalist.id, cash: capitalist.cash, capitalist });
    }
    buyers.push({ id: "BANK", cash: this.bank.cash, capitalist: null });
    buyers.sort((a, b) => b.cash - a.cash);
    let raised = 0.0;
    for (const buyer of buyers) {
      if (raised >= need) break;
      const take = Math.min(need - raised, buyer.cash * 0.5);
      if (take <= 1e-9) continue;
      if (buyer.id === "BANK") this.bank.cash -= take;
      else buyer.capitalist.cash -= take;
      gov.cash += take;
      gov.debt += take;
      gov.bondHolders.set(buyer.id, (gov.bondHolders.get(buyer.id) || 0.0) + take);
      raised += take;
    }
    return raised;
  }
  _submitFoodReserveOrders() {
    const reserve = this.foodReserve;
    const price = this.market.referencePrices.food;
    const initial = INITIAL_PRICES.food;
    const monthlyNeed = Math.max(1.0, this.feedingUnits() * C.FOOD_PER_WORKER);
    const reliefBuffer = C.FOOD_RELIEF_BUFFER_MONTHS * monthlyNeed;
    if (price > 1.15 * initial && reserve.food > reliefBuffer + 1e-9) {
      const quantity = Math.min(reserve.food - reliefBuffer, 0.50 * monthlyNeed);
      if (quantity > 1e-9) this.market.submitSell(reserve, "food", quantity, price * 0.95);
    } else if (price < 0.85 * initial && reserve.cash > 1e-9) {
      const quantity = Math.min(0.10 * monthlyNeed, reserve.cash / Math.max(price, 1e-9));
      if (quantity > 1e-9) this.market.submitBuy(reserve, "food", quantity, price * 1.05);
    }
  }
  _submitGovernmentOrders() {
    const gov = this.government;
    if (!gov || !gov.active) return;
    const gdp = this.stats.length ? this.stats[this.stats.length - 1].gdp : 0.0;
    let budget = gov.publicInvestmentRate * gdp;
    if (gov.publicInvestmentCountercyclical > 0 && this.stats.length) {
      const unemployment = this.stats[this.stats.length - 1].unemployment_rate;
      budget += gov.publicInvestmentCountercyclical * Math.max(0.0, 0.07 - unemployment) * gdp;
    }
    if (gov.cash > 5000.0 && gdp > 0) budget += Math.min(gov.cash - 5000.0, 0.05 * gdp);
    gov.publicInvestmentBudget = Math.max(0.0, budget);
    if (budget <= 1e-9) return;
    this._governmentFinance(Math.max(0.0, budget - gov.cash), "public_investment");
    const spend = Math.min(budget, gov.cash);
    if (spend <= 1e-9) return;
    const prices = this.market.referencePrices;
    for (const [good, weight] of [["building", 0.6], ["machinery", 0.4]]) {
      const target = spend * weight;
      const price = prices[good] ?? 1.0;
      const quantity = target / Math.max(price, 1e-9);
      if (quantity > 1e-9) this.market.submitBuy(gov, good, quantity, price * 1.05);
    }
  }
  _governmentSettlement() {
    const gov = this.government;
    if (!gov || !gov.active) return;
    for (const worker of this.workers.values()) {
      if (!worker.alive || !worker.employed) continue;
      const income = worker.wage * worker.effectiveLabor;
      if (income <= 0) continue;
      const tax = Math.min(worker.cash, income * gov.taxRateWage);
      worker.cash -= tax;
      gov.cash += tax;
      gov.taxRevenue += tax;
    }
    for (const enterprise of this.activeEnterprises()) {
      if (enterprise.lastProfit <= 0) continue;
      const tax = Math.min(enterprise.cash, enterprise.lastProfit * gov.taxRateProfit);
      enterprise.cash -= tax;
      gov.cash += tax;
      gov.taxRevenue += tax;
    }
    const avgWage = this.averageWage();
    for (const worker of this.workers.values()) {
      if (worker.alive) worker.lastUiIncome = 0.0;
    }
    for (const worker of this.workers.values()) {
      if (!worker.alive) continue;
      if (worker.isChild || worker.retired) continue;
      if (worker.employed) { worker.uiMonths = 0; continue; }
      if (worker.isOwnerOperator) continue;
      if (gov.uiDuration > 0 && worker.uiMonths >= gov.uiDuration) continue;
      const benefit = avgWage * gov.uiReplacement;
      if (benefit <= 0) continue;
      this._governmentFinance(Math.max(0.0, benefit - gov.cash), "ui");
      const paid = Math.min(benefit, gov.cash);
      if (paid > 0) {
        gov.cash -= paid;
        worker.cash += paid;
        gov.transfers += paid;
        worker.lastUiIncome = paid;
      }
      worker.uiMonths += 1;
    }
    if (gov.pensionReplacement > 0) {
      const retirementAge = this.demographics.retirementAgeMonths;
      const retirees = [];
      for (const worker of this.workers.values()) {
        if (!worker.alive) continue;
        if (worker.retired || (retirementAge > 0 && worker.isOwnerOperator &&
            !worker.isChild && worker.ageMonths >= retirementAge)) {
          retirees.push(worker);
        }
      }
      for (const worker of retirees) worker.pensionIncome = 0.0;
      const foodLine = C.FOOD_PER_WORKER * (this.market.referencePrices.food || 0.0);
      const benefit = Math.max(gov.pensionReplacement * avgWage, foodLine);
      const due = benefit * retirees.length;
      if (due > 1e-9) {
        if (gov.cash < due) this._governmentFinance(due - gov.cash, "pension");
        if (gov.pensionFund < due) {
          const topup = Math.min(due - gov.pensionFund, Math.max(0.0, gov.cash));
          if (topup > 0) {
            gov.pensionFund += topup;
            gov.pensionSubsidy += topup;
            gov.pensionRevenue += topup;
          }
        }
        const factor = Math.min(1.0, gov.pensionFund / due, gov.cash / due);
        if (factor < 1.0 - 1e-9) this._pensionShortfall += due * (1.0 - factor);
        let paidTotal = 0.0;
        for (const worker of retirees) {
          const paid = benefit * factor;
          if (paid <= 1e-9) continue;
          gov.cash -= paid;
          gov.pensionFund -= paid;
          worker.cash += paid;
          worker.pensionIncome = paid;
          paidTotal += paid;
        }
        gov.pensionSpending += paidTotal;
        if (gov.pensionFund < 0 && gov.pensionFund > -1e-6) gov.pensionFund = 0.0;
      }
    }
    if (gov.pensionRevenue > 0 || gov.pensionSpending > 0) {
      gov.pensionBalance = gov.pensionRevenue - gov.pensionSpending;
    }
    if (gov.debt > 0 && gov.bondHolders.size) {
      const interest = gov.debt * this.bank.interestRate;
      this._governmentFinance(Math.max(0.0, interest - gov.cash), "interest");
      const paid = Math.min(interest, gov.cash);
      if (paid > 0) {
        gov.cash -= paid;
        gov.interestPaid += paid;
        let total = 0.0;
        for (const amount of gov.bondHolders.values()) total += amount;
        total = total || 1.0;
        for (const [holderId, amount] of Array.from(gov.bondHolders.entries())) {
          const share = amount / total;
          if (holderId === "BANK" || holderId === "CENTRAL_BANK") this.bank.cash += paid * share;
          else {
            const holder = this.capitalists.get(holderId);
            if (holder) holder.cash += paid * share;
            else this.bank.cash += paid * share;
          }
        }
      }
    }
    gov.spending += this.market.governmentSpending;
    gov.deficit = gov.spending + gov.transfers + gov.pensionSpending + gov.interestPaid -
      gov.taxRevenue - gov.pensionContributions;
  }
  _produceAll() {
    for (const enterprise of this.activeEnterprises()) {
      if (enterprise.industry === "agriculture") {
        enterprise.useFertilizer = wantsFertilizer(this, enterprise);
      }
      const output = produce(this, enterprise);
      const outGood = SECTOR_PARAMS.get(enterprise.industry).output;
      this.productionMonth[outGood] += output;
    }
  }
  _collectFoodReliefLevy() {
    const monthlyNeed = Math.max(1.0, this.feedingUnits() * C.FOOD_PER_WORKER);
    const target = 3.0 * monthlyNeed;
    const reserve = this.foodReserve;
    if (reserve.food >= target) return;
    const rate = Math.min(0.25, 0.25 * (target - reserve.food) / target);
    if (rate <= 1e-9) return;
    let levied = 0.0;
    let remainingTarget = Math.max(0.0, target - reserve.food);
    for (const enterprise of this.activeEnterprises("agriculture")) {
      const available = enterprise.inv("food");
      if (available <= 1e-9) continue;
      const take = this.durablesA2
        // A2 farms can hold large inventories while current output is low
        // (durable inventory smoothing). Levy stock as well as current output
        // so the relief reserve does not starve next to full granaries.
        ? Math.min(available, Math.max(enterprise.lastOutput * rate, available * rate),
          remainingTarget)
        : Math.min(available, enterprise.lastOutput * rate);
      if (take <= 1e-9) continue;
      enterprise.inventory.food = available - take;
      reserve.food += take;
      levied += take;
      if (this.durablesA2) {
        remainingTarget -= take;
        if (remainingTarget <= 1e-9) break;
      }
    }
    this._foodLevyThisMonth = levied;
  }
  _distributeFoodRelief() {
    const reserve = this.foodReserve;
    if (reserve.food <= 1e-9) return;
    const demo = this.demographics;
    let cap = Math.min(reserve.food, Math.max(10.0, 0.25 * reserve.food));
    const candidates = [];
    for (const worker of this.workers.values()) {
      if (!worker.alive) continue;
      const target = worker.isChild ? demo.childFood : C.FOOD_PER_WORKER;
      if (worker.hungerMonths >= 1 && worker.food + 1e-9 < target) {
        candidates.push({ hunger: worker.hungerMonths, cash: worker.cash, id: worker.id, worker });
      }
    }
    if (!candidates.length) return;
    candidates.sort((a, b) => (b.hunger - a.hunger) || (a.cash - b.cash) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
    let relieved = 0.0;
    let unmet = 0.0;
    for (const candidate of candidates) {
      const worker = candidate.worker;
      const target = worker.isChild ? demo.childFood : C.FOOD_PER_WORKER;
      const need = Math.max(0.0, target - worker.food);
      if (need <= 1e-9) continue;
      if (cap <= 1e-9) { unmet += need; continue; }
      const take = Math.min(need, cap);
      worker.food += take;
      reserve.food -= take;
      cap -= take;
      relieved += take;
    }
    this._foodReliefThisMonth = relieved;
    this._foodReliefShortfall = unmet;
  }

  // ------------------------------------------------------------------
  // Investment decisions
  // ------------------------------------------------------------------
  _investmentDecisions() {
    let started = 0;
    for (const industry of Object.keys(MANUAL_EQUIPMENT)) {
      const activeManual = this.activeEnterprises(industry);
      const hasCapacity = activeManual.some((enterprise) =>
        capacityAtSkillOne(enterprise) > 1e-9);
      // A2 retirement can leave an industry with active shells but no
      // productive equipment; allow a new manual workshop so the supply
      // chain does not deadlock on expensive replacement capital.
      if (!activeManual.length || (this.durablesA2 && !hasCapacity)) {
        this._bootstrapManualEntry(industry, MANUAL_EQUIPMENT[industry]);
      }
    }

    // Replacement demand is honoured before expansion so an enterprise whose
    // vintage just retired does not silently lose capacity for years.
    if (this.durablesA2) {
      const replacement = this.activeEnterprises()
        .filter((enterprise) => (enterprise.replacementDemand || 0) > 0 &&
          !(enterprise.industry === "agriculture" && enterprise.isHousehold))
        .slice()
        .sort((a, b) => (b.replacementDemand - a.replacementDemand) ||
          (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
      for (const enterprise of replacement) {
        if (started >= C.MAX_PROJECTS_PER_TICK) break;
        let key = null;
        if (enterprise.industry === "agriculture") {
          const choice = bestEquipmentChoice(
            this, enterprise.industry, Math.max(0.0, enterprise.cash - 100.0),
            undefined, enterprise,
          );
          if (choice) key = choice.key;
        }
        if (!key) {
          for (const [candidate, quantity] of Object.entries(enterprise.replacementByKey || {})) {
            if (quantity > 1e-9) { key = candidate; break; }
          }
        }
        if (!key) {
          let bestCount = -1;
          let bestCapacity = -1;
          for (const [candidate, count] of enterprise.equipment) {
            if (count <= 1e-9) continue;
            const cap = EQUIPMENT.get(candidate).capacity;
            if (count > bestCount || (count === bestCount && cap > bestCapacity)) {
              key = candidate;
              bestCount = count;
              bestCapacity = cap;
            }
          }
        }
        if (!key) continue;
        if (this._startProject(enterprise, key, false, true, true)) {
          enterprise.replacementDemand = Math.max(0.0, enterprise.replacementDemand - 1.0);
          const pending = enterprise.replacementByKey[key] || 0.0;
          if (pending > 1e-9) {
            enterprise.replacementByKey[key] = Math.max(0.0, pending - 1.0);
          }
          this._replacementProjectsStarted += 1;
          started += 1;
        }
      }
    }

    for (const enterprise of this.activeEnterprises()) {
      if (started >= C.MAX_PROJECTS_PER_TICK) break;
      if (!enterprise.equipment.size) continue;
      if (enterprise.industry === "agriculture" && enterprise.isHousehold) continue;
      if (this.durablesA2 && enterprise.industry === "agriculture") continue;
      const outGood = SECTOR_PARAMS.get(enterprise.industry).output;
      if (enterprise.planRatio < 0.2 &&
          enterprise.inv(outGood) > 6.0 * Math.max(enterprise.demandForecast, 1e-9)) continue;
      if (this.tick - enterprise.lastInvestTick < 12) continue;
      // Python max(equipment, key=(count, capacity)): highest count, then
      // highest capacity; ties keep the first insertion-ordered key.
      let bestKey = null;
      let bestCount = -1;
      let bestCapacity = -1;
      for (const [candidate, count] of enterprise.equipment) {
        const cap = EQUIPMENT.get(candidate).capacity;
        if (count > bestCount || (count === bestCount && cap > bestCapacity)) {
          bestKey = candidate;
          bestCount = count;
          bestCapacity = cap;
        }
      }
      if (this._startProject(enterprise, bestKey)) started += 1;
    }

    const farms = this.activeEnterprises("agriculture")
      .filter((enterprise) => !enterprise.isHousehold)
      .slice()
      .sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
    let activeAgriProjects = 0;
    for (const project of this.projects.values()) {
      if (project.active && project.industry === "agriculture") activeAgriProjects += 1;
    }
    const agriCap = Math.max(1, Math.min(3, Math.floor(C.MAX_ACTIVE_PROJECTS / 3)));
    let farmsStarted = 0;
    for (const enterprise of farms) {
      if (started >= C.MAX_PROJECTS_PER_TICK || farmsStarted >= 2 || activeAgriProjects >= agriCap) break;
      const choice = shouldInvest(this, enterprise);
      if (choice === null) continue;
      if (this._startProject(enterprise, choice.key, false, true)) {
        started += 1;
        farmsStarted += 1;
        activeAgriProjects += 1;
      }
    }

    const entryCandidates = [];
    for (const industry of INDUSTRIES) {
      if (industry === "agriculture") continue;
      if (industry === "auto_factory" && !this.durablesA2) continue;
      const params = SECTOR_PARAMS.get(industry);
      if (this.activeEnterprises(industry).length >= params.maxFirms) continue;
      let choice;
      if (industry === "fertilizer_factory" && !this.activeEnterprises(industry).length) {
        let potentialDemand = 0.0;
        for (const farm of this.activeEnterprises("agriculture")) {
          if (farm.modernizationCapable) potentialDemand += farm.land * C.FERTILIZER_PER_MU;
        }
        choice = bestEquipmentChoice(this, industry, 100000.0, Math.max(potentialDemand, 1.0));
      } else {
        choice = bestEquipmentChoice(this, industry, 100000.0);
      }
      if (choice === null) continue;
      if (choice.roi >= C.INVESTMENT_HURDLE) entryCandidates.push({ roi: choice.roi, industry, key: choice.key });
    }
    entryCandidates.sort((a, b) => b.roi - a.roi);
    if (entryCandidates.length && started < C.MAX_PROJECTS_PER_TICK) {
      const noFertilizer = !this.activeEnterprises("fertilizer_factory").length;
      let preferred = null;
      if (noFertilizer) preferred = entryCandidates.find((candidate) => candidate.industry === "fertilizer_factory") || null;
      const selected = preferred || entryCandidates[0];
      const cost = equipmentCost(selected.key, this.market.referencePrices);
      const candidates = [];
      for (const capitalist of this.capitalists.values()) {
        if (capitalist.cash >= cost + 2000.0) candidates.push(capitalist);
      }
      candidates.sort((a, b) => {
        const owned = a.ownedCount(this.enterprises) - b.ownedCount(this.enterprises);
        if (owned !== 0) return owned;
        if (b.cash !== a.cash) return b.cash - a.cash;
        return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
      });
      if (candidates.length) {
        const owner = candidates[0];
        const budget = Math.min(owner.cash * 0.5, cost * 2.0 + 3000.0);
        if (budget >= cost + 1000.0) {
          owner.cash -= budget;
          const enterprise = this.createEnterprise({
            industry: selected.industry, ownerId: owner.id, cash: budget,
            modernizationCapable: true,
          });
          if (this._startProject(enterprise, selected.key, true)) started += 1;
          else {
            enterprise.active = false;
            owner.cash += enterprise.cash;
            enterprise.cash = 0.0;
          }
        }
      }
    }

    const priority = {
      machinery_factory: 0, steel_mill: 1, auto_factory: 2, brick_factory: 3,
      construction: 4, fertilizer_factory: 5, textile_mill: 6,
      coal_mine: 7, iron_mine: 8,
    };
    const existing = this.activeEnterprises().slice().sort((a, b) => {
      const pa = priority[a.industry] ?? 99;
      const pb = priority[b.industry] ?? 99;
      if (pa !== pb) return pa - pb;
      return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
    });
    for (const enterprise of existing) {
      if (started >= C.MAX_PROJECTS_PER_TICK) break;
      if (enterprise.industry === "agriculture") continue;
      const choice = shouldInvest(this, enterprise);
      if (choice === null) continue;
      if (this._startProject(enterprise, choice.key)) started += 1;
    }
  }

  // ------------------------------------------------------------------
  // Orders
  // ------------------------------------------------------------------
  _submitSellOrders() {
    const prices = this.market.referencePrices;
    for (const enterprise of this.activeEnterprises()) {
      const params = SECTOR_PARAMS.get(enterprise.industry);
      const quantity = enterprise.inv(params.output);
      if (quantity > 1e-9) {
        const ask = enterpriseAskPrice(this, enterprise);
        enterprise.askPrices[params.output] = ask;
        this.market.submitSell(enterprise, params.output, quantity, ask);
      }
      if (this.durablesA2 && enterprise.industry !== "steel_mill") {
        const scrap = enterprise.inv("scrap");
        if (scrap > 1e-9) {
          this.market.submitSell(enterprise, "scrap", scrap, (prices.scrap || 0.0) * 0.95);
        }
      }
    }
  }
  _householdStock(agent) {
    return {
      food: agent.food, meat: agent.meat, cloth: agent.cloth,
      building: agent.housing, service: agent.service,
    };
  }
  _submitBundleOrders(agent, targets, prices, scale, options) {
    scale = scale === undefined ? 1.0 : scale;
    const opts = options || {};
    const durableNeeds = opts.durableNeeds || null;
    const stock = this._householdStock(agent);
    let cashLeft = opts.cashCap === undefined
      ? Math.max(0.0, agent.cash || 0.0)
      : Math.max(0.0, opts.cashCap || 0.0);
    const goods = durableNeeds
      ? ["food", "cloth", "building", "car", "meat", "service"]
      : ["food", "cloth", "building", "meat", "service"];
    for (const good of goods) {
      let need;
      if (durableNeeds && (good === "cloth" || good === "building" || good === "car")) {
        need = Math.max(0.0, durableNeeds[good] || 0.0);
      } else {
        need = Math.max(0.0, (targets[good] || 0.0) - (stock[good] || 0.0));
      }
      if (good !== "food") need *= Math.max(0.0, scale);
      if (need <= 1e-9 || cashLeft <= 1e-9) continue;
      let bidMult;
      if (good === "food") bidMult = stock.food < 0.05 ? 1.08 : 1.05;
      else if (good === "meat") bidMult = 1.03;
      else if (good === "service") bidMult = 1.02;
      else if (good === "car") bidMult = 1.05;
      else bidMult = 1.04;
      const bid = (prices[good] ?? 1.0) * bidMult;
      const quantity = Math.min(need, cashLeft / Math.max(bid, 1e-9));
      if (quantity <= 1e-9) continue;
      this.market.submitBuy(agent, good, quantity, bid);
      cashLeft -= quantity * bid;
    }
  }
  _workerIncomeProxy(worker) {
    let income = 0.0;
    if (worker.retired) income += Math.max(0.0, worker.pensionIncome);
    if (worker.isOwnerOperator) {
      const enterprise = this.enterprises.get(worker.employerId || "");
      if (enterprise && enterprise.active) income += Math.max(0.0, enterprise.lastOperatingPayout);
    } else if (worker.employed && worker.wage > 0) {
      income += worker.wage * worker.effectiveLabor;
    } else if (!worker.employed) {
      income += Math.max(0.0, worker.lastUiIncome);
    }
    return income;
  }
  _submitGearyWorkerOrders(worker, prices) {
    const income = this._workerIncomeProxy(worker);
    const budget = consumptionBudget(worker.cash, prices, income, this.demandConfig);
    const targets = demandTargets(budget, prices, this.demandConfig);
    worker.demandBudget = budget;
    worker.demandTargets = { ...targets };
    if (this.durablesA2) {
      assignDurableTargets(this, worker, prices, budget);
      const durableNeeds = durablePurchaseNeeds(worker, prices);
      this._submitBundleOrders(worker, targets, prices, this.workerDemandScale, {
        durableNeeds,
        cashCap: durableSpendingCap(worker),
      });
      return;
    }
    this._submitBundleOrders(worker, targets, prices, this.workerDemandScale);
  }
  _capitalistBudget(capitalist) {
    let budget = capitalistConsumptionBudget(
      capitalist.cash, this.market.referencePrices,
      C.CAPITALIST_MIN_CONSUMPTION, C.CAPITALIST_CONSUMPTION_RATE,
      this.demandConfig,
    );
    if (this.durablesA2) {
      const wealthBudget = Math.max(0.0, capitalist.cash) *
        C.CAPITALIST_WEALTH_CONSUMPTION_RATE;
      budget = Math.max(budget, wealthBudget);
    }
    return Math.min(Math.max(0.0, capitalist.cash), budget);
  }
  _submitGearyCapitalistOrders(capitalist, prices) {
    const scale = this.capitalistDemandScale;
    let budget = this._capitalistBudget(capitalist);
    budget = Math.min(Math.max(0.0, capitalist.cash), budget * Math.max(0.0, scale));
    const targets = demandTargets(budget, prices, this.demandConfig);
    capitalist.demandBudget = budget;
    capitalist.demandTargets = { ...targets };
    if (this.durablesA2) {
      assignDurableTargets(this, capitalist, prices, budget);
      const durableNeeds = durablePurchaseNeeds(capitalist, prices);
      this._submitBundleOrders(capitalist, targets, prices, 1.0, {
        durableNeeds,
        cashCap: durableSpendingCap(capitalist),
      });
      return;
    }
    this._submitBundleOrders(capitalist, targets, prices);
  }
  _submitHouseholdScrapOrders(prices) {
    if (!this.durablesA2) return;
    const price = (prices.scrap || 0.0) * 0.95;
    if (price <= 0.0) return;
    for (const worker of this.workers.values()) {
      if (!worker.alive) continue;
      const quantity = Math.max(0.0, worker.scrap || 0.0);
      if (quantity > 1e-9) this.market.submitSell(worker, "scrap", quantity, price);
    }
    for (const capitalist of this.capitalists.values()) {
      const quantity = Math.max(0.0, capitalist.scrap || 0.0);
      if (quantity > 1e-9) this.market.submitSell(capitalist, "scrap", quantity, price);
    }
  }
  _submitHouseholdOrders() {
    const prices = this.market.referencePrices;
    this._payChildAllowances(prices);
    for (const worker of this.workers.values()) {
      if (!worker.alive) continue;
      if (worker.isChild) {
        this._submitChildOrders(worker, prices);
        continue;
      }
      this._submitGearyWorkerOrders(worker, prices);
    }
    for (const capitalist of this.capitalists.values()) {
      this._submitGearyCapitalistOrders(capitalist, prices);
    }
    this._submitHouseholdScrapOrders(prices);
  }
  _submitInputOrders() {
    const prices = this.market.referencePrices;
    for (const enterprise of this.activeEnterprises()) {
      const needs = inputNeeds(this, enterprise);
      if (!Object.keys(needs).length) continue;
      const workers = this.enterpriseWorkers(enterprise);
      let wageBill = 0.0;
      for (const worker of workers) wageBill += worker.wage * worker.effectiveLabor;
      let inputCash = 0.0;
      for (const good of Object.keys(needs)) inputCash += needs[good] * (prices[good] || 0.0) * 1.06;
      let requiredCash = wageBill * 2.0 + inputCash * 0.5;
      if (enterprise.industry === "fertilizer_factory") {
        requiredCash = wageBill * 2.0 + inputCash + this.fertilizerCoalReserve(enterprise);
      }
      if (enterprise.cash < requiredCash) {
        const owner = this.capitalists.get(enterprise.ownerId);
        if (owner && owner.cash > 0) {
          const injection = Math.min(requiredCash - enterprise.cash, owner.cash * 0.5);
          owner.cash -= injection;
          enterprise.cash += injection;
        }
      }
      let inputTotal = 0.0;
      for (const good of Object.keys(needs)) inputTotal += needs[good] * (prices[good] || 0.0) * 1.06;
      const inputReserve = inputTotal * 0.5;
      const shortfall = Math.max(0.0, wageBill * 2.0 + inputReserve - enterprise.cash);
      if (shortfall > 1e-9) this.bank.lend(enterprise, shortfall);
      const available = Math.max(0.0, enterprise.cash - wageBill * 2.0);
      if (available <= 1e-9) continue;
      const orders = [];
      let total = 0.0;
      for (const good of Object.keys(needs)) {
        const bid = (prices[good] || 0.0) * 1.06;
        orders.push([good, needs[good], bid]);
        total += needs[good] * bid;
      }
      const scale = total > 0 ? Math.min(1.0, available / total) : 0.0;
      for (const [good, qty, bid] of orders) {
        const q = qty * scale;
        if (q > 1e-9) this.market.submitBuy(enterprise, good, q, bid);
      }
    }
  }
  _submitProjectOrders() {
    const prices = this.market.referencePrices;
    for (const project of this.projects.values()) {
      if (!project.active) continue;
      const enterprise = this.enterprises.get(project.enterpriseId);
      if (enterprise && enterprise.active) {
        const workers = this.enterpriseWorkers(enterprise);
        let wageBill = 0.0;
        for (const worker of workers) wageBill += worker.wage * worker.effectiveLabor;
        const reserve = Math.max(wageBill * 3.0, 100.0);
        let remainingValue = 0.0;
        for (const good of Object.keys(project.needed)) {
          remainingValue += project.remaining(good) * (prices[good] || 0.0);
        }
        if (project.cash + 1e-9 < remainingValue * 1.05) {
          const need = remainingValue * 1.15 - project.cash;
          const transfer = Math.min(need, Math.max(0.0, enterprise.cash - reserve));
          if (transfer > 0) {
            enterprise.cash -= transfer;
            project.cash += transfer;
          }
        }
      }
      if (project.cash <= 1e-9) continue;
      for (const good of Object.keys(project.needed)) {
        const remaining = project.remaining(good);
        if (remaining <= 1e-9) continue;
        const bid = (prices[good] || 0.0) * (project.industry === "agriculture" ? 1.10 : 1.08);
        const qty = Math.min(remaining, project.cash / Math.max(bid, 1e-9));
        if (qty > 1e-9) this.market.submitBuy(project, good, qty, bid);
      }
    }
  }

  // ------------------------------------------------------------------
  // Projects / finance / liquidation
  // ------------------------------------------------------------------
  _progressProjects() {
    for (const project of Array.from(this.projects.values())) {
      if (!project.active) continue;
      project.age += 1;
      if (!project.started) {
        if (project.fullyPaid()) {
          project.started = true;
          project.monthsLeft = project.buildMonths;
          if (project.monthsLeft <= 0) this._completeProject(project);
        } else if (project.age > C.PROJECT_TIMEOUT_MONTHS) {
          this._cancelProject(project);
        }
        continue;
      }
      project.monthsLeft -= 1;
      if (project.monthsLeft <= 0) this._completeProject(project);
    }
  }
  _completeProject(project) {
    const enterprise = this.enterprises.get(project.enterpriseId);
    if (enterprise && enterprise.active) {
      if (project.industry === "fertilizer_factory" && enterprise.totalEquipment() >= 2) {
        this.assetPool.equipment.set(project.equipmentKey,
          (this.assetPool.equipment.get(project.equipmentKey) || 0) + project.quantity);
      } else {
        enterprise.addEquipment(project.equipmentKey, project.quantity);
      }
      enterprise.active = true;
      enterprise.cash += project.cash;
      for (const good of GOODS) {
        const qty = project.inventory[good] || 0.0;
        if (qty > 0) enterprise.inventory[good] = enterprise.inv(good) + qty;
      }
    } else {
      this.bank.cash += project.cash;
      for (const good of GOODS) {
        const qty = project.inventory[good] || 0.0;
        if (qty > 0) this.assetPool.inventory[good] += qty;
      }
    }
    project.inventory = zeros();
    project.cash = 0.0;
    project.active = false;
  }
  _cancelProject(project) {
    const enterprise = this.enterprises.get(project.enterpriseId);
    if (enterprise && enterprise.active) {
      enterprise.cash += project.cash;
      for (const good of GOODS) {
        const qty = project.inventory[good] || 0.0;
        if (qty > 0) enterprise.inventory[good] = enterprise.inv(good) + qty;
      }
    } else {
      this.bank.cash += project.cash;
      for (const good of GOODS) {
        const qty = project.inventory[good] || 0.0;
        if (qty > 0) this.assetPool.inventory[good] += qty;
      }
    }
    project.inventory = zeros();
    project.cash = 0.0;
    project.active = false;
  }
  _finance() {
    const prices = this.market.referencePrices;
    const gov = this.government;
    const pensionRate = gov ? gov.pensionTaxRate : 0.0;
    for (const enterprise of Array.from(this.activeEnterprises())) {
      this.bank.chargeInterest(enterprise);
      const workers = this.enterpriseWorkers(enterprise);
      let wageBill = 0.0;
      for (const worker of workers) wageBill += worker.wage * worker.effectiveLabor;
      if (enterprise.cash > wageBill * 6.0 + 100.0) {
        this.bank.repay(enterprise, (enterprise.cash - wageBill * 3.0) * 0.30);
      }
      enterprise.lastRevenue = enterprise.monthRevenue;
      let inputCost = 0.0;
      for (const good of Object.keys(enterprise.lastInputUsed)) {
        inputCost += enterprise.lastInputUsed[good] * (prices[good] || 0.0);
      }
      enterprise.lastCosts = inputCost;
      enterprise.lastWages = enterprise.monthWages;
      enterprise.lastInterest = enterprise.monthInterest;
      const depreciation = equipmentValue(enterprise, prices) / C.DEPRECIATION_MONTHS;
      enterprise.lastProfit = enterprise.lastRevenue - enterprise.lastCosts -
        enterprise.lastWages - enterprise.lastInterest - depreciation;

      if (enterprise.isHousehold && enterprise.industry === "service") {
        let payout = 0.0;
        const owner = this.workers.get(enterprise.ownerId);
        if (owner && owner.alive) {
          payout = Math.max(0.0, enterprise.cash - C.SERVICE_FIRM_RESERVE);
          if (payout > 0) {
            enterprise.cash -= payout;
            owner.cash += payout;
            enterprise.lastProfit -= payout;
          }
        }
        enterprise.lastOperatingPayout = payout;
        if (enterprise.monthRevenue <= 1e-9) enterprise.serviceIdleMonths += 1;
        else enterprise.serviceIdleMonths = 0;
      }
      if (this._isHouseholdFarm(enterprise)) {
        let payout = 0.0;
        const owner = this.workers.get(enterprise.ownerId);
        if (owner && owner.alive) {
          payout = Math.max(0.0, enterprise.cash - C.HOUSEHOLD_FARM_RESERVE);
          if (payout > 0) {
            let contribution = 0.0;
            if (pensionRate > 0 && gov) {
              contribution = payout * pensionRate;
              gov.cash += contribution;
              gov.pensionFund += contribution;
              gov.pensionContributions += contribution;
              gov.pensionRevenue += contribution;
            }
            enterprise.cash -= payout;
            owner.cash += payout - contribution;
            enterprise.lastProfit -= payout;
          }
        }
        enterprise.lastOperatingPayout = payout;
      }
      if (!this._isHouseholdFarm(enterprise) && enterprise.lastProfit > 0 &&
          enterprise.cash > wageBill * 3.0 + 100.0) {
        const dividend = Math.min(
          enterprise.lastProfit * C.DIVIDEND_PAYOUT,
          enterprise.cash - wageBill * 3.0,
        );
        if (dividend > 0) {
          enterprise.cash -= dividend;
          const owner = this.capitalists.get(enterprise.ownerId);
          if (!owner) {
            const ownerWorker = this.workers.get(enterprise.ownerId);
            if (ownerWorker && ownerWorker.alive) ownerWorker.cash += dividend;
            else this.bank.cash += dividend;
          } else owner.cash += dividend;
        }
      }
      const worth = netWorth(enterprise, prices, this.land.price);
      if (enterprise.cash <= 1e-9 && enterprise.lastProfit < 0 && worth < 0) {
        enterprise.bankruptcyMonths += 1;
      } else enterprise.bankruptcyMonths = 0;
      if (enterprise.bankruptcyMonths >= 12) this._liquidate(enterprise);
    }
  }
  _liquidate(enterprise) {
    enterprise.active = false;
    if (this._isHouseholdFarm(enterprise)) {
      this._householdFarmLiquidationsThisMonth += 1;
      this.householdFarmLiquidationsTotal += 1;
    }
    for (const workerId of enterprise.workers.slice()) {
      const worker = this.workers.get(workerId);
      if (worker) {
        worker.employerId = null;
        worker.wage = 0.0;
      }
    }
    enterprise.workers.length = 0;
    const ownerWorker = this.workers.get(enterprise.ownerId);
    if (ownerWorker) {
      ownerWorker.isOwnerOperator = false;
      const ownedMu = this.land.owners.get(ownerWorker.id) || 0.0;
      this.land.owners.delete(ownerWorker.id);
      ownerWorker.landOwned = 0.0;
      this.land.enterpriseByOwner.delete(ownerWorker.id);
      if (ownedMu > enterprise.land) this.land.estateLand += ownedMu - enterprise.land;
    }
    if (enterprise.cash > 0) {
      this.bank.cash += enterprise.cash;
      enterprise.cash = 0.0;
    }
    for (const good of GOODS) {
      const qty = enterprise.inventory[good] || 0.0;
      if (qty > 0) this.assetPool.inventory[good] += qty;
    }
    for (const [key, count] of enterprise.equipment) {
      if (count > 0) this.assetPool.equipment.set(key, (this.assetPool.equipment.get(key) || 0) + count);
    }
    if (enterprise.land > 0) this.land.estateLand += enterprise.land;
    enterprise.inventory = zeros();
    enterprise.equipment = new Map();
    enterprise.vintages.length = 0;
    enterprise.replacementDemand = 0.0;
    enterprise.replacementByKey = {};
    enterprise.land = 0.0;
    const loan = this.bank.loans.get(enterprise.id) || 0.0;
    this.bank.loans.delete(enterprise.id);
    this.bank.writeOffs += loan;
    enterprise.debt = 0.0;
  }
  _exitServiceFirm(enterprise) {
    enterprise.active = false;
    for (const workerId of enterprise.workers.slice()) {
      const worker = this.workers.get(workerId);
      if (worker) {
        worker.employerId = null;
        worker.wage = 0.0;
        worker.isOwnerOperator = false;
      }
    }
    enterprise.workers.length = 0;
    const owner = this.workers.get(enterprise.ownerId);
    if (enterprise.cash > 0) {
      if (owner && owner.alive) owner.cash += enterprise.cash;
      else this.bank.cash += enterprise.cash;
      enterprise.cash = 0.0;
    }
    for (const good of GOODS) {
      const qty = enterprise.inventory[good] || 0.0;
      if (qty > 0) this.assetPool.inventory[good] += qty;
    }
    for (const [key, count] of enterprise.equipment) {
      if (count > 0) this.assetPool.equipment.set(key, (this.assetPool.equipment.get(key) || 0) + count);
    }
    enterprise.inventory = zeros();
    enterprise.equipment = new Map();
    enterprise.vintages.length = 0;
    enterprise.replacementDemand = 0.0;
    enterprise.replacementByKey = {};
    enterprise.serviceIdleMonths = 0;
  }
  _cleanupDormant() {
    for (const enterprise of this.enterprises.values()) {
      if (!enterprise.active) continue;
      if (enterprise.industry === "service" && enterprise.isHousehold &&
          enterprise.serviceIdleMonths >= C.SERVICE_IDLE_EXIT_MONTHS) {
        this._exitServiceFirm(enterprise);
        continue;
      }
      let hasAssets = enterprise.equipment.size > 0 || enterprise.workers.length > 0 || enterprise.land > 0;
      if (!hasAssets) {
        for (const good of GOODS) {
          if (enterprise.inv(good) > 1e-9) { hasAssets = true; break; }
        }
      }
      if (hasAssets) { enterprise.dormantMonths = 0; continue; }
      enterprise.dormantMonths += 1;
      if (enterprise.dormantMonths < 6) continue;
      if (enterprise.cash > 0) {
        const owner = this.capitalists.get(enterprise.ownerId);
        if (owner) owner.cash += enterprise.cash;
        else this.bank.cash += enterprise.cash;
        enterprise.cash = 0.0;
      }
      enterprise.active = false;
    }
  }

  // ------------------------------------------------------------------
  // Inheritance / estates
  // ------------------------------------------------------------------
  _chooseHeir(worker) {
    const candidates = [];
    for (const childId of worker.childrenIds) {
      const child = this.workers.get(childId);
      if (!child || !child.alive) continue;
      if (child.isChild || child.retired || child.isOwnerOperator) continue;
      if (this.land.enterpriseByOwner.has(child.id)) continue;
      candidates.push(child);
    }
    if (candidates.length) {
      candidates.sort((a, b) => (b.ageMonths - a.ageMonths) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
      return candidates[0];
    }
    const landless = [];
    for (const other of this.workers.values()) {
      if (other.alive && !other.isChild && !other.retired && !other.isOwnerOperator &&
          other.landOwned <= 1e-9 && !this.land.enterpriseByOwner.has(other.id)) {
        landless.push(other);
      }
    }
    if (!landless.length) return null;
    landless.sort((a, b) => (a.cash - b.cash) || (b.ageMonths - a.ageMonths) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
    return landless[0];
  }
  _transferHouseholdFarm(enterprise, deceased, heir, landMu, enterpriseId) {
    const previous = this.enterprises.get(heir.employerId || "");
    if (previous && previous.workers.includes(heir.id)) {
      previous.workers = previous.workers.filter((id) => id !== heir.id);
    }
    if (this.government !== null && this.government.jgWorkers.includes(heir.id)) {
      this.government.jgWorkers = this.government.jgWorkers.filter((id) => id !== heir.id);
    }
    if (enterprise.workers.includes(deceased.id)) {
      enterprise.workers = enterprise.workers.filter((id) => id !== deceased.id);
    }
    if (!enterprise.workers.includes(heir.id)) enterprise.workers.push(heir.id);
    enterprise.ownerId = heir.id;
    this.land.enterpriseByOwner.set(heir.id, enterpriseId);
    const ownMu = Math.max(landMu, enterprise.land);
    if (ownMu > 0) this.land.owners.set(heir.id, ownMu);
    heir.employerId = enterpriseId;
    heir.isOwnerOperator = true;
    heir.industry = enterprise.industry;
    heir.landOwned = ownMu;
    heir.wage = 0.0;
    heir.standardHours = Math.max(1, Math.trunc(this.workHours || 16));
    heir.hours = heir.standardHours;
  }
  _settleEstate(worker, heir) {
    const entId = this.land.enterpriseByOwner.get(worker.id);
    this.land.enterpriseByOwner.delete(worker.id);
    const mu = this.land.owners.get(worker.id) || 0.0;
    this.land.owners.delete(worker.id);
    let farmLand = 0.0;
    if (entId) {
      const enterprise = this.enterprises.get(entId);
      if (enterprise && enterprise.active) {
        farmLand = enterprise.land;
        if (heir !== null && heir !== undefined && farmLand > 0) {
          this._transferHouseholdFarm(enterprise, worker, heir, mu, entId);
          this.bank.deposits.delete(worker.id);
          worker.landOwned = 0.0;
          worker.isOwnerOperator = false;
          return;
        }
        for (const workerId of enterprise.workers.slice()) {
          const other = this.workers.get(workerId);
          if (other && other.alive) {
            other.employerId = null;
            other.wage = 0.0;
          }
        }
        enterprise.workers.length = 0;
        if (enterprise.cash > 0) {
          this.bank.cash += enterprise.cash;
          enterprise.cash = 0.0;
        }
        for (const good of GOODS) {
          const qty = enterprise.inventory[good] || 0.0;
          if (qty > 0) this.assetPool.inventory[good] += qty;
        }
        for (const [key, count] of enterprise.equipment) {
          if (count > 0) this.assetPool.equipment.set(key, (this.assetPool.equipment.get(key) || 0) + count);
        }
        if (enterprise.land > 0) this.land.estateLand += enterprise.land;
        enterprise.inventory = zeros();
        enterprise.equipment = new Map();
    enterprise.vintages.length = 0;
    enterprise.replacementDemand = 0.0;
    enterprise.replacementByKey = {};
        enterprise.land = 0.0;
        enterprise.active = false;
      }
    }
    if (mu > farmLand + 1e-9) this.land.estateLand += mu - farmLand;
    this.bank.deposits.delete(worker.id);
    worker.landOwned = 0.0;
    worker.isOwnerOperator = false;
  }

  // ------------------------------------------------------------------
  // Consumption / stats
  // ------------------------------------------------------------------
  _consumeDurablesAndFlows() {
    const demo = this.demographics;
    const prices = this.market.referencePrices;
    // Household farm owners may hold grain in the enterprise while having no
    // cash (self-provisioning). Transfer physical grain to their own pantry
    // before consumption; this is not a market sale and creates no money.
    for (const enterprise of this.enterprises.values()) {
      if (!enterprise.active || !this._isHouseholdFarm(enterprise)) continue;
      let stock = enterprise.inv("food");
      if (stock <= 1e-9) continue;
      for (const workerId of enterprise.workers) {
        if (stock <= 1e-9) break;
        const worker = this.workers.get(workerId);
        if (!worker || !worker.alive) continue;
        const target = worker.isChild ? demo.childFood : C.FOOD_PER_WORKER;
        const need = Math.max(0.0, target - worker.food);
        if (need <= 1e-9) continue;
        const take = Math.min(stock, need);
        worker.food += take;
        stock -= take;
        this._householdSelfConsumptionThisMonth += take;
      }
      enterprise.inventory.food = stock;
    }
    for (const worker of this.workers.values()) {
      if (!worker.alive) continue;
      let foodTarget;
      let meatTarget;
      let serviceTarget;
      let hungerTarget;
      if (worker.isChild) {
        foodTarget = demo.childFood;
        meatTarget = 0.0;
        serviceTarget = 0.0;
        hungerTarget = demo.childFood;
      } else {
        let targets = worker.demandTargets;
        if (!targets || !Object.keys(targets).length) {
          const budget = consumptionBudget(
            worker.cash, prices, this._workerIncomeProxy(worker), this.demandConfig,
          );
          targets = demandTargets(budget, prices, this.demandConfig);
          worker.demandBudget = budget;
          worker.demandTargets = { ...targets };
        }
        foodTarget = targets.food ?? C.FOOD_PER_WORKER;
        meatTarget = targets.meat ?? 0.0;
        serviceTarget = targets.service ?? C.SERVICE_PER_HOUSEHOLD;
        hungerTarget = C.FOOD_PER_WORKER;
        if ((worker.clothTargetStock || 0) <= 1e-9 ||
            (worker.housingTargetStock || 0) <= 1e-9) {
          assignDurableTargets(this, worker, prices, worker.demandBudget || 0.0);
        }
      }
      worker.consumedFood = Math.min(worker.food, foodTarget);
      worker.food -= worker.consumedFood;
      worker.consumedMeat = Math.min(worker.meat, meatTarget);
      worker.meat -= worker.consumedMeat;
      worker.consumedService = Math.min(worker.service, serviceTarget);
      worker.service -= worker.consumedService;
      applyDurableWear(this, worker, prices);

      if (worker.consumedFood + 1e-9 < 0.90 * hungerTarget) worker.hungerMonths += 1;
      else worker.hungerMonths = 0;
      if (worker.hungerMonths >= 3) {
        const chance = Math.min(0.50, 0.08 + 0.08 * (worker.hungerMonths - 3));
        if (this.rng.random() < chance) {
          this._killWorker(worker, "hunger");
          continue;
        }
      }
      if (worker.isChild) {
        worker.livingStandard = "child";
        continue;
      }
      const clothRatio = (worker.clothTargetStock || 0) > 1e-9
        ? worker.cloth / worker.clothTargetStock : 1.0;
      const housingRatio = (worker.housingTargetStock || 0) > 1e-9
        ? worker.housing / worker.housingTargetStock : 1.0;
      const comfortFood = C.FOOD_PER_WORKER * C.COMFORT_MULTIPLIER;
      if (worker.consumedFood + 1e-9 < C.FOOD_PER_WORKER) {
        worker.livingStandard = "survival";
      } else if (clothRatio + 1e-9 < 0.75 || housingRatio + 1e-9 < 0.75) {
        worker.livingStandard = "subsistence";
      } else if (worker.consumedFood + 1e-9 >= comfortFood &&
                 clothRatio + 1e-9 >= 1.0 && housingRatio + 1e-9 >= 1.0 &&
                 worker.cash >= C.COMFORT_SAVINGS) {
        const leisureThreshold = Math.max(1, Math.round(worker.standardHours * 0.5));
        if (worker.hours <= leisureThreshold && worker.cash >= C.LEISURE_SAVINGS) {
          worker.livingStandard = "leisure";
        } else worker.livingStandard = "comfort";
      } else {
        worker.livingStandard = "subsistence";
      }
    }

    for (const capitalist of this.capitalists.values()) {
      let targets = capitalist.demandTargets;
      if (!targets || !Object.keys(targets).length) {
        const budget = this._capitalistBudget(capitalist);
        targets = demandTargets(budget, prices, this.demandConfig);
        capitalist.demandBudget = budget;
        capitalist.demandTargets = { ...targets };
      }
      if ((capitalist.clothTargetStock || 0) <= 1e-9 ||
          (capitalist.housingTargetStock || 0) <= 1e-9) {
        assignDurableTargets(this, capitalist, prices, capitalist.demandBudget || 0.0);
      }
      const foodTarget = targets.food ?? C.CAPITALIST_FOOD;
      const meatTarget = targets.meat ?? 0.0;
      const serviceTarget = targets.service ?? C.CAPITALIST_SERVICE;
      capitalist.consumedFood = Math.min(capitalist.food, foodTarget);
      capitalist.food -= capitalist.consumedFood;
      capitalist.consumedMeat = Math.min(capitalist.meat, meatTarget);
      capitalist.meat -= capitalist.consumedMeat;
      capitalist.consumedService = Math.min(capitalist.service, serviceTarget);
      capitalist.service -= capitalist.consumedService;
      applyDurableWear(this, capitalist, prices);
    }
  }

  _consumeAndDemographics() {
    if (this.durablesA2) {
      this._consumeDurablesAndFlows();
      return;
    }
    const demo = this.demographics;
    const prices = this.market.referencePrices;
    for (const worker of this.workers.values()) {
      if (!worker.alive) continue;
      let foodTarget;
      let meatTarget;
      let clothTarget;
      let housingTarget;
      let serviceTarget;
      let hungerTarget;
      if (worker.isChild) {
        foodTarget = demo.childFood;
        meatTarget = 0.0;
        clothTarget = demo.childCloth;
        housingTarget = demo.childHousing;
        serviceTarget = 0.0;
        hungerTarget = demo.childFood;
      } else {
        let targets = worker.demandTargets;
        if (!targets || !Object.keys(targets).length) {
          const budget = consumptionBudget(worker.cash, prices, this._workerIncomeProxy(worker), this.demandConfig);
          targets = demandTargets(budget, prices, this.demandConfig);
          worker.demandBudget = budget;
          worker.demandTargets = { ...targets };
        }
        foodTarget = targets.food ?? C.FOOD_PER_WORKER;
        meatTarget = targets.meat ?? 0.0;
        clothTarget = targets.cloth ?? C.CLOTH_PER_WORKER;
        housingTarget = targets.building ?? C.HOUSING_PER_WORKER;
        serviceTarget = targets.service ?? C.SERVICE_PER_HOUSEHOLD;
        hungerTarget = C.FOOD_PER_WORKER;
      }
      worker.consumedFood = Math.min(worker.food, foodTarget);
      worker.food -= worker.consumedFood;
      worker.consumedMeat = Math.min(worker.meat, meatTarget);
      worker.meat -= worker.consumedMeat;
      worker.consumedCloth = Math.min(worker.cloth, clothTarget);
      worker.cloth -= worker.consumedCloth;
      worker.consumedHousing = Math.min(worker.housing, housingTarget);
      worker.housing -= worker.consumedHousing;
      worker.consumedService = Math.min(worker.service, serviceTarget);
      worker.service -= worker.consumedService;

      if (worker.consumedFood + 1e-9 < 0.90 * hungerTarget) worker.hungerMonths += 1;
      else worker.hungerMonths = 0;

      if (worker.hungerMonths >= 3) {
        const chance = Math.min(0.50, 0.08 + 0.08 * (worker.hungerMonths - 3));
        if (this.rng.random() < chance) {
          this._killWorker(worker, "hunger");
          continue;
        }
      }
      if (worker.isChild) {
        worker.livingStandard = "child";
        continue;
      }
      const comfortFood = C.FOOD_PER_WORKER * C.COMFORT_MULTIPLIER;
      const comfortCloth = C.CLOTH_PER_WORKER * C.COMFORT_MULTIPLIER;
      const comfortHousing = C.HOUSING_PER_WORKER * C.COMFORT_MULTIPLIER;
      if (worker.consumedFood + 1e-9 < C.FOOD_PER_WORKER) {
        worker.livingStandard = "survival";
      } else if (worker.consumedCloth + 1e-9 < C.CLOTH_PER_WORKER ||
                 worker.consumedHousing + 1e-9 < C.HOUSING_PER_WORKER) {
        worker.livingStandard = "subsistence";
      } else if (worker.consumedFood + 1e-9 >= comfortFood &&
                 worker.consumedCloth + 1e-9 >= comfortCloth &&
                 worker.consumedHousing + 1e-9 >= comfortHousing &&
                 worker.cash >= C.COMFORT_SAVINGS) {
        const leisureThreshold = Math.max(1, Math.round(worker.standardHours * 0.5));
        if (worker.hours <= leisureThreshold && worker.cash >= C.LEISURE_SAVINGS) {
          worker.livingStandard = "leisure";
        } else worker.livingStandard = "comfort";
      } else {
        worker.livingStandard = "subsistence";
      }
    }

    for (const capitalist of this.capitalists.values()) {
      let targets = capitalist.demandTargets;
      if (!targets || !Object.keys(targets).length) {
        const budget = capitalistConsumptionBudget(
          capitalist.cash, prices, C.CAPITALIST_MIN_CONSUMPTION,
          C.CAPITALIST_CONSUMPTION_RATE, this.demandConfig,
        );
        targets = demandTargets(budget, prices, this.demandConfig);
        capitalist.demandBudget = budget;
        capitalist.demandTargets = { ...targets };
      }
      const foodTarget = targets.food ?? C.CAPITALIST_FOOD;
      const meatTarget = targets.meat ?? 0.0;
      const clothTarget = targets.cloth ?? C.CAPITALIST_CLOTH;
      const housingTarget = targets.building ?? C.CAPITALIST_HOUSING;
      const serviceTarget = targets.service ?? C.CAPITALIST_SERVICE;
      capitalist.consumedFood = Math.min(capitalist.food, foodTarget);
      capitalist.food -= capitalist.consumedFood;
      capitalist.consumedMeat = Math.min(capitalist.meat, meatTarget);
      capitalist.meat -= capitalist.consumedMeat;
      capitalist.consumedCloth = Math.min(capitalist.cloth, clothTarget);
      capitalist.cloth -= capitalist.consumedCloth;
      capitalist.consumedHousing = Math.min(capitalist.housing, housingTarget);
      capitalist.housing -= capitalist.consumedHousing;
      capitalist.consumedService = Math.min(capitalist.service, serviceTarget);
      capitalist.service -= capitalist.consumedService;
    }
  }

  _updateWagePriceIndices(realValueAdded, employedLabor, totalWages, prices) {
    this.realValueAdded = realValueAdded;
    if (employedLabor > 1e-9 && realValueAdded > 1e-9) {
      const raw = realValueAdded / employedLabor;
      this._productivityRaw = raw;
      if (this._productivitySmoothed === null) this._productivitySmoothed = raw;
      else this._productivitySmoothed += C.PRODUCTIVITY_SMOOTHING * (raw - this._productivitySmoothed);
      if (this._productivityBaseline === null) {
        if (this.tick >= C.PRODUCTIVITY_WARMUP_MONTHS) {
          this._productivityBaseline = Math.max(raw, 1e-9);
          this._productivitySmoothed = raw;
        }
        this.productivityIndex = 1.0;
      } else {
        this.productivityIndex = Math.min(
          C.PRODUCTIVITY_INDEX_MAX,
          Math.max(C.PRODUCTIVITY_INDEX_MIN, this._productivitySmoothed / this._productivityBaseline),
        );
      }
    } else {
      this._productivityRaw = 0.0;
    }
    const subsistence = wageSubsistenceCost(prices);
    const newCpi = subsistence / this._cpiBaseline;
    let observed = this.cpi > 1e-9 ? newCpi / this.cpi - 1.0 : 0.0;
    observed = Math.min(C.INFLATION_OBSERVATION_CAP, Math.max(-C.INFLATION_OBSERVATION_CAP, observed));
    this.observedInflation = observed;
    this.inflationExpectations = (1.0 - C.INFLATION_EXPECTATION_SMOOTHING) *
      this.inflationExpectations + C.INFLATION_EXPECTATION_SMOOTHING * observed;
    this.cpi = newCpi;
    this.wageIndex = this.averageWage() / Math.max(C.WAGE_BASE, 1e-9);
    this.unitLaborCost = realValueAdded > 1e-9 ? totalWages / realValueAdded : 0.0;
  }

  _recordStats() {
    const prices = this.market.referencePrices;
    const aliveWorkers = [];
    for (const worker of this.workers.values()) if (worker.alive) aliveWorkers.push(worker);
    const laborForce = aliveWorkers.filter((worker) => worker.isWorkingAge);
    const employed = laborForce.filter((worker) => worker.employed);
    const unemployed = laborForce.length - employed.length;
    const childrenCount = aliveWorkers.filter((worker) => worker.isChild).length;
    const retireeCount = aliveWorkers.filter((worker) => worker.retired).length;
    const agWorkers = employed.filter((worker) => worker.industry === "agriculture");
    const foodOutput = this.productionMonth.food || 0.0;
    const agProductivity = foodOutput / Math.max(agWorkers.length, 1);
    let employedLabor = 0.0;
    let hoursSum = 0.0;
    for (const worker of employed) {
      employedLabor += worker.effectiveLabor;
      hoursSum += worker.hours;
    }
    const averageHours = hoursSum / Math.max(employed.length, 1);

    const activeEnterprises = this.activeEnterprises();
    let totalCapital = 0.0;
    let totalProfit = 0.0;
    let totalRevenue = 0.0;
    let totalInputCosts = 0.0;
    let totalWages = 0.0;
    let totalInterest = 0.0;
    let totalDepreciation = 0.0;
    let realValueAdded = 0.0;
    let capitalistCapital = 0.0;
    let capitalistProfit = 0.0;
    let householdCapital = 0.0;
    let householdProfit = 0.0;
    let householdOperatingIncome = 0.0;
    for (const enterprise of activeEnterprises) {
      const enterpriseCapital = capitalValue(enterprise, prices, this.land.price) + inventoryValue(enterprise, prices);
      totalCapital += enterpriseCapital;
      totalProfit += enterprise.lastProfit;
      totalRevenue += enterprise.lastRevenue;
      totalInputCosts += enterprise.lastCosts;
      totalWages += enterprise.lastWages;
      totalInterest += enterprise.lastInterest;
      totalDepreciation += equipmentValue(enterprise, prices) / C.DEPRECIATION_MONTHS;
      const outGood = SECTOR_PARAMS.get(enterprise.industry).output;
      realValueAdded += enterprise.lastOutput * INITIAL_PRICES[outGood];
      for (const good of Object.keys(enterprise.lastInputUsed)) {
        realValueAdded -= enterprise.lastInputUsed[good] * (INITIAL_PRICES[good] || 0.0);
      }
      if (enterprise.isHousehold) {
        householdCapital += enterpriseCapital;
        householdProfit += enterprise.lastProfit;
        householdOperatingIncome += enterprise.lastOperatingPayout;
      } else {
        capitalistCapital += enterpriseCapital;
        capitalistProfit += enterprise.lastProfit;
      }
    }
    let outputIndex = 0.0;
    for (const good of GOODS) outputIndex += (this.productionMonth[good] || 0.0) * INITIAL_PRICES[good];
    this._updateWagePriceIndices(realValueAdded, employedLabor, totalWages, prices);
    const profitRate = capitalistCapital > 0 ? capitalistProfit / capitalistCapital : 0.0;
    const profitRateAnnualized = profitRate <= -1.0 ? -1.0 : Math.pow(1.0 + profitRate, 12) - 1.0;
    const recentProfits = this.stats.slice(-11).map((stat) => stat.capitalist_profit || 0.0);
    recentProfits.push(capitalistProfit);
    const recentCapitals = this.stats.slice(-11).map((stat) => stat.capitalist_capital_stock || 0.0);
    recentCapitals.push(capitalistCapital);
    const recentN = recentProfits.length;
    let averageCapital = 0.0;
    for (const value of recentCapitals) averageCapital += value;
    averageCapital = recentN ? averageCapital / recentN : 0.0;
    let recentProfitSum = 0.0;
    for (const value of recentProfits) recentProfitSum += value;
    const profitRateAnnual = averageCapital > 1e-9
      ? (recentProfitSum / averageCapital) * (12.0 / recentN)
      : 0.0;
    const allProfitRate = totalCapital > 0 ? totalProfit / totalCapital : 0.0;

    const aggregateInventory = {};
    for (const good of GOODS) {
      let sum = 0.0;
      for (const enterprise of activeEnterprises) sum += enterprise.inv(good);
      aggregateInventory[good] = sum;
    }
    const firmsByIndustry = {};
    const workersByIndustry = {};
    for (const industry of INDUSTRIES) {
      firmsByIndustry[industry] = this.activeEnterprises(industry).length;
      workersByIndustry[industry] = 0;
    }
    for (const worker of laborForce) {
      if (Object.prototype.hasOwnProperty.call(workersByIndustry, worker.industry)) {
        workersByIndustry[worker.industry] += 1;
      }
    }
    const living = { survival: 0, subsistence: 0, comfort: 0, leisure: 0, child: 0 };
    for (const worker of aliveWorkers) {
      living[worker.livingStandard] = (living[worker.livingStandard] || 0) + 1;
    }

    const consumptionQty = {};
    const adultQty = {};
    const targetSum = {};
    for (const good of BUNDLE) { consumptionQty[good] = 0.0; adultQty[good] = 0.0; targetSum[good] = 0.0; }
    let targetCount = 0;
    let demandBudgetSum = 0.0;
    let carQty = 0.0;
    let capitalistCarQty = 0.0;
    // A2 durable aggregates (physical stocks / purchases, not money).
    let durableAdults = 0;
    let clothStockSum = 0.0;
    let clothTargetSum = 0.0;
    let clothingQualityWeighted = 0.0;
    let clothWearSum = 0.0;
    let clothPurchaseSum = 0.0;
    let housingStockSum = 0.0;
    let housingTargetSum = 0.0;
    let housingWearSum = 0.0;
    let housingPurchaseSum = 0.0;
    let housingMaintenanceSum = 0.0;
    let housingNewConstructionSum = 0.0;
    let carStockSum = 0.0;
    let carTargetSum = 0.0;
    let carPurchaseSum = 0.0;
    let carScrappedSum = 0.0;
    for (const worker of aliveWorkers) {
      let quantities;
      if (this.durablesA2) {
        const purchases = worker.monthPurchases || {};
        quantities = {
          food: worker.consumedFood, meat: worker.consumedMeat,
          cloth: purchases.cloth || 0.0, building: purchases.building || 0.0,
          service: worker.consumedService,
        };
        carQty += purchases.car || 0.0;
        clothStockSum += Math.max(0.0, worker.cloth || 0.0);
        clothTargetSum += Math.max(0.0, worker.clothTargetStock || 0.0);
        clothingQualityWeighted += Math.max(0.0, worker.cloth || 0.0) *
          Math.max(0.0, worker.clothQuality || 1.0);
        clothWearSum += Math.max(0.0, worker.clothWear || 0.0);
        clothPurchaseSum += Math.max(0.0, purchases.cloth || 0.0);
        housingStockSum += Math.max(0.0, worker.housing || 0.0);
        housingTargetSum += Math.max(0.0, worker.housingTargetStock || 0.0);
        housingWearSum += Math.max(0.0, worker.housingWear || 0.0);
        housingPurchaseSum += Math.max(0.0, purchases.building || 0.0);
        housingMaintenanceSum += Math.max(0.0, worker.housingMaintenancePaid || 0.0);
        housingNewConstructionSum += Math.max(0.0, worker.housingNewConstruction || 0.0);
        carStockSum += Math.max(0.0, worker.cars || 0.0);
        carTargetSum += Math.max(0.0, worker.carTargetStock || 0.0);
        carPurchaseSum += Math.max(0.0, purchases.car || 0.0);
        carScrappedSum += Math.max(0.0, worker.carScrapped || 0.0);
      } else {
        quantities = {
          food: worker.consumedFood, meat: worker.consumedMeat,
          cloth: worker.consumedCloth, building: worker.consumedHousing,
          service: worker.consumedService,
        };
      }
      for (const good of BUNDLE) consumptionQty[good] += quantities[good];
      if (worker.isChild) continue;
      durableAdults += 1;
      for (const good of BUNDLE) adultQty[good] += quantities[good];
      const targets = worker.demandTargets;
      if (targets && Object.keys(targets).length) {
        targetCount += 1;
        demandBudgetSum += worker.demandBudget;
        for (const good of BUNDLE) targetSum[good] += targets[good] || 0.0;
      }
    }
    const budgetShares = demandShares(consumptionQty, prices);
    const adultBudgetShares = demandShares(adultQty, prices);
    const capitalistQty = {};
    for (const good of BUNDLE) capitalistQty[good] = 0.0;
    for (const capitalist of this.capitalists.values()) {
      const purchases = capitalist.monthPurchases || {};
      capitalistQty.food += capitalist.consumedFood;
      capitalistQty.meat += capitalist.consumedMeat;
      if (this.durablesA2) {
        capitalistQty.cloth += purchases.cloth || 0.0;
        capitalistQty.building += purchases.building || 0.0;
        capitalistCarQty += purchases.car || 0.0;
        clothStockSum += Math.max(0.0, capitalist.cloth || 0.0);
        clothTargetSum += Math.max(0.0, capitalist.clothTargetStock || 0.0);
        clothingQualityWeighted += Math.max(0.0, capitalist.cloth || 0.0) *
          Math.max(0.0, capitalist.clothQuality || 1.0);
        clothWearSum += Math.max(0.0, capitalist.clothWear || 0.0);
        clothPurchaseSum += Math.max(0.0, purchases.cloth || 0.0);
        housingStockSum += Math.max(0.0, capitalist.housing || 0.0);
        housingTargetSum += Math.max(0.0, capitalist.housingTargetStock || 0.0);
        housingWearSum += Math.max(0.0, capitalist.housingWear || 0.0);
        housingPurchaseSum += Math.max(0.0, purchases.building || 0.0);
        housingMaintenanceSum += Math.max(0.0, capitalist.housingMaintenancePaid || 0.0);
        housingNewConstructionSum += Math.max(0.0, capitalist.housingNewConstruction || 0.0);
        carStockSum += Math.max(0.0, capitalist.cars || 0.0);
        carTargetSum += Math.max(0.0, capitalist.carTargetStock || 0.0);
        carPurchaseSum += Math.max(0.0, purchases.car || 0.0);
        carScrappedSum += Math.max(0.0, capitalist.carScrapped || 0.0);
        durableAdults += 1;
      } else {
        capitalistQty.cloth += capitalist.consumedCloth;
        capitalistQty.building += capitalist.consumedHousing;
      }
      capitalistQty.service += capitalist.consumedService;
    }
    const totalQty = {};
    for (const good of BUNDLE) totalQty[good] = consumptionQty[good] + capitalistQty[good];
    const marketBudgetShares = demandShares(totalQty, prices);
    const averageTargets = {};
    for (const good of BUNDLE) averageTargets[good] = targetCount ? targetSum[good] / targetCount : 0.0;
    let householdConsumptionValue = 0.0;
    for (const good of BUNDLE) householdConsumptionValue += consumptionQty[good] * (prices[good] || 0.0);
    let totalConsumptionValue = 0.0;
    for (const good of BUNDLE) totalConsumptionValue += totalQty[good] * (prices[good] || 0.0);
    const carSpending = (carQty + capitalistCarQty) * (prices.car || 0.0);
    householdConsumptionValue += carQty * (prices.car || 0.0);
    totalConsumptionValue += carSpending;
    const carShare = totalConsumptionValue > 1e-9 ? carSpending / totalConsumptionValue : 0.0;
    const clothStockPerAdult = durableAdults > 0 ? clothStockSum / durableAdults : 0.0;
    const clothTargetPerAdult = durableAdults > 0 ? clothTargetSum / durableAdults : 0.0;
    const housingStockPerAdult = durableAdults > 0 ? housingStockSum / durableAdults : 0.0;
    const housingTargetPerAdult = durableAdults > 0 ? housingTargetSum / durableAdults : 0.0;
    const carsPer100Adults = durableAdults > 0 ? carStockSum / durableAdults * 100.0 : 0.0;
    const clothQualityAverage = clothStockSum > 1e-9
      ? clothingQualityWeighted / clothStockSum : 1.0;
    const serviceEmployed = employed.filter((worker) => worker.industry === "service").length;
    const livestockEmployed = employed.filter((worker) => worker.industry === "livestock").length;
    const capitalistFarms = this.activeEnterprises("agriculture").filter((e) => !e.isHousehold).length;
    const householdFarms = this.activeEnterprises("agriculture").filter((e) => e.isHousehold).length;
    let fertilizerUsed = 0.0;
    for (const enterprise of this.activeEnterprises("agriculture")) {
      fertilizerUsed += enterprise.lastInputUsed.fertilizer || 0.0;
    }
    let farmMachinery = 0;
    for (const enterprise of this.activeEnterprises("agriculture")) {
      for (const [key, count] of enterprise.equipment) {
        if (key.startsWith("farm_")) farmMachinery += count;
      }
    }

    // Equipment vintages / scrap / land consolidation aggregates.
    const vintageBins = { "0-23": 0.0, "24-59": 0.0, "60-89": 0.0, "90-119": 0.0 };
    let vintageUnits = 0.0;
    let vintageAgeSum = 0.0;
    let replacementDemand = 0.0;
    let farmPowerTotal = 0.0;
    let consolidatedFarms = 0;
    let consolidatedLand = 0.0;
    let capitalistFarmLand = 0.0;
    let capitalistFarmCount = 0;
    let scrapUsedSteel = 0.0;
    let steelScrapOutput = 0.0;
    let steelOreOutput = 0.0;
    for (const enterprise of activeEnterprises) {
      replacementDemand += Math.max(0.0, enterprise.replacementDemand || 0.0);
      if (this.durablesA2) {
        for (const batch of enterprise.vintages) {
          if (batch.quantity <= 1e-12) continue;
          const age = Math.max(0.0, C.EQUIPMENT_LIFETIME_MONTHS - batch.monthsLeft);
          vintageUnits += batch.quantity;
          vintageAgeSum += age * batch.quantity;
          if (age < 24) vintageBins["0-23"] += batch.quantity;
          else if (age < 60) vintageBins["24-59"] += batch.quantity;
          else if (age < 90) vintageBins["60-89"] += batch.quantity;
          else vintageBins["90-119"] += batch.quantity;
        }
      }
      if (enterprise.industry === "agriculture" && !enterprise.isHousehold) {
        capitalistFarmCount += 1;
        capitalistFarmLand += enterprise.land;
        const maxPower = farmMaxPower(enterprise);
        for (const [key, count] of enterprise.equipment) {
          if (count <= 1e-9 || !key.startsWith("farm_")) continue;
          const et = EQUIPMENT.get(key);
          if (et) farmPowerTotal += et.power * count;
        }
        if (maxPower + 1e-9 >= C.CONSOLIDATION_MIN_POWER) {
          consolidatedFarms += 1;
          consolidatedLand += enterprise.land;
        }
      }
      if (enterprise.industry === "steel_mill") {
        const used = enterprise.lastInputUsed || {};
        scrapUsedSteel += used.scrap || 0.0;
        if (enterprise.lastSteelRecipe === "scrap") steelScrapOutput += enterprise.lastOutput;
        else steelOreOutput += enterprise.lastOutput;
      }
    }
    const equipmentAverageAge = vintageUnits > 1e-9 ? vintageAgeSum / vintageUnits : 0.0;
    const scrapGeneratedEquipment = this._scrapGeneratedEquipmentThisMonth;
    const scrapGeneratedCar = this._scrapGeneratedCarThisMonth;
    const scrapGenerated = scrapGeneratedEquipment + scrapGeneratedCar;
    const scrapInventory = this.durablesA2 ? this._sumScrapStock() : 0.0;
    const steelOutputTotal = steelScrapOutput + steelOreOutput;
    const scrapRecipeShare = steelOutputTotal > 1e-9 ? steelScrapOutput / steelOutputTotal : 0.0;
    const averageCapitalistFarmMu = capitalistFarmCount > 0
      ? capitalistFarmLand / capitalistFarmCount : 0.0;
    const landConsolidationShare = capitalistFarmLand > 1e-9
      ? consolidatedLand / capitalistFarmLand : 0.0;
    const durableSpending = clothPurchaseSum * (prices.cloth || 0.0) +
      housingPurchaseSum * (prices.building || 0.0) +
      carPurchaseSum * (prices.car || 0.0);
    const durableAssetValue = clothStockSum * (prices.cloth || 0.0) +
      housingStockSum * (prices.building || 0.0) +
      carStockSum * (prices.car || 0.0);

    const moneyTotal = this.totalMoney();
    const fiat = this.government !== null && this.government.fiatMoney;
    if (!fiat && this.moneyInitial > 0 && Math.abs(moneyTotal - this.moneyInitial) > 0.01) {
      this._warnings.push(`货币漂移：${moneyTotal.toFixed(2)} != ${this.moneyInitial.toFixed(2)}`);
    }
    const zeroOutputStreak = {};
    const autoFirmCount = this.activeEnterprises("auto_factory").length;
    for (const good of GOODS) {
      const price = prices[good];
      const initial = INITIAL_PRICES[good];
      if (price > initial * 10) this._warnings.push(`${GOOD_LABELS[good]} 价格高于初始价的 10 倍`);
      if (price < initial * 0.1) this._warnings.push(`${GOOD_LABELS[good]} 价格低于初始价的 0.1 倍`);
      const skipZeroOutput = this.durablesA2 &&
        (good === "scrap" || (good === "car" && autoFirmCount === 0));
      if (skipZeroOutput) {
        this._zeroOutputStreak.set(good, 0);
        zeroOutputStreak[good] = 0;
        continue;
      }
      const output = this.productionMonth[good] || 0.0;
      if (output <= 1e-9) this._zeroOutputStreak.set(good, (this._zeroOutputStreak.get(good) || 0) + 1);
      else this._zeroOutputStreak.set(good, 0);
      const streak = this._zeroOutputStreak.get(good) || 0;
      zeroOutputStreak[good] = streak;
      if (streak === 3 || (streak > 3 && streak % 12 === 0)) {
        this._warnings.push(`${GOOD_LABELS[good]} 连续 ${streak} 个月产量为 0`);
      }
    }

    const agesMonths = aliveWorkers.map((worker) => worker.ageMonths).sort((a, b) => a - b);
    const population = agesMonths.length;
    let averageAge = 0.0;
    let medianAge = 0.0;
    if (population) {
      let ageSum = 0.0;
      for (const age of agesMonths) ageSum += age;
      averageAge = ageSum / population / 12.0;
      const middle = Math.floor(population / 2);
      medianAge = population % 2 ? agesMonths[middle] / 12.0
        : (agesMonths[middle - 1] + agesMonths[middle]) / 2.0 / 12.0;
    }
    const ageHistogram = {};
    for (let start = 0; start < 90; start += 5) {
      ageHistogram[start < 85 ? `${start}-${start + 4}` : "85+"] = 0;
    }
    for (const ageMonths of agesMonths) {
      const bucket = Math.floor(ageMonths / 60);
      if (bucket >= 17) ageHistogram["85+"] += 1;
      else {
        const key = `${bucket * 5}-${bucket * 5 + 4}`;
        if (Object.prototype.hasOwnProperty.call(ageHistogram, key)) ageHistogram[key] += 1;
      }
    }
    const orphans = aliveWorkers.filter((worker) => worker.isChild && worker.parentId === null).length;
    if (this._orphanedThisMonth > 0) {
      this._warnings.push(`本月 ${this._orphanedThisMonth} 名儿童因家长死亡成为孤儿；allowance 归零（不凭空创造兜底资金）`);
    }
    if (this._pensionShortfall > 1e-6) {
      this._warnings.push(`养老金基金缺口 ${this._pensionShortfall.toFixed(2)}，已按比例发放`);
    }
    if (this._foodReliefShortfall > 1e-6) {
      this._warnings.push(`粮食救济库存不足，缺口 ${this._foodReliefShortfall.toFixed(2)} 吨`);
    }
    const projectsByIndustry = {};
    const industryCapacity = {};
    const industryEquipmentUnits = {};
    const industryEmployed = {};
    for (const industry of INDUSTRIES) {
      projectsByIndustry[industry] = 0;
      industryCapacity[industry] = 0.0;
      industryEquipmentUnits[industry] = 0;
      industryEmployed[industry] = 0;
    }
    for (const project of this.projects.values()) {
      if (project.active) projectsByIndustry[project.industry] += 1;
    }
    for (const enterprise of activeEnterprises) {
      const enterpriseWorkers = this.enterpriseWorkers(enterprise);
      const skill = enterpriseWorkers.length ? Math.max(1.0, averageSkill(enterpriseWorkers)) : 1.0;
      industryCapacity[enterprise.industry] += capacityAtSkillOne(enterprise) * skill;
      for (const count of enterprise.equipment.values()) industryEquipmentUnits[enterprise.industry] += count;
    }
    for (const worker of employed) {
      if (Object.prototype.hasOwnProperty.call(industryEmployed, worker.industry)) {
        industryEmployed[worker.industry] += 1;
      }
    }
    const gdp = this.market.consumptionSpending + this.market.investmentSpending + this.market.governmentSpending;
    const government = this.government;
    const priceFloors = {};
    const priceCeilings = {};
    for (const good of GOODS) {
      priceFloors[good] = this.market.floors[good] ?? 0.0;
      priceCeilings[good] = this.market.ceilings[good] ?? 0.0;
    }
    let assetPoolInventoryValue = 0.0;
    for (const good of GOODS) assetPoolInventoryValue += this.assetPool.inventory[good] * (prices[good] || 0.0);
    let assetPoolEquipmentUnits = 0;
    for (const count of this.assetPool.equipment.values()) assetPoolEquipmentUnits += count;
    let pensionRecipients = 0;
    for (const worker of aliveWorkers) if (worker.pensionIncome > 0) pensionRecipients += 1;

    const stat = {
      tick: this.tick,
      alive: population,
      population,
      children: childrenCount,
      working_age: laborForce.length,
      retirees: retireeCount,
      labor_force: laborForce.length,
      employed: employed.length,
      unemployed,
      births: this.birthsThisMonth,
      deaths: this.deadThisMonth,
      age_deaths: this._ageDeathsThisMonth,
      hunger_deaths: this._hungerDeathsThisMonth,
      birth_rate: this.birthsThisMonth / Math.max(population, 1),
      death_rate: this.deadThisMonth / Math.max(population, 1),
      birth_rate_annual: 12.0 * this.birthsThisMonth / Math.max(population, 1),
      death_rate_annual: 12.0 * this.deadThisMonth / Math.max(population, 1),
      dependency_ratio: (childrenCount + retireeCount) / Math.max(laborForce.length, 1),
      old_age_dependency: retireeCount / Math.max(laborForce.length, 1),
      child_dependency: childrenCount / Math.max(laborForce.length, 1),
      age_histogram: ageHistogram,
      average_age: averageAge,
      median_age: medianAge,
      orphans,
      dead_this_month: this.deadThisMonth,
      active_enterprises: activeEnterprises.length,
      money_total: moneyTotal,
      bank_cash: this.bank.cash,
      bank_frozen_cash: this.bank.frozenCash,
      bank_loans: Array.from(this.bank.loans.values()).reduce((a, b) => a + b, 0.0),
      bank_write_offs: this.bank.writeOffs,
      bank_deposits: Array.from(this.bank.deposits.values()).reduce((a, b) => a + b, 0.0),
      government_cash: government ? government.cash : 0.0,
      government_debt: government ? government.debt : 0.0,
      government_tax_revenue: government ? government.taxRevenue : 0.0,
      government_transfers: government ? government.transfers : 0.0,
      government_spending: government ? government.spending : 0.0,
      government_interest_paid: government ? government.interestPaid : 0.0,
      government_market_spending: this.market.governmentSpending,
      government_deficit: government ? government.deficit : 0.0,
      government_public_investment_budget: government ? government.publicInvestmentBudget : 0.0,
      government_jg_workers: government ? government.jgWorkers.length : 0,
      pension_contributions: government ? government.pensionContributions : 0.0,
      pension_subsidy: government ? government.pensionSubsidy : 0.0,
      pension_revenue: government ? government.pensionRevenue : 0.0,
      pension_spending: government ? government.pensionSpending : 0.0,
      pension_balance: government ? government.pensionBalance : 0.0,
      pension_fund: government ? government.pensionFund : 0.0,
      pension_recipients: pensionRecipients,
      pension_fund_unfunded: government ? Math.max(0.0, government.pensionFund - government.cash) : 0.0,
      central_bank_money: government ? government.centralBankMoney : 0.0,
      policy_regime: government ? government.regime : "classical",
      money_regime: government ? government.moneyRegime : "gold",
      price_regime: this.priceRegime,
      durables_a2: this.durablesA2,
      average_markup: activeEnterprises.reduce((sum, e) => sum + e.markup, 0.0) / Math.max(1, activeEnterprises.length),
      revenue: totalRevenue,
      input_costs: totalInputCosts,
      wages: totalWages,
      interest: totalInterest,
      depreciation: totalDepreciation,
      profit: totalProfit,
      inventory: aggregateInventory,
      price_floors: priceFloors,
      price_ceilings: priceCeilings,
      estate_land: this.land.estateLand,
      food_reserve: this.foodReserve.food,
      food_reserve_cash: this.foodReserve.cash,
      food_relief: this._foodReliefThisMonth,
      food_relief_unmet: this._foodReliefShortfall,
      food_levy: this._foodLevyThisMonth,
      household_self_consumption: this._householdSelfConsumptionThisMonth,
      asset_pool_inventory_value: assetPoolInventoryValue,
      asset_pool_equipment_units: assetPoolEquipmentUnits,
      zero_output_streak: zeroOutputStreak,
      active_projects: projectsByIndustry,
      industry_capacity: industryCapacity,
      industry_equipment_units: industryEquipmentUnits,
      industry_employed: industryEmployed,
      gdp,
      consumption: this.market.consumptionSpending,
      investment: this.market.investmentSpending,
      unemployment_rate: unemployed / Math.max(laborForce.length, 1),
      profit_rate: profitRate,
      profit_rate_annualized: profitRateAnnualized,
      profit_rate_annual: profitRateAnnual,
      all_profit_rate: allProfitRate,
      capital_stock: totalCapital,
      capitalist_capital_stock: capitalistCapital,
      capitalist_profit: capitalistProfit,
      household_capital: householdCapital,
      household_profit: householdProfit,
      household_operating_income: householdOperatingIncome,
      household_farm_liquidations: this._householdFarmLiquidationsThisMonth,
      household_farm_liquidations_total: this.householdFarmLiquidationsTotal,
      ag_productivity: agProductivity,
      food_output: foodOutput,
      prices: { ...prices },
      production: { ...this.productionMonth },
      output_index: outputIndex,
      real_value_added: realValueAdded,
      employed_labor: employedLabor,
      average_hours: averageHours,
      standard_work_hours: this.workHours,
      average_wage: this.averageWage(),
      wage_index: this.wageIndex,
      productivity_index: this.productivityIndex,
      productivity_level: this._productivityRaw,
      unit_labor_cost: this.unitLaborCost,
      cpi: this.cpi,
      observed_inflation: this.observedInflation,
      inflation_expectation: this.inflationExpectations,
      real_wage_index: this.wageIndex / Math.max(this.cpi, 1e-9),
      wage_productivity_share: this.wageProductivityShare,
      wage_bargain_power: this.wageBargainPower,
      wage_inflation_pass_through: this.wageInflationPassThrough,
      price_cost_anchors: {},
      price_markup_anchors: {},
      volumes: {},
      demand: {},
      supply: {},
      firms: firmsByIndustry,
      workers_by_industry: workersByIndustry,
      living_standard: living,
      budget_shares: budgetShares,
      adult_budget_shares: adultBudgetShares,
      food_share: budgetShares.food,
      food_total_share: budgetShares.food_total,
      adult_food_share: adultBudgetShares.food,
      meat_share: budgetShares.meat,
      cloth_share: budgetShares.cloth,
      housing_share: budgetShares.housing,
      car_share: carShare,
      service_spending_share: budgetShares.service,
      household_consumption_value: householdConsumptionValue,
      market_budget_shares: marketBudgetShares,
      market_food_share: marketBudgetShares.food,
      market_food_total_share: marketBudgetShares.food_total,
      market_meat_share: marketBudgetShares.meat,
      market_service_spending_share: marketBudgetShares.service,
      market_car_share: carShare,
      market_consumption_value: totalConsumptionValue,
      capitalist_meat_consumed: capitalistQty.meat,
      demand_targets: averageTargets,
      demand_budget: targetCount ? demandBudgetSum / targetCount : 0.0,
      real_wage_proxy: realWageProxy(this.averageWage(), prices, this.demandConfig),
      consumer_price_index: consumerPriceIndex(prices, INITIAL_PRICES, this.demandConfig),
      service_employment_share: serviceEmployed / Math.max(employed.length, 1),
      livestock_employment_share: livestockEmployed / Math.max(employed.length, 1),
      service_employed: serviceEmployed,
      livestock_employed: livestockEmployed,
      capitalist_farms: capitalistFarms,
      household_farms: householdFarms,
      fertilizer_used: fertilizerUsed,
      farm_machinery: farmMachinery,
      smallholder_land: this.land.smallholderLand,
      land_price: this.land.price,

      // A2 durable household stocks and physical flows.
      cloth_stock: clothStockSum,
      cloth_target: clothTargetSum,
      cloth_stock_per_adult: clothStockPerAdult,
      cloth_target_per_adult: clothTargetPerAdult,
      cloth_quality_index: clothQualityAverage,
      cloth_wear: clothWearSum,
      cloth_purchases: clothPurchaseSum,
      housing_stock: housingStockSum,
      housing_target: housingTargetSum,
      housing_stock_per_adult: housingStockPerAdult,
      housing_target_per_adult: housingTargetPerAdult,
      housing_wear: housingWearSum,
      housing_purchases: housingPurchaseSum,
      housing_maintenance_spending: housingMaintenanceSum,
      housing_new_construction: housingNewConstructionSum,
      maintenance_spending: housingMaintenanceSum,
      car_stock: carStockSum,
      car_target: carTargetSum,
      cars_per_100_adults: carsPer100Adults,
      car_purchases: carPurchaseSum,
      car_scrapped: carScrappedSum,
      durable_spending: durableSpending,
      durable_asset_value: durableAssetValue,

      // A2 equipment vintages / scrap / steel recipe / land consolidation.
      equipment_retired_units: this._equipmentRetiredThisMonth,
      equipment_average_age_months: equipmentAverageAge,
      equipment_vintage_bins: vintageBins,
      equipment_vintage_units: vintageUnits,
      replacement_demand_units: replacementDemand,
      replacement_projects: this._replacementProjectsStarted,
      scrap_generated: scrapGenerated,
      scrap_generated_equipment: scrapGeneratedEquipment,
      scrap_generated_car: scrapGeneratedCar,
      car_retired_units: this._carRetiredThisMonth,
      idle_equipment_scrapped: this._idleEquipmentScrappedThisMonth,
      scrap_inventory: scrapInventory,
      scrap_price: prices.scrap || 0.0,
      scrap_used_steel: scrapUsedSteel,
      steel_scrap_output: steelScrapOutput,
      steel_ore_output: steelOreOutput,
      scrap_recipe_share: scrapRecipeShare,
      farm_equipment_power: farmPowerTotal,
      consolidated_farms: consolidatedFarms,
      consolidated_land: consolidatedLand,
      average_capitalist_farm_mu: averageCapitalistFarmMu,
      land_consolidation_share: landConsolidationShare,
      warnings: this._warnings.slice(),
    };
    for (const good of GOODS) {
      stat.price_cost_anchors[good] = this.market.costAnchors[good] ?? 0.0;
      stat.price_markup_anchors[good] = this.market.markupAnchors[good] ?? 0.0;
      stat.volumes[good] = this.market.history[good].volume;
      stat.demand[good] = this.market.history[good].demand;
      stat.supply[good] = this.market.history[good].supply;
    }
    this.stats.push(stat);
    return stat;
  }
}

export { Engine, makeDemographics };
