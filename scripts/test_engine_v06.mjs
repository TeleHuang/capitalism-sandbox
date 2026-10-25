/**
 * Node-based engine tests for the EcoSim V0.6 JS source of truth.
 *
 * Usage: node scripts/test_engine_v06.mjs [--slow]
 *
 * No external dependencies. The Python golden file is only a migration oracle;
 * these tests exercise the JS engine and compare core metrics in bands.
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createEngine } from "../web/release/src/50-scenarios.js";
import { C } from "../web/release/src/00-core.js";
import { produce } from "../web/release/src/10-models.js";
import { farmTargetLand, sellIdleFarmEquipment } from "../web/release/src/35-land.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const GOLDEN = JSON.parse(fs.readFileSync(path.join(ROOT, "web", "release", "src", "golden_v06.json"), "utf8"));
const SLOW = process.argv.includes("--slow");
const results = [];
let failures = 0;

function test(name, fn) {
  const started = Date.now();
  try {
    fn();
    results.push({ name, ok: true, ms: Date.now() - started });
    console.log(`ok   ${name} (${Date.now() - started} ms)`);
  } catch (error) {
    failures += 1;
    results.push({ name, ok: false, ms: Date.now() - started, error: error.message });
    console.error(`FAIL ${name}: ${error.message}`);
  }
}
function run(regime, months, seed = 1, priceRegime = "free", options = {}) {
  const { engine } = createEngine({ regime, seed, priceRegime, ...options });
  for (let month = 0; month < months; month++) engine.step();
  return engine;
}
function rel(a, b) { return Math.abs(a - b) / Math.max(Math.abs(b), 1e-9); }
function close(actual, expected, tolerance, label) {
  assert.ok(rel(actual, expected) <= tolerance,
    `${label}: JS ${actual} vs oracle ${expected} (${(rel(actual, expected) * 100).toFixed(1)}% > ${(tolerance * 100).toFixed(0)}%)`);
}
function finiteStat(stat) {
  for (const [key, value] of Object.entries(stat)) {
    if (typeof value === "number") assert.ok(Number.isFinite(value), `stat.${key} is not finite`);
  }
  for (const good of ["food", "meat", "coal", "iron_ore", "steel", "brick", "cloth", "fertilizer", "machinery", "building", "service", "car", "scrap"]) {
    assert.ok(Number.isFinite(stat.prices[good]) && stat.prices[good] > 0, `price ${good}`);
  }
  const shares = stat.market_budget_shares;
  const total = shares.food + shares.meat + shares.cloth + shares.housing + shares.service;
  assert.ok(Math.abs(total - 1) < 1e-6, `budget shares sum ${total}`);
}

// ---------------------------------------------------------------------
// 1. Determinism and money conservation
// ---------------------------------------------------------------------
test("determinism: same seed/config yields identical path", () => {
  const a = run("classical", 24, 7);
  const b = run("classical", 24, 7);
  for (const stat of a.stats) delete stat.warnings;
  for (const stat of b.stats) delete stat.warnings;
  const keys = ["population", "gdp", "money_total", "average_wage", "cpi", "profit_rate", "unemployment_rate"];
  for (let i = 0; i < a.stats.length; i++) {
    for (const key of keys) {
      assert.equal(a.stats[i][key], b.stats[i][key], `T${i + 1} ${key}`);
    }
  }
});

test("money conservation: gold-standard regimes keep total money constant", () => {
  for (const regime of ["classical", "keynesian", "late_capitalism"]) {
    const engine = run(regime, 60, 1);
    for (const stat of engine.stats) {
      assert.ok(Math.abs(stat.money_total - engine.moneyInitial) < 0.01,
        `${regime} T${stat.tick} money drift ${stat.money_total - engine.moneyInitial}`);
    }
  }
});

test("fiat money: MMT expands money and records central-bank debt", () => {
  const engine = run("mmt", 60, 1);
  const final = engine.stats.at(-1);
  assert.ok(final.money_total > engine.moneyInitial, "MMT money should grow");
  assert.ok(final.government_debt > 0, "MMT government debt should be positive");
  assert.ok(final.central_bank_money > 0, "MMT central-bank money should be positive");
});

// ---------------------------------------------------------------------
// 2. Scenario smoke tests and V0.6 mechanisms
// ---------------------------------------------------------------------
test("all four regimes run 12 months with finite stats", () => {
  for (const regime of ["classical", "keynesian", "mmt", "late_capitalism"]) {
    const engine = run(regime, 12, 1);
    finiteStat(engine.stats.at(-1));
    assert.ok(engine.stats.at(-1).population > 0, `${regime} population`);
    assert.ok(engine.stats.at(-1).gdp > 0, `${regime} gdp`);
  }
});

test("V0.6 demand / services / meat / free regime", () => {
  const engine = run("classical", 60, 1);
  const first = engine.stats[0];
  const final = engine.stats.at(-1);
  assert.ok(final.food_total_share < first.food_total_share + 1e-9,
    `food share should not rise from T1 (${first.food_total_share} -> ${final.food_total_share})`);
  assert.ok(final.service_employment_share > 0, "service employment should appear");
  assert.ok(final.service_spending_share > 0.1, "service budget share should be meaningful");
  const maxMeat = Math.max(...engine.stats.map((stat) => stat.production.meat || 0));
  assert.ok(maxMeat > 0, "livestock/meat production should occur");
  assert.equal(final.price_regime, "free");
  for (const good of Object.keys(final.price_floors)) {
    assert.equal(final.price_floors[good], 0, `free regime must not expose floors (${good})`);
    assert.equal(final.price_ceilings[good], 0, `free regime must not expose ceilings (${good})`);
  }
  assert.equal(engine.features.durablesA2, true, "A2 durables should be on by default");
  assert.equal(engine.features.creditRegimeC, false, "C must be explicitly deferred");
});

test("wage-productivity / work-hours institutions", () => {
  const classical = run("classical", 24, 1).stats.at(-1);
  const keynesian = run("keynesian", 24, 1).stats.at(-1);
  assert.equal(classical.standard_work_hours, 16);
  assert.equal(keynesian.standard_work_hours, 8);
  assert.ok(classical.average_hours <= 16 && classical.average_hours > 0);
  assert.ok(keynesian.average_hours <= 8 && keynesian.average_hours > 0);
  assert.ok(keynesian.average_wage > classical.average_wage,
    "Keynesian wage should exceed classical at same seed/month");
});

test("demography and PAYG pension hooks", () => {
  const engine = run("keynesian", 60, 1);
  const final = engine.stats.at(-1);
  assert.ok(final.children > 0 && final.working_age > 0, "population structure");
  assert.ok(final.pension_contributions > 0, "pension contributions should be collected");
  assert.ok(final.pension_spending > 0, "pension benefits should be paid");
  assert.ok(final.pension_fund >= 0, "pension fund cannot go negative");
});

// ---------------------------------------------------------------------
// 3. Golden-oracle band checks (60 months, all regimes)
// ---------------------------------------------------------------------
test("golden 60-month core-metric bands (all regimes)", () => {
  for (const runInfo of GOLDEN.runs.filter((item) => item.months === 60)) {
    const engine = run(runInfo.regime, runInfo.months, runInfo.seed, runInfo.price_regime, { durables: false });
    const js = engine.stats.at(-1);
    const py = runInfo.samples[String(runInfo.months)];
    close(js.population, py.population, 0.02, `${runInfo.regime} population`);
    close(js.gdp, py.gdp, 0.15, `${runInfo.regime} gdp`);
    close(js.cpi, py.cpi, 0.10, `${runInfo.regime} cpi`);
    close(js.average_wage, py.average_wage, 0.05, `${runInfo.regime} average wage`);
    assert.ok(Math.abs(js.food_total_share - py.food_total_share) <= 0.05,
      `${runInfo.regime} food share diff ${(js.food_total_share - py.food_total_share).toFixed(4)}`);
    assert.ok(Math.abs(js.service_spending_share - py.service_spending_share) <= 0.05,
      `${runInfo.regime} service share diff`);
    close(js.prices.food, py.prices.food, 0.10, `${runInfo.regime} food price`);
    close(js.money_total, py.money_total, 0.01, `${runInfo.regime} money total`);
  }
});

test("golden 240-month core-metric bands (classical, keynesian)", () => {
  for (const runInfo of GOLDEN.runs.filter((item) => item.months === 240 &&
    ["classical", "keynesian"].includes(item.regime))) {
    const engine = run(runInfo.regime, runInfo.months, runInfo.seed, runInfo.price_regime, { durables: false });
    const js = engine.stats.at(-1);
    const py = runInfo.samples[String(runInfo.months)];
    close(js.population, py.population, 0.03, `${runInfo.regime} population`);
    close(js.gdp, py.gdp, 0.15, `${runInfo.regime} gdp`);
    close(js.cpi, py.cpi, 0.10, `${runInfo.regime} cpi`);
    assert.ok(Math.abs(js.food_total_share - py.food_total_share) <= 0.05,
      `${runInfo.regime} food share diff`);
    close(js.money_total, py.money_total, 0.01, `${runInfo.regime} money total`);
  }
});

// ---------------------------------------------------------------------
// 4. A2 durables / scrap / land consolidation
// ---------------------------------------------------------------------
test("A2: cloth/housing wear rates and car lifetime", () => {
  const { engine } = createEngine({ regime: "classical", seed: 1, durables: true });
  engine.step();
  const worker = Array.from(engine.workers.values())
    .find((item) => item.alive && !item.isChild && !item.retired);
  assert.ok(worker, "expected an adult worker");
  const purchasedCloth = worker.monthPurchases.cloth || 0.0;
  const preCloth = worker.cloth + worker.clothWear - purchasedCloth;
  assert.ok(Math.abs(worker.clothWear - Math.max(0.0, preCloth) * C.CLOTH_WEAR_RATE) < 1e-8,
    "cloth wear must equal pre-purchase stock / 60");
  const purchasedHousing = worker.monthPurchases.building || 0.0;
  const preHousing = worker.housing + worker.housingWear - purchasedHousing;
  assert.ok(Math.abs(worker.housingWear - Math.max(0.0, preHousing) * C.HOUSING_WEAR_RATE) < 1e-8,
    "housing wear must equal pre-purchase stock / 600");
  assert.ok(worker.clothTargetStock > 0 && worker.housingTargetStock > 0,
    "soft durable stock targets should be set");

  const carWorker = Array.from(engine.workers.values())
    .find((item) => item.alive && !item.isChild && (item.cars || 0) <= 1e-9);
  assert.ok(carWorker, "expected a worker without a car");
  const scrapBefore = carWorker.scrap || 0.0;
  carWorker.cars = 1.0;
  carWorker.carBatches = [{ quantity: 1.0, monthsLeft: 2 }];
  engine.step();
  engine.step();
  assert.ok(Math.abs(carWorker.cars) < 1e-9, "car should retire at end of 120-month lifetime");
  assert.ok(carWorker.scrap >= scrapBefore + C.SCRAP_PER_CAR - 1e-9,
    "retired car should yield scrap exactly once");
});

test("A2: equipment vintage retirement creates scrap and replacement demand", () => {
  const { engine } = createEngine({ regime: "classical", seed: 1, durables: true });
  const owner = Array.from(engine.capitalists.values())[0];
  const enterprise = engine.createEnterprise({
    industry: "machinery_factory", ownerId: owner.id,
    cash: 10000.0, modernizationCapable: true,
  });
  enterprise.addEquipment("auto_t0", 1, C.EQUIPMENT_LIFETIME_MONTHS - 1);
  const generatedBefore = enterprise.scrapGenerated || 0.0;
  engine.step();
  assert.ok(enterprise.equipmentCount("auto_t0") <= 1e-9, "expired vintage should leave equipment map");
  const expectedScrap = 10.0 * C.SCRAP_PER_STEEL_GOOD;
  assert.ok((enterprise.scrapGenerated || 0.0) >= generatedBefore + expectedScrap - 1e-9,
    "equipment scrap should be generated once");
  const replacementStarted = enterprise.replacementDemand >= 1.0 ||
    engine.stats.at(-1).replacement_projects >= 1;
  assert.ok(replacementStarted, "retirement should create replacement demand/project");
  for (const [good, quantity] of Object.entries(enterprise.inventory)) {
    assert.ok(quantity >= -1e-9, `${good} inventory must not be negative`);
  }
});

test("A2: steel scrap recipe uses half coal and no negative inventories", () => {
  const { engine } = createEngine({ regime: "classical", seed: 1, durables: true });
  const mill = engine.activeEnterprises("steel_mill")[0];
  assert.ok(mill, "expected a steel mill");
  mill.planRatio = 1.0;
  mill.inventory.iron_ore = 0.0;
  mill.inventory.scrap = 100.0;
  mill.inventory.coal = 100.0;
  const scrap0 = mill.inv("scrap");
  const coal0 = mill.inv("coal");
  const output = produce(engine, mill);
  assert.ok(output > 1e-9, "scrap route should produce steel");
  assert.ok(Math.abs((scrap0 - mill.inv("scrap")) - output * 1.5) < 1e-6,
    "scrap use must be 1.5 per steel");
  assert.ok(Math.abs((coal0 - mill.inv("coal")) - output * 0.5) < 1e-6,
    "scrap route must use half the coal of the ore route");
  assert.ok(mill.inv("scrap") >= -1e-9 && mill.inv("coal") >= -1e-9);
});

test("A2: land consolidation raises farm target and retires surplus small machines as scrap", () => {
  const { engine } = createEngine({ regime: "classical", seed: 1, durables: true });
  const owner = Array.from(engine.capitalists.values())[0];
  const enterprise = engine.createEnterprise({
    industry: "agriculture", ownerId: owner.id, cash: 10000.0,
    land: C.TARGET_CAPITALIST_FARM_MU, modernizationCapable: true,
  });
  enterprise.addEquipment("farm_t4", 1, 0);
  enterprise.addEquipment("farm_t0", 2, 0);
  assert.ok(farmTargetLand(enterprise) + 1e-9 >= C.CONSOLIDATED_FARM_MU,
    "power >= 4 should permit a 200-mu consolidated farm");
  const landBefore = enterprise.land;
  const smallBefore = enterprise.equipmentCount("farm_t0");
  const scrapBefore = enterprise.inv("scrap");
  sellIdleFarmEquipment(engine);
  assert.equal(enterprise.land, landBefore, "consolidation must not duplicate land");
  assert.ok(enterprise.equipmentCount("farm_t0") < smallBefore,
    "surplus small machinery should be sold/scrapped");
  assert.ok(enterprise.inv("scrap") > scrapBefore, "sold small machinery should yield scrap");
  const vintageSmall = enterprise.vintages
    .filter((batch) => batch.key === "farm_t0")
    .reduce((sum, batch) => sum + batch.quantity, 0.0);
  assert.ok(Math.abs(vintageSmall - enterprise.equipmentCount("farm_t0")) < 1e-9,
    "vintage quantities must match equipment counts");
});

test("A2: 60-month stock conservation, money conservation and no famine", () => {
  const engine = run("classical", 60, 1, "free", { durables: true });
  const final = engine.stats.at(-1);
  assert.ok(Math.abs(final.money_total - engine.moneyInitial) < 0.01, "money drift");
  assert.ok(engine.stats.reduce((sum, stat) => sum + stat.hunger_deaths, 0) === 0,
    "A2 should not regress into famine at 60 months");
  assert.ok(final.cloth_stock_per_adult > 0 && final.housing_stock_per_adult > 0,
    "durable stocks should exist");
  assert.ok(final.car_stock >= 0 && final.scrap_inventory >= 0, "car/scrap stocks nonnegative");
  assert.ok(final.scrap_price > 0 && final.steel_scrap_output >= 0, "scrap market should be priced");
  for (const enterprise of engine.enterprises.values()) {
    if (!enterprise.active) continue;
    for (const [good, quantity] of Object.entries(enterprise.inventory)) {
      assert.ok(quantity >= -1e-9, `${enterprise.id}.${good} inventory negative`);
    }
  }
  for (const worker of engine.workers.values()) {
    if (!worker.alive) continue;
    assert.ok(worker.cloth >= -1e-9 && worker.housing >= -1e-9 &&
      worker.cars >= -1e-9 && (worker.scrap || 0) >= -1e-9,
      "household durable stocks must not be negative");
  }
  // Dead workers are excluded from every stock aggregate and market; their
  // durables must be settled to the heir or the estate asset pool.
  for (const worker of engine.workers.values()) {
    if (worker.alive) continue;
    assert.ok((worker.cloth || 0) < 1e-9 && (worker.housing || 0) < 1e-9 &&
      (worker.cars || 0) < 1e-9 && (worker.scrap || 0) < 1e-9,
      `${worker.id} retained durable stocks after death`);
  }
});

test("A2 off: car/scrap zero-output warnings are suppressed", () => {
  const engine = run("classical", 60, 1, "free", { durables: false });
  const stat = engine.stats.at(-1);
  assert.equal(stat.warnings.filter((warning) => /汽车|废钢/.test(warning)).length, 0,
    "A2-off oracle replay should not warn about car/scrap zero output");
  assert.ok(!stat.zero_output_streak.car, "car zero-output streak should be absent/zero");
  assert.ok(!stat.zero_output_streak.scrap, "scrap zero-output streak should be absent/zero");
});

// ---------------------------------------------------------------------
// 5. Performance / invariants
// ---------------------------------------------------------------------
test("performance: 60-month classical run under 20 s", () => {
  const started = Date.now();
  run("classical", 60, 1);
  const elapsed = Date.now() - started;
  assert.ok(elapsed < 20000, `60-month run took ${elapsed} ms`);
});

if (SLOW) {
  test("slow: all four regimes complete 240 months without NaN", () => {
    for (const regime of ["classical", "keynesian", "mmt", "late_capitalism"]) {
      const engine = run(regime, 240, 1);
      finiteStat(engine.stats.at(-1));
      assert.ok(engine.stats.at(-1).population > 0, `${regime} population should survive 240 months`);
      if (regime === "classical") {
        assert.equal(engine.stats.reduce((sum, stat) => sum + stat.hunger_deaths, 0), 0,
          "classical A2 must not regress into famine at 240 months");
        assert.ok(engine.stats.at(-1).production.machinery > 0,
          "classical machinery supply must survive A2 retirement");
        assert.ok(engine.stats.at(-1).production.steel > 0,
          "classical steel supply must not collapse");
      }
      if (regime === "keynesian") {
        assert.ok(engine.stats.at(-1).production.fertilizer > 0,
          "keynesian fertilizer supply must not collapse");
        for (const enterprise of engine.enterprises.values()) {
          if (enterprise.active && enterprise.industry !== "agriculture") {
            assert.ok(enterprise.equipment.size > 0,
              `${enterprise.id} (${enterprise.industry}) is active without equipment`);
          }
        }
      }
    }
  });
}

console.log(`\n${results.filter((item) => item.ok).length}/${results.length} tests passed.`);
if (failures) {
  console.error(`${failures} failure(s).`);
  process.exitCode = 1;
}
