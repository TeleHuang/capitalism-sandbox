/*
 * EcoSim V0.6 · engine source — module 50: historical scenario presets and
 * the initial 1840-style economy. The parameter values are the V0.6 defaults
 * (free cost-plus prices, income-dependent demand, 16h/8h institutions).
 */
import {
  C, INITIAL_PRICES,
} from "./00-core.js";
import { Engine, makeDemographics } from "./40-engine.js";
import { Government, POLICY_REGIMES, MONEY_REGIMES } from "./15-government.js";
import { Capitalist as EcoCapitalist, FoodReserve, equipmentSummary } from "./10-models.js";

const SCENARIOS = Object.freeze({
  classical: {
    id: "classical",
    label: "古典",
    name: "古典自由放任（pre-Keynesian）",
    policyRegime: POLICY_REGIMES.CLASSICAL,
    moneyRegime: MONEY_REGIMES.GOLD,
    priceRegime: "free",
    demandRegime: "geary",
    bankIntermediation: false,
    workHours: 16,
    wageProductivityShare: 0.50,
    wageAdjustmentSpeed: 0.10,
    inflationExpectation: 0.0,
    wageInflationPassThrough: 0.25,
    wageBargainPower: 0.10,
    workingAgeYears: 14,
    retirementAgeYears: 0,
    fertilityMonthly: 0.012,
    lifeExpectancyYears: 50.0,
    mortalityA: 0.0015,
    mortalityB: 0.0001,
    mortalityC: 0.085,
    infantMortalityAnnual: 0.18,
    childMortalityAnnual: 0.02,
    initialAgeMinYears: 18,
    initialAgeMaxYears: 60,
    initialFemaleShare: 0.5,
    initialChildren: 300,
    initialRetirees: 0,
    childFood: 0.05,
    childCloth: 0.5,
    childHousing: 0.1,
    pensionTaxRate: 0.0,
    pensionReplacement: 0.0,
    governmentCash: 0.0,
  },
  keynesian: {
    id: "keynesian",
    label: "凯恩斯",
    name: "凯恩斯福利国家",
    policyRegime: POLICY_REGIMES.KEYNESIAN,
    moneyRegime: MONEY_REGIMES.GOLD,
    priceRegime: "free",
    demandRegime: "geary",
    bankIntermediation: true,
    workHours: 8,
    wageProductivityShare: 1.00,
    wageAdjustmentSpeed: 0.25,
    inflationExpectation: 0.0,
    wageInflationPassThrough: 0.75,
    wageBargainPower: 0.55,
    taxRateWage: 0.08,
    taxRateProfit: 0.08,
    uiReplacement: 0.50,
    uiDuration: 12,
    publicInvestmentRate: 0.15,
    publicInvestmentCountercyclical: 0.08,
    governmentCash: 10000.0,
    workingAgeYears: 16,
    retirementAgeYears: 65,
    fertilityMonthly: 0.0105,
    lifeExpectancyYears: 80.0,
    mortalityA: 0.0003,
    mortalityB: 0.000045,
    mortalityC: 0.09,
    infantMortalityAnnual: 0.005,
    childMortalityAnnual: 0.0005,
    initialAgeMinYears: 18,
    initialAgeMaxYears: 60,
    initialFemaleShare: 0.5,
    initialChildren: 200,
    initialRetirees: 50,
    childFood: 0.05,
    childCloth: 0.5,
    childHousing: 0.1,
    pensionTaxRate: 0.10,
    pensionReplacement: 0.45,
  },
  mmt: {
    id: "mmt",
    label: "MMT",
    name: "MMT 主权货币 + 就业保障",
    policyRegime: POLICY_REGIMES.MMT,
    moneyRegime: MONEY_REGIMES.CREDIT,
    priceRegime: "free",
    demandRegime: "geary",
    bankIntermediation: true,
    workHours: 8,
    wageProductivityShare: 1.00,
    wageAdjustmentSpeed: 0.30,
    inflationExpectation: 0.0015,
    wageInflationPassThrough: 1.00,
    wageBargainPower: 0.65,
    taxRateWage: 0.08,
    taxRateProfit: 0.08,
    uiReplacement: 0.45,
    uiDuration: 12,
    publicInvestmentRate: 0.08,
    publicInvestmentCountercyclical: 0.04,
    jobGuarantee: true,
    jgWage: 30.0,
    jgMaxWorkers: 0,
    governmentCash: 0.0,
    workingAgeYears: 16,
    retirementAgeYears: 65,
    fertilityMonthly: 0.0082,
    lifeExpectancyYears: 80.0,
    mortalityA: 0.00028,
    mortalityB: 0.000042,
    mortalityC: 0.09,
    infantMortalityAnnual: 0.0045,
    childMortalityAnnual: 0.0004,
    initialAgeMinYears: 18,
    initialAgeMaxYears: 60,
    initialFemaleShare: 0.5,
    initialChildren: 200,
    initialRetirees: 50,
    childFood: 0.05,
    childCloth: 0.5,
    childHousing: 0.1,
    pensionTaxRate: 0.12,
    pensionReplacement: 0.50,
  },
  late_capitalism: {
    id: "late_capitalism",
    label: "晚期资本主义",
    name: "晚期资本主义（低生育/长寿/老龄化）",
    policyRegime: POLICY_REGIMES.KEYNESIAN,
    moneyRegime: MONEY_REGIMES.GOLD,
    priceRegime: "free",
    demandRegime: "geary",
    bankIntermediation: true,
    workHours: 8,
    wageProductivityShare: 0.90,
    wageAdjustmentSpeed: 0.20,
    inflationExpectation: 0.0005,
    wageInflationPassThrough: 0.75,
    wageBargainPower: 0.45,
    taxRateWage: 0.10,
    taxRateProfit: 0.10,
    uiReplacement: 0.40,
    uiDuration: 18,
    publicInvestmentRate: 0.12,
    publicInvestmentCountercyclical: 0.06,
    governmentCash: 20000.0,
    workingAgeYears: 18,
    retirementAgeYears: 67,
    fertilityMonthly: 0.0055,
    lifeExpectancyYears: 85.0,
    mortalityA: 0.00018,
    mortalityB: 0.00003,
    mortalityC: 0.095,
    infantMortalityAnnual: 0.002,
    childMortalityAnnual: 0.0002,
    initialAgeMinYears: 20,
    initialAgeMaxYears: 70,
    initialFemaleShare: 0.5,
    initialChildren: 150,
    initialRetirees: 100,
    childFood: 0.04,
    childCloth: 0.4,
    childHousing: 0.08,
    pensionTaxRate: 0.16,
    pensionReplacement: 0.55,
  },
});

const SCENARIO_ORDER = ["classical", "keynesian", "mmt", "late_capitalism"];

function demographicsFromConfig(config) {
  return makeDemographics({
    workingAgeMonths: config.workingAgeYears * 12,
    retirementAgeMonths: config.retirementAgeYears * 12,
    fertilityMonthly: config.fertilityMonthly,
    fertilityMultiplier: config.fertilityMultiplier ?? 1.0,
    mortalityA: config.mortalityA,
    mortalityB: config.mortalityB,
    mortalityC: config.mortalityC,
    infantMortalityAnnual: config.infantMortalityAnnual,
    childMortalityAnnual: config.childMortalityAnnual,
    initialAgeMinMonths: config.initialAgeMinYears * 12,
    initialAgeMaxMonths: config.initialAgeMaxYears * 12,
    initialFemaleShare: config.initialFemaleShare,
    childFood: config.childFood,
    childCloth: config.childCloth,
    childHousing: config.childHousing,
    pensionTaxRate: config.pensionTaxRate,
    pensionReplacement: config.pensionReplacement,
  });
}

function seedInputs(engine, enterprise) {
  const params = engine.sectorParams(enterprise.industry);
  if (!Object.keys(params.inputs).length) return;
  const { capacity } = equipmentSummary(enterprise);
  const output = capacity * 2.0;
  for (const good of Object.keys(params.inputs)) {
    enterprise.inventory[good] = Math.max(
      enterprise.inventory[good] || 0.0,
      output * params.inputs[good],
    );
  }
}

function buildScenario1(engine, config) {
  config = config || SCENARIOS.classical;
  engine.demographics = demographicsFromConfig(config);
  const demo = engine.demographics;
  engine.workHours = Math.max(1, Math.trunc(config.workHours));
  engine.wageProductivityShare = config.wageProductivityShare;
  engine.wageAdjustmentSpeed = config.wageAdjustmentSpeed;
  engine.wageBargainPower = config.wageBargainPower;
  engine.wageInflationPassThrough = config.wageInflationPassThrough;
  engine.inflationExpectations = config.inflationExpectation;

  const sampleInitialAge = () => {
    const minYear = Math.floor(demo.initialAgeMinMonths / 12);
    let maxYear = Math.floor(demo.initialAgeMaxMonths / 12);
    if (demo.retirementAgeMonths > 0) {
      maxYear = Math.min(maxYear, Math.floor(demo.retirementAgeMonths / 12) - 1);
    }
    const years = [];
    for (let year = minYear; year <= maxYear; year++) years.push(year);
    const scale = Math.max(5.0, 0.8 * config.lifeExpectancyYears);
    const weights = years.map((year) => Math.exp(-year / scale));
    const year = engine.demographicRng.choices(years, weights);
    return year * 12 + engine.demographicRng.randint(0, 11);
  };
  const seedWorker = (industry, skill, cash, food) => {
    const age = sampleInitialAge();
    const sex = engine.demographicRng.random() < demo.initialFemaleShare ? "F" : "M";
    return engine.createWorker({
      industry, skill, cash, food, ageMonths: age, sex,
      isChild: false, birthTick: -age,
    });
  };

  for (let i = 0; i < 50; i++) {
    engine.capitalists.set(`C_${i}`, new EcoCapitalist({ id: `C_${i}`, cash: 100000.0, role: "director" }));
  }
  for (let i = 50; i < 100; i++) {
    engine.capitalists.set(`C_${i}`, new EcoCapitalist({ id: `C_${i}`, cash: 10000.0, role: "manager" }));
  }
  const ownerIds = Array.from(engine.capitalists.keys());
  let ownerCursor = 0;

  for (let i = 0; i < 600; i++) {
    const worker = seedWorker("agriculture", 2.0, 20.0, 0.0);
    const enterprise = engine.createEnterprise({
      industry: "agriculture", ownerId: worker.id, cash: 100.0, land: 10.0,
      isHousehold: true, modernizationCapable: false,
    });
    worker.employerId = enterprise.id;
    worker.wage = 0.0;
    worker.isOwnerOperator = true;
    worker.landOwned = 10.0;
    enterprise.workers.push(worker.id);
    enterprise.demandForecast = 0.2;
    enterprise.targetInventoryMonths = 6.0;
    engine.land.owners.set(worker.id, 10.0);
    engine.land.enterpriseByOwner.set(worker.id, enterprise.id);
  }

  const addIndustry = (industry, enterpriseCount, workersPerEnterprise, equipment, extraWorkers) => {
    extraWorkers = extraWorkers || 0;
    for (let index = 0; index < enterpriseCount; index++) {
      const owner = engine.capitalists.get(ownerIds[ownerCursor % ownerIds.length]);
      ownerCursor += 1;
      const enterprise = engine.createEnterprise({
        industry, ownerId: owner.id, cash: 5000.0, modernizationCapable: true,
      });
      enterprise.wageOffer = C.WAGE_BASE;
      for (const [key, count] of Object.entries(equipment)) {
        for (let n = 0; n < count; n++) enterprise.addEquipment(key);
      }
      const workerCount = workersPerEnterprise + (index < extraWorkers ? 1 : 0);
      for (let n = 0; n < workerCount; n++) {
        const worker = seedWorker(industry, 2.0, 20.0, 0.0);
        worker.employerId = enterprise.id;
        worker.wage = C.WAGE_BASE;
        enterprise.workers.push(worker.id);
      }
      seedInputs(engine, enterprise);
      enterprise.demandForecast = equipmentSummary(enterprise).capacity * 2.0;
    }
  };

  addIndustry("coal_mine", 20, 10, { coal_t0: 1 });
  addIndustry("iron_mine", 8, 10, { iron_t0: 1 });
  addIndustry("steel_mill", 3, 4, { steel_t0: 1 });
  addIndustry("brick_factory", 1, 50, { brick_t0: 1 });
  addIndustry("textile_mill", 1, 20, { textile_t0: 20 });
  addIndustry("machinery_factory", 1, 10, { machinery_t0: 1 });
  addIndustry("construction", 5, 25, { construction_t0: 1 }, 3);

  engine.land.totalLand = C.TOTAL_LAND_MU;
  engine.market.referencePrices = { ...INITIAL_PRICES };
  engine.wageFloorScale = config.policyRegime === POLICY_REGIMES.CLASSICAL ? 0.90 : 1.0;
  engine.priceRegime = config.priceRegime;
  engine.demandRegime = config.demandRegime;
  engine.bankIntermediation = !!config.bankIntermediation;
  engine.foodReserve = new FoodReserve({ cash: 60000.0, food: 600.0 });
  if (config.policyRegime === POLICY_REGIMES.CLASSICAL) {
    engine.government = null;
  } else {
    engine.government = new Government({
      regime: config.policyRegime,
      moneyRegime: config.moneyRegime,
      cash: config.governmentCash || 0.0,
      taxRateWage: config.taxRateWage || 0.0,
      taxRateProfit: config.taxRateProfit || 0.0,
      uiReplacement: config.uiReplacement || 0.0,
      uiDuration: config.uiDuration || 0,
      publicInvestmentRate: config.publicInvestmentRate || 0.0,
      publicInvestmentCountercyclical: config.publicInvestmentCountercyclical || 0.0,
      jobGuarantee: !!config.jobGuarantee,
      jgWage: config.jgWage || 0.0,
      jgMaxWorkers: config.jgMaxWorkers || 0,
      pensionTaxRate: config.pensionTaxRate || 0.0,
      pensionReplacement: config.pensionReplacement || 0.0,
    });
    engine.government.pensionFund = Math.min(config.pensionFundInitial || 0.0, engine.government.cash);
  }
  seedDependents(engine, config);
  engine.moneyInitial = engine.totalMoney();
  return engine;
}

function seedDependents(engine, config) {
  const demo = engine.demographics;
  const adults = [];
  for (const worker of engine.workers.values()) {
    if (worker.alive && !worker.isChild && !worker.retired) adults.push(worker);
  }
  const women = adults.filter((worker) => worker.sex === "F");
  for (let index = 0; index < Math.max(0, config.initialChildren || 0); index++) {
    const age = engine.demographicRng.randint(0, Math.max(0, demo.workingAgeMonths - 1));
    const sex = engine.demographicRng.random() < 0.5 ? "F" : "M";
    const mother = women.length ? women[index % women.length] : null;
    const child = engine.createWorker({
      industry: mother ? mother.industry : "service",
      skill: 0.0, cash: 0.0, food: 0.0, ageMonths: age, sex,
      isChild: true, parentId: mother ? mother.id : null, birthTick: -age,
    });
    child.cloth = 0.0;
    child.housing = 0.0;
    child.livingStandard = "child";
    if (mother) mother.childrenIds.push(child.id);
  }
  if (config.retirementAgeYears <= 0) return;
  const retireMin = demo.retirementAgeMonths;
  const retireMax = Math.min(demo.maxAgeMonths - 12, demo.retirementAgeMonths + 18 * 12);
  const retirees = [];
  for (let index = 0; index < Math.max(0, config.initialRetirees || 0); index++) {
    const age = engine.demographicRng.randint(retireMin, Math.max(retireMin, retireMax));
    const sex = engine.demographicRng.random() < 0.5 ? "F" : "M";
    const retiree = engine.createWorker({
      industry: "service", skill: 1.0, cash: 0.0, food: 0.0,
      ageMonths: age, sex, isChild: false, birthTick: -age, retired: true,
    });
    retiree.cloth = 0.0;
    retiree.housing = 0.0;
    retiree.hours = 0;
    retirees.push(retiree);
  }
  const gov = engine.government;
  if (gov && gov.pensionReplacement > 0 && retirees.length) {
    const pensionEstimate = Math.max(
      C.WAGE_BASE * gov.pensionReplacement,
      C.FOOD_PER_WORKER * INITIAL_PRICES.food,
    );
    const advanceTotal = pensionEstimate * 2.0 * retirees.length;
    if (gov.cash < advanceTotal) engine._governmentFinance(advanceTotal - gov.cash, "pension_advance");
    const paid = Math.min(advanceTotal, gov.cash);
    if (paid > 0) {
      const perRetiree = paid / retirees.length;
      for (const retiree of retirees) retiree.cash += perRetiree;
      gov.cash -= paid;
    }
  }
}

function createEngine(options) {
  const opts = options || {};
  const config = typeof opts.regime === "string"
    ? { ...(SCENARIOS[opts.regime] || SCENARIOS.classical) }
    : { ...(opts.config || SCENARIOS.classical) };
  if (opts.priceRegime) config.priceRegime = opts.priceRegime;
  if (opts.demandRegime) config.demandRegime = opts.demandRegime;
  const engine = new Engine(opts.seed === undefined ? 1 : opts.seed);
  buildScenario1(engine, config);
  return { engine, config };
}

function runScenario(options) {
  const { engine } = createEngine(options);
  const months = options && options.months ? options.months : 60;
  const onTick = options && options.onTick ? options.onTick : null;
  for (let month = 1; month <= months; month++) {
    const stat = engine.step();
    if (onTick) onTick(stat, month, months);
  }
  return engine;
}

export { SCENARIOS, SCENARIO_ORDER, buildScenario1, createEngine, runScenario };
