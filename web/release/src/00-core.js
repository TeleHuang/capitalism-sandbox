/*
 * EcoSim V0.6 · engine source — module 00: utilities, calibration, equipment,
 * sector catalogue, Python-compatible RNG and the V0.6 Stone-Geary demand.
 *
 * This is the single source of truth for these definitions. The release build
 * (`scripts/build_release_v06.py`) bundles the ES modules into one inline
 * script; the Node golden harness imports them directly. No network, no CDN,
 * no runtime dependency on Python or external files.
 */

  // -------------------------------------------------------------------
  // Goods / industries (order mirrors src/ecosim/enums.py)
  // -------------------------------------------------------------------
  const GOODS = [
    "food", "meat", "coal", "iron_ore", "steel", "brick",
    "cloth", "fertilizer", "machinery", "building", "service",
    "car", "scrap",
  ];
  const INDUSTRIES = [
    "agriculture", "livestock", "coal_mine", "iron_mine", "steel_mill",
    "brick_factory", "textile_mill", "machinery_factory", "auto_factory",
    "construction", "fertilizer_factory", "service",
  ];
  const GOOD_LABELS = {
    food: "粮食", meat: "肉类", coal: "煤炭", iron_ore: "铁矿石",
    steel: "钢铁", brick: "砖头", cloth: "纺织品", fertilizer: "化肥",
    machinery: "机械", building: "建筑", service: "服务",
    car: "汽车", scrap: "废钢",
  };
  const GOOD_UNITS = {
    food: "吨", meat: "吨", coal: "吨", iron_ore: "吨", steel: "吨",
    brick: "块", cloth: "件", fertilizer: "吨", machinery: "台",
    building: "平方米", service: "单位", car: "辆", scrap: "吨",
  };
  const INDUSTRY_LABELS = {
    agriculture: "农业", livestock: "畜牧业", coal_mine: "煤矿",
    iron_mine: "铁矿", steel_mill: "炼钢厂", brick_factory: "砖窑",
    textile_mill: "纺织厂", machinery_factory: "机械厂",
    auto_factory: "汽车厂", construction: "建筑业", fertilizer_factory: "化肥厂",
    service: "服务业",
  };
  const CONSUMER_GOODS = new Set(["food", "meat", "cloth", "building", "service", "car"]);
  const CAPITAL_GOODS = new Set(["machinery", "brick", "steel"]);

  const INITIAL_PRICES = {
    food: 100.0, meat: 400.0, coal: 20.0, iron_ore: 30.0, steel: 150.0,
    brick: 10.0, cloth: 1.0, fertilizer: 50.0, machinery: 200.0,
    building: 10.0, service: 10.0, car: 800.0, scrap: 18.0,
  };

  // Steel can be produced from iron ore (classic route) or scrap steel.
  // The scrap route charges the same scrap-per-steel ratio as the ore route
  // but only half the coal, mirroring the lower energy requirement of EAF-like
  // remelting. Both recipes are real material balances: no good is created.
  const STEEL_RECIPES = Object.freeze([
    Object.freeze({ name: "ore", inputs: Object.freeze({ iron_ore: 1.5, coal: 1.0 }) }),
    Object.freeze({ name: "scrap", inputs: Object.freeze({ scrap: 1.5, coal: 0.5 }) }),
  ]);

  // -------------------------------------------------------------------
  // Calibration constants (src/ecosim/config.py). Kept in one frozen object
  // so A2 (durables) / C (credit) extensions add fields without touching
  // scattered literals.
  // -------------------------------------------------------------------
  const C = Object.freeze({
    LIVESTOCK_FEED_PER_MEAT: 3.0,
    FOOD_PER_WORKER: 0.10,
    CLOTH_PER_WORKER: 1.0,
    HOUSING_PER_WORKER: 0.20,
    FOOD_RELIEF_BUFFER_MONTHS: 1.5,
    SERVICE_PER_HOUSEHOLD: 0.5,
    CAPITALIST_SERVICE: 0.75,
    COMFORT_MULTIPLIER: 1.5,
    COMFORT_SAVINGS: 60.0,
    LEISURE_SAVINGS: 120.0,
    HOURS_OPTIONS: [16, 12, 8],
    DEFAULT_HOURS: 16,
    SKILL_MIN: 1.0,
    SKILL_MAX: 2.0,
    SKILL_GROWTH_PER_MONTH: 1.0 / 60.0,
    HUNGER_DEATH_AFTER_MONTHS: 3,
    HUNGER_DEATH_BASE: 0.08,
    HUNGER_DEATH_STEP: 0.08,
    HUNGER_DEATH_CAP: 0.50,
    WAGE_BASE: 20.0,
    WAGE_SEARCH_PREMIUM: 0.08,
    WAGE_SWITCH_THRESHOLD: 0.06,
    MAX_HIRES_PER_ENTERPRISE_PER_MONTH: 20,
    WAGE_INFLATION_PASS_THROUGH: 1.0,
    WAGE_TIGHTNESS_SLOPE: 0.5,
    WAGE_PROFIT_SLOPE: 0.5,
    WAGE_HIRING_PREMIUM: 1.10,
    WAGE_CASH_DISCOUNT: 0.95,
    WAGE_CAP_MULT: 5.0,
    WAGE_CATCHUP_WEIGHT: 0.6,
    WAGE_COST_OF_LIVING_WEIGHT: 0.4,
    WAGE_CATCHUP_CAP: 2.0,
    WAGE_INSTITUTIONAL_CAP: 0.50,
    WAGE_DOWNWARD_SPEED_MULT: 3.00,
    PRODUCTIVITY_WARMUP_MONTHS: 12,
    PRODUCTIVITY_SMOOTHING: 0.10,
    PRODUCTIVITY_INDEX_MIN: 0.20,
    PRODUCTIVITY_INDEX_MAX: 5.00,
    INFLATION_OBSERVATION_CAP: 0.20,
    INFLATION_EXPECTATION_SMOOTHING: 0.15,
    CAPITALIST_CONSUMPTION_RATE: 0.02,
    CAPITALIST_MIN_CONSUMPTION: 100.0,
    CAPITALIST_FOOD: 0.15,
    CAPITALIST_CLOTH: 1.5,
    CAPITALIST_HOUSING: 0.3,
    INVESTMENT_HURDLE: 0.012,
    INVESTMENT_RESERVE_MONTHS: 3.0,
    MAX_NEW_FIRMS_PER_TICK: 1,
    MAX_PROJECTS_PER_TICK: 5,
    MAX_ACTIVE_PROJECTS: 10,
    PROJECT_TIMEOUT_MONTHS: 18,
    DEPRECIATION_MONTHS: 120.0,
    DIVIDEND_PAYOUT: 0.50,
    MAX_SERVICE_ENTRIES_PER_MONTH: 25,
    SERVICE_ENTRY_MIN_REVENUE: 5.0,
    SERVICE_FIRM_RESERVE: 2.0,
    HOUSEHOLD_FARM_RESERVE: 50.0,
    SERVICE_IDLE_EXIT_MONTHS: 6,
    TOTAL_LAND_MU: 6000.0,
    INITIAL_LAND_PRICE: 100.0,
    LAND_RESERVATION_PRICE: 150.0,
    LAND_PRICE_STEP: 0.05,
    LAND_SALES_PER_TICK: 0.02,
    MIN_CAPITALIST_FARM_MU: 50.0,
    TARGET_CAPITALIST_FARM_MU: 100.0,
    PRICE_STEP: 0.05,
    PRICE_FLOOR: 0.01,
    FREE_PRICE_CAP_MULT: 20.0,
    FREE_MARKUP_INIT_MIN: 0.00,
    FREE_MARKUP_INIT_MAX: 3.00,
    FREE_MARKUP_MIN: 0.00,
    FREE_MARKUP_MAX: 3.00,
    FREE_MARKUP_SPEED: 0.02,
    FREE_DEMAND_SLOPE: 0.35,
    FREE_GLUT_SLOPE: 0.20,
    FREE_DEMAND_FACTOR_MIN: 0.85,
    FREE_DEMAND_FACTOR_MAX: 1.20,
    FREE_OBSERVED_WEIGHT: 0.25,
    FREE_REF_CORRIDOR: 0.03,
    FREE_COST_ANCHOR_WEIGHT: 0.45,
    FREE_OBSERVED_ANCHOR_WEIGHT: 0.35,
    FREE_REF_ANCHOR_WEIGHT: 0.20,
    FREE_SHORTAGE_COVERAGE: 1.0,
    FREE_GLUT_COVERAGE: 3.0,
    FREE_SHORTAGE_STEP_MIN: 0.04,
    FREE_SHORTAGE_STEP_MAX: 0.25,
    FREE_SHORTAGE_SLOPE: 0.50,
    FREE_GLUT_STEP_MIN: 0.02,
    FREE_GLUT_STEP_MAX: 0.12,
    FREE_GLUT_SLOPE: 0.10,
    BANK_CASH: 100000.0,
    BANK_INTEREST_RATE: 0.01,
    BANK_LOAN_MONTHS: 3.0,
    BASE_GRAIN_YIELD: 0.01,
    FERTILIZER_PER_MU: 0.01,
    FERTILIZER_YIELD_MULTIPLIER: 2.0,
    LAND_PER_WORKER_BASE: 10.0,
    FERTILIZER_COAL_BUFFER_MONTHS: 2.0,
    FERTILIZER_HIRING_PRIORITY: true,

    // ------------------------------------------------------------------
    // A2 durables / lifetimes / scrap / land consolidation
    // ------------------------------------------------------------------
    CLOTH_LIFETIME_MONTHS: 60.0,
    HOUSING_LIFETIME_MONTHS: 600.0,
    CAR_LIFETIME_MONTHS: 120.0,
    EQUIPMENT_LIFETIME_MONTHS: 120.0,
    CLOTH_WEAR_RATE: 1.0 / 60.0,
    HOUSING_WEAR_RATE: 1.0 / 600.0,
    // Desired stock targets are soft income functions (no hard "fully
    // clothed" cutoff). They grow with real income; quality also improves.
    // A target stock of roughly one lifetime of normal service flow makes
    // steady-state replacement demand comparable to the old flow demand:
    // 60 pieces of clothing / 60 months, and 120 m² / 600 months per adult.
    // Both scale with income and quality; there is no hard clothes cutoff.
    CLOTH_STOCK_BASE: 60.0,
    CLOTH_STOCK_INCOME_GAIN: 20.0,
    CLOTH_STOCK_CATCHUP_MONTHS: 24.0,
    CLOTH_QUALITY_BASE: 0.80,
    CLOTH_QUALITY_GAIN: 0.20,
    CLOTH_QUALITY_MIN: 0.80,
    CLOTH_QUALITY_MAX: 2.00,
    HOUSING_STOCK_BASE: 120.0,
    HOUSING_STOCK_INCOME_GAIN: 20.0,
    HOUSING_STOCK_CATCHUP_MONTHS: 60.0,
    HOUSING_PRODUCTIVITY_WEIGHT: 0.25,
    // Cars are a rich-household durable; ownership grows with real income.
    CAR_INCOME_THRESHOLD: 2.0,
    CAR_INCOME_SLOPE: 0.50,
    CAR_TARGET_MAX: 2.0,
    CAR_CATCHUP_MONTHS: 24.0,
    CAR_STEEL_PER_UNIT: 2.0,
    // Rich households may draw on savings for durables (capitalists in the
    // headless runs); workers mostly finance durables from current income.
    DURABLE_SAVINGS_FLOOR: 1000.0,
    DURABLE_SAVINGS_DRAWDOWN: 0.02,
    // A2 rich-household consumption: a small share of capitalist wealth is
    // spent each month on durables, housing and services. This is a transfer,
    // not money creation, and prevents indefinite hoarding from starving the
    // service/housing sectors of demand.
    CAPITALIST_WEALTH_CONSUMPTION_RATE: 0.002,
    INITIAL_CLOTH_STOCK_ADULT: 70.0,
    INITIAL_HOUSING_STOCK_ADULT: 130.0,
    INITIAL_CLOTH_STOCK_CHILD: 20.0,
    INITIAL_HOUSING_STOCK_CHILD: 40.0,
    INITIAL_CLOTH_STOCK_CAPITALIST: 90.0,
    INITIAL_HOUSING_STOCK_CAPITALIST: 160.0,
    INITIAL_CAR_OWNERS: 10,
    INITIAL_CAR_AGE_MIN: 30,
    INITIAL_CAR_AGE_SPAN: 90,
    // Scrap recovery: equipment/cars are physical assets; retirement moves
    // their metal content into the scrap good exactly once.
    SCRAP_PER_CAR: 1.2,
    SCRAP_PER_MACHINERY_GOOD: 0.6,
    SCRAP_PER_STEEL_GOOD: 0.8,
    SCRAP_PER_BRICK_GOOD: 0.005,
    SCRAP_PRICE_RATIO: 0.60,
    SCRAP_PRICE_ANCHOR_WEIGHT: 0.55,
    INITIAL_SCRAP_PER_STEEL_MILL: 20.0,
    // Land consolidation: mechanised capitalist farms can grow beyond the
    // 100-mu baseline and retire surplus small machines as scrap.
    CONSOLIDATED_FARM_MU: 200.0,
    CONSOLIDATION_MIN_POWER: 4.0,
    CONSOLIDATION_TARGET_WORKERS: 1.0,
    FARM_IDLE_MIN_LAND: 100.0,
  });

  // -------------------------------------------------------------------
  // Small helpers
  // -------------------------------------------------------------------
  function zeros() {
    const out = {};
    for (const good of GOODS) out[good] = 0.0;
    return out;
  }
  function copyNumbers(source) {
    const out = {};
    for (const good of GOODS) out[good] = source && source[good] ? source[good] : 0.0;
    return out;
  }
  function clamp(value, low, high) {
    return Math.max(low, Math.min(high, value));
  }
  function pySum(values) {
    let total = 0.0;
    for (const value of values) total += value;
    return total;
  }
  function round2(value) {
    // Python round(x, 2) uses banker's rounding; the wage offer is the only
    // place that relies on it. A tiny epsilon-free helper is close enough for
    // a display-grade number and avoids surprising upward bias.
    return Math.round((value + Number.EPSILON) * 100) / 100;
  }
  function maxKeyBy(map, score) {
    // Python max(dict, key=...) returns the first key on ties.
    let bestKey = null;
    let bestScore = null;
    for (const [key, value] of map) {
      const current = score(key, value);
      if (bestScore === null || current > bestScore) {
        bestKey = key;
        bestScore = current;
      }
    }
    return bestKey;
  }

  // -------------------------------------------------------------------
  // CPython-compatible Mersenne Twister.
  // The engine uses two independent streams exactly like the Python engine:
  //   rng            = Random(seed)
  //   demographicRng = Random(seed + 1_000_003)
  // Matching the stream keeps demography / hunger deaths aligned with the
  // golden runs (small numeric differences can still propagate).
  // -------------------------------------------------------------------
  class PythonRandom {
    constructor(seed) {
      this.mt = new Uint32Array(624);
      this.index = 624;
      this.seed(seed);
    }
    seed(seed) {
      let number = Math.abs(Math.trunc(Number(seed) || 0));
      const key = [];
      if (number === 0) key.push(0);
      while (number > 0) {
        key.push(number >>> 0);
        number = Math.floor(number / 4294967296);
      }
      this.initByArray(key);
    }
    initByArray(key) {
      const mt = this.mt;
      mt[0] = 19650218;
      for (let i = 1; i < 624; i++) {
        const prev = mt[i - 1];
        mt[i] = (Math.imul(1812433253, (prev ^ (prev >>> 30)) >>> 0) + i) >>> 0;
      }
      let i = 1;
      let j = 0;
      for (let k = Math.max(624, key.length); k > 0; k--) {
        const prev = mt[i - 1];
        const mixed = Math.imul((prev ^ (prev >>> 30)) >>> 0, 1664525) >>> 0;
        mt[i] = ((mt[i] ^ mixed) + key[j] + j) >>> 0;
        i += 1;
        j += 1;
        if (i >= 624) { mt[0] = mt[623]; i = 1; }
        if (j >= key.length) j = 0;
      }
      for (let k = 623; k > 0; k--) {
        const prev = mt[i - 1];
        const mixed = Math.imul((prev ^ (prev >>> 30)) >>> 0, 1566083941) >>> 0;
        mt[i] = ((mt[i] ^ mixed) - i) >>> 0;
        i += 1;
        if (i >= 624) { mt[0] = mt[623]; i = 1; }
      }
      mt[0] = 0x80000000;
      this.index = 624;
    }
    twist() {
      for (let i = 0; i < 624; i++) {
        const y = (this.mt[i] & 0x80000000) | (this.mt[(i + 1) % 624] & 0x7fffffff);
        let value = this.mt[(i + 397) % 624] ^ (y >>> 1);
        if (y & 1) value ^= 0x9908b0df;
        this.mt[i] = value >>> 0;
      }
      this.index = 0;
    }
    uint32() {
      if (this.index >= 624) this.twist();
      let y = this.mt[this.index++];
      y ^= y >>> 11;
      y ^= (y << 7) & 0x9d2c5680;
      y ^= (y << 15) & 0xefc60000;
      y ^= y >>> 18;
      return y >>> 0;
    }
    random() {
      const a = this.uint32() >>> 5;
      const b = this.uint32() >>> 6;
      return (a * 67108864.0 + b) * (1.0 / 9007199254740992.0);
    }
    getrandbits(k) {
      if (k <= 0) return 0;
      if (k <= 32) return this.uint32() >>> (32 - k);
      let words = Math.ceil(k / 32);
      let result = 0n;
      let shift = 0n;
      for (let i = 0; i < words; i++) {
        let word = this.uint32();
        const bits = Math.min(k, 32);
        if (bits < 32) word >>>= 32 - bits;
        result |= BigInt(word) << shift;
        shift += 32n;
        k -= 32;
      }
      return Number(result);
    }
    randbelow(n) {
      if (n <= 0) return 0;
      const k = Math.floor(Math.log2(n)) + 1;
      let r = this.getrandbits(k);
      while (r >= n) r = this.getrandbits(k);
      return r;
    }
    randrange(start, stop, step) {
      const st = step === undefined ? 1 : step;
      const width = stop - start;
      if (st === 1 && width > 0) return start + this.randbelow(width);
      const n = Math.floor((width + st - 1) / st);
      return start + st * this.randbelow(n);
    }
    randint(a, b) {
      return this.randrange(a, b + 1);
    }
    choices(population, weights) {
      const total = pySum(weights);
      let x = this.random() * total;
      let cumulative = 0.0;
      for (let i = 0; i < population.length; i++) {
        cumulative += weights[i];
        if (x < cumulative) return population[i];
      }
      return population[population.length - 1];
    }
  }

  // -------------------------------------------------------------------
  // Equipment catalogue (config.py `_make_equipment_tiers`)
  // -------------------------------------------------------------------
  class EquipmentType {
    constructor(fields) {
      Object.assign(this, fields);
      this.tier = fields.tier === undefined ? 0 : fields.tier;
    }
  }

  const EQUIPMENT = new Map();

  function makeEquipmentTiers(prefix, industry, label, baseCapacity, baseWorkers,
                              capitalGood, t0Cost, upgradeCost, baseBuildMonths,
                              powerBase, t0Label) {
    const result = new Map();
    for (let n = 0; n < 8; n++) {
      const key = `${prefix}_t${n}`;
      const cost = n === 0 ? t0Cost : upgradeCost * Math.pow(2, n - 1);
      const good = n === 0 && t0Cost <= 0 ? null : capitalGood;
      const tierLabel = n === 0 && t0Label ? t0Label : label;
      result.set(key, new EquipmentType({
        key,
        label: `${tierLabel} ${Math.pow(2, n)}×`,
        industry,
        capacity: baseCapacity * Math.pow(2, n),
        workers: powerBase > 0 ? 0 : baseWorkers + n,
        capitalGood: good,
        capitalCost: cost,
        buildMonths: baseBuildMonths + Math.floor(n / 2),
        power: powerBase > 0 ? powerBase * Math.pow(2, n) : 0.0,
        buildingCost: 0.0,
        tier: n,
      }));
    }
    return result;
  }

  for (const [key, value] of makeEquipmentTiers(
    "farm", "agriculture", "农机", 0.0, 0, "machinery", 1.0, 2.0, 2, 1.0, null,
  )) EQUIPMENT.set(key, value);

  const INDUSTRIAL_TIER_SPECS = [
    ["coal", "coal_mine", "矿井设备", 10.0, 10, "machinery", 0.0, 2.0, 0],
    ["iron", "iron_mine", "矿井设备", 10.0, 10, "machinery", 0.0, 2.0, 0],
    ["steel", "steel_mill", "炼钢炉", 50.0, 3, "brick", 1000.0, 2000.0, 2],
    ["brick", "brick_factory", "砖窑", 100.0, 50, "brick", 300.0, 600.0, 2],
    ["textile", "textile_mill", "织机", 50.0, 1, "machinery", 0.0, 5.0, 1],
    ["machinery", "machinery_factory", "机械工坊", 5.0, 10, "steel", 0.0, 20.0, 1],
    ["auto", "auto_factory", "汽车装配线", 2.0, 10, "steel", 10.0, 10.0, 2],
    ["construction", "construction", "施工队", 50.0, 20, "machinery", 0.0, 3.0, 1],
    ["fertilizer", "fertilizer_factory", "反应炉", 20.0, 5, "machinery", 1.0, 2.0, 1],
    ["livestock", "livestock", "畜舍", 2.0, 5, "machinery", 1.0, 2.0, 2],
  ];
  for (const spec of INDUSTRIAL_TIER_SPECS) {
    const [prefix, industry, label, capacity, workers, good, t0, upgrade, build] = spec;
    const t0Label = prefix === "coal" || prefix === "iron" ? "徒手采矿" : null;
    for (const [key, value] of makeEquipmentTiers(
      prefix, industry, label, capacity, workers, good, t0, upgrade, build, 0.0, t0Label,
    )) EQUIPMENT.set(key, value);
  }

  const MANUAL_SPECS = [
    ["brick_manual", "brick_factory", "手工砖窑", 10.0, 10],
    ["steel_manual", "steel_mill", "手工炼钢炉", 5.0, 5],
    ["machinery_manual", "machinery_factory", "手工机械工坊", 1.0, 5],
    ["construction_manual", "construction", "手工施工队", 5.0, 10],
    ["textile_manual", "textile_mill", "手工织机", 10.0, 5],
  ];
  for (const [key, industry, label, capacity, workers] of MANUAL_SPECS) {
    EQUIPMENT.set(key, new EquipmentType({
      key, label, industry, capacity, workers, capitalGood: null,
      capitalCost: 0.0, buildMonths: 0, power: 0.0, buildingCost: 0.0, tier: 0,
    }));
  }
  const MANUAL_EQUIPMENT = {
    brick_factory: "brick_manual",
    steel_mill: "steel_manual",
    machinery_factory: "machinery_manual",
    construction: "construction_manual",
    textile_mill: "textile_manual",
  };
  EQUIPMENT.set("service_t0", new EquipmentType({
    key: "service_t0", label: "手工服务摊 1×", industry: "service",
    capacity: 1.0, workers: 1, capitalGood: null, capitalCost: 0.0,
    buildMonths: 0, power: 0.0, buildingCost: 0.0, tier: 0,
  }));

  const SECTOR_PARAMS = new Map();
  function sector(industry, output, inputs, maxFirms, isResource) {
    // Explicit tier-key prefixes (multi-word industries would not derive
    // correctly from a generic string replacement).
    const PREFIX = {
      agriculture: "farm", livestock: "livestock", coal_mine: "coal",
      iron_mine: "iron", steel_mill: "steel", brick_factory: "brick",
      textile_mill: "textile", machinery_factory: "machinery",
      auto_factory: "auto", construction: "construction",
      fertilizer_factory: "fertilizer",
    };
    const keys = industry === "service"
      ? ["service_t0"]
      : Array.from({ length: 8 }, (_, n) => `${PREFIX[industry]}_t${n}`);
    SECTOR_PARAMS.set(industry, {
      industry, output, inputs, equipment: keys, maxFirms,
      isResource: !!isResource,
    });
  }
  sector("agriculture", "food", {}, 300, true);
  sector("livestock", "meat", { food: C.LIVESTOCK_FEED_PER_MEAT }, 12, false);
  sector("coal_mine", "coal", {}, 30, true);
  sector("iron_mine", "iron_ore", {}, 15, true);
  sector("steel_mill", "steel", { iron_ore: 1.5, coal: 1.0 }, 8, false);
  sector("brick_factory", "brick", { coal: 0.2 }, 5, false);
  sector("textile_mill", "cloth", { food: 0.001 }, 6, false);
  sector("machinery_factory", "machinery", { steel: 1.0 }, 4, false);
  sector("auto_factory", "car", { steel: C.CAR_STEEL_PER_UNIT }, 4, false);
  sector("construction", "building", { brick: 0.5 }, 6, false);
  sector("fertilizer_factory", "fertilizer", { coal: 2.0 }, 3, false);
  sector("service", "service", {}, 1000, false);

  // Steel mills additionally accept the scrap recipe. `inputs` above stays
  // the ore route so legacy/A2-off code sees exactly the V0.6 recipe.
  const steelParams = SECTOR_PARAMS.get("steel_mill");
  steelParams.recipes = STEEL_RECIPES;
  steelParams.extraInputs = { scrap: true };

  // -------------------------------------------------------------------
  // V0.6 Stone-Geary / linear expenditure demand (src/ecosim/demand.py)
  // -------------------------------------------------------------------
  const BUNDLE = ["food", "meat", "cloth", "building", "service"];
  const BUNDLE_LABELS = {
    food: "food", meat: "meat", cloth: "cloth", building: "housing", service: "service",
  };
  const DEFAULT_DEMAND = Object.freeze({
    foodSubsistence: 0.10,
    meatSubsistence: 0.0,
    clothSubsistence: 0.50,
    housingSubsistence: 0.10,
    serviceSubsistence: 0.35,
    incomeSpendingShare: 0.90,
    consumptionFloorRatio: 1.45,
    capitalistBudgetMultiple: 4.0,
    incomeAnchors: [1.5, 3.0, 6.0],
    foodMarginalShares: [0.00, 0.00, 0.00],
    meatMarginalShares: [0.00, 0.10, 0.14],
    clothMarginalShares: [0.13, 0.13, 0.13],
    housingMarginalShares: [0.22, 0.22, 0.22],
    serviceMarginalShares: [0.65, 0.55, 0.51],
    foodCap: 0.25,
    meatCap: 0.05,
    clothCap: 10.0,
    housingCap: 2.0,
    serviceCap: 8.0,
  });

  function demandSubsistence(config) {
    return {
      food: config.foodSubsistence,
      meat: config.meatSubsistence,
      cloth: config.clothSubsistence,
      building: config.housingSubsistence,
      service: config.serviceSubsistence,
    };
  }
  function demandCaps(config) {
    return {
      food: config.foodCap, meat: config.meatCap, cloth: config.clothCap,
      building: config.housingCap, service: config.serviceCap,
    };
  }
  function demandShareTable(config) {
    return {
      food: config.foodMarginalShares,
      meat: config.meatMarginalShares,
      cloth: config.clothMarginalShares,
      building: config.housingMarginalShares,
      service: config.serviceMarginalShares,
    };
  }
  function priceOf(prices, good) {
    return Math.max(prices[good] || 0.0, 1e-9);
  }
  function subsistenceCost(prices, config) {
    const quantities = demandSubsistence(config || DEFAULT_DEMAND);
    let total = 0.0;
    for (const good of BUNDLE) total += priceOf(prices, good) * quantities[good];
    return total;
  }
  function consumptionBudget(cash, prices, income, config) {
    const cfg = config || DEFAULT_DEMAND;
    cash = Math.max(0.0, cash);
    if (cash <= 0.0) return 0.0;
    const floor = subsistenceCost(prices, cfg) * cfg.consumptionFloorRatio;
    const desired = Math.max(floor, Math.max(0.0, income) * cfg.incomeSpendingShare);
    return Math.min(cash, desired);
  }
  function capitalistConsumptionBudget(cash, prices, minConsumption, consumptionRate, config) {
    const cfg = config || DEFAULT_DEMAND;
    cash = Math.max(0.0, cash);
    if (cash <= 0.0) return 0.0;
    const cap = subsistenceCost(prices, cfg) * cfg.capitalistBudgetMultiple;
    const desired = Math.max(minConsumption, cash * consumptionRate);
    return Math.max(0.0, Math.min(cash, desired, cap));
  }
  function lerp(a, b, weight) {
    return a + (b - a) * weight;
  }
  function interpolate(values, anchors, realIncome) {
    const x = Math.max(1e-9, realIncome);
    if (x <= anchors[0]) return values[0];
    if (x >= anchors[2]) return values[2];
    if (x <= anchors[1]) {
      const weight = Math.log(x / anchors[0]) / Math.log(anchors[1] / anchors[0]);
      return lerp(values[0], values[1], weight);
    }
    const weight = Math.log(x / anchors[1]) / Math.log(anchors[2] / anchors[1]);
    return lerp(values[1], values[2], weight);
  }
  function marginalBudgetShares(realIncome, config) {
    const cfg = config || DEFAULT_DEMAND;
    const table = demandShareTable(cfg);
    const raw = {};
    let total = 0.0;
    for (const good of BUNDLE) {
      raw[good] = interpolate(table[good], cfg.incomeAnchors, realIncome);
      total += raw[good];
    }
    if (total <= 1e-12) {
      const zero = {};
      for (const good of BUNDLE) zero[good] = 0.0;
      return zero;
    }
    const shares = {};
    for (const good of BUNDLE) shares[good] = raw[good] / total;
    return shares;
  }
  function demandTargets(budget, prices, config) {
    const cfg = config || DEFAULT_DEMAND;
    const subsistence = demandSubsistence(cfg);
    const caps = demandCaps(cfg);
    const baseCost = subsistenceCost(prices, cfg);
    budget = Math.max(0.0, budget);
    const extra = Math.max(0.0, budget - baseCost);
    const realIncome = budget / Math.max(baseCost, 1e-9);
    const shares = marginalBudgetShares(realIncome, cfg);
    const targets = {};
    for (const good of BUNDLE) {
      const price = priceOf(prices, good);
      const quantity = subsistence[good] + shares[good] * extra / price;
      targets[good] = Math.max(0.0, Math.min(caps[good], quantity));
    }
    targets.food = Math.max(targets.food, cfg.foodSubsistence);
    return targets;
  }
  function demandShares(targets, prices) {
    const values = {};
    let total = 0.0;
    for (const good of BUNDLE) {
      values[good] = (targets[good] || 0.0) * priceOf(prices, good);
      total += values[good];
    }
    if (total <= 1e-12) {
      const shares = { food: 0.0, meat: 0.0, cloth: 0.0, housing: 0.0, service: 0.0, food_total: 0.0 };
      return shares;
    }
    const shares = {};
    for (const good of BUNDLE) shares[BUNDLE_LABELS[good]] = values[good] / total;
    shares.food_total = (values.food + values.meat) / total;
    return shares;
  }
  function realWageProxy(averageWage, prices, config) {
    return Math.max(0.0, averageWage) / Math.max(subsistenceCost(prices, config || DEFAULT_DEMAND), 1e-9);
  }
  function consumerPriceIndex(prices, initialPrices, config) {
    const cfg = config || DEFAULT_DEMAND;
    const initial = subsistenceCost(initialPrices, cfg);
    if (initial <= 1e-12) return 100.0;
    return 100.0 * subsistenceCost(prices, cfg) / initial;
  }
  function sectorUsesInput(industry, good) {
    const params = SECTOR_PARAMS.get(industry);
    if (!params) return false;
    if (params.inputs[good]) return true;
    return !!(params.extraInputs && params.extraInputs[good]);
  }

export {
  C, GOODS, INDUSTRIES, GOOD_LABELS, GOOD_UNITS, INDUSTRY_LABELS,
  CONSUMER_GOODS, CAPITAL_GOODS, INITIAL_PRICES, EQUIPMENT,
  MANUAL_EQUIPMENT, SECTOR_PARAMS, EquipmentType, STEEL_RECIPES,
  BUNDLE, BUNDLE_LABELS, DEFAULT_DEMAND,
  zeros, copyNumbers, clamp, pySum, round2, maxKeyBy, PythonRandom,
  demandSubsistence, demandCaps, demandShareTable, priceOf,
  subsistenceCost, consumptionBudget, capitalistConsumptionBudget,
  marginalBudgetShares, demandTargets, demandShares, realWageProxy,
  consumerPriceIndex, sectorUsesInput,
};
