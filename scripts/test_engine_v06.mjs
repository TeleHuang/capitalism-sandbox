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
function run(regime, months, seed = 1, priceRegime = "free") {
  const { engine } = createEngine({ regime, seed, priceRegime });
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
  for (const good of ["food", "meat", "coal", "iron_ore", "steel", "brick", "cloth", "fertilizer", "machinery", "building", "service"]) {
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
  assert.equal(engine.features.durablesA2, false, "A2 must be explicitly deferred");
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
    const engine = run(runInfo.regime, runInfo.months, runInfo.seed, runInfo.price_regime);
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
    const engine = run(runInfo.regime, runInfo.months, runInfo.seed, runInfo.price_regime);
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
// 4. Performance / invariants
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
    }
  });
}

console.log(`\n${results.filter((item) => item.ok).length}/${results.length} tests passed.`);
if (failures) {
  console.error(`${failures} failure(s).`);
  process.exitCode = 1;
}
