/**
 * Replay the Python golden matrix through the JS engine and report deviations.
 *
 * Usage:
 *   node scripts/compare_golden_v06.mjs [--months=60] [--regime=classical] [--json=path]
 *
 * The JS engine is the release source of truth; this script only measures how
 * far the first JS milestone has drifted from the migration oracle.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createEngine } from "../web/release/src/50-scenarios.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const GOLDEN_PATH = path.join(ROOT, "web", "release", "src", "golden_v06.json");

const args = Object.fromEntries(process.argv.slice(2).map((arg) => {
  const [key, value] = arg.replace(/^--/, "").split("=");
  return [key, value === undefined ? true : value];
}));

const golden = JSON.parse(fs.readFileSync(GOLDEN_PATH, "utf8"));
const onlyMonths = args.months ? Number(args.months) : null;
const onlyRegime = args.regime || null;

const FIELDS = [
  "population", "gdp", "consumption", "investment", "unemployment_rate",
  "profit_rate", "average_wage", "cpi", "money_total",
  "food_output", "ag_productivity", "service_employment_share",
  "food_share", "meat_share", "cloth_share", "housing_share",
  "service_spending_share", "market_food_total_share",
  "bank_loans", "government_debt", "land_price", "capital_stock",
];
const PRICE_GOODS = ["food", "meat", "coal", "iron_ore", "steel", "brick", "cloth", "fertilizer", "machinery", "building", "service"];

function fmt(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return Number(value).toFixed(digits);
}
function pctDeviation(jsValue, pyValue) {
  if (Math.abs(pyValue) < 1e-9) return Math.abs(jsValue - pyValue) < 1e-6 ? 0 : Infinity;
  return (jsValue - pyValue) / Math.abs(pyValue) * 100;
}
function sampleJs(engine, tick) {
  const stat = engine.stats[tick - 1];
  return stat;
}

let failures = 0;
const report = [];
for (const run of golden.runs) {
  if (onlyMonths && run.months !== onlyMonths) continue;
  if (onlyRegime && run.regime !== onlyRegime) continue;
  const t0 = Date.now();
  const { engine } = createEngine({
    regime: run.regime,
    seed: run.seed,
    priceRegime: run.price_regime,
  });
  const samples = {};
  for (let month = 1; month <= run.months; month++) {
    engine.step();
    if (run.samples[String(month)]) samples[month] = sampleJs(engine, month);
  }
  const rows = [];
  for (const [tickText, py] of Object.entries(run.samples)) {
    const tick = Number(tickText);
    const js = samples[tick];
    if (!js) continue;
    const deviations = [];
    for (const field of FIELDS) {
      const dev = pctDeviation(js[field], py[field]);
      deviations.push({ field, dev, js: js[field], py: py[field] });
    }
    for (const good of PRICE_GOODS) {
      const dev = pctDeviation(js.prices[good], py.prices[good]);
      deviations.push({ field: `price.${good}`, dev, js: js.prices[good], py: py.prices[good] });
    }
    rows.push({ tick, deviations });
  }
  const worst = rows.flatMap((row) => row.deviations.map((dev) => ({ ...dev, tick: row.tick })))
    .filter((dev) => Number.isFinite(dev.dev))
    .sort((a, b) => Math.abs(b.dev) - Math.abs(a.dev));
  const final = rows[rows.length - 1];
  console.log(`\n=== ${run.regime} · seed ${run.seed} · ${run.months}mo · ${((Date.now() - t0) / 1000).toFixed(1)}s ===`);
  const headline = final.deviations.filter((dev) =>
    ["population", "gdp", "investment", "unemployment_rate", "profit_rate", "cpi", "average_wage", "money_total",
      "food_share", "service_spending_share", "price.food", "price.coal", "price.steel"].includes(dev.field));
  for (const dev of headline) {
    const flag = Math.abs(dev.dev) <= 5 ? "ok" : Math.abs(dev.dev) <= 15 ? "watch" : "DIVERGED";
    console.log(`  T${final.tick} ${dev.field.padEnd(28)} JS ${fmt(dev.js, 3).padStart(12)}  PY ${fmt(dev.py, 3).padStart(12)}  ${fmt(dev.dev, 2).padStart(8)}%  ${flag}`);
  }
  console.log("  worst deviations:");
  for (const dev of worst.slice(0, 5)) {
    console.log(`    T${dev.tick} ${dev.field.padEnd(28)} ${fmt(dev.dev, 1).padStart(9)}%  (JS ${fmt(dev.js, 3)}, PY ${fmt(dev.py, 3)})`);
  }
  const gdpDev = final.deviations.find((dev) => dev.field === "gdp")?.dev ?? Infinity;
  if (!Number.isFinite(gdpDev) || Math.abs(gdpDev) > 15) failures += 1;
  report.push({ run: { regime: run.regime, seed: run.seed, months: run.months }, rows });
}

if (args.json) {
  fs.writeFileSync(args.json, JSON.stringify(report, null, 2));
  console.log(`\nwrote ${args.json}`);
}
console.log(`\n${failures} run(s) outside the ±15% GDP band.`);
process.exitCode = failures ? 1 : 0;
