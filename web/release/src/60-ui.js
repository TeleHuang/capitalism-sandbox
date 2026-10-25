/*
 * EcoSim V0.6 · release UI — module 60.
 *
 * Player-facing cockpit for the single-file build. Only uses the ES-module
 * engine and data embedded in the HTML; no fetch, no CDN, no external assets.
 */
import {
  C, GOODS, INDUSTRIES, GOOD_LABELS, GOOD_UNITS, INDUSTRY_LABELS,
  INITIAL_PRICES, EQUIPMENT, SECTOR_PARAMS,
} from "./00-core.js";
import { SCENARIOS, SCENARIO_ORDER, createEngine } from "./50-scenarios.js";

/* ------------------------------------------------------------------ */
/* small utilities                                                     */
/* ------------------------------------------------------------------ */
const $ = (id) => document.getElementById(id);
const state = {
  regime: "classical",
  seed: 1,
  months: 240,
  priceRegime: "free",
  durables: true,
  engine: null,
  config: null,
  month: 1,
  running: false,
  playing: false,
  playTimer: null,
  view: "overview",
  scaleIndustry: "coal_mine",
  factoryIndustry: null,
  factoryTrigger: null,
  elapsed: 0,
  startedAt: 0,
  runToken: 0,
};

function escapeHtml(value) {
  return String(value === undefined || value === null ? "" : value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
function num(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : (fallback === undefined ? 0 : fallback);
}
function fmtNum(value, digits) {
  const d = digits === undefined ? 2 : digits;
  if (!Number.isFinite(value)) return "—";
  return num(value).toLocaleString("zh-CN", {
    minimumFractionDigits: d, maximumFractionDigits: d,
  });
}
function fmtInt(value) {
  if (!Number.isFinite(value)) return "—";
  return Math.round(value).toLocaleString("zh-CN");
}
function fmtCompact(value) {
  if (!Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  if (abs >= 1e8) return `${(value / 1e8).toFixed(2)} 亿`;
  if (abs >= 1e5) return `${(value / 1e4).toFixed(1)} 万`;
  if (abs >= 1e4) return `${(value / 1e4).toFixed(2)} 万`;
  return fmtInt(value);
}
function fmtSigned(value, digits) {
  if (!Number.isFinite(value)) return "—";
  const d = digits === undefined ? 0 : digits;
  const sign = value > 0 ? "+" : "";
  return sign + fmtNum(value, d);
}
function fmtPct(value, digits) {
  if (!Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(digits === undefined ? 1 : digits)}%`;
}
function fmtDelta(value, digits) {
  if (!Number.isFinite(value)) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits === undefined ? 2 : digits)}`;
}
function clamp(value, low, high) { return Math.max(low, Math.min(high, value)); }
function currentStat() {
  if (!state.engine) return null;
  return state.engine.stats[clamp(state.month - 1, 0, state.engine.stats.length - 1)] || null;
}
function statAt(month) {
  if (!state.engine) return null;
  return state.engine.stats[clamp(month - 1, 0, state.engine.stats.length - 1)] || null;
}
function series(key, scale) {
  if (!state.engine) return [];
  const factor = scale === undefined ? 1 : scale;
  const out = [];
  for (let i = 0; i < state.month; i++) {
    const stat = state.engine.stats[i];
    let value;
    if (typeof key === "function") value = key(stat);
    else if (key.includes(".")) {
      const [first, second] = key.split(".");
      value = stat[first] ? stat[first][second] : undefined;
    } else value = stat[key];
    out.push(num(value) * factor);
  }
  return out;
}
function getGood(stat, path, good) {
  const obj = stat[path] || {};
  return num(obj[good]);
}

/* ------------------------------------------------------------------ */
/* inline SVG product icons (adapted from the V0.6 diagnostic cockpit) */
/* ------------------------------------------------------------------ */
const ICON_STROKE = 'stroke="#071014" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"';
function iconWrap(body) {
  return `<svg class="good-icon" viewBox="0 0 40 40" aria-hidden="true" focusable="false">${body}</svg>`;
}
const ICONS = {
  food: () => iconWrap(
    `<path d="M12 17c0-3 3-5 8-5s8 2 8 5l3 14c.6 2.6-1 4.6-3.8 4.6H12.8C10 35.6 8.4 33.6 9 31z" fill="#dda95a" ${ICON_STROKE}/>` +
    `<path d="M15 13c0-2.4 2.1-4.2 5-4.2s5 1.8 5 4.2l-2 3.4h-6z" fill="#b47632" ${ICON_STROKE}/>` +
    `<path d="M17 9.5l3-4 3 4" fill="none" stroke="#7c4d1f" stroke-width="2" stroke-linecap="round"/>` +
    `<circle cx="17" cy="24" r="1.3" fill="#8b5a24"/><circle cx="22.5" cy="27" r="1.3" fill="#8b5a24"/>` +
    `<circle cx="20" cy="20" r="1.3" fill="#8b5a24"/>` +
    `<path d="M14 31.5c4-1 8-1 12 0" fill="none" stroke="#b47632" stroke-width="1.5" opacity=".7"/>`),
  meat: () => iconWrap(
    `<path d="M10 22c-2-5 1-11 7-12 6-1 12 3 13 9 1 6-3 12-9 13-5 1-9-2-11-10z" fill="#c96b5b" ${ICON_STROKE}/>` +
    `<path d="M16 15c3-2 8-1 10 3 2 4 0 9-4 11-4 1-7-1-8-5" fill="#e39b8c" stroke="none"/>` +
    `<circle cx="26" cy="17" r="3.2" fill="#f5e5c8" ${ICON_STROKE}/>` +
    `<path d="M23 31l-2 5M28 30l1 5" stroke="#7b3d33" stroke-width="2" stroke-linecap="round"/>`),
  coal: () => iconWrap(
    `<path d="M8 27l3-11 8-5 11 3 3 9-7 8-12 1z" fill="#3f4c56" ${ICON_STROKE}/>` +
    `<path d="M11 16l8-5 5 6-7 5z" fill="#5b6b77" stroke="none"/>` +
    `<path d="M19 22l7-5 3 6-6 4z" fill="#2e3840" stroke="none"/>` +
    `<path d="M10 23l4-2M24 27l4-2" stroke="#92a4b1" stroke-width="1.6" fill="none" opacity=".65"/>`),
  iron_ore: () => iconWrap(
    `<path d="M9 29l2-10 7-7 9 2 5 9-4 9-11 2z" fill="#8d8171" ${ICON_STROKE}/>` +
    `<path d="M12 19l6-5 4 4-6 5z" fill="#aa9b84" stroke="none"/>` +
    `<circle cx="23" cy="24" r="2.1" fill="#b25b44" stroke="none"/>` +
    `<circle cx="16" cy="26" r="1.5" fill="#b25b44" stroke="none"/>` +
    `<path d="M11 30l18-1M22 10l2 5" stroke="#6c6256" stroke-width="1.4" fill="none" opacity=".8"/>`),
  steel: () => iconWrap(
    `<g transform="rotate(-8 20 20)"><path d="M8 7h24v6h-8v14h8v6H8v-6h8V13H8z" fill="#7fa2bf" ${ICON_STROKE}/>` +
    `<path d="M10 9h20v2H10z" fill="#c2dced" stroke="none"/>` +
    `<path d="M19 13h2v14h-2z" fill="#a9c8dd" stroke="none"/>` +
    `<circle cx="12" cy="10" r="1" fill="#e8f4fb" stroke="none"/>` +
    `<circle cx="28" cy="30" r="1" fill="#e8f4fb" stroke="none"/></g>`),
  brick: () => iconWrap(
    `<g transform="rotate(-2 20 22)"><rect x="6" y="15" width="14" height="9" rx="1.6" fill="#c15a3f" ${ICON_STROKE}/>` +
    `<rect x="22" y="15" width="12" height="9" rx="1.6" fill="#b04c36" ${ICON_STROKE}/>` +
    `<rect x="10" y="26" width="20" height="9" rx="1.6" fill="#cf7050" ${ICON_STROKE}/>` +
    `<path d="M9 17.5h8M24 17.5h7M14 28.5h11" stroke="#f1d3bd" stroke-width="1.3" stroke-linecap="round" opacity=".8"/></g>`),
  cloth: () => iconWrap(
    `<path d="M15 7l5 3 5-3 9 5-4.5 8-3.5-2v13.5H14V18l-3.5 2L6 12z" fill="#4fa89a" ${ICON_STROKE}/>` +
    `<path d="M15 7l5 3 5-3" fill="none" stroke="#2f6f66" stroke-width="1.8"/>` +
    `<path d="M20 13v18.5" stroke="#2f6f66" stroke-width="1.3"/>` +
    `<circle cx="20" cy="19" r="1.2" fill="#e9f5ef"/><circle cx="20" cy="24" r="1.2" fill="#e9f5ef"/>` +
    `<path d="M8.5 12.5l2.5 5M31.5 12.5l-2.5 5" stroke="#2f6f66" stroke-width="1.2"/>`),
  fertilizer: () => iconWrap(
    `<path d="M12 12h16l2 17.5c.3 2.4-1.3 4-3.5 4H13.5C11.3 33.5 9.7 32 10 29.5z" fill="#6f9c46" ${ICON_STROKE}/>` +
    `<path d="M14 8h12l2.5 4.5h-17z" fill="#507a2f" ${ICON_STROKE}/>` +
    `<path d="M20 17.5c-4.5 0-7 3-7 6.5 4.5 0 7-2.5 7-6.5z" fill="#c8e6a0" stroke="none"/>` +
    `<path d="M20 17.5c4.5 0 7 3 7 6.5-4.5 0-7-2.5-7-6.5z" fill="#a8d478" stroke="none"/>` +
    `<path d="M20 24v6" stroke="#e9f5d8" stroke-width="1.6" stroke-linecap="round"/>`),
  machinery: () => iconWrap(
    `<g fill="#d68f2e" ${ICON_STROKE}><rect x="17" y="1.5" width="6" height="10" rx="1.4"/>` +
    `<rect x="17" y="28.5" width="6" height="10" rx="1.4"/><rect x="1.5" y="17" width="10" height="6" rx="1.4"/>` +
    `<rect x="28.5" y="17" width="10" height="6" rx="1.4"/>` +
    `<rect x="5" y="5" width="6" height="10" rx="1.4" transform="rotate(-45 8 10)"/>` +
    `<rect x="24" y="5" width="6" height="10" rx="1.4" transform="rotate(45 27 10)"/>` +
    `<rect x="5" y="25" width="6" height="10" rx="1.4" transform="rotate(45 8 30)"/>` +
    `<rect x="24" y="25" width="6" height="10" rx="1.4" transform="rotate(-45 27 30)"/></g>` +
    `<circle cx="20" cy="20" r="11" fill="#e0a03c" ${ICON_STROKE}/>` +
    `<circle cx="20" cy="20" r="4.3" fill="#26323a" stroke="#071014" stroke-width="1.5"/>`),
  building: () => iconWrap(
    `<path d="M20 4L3.5 18h33z" fill="#b8583f" ${ICON_STROKE}/>` +
    `<rect x="9" y="18" width="22" height="16" rx="1" fill="#d8c097" ${ICON_STROKE}/>` +
    `<rect x="17" y="25" width="7" height="9" rx="1" fill="#7b4c2f" stroke="#071014" stroke-width="1.5"/>` +
    `<rect x="11.5" y="21" width="4" height="4" rx=".8" fill="#9fd7e8" stroke="#071014" stroke-width="1.2"/>` +
    `<rect x="24.5" y="21" width="4" height="4" rx=".8" fill="#9fd7e8" stroke="#071014" stroke-width="1.2"/>`),
  service: () => iconWrap(
    `<rect x="8" y="17" width="24" height="17" rx="1.5" fill="#c98a5e" ${ICON_STROKE}/>` +
    `<path d="M5 12h30l-3.5 8H8.5z" fill="#3f9d8f" ${ICON_STROKE}/>` +
    `<path d="M12.5 12.5L11 19.5M20 12.5v7M27.5 12.5l1.5 7" stroke="#dff3ee" stroke-width="2.2" stroke-linecap="round"/>` +
    `<rect x="16.5" y="23" width="7" height="11" rx="1" fill="#5b3a28" stroke="#071014" stroke-width="1.4"/>` +
    `<rect x="9.5" y="22.5" width="4" height="4" rx=".8" fill="#9fd7e8" stroke="#071014" stroke-width="1.2"/>`),
  car: () => iconWrap(
    `<path d="M6 25l3-8 5-4h12l5 4 3 8v6H6z" fill="#5fa7c9" ${ICON_STROKE}/>` +
    `<path d="M10 18l4-4h12l4 4z" fill="#a9d8ea" stroke="#071014" stroke-width="1.4"/>` +
    `<circle cx="12" cy="30" r="3.2" fill="#26323a" ${ICON_STROKE}/>` +
    `<circle cx="28" cy="30" r="3.2" fill="#26323a" ${ICON_STROKE}/>` +
    `<rect x="7" y="24" width="4" height="2" rx="1" fill="#f2d76a" stroke="none"/>` +
    `<rect x="29" y="24" width="4" height="2" rx="1" fill="#e8f4fb" stroke="none"/>`),
  scrap: () => iconWrap(
    `<path d="M8 31l4-10 7 2 3-7 6 6 4-2 2 11z" fill="#8d99a6" ${ICON_STROKE}/>` +
    `<path d="M12 21l5 3 3-6 4 5 5-1" fill="none" stroke="#c7d3dd" stroke-width="1.6"/>` +
    `<path d="M9 32h23" stroke="#5d6a75" stroke-width="2" stroke-linecap="round"/>` +
    `<rect x="15" y="12" width="3" height="7" rx="1" transform="rotate(-25 16.5 15.5)" fill="#b8c4ce" stroke="#071014" stroke-width="1"/>` +
    `<rect x="25" y="10" width="3" height="8" rx="1" transform="rotate(18 26.5 14)" fill="#9aa8b4" stroke="#071014" stroke-width="1"/>`),
  person: () => iconWrap(
    `<circle cx="20" cy="11.5" r="6.2" fill="#6cb3e6" ${ICON_STROKE}/>` +
    `<path d="M8 34c0-7 4.8-12.4 12-12.4S32 27 32 34z" fill="#3987e5" ${ICON_STROKE}/>`),
  coin: () => iconWrap(
    `<circle cx="20" cy="20" r="14" fill="#e5b93c" ${ICON_STROKE}/>` +
    `<circle cx="20" cy="20" r="9.5" fill="#f2cd66" stroke="#8a6510" stroke-width="1.6"/>` +
    `<text x="20" y="25.2" text-anchor="middle" font-size="13" font-weight="700" fill="#7a5a0f">¥</text>`),
  bank: () => iconWrap(
    `<path d="M20 4L3 13.5h34z" fill="#d6c39a" ${ICON_STROKE}/>` +
    `<rect x="6" y="14" width="28" height="3" fill="#b49a6a" stroke="#071014" stroke-width="1.4"/>` +
    `<rect x="8.5" y="18" width="4" height="12" fill="#d9c69c" stroke="#071014" stroke-width="1.4"/>` +
    `<rect x="17.5" y="18" width="5" height="12" fill="#d9c69c" stroke="#071014" stroke-width="1.4"/>` +
    `<rect x="27.5" y="18" width="4" height="12" fill="#d9c69c" stroke="#071014" stroke-width="1.4"/>` +
    `<rect x="5" y="30" width="30" height="5" rx=".8" fill="#b49a6a" stroke="#071014" stroke-width="1.4"/>`),
  land: () => iconWrap(
    `<rect x="4" y="21" width="32" height="13" rx="2" fill="#6f9146" ${ICON_STROKE}/>` +
    `<path d="M5 26h30M5 31h30" stroke="#4d6b2f" stroke-width="1.5"/>` +
    `<path d="M20 24v-8" stroke="#4d6b2f" stroke-width="2.2" stroke-linecap="round"/>` +
    `<path d="M20 18c-4 0-6.5-2-6.5-5.5 4.5 0 6.5 2.2 6.5 5.5z" fill="#9ac96a" stroke="#071014" stroke-width="1.4"/>` +
    `<path d="M20 18c4 0 6.5-2 6.5-5.5-4.5 0-6.5 2.2-6.5 5.5z" fill="#7fb54f" stroke="#071014" stroke-width="1.4"/>`),
  generic: () => iconWrap(
    `<rect x="6" y="11" width="28" height="23" rx="2.5" fill="#9b8159" ${ICON_STROKE}/>` +
    `<path d="M6 19h28M6 27h28M14 11v23M26 11v23" stroke="#6b5638" stroke-width="1.5"/>` +
    `<text x="20" y="27.5" text-anchor="middle" font-size="14" font-weight="700" fill="#f5e9cf">?</text>`),
};
function goodIcon(id, extraClass) {
  const key = Object.prototype.hasOwnProperty.call(ICONS, id) ? id : "generic";
  let body = ICONS[key]();
  if (extraClass) body = body.replace('class="good-icon"', `class="good-icon ${extraClass}"`);
  return body;
}
function iconChip(id, label, extraClass) {
  return `<span class="icon-label ${extraClass || ""}">${goodIcon(id, "sm")}<span class="icon-label-text">${escapeHtml(label)}</span></span>`;
}
const GOOD_TO_INDUSTRY = {};
for (const industry of INDUSTRIES) GOOD_TO_INDUSTRY[SECTOR_PARAMS.get(industry).output] = industry;
// Scrap has no producing industry; clicking it opens the main scrap consumer.
GOOD_TO_INDUSTRY.scrap = "steel_mill";

/* ------------------------------------------------------------------ */
/* charts                                                              */
/* ------------------------------------------------------------------ */
const tooltip = document.createElement("div");
tooltip.className = "chart-tooltip";
tooltip.hidden = true;
document.body.appendChild(tooltip);
function hideTooltip() { tooltip.hidden = true; }
function showTooltip(event, html) {
  tooltip.innerHTML = html;
  tooltip.hidden = false;
  const pad = 14;
  let left = event.clientX + pad;
  let top = event.clientY + pad;
  const rect = tooltip.getBoundingClientRect();
  if (left + rect.width > window.innerWidth - 8) left = event.clientX - rect.width - pad;
  if (top + rect.height > window.innerHeight - 8) top = event.clientY - rect.height - pad;
  tooltip.style.left = `${Math.max(8, left)}px`;
  tooltip.style.top = `${Math.max(8, top)}px`;
}
function axisFormat(value, pct, digits) {
  if (pct) return `${value.toFixed(0)}%`;
  const abs = Math.abs(value);
  if (abs >= 1e8) return `${(value / 1e8).toFixed(1)}亿`;
  if (abs >= 1e4) return `${(value / 1e4).toFixed(0)}万`;
  if (abs >= 100) return value.toFixed(0);
  return value.toFixed(digits === undefined ? 1 : digits);
}
function chartLegend(series) {
  if (!series.length) return "";
  return `<div class="legend">${series.map((item) =>
    `<span><i style="background:${item.color}"></i>${escapeHtml(item.label)}</span>`).join("")}</div>`;
}
function lineChart(host, series, options) {
  const opts = options || {};
  const width = 680;
  const height = opts.height || 210;
  const margin = { left: opts.pct ? 42 : 52, right: 14, top: 14, bottom: 22 };
  const count = Math.max(1, state.month);
  const xMax = Math.max(2, count);
  const values = [];
  for (const item of series) {
    for (let i = 0; i < count; i++) {
      const value = item.values[i];
      if (Number.isFinite(value)) values.push(value);
    }
  }
  if (!values.length) { host.innerHTML = '<div class="chart-empty">暂无数据</div>'; return; }
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (opts.zeroBase || opts.pct) min = Math.min(0, min);
  if (max - min < 1e-9) { max += 1; min -= 1; }
  const span = max - min;
  min -= span * 0.06;
  max += span * 0.08;
  if (opts.zeroBase && min < 0) min = 0;
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const x = (index) => margin.left + (index / (xMax - 1)) * plotW;
  const y = (value) => margin.top + (1 - (value - min) / (max - min)) * plotH;
  const gridCount = 4;
  let grid = "";
  for (let i = 0; i <= gridCount; i++) {
    const value = min + (max - min) * i / gridCount;
    const gy = y(value);
    grid += `<line class="chart-grid" x1="${margin.left}" y1="${gy}" x2="${width - margin.right}" y2="${gy}"/>`;
    grid += `<text class="chart-axis" x="${margin.left - 6}" y="${gy + 3}" text-anchor="end">${axisFormat(value, opts.pct, opts.digits)}</text>`;
  }
  if (min < 0 && max > 0) {
    grid += `<line class="chart-zero" x1="${margin.left}" y1="${y(0)}" x2="${width - margin.right}" y2="${y(0)}"/>`;
  }
  const tickIndices = [];
  const tickCount = width < 500 ? 3 : 5;
  for (let i = 0; i < tickCount; i++) {
    tickIndices.push(Math.round(1 + (count - 1) * i / (tickCount - 1)));
  }
  let xAxis = "";
  for (const tick of Array.from(new Set(tickIndices))) {
    xAxis += `<text class="chart-axis" x="${x(tick - 1)}" y="${height - 6}" text-anchor="middle">T${tick}</text>`;
  }
  let paths = "";
  for (const item of series) {
    const points = [];
    for (let i = 0; i < count; i++) {
      const value = item.values[i];
      if (Number.isFinite(value)) points.push([x(i), y(value)]);
    }
    if (!points.length) continue;
    const d = points.map((point, index) => `${index ? "L" : "M"}${point[0].toFixed(2)} ${point[1].toFixed(2)}`).join(" ");
    if (opts.area) {
      paths += `<path class="chart-area" style="fill:${item.color}" d="${d} L${points[points.length - 1][0].toFixed(2)} ${y(Math.max(0, min)).toFixed(2)} L${points[0][0].toFixed(2)} ${y(Math.max(0, min)).toFixed(2)} Z"/>`;
    }
    paths += `<path class="chart-line" style="stroke:${item.color}" d="${d}"/>`;
    const last = points[points.length - 1];
    paths += `<circle cx="${last[0].toFixed(2)}" cy="${last[1].toFixed(2)}" r="2.7" fill="${item.color}" stroke="#0b1218" stroke-width="1"/>`;
  }
  const plotLeft = margin.left;
  const plotRight = width - margin.right;
  const plotTop = margin.top;
  const plotBottom = height - margin.bottom;
  host.innerHTML = chartLegend(series) +
    `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(opts.aria || "趋势图")}">` +
    `${grid}${xAxis}<g class="chart-plot">${paths}</g>` +
    `<line id="hover-line" class="chart-marker" x1="0" y1="${plotTop}" x2="0" y2="${plotBottom}" opacity="0"/>` +
    `<rect id="hover-rect" x="${plotLeft}" y="${plotTop}" width="${plotRight - plotLeft}" height="${plotBottom - plotTop}" fill="transparent"/>` +
    `</svg>`;
  const svg = host.querySelector("svg");
  const hoverLine = svg.querySelector("#hover-line");
  const hoverRect = svg.querySelector("#hover-rect");
  const move = (event) => {
    const rect = svg.getBoundingClientRect();
    const px = (event.clientX - rect.left) / rect.width * width;
    const ratio = clamp((px - plotLeft) / Math.max(1, plotRight - plotLeft), 0, 1);
    const index = clamp(Math.round(ratio * (count - 1)), 0, count - 1);
    const gx = x(index);
    hoverLine.setAttribute("x1", gx);
    hoverLine.setAttribute("x2", gx);
    hoverLine.setAttribute("opacity", "0.7");
    let rows = "";
    for (const item of series) {
      const value = item.values[index];
      if (!Number.isFinite(value)) continue;
      rows += `<div class="tt-row"><span style="color:${item.color}">${escapeHtml(item.label)}</span><b>${opts.pct ? value.toFixed(2) + "%" : fmtNum(value, opts.digits === undefined ? 1 : opts.digits)}</b></div>`;
    }
    showTooltip(event, `<strong>T${index + 1}</strong>${rows}`);
  };
  hoverRect.addEventListener("mousemove", move);
  hoverRect.addEventListener("mouseleave", () => {
    hideTooltip();
    if (hoverLine) hoverLine.setAttribute("opacity", "0");
  });
}
function sharesChart(host) {
  const count = Math.max(1, state.month);
  const width = 680;
  const height = 220;
  const margin = { left: 40, right: 12, top: 12, bottom: 22 };
  const keys = [
    ["food", "食品", "#e0a95a"],
    ["meat", "肉类", "#d97868"],
    ["cloth", "衣物", "#4fa89a"],
    ["housing", "住房", "#7f9bb5"],
    ["service", "服务", "#c3a6ff"],
  ];
  const seriesData = keys.map(([key, label, color]) => ({
    key, label, color,
    values: series((stat) => {
      const shares = stat.market_budget_shares || stat.budget_shares || {};
      return num(shares[key]) * 100;
    }),
  }));
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const x = (index) => margin.left + (index / Math.max(1, count - 1)) * plotW;
  const y = (value) => margin.top + (1 - value / 100) * plotH;
  let grid = "";
  for (let pct = 0; pct <= 100; pct += 25) {
    grid += `<line class="chart-grid" x1="${margin.left}" y1="${y(pct)}" x2="${width - margin.right}" y2="${y(pct)}"/>`;
    grid += `<text class="chart-axis" x="${margin.left - 6}" y="${y(pct) + 3}" text-anchor="end">${pct}%</text>`;
  }
  const tickCount = 5;
  let xAxis = "";
  for (let i = 0; i < tickCount; i++) {
    const tick = Math.round(1 + (count - 1) * i / (tickCount - 1));
    xAxis += `<text class="chart-axis" x="${x(tick - 1)}" y="${height - 6}" text-anchor="middle">T${tick}</text>`;
  }
  const bottoms = new Array(count).fill(0);
  const bands = [];
  for (const item of seriesData) {
    const top = [];
    for (let i = 0; i < count; i++) {
      bottoms[i] += item.values[i];
      top.push(bottoms[i]);
    }
    bands.push({ item, top, bottom: top.map((value, index) => value - item.values[index]) });
  }
  let paths = "";
  for (const band of bands) {
    const topPoints = [];
    const bottomPoints = [];
    for (let i = 0; i < count; i++) {
      topPoints.push([x(i), y(band.top[i])]);
      bottomPoints.push([x(i), y(band.bottom[i])]);
    }
    const topPath = topPoints.map((point, index) => `${index ? "L" : "M"}${point[0].toFixed(2)} ${point[1].toFixed(2)}`).join(" ");
    const bottomPath = bottomPoints.slice().reverse().map((point) => `L${point[0].toFixed(2)} ${point[1].toFixed(2)}`).join(" ");
    paths += `<path d="${topPath} ${bottomPath} Z" fill="${band.item.color}" opacity=".72"/>`;
    paths += `<path d="${topPath}" fill="none" stroke="${band.item.color}" stroke-width="1.1" opacity=".95"/>`;
  }
  host.innerHTML = chartLegend(seriesData) +
    `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="消费预算份额堆叠图">` +
    `${grid}${xAxis}${paths}` +
    `<line id="share-line" class="chart-marker" x1="0" y1="${margin.top}" x2="0" y2="${height - margin.bottom}" opacity="0"/>` +
    `<rect id="share-rect" x="${margin.left}" y="${margin.top}" width="${plotW}" height="${plotH}" fill="transparent"/>` +
    `</svg>`;
  const svg = host.querySelector("svg");
  const hoverLine = svg.querySelector("#share-line");
  const hoverRect = svg.querySelector("#share-rect");
  hoverRect.addEventListener("mousemove", (event) => {
    const rect = svg.getBoundingClientRect();
    const px = (event.clientX - rect.left) / rect.width * width;
    const ratio = clamp((px - margin.left) / plotW, 0, 1);
    const index = clamp(Math.round(ratio * (count - 1)), 0, count - 1);
    const gx = x(index);
    hoverLine.setAttribute("x1", gx);
    hoverLine.setAttribute("x2", gx);
    hoverLine.setAttribute("opacity", "0.7");
    const stat = state.engine.stats[index];
    const shares = stat.market_budget_shares || stat.budget_shares || {};
    let rows = "";
    for (const item of seriesData) {
      rows += `<div class="tt-row"><span style="color:${item.color}">${item.label}</span><b>${(num(shares[item.key]) * 100).toFixed(1)}%</b></div>`;
    }
    showTooltip(event, `<strong>T${index + 1}</strong>${rows}`);
  });
  hoverRect.addEventListener("mouseleave", () => {
    hideTooltip();
    hoverLine.setAttribute("opacity", "0");
  });
}
function sparkline(values, color, width, height) {
  const w = width || 120;
  const h = height || 26;
  const finite = values.map((value, index) => [index, num(value)]).filter(([, value]) => Number.isFinite(value));
  if (finite.length < 2) return "";
  let min = Math.min(...finite.map(([, value]) => value));
  let max = Math.max(...finite.map(([, value]) => value));
  if (max - min < 1e-9) { max += 1; min -= 1; }
  const x = (index) => 1 + (index / Math.max(1, values.length - 1)) * (w - 2);
  const y = (value) => 1 + (1 - (value - min) / (max - min)) * (h - 2);
  const d = finite.map(([index, value], i) => `${i ? "L" : "M"}${x(index).toFixed(1)} ${y(value).toFixed(1)}`).join(" ");
  return `<svg class="mini-spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true"><path d="${d}" fill="none" stroke="${color}" stroke-width="1.4" stroke-linejoin="round" stroke-linecap="round"/></svg>`;
}

/* ------------------------------------------------------------------ */
/* small render helpers                                                */
/* ------------------------------------------------------------------ */
function factRows(rows) {
  return rows.map(([label, value]) => `<div class="fact-row"><span>${escapeHtml(label)}</span><strong>${value}</strong></div>`).join("");
}
function table(headers, rows, options) {
  const opts = options || {};
  const head = `<thead><tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead>`;
  const bodyRows = rows.map((row) => {
    if (Array.isArray(row)) {
      return `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`;
    }
    return row;
  });
  const body = `<tbody>${bodyRows.join("")}</tbody>`;
  return `<div class="table-wrap"><table${opts.cls ? ` class="${opts.cls}"` : ""}>${head}${body}</table></div>`;
}
function statusBadge(value) {
  if (!Number.isFinite(value)) return '<span class="badge warn">—</span>';
  if (value >= 2) return `<span class="badge ok">${value.toFixed(1)}%</span>`;
  if (value >= 0.5) return `<span class="badge warn">${value.toFixed(1)}%</span>`;
  return `<span class="badge bad">${value.toFixed(1)}%</span>`;
}

/* ------------------------------------------------------------------ */
/* start screen                                                        */
/* ------------------------------------------------------------------ */
function buildStartScreen() {
  const grid = $("regime-grid");
  grid.innerHTML = SCENARIO_ORDER.map((id) => {
    const config = SCENARIOS[id];
    const tags = [];
    tags.push(`<span class="tag">${config.workHours}h 标准工时</span>`);
    if (config.policyRegime === "classical") tags.push('<span class="tag">金本位</span>');
    else if (config.moneyRegime === "credit") tags.push('<span class="tag blue">主权货币</span>');
    else tags.push('<span class="tag">金本位</span>');
    if (config.taxRateWage) tags.push(`<span class="tag">工资税 ${(config.taxRateWage * 100).toFixed(0)}%</span>`);
    if (config.uiReplacement) tags.push(`<span class="tag">失业救济 ${(config.uiReplacement * 100).toFixed(0)}%</span>`);
    if (config.pensionReplacement) tags.push(`<span class="tag">养老金 ${(config.pensionReplacement * 100).toFixed(0)}%</span>`);
    if (config.publicInvestmentRate) tags.push(`<span class="tag">公共投资 ${(config.publicInvestmentRate * 100).toFixed(0)}% GDP</span>`);
    if (config.jobGuarantee) tags.push('<span class="tag green">就业保障</span>');
    if (config.retirementAgeYears) tags.push(`<span class="tag">${config.retirementAgeYears} 岁退休</span>`);
    if (id === "late_capitalism") tags.push('<span class="tag amber">老龄化</span>');
    return `<button type="button" class="regime-card${id === state.regime ? " active" : ""}" data-regime="${id}" role="radio" aria-checked="${id === state.regime}">` +
      `<span class="regime-top"><strong>${escapeHtml(config.label)}</strong><span class="tag ${id === "mmt" ? "blue" : id === "classical" ? "" : "green"}">${escapeHtml(config.policyRegime)}</span></span>` +
      `<small>${escapeHtml(config.name)}</small>` +
      `<span class="regime-tags">${tags.join("")}</span></button>`;
  }).join("");
  grid.addEventListener("click", (event) => {
    const card = event.target.closest("[data-regime]");
    if (!card) return;
    state.regime = card.dataset.regime;
    for (const item of grid.querySelectorAll("[data-regime]")) {
      const active = item === card;
      item.classList.toggle("active", active);
      item.setAttribute("aria-checked", String(active));
    }
    renderDeckNote();
  });
  $("months-seg").addEventListener("click", (event) => {
    const button = event.target.closest("[data-months]");
    if (!button) return;
    state.months = Number(button.dataset.months);
    for (const item of $("months-seg").querySelectorAll("[data-months]")) {
      item.classList.toggle("active", item === button);
    }
  });
  $("seed-input").addEventListener("change", () => {
    const value = clamp(Math.trunc(num($("seed-input").value, 1)), 0, 2147483647);
    state.seed = value;
    $("seed-input").value = value;
  });
  $("price-regime").addEventListener("change", () => { state.priceRegime = $("price-regime").value; });
  const durablesToggle = $("durables-toggle");
  if (durablesToggle) {
    durablesToggle.checked = state.durables;
    durablesToggle.addEventListener("change", () => { state.durables = durablesToggle.checked; });
  }
  $("start-run").addEventListener("click", startRun);
  renderDeckNote();
  try {
    const raw = $("golden-data")?.textContent || "";
    if (raw.trim()) GOLDEN = JSON.parse(raw);
  } catch (error) {
    reportError(`黄金数据解析失败：${error.message}`);
  }
}
let GOLDEN = null;

function regimeConfig() { return SCENARIOS[state.regime] || SCENARIOS.classical; }
function regimeLabel() { return regimeConfig().label || state.regime; }
function renderDeckNote() {
  const config = regimeConfig();
  const node = $("deck-regime");
  if (node) node.textContent = `${config.label} · ${state.priceRegime}`;
  const note = $("deck-note");
  if (note) {
    note.textContent = `${config.workHours}h 标准工时 · ` +
      (config.jobGuarantee ? "就业保障 + " : "") +
      (config.pensionReplacement ? `养老金替代率 ${(config.pensionReplacement * 100).toFixed(0)}%` : "无养老金") +
      ` · ${config.policyRegime} · A2 ${state.durables ? "开启" : "关闭"}`;
  }
}

/* ------------------------------------------------------------------ */
/* run / playback                                                      */
/* ------------------------------------------------------------------ */
function reportError(message) {
  const banner = $("error-banner");
  const text = $("error-text");
  if (banner && text) {
    text.textContent = String(message).slice(0, 700);
    banner.hidden = false;
  }
  try { console.error("[ecosim]", message); } catch (_) {}
}
window.addEventListener("error", (event) => {
  reportError((event.error && event.error.stack) || event.message || "未知脚本错误");
});
window.addEventListener("unhandledrejection", (event) => {
  const reason = event.reason;
  reportError((reason && (reason.stack || reason.message)) || String(reason));
});
document.addEventListener("DOMContentLoaded", () => {
  const close = $("error-close");
  if (close) close.addEventListener("click", () => { $("error-banner").hidden = true; });
  buildStartScreen();
  bindMainControls();
  applyQueryOptions();
});
let pendingView = null;
let pendingFactory = null;
function applyQueryOptions() {
  // Deep-link / headless-screenshot hook. Examples:
  //   ?autostart=keynesian&months=60&seed=1&price=free&view=parity
  //   ?autostart=classical&months=60&factory=steel_mill
  const params = new URLSearchParams(window.location.search);
  const durables = params.get("durables");
  if (durables !== null) {
    state.durables = !["0", "false", "off"].includes(durables.toLowerCase());
    if ($("durables-toggle")) $("durables-toggle").checked = state.durables;
    renderDeckNote();
  }
  const auto = params.get("autostart");
  if (!auto) return;
  const regime = auto === "1" ? "classical" : auto;
  if (SCENARIOS[regime]) state.regime = regime;
  const months = Number(params.get("months"));
  if ([60, 120, 240].includes(months)) state.months = months;
  const seed = Number(params.get("seed"));
  if (Number.isFinite(seed) && seed >= 0) state.seed = Math.trunc(seed);
  const price = params.get("price");
  if (["free", "band", "markup_soft"].includes(price)) state.priceRegime = price;
  pendingView = params.get("view");
  pendingFactory = params.get("factory");
  $("seed-input").value = state.seed;
  $("price-regime").value = state.priceRegime;
  for (const button of $("months-seg").querySelectorAll("[data-months]")) {
    button.classList.toggle("active", Number(button.dataset.months) === state.months);
  }
  for (const card of $("regime-grid").querySelectorAll("[data-regime]")) {
    const active = card.dataset.regime === state.regime;
    card.classList.toggle("active", active);
    card.setAttribute("aria-checked", String(active));
  }
  renderDeckNote();
  startRun();
}

function startRun() {
  if (state.running) return;
  state.seed = clamp(Math.trunc(num($("seed-input").value, 1)), 0, 2147483647);
  state.priceRegime = $("price-regime").value;
  state.durables = $("durables-toggle") ? $("durables-toggle").checked : true;
  state.months = Number($("months-seg").querySelector(".active")?.dataset.months || 240);
  $("seed-input").value = state.seed;
  $("start-screen").classList.add("hidden");
  $("app").classList.remove("hidden");
  $("run-progress").classList.remove("hidden");
  $("month-slider").disabled = true;
  $("prev-month").disabled = true;
  $("next-month").disabled = true;
  $("play-timeline").disabled = true;
  $("progress-label").textContent = "正在创建经济…";
  $("progress-fill").style.width = "0%";
  $("progress-pct").textContent = "0%";
  state.running = true;
  state.playing = false;
  state.startedAt = performance.now();
  const token = ++state.runToken;
  setTimeout(() => {
    try {
      const created = createEngine({
        regime: state.regime, seed: state.seed,
        priceRegime: state.priceRegime, durables: state.durables,
      });
      state.engine = created.engine;
      state.config = created.config;
      state.month = 1;
      const total = state.months;
      let done = 0;
      const chunk = state.months > 120 ? 4 : 6;
      const advance = () => {
        if (token !== state.runToken) return;
        try {
          const end = Math.min(total, done + chunk);
          for (; done < end; done++) state.engine.step();
          const percent = Math.round(done / total * 100);
          $("progress-label").textContent = `正在运行 T${done} / ${total}`;
          $("progress-fill").style.width = `${percent}%`;
          $("progress-pct").textContent = `${percent}%`;
          if (done === 1 || (done % 12 === 0 && done < total)) {
            state.month = done;
            $("month-slider").value = done;
            renderAll();
          }
          if (done < total) {
            setTimeout(advance, 0);
          } else if (token === state.runToken) {
            finishRun();
          }
        } catch (error) {
          reportError(error && error.stack ? error.stack : String(error));
          state.running = false;
        }
      };
      advance();
    } catch (error) {
      reportError(error && error.stack ? error.stack : String(error));
      state.running = false;
    }
  }, 20);
}
function finishRun() {
  state.running = false;
  state.elapsed = (performance.now() - state.startedAt) / 1000;
  state.month = state.months;
  $("run-progress").classList.add("hidden");
  $("month-slider").disabled = false;
  $("prev-month").disabled = false;
  $("next-month").disabled = false;
  $("play-timeline").disabled = false;
  const config = regimeConfig();
  $("run-title").textContent = `${config.label} · 经济驾驶舱`;
  $("run-meta").textContent = `${state.months} 月 · ${state.priceRegime} 价格 · ${state.elapsed.toFixed(2)} 秒`;
  $("run-seed").textContent = `seed ${state.seed}`;
  $("run-status-caption").textContent = `T${state.month} / ${state.months} · 运行完成`;
  $("run-eyebrow").textContent = `ECOSIM / V0.6 / ${state.regime.toUpperCase()}`;
  $("month-total").textContent = `/ ${state.months} 月`;
  const slider = $("month-slider");
  slider.max = state.months;
  slider.value = state.month;
  $("timeline-scale").innerHTML = [1, Math.round(state.months * 0.25), Math.round(state.months * 0.5), Math.round(state.months * 0.75), state.months]
    .filter((value, index, array) => array.indexOf(value) === index)
    .map((value) => `<span>T${value}</span>`).join("");
  renderDeckNote();
  renderAll();
  hideTooltip();
  if (pendingView) {
    const view = pendingView;
    pendingView = null;
    if (document.querySelector(`.tab-btn[data-view="${view}"]`)) switchView(view);
  }
  if (pendingFactory) {
    const industry = pendingFactory;
    pendingFactory = null;
    if (SECTOR_PARAMS.has(industry)) openFactory(industry, null);
  }
}
function bindMainControls() {
  $("month-slider").addEventListener("input", (event) => {
    if (state.running) return;
    stopPlayback();
    state.month = Number(event.target.value);
    renderAll();
  });
  $("prev-month").addEventListener("click", () => {
    if (state.running) return;
    stopPlayback();
    state.month = clamp(state.month - 1, 1, state.months);
    $("month-slider").value = state.month;
    renderAll();
  });
  $("next-month").addEventListener("click", () => {
    if (state.running) return;
    stopPlayback();
    state.month = clamp(state.month + 1, 1, state.months);
    $("month-slider").value = state.month;
    renderAll();
  });
  $("play-timeline").addEventListener("click", () => {
    if (state.running) return;
    if (state.playing) stopPlayback();
    else startPlayback();
  });
  document.querySelectorAll(".tab-btn").forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.view));
  });
  $("scale-sector").addEventListener("change", (event) => {
    state.scaleIndustry = event.target.value;
    renderScalePanel();
  });
  $("new-run").addEventListener("click", resetToStart);
  $("factory-close").addEventListener("click", closeFactory);
  $("factory-overlay").addEventListener("click", (event) => {
    if (event.target === $("factory-overlay")) closeFactory();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && state.factoryIndustry) closeFactory();
  });
  document.addEventListener("click", (event) => {
    const trigger = event.target.closest && event.target.closest("[data-industry]");
    if (trigger) {
      event.preventDefault();
      openFactory(trigger.dataset.industry, trigger);
      return;
    }
    const goodTrigger = event.target.closest && event.target.closest("[data-factory-good]");
    if (goodTrigger) {
      event.preventDefault();
      const industry = GOOD_TO_INDUSTRY[goodTrigger.dataset.factoryGood];
      if (industry) openFactory(industry, goodTrigger);
    }
  });
}
function startPlayback() {
  if (!state.engine) return;
  if (state.month >= state.months) state.month = 1;
  state.playing = true;
  $("play-timeline").classList.add("playing");
  $("play-timeline").textContent = "❚❚ 暂停";
  state.playTimer = setInterval(() => {
    state.month += 1;
    if (state.month >= state.months) {
      state.month = state.months;
      stopPlayback();
    }
    $("month-slider").value = state.month;
    renderAll();
  }, 170);
}
function stopPlayback() {
  if (state.playTimer) clearInterval(state.playTimer);
  state.playTimer = null;
  state.playing = false;
  const button = $("play-timeline");
  if (button) {
    button.classList.remove("playing");
    button.textContent = "▶ 逐月播放";
  }
}
function resetToStart() {
  state.runToken += 1;
  state.running = false;
  stopPlayback();
  state.engine = null;
  state.month = 1;
  state.factoryIndustry = null;
  $("factory-overlay").hidden = true;
  $("app").classList.add("hidden");
  $("start-screen").classList.remove("hidden");
  $("run-progress").classList.add("hidden");
  $("month-slider").disabled = false;
  $("prev-month").disabled = false;
  $("next-month").disabled = false;
  $("play-timeline").disabled = false;
  hideTooltip();
  switchView("overview");
  renderDeckNote();
}
function switchView(view) {
  state.view = view;
  for (const button of document.querySelectorAll(".tab-btn")) {
    button.classList.toggle("active", button.dataset.view === view);
  }
  for (const section of document.querySelectorAll(".view")) {
    section.classList.toggle("hidden", section.id !== `view-${view}`);
  }
  renderAll();
}

/* ------------------------------------------------------------------ */
/* main render                                                         */
/* ------------------------------------------------------------------ */
function renderAll() {
  if (!state.engine) return;
  const stat = currentStat();
  if (!stat) return;
  $("month-value").textContent = `T${state.month}`;
  $("run-status-caption").textContent = `T${state.month} / ${state.months} · ${state.running ? "运行中" : "快照"}`;
  stopPlaybackIfAtEnd();
  renderKpis(stat);
  if (state.view === "overview") renderOverview(stat);
  else if (state.view === "map") renderMap(stat);
  else if (state.view === "markets") renderMarkets(stat);
  else if (state.view === "factories") renderFactories(stat);
  else if (state.view === "mechanism") renderMechanism(stat);
  else if (state.view === "parity") renderParity(stat);
  else if (state.view === "data") renderData(stat);
  if (state.factoryIndustry) renderFactory();
}
function stopPlaybackIfAtEnd() {
  if (state.playing && state.month >= state.months) stopPlayback();
}

function renderKpis(stat) {
  const cards = [
    {
      label: "总人口", icon: "person", color: "var(--series-2)",
      value: fmtInt(stat.population), unit: "人",
      foot: `劳动年龄 ${fmtInt(stat.working_age)} · 儿童 ${fmtInt(stat.children)} · 退休 ${fmtInt(stat.retirees)}`,
      history: series("population"), delta: state.month > 1 ? stat.population - statAt(state.month - 1).population : 0,
    },
    {
      label: "GDP（月）", icon: "machinery", color: "var(--series-1)",
      value: fmtCompact(stat.gdp), unit: "元",
      foot: `消费 ${fmtCompact(stat.consumption)} · 投资 ${fmtCompact(stat.investment)}`,
      history: series("gdp"), delta: state.month > 1 ? stat.gdp - statAt(state.month - 1).gdp : 0,
    },
    {
      label: "失业率", icon: "person", color: "var(--series-3)",
      value: fmtPct(stat.unemployment_rate), unit: "",
      foot: `就业 ${fmtInt(stat.employed)} · 失业 ${fmtInt(stat.unemployed)}`,
      history: series("unemployment_rate", 100), delta: state.month > 1 ? (stat.unemployment_rate - statAt(state.month - 1).unemployment_rate) * 100 : 0,
    },
    {
      label: "资本主义利润率", icon: "steel", color: "var(--series-4)",
      value: fmtPct(stat.profit_rate, 2), unit: "/ 月",
      foot: `年化 ${fmtPct(stat.profit_rate_annualized, 1)} · 12 月均值 ${fmtPct(stat.profit_rate_annual, 1)}`,
      history: series("profit_rate", 100), delta: state.month > 1 ? (stat.profit_rate - statAt(state.month - 1).profit_rate) * 100 : 0,
    },
    {
      label: "CPI（温饱篮子）", icon: "coin", color: "var(--series-3)",
      value: fmtNum(stat.cpi * 100, 1), unit: "初始=100",
      foot: `通胀预期 ${fmtPct(stat.inflation_expectation, 2)}/月`,
      history: series("cpi", 100), delta: state.month > 1 ? (stat.cpi - statAt(state.month - 1).cpi) * 100 : 0,
    },
    {
      label: "平均工资", icon: "coin", color: "var(--series-1)",
      value: fmtNum(stat.average_wage, 2), unit: "元/月",
      foot: `标准 ${stat.standard_work_hours}h · 实际 ${fmtNum(stat.average_hours, 1)}h`,
      history: series("average_wage"), delta: state.month > 1 ? stat.average_wage - statAt(state.month - 1).average_wage : 0,
    },
    {
      label: "货币总量", icon: "bank", color: "var(--series-2)",
      value: fmtCompact(stat.money_total), unit: "元",
      foot: `银行贷款 ${fmtCompact(stat.bank_loans)} · 存款 ${fmtCompact(stat.bank_deposits)}`,
      history: series("money_total"), delta: state.month > 1 ? stat.money_total - statAt(state.month - 1).money_total : 0,
    },
    {
      label: "食品占比", icon: "food", color: "var(--series-3)",
      value: fmtPct(stat.market_food_total_share), unit: "消费预算",
      foot: `服务 ${fmtPct(stat.market_service_spending_share)} · 肉类 ${fmtPct(stat.market_meat_share)}`,
      history: series("market_food_total_share", 100), delta: state.month > 1 ? (stat.market_food_total_share - statAt(state.month - 1).market_food_total_share) * 100 : 0,
    },
    {
      label: "住房存量", icon: "building", color: "var(--series-2)",
      value: fmtNum(stat.housing_stock_per_adult, 1), unit: "㎡/成人",
      foot: `衣物 ${fmtNum(stat.cloth_stock_per_adult, 1)} 件 · 汽车 ${fmtNum(stat.cars_per_100_adults, 1)}/百人 · 维修 ${fmtCompact(stat.maintenance_spending)} 元`,
      history: series("housing_stock_per_adult"), delta: state.month > 1 ? stat.housing_stock_per_adult - statAt(state.month - 1).housing_stock_per_adult : 0,
    },
  ];
  const durableOn = !!state.engine?.features?.durablesA2;
  const visibleCards = durableOn
    ? cards
    : cards.filter((card) => card.label !== "住房存量");
  $("kpi-grid").innerHTML = visibleCards.map((card) => {
    const deltaClass = card.delta > 0 ? "pos" : card.delta < 0 ? "neg" : "muted";
    const deltaText = card.label.includes("失业率") || card.label.includes("食品占比")
      ? `${card.delta >= 0 ? "+" : ""}${card.delta.toFixed(2)} pp`
      : `${card.delta >= 0 ? "+" : ""}${fmtCompact(card.delta)}`;
    return `<article class="kpi-card">` +
      `<div class="kpi-top"><span class="kpi-label">${card.label}</span>${goodIcon(card.icon, "kpi-icon")}</div>` +
      `<div class="kpi-value">${card.value}<small>${card.unit}</small></div>` +
      `<div class="kpi-foot"><span class="kpi-delta ${deltaClass}">${deltaText}</span>${sparkline(card.history.slice(-24), card.color, 64, 20)}</div>` +
      `<div class="kpi-foot" style="margin-top:4px"><span class="faint">${card.foot}</span></div>` +
      `</article>`;
  }).join("");
}

function renderOverview(stat) {
  lineChart($("chart-macro"), [
    { label: "GDP", color: "var(--series-1)", values: series("gdp") },
    { label: "消费", color: "var(--series-2)", values: series("consumption") },
    { label: "投资", color: "var(--series-3)", values: series("investment") },
  ], { height: 220, zeroBase: true, aria: "GDP 消费 投资 趋势" });
  lineChart($("chart-labor"), [
    { label: "失业率 %", color: "var(--series-3)", values: series("unemployment_rate", 100) },
    { label: "利润率 %", color: "var(--series-4)", values: series("profit_rate", 100) },
  ], { height: 220, pct: true, aria: "失业率与利润率" });
  sharesChart($("chart-shares"));
  renderMiniPrices();
  lineChart($("chart-population"), [
    { label: "总人口", color: "var(--series-2)", values: series("population") },
  ], { height: 190, digits: 0, aria: "总人口趋势" });
  $("population-facts").innerHTML = factRows([
    ["出生 / 死亡", `${fmtInt(stat.births)} / ${fmtInt(stat.deaths)} 人/月`],
    ["饥饿死亡", `${fmtInt(stat.hunger_deaths)} 人/月`],
    ["平均 / 中位年龄", `${fmtNum(stat.average_age, 1)} / ${fmtNum(stat.median_age, 1)} 岁`],
    ["抚养比", fmtPct(stat.dependency_ratio, 1)],
    ["生活标准", `生存 ${fmtInt(stat.living_standard.survival)} · 温饱 ${fmtInt(stat.living_standard.subsistence)} · 小康 ${fmtInt(stat.living_standard.comfort)} · 悠闲 ${fmtInt(stat.living_standard.leisure)}`],
    ["儿童 / 退休", `${fmtInt(stat.children)} / ${fmtInt(stat.retirees)}`],
  ]);
  lineChart($("chart-money"), [
    { label: "货币总量", color: "var(--series-1)", values: series("money_total") },
    { label: "银行贷款", color: "var(--series-2)", values: series("bank_loans") },
    { label: "银行存款", color: "var(--series-5)", values: series("bank_deposits") },
    { label: "政府债务", color: "var(--series-3)", values: series("government_debt") },
    { label: "央行货币", color: "var(--series-4)", values: series("central_bank_money") },
  ], { height: 190, zeroBase: true, aria: "货币与政府债务" });
  const gov = stat.policy_regime === "classical";
  $("money-facts").innerHTML = factRows([
    ["政府现金", fmtCompact(stat.government_cash)],
    ["税收 / 转移", `${fmtCompact(stat.government_tax_revenue)} / ${fmtCompact(stat.government_transfers)}`],
    ["财政赤字", fmtCompact(stat.government_deficit)],
    ["就业保障人数", gov ? "—" : fmtInt(stat.government_jg_workers)],
    ["养老金基金", gov ? "—" : fmtCompact(stat.pension_fund)],
    ["银行坏账累计", fmtCompact(stat.bank_write_offs)],
  ]);
}

function renderMiniPrices() {
  const stat = currentStat();
  const goods = ["food", "meat", "coal", "steel", "scrap", "cloth", "building", "service", "fertilizer", "car"];
  $("mini-prices").innerHTML = goods.map((good) => {
    const industry = GOOD_TO_INDUSTRY[good];
    const history = series((item) => item.prices[good]);
    const price = stat.prices[good];
    const production = getGood(stat, "production", good);
    const inventory = getGood(stat, "inventory", good);
    return `<button type="button" class="mini-card" data-factory-good="${good}" aria-label="打开 ${GOOD_LABELS[good]} 工厂面板">` +
      `<div class="mini-top">${goodIcon(good, "mini-icon")}<div class="mini-title"><strong>${GOOD_LABELS[good]}</strong><small>${INDUSTRY_LABELS[industry]}</small></div>` +
      `<div class="mini-price">${fmtNum(price, 2)}<small>元/${GOOD_UNITS[good]}</small></div></div>` +
      `<div class="mini-spark">${sparkline(history.slice(-24), "var(--series-1)", 140, 26)}</div>` +
      `<div class="mini-foot"><span>产 ${fmtNum(production, 2)}</span><span>存 ${fmtNum(inventory, 2)}</span></div></button>`;
  }).join("");
}

function renderMarkets(stat) {
  $("market-grid").innerHTML = GOODS.map((good) => {
    const industry = GOOD_TO_INDUSTRY[good];
    const history = series((item) => item.prices[good]);
    const zeroStreak = num(stat.zero_output_streak[good]);
    const demand = getGood(stat, "demand", good);
    const supply = getGood(stat, "supply", good);
    return `<button type="button" class="mini-card" data-factory-good="${good}" aria-label="打开 ${GOOD_LABELS[good]} 工厂面板">` +
      `<div class="mini-top">${goodIcon(good, "mini-icon")}<div class="mini-title"><strong>${GOOD_LABELS[good]}</strong><small>${INDUSTRY_LABELS[industry]}</small></div>` +
      `<div class="mini-price">${fmtNum(stat.prices[good], 2)}<small>元/${GOOD_UNITS[good]}</small></div></div>` +
      `<div class="mini-spark">${sparkline(history.slice(-30), "var(--series-2)", 140, 26)}</div>` +
      `<div class="mini-foot"><span>需求 ${fmtNum(demand, 1)}</span><span>供给 ${fmtNum(supply, 1)}</span><span>${zeroStreak >= 3 ? `<span class="badge bad">零产出 ${zeroStreak} 月</span>` : `<span class="badge ok">${fmtNum(getGood(stat, "production", good), 1)}</span>`}</span></div></button>`;
  }).join("");
  const headers = ["商品", "价格", "产量", "需求", "供给", "成交", "库存", "下轨", "上轨", "状态"];
  const rows = GOODS.map((good) => {
    const zeroStreak = num(stat.zero_output_streak[good]);
    const floors = stat.price_regime === "free" ? null : stat.price_floors[good];
    const ceilings = stat.price_regime === "free" ? null : stat.price_ceilings[good];
    return `<tr class="clickable-row" data-factory-good="${good}" tabindex="0">` +
      `<td>${iconChip(good, GOOD_LABELS[good])}<span class="cell-sub">${INDUSTRY_LABELS[GOOD_TO_INDUSTRY[good]]}</span></td>` +
      `<td class="mono">${fmtNum(stat.prices[good], 2)}</td>` +
      `<td class="mono">${fmtNum(getGood(stat, "production", good), 2)}</td>` +
      `<td class="mono">${fmtNum(getGood(stat, "demand", good), 2)}</td>` +
      `<td class="mono">${fmtNum(getGood(stat, "supply", good), 2)}</td>` +
      `<td class="mono">${fmtNum(getGood(stat, "volumes", good), 2)}</td>` +
      `<td class="mono">${fmtNum(getGood(stat, "inventory", good), 2)}</td>` +
      `<td class="muted">${floors === null ? "—" : fmtNum(floors, 2)}</td>` +
      `<td class="muted">${ceilings === null ? "—" : fmtNum(ceilings, 2)}</td>` +
      `<td>${zeroStreak >= 3 ? `<span class="badge bad">零产出 ${zeroStreak} 月</span>` : '<span class="badge ok">正常</span>'}</td></tr>`;
  });
  $("goods-table").innerHTML = table(headers, rows) +
    `<p class="table-foot">${stat.price_regime === "free" ? "free 制度不向界面暴露成本地板/天花板；参考价由成本加成、成交锚与短缺/过剩调整。只保留内部绝对安全轨。" : "当前为旧价格制度，显示成本带上下轨。"}</p>`;
}

/* ------------------------------------------------------------------ */
/* hex city map                                                        */
/* ------------------------------------------------------------------ */
const HEX_R = 155;
const HEX_CX = 600;
const HEX_CY = 465;
const HEX_TILES = [
  { id: "city", label: "城市", terrain: "city", cx: HEX_CX, cy: HEX_CY, industries: ["textile_mill", "construction"] },
  { id: "machinery", label: "机械", terrain: "plain", cx: HEX_CX - 0.866 * HEX_R, cy: HEX_CY - 1.5 * HEX_R, industries: ["machinery_factory"] },
  { id: "steel", label: "钢铁", terrain: "plain", cx: HEX_CX + 0.866 * HEX_R, cy: HEX_CY - 1.5 * HEX_R, industries: ["steel_mill"] },
  { id: "agriculture", label: "农业", terrain: "farm", cx: HEX_CX - 1.732 * HEX_R, cy: HEX_CY, industries: ["agriculture"] },
  { id: "mine", label: "矿场", terrain: "mine", cx: HEX_CX + 1.732 * HEX_R, cy: HEX_CY, industries: ["coal_mine", "iron_mine"] },
  { id: "fertilizer", label: "化肥", terrain: "plain", cx: HEX_CX - 0.866 * HEX_R, cy: HEX_CY + 1.5 * HEX_R, industries: ["fertilizer_factory"] },
  { id: "brick", label: "砖厂", terrain: "plain", cx: HEX_CX + 0.866 * HEX_R, cy: HEX_CY + 1.5 * HEX_R, industries: ["brick_factory"] },
];

function hexPoints(cx, cy, r) {
  const points = [];
  for (let i = 0; i < 6; i += 1) {
    const angle = (Math.PI / 3) * i + Math.PI / 6;
    points.push(`${(cx + r * Math.cos(angle)).toFixed(2)},${(cy + r * Math.sin(angle)).toFixed(2)}`);
  }
  return points.join(" ");
}

function mapTree(x, y, scale) {
  const s = scale === undefined ? 1 : scale;
  return `<g transform="translate(${x} ${y}) scale(${s})">` +
    `<rect x="-2" y="0" width="4" height="14" fill="#6b4f32"/>` +
    `<circle cx="0" cy="-5" r="11" fill="#4f8a4b" opacity="0.85"/>` +
    `<circle cx="-7" cy="1" r="8" fill="#5e9c56" opacity="0.8"/>` +
    `<circle cx="7" cy="1" r="8" fill="#477f45" opacity="0.8"/></g>`;
}

function mapTerrain(tile) {
  const { cx, cy } = tile;
  if (tile.terrain === "farm") {
    return `<path d="M ${cx - 128} ${cy + 34} C ${cx - 40} ${cy + 10}, ${cx + 30} ${cy + 58}, ${cx + 120} ${cy + 30}" fill="none" stroke="#5b9bd5" stroke-width="7" opacity="0.55"/>` +
      `<path d="M ${cx - 100} ${cy - 18} L ${cx + 84} ${cy - 40} M ${cx - 96} ${cy - 4} L ${cx + 90} ${cy - 26} M ${cx - 92} ${cy + 10} L ${cx + 96} ${cy - 12}" stroke="#7ba65b" stroke-width="3" opacity="0.7"/>` +
      mapTree(cx - 105, cy + 30, 1.0) + mapTree(cx + 95, cy - 35, 0.9) + mapTree(cx - 70, cy - 48, 0.75);
  }
  if (tile.terrain === "mine") {
    return `<path d="M ${cx - 92} ${cy + 28} L ${cx - 30} ${cy - 62} L ${cx + 28} ${cy + 28} Z" fill="#8e8b84" stroke="#6e6b64" stroke-width="2"/>` +
      `<path d="M ${cx - 10} ${cy + 28} L ${cx + 55} ${cy - 48} L ${cx + 108} ${cy + 28} Z" fill="#a29e95" stroke="#6e6b64" stroke-width="2"/>` +
      `<path d="M ${cx - 30} ${cy - 62} L ${cx - 18} ${cy - 39} L ${cx - 40} ${cy - 36} Z" fill="#e7e3d8" opacity="0.85"/>` +
      `<path d="M ${cx + 55} ${cy - 48} L ${cx + 67} ${cy - 25} L ${cx + 45} ${cy - 22} Z" fill="#e7e3d8" opacity="0.85"/>`;
  }
  if (tile.terrain === "city") {
    return `<g opacity="0.9">` +
      `<rect x="${cx - 104}" y="${cy - 52}" width="42" height="76" rx="3" fill="#b98d5e" stroke="#7e5c39" stroke-width="2"/>` +
      `<rect x="${cx - 50}" y="${cy - 76}" width="50" height="100" rx="3" fill="#c9a271" stroke="#7e5c39" stroke-width="2"/>` +
      `<rect x="${cx + 12}" y="${cy - 40}" width="38" height="64" rx="3" fill="#a77c51" stroke="#7e5c39" stroke-width="2"/>` +
      `<rect x="${cx + 58}" y="${cy - 60}" width="44" height="84" rx="3" fill="#c39a68" stroke="#7e5c39" stroke-width="2"/>` +
      `<path d="M ${cx - 90} ${cy - 32} h 14 M ${cx - 90} ${cy - 18} h 14 M ${cx - 34} ${cy - 55} h 18 M ${cx - 34} ${cy - 39} h 18 M ${cx + 28} ${cy - 22} h 12 M ${cx + 74} ${cy - 40} h 14 M ${cx + 74} ${cy - 24} h 14" stroke="#f5e6bf" stroke-width="3" opacity="0.8"/></g>`;
  }
  return mapTree(cx - 92, cy + 22, 1.0) + mapTree(cx + 88, cy - 30, 0.85) + mapTree(cx - 35, cy - 58, 0.7);
}

function mapFirm(stat, industry, x, y) {
  const params = SECTOR_PARAMS.get(industry);
  if (!params) return "";
  const output = params.output;
  const firms = num((stat.firms || {})[industry]);
  const workers = num((stat.industry_employed || {})[industry]);
  const production = num((stat.production || {})[output]);
  const equipment = num((stat.industry_equipment_units || {})[industry]);
  const projects = num((stat.active_projects || {})[industry]);
  const unit = GOOD_UNITS[output] || "单位";
  // goodIcon 返回的是 <svg viewBox>，嵌进外层 SVG 时必须显式给宽高，
  // 否则浏览器会按默认 300×150 渲染，整个地图会被图标盖住。
  const icon = goodIcon(output, "map-icon").replace(
    "<svg ", '<svg width="32" height="32" '
  );
  return `<g class="map-firm" data-industry="${escapeHtml(industry)}" tabindex="0" role="button" aria-label="打开 ${escapeHtml(INDUSTRY_LABELS[industry])} 工厂面板">` +
    `<rect class="map-firm-bg" x="${x - 108}" y="${y - 31}" width="216" height="62" rx="10"/>` +
    `<g transform="translate(${x - 96} ${y - 20})">${icon}</g>` +
    `<text class="map-firm-title" x="${x - 64}" y="${y - 10}">${escapeHtml(INDUSTRY_LABELS[industry])} ×${fmtInt(firms)}</text>` +
    `<text class="map-firm-sub" x="${x - 64}" y="${y + 8}">${fmtInt(workers)} 人 · ${fmtNum(production, 1)} ${escapeHtml(unit)}/月</text>` +
    `<text class="map-firm-sub" x="${x - 64}" y="${y + 24}">设备 ${fmtInt(equipment)} · 项目 ${fmtInt(projects)}</text></g>`;
}

function renderMap(stat) {
  const host = $("hex-map");
  if (!host) return;
  const tiles = HEX_TILES.map((tile) => {
    const single = tile.industries.length === 1 ? tile.industries[0] : "";
    const tileAttr = single ? ` data-industry="${escapeHtml(single)}" tabindex="0" role="button" aria-label="打开 ${escapeHtml(INDUSTRY_LABELS[single])} 工厂面板"` : "";
    const firms = tile.industries.map((industry, index) => {
      const y = tile.industries.length > 1
        ? tile.cy + (index === 0 ? -38 : 42)
        : tile.cy + 12;
      return mapFirm(stat, industry, tile.cx, y);
    }).join("");
    return `<g class="map-tile"${tileAttr}>` +
      `<polygon class="map-hex" points="${hexPoints(tile.cx, tile.cy, HEX_R)}" fill="${tile.terrain === "mine" ? "#b8b2a6" : tile.terrain === "city" ? "#d8c7a7" : tile.terrain === "farm" ? "#a9c987" : "#b6c9a2"}"/>` +
      `<polygon points="${hexPoints(tile.cx, tile.cy - 2, HEX_R - 8)}" fill="none" stroke="rgba(255,255,255,0.35)" stroke-width="2"/>` +
      mapTerrain(tile) +
      `<text class="map-tile-label" x="${tile.cx}" y="${tile.cy - HEX_R + 26}" text-anchor="middle">${escapeHtml(tile.label)}</text>` +
      firms + `</g>`;
  }).join("");
  host.innerHTML = `<svg class="hex-map-svg" viewBox="0 0 1200 930" role="img" aria-label="六边形城市地图">${tiles}</svg>`;
  const totalFirms = INDUSTRIES.reduce((sum, industry) => sum + num((stat.firms || {})[industry]), 0);
  const totalWorkers = INDUSTRIES.reduce((sum, industry) => sum + num((stat.industry_employed || {})[industry]), 0);
  const food = num((stat.production || {}).food);
  const steel = num((stat.production || {}).steel);
  $("map-facts").innerHTML = factRows([
    ["月份", `T${state.month} / ${state.months}`],
    ["企业 / 就业", `${fmtInt(totalFirms)} 家 / ${fmtInt(totalWorkers)} 人`],
    ["粮食 / 钢铁", `${fmtNum(food, 1)} 吨 / ${fmtNum(steel, 1)} 吨`],
    ["价格制度", stat.price_regime === "free" ? "自由成本加成（无硬边界）" : "旧价格带"],
    ["矿类", "1× 徒手采矿 · 2×+ 矿井设备"],
    ["点击", "工厂图标 → 配方/2^N/生产资料"],
  ]);
  const note = $("map-month-note");
  if (note) note.textContent = `T${state.month} · ${fmtInt(totalFirms)} 家企业`;
}

function renderFactories(stat) {
  $("industry-grid").innerHTML = INDUSTRIES.map((industry) => {
    const params = SECTOR_PARAMS.get(industry);
    const output = params.output;
    const production = getGood(stat, "production", output);
    const capacity = num((stat.industry_capacity || {})[industry]);
    const employed = num((stat.industry_employed || {})[industry]);
    const firms = num((stat.firms || {})[industry]);
    return `<button type="button" class="industry-card" data-industry="${industry}" aria-label="打开 ${INDUSTRY_LABELS[industry]} 工厂面板">` +
      `<div class="ind-top">${goodIcon(output, "mini-icon")}<div><strong>${INDUSTRY_LABELS[industry]}</strong><small>${industry} · ${GOOD_LABELS[output]}</small></div></div>` +
      `<div class="ind-prod"><strong>${fmtNum(production, 2)}</strong><span>${GOOD_UNITS[output]}/月</span></div>` +
      `<div class="ind-meta"><span>${fmtInt(firms)} 家 · ${fmtInt(employed)} 人</span><span>产能 ${fmtNum(capacity, 1)}</span></div>` +
      `<div class="ind-meta"><span>价格 ${fmtNum(stat.prices[output], 1)}</span><span>项目 ${fmtInt((stat.active_projects || {})[industry])}</span></div></button>`;
  }).join("");
  const headers = ["行业", "产出", "企业", "就业", "产量", "产能", "利用率", "设备", "项目"];
  const rows = INDUSTRIES.map((industry) => {
    const params = SECTOR_PARAMS.get(industry);
    const output = params.output;
    const production = getGood(stat, "production", output);
    const capacity = num((stat.industry_capacity || {})[industry]);
    const utilization = capacity > 0 ? production / capacity : 0;
    return `<tr class="clickable-row" data-industry="${industry}" tabindex="0">` +
      `<td>${escapeHtml(INDUSTRY_LABELS[industry])}<span class="cell-sub">${industry}</span></td>` +
      `<td>${iconChip(output, GOOD_LABELS[output])}</td>` +
      `<td>${fmtInt((stat.firms || {})[industry])}</td>` +
      `<td>${fmtInt((stat.industry_employed || {})[industry])}</td>` +
      `<td class="mono">${fmtNum(production, 2)}</td>` +
      `<td class="mono">${fmtNum(capacity, 2)}</td>` +
      `<td>${capacity > 0 ? fmtPct(utilization, 1) : "—"}</td>` +
      `<td>${fmtInt((stat.industry_equipment_units || {})[industry])}</td>` +
      `<td>${fmtInt((stat.active_projects || {})[industry])}</td></tr>`;
  });
  $("industry-table").innerHTML = table(headers, rows) +
    `<p class="table-foot">名义产能按当前企业设备容量与在岗工人平均熟练度汇总；利用率超过 100% 表示实际产量高于熟练度 1 的名义产能。</p>`;
  renderLandPanel(stat);
  renderProjects(stat);
}
function renderLandPanel(stat) {
  const total = num(state.engine.land.totalLand);
  const smallholder = num(stat.smallholder_land);
  const estate = num(stat.estate_land);
  const capitalist = Math.max(0, total - smallholder);
  const activeCapitalist = Math.max(0, capitalist - estate);
  const pct = (value) => total > 0 ? clamp(value / total * 100, 0, 100) : 0;
  $("land-panel").innerHTML =
    `<div class="land-bar"><div class="land-track" role="img" aria-label="土地分配">` +
    `<span class="land-seg land-smallholder" style="width:${pct(smallholder)}%"></span>` +
    `<span class="land-seg land-capitalist" style="width:${pct(activeCapitalist)}%"></span>` +
    `<span class="land-seg land-estate" style="width:${pct(estate)}%"></span></div>` +
    `<div class="land-legend"><span><i class="land-key smallholder"></i>自耕农 ${fmtNum(smallholder, 0)} 亩</span>` +
    `<span><i class="land-key capitalist"></i>资本主义农场 ${fmtNum(activeCapitalist, 0)} 亩</span>` +
    `<span><i class="land-key estate"></i>待售遗产地 ${fmtNum(estate, 0)} 亩</span></div></div>` +
    `<div class="fact-grid">` +
    factRows([
      ["地价", `${fmtNum(stat.land_price, 1)} 元/亩`],
      ["资本主义 / 家庭农场", `${fmtInt(stat.capitalist_farms)} / ${fmtInt(stat.household_farms)}`],
      ["农机 / 总功率", `${fmtInt(stat.farm_machinery)} 台 / ${fmtNum(stat.farm_equipment_power, 0)}`],
      ["兼并农场 / 面积", `${fmtInt(stat.consolidated_farms)} 家 / ${fmtNum(stat.consolidated_land, 0)} 亩`],
      ["平均资本主义农场", `${fmtNum(stat.average_capitalist_farm_mu, 1)} 亩`],
      ["出售闲置小农机", `${fmtNum(stat.idle_equipment_scrapped, 1)} 台/月`],
      ["化肥用量", `${fmtNum(stat.fertilizer_used, 2)} 吨/月`],
      ["农业劳动生产率", `${fmtNum(stat.ag_productivity, 2)} 吨/人/月`],
      ["粮食产出 / 储备", `${fmtNum(stat.food_output, 1)} / ${fmtNum(stat.food_reserve, 1)} 吨`],
      ["粮食自用 / 救济 / 征税", `${fmtNum(stat.household_self_consumption, 2)} / ${fmtNum(stat.food_relief, 2)} / ${fmtNum(stat.food_levy, 2)} 吨`],
    ]) + `</div>` +
    `<p class="mechanism-note">土地市场：资本主义农场竞价买地，自耕农在地价达到保留价后整块出售。A2 下拥有 ≥4× 功率的农场可兼并到 200 亩，并按 2^N 功率减少用工；多余小农机会卖给钢厂作为废钢。自耕农仍可自用粮食，粮食救济会从农场库存与当期产出中征粮。</p>`;
}
function renderProjects(stat) {
  const rows = INDUSTRIES.filter((industry) => num((stat.active_projects || {})[industry]) > 0).map((industry) => {
    const params = SECTOR_PARAMS.get(industry);
    return `<tr><td>${escapeHtml(INDUSTRY_LABELS[industry])}</td><td>${iconChip(params.output, GOOD_LABELS[params.output])}</td><td>${fmtInt(stat.active_projects[industry])}</td></tr>`;
  });
  $("project-panel").innerHTML = rows.length
    ? table(["行业", "产出", "活跃项目"], rows)
    : '<div class="empty-state">当前没有活跃投资项目。投资需要现金、ROI ≥ 1.2%/月，并受 10 个活跃项目上限约束。</div>';
}

function renderMechanism(stat) {
  $("recipe-chain").innerHTML = INDUSTRIES.map((industry) => {
    const params = SECTOR_PARAMS.get(industry);
    const chips = [];
    if (industry === "agriculture") {
      chips.push(iconChip("land", "土地", "recipe-chip"));
      chips.push(iconChip("person", "劳动", "recipe-chip"));
    } else if (!Object.keys(params.inputs).length) {
      chips.push(iconChip("person", "劳动", "recipe-chip"));
    }
    for (const good of Object.keys(params.inputs)) {
      chips.push(iconChip(good, `${GOOD_LABELS[good]} ${params.inputs[good]}${GOOD_UNITS[good]}/单位`, "recipe-chip"));
    }
    if (industry === "agriculture") {
      chips.push(iconChip("fertilizer", "化肥（可选，亩产 ×2）", "recipe-chip"));
    }
    if (industry === "steel_mill" && state.engine?.features.durablesA2) {
      chips.push(iconChip("scrap", "废钢路线 1.5 废钢 + 0.5 煤", "recipe-chip"));
    }
    return `<button type="button" class="recipe-row" data-industry="${industry}">` +
      `<span class="recipe-industry"><strong>${INDUSTRY_LABELS[industry]}</strong><small>${industry}</small></span>` +
      `<span class="recipe-flow">${chips.join('<span class="recipe-plus">+</span>')}<span class="recipe-arrow">→</span>${iconChip(params.output, GOOD_LABELS[params.output], "recipe-chip recipe-output")}</span>` +
      `<span class="recipe-meta">${industry === "service" ? "手工摊 · 无 2^N" : "2^N 设备"}</span></button>`;
  }).join("");
  if (!$("scale-sector").options.length) {
    $("scale-sector").innerHTML = INDUSTRIES.map((industry) =>
      `<option value="${industry}">${INDUSTRY_LABELS[industry]}</option>`).join("");
    $("scale-sector").value = state.scaleIndustry;
  }
  renderScalePanel();
  const cfg = state.engine.demandConfig;
  $("demand-mechanism").innerHTML =
    `<p class="mechanism-note">每个成年人先保留生存篮子的实物底线（粮食 ${cfg.foodSubsistence} 吨、衣物 ${cfg.clothSubsistence} 件、住房 ${cfg.housingSubsistence} ㎡、服务 ${cfg.serviceSubsistence} 单位）；超过生存成本的预算进入温饱以上层，按收入依赖的边际预算份额 β 分配。</p>` +
    `<pre class="formula">q_i = γ_i + β_i(x) · E / p_i
E = max(0, M − Σ_j p_j γ_j)
x = M / Σ_j p_j γ_j        （M = 家庭当月消费预算）</pre>` +
    `<p class="mechanism-note">食品边际份额为 0（Engel 定律：口粮在温饱后饱和）；肉类在低收入锚点为 0、中高收入上升为 10%–14%；服务份额最高（51%–65%）并随收入上升，服务业因此吸收工业裁员。衣物/住房/服务没有硬饱和点，只有极高的安全上限。</p>` +
    `<div class="fact-grid">${factRows([
      ["食品占比（含肉类）", fmtPct(stat.market_food_total_share)],
      ["肉类 / 服务占比", `${fmtPct(stat.market_meat_share)} / ${fmtPct(stat.market_service_spending_share)}`],
      ["成人平均消费预算", `${fmtNum(stat.demand_budget, 1)} 元/月`],
      ["实际工资代理", `${fmtNum(stat.real_wage_proxy, 2)} 个生存篮子/月`],
      ["食品消费价值", `${fmtCompact(stat.household_consumption_value)} 元/月`],
      ["服务就业占比", fmtPct(stat.service_employment_share)],
    ])}</div>`;
  $("wage-mechanism").innerHTML =
    `<p class="mechanism-note">V0.6 工资目标是生产率分享、通胀补偿、劳动市场紧张度与制度性追赶的函数；企业工资报价每月只向目标部分调整（向上粘性、向下更快）。</p>` +
    `<pre class="formula">w* = ${C.WAGE_BASE} × A^β × (1+π^e)^α × (1 + tightness + institutional)
β = 生产率分享   α = 通胀传导   tightness = 0.5·(0.07−u) + 0.5·利润率</pre>` +
    `<div class="fact-grid">${factRows([
      ["生产率指数 A", fmtNum(stat.productivity_index, 3)],
      ["工资指数 / CPI", `${fmtNum(stat.wage_index, 3)} / ${fmtNum(stat.cpi, 3)}`],
      ["实际工资指数", fmtNum(stat.real_wage_index, 3)],
      ["单位劳动成本", fmtNum(stat.unit_labor_cost, 3)],
      ["β / α / 议价力", `${fmtNum(stat.wage_productivity_share, 2)} / ${fmtNum(stat.wage_inflation_pass_through, 2)} / ${fmtNum(stat.wage_bargain_power, 2)}`],
      ["标准工时", `${stat.standard_work_hours}h`],
    ])}</div>` +
    `<p class="mechanism-note">free 价格制度：参考价由“成本加成锚 + 成交价锚 + 惯性”混合，并按短缺/过剩调整。${stat.price_regime === "free" ? "界面不显示成本地板/天花板；只保留内部数值安全轨。" : "当前为旧制度，市场存在成本价格带。"}</p>` +
    `<pre class="formula">p* = (1 + markup) × unit_cost × demand_factor
markup 围绕正常加成率随库存缺口/未成交需求/未售出库存慢速调整</pre>` +
    `<p class="mechanism-note">矿业术语：t0 是<strong>徒手采矿 1×</strong>；t1–t7 才是<strong>矿井设备 2×…128×</strong>，由机械厂生产。农机每级功率翻倍，只扩大可管理土地，不直接提高亩产。</p>`;
  const durableOn = !!state.engine.features.durablesA2;
  const noteNode = $("durable-mechanism-note");
  if (noteNode) noteNode.textContent = durableOn ? "A2 开启" : "A2 关闭";
  $("durable-mechanism").innerHTML = durableOn
    ? `<p class="mechanism-note">衣物是家庭实物存量：每月磨损约存量的 1/60；购买先补磨损，再按收入/质量目标逐步增补，没有“穿够了”的硬饱和。住房存量按月磨损 1/600，维修/重建支出对应建筑品购买；汽车与农机/设备按 120 个月 vintage 批次报废，报废金属进入废钢市场。存量是资产，不是货币；购买是现金转移，磨损与报废是实物消耗/资产退役。</p>` +
      `<pre class="formula">cloth_wear = cloth_stock / 60      housing_wear = housing_stock / 600
cloth_purchase = wear + max(0, target_stock − stock) / 24
housing_purchase = wear + max(0, target_stock − stock) / 60
car_target = f(real income),  car lifetime = 120 months
equipment vintage: 120 months → scrap; replacement investment</pre>` +
      `<div class="fact-grid">${factRows([
        ["衣物存量 / 目标", `${fmtNum(stat.cloth_stock_per_adult, 1)} / ${fmtNum(stat.cloth_target_per_adult, 1)} 件/成人`],
        ["衣物购买 / 磨损", `${fmtNum(stat.cloth_purchases, 0)} / ${fmtNum(stat.cloth_wear, 0)} 件/月`],
        ["衣物质量指数", fmtNum(stat.cloth_quality_index, 2)],
        ["住房存量 / 目标", `${fmtNum(stat.housing_stock_per_adult, 1)} / ${fmtNum(stat.housing_target_per_adult, 1)} ㎡/成人`],
        ["住房购买 / 磨损", `${fmtNum(stat.housing_purchases, 0)} / ${fmtNum(stat.housing_wear, 0)} ㎡/月`],
        ["住房维修 / 新建", `${fmtCompact(stat.maintenance_spending)} / ${fmtNum(stat.housing_new_construction, 1)} ㎡`],
        ["汽车存量 / 目标", `${fmtNum(stat.cars_per_100_adults, 1)} / ${fmtNum(stat.car_target / Math.max(1, stat.population - stat.children) * 100, 1)} 辆/百成人`],
        ["汽车购买 / 报废", `${fmtNum(stat.car_purchases, 2)} / ${fmtNum(stat.car_scrapped, 2)} 辆/月`],
        ["设备平均年龄", `${fmtNum(stat.equipment_average_age_months, 1)} 月`],
        ["设备报废 / 废钢", `${fmtNum(stat.equipment_retired_units, 1)} 台 / ${fmtNum(stat.scrap_generated, 2)} 吨`],
        ["废钢价格 / 库存", `${fmtNum(stat.scrap_price, 2)} 元/吨 · ${fmtNum(stat.scrap_inventory, 1)} 吨`],
        ["钢厂废钢用量 / 占比", `${fmtNum(stat.scrap_used_steel, 2)} 吨 · ${fmtPct(stat.scrap_recipe_share, 1)}`],
        ["兼并农场 / 平均规模", `${fmtInt(stat.consolidated_farms)} 家 · ${fmtNum(stat.average_capitalist_farm_mu, 1)} 亩`],
      ])}</div>` +
      `<p class="mechanism-note">钢厂配方：铁矿路线 <code>1 钢 = 1.5 铁矿 + 1.0 煤</code>；废钢路线 <code>1 钢 = 1.5 废钢 + 0.5 煤</code>。废钢价格锚定铁矿价（约 0.6×），并按短缺/过剩调整。为保持“一企业一产出”的市场结构，汽车由独立的汽车装配行业生产（投入钢铁）；机械厂继续生产农机/设备。这是对“机械厂可产农机或汽车”的已记录偏差。</p>`
    : `<p class="mechanism-note">当前以 V0.6 流量口径运行（衣物/住房按月消费，无设备寿命与废钢）。可在开始界面勾选 A2 后重新运行。</p>`;
  const coverage = [
    ["V0.4 商品 / 行业 / 市场匹配", true],
    ["V0.4 生产 / 设备 / 劳动市场 / 投资", true],
    ["V0.4 会计 / 银行存贷 / 政府税收/UI", true],
    ["V0.4 公共投资 / MMT / 就业保障", true],
    ["V0.4 化肥 / 农业 / 土地市场", true],
    ["V0.6 收入依赖 Stone-Geary 需求", true],
    ["V0.6 肉类 / 畜牧业 / 服务吸收", true],
    ["V0.6 工资—生产率 / 8h–16h / free 价格", true],
    ["V0.5 人口 / 代际 / 养老金", true],
    ["A2 衣物/住房/汽车寿命、废钢、土地兼并", durableOn, "off"],
    ["C 贷款创造存款 / 准备金 / 央行反应函数", false, "deferred"],
  ];
  $("feature-coverage").innerHTML = coverage.map(([label, done, off]) => {
    const status = done
      ? "已移植到 JS 引擎"
      : off === "off" ? "本次运行关闭 · 可在开始界面开启" : "未实现 · 扩展点已预留";
    const dot = done ? "ok" : off === "off" ? "off" : "deferred";
    return `<div class="feature-item"><span class="dot ${dot}"></span><span>${escapeHtml(label)}<br><span class="faint">${status}</span></span></div>`;
  }).join("");
}
function renderScalePanel() {
  const industry = state.scaleIndustry;
  const params = SECTOR_PARAMS.get(industry);
  const et = params.equipment.map((key) => EQUIPMENT.get(key));
  const isFarm = industry === "agriculture";
  const isService = industry === "service";
  const valueKey = isFarm ? "power" : "capacity";
  const maxValue = Math.max(...et.map((item) => item[valueKey]), 1e-9);
  const bars = et.map((item) => {
    const value = item[valueKey];
    const width = value > 0 ? Math.max(2.5, value / maxValue * 100) : 0;
    const valueText = isFarm ? `${fmtNum(value, 0)}× 动力` : `${fmtNum(value, 2)} / 月`;
    return `<div class="scale-row"><span class="scale-level">${escapeHtml(item.label)}</span>` +
      `<span class="scale-track"><span class="scale-fill" style="width:${width}%"></span></span>` +
      `<span class="scale-value">${valueText}</span></div>`;
  }).join("");
  let note;
  if (isService) {
    note = "服务业只有手工服务摊 t0（1×），没有 2^N 资本升级；失业者在服务需求未满足时自雇进入，连续无销售会退出。";
  } else if (isFarm) {
    note = "农机功率每级翻倍：每个劳动力可管理 10×(1+功率) 亩。它控制土地规模，不改变亩产；亩产由熟练度和化肥决定。";
  } else if (industry === "coal_mine" || industry === "iron_mine") {
    note = "矿类没有独立矿井资产：t0 是徒手采矿 1×；t1–t7 是矿井设备 2×…128×，由机械厂生产。";
  } else if (industry === "auto_factory") {
    note = "A2 汽车装配线：投入钢铁、产出汽车。汽车是家庭耐用品，寿命 120 个月，报废后进入废钢市场；独立汽车厂是对“机械厂可切换产农机/汽车”的已记录偏差。";
  } else {
    note = `t0→t7：产能 ${fmtNum(et[0].capacity, 2)}→${fmtNum(et[et.length - 1].capacity, 2)}，满产用工 ${fmtInt(et[0].workers)}→${fmtInt(et[et.length - 1].workers)}；每级资本品数量翻倍。`;
  }
  const last = et[et.length - 1];
  $("scale-panel").innerHTML = `<div class="scale-bars">${bars}</div>` +
    `<p class="mechanism-note">${note}</p>` +
    `<div class="fact-grid">${factRows([
      ["设备等级", `${et.length} 级`],
      ["最高等级", last.label],
      ["最大企业数", fmtInt(params.maxFirms)],
      ["资源型行业", params.isResource ? "是" : "否"],
      ["t0 资本品", et[0].capitalGood === null ? "无（手工/徒手）" : `${GOOD_LABELS[et[0].capitalGood]} × ${et[0].capitalCost}`],
      ["最高级资本品", last.capitalGood === null ? "无" : `${GOOD_LABELS[last.capitalGood]} × ${last.capitalCost}`],
    ])}</div>`;
}

function renderParity(stat) {
  const banner = $("parity-banner");
  const tableHost = $("parity-table");
  const method = $("parity-method");
  if (!GOLDEN) {
    banner.innerHTML = "<span>未找到内嵌的黄金数据。</span>";
    tableHost.innerHTML = '<div class="empty-state">黄金数据缺失；请重新构建发行版。</div>';
  } else if (state.durables) {
    banner.innerHTML = `<span><strong>A2 耐用品已开启。</strong> 内嵌黄金运行是 A2 之前的 V0.6 Python oracle；两者不应逐位对比。关闭 A2 后可重放 oracle。</span>`;
    tableHost.innerHTML = '<div class="empty-state">在开始界面关闭“A2 耐用品与废钢”，选择 60 或 240 月后重新运行，即可查看迁移 oracle 对比。</div>';
  } else if (state.seed !== 1 || state.priceRegime !== "free") {
    banner.innerHTML = `<span><strong>当前配置没有黄金运行。</strong> 内嵌对比只覆盖 seed=1、free 价格制度、geary 需求；可在开始界面重新运行。</span>`;
    tableHost.innerHTML = '<div class="empty-state">当前 seed 或价格制度不在黄金矩阵内。</div>';
  } else {
    const run = GOLDEN.runs.find((item) => item.regime === state.regime &&
      item.months === state.months && item.seed === 1 && item.price_regime === "free");
    if (!run) {
      banner.innerHTML = `<span><strong>${escapeHtml(regimeLabel())} · ${state.months} 月</strong> 没有内嵌黄金运行（仅 60 / 240 月）。</span>`;
      tableHost.innerHTML = '<div class="empty-state">可在开始界面选择 60 或 240 月后重新运行。</div>';
    } else {
      const ticks = Object.keys(run.samples).map(Number).sort((a, b) => a - b);
      const tick = ticks.includes(state.month) ? state.month : ticks.filter((value) => value <= state.month).pop();
      if (!tick) {
        banner.innerHTML = `<span>当前月份 T${state.month} 早于第一个黄金采样点。</span>`;
        tableHost.innerHTML = '<div class="empty-state">黄金采样从 T1 开始。</div>';
      } else {
        const py = run.samples[String(tick)];
        const js = statAt(tick);
        const fields = [
          ["population", "总人口", 0, "int"],
          ["gdp", "GDP（月）", 0, "money"],
          ["investment", "投资（月）", 0, "money"],
          ["unemployment_rate", "失业率", 2, "pp"],
          ["profit_rate", "利润率", 2, "pp"],
          ["cpi", "CPI", 3, "num"],
          ["average_wage", "平均工资", 2, "num"],
          ["money_total", "货币总量", 0, "money"],
          ["food_share", "食品占比", 2, "pct"],
          ["market_food_total_share", "食品+肉类占比", 2, "pct"],
          ["service_spending_share", "服务占比", 2, "pct"],
          ["bank_loans", "银行贷款", 0, "money"],
          ["government_debt", "政府债务", 0, "money"],
          ["land_price", "地价", 1, "num"],
        ];
        const priceFields = ["food", "meat", "coal", "iron_ore", "steel", "cloth"];
        const rows = [];
        for (const [key, label, digits, kind] of fields) {
          const jsValue = num(js[key]);
          const pyValue = num(py[key]);
          const dev = kind === "pp"
            ? (jsValue - pyValue) * 100
            : (Math.abs(pyValue) > 1e-9 ? (jsValue - pyValue) / Math.abs(pyValue) * 100 : (Math.abs(jsValue - pyValue) < 1e-6 ? 0 : Infinity));
          rows.push(compareRow(label, jsValue, pyValue, dev, kind, digits));
        }
        for (const good of priceFields) {
          const jsValue = num(js.prices[good]);
          const pyValue = num(py.prices[good]);
          const dev = Math.abs(pyValue) > 1e-9 ? (jsValue - pyValue) / Math.abs(pyValue) * 100 : Infinity;
          rows.push(compareRow(`价格 · ${GOOD_LABELS[good]}`, jsValue, pyValue, dev, "num", 2));
        }
        const gdpJs = num(js.gdp);
        const gdpPy = num(py.gdp);
        const finalDev = Math.abs(gdpPy) > 1e-9 ? (gdpJs - gdpPy) / Math.abs(gdpPy) * 100 : 0;
        banner.innerHTML = `<span><strong>T${tick} · ${escapeHtml(regimeLabel())} · seed 1 · ${run.months} 月</strong> · JavaScript 运行 vs Python 迁移 oracle</span>` +
          `<span>GDP 偏差 <b class="dev ${devClass(finalDev)}">${fmtSigned(finalDev, 1)}%</b> · 合理区间 ±15%</span>`;
        tableHost.innerHTML = table(["指标", "JavaScript", "Python oracle", "偏差", "判定"], rows) +
          `<p class="table-foot">偏差 = (JS − Python) / |Python|。货币总量在非信用制度下应精确守恒；投资/利润率为月度流量，受项目启动时点影响较大，不作为逐位一致指标。</p>`;
      }
    }
  }
  method.innerHTML =
    `<p class="mechanism-note"><strong>黄金运行口径：</strong>Python 参考引擎以 seed=1、price_regime=free、demand_regime=geary 运行 60/240 月，采集 T1/6/12/24/36/48/60/120/180/240 的关键指标。JS 发行版在同一配置下重放，比较人口、GDP、投资、失业、利润率、CPI、工资、货币、消费份额、价格、银行/政府/土地指标。</p>` +
    `<p class="mechanism-note"><strong>已知偏差：</strong>① 投资是块状决策，项目启动/完成月份在 JS 与 Python 间会移动，导致单月投资与利润率大幅波动；② 240 月 Keynesian/MMT 的煤/钢价格可偏离 20%–40%，但粮食/服务/工资/CPI 等核心指标仍在个位数百分比内；③ 人口过程使用与 CPython 兼容的 MT19937 与相同调用顺序，人口总量接近，但细微经济差异会通过生活标准/生育率反馈；④ 该黄金矩阵早于 A2：只有关闭“A2 耐用品与废钢”时才是同口径对比；A2 开启后的衣物/住房/汽车存量、废钢与土地兼并指标不与 Python oracle 对齐。C 信贷反应函数仍未实现。</p>` +
    `<p class="mechanism-note">复现脚本：<code>scripts/export_golden_v06.py</code> 与 <code>scripts/compare_golden_v06.mjs</code>。</p>`;
}
function compareRow(label, jsValue, pyValue, dev, kind, digits) {
  const format = (value) => {
    if (kind === "pct" || kind === "pp") return fmtPct(value, digits);
    if (kind === "money") return fmtCompact(value);
    if (kind === "int") return fmtInt(value);
    return fmtNum(value, digits);
  };
  const cls = kind === "pp" ? ppClass(dev) : devClass(dev);
  const text = Number.isFinite(dev) ? `${dev >= 0 ? "+" : ""}${dev.toFixed(1)}${kind === "pp" ? " pp" : "%"}` : "—";
  return `<tr><td>${escapeHtml(label)}</td><td class="mono">${format(jsValue)}</td><td class="mono muted">${format(pyValue)}</td>` +
    `<td><span class="dev ${cls}">${text}</span></td><td>${cls === "ok" ? '<span class="badge ok">合理</span>' : cls === "watch" ? '<span class="badge warn">观察</span>' : '<span class="badge bad">偏离</span>'}</td></tr>`;
}
function devClass(dev) {
  if (!Number.isFinite(dev)) return "bad";
  const abs = Math.abs(dev);
  if (abs <= 5) return "ok";
  if (abs <= 15) return "watch";
  return "bad";
}
function ppClass(dev) {
  if (!Number.isFinite(dev)) return "bad";
  const abs = Math.abs(dev);
  if (abs <= 1) return "ok";
  if (abs <= 3) return "watch";
  return "bad";
}

function renderData(stat) {
  const durableOn = !!state.engine?.features?.durablesA2;
  const warnings = stat.warnings || [];
  $("warning-panel").innerHTML = warnings.length
    ? `<ul class="warning-list">${warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul>`
    : '<div class="empty-state">当前月没有引擎警告。货币守恒、无连续零产出、无救济/养老金缺口。</div>';
  const profitTable = table(["利润表项目", "金额（元）", "占收入"], [
    ["营业收入", fmtNum(stat.revenue, 0), "100%"],
    ["中间投入", fmtSigned(-stat.input_costs, 0), revenueShare(-stat.input_costs, stat.revenue)],
    ["工资", fmtSigned(-stat.wages, 0), revenueShare(-stat.wages, stat.revenue)],
    ["利息", fmtSigned(-stat.interest, 0), revenueShare(-stat.interest, stat.revenue)],
    ["折旧", fmtSigned(-stat.depreciation, 0), revenueShare(-stat.depreciation, stat.revenue)],
    ["经济利润", fmtSigned(stat.profit, 0), revenueShare(stat.profit, stat.revenue)],
  ]);
  const bankTable = table(["科目", "金额（元）"], [
    ["银行现金", fmtNum(stat.bank_cash, 0)],
    ["银行贷款", fmtNum(stat.bank_loans, 0)],
    ["银行存款", fmtNum(stat.bank_deposits, 0)],
    ["坏账核销累计", fmtNum(stat.bank_write_offs, 0)],
    ["货币总量", fmtNum(stat.money_total, 0)],
    ["期初货币", fmtNum(state.engine.moneyInitial, 0)],
    ["货币漂移", fmtSigned(stat.money_total - state.engine.moneyInitial, 2)],
  ]);
  const govTable = table(["科目", "金额（元）"], [
    ["政府现金", fmtNum(stat.government_cash, 0)],
    ["税收收入", fmtNum(stat.government_tax_revenue, 0)],
    ["转移支付", fmtNum(stat.government_transfers, 0)],
    ["政府支出", fmtNum(stat.government_spending, 0)],
    ["财政赤字", fmtNum(stat.government_deficit, 0)],
    ["政府债务", fmtNum(stat.government_debt, 0)],
    ["央行货币", fmtNum(stat.central_bank_money, 0)],
    ["就业保障人数", fmtInt(stat.government_jg_workers)],
    ["养老金基金 / 发放", `${fmtNum(stat.pension_fund, 0)} / ${fmtNum(stat.pension_spending, 0)}`],
  ]);
  $("account-panel").innerHTML = `<h3 style="margin:0 0 6px;font-size:12px;color:var(--muted)">利润表</h3>${profitTable}` +
    `<h3 style="margin:14px 0 6px;font-size:12px;color:var(--muted)">银行</h3>${bankTable}` +
    `<h3 style="margin:14px 0 6px;font-size:12px;color:var(--muted)">政府</h3>${govTable}`;
  const ageRows = Object.entries(stat.age_histogram).map(([bucket, count]) =>
    `<tr><td>${escapeHtml(bucket)} 岁</td><td>${fmtInt(count)}</td><td><span style="display:inline-block;height:6px;border-radius:999px;background:var(--green);width:${Math.min(100, count / Math.max(1, stat.population) * 300)}px"></span></td></tr>`);
  const livingRows = Object.entries(stat.living_standard).map(([key, count]) => {
    const labels = { survival: "生存", subsistence: "温饱", comfort: "小康", leisure: "悠闲", child: "儿童" };
    return `<tr><td>${labels[key] || key}</td><td>${fmtInt(count)}</td><td>${fmtPct(count / Math.max(1, stat.population), 1)}</td></tr>`;
  });
  $("population-table").innerHTML = table(["年龄桶", "人数", "分布"], ageRows) +
    `<h3 style="margin:14px 0 6px;font-size:12px;color:var(--muted)">生活标准</h3>` + table(["类别", "人数", "占比"], livingRows);
  const targets = stat.demand_targets || {};
  const shares = stat.market_budget_shares || {};
  const demandRows = [
    ["粮食", fmtNum(targets.food, 3) + " 吨", fmtPct(shares.food, 1)],
    ["肉类", fmtNum(targets.meat, 4) + " 吨", fmtPct(shares.meat, 1)],
    ["衣物", fmtNum(targets.cloth, 2) + " 件", fmtPct(shares.cloth, 1)],
    ["住房", fmtNum(targets.building, 3) + " ㎡", fmtPct(shares.housing, 1)],
    ["服务", fmtNum(targets.service, 2) + " 单位", fmtPct(shares.service, 1)],
  ].map(([label, target, share]) => `<tr><td>${label}</td><td>${target}</td><td>${share}</td></tr>`);
  $("demand-table").innerHTML = table(["商品", "成人平均目标", "预算份额"], demandRows) +
    `<div class="fact-grid">${factRows([
      ["成人平均消费预算", `${fmtNum(stat.demand_budget, 1)} 元/月`],
      ["实际工资代理", `${fmtNum(stat.real_wage_proxy, 2)} 个生存篮子/月`],
      ["CPI", fmtNum(stat.cpi, 3)],
      ["食品 / 肉类 / 服务", `${fmtPct(stat.market_food_total_share)} / ${fmtPct(stat.market_meat_share)} / ${fmtPct(stat.market_service_spending_share)}`],
      ["服务就业占比", fmtPct(stat.service_employment_share)],
      ["肉类就业占比", fmtPct(stat.livestock_employment_share)],
    ])}</div>`;
  if (durableOn) {
    const durableRows = [
      ["衣物", `${fmtNum(stat.cloth_stock_per_adult, 1)} 件/成人`, `${fmtNum(stat.cloth_target_per_adult, 1)} 件/成人`, fmtNum(stat.cloth_purchases, 0), fmtNum(stat.cloth_wear, 0), `质量 ${fmtNum(stat.cloth_quality_index, 2)} · 寿命 60 月`],
      ["住房", `${fmtNum(stat.housing_stock_per_adult, 1)} ㎡/成人`, `${fmtNum(stat.housing_target_per_adult, 1)} ㎡/成人`, fmtNum(stat.housing_purchases, 0), fmtNum(stat.housing_wear, 0), `维修 ${fmtCompact(stat.maintenance_spending)} 元 · 新建 ${fmtNum(stat.housing_new_construction, 1)} ㎡ · 寿命 600 月`],
      ["汽车", `${fmtNum(stat.cars_per_100_adults, 1)} 辆/百成人`, `${fmtNum(stat.car_target / Math.max(1, stat.population - stat.children) * 100, 1)} 辆/百成人`, fmtNum(stat.car_purchases, 2), fmtNum(stat.car_scrapped, 2), `价格 ${fmtNum(stat.prices.car, 1)} 元 · 寿命 120 月`],
    ];
    $("durable-data").innerHTML = table(["类别", "存量", "目标", "购买/月", "磨损或报废/月", "说明"], durableRows) +
      table(["设备", "存量", "平均年龄", "替换需求/月", "报废/月", "说明"], [[
        "农机/矿井设备",
        `${fmtNum(stat.equipment_vintage_units, 0)} 台`,
        `${fmtNum(stat.equipment_average_age_months, 1)} 月`,
        `${fmtNum(stat.replacement_demand_units, 0)} 台`,
        `${fmtNum(stat.equipment_retired_units, 1)} 台`,
        `废钢 ${fmtNum(stat.scrap_generated_equipment, 2)} 吨（汽车另 ${fmtNum(stat.scrap_generated_car, 2)} 吨）`,
      ]]) +
      `<div class="fact-grid">${factRows([
        ["耐用品支出", `${fmtCompact(stat.durable_spending)} 元/月`],
        ["耐用品资产价值", `${fmtCompact(stat.durable_asset_value)} 元`],
        ["维修支出", `${fmtCompact(stat.maintenance_spending)} 元/月`],
        ["房屋新建", `${fmtNum(stat.housing_new_construction, 1)} ㎡/月`],
        ["设备替换需求", `${fmtNum(stat.replacement_demand_units, 0)} 台`],
        ["替换项目", fmtInt(stat.replacement_projects)],
      ])}</div>` +
      `<p class="table-foot">存量不进入货币总量；购买是家庭与企业的现金转移。衣物/住房预算份额按当月购买计算，磨损按存量/寿命计算，两者不重复计入消费。</p>`;
    const bins = stat.equipment_vintage_bins || {};
    $("scrap-data").innerHTML = table(["指标", "数值", "说明"], [
      ["废钢价格", `${fmtNum(stat.scrap_price, 2)} 元/吨`, "锚定铁矿价 × 0.6，按短缺/过剩调整"],
      ["废钢库存", `${fmtNum(stat.scrap_inventory, 1)} 吨`, "企业 + 家庭 + 资产池"],
      ["钢厂废钢用量", `${fmtNum(stat.scrap_used_steel, 2)} 吨/月`, "替代铁矿路线"],
      ["废钢钢 / 铁矿钢", `${fmtNum(stat.steel_scrap_output, 1)} / ${fmtNum(stat.steel_ore_output, 1)} 吨`, `废钢路线占比 ${fmtPct(stat.scrap_recipe_share, 1)}`],
      ["设备平均年龄", `${fmtNum(stat.equipment_average_age_months, 1)} 月`, `0–23: ${fmtNum(bins["0-23"], 0)} · 24–59: ${fmtNum(bins["24-59"], 0)} · 60–89: ${fmtNum(bins["60-89"], 0)} · 90–119: ${fmtNum(bins["90-119"], 0)}`],
      ["设备报废 / 废钢", `${fmtNum(stat.equipment_retired_units, 1)} 台 / ${fmtNum(stat.scrap_generated_equipment, 2)} 吨`, "120 月寿命；小农机出售也计入"],
      ["汽车报废 / 废钢", `${fmtNum(stat.car_scrapped, 2)} 辆 / ${fmtNum(stat.scrap_generated_car, 2)} 吨`, "每辆约 1.2 吨废钢"],
      ["兼并农场 / 面积", `${fmtInt(stat.consolidated_farms)} 家 / ${fmtNum(stat.consolidated_land, 0)} 亩`, `平均 ${fmtNum(stat.average_capitalist_farm_mu, 1)} 亩`],
      ["农机总功率", fmtNum(stat.farm_equipment_power, 0), `农业就业 ${fmtInt(stat.industry_employed.agriculture)} 人`],
      ["闲置小农机出售", `${fmtNum(stat.idle_equipment_scrapped, 1)} 台/月`, "卖给钢厂作为废钢，不重复计土地/设备"],
    ]) +
      `<p class="table-foot">废钢是实物商品，不是货币；设备/汽车退役只把金属转入废钢一次。钢厂废钢路线每吨钢耗 1.5 吨废钢 + 0.5 吨煤；铁矿路线耗 1.5 吨铁矿 + 1.0 吨煤。</p>`;
  } else {
    $("durable-data").innerHTML =
      '<p class="table-foot">A2 关闭：本次运行使用 V0.6 月度流量口径，无耐用品存量、设备寿命或废钢。</p>';
    $("scrap-data").innerHTML =
      '<p class="table-foot">A2 关闭：无设备 vintage 与废钢市场。</p>';
  }
}
function revenueShare(value, revenue) {
  if (Math.abs(revenue) < 1e-9) return "—";
  return fmtPct(value / revenue, 1);
}

/* ------------------------------------------------------------------ */
/* factory modal                                                       */
/* ------------------------------------------------------------------ */
function openFactory(industry, trigger) {
  state.factoryIndustry = industry;
  state.factoryTrigger = trigger || document.activeElement;
  $("factory-overlay").hidden = false;
  renderFactory();
  setTimeout(() => { $("factory-close").focus(); }, 0);
}
function closeFactory() {
  state.factoryIndustry = null;
  $("factory-overlay").hidden = true;
  const trigger = state.factoryTrigger;
  state.factoryTrigger = null;
  if (trigger && trigger.focus) {
    try { trigger.focus({ preventScroll: true }); } catch (_) { trigger.focus(); }
  }
}
function renderFactory() {
  const industry = state.factoryIndustry;
  if (!industry || !state.engine) return;
  const stat = currentStat();
  const params = SECTOR_PARAMS.get(industry);
  const output = params.output;
  const production = getGood(stat, "production", output);
  const capacity = num((stat.industry_capacity || {})[industry]);
  const employed = num((stat.industry_employed || {})[industry]);
  const firms = num((stat.firms || {})[industry]);
  const projects = num((stat.active_projects || {})[industry]);
  const equipmentUnits = num((stat.industry_equipment_units || {})[industry]);
  const utilization = capacity > 0 ? production / capacity : 0;
  $("factory-icon").innerHTML = goodIcon(output, "xl");
  $("factory-title").textContent = INDUSTRY_LABELS[industry];
  $("factory-sub").innerHTML = `产出 ${iconChip(output, GOOD_LABELS[output], "")} · <span class="mono">${industry}</span> · ` +
    `${params.isResource ? "资源型行业" : industry === "service" ? "非正规/自雇部门" : "制造业"} · T${state.month}`;
  const chips = [];
  if (industry === "agriculture") {
    chips.push(iconChip("land", "土地", "factory-chip"));
    chips.push(iconChip("person", "劳动", "factory-chip"));
  } else if (!Object.keys(params.inputs).length) {
    chips.push(iconChip("person", "劳动", "factory-chip"));
  }
  for (const good of Object.keys(params.inputs)) {
    chips.push(iconChip(good, `${GOOD_LABELS[good]} ${params.inputs[good]} ${GOOD_UNITS[good]}/单位`, "factory-chip"));
  }
  if (industry === "agriculture") chips.push(iconChip("fertilizer", "化肥（可选，亩产 ×2）", "factory-chip"));
  if (industry === "steel_mill" && state.engine?.features.durablesA2) {
    chips.push(iconChip("scrap", "废钢路线 1.5 废钢 + 0.5 煤", "factory-chip"));
  }
  const recipe = `<div class="factory-recipe">${chips.join('<span class="recipe-plus">+</span>')}<span class="recipe-arrow">→</span>${iconChip(output, GOOD_LABELS[output], "factory-chip factory-output")}</div>`;
  const tiers = params.equipment.map((key) => EQUIPMENT.get(key));
  const isFarm = industry === "agriculture";
  const tierRows = tiers.map((item) => {
    const capital = item.capitalGood === null ? "手工 / 无" : `${GOOD_LABELS[item.capitalGood]} × ${item.capitalCost}`;
    if (isFarm) {
      return `<tr><td>${escapeHtml(item.label)}</td><td>${fmtNum(item.power, 0)}×</td><td>${capital}</td><td>${fmtInt(item.buildMonths)} 月</td></tr>`;
    }
    return `<tr><td>${escapeHtml(item.label)}</td><td>${fmtNum(item.capacity, 2)}</td><td>${fmtInt(item.workers)}</td><td>${capital}</td><td>${fmtInt(item.buildMonths)} 月</td></tr>`;
  });
  const tierTable = isFarm
    ? table(["等级", "功率", "资本品 / 数量", "建造"], tierRows)
    : table(["等级", "产能/月", "用工", "资本品 / 数量", "建造"], tierRows);
  let mechanism;
  if (industry === "agriculture") {
    mechanism = "农机的 2^N 功率（1×、2×…128×）让每个劳动力管理更多土地，但不改变亩产。产出 = 土地 × 亩产 × 熟练度 × 化肥倍率；化肥按土地面积投入（每亩 0.01 吨，亩产 ×2）。";
  } else if (industry === "coal_mine" || industry === "iron_mine") {
    mechanism = "矿类没有独立的“矿井”生产资料：t0 是<b>徒手采矿 1×</b>；t1–t7 才是<b>矿井设备 2×…128×</b>，由机械厂生产。每级产能翻倍、满产用工 +1。";
  } else if (industry === "service") {
    mechanism = "服务业只有手工服务摊 t0（1×），没有 2^N 资本升级。失业者在服务需求未满足时自雇进入；连续 6 个月无销售会退出并回到失业池。A2 下若失业率较高且服务收入仍可行，会逐步增加低薪自雇缓冲。";
  } else if (industry === "auto_factory") {
    mechanism = "汽车装配线投入钢铁、产出汽车；汽车是家庭耐用品，寿命 120 个月，报废后成为废钢。为保持一企业一产出，汽车由独立汽车厂生产，而不是机械厂同厂切换（已记录偏差）。";
  } else if (industry === "steel_mill") {
    mechanism = state.engine?.features?.durablesA2
      ? "炼钢厂有两条实物配方：铁矿路线 1 钢 = 1.5 铁矿 + 1.0 煤；废钢路线 1 钢 = 1.5 废钢 + 0.5 煤。钢厂按可得库存与相对成本选择路线，废钢来自报废设备与汽车。"
      : "炼钢厂当前只走铁矿路线：1 钢 = 1.5 铁矿 + 1.0 煤。废钢路线与报废设备/汽车仅在 A2 开启时可用。";
  } else if (industry === "machinery_factory") {
    mechanism = "机械厂生产农机/矿井设备/纺织机/反应炉等资本品，投入钢铁。A2 的汽车由独立汽车装配行业生产；这是对“机械厂可产农机或汽车”的简化偏差。";
  } else if (industry === "livestock") {
    mechanism = "畜牧业把饲料粮转化为肉类：每吨肉消耗 3 吨粮。畜舍 t0 起需要机械，产能 2 吨/月、5 名工人；规模每级翻倍、用工 +1。肉类是收入上升后的食品质量阶梯。";
  } else if (industry === "fertilizer_factory") {
    mechanism = "化肥厂只有煤一种投入，必须用现金现货采购；煤库存缓冲 2 个月。反应炉单厂最多 2 台；短缺时化肥厂在招聘队列中优先补位。";
  } else {
    mechanism = "设备等级 t0–t7 对应 1×、2×…128×：产能翻倍、满产用工 +1、资本品数量翻倍（t0 可为手工设备）。企业优先选择可负担的最小规模，再按需求和 ROI 升级。";
  }
  const capitalSource = (() => {
    const sources = [...new Set(tiers.filter((item) => item.capitalGood).map((item) => item.capitalGood))];
    if (!sources.length) return "该行业不需要资本品：设备为手工/自雇形态。";
    return `资本品来源：${sources.map((good) => `${GOOD_LABELS[good]}（${INDUSTRY_LABELS[GOOD_TO_INDUSTRY[good]]}）`).join("、")}。设备由本行业企业发起投资项目，支付资本品并经过建造期后形成。`;
  })();
  $("factory-body").innerHTML =
    `<div class="factory-stats">` +
    `<div class="factory-stat"><span>当月产量</span><strong>${fmtNum(production, 2)}<small>${GOOD_UNITS[output]}</small></strong></div>` +
    `<div class="factory-stat"><span>名义产能</span><strong>${fmtNum(capacity, 2)}<small>${GOOD_UNITS[output]}</small></strong></div>` +
    `<div class="factory-stat"><span>利用率</span><strong>${capacity > 0 ? fmtPct(utilization, 1) : "—"}</strong></div>` +
    `<div class="factory-stat"><span>企业 / 就业</span><strong>${fmtInt(firms)}<small>家</small> / ${fmtInt(employed)}<small>人</small></strong></div>` +
    `<div class="factory-stat"><span>设备 / 项目</span><strong>${fmtInt(equipmentUnits)}<small>台</small> / ${fmtInt(projects)}<small>个</small></strong></div>` +
    `<div class="factory-stat"><span>价格</span><strong>${fmtNum(stat.prices[output], 2)}<small>元</small></strong></div>` +
    `<div class="factory-stat"><span>库存</span><strong>${fmtNum(getGood(stat, "inventory", output), 2)}<small>${GOOD_UNITS[output]}</small></strong></div>` +
    `<div class="factory-stat"><span>需求 / 供给</span><strong>${fmtNum(getGood(stat, "demand", output), 1)} / ${fmtNum(getGood(stat, "supply", output), 1)}</strong></div>` +
    `<div class="factory-stat"><span>成交</span><strong>${fmtNum(getGood(stat, "volumes", output), 1)}</strong></div>` +
    `<div class="factory-stat"><span>零产出 streak</span><strong>${fmtInt(getGood(stat, "zero_output_streak", output))}<small>月</small></strong></div>` +
    `</div>` +
    `<div class="factory-columns">` +
    `<section class="factory-section"><h3>投入 → 产出</h3>${recipe}` +
    `<p class="factory-source">${capitalSource}</p>` +
    `<p class="factory-source">劳动来自失业者与其他行业招聘；产量 = 设备产能 × min(计划, 有效劳动/所需劳动) × 平均熟练度，并受投入品库存约束。</p></section>` +
    `<section class="factory-section"><h3>2^N 设备阶梯</h3><p class="factory-explain">${mechanism}</p></section>` +
    `<section class="factory-section factory-wide"><h3>设备目录</h3><div class="tier-table-wrap factory-tier-table">${tierTable}</div>` +
    `<p class="mechanism-note">名义产能按熟练度 1 定义；实际产量会乘平均熟练度（最高 2.0）和化肥/投入品条件。当前月 T${state.month}。</p></section>` +
    `</div>`;
}
