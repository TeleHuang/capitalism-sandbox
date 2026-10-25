(function () {
  "use strict";

  /* ------------------------------------------------------------------ */
  /* 错误可见性：任何脚本错误都必须显示横幅，而不是白屏。                */
  /* ------------------------------------------------------------------ */
  var errorBanner = document.getElementById("error-banner");
  var errorText = document.getElementById("error-text");
  var errorClose = document.getElementById("error-close");
  var reportedErrors = [];
  function reportError(message) {
    var text = String(message || "未知错误");
    if (text.length > 700) text = text.slice(0, 700) + "…";
    if (reportedErrors.indexOf(text) === -1) reportedErrors.push(text);
    if (errorText) errorText.textContent = reportedErrors.slice(-3).join("  |  ");
    if (errorBanner) errorBanner.hidden = false;
    try { console.error("[dashboard]", message); } catch (_) {}
  }
  window.__dashboardReportError = reportError;
  window.onerror = function (message, source, lineno, colno, error) {
    var where = source ? " @ " + source + (lineno ? ":" + lineno : "") : "";
    reportError((error && error.stack) || (message + where));
    return false;
  };
  window.addEventListener("unhandledrejection", function (event) {
    var reason = event && event.reason;
    reportError("未处理的 Promise 拒绝：" + (reason && (reason.stack || reason.message) || String(reason)));
  });
  if (errorClose) {
    errorClose.addEventListener("click", function () { errorBanner.hidden = true; });
  }

  var tooltip = document.getElementById("chart-tooltip");
  function hideTooltip() {
    if (tooltip) tooltip.hidden = true;
  }

  /* ------------------------------------------------------------------ */
  /* 本地 API 引导                                                       */
  /* ------------------------------------------------------------------ */
  var REGIME_DEFS = [
    {
      id: "classical", label: "古典", name: "古典自由放任（pre-Keynesian）",
      policy_regime: "classical", money_regime: "gold", price_regime: "band",
      demand_regime: "fixed", bank_intermediation: false,
      tax_rate_wage: 0, tax_rate_profit: 0, ui_replacement: 0,
      public_investment_rate: 0, job_guarantee: false, jg_wage: 0
    },
    {
      id: "keynesian", label: "凯恩斯", name: "凯恩斯福利国家",
      policy_regime: "keynesian", money_regime: "gold", price_regime: "band",
      demand_regime: "fixed", bank_intermediation: true,
      tax_rate_wage: 0.08, tax_rate_profit: 0.08, ui_replacement: 0.5,
      public_investment_rate: 0.15, job_guarantee: false, jg_wage: 0
    },
    {
      id: "mmt", label: "MMT", name: "MMT 主权货币 + 就业保障",
      policy_regime: "mmt", money_regime: "credit", price_regime: "band",
      demand_regime: "fixed", bank_intermediation: true,
      tax_rate_wage: 0.08, tax_rate_profit: 0.08, ui_replacement: 0.45,
      public_investment_rate: 0.08, job_guarantee: true, jg_wage: 30
    }
  ];
  var REGIME_IDS = REGIME_DEFS.map(function (regime) { return regime.id; });
  var query = new URLSearchParams(window.location.search);
  function queryInt(name, fallback, low, high) {
    var raw = query.get(name);
    if (raw === null || raw === "") return fallback;
    var value = Number(raw);
    if (!Number.isFinite(value) || Math.floor(value) !== value || value < low || value > high) return fallback;
    return value;
  }
  var API_MONTHS = queryInt("months", 240, 1, 1200);
  var API_SEED = queryInt("seed", 1, -(2 ** 31), 2 ** 31 - 1);
  var requestedRegime = query.get("regime");
  var INITIAL_REGIME = REGIME_IDS.indexOf(requestedRegime) >= 0 ? requestedRegime : "classical";
  var RUNS = {};
  var RUN_PROMISES = {};
  var RUN_STATES = {};
  REGIME_IDS.forEach(function (id) { RUN_STATES[id] = "idle"; });
  RUN_STATES[INITIAL_REGIME] = "loading";
  var COMPARE = null;
  var COMPARE_PROMISE = null;
  var COMPARE_STATE = "idle";
  var META = null;
  var REGIMES = REGIME_DEFS.slice();
  var REGIME_BY_ID = {};
  var GOODS = [];
  var INDUSTRIES = [];
  var GOOD_BY_ID = {};
  var INDUSTRY_BY_ID = {};
  var MONTHS = API_MONTHS;

  function rebuildRegimeIndex() {
    REGIME_BY_ID = {};
    REGIMES.forEach(function (regime) { REGIME_BY_ID[regime.id] = regime; });
  }
  function rebuildGoodIndex() {
    GOOD_BY_ID = {};
    GOODS.forEach(function (good) { GOOD_BY_ID[good.id] = good; });
  }
  function rebuildIndustryIndex() {
    INDUSTRY_BY_ID = {};
    INDUSTRIES.forEach(function (industry) { INDUSTRY_BY_ID[industry.id] = industry; });
  }
  rebuildRegimeIndex();

  var state = {
    regime: INITIAL_REGIME,
    month: MONTHS,
    pending: false,
    booted: false,
    retryAction: null
  };
  var refs = {
    regimeTabs: document.getElementById("regime-tabs"),
    regimeMeta: document.getElementById("regime-meta"),
    monthValue: document.getElementById("month-value"),
    monthTotal: document.getElementById("month-total"),
    monthSlider: document.getElementById("month-slider"),
    timelineScale: document.getElementById("timeline-scale"),
    prevMonth: document.getElementById("prev-month"),
    nextMonth: document.getElementById("next-month"),
    sourceLine: document.getElementById("source-line"),
    generatedLine: document.getElementById("generated-line"),
    runtimeBadges: document.getElementById("runtime-badges"),
    kpiContext: document.getElementById("kpi-context"),
    kpiGrid: document.getElementById("kpi-grid"),
    macroGrid: document.getElementById("macro-grid"),
    govLegend: document.getElementById("gov-legend"),
    govFacts: document.getElementById("gov-facts"),
    priceGrid: document.getElementById("price-grid"),
    productionGrid: document.getElementById("production-grid"),
    diagnosticsGrid: document.getElementById("diagnostics-grid"),
    footerEngine: document.getElementById("footer-engine"),
    footerGenerated: document.getElementById("footer-generated"),
    bootPlaceholder: document.getElementById("boot-placeholder"),
    bootTitle: document.getElementById("boot-title"),
    bootDetail: document.getElementById("boot-detail"),
    bootRetry: document.getElementById("boot-retry"),
    dashboardContent: document.getElementById("dashboard-content"),
    loadBanner: document.getElementById("load-banner"),
    loadTitle: document.getElementById("load-title"),
    loadDetail: document.getElementById("load-detail"),
    loadRetry: document.getElementById("load-retry")
  };
  if (refs.bootRetry) {
    refs.bootRetry.addEventListener("click", function () {
      var action = state.retryAction;
      if (action) action();
    });
  }
  if (refs.loadRetry) {
    refs.loadRetry.addEventListener("click", function () {
      var action = state.retryAction;
      if (action) action();
    });
  }
  if (refs.monthSlider) refs.monthSlider.disabled = true;

  function setRegimeState(id, value) {
    if (REGIME_IDS.indexOf(id) < 0) return;
    RUN_STATES[id] = value;
    renderRuntimeBadges();
    updateRegimeTabStates();
  }
  function renderRuntimeBadges() {
    if (!refs.runtimeBadges) return;
    var labels = { idle: "待运行", loading: "运行中", loaded: "已载入", error: "失败" };
    var badges = REGIME_IDS.map(function (id) {
      var def = REGIME_BY_ID[id] || REGIME_DEFS.filter(function (r) { return r.id === id; })[0];
      return '<span class="runtime-badge" data-state="' + RUN_STATES[id] + '"><span class="dot"></span><span>' +
        escapeHtml(def ? def.label : id) + " · " + labels[RUN_STATES[id]] + '</span></span>';
    });
    var compareLabels = { idle: "待加载", loading: "运行中", loaded: "已载入", error: "失败" };
    badges.push('<span class="runtime-badge" data-state="' + COMPARE_STATE + '"><span class="dot"></span><span>三制度对比 · ' +
      (compareLabels[COMPARE_STATE] || COMPARE_STATE) + '</span></span>');
    refs.runtimeBadges.innerHTML = badges.join("");
  }
  function updateRegimeTabStates() {
    if (!refs.regimeTabs) return;
    Array.prototype.forEach.call(refs.regimeTabs.querySelectorAll("[data-regime]"), function (button) {
      var id = button.getAttribute("data-regime");
      button.setAttribute("data-state", RUN_STATES[id] || "idle");
      button.disabled = state.pending;
      var status = button.querySelector(".tab-status");
      if (status) status.title = RUN_STATES[id] || "idle";
    });
  }
  function setControlsLocked(locked) {
    state.pending = locked;
    if (refs.monthSlider) refs.monthSlider.disabled = locked || !state.booted;
    if (refs.prevMonth) refs.prevMonth.disabled = locked || !state.booted || state.month <= 1;
    if (refs.nextMonth) refs.nextMonth.disabled = locked || !state.booted || state.month >= MONTHS;
    document.body.classList.toggle("is-busy", locked);
    updateRegimeTabStates();
  }
  function showLoad(title, detail, retryAction) {
    state.retryAction = retryAction || null;
    if (refs.loadTitle) refs.loadTitle.textContent = title || "正在运行仿真";
    if (refs.loadDetail) refs.loadDetail.textContent = detail || "";
    if (refs.loadBanner) refs.loadBanner.hidden = false;
    if (refs.loadRetry) refs.loadRetry.hidden = !retryAction;
    if (refs.bootRetry) refs.bootRetry.hidden = !retryAction;
  }
  function hideLoad() {
    state.retryAction = null;
    if (refs.loadBanner) refs.loadBanner.hidden = true;
    if (refs.loadRetry) refs.loadRetry.hidden = true;
    if (refs.bootRetry) refs.bootRetry.hidden = true;
  }
  function showBoot(title, detail, retryAction) {
    if (refs.bootTitle) refs.bootTitle.textContent = title;
    if (refs.bootDetail) refs.bootDetail.textContent = detail;
    if (refs.bootPlaceholder) refs.bootPlaceholder.hidden = false;
    if (refs.bootRetry) refs.bootRetry.hidden = !retryAction;
    state.retryAction = retryAction || null;
  }
  function hideBoot() {
    if (refs.bootPlaceholder) refs.bootPlaceholder.hidden = true;
    if (refs.bootRetry) refs.bootRetry.hidden = true;
  }
  function showContent() {
    hideBoot();
    if (refs.dashboardContent) refs.dashboardContent.classList.remove("hidden");
    state.booted = true;
    if (refs.monthSlider) refs.monthSlider.disabled = false;
    setControlsLocked(false);
  }

  function applyRunMeta(response) {
    if (response && response.meta) {
      META = response.meta;
      if (Array.isArray(META.regimes) && META.regimes.length) REGIMES = META.regimes;
      GOODS = Array.isArray(META.goods) ? META.goods : [];
      INDUSTRIES = Array.isArray(META.industries) ? META.industries : [];
      rebuildRegimeIndex();
      rebuildGoodIndex();
      rebuildIndustryIndex();
      var actualMonths = Number(META.months);
      if (Number.isFinite(actualMonths) && actualMonths > 0 && actualMonths !== MONTHS) {
        MONTHS = actualMonths;
        state.month = clamp(state.month, 1, MONTHS);
        updateTimelineScale();
      }
      if (!META.months) MONTHS = API_MONTHS;
      refs.sourceLine.textContent = META.engine + " · " + MONTHS + " 月 · seed " + META.seed + " · " + REGIMES.length + " 种制度";
      refs.generatedLine.textContent = "API 生成于 " + META.generated_at;
      refs.footerEngine.textContent = META.engine + " · seed " + META.seed + " · " + MONTHS + " 月";
      refs.footerGenerated.textContent = "V" + META.version + " · 本地 API · " + META.generated_at;
    }
    renderRegimeTabs();
    updateTimelineScale();
  }

  function fetchJson(url) {
    return fetch(url, { headers: { "Accept": "application/json" }, cache: "no-store" })
      .then(function (response) {
        return response.json().catch(function () { return {}; }).then(function (payload) {
          if (!response.ok) {
            throw new Error(payload.error || ("HTTP " + response.status));
          }
          return payload;
        });
      });
  }

  function fetchRun(regimeId) {
    if (RUNS[regimeId]) return Promise.resolve(RUNS[regimeId]);
    if (RUN_PROMISES[regimeId]) return RUN_PROMISES[regimeId];
    setRegimeState(regimeId, "loading");
    var url = "/api/run?regime=" + encodeURIComponent(regimeId) +
      "&months=" + encodeURIComponent(API_MONTHS) + "&seed=" + encodeURIComponent(API_SEED);
    var promise = fetchJson(url).then(function (response) {
      RUNS[regimeId] = response;
      setRegimeState(regimeId, "loaded");
      return response;
    }).catch(function (error) {
      setRegimeState(regimeId, "error");
      throw error;
    }).finally(function () {
      delete RUN_PROMISES[regimeId];
    });
    RUN_PROMISES[regimeId] = promise;
    return promise;
  }

  function switchRegime(regimeId, initial) {
    if (REGIME_IDS.indexOf(regimeId) < 0) return Promise.resolve();
    if (state.pending && !initial) return Promise.resolve();
    hideTooltip();
    if (RUNS[regimeId] && !initial) {
      state.regime = regimeId;
      applyRunMeta(RUNS[regimeId]);
      updateControls();
      renderAll();
      return Promise.resolve(RUNS[regimeId]);
    }
    setControlsLocked(true);
    setRegimeState(regimeId, "loading");
    if (initial) {
      showBoot("正在运行 " + regimeLabel(regimeId) + " 制度…",
        "引擎正在运行 " + API_MONTHS + " 个月；首次运行需要等待，结果会缓存在本地服务端。", null);
    } else {
      showLoad("正在运行 " + regimeLabel(regimeId) + " 制度…",
        MONTHS + " 个月 · seed " + API_SEED + " · 请等待引擎完成", null);
    }
    return fetchRun(regimeId).then(function (response) {
      state.regime = regimeId;
      applyRunMeta(response);
      hideLoad();
      showContent();
      updateControls();
      renderAll();
      return response;
    }).catch(function (error) {
      reportError("制度 " + regimeLabel(regimeId) + " 载入失败：" + error.message);
      setRegimeState(regimeId, "error");
      var retry = function () {
        hideLoad();
        setControlsLocked(true);
        switchRegime(regimeId, !state.booted).catch(function () {});
      };
      if (state.booted) {
        showLoad("载入失败：" + regimeLabel(regimeId), error.message, retry);
        setControlsLocked(false);
      } else {
        showBoot("无法运行 " + regimeLabel(regimeId) + " 制度", error.message, retry);
        setControlsLocked(false);
        if (refs.bootRetry) refs.bootRetry.hidden = false;
      }
      throw error;
    });
  }

  function regimeLabel(id) {
    var regime = REGIME_BY_ID[id] || REGIME_DEFS.filter(function (r) { return r.id === id; })[0];
    return regime ? regime.label : id;
  }

  function loadCompare() {
    if (COMPARE) return Promise.resolve(COMPARE);
    if (COMPARE_PROMISE) return COMPARE_PROMISE;
    setCompareState("loading");
    var url = "/api/compare?months=" + encodeURIComponent(API_MONTHS) + "&seed=" + encodeURIComponent(API_SEED);
    COMPARE_PROMISE = fetchJson(url).then(function (response) {
      COMPARE = response;
      setCompareState("loaded");
      if (state.booted) renderAll();
      return response;
    }).catch(function (error) {
      setCompareState("error");
      reportError("三制度对比加载失败：" + error.message);
      if (state.booted) renderAll();
      return null;
    }).finally(function () {
      COMPARE_PROMISE = null;
    });
    return COMPARE_PROMISE;
  }
  function setCompareState(value) {
    COMPARE_STATE = value;
    renderRuntimeBadges();
    if (state.booted && value !== "loading") renderAll();
  }

  function prefetchRemaining() {
    var remaining = REGIME_IDS.filter(function (id) { return !RUNS[id]; });
    if (!remaining.length) {
      loadCompare();
      return;
    }
    var index = 0;
    function next() {
      if (index >= remaining.length) {
        loadCompare();
        return;
      }
      var regimeId = remaining[index++];
      if (RUNS[regimeId] || RUN_STATES[regimeId] === "loading") {
        // 如果正在显式加载，等它完成后再继续。
        if (RUN_PROMISES[regimeId]) {
          RUN_PROMISES[regimeId].then(next, next);
        } else {
          next();
        }
        return;
      }
      setRegimeState(regimeId, "loading");
      fetchRun(regimeId).then(next, function () { next(); });
    }
    next();
  }

  function boot() {
    setControlsLocked(true);
    renderRuntimeBadges();
    switchRegime(INITIAL_REGIME, true).then(function () {
      // 先让默认制度落到屏幕上，再在后台预取另外两个。
      window.setTimeout(prefetchRemaining, 700);
    }).catch(function () {
      // 错误横幅和 boot 占位已经显示，保持可重试。
    });
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function clamp(value, low, high) { return Math.max(low, Math.min(high, value)); }
  function num(value, fallback) {
    var n = Number(value);
    return Number.isFinite(n) ? n : (fallback == null ? 0 : fallback);
  }
  var integerFormat = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 });
  function fmtInt(value) {
    if (!Number.isFinite(Number(value))) return "—";
    return integerFormat.format(Number(value));
  }
  function fmtNum(value, digits) {
    if (!Number.isFinite(Number(value))) return "—";
    var d = digits == null ? 2 : digits;
    return new Intl.NumberFormat("zh-CN", {
      maximumFractionDigits: d, minimumFractionDigits: 0
    }).format(Number(value));
  }
  function fmtFixed(value, digits) {
    if (!Number.isFinite(Number(value))) return "—";
    return new Intl.NumberFormat("zh-CN", {
      maximumFractionDigits: digits, minimumFractionDigits: digits
    }).format(Number(value));
  }
  function fmtPct(value, digits) {
    if (!Number.isFinite(Number(value))) return "—";
    return (Number(value) * 100).toFixed(digits == null ? 1 : digits) + "%";
  }
  function trimZeros(text) {
    return String(text).replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
  }
  function fmtCompact(value) {
    var n = Number(value);
    if (!Number.isFinite(n)) return "—";
    var abs = Math.abs(n);
    if (abs >= 100000000) return trimZeros((n / 100000000).toFixed(2)) + "亿";
    if (abs >= 10000) return trimZeros((n / 10000).toFixed(1)) + "万";
    if (abs >= 1000) return trimZeros((n / 1000).toFixed(1)) + "k";
    if (abs >= 10) return fmtNum(n, 1);
    return fmtNum(n, 2);
  }
  function fmtAxis(value, format) {
    if (format === "rate") return fmtPct(value, 1);
    if (format === "price") return trimZeros(fmtNum(value, 2));
    if (format === "qty") return trimZeros(fmtNum(value, 1));
    return trimZeros(fmtCompact(value));
  }
  function fmtValue(value, format) {
    if (format === "rate") return fmtPct(value, 2);
    if (format === "price") return fmtNum(value, 2);
    if (format === "qty") return fmtNum(value, 2);
    if (format === "count") return fmtInt(value);
    return fmtNum(value, 0);
  }
  function fmtSigned(value, format) {
    var n = Number(value) || 0;
    var prefix = n > 0 ? "+" : n < 0 ? "−" : "";
    var formatted = format === "rate" ? fmtPct(Math.abs(n), 2) : fmtNum(Math.abs(n), format === "count" ? 0 : 2);
    return prefix + formatted;
  }
  function fmtMonths(value) {
    if (!Number.isFinite(Number(value))) return "—";
    return fmtNum(value, 1) + " 个月";
  }

  function currentRun() { return RUNS[state.regime] || null; }
  function currentData() { return currentRun() || {}; }
  function regimeMeta(id) {
    var fallback = REGIME_DEFS.filter(function (regime) { return regime.id === id; })[0];
    return REGIME_BY_ID[id || state.regime] || fallback || REGIMES[0] || REGIME_DEFS[0];
  }
  function scalarSeries(metric, regimeId) {
    var run = RUNS[regimeId || state.regime];
    var series = run && run.scalars && run.scalars[metric];
    return Array.isArray(series) ? series : [];
  }
  function scalarAt(metric, index, regimeId) {
    return num(scalarSeries(metric, regimeId)[index], 0);
  }
  function goodSeries(field, key, regimeId) {
    var run = RUNS[regimeId || state.regime];
    var mapping = run && run.goods && run.goods[field];
    if (!mapping || !Array.isArray(mapping[key])) return [];
    return mapping[key];
  }
  function goodAt(field, key, index, regimeId) {
    return num(goodSeries(field, key, regimeId)[index], 0);
  }
  function industrySeries(field, key, regimeId) {
    var run = RUNS[regimeId || state.regime];
    var mapping = run && run.industries && run.industries[field];
    if (!mapping || !Array.isArray(mapping[key])) return [];
    return mapping[key];
  }
  function industryAt(field, key, index) {
    return num(industrySeries(field, key)[index], 0);
  }
  function ageHistogramSeries(bucket, regimeId) {
    var run = RUNS[regimeId || state.regime];
    var mapping = run && run.demography && run.demography.age_histogram;
    if (!mapping || !Array.isArray(mapping[bucket])) return [];
    return mapping[bucket];
  }
  function ageAt(bucket, index, regimeId) {
    return num(ageHistogramSeries(bucket, regimeId)[index], 0);
  }
  function ageBuckets() {
    var run = currentData();
    var buckets = run.demography && run.demography.age_buckets;
    return Array.isArray(buckets) ? buckets : [];
  }
  function warningsAt(index) {
    var data = currentData();
    var warnings = data.warnings && data.warnings[index];
    return Array.isArray(warnings) ? warnings : [];
  }
  function goodLabel(id) { return (GOOD_BY_ID[id] && GOOD_BY_ID[id].label) || id; }
  function industryLabel(id) { return (INDUSTRY_BY_ID[id] && INDUSTRY_BY_ID[id].label) || id; }
  function industryOutput(id) {
    var industry = INDUSTRY_BY_ID[id];
    return industry && industry.output ? industry.output : null;
  }
  function compareValue(regimeId, metric, index) {
    if (!COMPARE || !COMPARE.monthly || !COMPARE.monthly[regimeId]) return null;
    var series = COMPARE.monthly[regimeId][metric];
    if (!Array.isArray(series) || index < 0 || index >= series.length) return null;
    return num(series[index]);
  }

  function policyBits(regime) {
    var bits = [];
    if (regime.policy_regime === "classical") bits.push("无政府模块");
    else {
      if (num(regime.tax_rate_wage) > 0) bits.push("工资税 " + fmtPct(regime.tax_rate_wage, 0));
      if (num(regime.tax_rate_profit) > 0) bits.push("利润税 " + fmtPct(regime.tax_rate_profit, 0));
      if (num(regime.ui_replacement) > 0) bits.push("失业救济 " + fmtPct(regime.ui_replacement, 0));
      if (num(regime.public_investment_rate) > 0) bits.push("公共投资 " + fmtPct(regime.public_investment_rate, 0) + " GDP");
      if (regime.job_guarantee) bits.push("就业保障");
    }
    bits.push(regime.money_regime === "credit" ? "信用货币" : "金本位");
    bits.push(regime.bank_intermediation ? "银行中介" : "无银行中介");
    bits.push(regime.price_regime === "markup" ? "成本加成价格" : "价格带");
    bits.push(regime.demand_regime === "les" ? "LES 需求" : "固定篮子需求");
    return bits;
  }
  function regimeHint(regime) {
    var money = regime.money_regime === "credit" ? "信用货币" : "金本位";
    var policy = regime.policy_regime === "classical" ? "无政府" : regime.job_guarantee ? "央行 + 就业保障" : "税收 + UI + 公共投资";
    return money + " · " + policy;
  }

  function deltaText(current, previous, mode) {
    if (!Number.isFinite(previous)) return "起始月";
    var diff = current - previous;
    if (Math.abs(diff) < 1e-12) return "与上月持平";
    var arrow = diff > 0 ? "↑" : "↓";
    var absolute = Math.abs(diff);
    if (mode === "pp") return arrow + " " + (absolute * 100).toFixed(2) + " pp 较上月";
    if (mode === "pct") {
      if (Math.abs(previous) < 1e-9) return arrow + " " + fmtCompact(absolute) + " 较上月";
      return arrow + " " + Math.abs(diff / Math.abs(previous) * 100).toFixed(1) + "% 较上月";
    }
    if (mode === "count") return arrow + " " + fmtInt(absolute) + " 较上月";
    return arrow + " " + fmtCompact(absolute) + " 较上月";
  }

  /* ------------------------------------------------------------------ */
  /* 控制条                                                              */
  /* ------------------------------------------------------------------ */
  function renderRegimeTabs() {
    if (!refs.regimeTabs) return;
    refs.regimeTabs.innerHTML = REGIMES.map(function (regime) {
      var active = regime.id === state.regime;
      return '<button class="regime-tab" type="button" role="tab" data-regime="' +
        escapeHtml(regime.id) + '" aria-selected="' + (active ? "true" : "false") + '" title="' +
        escapeHtml(regime.name || regime.label) + '">' +
        '<span class="tab-name">' + escapeHtml(regime.label || regime.id) +
        '<span class="tab-status" aria-hidden="true"></span></span>' +
        '<span class="tab-hint">' + escapeHtml(regimeHint(regime)) + '</span>' +
        '</button>';
    }).join("");
    updateRegimeTabStates();
  }
  function updateTimelineScale() {
    if (!refs.monthSlider) return;
    refs.monthSlider.min = "1";
    refs.monthSlider.max = String(MONTHS);
    refs.monthSlider.step = "1";
    refs.monthSlider.value = String(state.month);
    var tickCount = 5;
    var ticks = [];
    for (var i = 0; i < tickCount; i++) {
      ticks.push(Math.round(1 + (MONTHS - 1) * (i / (tickCount - 1))));
    }
    ticks = ticks.filter(function (value, index, arr) { return arr.indexOf(value) === index; });
    if (refs.timelineScale) {
      refs.timelineScale.innerHTML = ticks.map(function (tick) {
        return "<span>T" + tick + "</span>";
      }).join("");
    }
  }
  function buildControls() {
    renderRegimeTabs();
    if (refs.regimeTabs) {
      refs.regimeTabs.addEventListener("click", function (event) {
        var button = event.target.closest("[data-regime]");
        if (!button || button.disabled) return;
        switchRegime(button.getAttribute("data-regime")).catch(function () {});
      });
    }
    if (refs.monthSlider) {
      refs.monthSlider.addEventListener("input", function () {
        selectMonth(Number(refs.monthSlider.value));
      });
    }
    if (refs.prevMonth) refs.prevMonth.addEventListener("click", function () { selectMonth(state.month - 1); });
    if (refs.nextMonth) refs.nextMonth.addEventListener("click", function () { selectMonth(state.month + 1); });
    updateTimelineScale();
    document.addEventListener("keydown", function (event) {
      if (!state.booted || state.pending) return;
      var tag = event.target && event.target.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (event.key === "ArrowLeft") { event.preventDefault(); selectMonth(state.month - 1); }
      if (event.key === "ArrowRight") { event.preventDefault(); selectMonth(state.month + 1); }
    });
  }

  function selectMonth(month) {
    if (!state.booted || state.pending) return;
    var next = clamp(Math.round(Number(month) || 1), 1, MONTHS);
    if (next === state.month) return;
    state.month = next;
    hideTooltip();
    if (refs.monthSlider.value !== String(next)) refs.monthSlider.value = String(next);
    updateControls();
    scheduleRender();
  }
  function updateControls() {
    var regime = regimeMeta();
    if (refs.regimeTabs) {
      Array.prototype.forEach.call(refs.regimeTabs.querySelectorAll("[data-regime]"), function (button) {
        var active = button.getAttribute("data-regime") === state.regime;
        button.setAttribute("aria-selected", active ? "true" : "false");
        button.tabIndex = active ? 0 : -1;
      });
    }
    var percent = MONTHS <= 1 ? 100 : ((state.month - 1) / (MONTHS - 1)) * 100;
    if (refs.monthSlider) {
      refs.monthSlider.value = String(state.month);
      refs.monthSlider.style.setProperty("--fill", percent + "%");
      refs.monthSlider.setAttribute("aria-valuetext", "第 " + state.month + " 月，共 " + MONTHS + " 月");
    }
    if (refs.monthValue) refs.monthValue.textContent = state.booted ? "T" + state.month : "T—";
    if (refs.monthTotal) refs.monthTotal.textContent = "/ " + MONTHS + " 月";
    if (refs.prevMonth) refs.prevMonth.disabled = state.pending || !state.booted || state.month <= 1;
    if (refs.nextMonth) refs.nextMonth.disabled = state.pending || !state.booted || state.month >= MONTHS;
    if (refs.regimeMeta) {
      if (state.booted && currentRun()) {
        refs.regimeMeta.innerHTML = '<span class="chip">' + escapeHtml(regime.name || regime.label) + '</span>' +
          policyBits(regime).map(function (bit) { return '<span class="chip">' + escapeHtml(bit) + '</span>'; }).join("");
      } else {
        refs.regimeMeta.textContent = "等待引擎返回配置…";
      }
    }
    if (refs.kpiContext) refs.kpiContext.textContent = "第 " + state.month + " 月 / 共 " + MONTHS + " 月 · " + regime.label;
    document.title = "EcoSim V0.5 · " + regime.label + " · T" + state.month;
    updateRegimeTabStates();
  }

  /* ------------------------------------------------------------------ */
  /* 格式化 / KPI                                                       */
  /* ------------------------------------------------------------------ */
  function kpiCard(options) {
    return '<article class="kpi" style="--kpi-color:' + options.color + '">' +
      '<div class="kpi-head"><span class="kpi-label">' + escapeHtml(options.label) + '</span>' +
      '<span class="kpi-tag">' + escapeHtml(options.tag) + '</span></div>' +
      '<div class="kpi-main"><span class="kpi-value" title="' + escapeHtml(options.exact || options.value) + '">' +
      escapeHtml(options.value) + '</span><span class="kpi-unit">' + escapeHtml(options.unit) + '</span></div>' +
      '<div class="kpi-sub">' + options.sub + '</div>' +
      '<div class="kpi-delta" title="与上一月比较">' + escapeHtml(options.delta || "起始月") + '</div>' +
      '<div class="spark" data-spark="' + escapeHtml(options.spark) + '" data-color="' + options.color + '" aria-hidden="true"></div>' +
      '</article>';
  }

  function renderKpis(index) {
    var previous = index > 0 ? index - 1 : null;
    var alive = scalarAt("alive", index);
    var unemployed = scalarAt("unemployed", index);
    var unemploymentRate = scalarAt("unemployment_rate", index);
    var gdp = scalarAt("gdp", index);
    var investment = scalarAt("investment", index);
    var consumption = scalarAt("consumption", index);
    var profitRate = scalarAt("profit_rate", index);
    var profit = scalarAt("profit", index);
    var debt = scalarAt("government_debt", index);
    var deficit = scalarAt("government_deficit", index);
    var centralBank = scalarAt("central_bank_money", index);
    var moneyTotal = scalarAt("money_total", index);
    var jgWorkers = scalarAt("government_jg_workers", index);
    var foodReserve = scalarAt("food_reserve", index);
    var foodReserveCash = scalarAt("food_reserve_cash", index);
    var foodDemand = goodAt("demand", "food", index);
    var reserveMonths = foodDemand > 1e-9 ? foodReserve / foodDemand : null;
    var bankCash = scalarAt("bank_cash", index);
    var deposits = scalarAt("bank_deposits", index);
    var loans = scalarAt("bank_loans", index);
    var writeOffs = scalarAt("bank_write_offs", index);
    var equity = scalarAt("bank_equity", index);
    var regime = regimeMeta();
    var reserveMonthsText = reserveMonths == null ? "无食品市场需求" : fmtMonths(reserveMonths);
    var jgShare = alive > 0 ? jgWorkers / alive : 0;
    var population = scalarAt("population", index);
    var children = scalarAt("children", index);
    var workingAge = scalarAt("working_age", index);
    var retirees = scalarAt("retirees", index);
    var births = scalarAt("births", index);
    var deaths = scalarAt("deaths", index);
    var birthRate = scalarAt("birth_rate", index);
    var deathRate = scalarAt("death_rate", index);
    var dependencyRatio = scalarAt("dependency_ratio", index);
    var oldAgeDependency = scalarAt("old_age_dependency", index);
    var pensionFund = scalarAt("pension_fund", index);
    var pensionRevenue = scalarAt("pension_revenue", index);
    var pensionSpending = scalarAt("pension_spending", index);
    var pensionRecipients = scalarAt("pension_recipients", index);
    var averageAge = scalarAt("average_age", index);

    refs.kpiGrid.innerHTML = [
      kpiCard({
        label: "存活 / 失业", tag: "人口", color: "var(--series-3)",
        value: fmtInt(alive), exact: fmtInt(alive) + " 人", unit: "人",
        sub: "失业 <b>" + fmtInt(unemployed) + "</b> 人 · 失业率 <b>" + fmtPct(unemploymentRate, 1) + "</b>",
        delta: previous == null ? "起始月" : deltaText(alive, scalarAt("alive", previous), "count"),
        spark: "alive"
      }),
      kpiCard({
        label: "GDP / 投资", tag: "宏观", color: "var(--series-1)",
        value: fmtInt(gdp), exact: fmtInt(gdp) + " 元 / 月", unit: "元",
        sub: "投资 <b>" + fmtCompact(investment) + "</b> · 消费 <b>" + fmtCompact(consumption) + "</b>",
        delta: previous == null ? "起始月" : deltaText(gdp, scalarAt("gdp", previous), "pct"),
        spark: "gdp"
      }),
      kpiCard({
        label: "资本主义利润率", tag: "利润", color: "var(--series-4)",
        value: fmtPct(profitRate, 2), exact: fmtPct(profitRate, 4), unit: "",
        sub: "月度经济利润 <b>" + fmtSigned(profit, "money") + "</b> 元",
        delta: previous == null ? "起始月" : deltaText(profitRate, scalarAt("profit_rate", previous), "pp"),
        spark: "profit_rate"
      }),
      kpiCard({
        label: "政府债务 / 赤字", tag: "财政", color: "var(--series-1)",
        value: fmtInt(debt), exact: fmtInt(debt) + " 元", unit: "元",
        sub: "本月赤字 <b>" + fmtSigned(deficit, "money") + "</b> 元",
        delta: previous == null ? "起始月" : deltaText(debt, scalarAt("government_debt", previous), "pct"),
        spark: "government_debt"
      }),
      kpiCard({
        label: "央行货币", tag: "货币", color: "var(--series-2)",
        value: fmtInt(centralBank), exact: fmtInt(centralBank) + " 元", unit: "元",
        sub: "货币总量 <b>" + fmtCompact(moneyTotal) + "</b> 元 · " + escapeHtml(regime.money_regime === "credit" ? "信用货币" : "金本位"),
        delta: previous == null ? "起始月" : deltaText(centralBank, scalarAt("central_bank_money", previous), "pct"),
        spark: "central_bank_money"
      }),
      kpiCard({
        label: "就业保障人数", tag: "就业", color: "var(--series-3)",
        value: fmtInt(jgWorkers), exact: fmtInt(jgWorkers) + " 人", unit: "人",
        sub: (regime.job_guarantee ? "占存活工人 <b>" + fmtPct(jgShare, 1) + "</b> · 保障工资 <b>" + fmtNum(regime.jg_wage, 0) + "</b> 元" : "该制度未启用就业保障"),
        delta: previous == null ? "起始月" : deltaText(jgWorkers, scalarAt("government_jg_workers", previous), "count"),
        spark: "government_jg_workers"
      }),
      kpiCard({
        label: "粮食储备", tag: "储备", color: "var(--series-3)",
        value: fmtNum(foodReserve, 1), exact: fmtNum(foodReserve, 2) + " 吨", unit: "吨",
        sub: "覆盖市场需求 <b>" + escapeHtml(reserveMonthsText) + "</b> · 储备现金 <b>" + fmtCompact(foodReserveCash) + "</b> 元",
        delta: previous == null ? "起始月" : deltaText(foodReserve, scalarAt("food_reserve", previous), "pct"),
        spark: "food_reserve"
      }),
      kpiCard({
        label: "银行现金 / 资产负债", tag: "银行", color: "var(--series-7)",
        value: fmtInt(bankCash), exact: fmtInt(bankCash) + " 元", unit: "元",
        sub: "存款 <b>" + fmtCompact(deposits) + "</b> · 贷款 <b>" + fmtCompact(loans) + "</b><br>坏账 <b>" + fmtCompact(writeOffs) + "</b> · 权益 <b>" + fmtCompact(equity) + "</b>",
        delta: previous == null ? "起始月" : deltaText(bankCash, scalarAt("bank_cash", previous), "pct"),
        spark: "bank_cash"
      }),
      kpiCard({
        label: "人口结构", tag: "人口", color: "var(--series-3)",
        value: fmtInt(population), exact: fmtInt(population) + " 人", unit: "人",
        sub: "儿童 <b>" + fmtInt(children) + "</b> · 劳动 <b>" + fmtInt(workingAge) +
          "</b> · 退休 <b>" + fmtInt(retirees) + "</b><br>平均年龄 <b>" + fmtNum(averageAge, 1) + "</b> 岁",
        delta: previous == null ? "起始月" : deltaText(population, scalarAt("population", previous), "count"),
        spark: "population"
      }),
      kpiCard({
        label: "出生 / 死亡", tag: "人口流", color: "var(--series-1)",
        value: fmtInt(births), exact: fmtInt(births) + " 人 / 月", unit: "人",
        sub: "死亡 <b>" + fmtInt(deaths) + "</b> 人 · 出生率 <b>" + fmtPct(birthRate, 2) +
          "</b><br>死亡率 <b>" + fmtPct(deathRate, 2) + "</b>",
        delta: previous == null ? "起始月" : deltaText(births, scalarAt("births", previous), "count"),
        spark: "births"
      }),
      kpiCard({
        label: "总抚养比", tag: "代际", color: "var(--series-2)",
        value: fmtPct(dependencyRatio, 1), exact: fmtPct(dependencyRatio, 2), unit: "",
        sub: "老年抚养比 <b>" + fmtPct(oldAgeDependency, 1) +
          "</b> · 儿童 + 退休 / 劳动年龄",
        delta: previous == null ? "起始月" : deltaText(dependencyRatio, scalarAt("dependency_ratio", previous), "pp"),
        spark: "dependency_ratio"
      }),
      kpiCard({
        label: "养老金基金", tag: "养老金", color: "var(--series-4)",
        value: fmtInt(pensionFund), exact: fmtInt(pensionFund) + " 元", unit: "元",
        sub: "本月收入 <b>" + fmtCompact(pensionRevenue) + "</b> · 支出 <b>" +
          fmtCompact(pensionSpending) + "</b><br>领取者 <b>" + fmtInt(pensionRecipients) + "</b> 人",
        delta: previous == null ? "起始月" : deltaText(pensionFund, scalarAt("pension_fund", previous), "pct"),
        spark: "pension_fund"
      })
    ].join("");
  }

  /* ------------------------------------------------------------------ */
  /* SVG 图表                                                            */
  /* ------------------------------------------------------------------ */
  var LINE_META = {
    gdp: { label: "GDP", unit: "元 / 月", color: "var(--series-1)", format: "money", includeZero: true },
    investment: { label: "投资", unit: "元 / 月", color: "var(--series-2)", format: "money", includeZero: true },
    unemployment_rate: { label: "失业率", unit: "%", color: "var(--series-3)", format: "rate", includeZero: true },
    profit_rate: { label: "资本主义利润率", unit: "%", color: "var(--series-4)", format: "rate", includeZero: true }
  };
  var MULTI_META = {
    government_debt: { label: "政府债务", color: "var(--series-1)", format: "money" },
    central_bank_money: { label: "央行货币", color: "var(--series-2)", format: "money" },
    births: { label: "出生", color: "var(--series-1)", format: "count" },
    deaths: { label: "死亡", color: "var(--series-4)", format: "count" },
    dependency_ratio: { label: "总抚养比", color: "var(--series-3)", format: "rate" },
    old_age_dependency: { label: "老年抚养比", color: "var(--series-2)", format: "rate" },
    pension_revenue: { label: "养老金收入", color: "var(--series-1)", format: "money" },
    pension_spending: { label: "养老金支出", color: "var(--series-4)", format: "money" },
    pension_fund: { label: "基金余额", color: "var(--series-3)", format: "money" }
  };
  var SVG_NS = "http://www.w3.org/2000/svg";

  function svgEl(name, attrs) {
    var element = document.createElementNS(SVG_NS, name);
    if (attrs) Object.keys(attrs).forEach(function (key) { element.setAttribute(key, attrs[key]); });
    return element;
  }
  function svgText(parent, x, y, text, attrs) {
    var node = svgEl("text", Object.assign({ x: x, y: y, class: "chart-axis" }, attrs || {}));
    node.textContent = text;
    parent.appendChild(node);
    return node;
  }
  function numericValues(values) {
    return (values || []).filter(function (value) { return Number.isFinite(Number(value)); }).map(Number);
  }
  function paddedDomain(values, includeZero) {
    var nums = numericValues(values);
    if (!nums.length) return { low: 0, high: 1 };
    var low = Math.min.apply(null, nums);
    var high = Math.max.apply(null, nums);
    if (includeZero) { low = Math.min(0, low); high = Math.max(0, high); }
    var span = high - low;
    if (span < 1e-12) {
      var pad = Math.max(Math.abs(high) * 0.12, 0.01);
      low -= pad; high += pad;
      if (includeZero) low = Math.min(0, low);
    } else {
      var padding = span * 0.10;
      if (includeZero) {
        if (low < 0) low -= padding;
        high += padding * 0.6;
      } else {
        low -= padding; high += padding;
      }
    }
    if (high - low < 1e-12) high = low + 1;
    return { low: low, high: high };
  }
  function niceTicks(low, high, count) {
    count = count || 3;
    var span = high - low;
    if (!(span > 1e-12)) return [low];
    var raw = span / count;
    var power = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10));
    var normalized = raw / power;
    var step = (normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10) * power;
    var first = Math.ceil((low - 1e-12) / step) * step;
    var ticks = [];
    for (var value = first; value <= high + step * 1e-8 && ticks.length < 20; value += step) {
      ticks.push(Math.abs(value) < step * 1e-9 ? 0 : value);
    }
    if (!ticks.length) ticks.push(low, high);
    return ticks;
  }
  function monthTickIndices() {
    var count = Math.min(5, MONTHS);
    if (count === 1) return [0];
    var indices = [];
    for (var i = 0; i < count; i++) {
      var value = Math.round((MONTHS - 1) * (i / (count - 1)));
      if (indices.indexOf(value) === -1) indices.push(value);
    }
    return indices;
  }
  function setHostAria(host, label) {
    host.setAttribute("role", "img");
    host.setAttribute("aria-label", label);
  }
  function showTooltip(event, html) {
    if (!tooltip) return;
    tooltip.innerHTML = html;
    tooltip.hidden = false;
    var padding = 14;
    var width = tooltip.offsetWidth || 170;
    var height = tooltip.offsetHeight || 60;
    var left = event.clientX + padding;
    var top = event.clientY + padding;
    if (left + width > window.innerWidth - 10) left = event.clientX - width - padding;
    if (top + height > window.innerHeight - 10) top = event.clientY - height - padding;
    tooltip.style.left = Math.max(8, left) + "px";
    tooltip.style.top = Math.max(8, top) + "px";
  }
  function tooltipRows(series, index) {
    return series.map(function (one) {
      return '<div class="tt-row"><span class="tt-key"><i style="--tt-color:' + one.color + '"></i>' +
        escapeHtml(one.label) + '</span><strong>' + fmtValue(one.values[index], one.format) + '</strong></div>';
    }).join("");
  }

  function drawLineChart(host, series, options) {
    var width = Math.max(220, Math.round(host.getBoundingClientRect().width || host.clientWidth || 360));
    var height = options.height || 156;
    var margin = { left: 48, right: 14, top: 10, bottom: 22 };
    var plotWidth = Math.max(20, width - margin.left - margin.right);
    var plotHeight = Math.max(20, height - margin.top - margin.bottom);
    var allValues = [];
    series.forEach(function (one) { allValues = allValues.concat(one.values); });
    var domain = paddedDomain(allValues, options.includeZero !== false);
    var xScale = function (index) {
      return MONTHS <= 1 ? margin.left + plotWidth / 2 : margin.left + (index / (MONTHS - 1)) * plotWidth;
    };
    var yScale = function (value) {
      return margin.top + (domain.high - value) / (domain.high - domain.low) * plotHeight;
    };
    var svg = svgEl("svg", {
      viewBox: "0 0 " + width + " " + height,
      width: "100%", height: String(height),
      "aria-hidden": "true", focusable: "false"
    });
    // grid + y labels
    niceTicks(domain.low, domain.high, 3).forEach(function (tick) {
      var y = yScale(tick);
      svg.appendChild(svgEl("line", {
        x1: margin.left, y1: y, x2: width - margin.right, y2: y, class: "chart-grid"
      }));
      svgText(svg, margin.left - 7, y + 3, fmtAxis(tick, options.format), { "text-anchor": "end" });
    });
    // x ticks
    monthTickIndices().forEach(function (index) {
      var x = xScale(index);
      svg.appendChild(svgEl("line", {
        x1: x, y1: margin.top, x2: x, y2: height - margin.bottom, class: "chart-grid", opacity: "0.55"
      }));
      svgText(svg, x, height - 7, "T" + (index + 1), { "text-anchor": "middle" });
    });
    svg.appendChild(svgEl("line", {
      x1: margin.left, y1: height - margin.bottom,
      x2: width - margin.right, y2: height - margin.bottom, class: "chart-axis-line"
    }));
    var selected = clamp(state.month - 1, 0, MONTHS - 1);
    var zeroY = yScale(clamp(0, domain.low, domain.high));
    series.forEach(function (one) {
      var values = one.values.slice(0, selected + 1);
      if (!values.length) return;
      if (options.fill !== false && series.length === 1) {
        var area = "M " + xScale(0) + " " + zeroY;
        values.forEach(function (value, index) { area += " L " + xScale(index) + " " + yScale(num(value)); });
        area += " L " + xScale(values.length - 1) + " " + zeroY + " Z";
        svg.appendChild(svgEl("path", { d: area, fill: one.color, opacity: "0.10" }));
      }
      if (values.length > 1) {
        var path = values.map(function (value, index) {
          return (index === 0 ? "M " : "L ") + xScale(index) + " " + yScale(num(value));
        }).join(" ");
        svg.appendChild(svgEl("path", {
          d: path, fill: "none", stroke: one.color, "stroke-width": "2",
          "stroke-linecap": "round", "stroke-linejoin": "round"
        }));
      }
      var current = num(one.values[selected]);
      var point = svgEl("circle", {
        cx: xScale(selected), cy: yScale(current), r: "4",
        fill: one.color, class: "chart-marker"
      });
      svg.appendChild(point);
    });
    var crosshair = svgEl("line", {
      x1: 0, y1: margin.top, x2: 0, y2: height - margin.bottom,
      class: "chart-crosshair", visibility: "hidden"
    });
    svg.appendChild(crosshair);
    var hoverDots = series.map(function (one) {
      var dot = svgEl("circle", {
        cx: 0, cy: 0, r: "3.5", fill: one.color, stroke: "var(--surface)",
        "stroke-width": "2", visibility: "hidden", "pointer-events": "none"
      });
      svg.appendChild(dot);
      return dot;
    });
    var overlay = svgEl("rect", {
      x: margin.left, y: margin.top, width: plotWidth, height: plotHeight,
      fill: "transparent", style: "cursor:crosshair"
    });
    svg.appendChild(overlay);
    host.innerHTML = "";
    host.appendChild(svg);
    var currentValue = num(series[0].values[selected]);
    setHostAria(host, options.label + "折线图，当前 T" + state.month + "：" + fmtValue(currentValue, options.format) + "，点击图表选择月份");
    function nearestFromEvent(event) {
      var rect = svg.getBoundingClientRect();
      var x = (event.clientX - rect.left) * (width / Math.max(rect.width, 1));
      if (MONTHS <= 1) return 0;
      return clamp(Math.round((x - margin.left) / plotWidth * (MONTHS - 1)), 0, MONTHS - 1);
    }
    function pointerMove(event) {
      var index = nearestFromEvent(event);
      var x = xScale(index);
      crosshair.setAttribute("x1", String(x));
      crosshair.setAttribute("x2", String(x));
      crosshair.setAttribute("visibility", "visible");
      series.forEach(function (one, i) {
        hoverDots[i].setAttribute("cx", String(x));
        hoverDots[i].setAttribute("cy", String(yScale(num(one.values[index]))));
        hoverDots[i].setAttribute("visibility", "visible");
      });
      showTooltip(event, '<div class="tt-head">T' + (index + 1) + ' · 第 ' + (index + 1) + ' 月</div>' +
        tooltipRows(series, index) + '<div class="tt-hint">点击锁定这个月份</div>');
    }
    function pointerLeave() {
      crosshair.setAttribute("visibility", "hidden");
      hoverDots.forEach(function (dot) { dot.setAttribute("visibility", "hidden"); });
      hideTooltip();
    }
    overlay.addEventListener("pointermove", pointerMove);
    overlay.addEventListener("pointerleave", pointerLeave);
    overlay.addEventListener("click", function (event) {
      selectMonth(nearestFromEvent(event) + 1);
    });
  }

  function drawMiniChart(host, values, options) {
    var width = Math.max(120, Math.round(host.getBoundingClientRect().width || host.clientWidth || 180));
    var height = Math.max(42, Math.round(host.getBoundingClientRect().height || 55));
    var margin = { left: 3, right: 8, top: 7, bottom: 6 };
    var plotWidth = Math.max(10, width - margin.left - margin.right);
    var plotHeight = Math.max(10, height - margin.top - margin.bottom);
    var domain = paddedDomain(values, false);
    var xScale = function (index) {
      return MONTHS <= 1 ? margin.left + plotWidth / 2 : margin.left + (index / (MONTHS - 1)) * plotWidth;
    };
    var yScale = function (value) {
      return margin.top + (domain.high - value) / (domain.high - domain.low) * plotHeight;
    };
    var svg = svgEl("svg", {
      viewBox: "0 0 " + width + " " + height, width: "100%", height: String(height),
      "aria-hidden": "true", focusable: "false"
    });
    var selected = clamp(state.month - 1, 0, MONTHS - 1);
    var visible = values.slice(0, selected + 1);
    if (visible.length) {
      var area = "M " + xScale(0) + " " + (height - margin.bottom);
      visible.forEach(function (value, index) {
        area += " L " + xScale(index) + " " + yScale(num(value));
      });
      area += " L " + xScale(visible.length - 1) + " " + (height - margin.bottom) + " Z";
      svg.appendChild(svgEl("path", { d: area, fill: options.color, opacity: "0.08" }));
      if (visible.length > 1) {
        var path = visible.map(function (value, index) {
          return (index === 0 ? "M " : "L ") + xScale(index) + " " + yScale(num(value));
        }).join(" ");
        svg.appendChild(svgEl("path", {
          d: path, fill: "none", stroke: options.color, "stroke-width": "1.7",
          "stroke-linecap": "round", "stroke-linejoin": "round"
        }));
      }
      svg.appendChild(svgEl("circle", {
        cx: xScale(selected), cy: yScale(num(values[selected])), r: "3.2",
        fill: options.color, class: "chart-marker"
      }));
    }
    var crosshair = svgEl("line", {
      x1: 0, y1: margin.top, x2: 0, y2: height - margin.bottom,
      class: "chart-crosshair", visibility: "hidden"
    });
    svg.appendChild(crosshair);
    var hoverDot = svgEl("circle", {
      cx: 0, cy: 0, r: "3", fill: options.color, stroke: "var(--surface)",
      "stroke-width": "2", visibility: "hidden", "pointer-events": "none"
    });
    svg.appendChild(hoverDot);
    var overlay = svgEl("rect", {
      x: margin.left, y: 0, width: plotWidth, height: height,
      fill: "transparent", style: "cursor:crosshair"
    });
    svg.appendChild(overlay);
    host.innerHTML = "";
    host.appendChild(svg);
    setHostAria(host, options.label + "小图，当前 T" + state.month + "：" + fmtValue(values[selected], options.format) + "，点击选择月份");
    function nearestFromEvent(event) {
      var rect = svg.getBoundingClientRect();
      var x = (event.clientX - rect.left) * (width / Math.max(rect.width, 1));
      if (MONTHS <= 1) return 0;
      return clamp(Math.round((x - margin.left) / plotWidth * (MONTHS - 1)), 0, MONTHS - 1);
    }
    function pointerMove(event) {
      var index = nearestFromEvent(event);
      var x = xScale(index);
      crosshair.setAttribute("x1", String(x));
      crosshair.setAttribute("x2", String(x));
      crosshair.setAttribute("visibility", "visible");
      hoverDot.setAttribute("cx", String(x));
      hoverDot.setAttribute("cy", String(yScale(num(values[index]))));
      hoverDot.setAttribute("visibility", "visible");
      showTooltip(event, '<div class="tt-head">T' + (index + 1) + ' · ' + escapeHtml(options.label) + '</div>' +
        '<div class="tt-row"><span class="tt-key"><i style="--tt-color:' + options.color + '"></i>' +
        escapeHtml(options.seriesLabel || options.label) + '</span><strong>' +
        fmtValue(values[index], options.format) + '</strong></div>' +
        '<div class="tt-hint">点击锁定这个月份</div>');
    }
    function pointerLeave() {
      crosshair.setAttribute("visibility", "hidden");
      hoverDot.setAttribute("visibility", "hidden");
      hideTooltip();
    }
    overlay.addEventListener("pointermove", pointerMove);
    overlay.addEventListener("pointerleave", pointerLeave);
    overlay.addEventListener("click", function (event) {
      selectMonth(nearestFromEvent(event) + 1);
    });
  }

  function drawSparkline(host, values, color) {
    var width = Math.max(80, Math.round(host.getBoundingClientRect().width || host.clientWidth || 180));
    var height = 27;
    var margin = { left: 2, right: 6, top: 3, bottom: 3 };
    var plotWidth = Math.max(5, width - margin.left - margin.right);
    var plotHeight = Math.max(5, height - margin.top - margin.bottom);
    var domain = paddedDomain(values, false);
    var selected = clamp(state.month - 1, 0, MONTHS - 1);
    var visible = values.slice(0, selected + 1);
    var svg = svgEl("svg", {
      viewBox: "0 0 " + width + " " + height, width: "100%", height: String(height),
      "aria-hidden": "true", focusable: "false"
    });
    if (visible.length > 1) {
      var path = visible.map(function (value, index) {
        var x = MONTHS <= 1 ? margin.left + plotWidth / 2 : margin.left + (index / (MONTHS - 1)) * plotWidth;
        var y = margin.top + (domain.high - num(value)) / (domain.high - domain.low) * plotHeight;
        return (index === 0 ? "M " : "L ") + x + " " + y;
      }).join(" ");
      svg.appendChild(svgEl("path", {
        d: path, fill: "none", stroke: color, "stroke-width": "1.4",
        "stroke-linecap": "round", "stroke-linejoin": "round", opacity: "0.8"
      }));
    }
    if (visible.length) {
      var lastX = MONTHS <= 1 ? margin.left + plotWidth / 2 : margin.left + (selected / (MONTHS - 1)) * plotWidth;
      var lastY = margin.top + (domain.high - num(values[selected])) / (domain.high - domain.low) * plotHeight;
      svg.appendChild(svgEl("circle", {
        cx: lastX, cy: lastY, r: "2.5", fill: color, stroke: "var(--surface)", "stroke-width": "1.5"
      }));
    }
    host.innerHTML = "";
    host.appendChild(svg);
  }

  function mountCharts() {
    Array.prototype.forEach.call(document.querySelectorAll('.chart-host[data-chart="line"]'), function (host) {
      try {
        var metric = host.getAttribute("data-metric");
        var meta = LINE_META[metric];
        if (!meta) return;
        var values = scalarSeries(metric);
        var series = [{ label: meta.label, values: values, color: meta.color, format: meta.format }];
        drawLineChart(host, series, {
          label: meta.label, format: meta.format, includeZero: meta.includeZero,
          height: Number(host.getAttribute("data-height")) || 156
        });
      } catch (error) {
        host.innerHTML = '<div class="chart-empty">图表不可用</div>';
        reportError("宏观图渲染失败：" + error.message);
      }
    });
    Array.prototype.forEach.call(document.querySelectorAll('.chart-host[data-chart="multi"]'), function (host) {
      try {
        var keys = (host.getAttribute("data-metrics") || "").split(",").filter(Boolean);
        var series = keys.map(function (key) {
          var meta = MULTI_META[key];
          return {
            label: meta ? meta.label : key,
            values: scalarSeries(key),
            color: meta ? meta.color : "var(--series-3)",
            format: meta ? meta.format : "money"
          };
        }).filter(function (one) { return one.values.length; });
        if (!series.length) throw new Error("没有可用序列");
        drawLineChart(host, series, {
          label: "趋势", format: series[0].format || "money", includeZero: true,
          height: Number(host.getAttribute("data-height")) || 228, fill: false
        });
      } catch (error) {
        host.innerHTML = '<div class="chart-empty">图表不可用</div>';
        reportError("政府/货币图渲染失败：" + error.message);
      }
    });
    Array.prototype.forEach.call(document.querySelectorAll('.chart-host[data-chart="mini"]'), function (host) {
      try {
        var kind = host.getAttribute("data-kind");
        var key = host.getAttribute("data-key");
        if (kind === "price") {
          drawMiniChart(host, goodSeries("prices", key), {
            label: goodLabel(key) + "价格", seriesLabel: "参考价",
            color: "var(--series-3)", format: "price"
          });
        } else {
          drawMiniChart(host, goodSeries("production", key), {
            label: goodLabel(key) + "产量", seriesLabel: "产量",
            color: "var(--series-1)", format: "qty"
          });
        }
      } catch (error) {
        host.innerHTML = '<div class="chart-empty">—</div>';
        reportError("小图渲染失败：" + error.message);
      }
    });
    Array.prototype.forEach.call(document.querySelectorAll("[data-spark]"), function (host) {
      try {
        var metric = host.getAttribute("data-spark");
        drawSparkline(host, scalarSeries(metric), host.getAttribute("data-color") || "var(--series-1)");
      } catch (error) {
        host.innerHTML = "";
        reportError("sparkline 渲染失败：" + error.message);
      }
    });
  }

  /* ------------------------------------------------------------------ */
  /* 图表卡片与各区块 HTML                                              */
  /* ------------------------------------------------------------------ */
  function renderMacroGrid(index) {
    var previous = index > 0 ? index - 1 : null;
    var order = ["gdp", "investment", "unemployment_rate", "profit_rate"];
    refs.macroGrid.innerHTML = order.map(function (metric) {
      var meta = LINE_META[metric];
      var current = scalarAt(metric, index);
      var previousValue = previous == null ? null : scalarAt(metric, previous);
      var mode = metric === "gdp" || metric === "investment" ? "pct" : "pp";
      return '<article class="chart-box">' +
        '<div class="chart-box-head"><div><span class="chart-box-title">' + escapeHtml(meta.label) +
        '</span><span class="chart-box-unit">' + escapeHtml(meta.unit) + '</span></div>' +
        '<strong class="chart-current">' + fmtValue(current, meta.format) + '</strong></div>' +
        '<div class="chart-box-sub">' + escapeHtml(previous == null ? "起始月" : deltaText(current, previousValue, mode)) +
        ' · 选中 T' + state.month + '</div>' +
        '<div class="chart-host" data-chart="line" data-metric="' + metric + '" data-height="145"></div>' +
        '</article>';
    }).join("");
  }

  function renderGovPanel(index) {
    var series = [
      { key: "government_debt", label: "政府债务", color: "var(--series-1)", format: "money" },
      { key: "central_bank_money", label: "央行货币", color: "var(--series-2)", format: "money" }
    ];
    refs.govLegend.innerHTML = series.map(function (one) {
      return '<span class="legend-item"><span class="legend-key" style="--legend-color:' + one.color + '"></span>' +
        escapeHtml(one.label) + ' <span class="legend-value">' + fmtValue(scalarAt(one.key, index), one.format) + '</span></span>';
    }).join("");
    var gdp = scalarAt("gdp", index);
    var deficit = scalarAt("government_deficit", index);
    var regime = regimeMeta();
    refs.govFacts.innerHTML = [
      ["赤字 / GDP", fmtPct(gdp > 1e-9 ? deficit / gdp : 0, 2)],
      ["政府现金", fmtCompact(scalarAt("government_cash", index)) + " 元"],
      ["银行中介", regime.bank_intermediation ? "开启" : "关闭"]
    ].map(function (fact) {
      return '<div class="fact"><span>' + escapeHtml(fact[0]) + '</span><strong title="' +
        escapeHtml(fact[1]) + '">' + escapeHtml(fact[1]) + '</strong></div>';
    }).join("");
  }

  function bandState(price, floor, ceiling) {
    if (!(ceiling > floor) || ceiling <= 0) return { text: "未设带宽", position: 0.5, alert: false };
    var epsilon = Math.max(1e-9, Math.abs(ceiling) * 1e-6);
    if (price >= ceiling - epsilon) return { text: "触顶", position: 1, alert: true };
    if (price <= floor + epsilon) return { text: "触底", position: 0, alert: true };
    return { text: "带内", position: clamp((price - floor) / (ceiling - floor), 0, 1), alert: false };
  }

  function renderPriceGrid(index) {
    refs.priceGrid.innerHTML = GOODS.map(function (good) {
      var price = goodAt("prices", good.id, index);
      var floor = goodAt("price_floors", good.id, index);
      var ceiling = goodAt("price_ceilings", good.id, index);
      var band = bandState(price, floor, ceiling);
      var previous = index > 0 ? goodAt("prices", good.id, index - 1) : null;
      var change = previous == null ? "起始月" : deltaText(price, previous, "pct");
      var alert = band.alert ? ' · <span class="mini-alert">' + band.text + '</span>' : "";
      return '<article class="mini-card">' +
        '<div class="mini-head"><span class="mini-title" title="' + escapeHtml(good.label) + '">' + escapeHtml(good.label) + '</span>' +
        '<span class="mini-value">' + fmtNum(price, 2) + '</span></div>' +
        '<div class="mini-sub" title="价格带下轨 ' + escapeHtml(fmtNum(floor, 2)) + ' · 上轨 ' + escapeHtml(fmtNum(ceiling, 2)) + '">' +
        fmtNum(floor, 2) + '–' + fmtNum(ceiling, 2) + ' · ' + escapeHtml(change) + alert + '</div>' +
        '<div class="chart-host mini-chart" data-chart="mini" data-kind="price" data-key="' + escapeHtml(good.id) + '"></div>' +
        '</article>';
    }).join("");
  }

  function renderProductionGrid(index) {
    refs.productionGrid.innerHTML = GOODS.map(function (good) {
      var output = goodAt("production", good.id, index);
      var streak = goodAt("zero_output_streak", good.id, index);
      var industries = INDUSTRIES.filter(function (industry) { return industry.output === good.id; });
      var title = (industries.length ? industries.map(function (industry) { return industry.label; }).join("/") + " · " : "") + good.label;
      var status = streak >= 1 ? '<span class="mini-alert">零产出 ' + fmtInt(streak) + ' 月</span>' : "正常";
      return '<article class="mini-card">' +
        '<div class="mini-head"><span class="mini-title" title="' + escapeHtml(title) + '">' + escapeHtml(title) + '</span>' +
        '<span class="mini-value">' + fmtNum(output, 2) + '</span></div>' +
        '<div class="mini-sub" title="连续零产出 ' + fmtInt(streak) + ' 月">' + status + '</div>' +
        '<div class="chart-host mini-chart" data-chart="mini" data-kind="production" data-key="' + escapeHtml(good.id) + '"></div>' +
        '</article>';
    }).join("");
  }

  /* ------------------------------------------------------------------ */
  /* 诊断表                                                              */
  /* ------------------------------------------------------------------ */
  function panel(title, kicker, note, body, wide) {
    return '<article class="panel' + (wide ? ' wide' : '') + '">' +
      '<header class="panel-head"><div class="panel-title-wrap"><span class="kicker">' + escapeHtml(kicker) + '</span>' +
      '<h2>' + escapeHtml(title) + '</h2>' + (note ? '<p class="panel-sub">' + note + '</p>' : '') +
      '</div></header><div class="panel-body">' + body + '</div></article>';
  }

  function renderGoodsTable(index) {
    var rows = GOODS.map(function (good) {
      var price = goodAt("prices", good.id, index);
      var floor = goodAt("price_floors", good.id, index);
      var ceiling = goodAt("price_ceilings", good.id, index);
      var streak = goodAt("zero_output_streak", good.id, index);
      var band = bandState(price, floor, ceiling);
      var zeroBadge = streak > 0 ?
        '<span class="badge ' + (streak >= 3 ? "bad" : "warn") + '">零产出 ' + fmtInt(streak) + ' 月</span>' :
        '<span class="badge ok">正常</span>';
      var bandBadge = band.alert ? ' <span class="badge ' + (band.text === "触底" ? "bad" : "warn") + '">' + band.text + '</span>' : "";
      return '<tr>' +
        '<td class="name-cell">' + escapeHtml(good.label) + '<small>' + escapeHtml(good.id) + '</small></td>' +
        '<td>' + fmtNum(goodAt("production", good.id, index), 2) + '</td>' +
        '<td>' + fmtNum(goodAt("demand", good.id, index), 2) + '</td>' +
        '<td>' + fmtNum(goodAt("supply", good.id, index), 2) + '</td>' +
        '<td>' + fmtNum(goodAt("volumes", good.id, index), 2) + '</td>' +
        '<td class="num-strong">' + fmtNum(price, 2) + bandBadge + '</td>' +
        '<td class="muted">' + fmtNum(floor, 2) + '</td>' +
        '<td class="muted">' + fmtNum(ceiling, 2) + '</td>' +
        '<td>' + zeroBadge + '</td>' +
        '</tr>';
    }).join("");
    return '<div class="table-wrap"><table>' +
      '<thead><tr><th>商品</th><th>产量</th><th>需求</th><th>供给</th><th>成交</th><th>价格</th><th>价格下轨</th><th>价格上轨</th><th>连续零产出</th></tr></thead>' +
      '<tbody>' + rows + '</tbody></table></div>' +
      '<p class="table-foot">产量 / 需求 / 供给 / 成交为当月流量；价格与上下轨均为引擎参考价字段。商品行由 stats 的 goods keys 动态生成。</p>';
  }

  function renderProfitTable(index) {
    var revenue = scalarAt("revenue", index);
    var inputCosts = scalarAt("input_costs", index);
    var wages = scalarAt("wages", index);
    var interest = scalarAt("interest", index);
    var depreciation = scalarAt("depreciation", index);
    var profit = scalarAt("profit", index);
    var profitRate = scalarAt("profit_rate", index);
    var capital = scalarAt("capital_stock", index);
    var check = revenue - inputCosts - wages - interest - depreciation - profit;
    var rows = [
      ["营业收入", revenue, "money", false],
      ["中间投入", -inputCosts, "money", false],
      ["工资", -wages, "money", false],
      ["利息", -interest, "money", false],
      ["折旧", -depreciation, "money", false],
      ["经济利润", profit, "money", true]
    ];
    function share(value) {
      if (Math.abs(revenue) < 1e-9) return "—";
      return fmtPct(value / revenue, 1);
    }
    var html = rows.map(function (row) {
      var value = row[1];
      var formatted = fmtSigned(value, row[2]);
      var cls = row[3] ? "num-strong " + (value < 0 ? "neg" : "pos") : (value < 0 ? "neg" : "");
      return '<tr' + (row[3] ? ' class="total-row"' : '') + '><td class="name-cell">' + escapeHtml(row[0]) + '</td>' +
        '<td class="' + cls + '">' + formatted + '</td><td class="muted">' + share(value) + '</td></tr>';
    }).join("");
    var checkBadge = Math.abs(check) <= 0.01 ? '<span class="badge ok">恒等式闭合</span>' :
      '<span class="badge bad">残差 ' + fmtNum(check, 4) + '</span>';
    return '<div class="table-wrap"><table class="kv-table">' +
      '<thead><tr><th>利润表项目</th><th>金额（元）</th><th>占收入</th></tr></thead><tbody>' + html + '</tbody></table></div>' +
      '<p class="table-foot">收入 − 投入 − 工资 − 利息 − 折旧 = 利润；' + checkBadge +
      ' · 利润率 ' + fmtPct(profitRate, 4) + ' · 资本存量 ' + fmtInt(capital) + ' 元。</p>';
  }

  function renderIndustryTable(index) {
    var totalFirms = 0, totalWorkers = 0, totalProjects = 0;
    var rows = INDUSTRIES.map(function (industry) {
      var firms = industryAt("firms", industry.id, index);
      var workers = industryAt("workers_by_industry", industry.id, index);
      var projects = industryAt("active_projects", industry.id, index);
      totalFirms += firms; totalWorkers += workers; totalProjects += projects;
      var output = industry.output && GOOD_BY_ID[industry.output] ? goodLabel(industry.output) : "—";
      var production = industry.output ? fmtNum(goodAt("production", industry.output, index), 2) : "—";
      return '<tr><td class="name-cell">' + escapeHtml(industry.label) + '<small>' + escapeHtml(industry.id) + '</small></td>' +
        '<td>' + escapeHtml(output) + '</td><td>' + fmtInt(firms) + '</td><td>' + fmtInt(workers) + '</td>' +
        '<td>' + fmtInt(projects) + '</td><td class="num-strong">' + production + '</td></tr>';
    }).join("");
    return '<div class="table-wrap"><table>' +
      '<thead><tr><th>行业</th><th>产出商品</th><th>企业数</th><th>工人数</th><th>活跃项目</th><th>产量</th></tr></thead>' +
      '<tbody>' + rows + '<tr class="total-row"><td>合计</td><td>—</td><td>' + fmtInt(totalFirms) +
      '</td><td>' + fmtInt(totalWorkers) + '</td><td>' + fmtInt(totalProjects) + '</td><td>—</td></tr></tbody></table></div>' +
      '<p class="table-foot">行业行从 <code>firms</code> / <code>workers_by_industry</code> / <code>active_projects</code> 的 keys 合并，新增行业会自动出现。</p>';
  }

  function renderBankTable(index) {
    var cash = scalarAt("bank_cash", index);
    var loans = scalarAt("bank_loans", index);
    var deposits = scalarAt("bank_deposits", index);
    var equity = scalarAt("bank_equity", index);
    var writeOffs = scalarAt("bank_write_offs", index);
    var moneyTotal = scalarAt("money_total", index);
    var initial = num(regimeMeta().money_initial, 0);
    var drift = moneyTotal - initial;
    var equityBadge = equity < -0.01 ? ' <span class="badge bad">为负</span>' : '';
    var rows = [
      ["银行现金", "资产", fmtInt(cash), ""],
      ["银行贷款", "资产", fmtInt(loans), ""],
      ["银行存款", "负债", fmtInt(deposits), ""],
      ["银行权益（现金 + 贷款 − 存款）", "权益", fmtInt(equity) + equityBadge, equity < -0.01 ? "neg" : ""],
      ["坏账核销累计", "备查", fmtInt(writeOffs), ""],
      ["货币总量", "宏观", fmtInt(moneyTotal), ""],
      ["期初货币", "宏观", fmtInt(initial), ""],
      ["货币漂移（总量 − 期初）", "备查", fmtSigned(drift, "money"), Math.abs(drift) > 0.01 ? "neg" : ""]
    ];
    var body = rows.map(function (row) {
      return '<tr><td class="name-cell">' + escapeHtml(row[0]) + '</td><td class="muted">' + row[1] +
        '</td><td class="' + row[3] + '">' + row[2] + '</td></tr>';
    }).join("");
    return '<div class="table-wrap"><table class="kv-table">' +
      '<thead><tr><th>科目</th><th>类别</th><th>金额（元）</th></tr></thead><tbody>' + body + '</tbody></table></div>' +
      '<p class="table-foot">权益为‘现金 + 贷款 − 存款’的测算值；信用货币制度下货币漂移是央行创造的货币，不代表会计错误。</p>';
  }

  function renderGovernmentTable(index) {
    var regime = regimeMeta();
    var rows = [
      ["政府现金", "存量", fmtInt(scalarAt("government_cash", index))],
      ["税收收入", "月流量", fmtSigned(scalarAt("government_tax_revenue", index), "money")],
      ["转移支付 / 失业救济", "月流量", fmtSigned(scalarAt("government_transfers", index), "money")],
      ["政府采购支出", "月流量", fmtSigned(scalarAt("government_spending", index), "money")],
      ["公共投资预算", "月流量", fmtSigned(scalarAt("government_public_investment_budget", index), "money")],
      ["国债利息", "月流量", fmtSigned(scalarAt("government_interest_paid", index), "money")],
      ["财政赤字（负为盈余）", "月流量", fmtSigned(scalarAt("government_deficit", index), "money")],
      ["政府债务", "存量", fmtInt(scalarAt("government_debt", index))],
      ["央行货币", "存量", fmtInt(scalarAt("central_bank_money", index))],
      ["就业保障人数", "人数", fmtInt(scalarAt("government_jg_workers", index)) + " 人"]
    ];
    var body = rows.map(function (row) {
      return '<tr><td class="name-cell">' + escapeHtml(row[0]) + '</td><td class="muted">' + escapeHtml(row[1]) +
        '</td><td>' + row[2] + '</td></tr>';
    }).join("");
    var note = regime.policy_regime === "classical" ? "古典制度无政府模块，全部政府账户为零。" : "";
    return '<div class="table-wrap"><table class="kv-table">' +
      '<thead><tr><th>预算项目</th><th>口径</th><th>数值</th></tr></thead><tbody>' + body + '</tbody></table></div>' +
      '<p class="table-foot">' + (note ? escapeHtml(note) + ' ' : '') + '税收/支出/赤字为月度流量，债务与央行货币为存量。</p>';
  }

  function renderInventoryTable(index) {
    var totalValue = 0;
    var rows = GOODS.map(function (good) {
      var inventory = goodAt("inventory", good.id, index);
      var demand = goodAt("demand", good.id, index);
      var price = goodAt("prices", good.id, index);
      var value = inventory * price;
      totalValue += value;
      var coverage = demand > 1e-9 ? fmtMonths(inventory / demand) : "无需求";
      return '<tr><td class="name-cell">' + escapeHtml(good.label) + '<small>' + escapeHtml(good.id) + '</small></td>' +
        '<td>' + fmtNum(inventory, 2) + '</td><td>' + fmtNum(demand, 2) + '</td>' +
        '<td>' + coverage + '</td><td>' + fmtInt(value) + '</td></tr>';
    }).join("");
    return '<div class="table-wrap"><table>' +
      '<thead><tr><th>商品</th><th>库存量</th><th>本月需求</th><th>覆盖月数</th><th>估值（元）</th></tr></thead>' +
      '<tbody>' + rows + '<tr class="total-row"><td>合计</td><td>—</td><td>—</td><td>—</td><td>' +
      fmtInt(totalValue) + '</td></tr></tbody></table></div>' +
      '<p class="table-foot">覆盖月数 = 库存 / 本月需求；需求为 0 时显示‘无需求’。估值为库存 × 当月参考价。</p>';
  }

  function renderBandTable(index) {
    var rows = GOODS.map(function (good) {
      var price = goodAt("prices", good.id, index);
      var floor = goodAt("price_floors", good.id, index);
      var ceiling = goodAt("price_ceilings", good.id, index);
      var band = bandState(price, floor, ceiling);
      var badge = band.alert ? ' <span class="badge ' + (band.text === "触底" ? "bad" : "warn") + '">' + band.text + '</span>' : "";
      return '<div class="band-row">' +
        '<span class="band-name" title="' + escapeHtml(good.id) + '">' + escapeHtml(good.label) + '</span>' +
        '<div class="band-meter" title="下轨 ' + escapeHtml(fmtNum(floor, 2)) + ' · 现价 ' + escapeHtml(fmtNum(price, 2)) + ' · 上轨 ' + escapeHtml(fmtNum(ceiling, 2)) + '">' +
        '<span class="band-dot" style="left:' + (band.position * 100).toFixed(2) + '%"></span></div>' +
        '<span class="band-nums"><span class="floor">' + fmtNum(floor, 2) + '</span> · <strong>' +
        fmtNum(price, 2) + '</strong>' + badge + ' · <span class="ceil">' + fmtNum(ceiling, 2) + '</span></span>' +
        '</div>';
    }).join("");
    return '<div class="band-list">' + rows + '</div>' +
      '<p class="table-foot">圆点表示当月价格在下轨—上轨之间的位置；触顶/触底是实时价格带状态。</p>';
  }

  function renderComparisonTable(index) {
    if (!COMPARE) {
      var message = COMPARE_STATE === "error"
        ? "三制度对比加载失败。可以重试；默认制度仍可正常查看。"
        : "后台正在运行另外两个制度并整理对比数据；首次完整对比通常需要约 1–2 分钟。";
      var retry = COMPARE_STATE === "error"
        ? '<button class="step-btn" type="button" data-retry-compare>重试对比</button>'
        : "";
      return '<div class="compare-pending"><span class="mini-spinner" aria-hidden="true"></span><span>' +
        escapeHtml(message) + '</span>' + retry + '</div>' +
        '<p class="table-foot">对比接口：<code>/api/compare?months=' + MONTHS + '&amp;seed=' + API_SEED + '</code></p>';
    }
    var compareMonths = Number(COMPARE.meta && COMPARE.meta.months) || MONTHS;
    var compareIndex = clamp(index, 0, compareMonths - 1);
    var regimes = (COMPARE.meta && Array.isArray(COMPARE.meta.regimes) && COMPARE.meta.regimes.length)
      ? COMPARE.meta.regimes : REGIMES;
    var rows = regimes.map(function (regime) {
      var values = {
        alive: compareValue(regime.id, "alive", compareIndex),
        unemployment: compareValue(regime.id, "unemployment_rate", compareIndex),
        gdp: compareValue(regime.id, "gdp", compareIndex),
        investment: compareValue(regime.id, "investment", compareIndex),
        profitRate: compareValue(regime.id, "profit_rate", compareIndex),
        debt: compareValue(regime.id, "government_debt", compareIndex),
        centralBank: compareValue(regime.id, "central_bank_money", compareIndex),
        jg: compareValue(regime.id, "government_jg_workers", compareIndex),
        food: compareValue(regime.id, "food_reserve", compareIndex),
        population: compareValue(regime.id, "population", compareIndex),
        dependency: compareValue(regime.id, "dependency_ratio", compareIndex),
        pension: compareValue(regime.id, "pension_fund", compareIndex)
      };
      var loaded = !!RUNS[regime.id];
      var moneyLabel = regime.money_regime === "credit" ? "信用货币" : "金本位";
      return '<tr data-compare-regime="' + escapeHtml(regime.id) + '" tabindex="0" class="' +
        (regime.id === state.regime ? "active-regime" : "") + '" title="' +
        escapeHtml(loaded ? "切换到 " + regime.name : "运行并切换到 " + regime.name) + '">' +
        '<td class="name-cell">' + escapeHtml(regime.label) + '<small>' + escapeHtml(moneyLabel) +
        (loaded ? "" : " · 未载入") + '</small></td>' +
        '<td>' + fmtInt(values.alive) + '</td>' +
        '<td>' + fmtPct(values.unemployment, 1) + '</td>' +
        '<td>' + fmtInt(values.gdp) + '</td>' +
        '<td>' + fmtInt(values.investment) + '</td>' +
        '<td class="' + ((values.profitRate || 0) < 0 ? "neg" : "pos") + '">' + fmtPct(values.profitRate, 2) + '</td>' +
        '<td>' + fmtInt(values.debt) + '</td>' +
        '<td>' + fmtInt(values.centralBank) + '</td>' +
        '<td>' + fmtInt(values.jg) + '</td>' +
        '<td>' + fmtNum(values.food, 1) + '</td>' +
        '<td>' + fmtInt(values.population) + '</td>' +
        '<td>' + fmtPct(values.dependency, 1) + '</td>' +
        '<td>' + fmtInt(values.pension) + '</td>' +
        '</tr>';
    }).join("");
    return '<div class="table-wrap"><table class="compare-table">' +
      '<thead><tr><th>制度</th><th>存活</th><th>失业率</th><th>GDP</th><th>投资</th><th>资本主义利润率</th><th>政府债务</th><th>央行货币</th><th>就业保障</th><th>粮食储备</th><th>人口</th><th>抚养比</th><th>养老金基金</th></tr></thead>' +
      '<tbody>' + rows + '</tbody></table></div>' +
      '<p class="table-foot">来自轻量对比接口 <code>/api/compare</code>，与当前时间轴同步；点击行可切换到该制度（未载入时首次会运行引擎）。</p>';
  }

  function collectIssues(index) {
    var issues = [];
    warningsAt(index).forEach(function (text) {
      issues.push({ level: "warning", tag: "引擎告警", text: text });
    });
    GOODS.forEach(function (good) {
      var streak = goodAt("zero_output_streak", good.id, index);
      if (streak >= 3) {
        issues.push({ level: "warning", tag: "零产出", text: good.label + "已连续 " + fmtInt(streak) + " 个月产量为 0" });
      }
    });
    var equity = scalarAt("bank_equity", index);
    if (equity < -0.01) {
      issues.push({ level: "critical", tag: "银行权益", text: "银行权益测算为负（现金 + 贷款 − 存款 = " + fmtInt(equity) + " 元），需检查银行资产负债表" });
    }
    var regime = regimeMeta();
    var moneyTotal = scalarAt("money_total", index);
    var initial = num(regime.money_initial);
    if (regime.money_regime !== "credit" && Math.abs(moneyTotal - initial) > 0.01) {
      issues.push({ level: "critical", tag: "货币", text: "金本位货币漂移：总量 " + fmtInt(moneyTotal) + " ≠ 期初 " + fmtInt(initial) });
    }
    if (scalarAt("investment", index) <= 1e-9) {
      issues.push({ level: "info", tag: "投资", text: "本月投资支出为 0，增长循环可能停滞" });
    }
    if (scalarAt("unemployment_rate", index) > 0.20) {
      issues.push({ level: "info", tag: "失业", text: "失业率 " + fmtPct(scalarAt("unemployment_rate", index), 1) + "，高于 20% 诊断阈值" });
    }
    if (scalarAt("profit", index) < 0) {
      issues.push({ level: "info", tag: "利润", text: "本月经济利润为 " + fmtSigned(scalarAt("profit", index), "money") + " 元，部门整体亏损" });
    }
    GOODS.forEach(function (good) {
      var price = goodAt("prices", good.id, index);
      var floor = goodAt("price_floors", good.id, index);
      var ceiling = goodAt("price_ceilings", good.id, index);
      var band = bandState(price, floor, ceiling);
      if (band.alert) {
        issues.push({ level: "warning", tag: "价格带", text: good.label + "价格 " + fmtNum(price, 2) + " 处于" + band.text + "（下轨 " + fmtNum(floor, 2) + " / 上轨 " + fmtNum(ceiling, 2) + "）" });
      }
    });
    var seen = {};
    return issues.filter(function (issue) {
      var key = issue.level + "|" + issue.tag + "|" + issue.text;
      if (seen[key]) return false;
      seen[key] = true;
      return true;
    }).slice(0, 22);
  }

  function renderIssues(index) {
    var issues = collectIssues(index);
    if (!issues.length) {
      return '<div class="empty-state"><span class="dot" aria-hidden="true"></span>本月没有引擎告警或显著异常。</div>';
    }
    return '<div class="issue-list">' + issues.map(function (issue) {
      var label = issue.level === "critical" ? "异常" : issue.level === "warning" ? "告警" : "提示";
      return '<div class="issue"><span class="issue-tag ' + issue.level + '">' + label + '</span><span>' +
        escapeHtml(issue.text) + '</span></div>';
    }).join("") + '</div>' +
      '<p class="table-foot">“引擎告警”直接来自 stats.warnings；其余项目由当前月份字段派生。最多展示 22 条。</p>';
  }

  function renderDiagnostics(index) {
    refs.diagnosticsGrid.innerHTML = [
      panel("商品诊断", "GOODS", "产量、需求、供给、成交、价格与价格带、连续零产出", renderGoodsTable(index), true),
      panel("利润分解", "PROFIT", "收入 → 中间投入 → 工资 → 利息 → 折旧 → 利润", renderProfitTable(index), false),
      panel("行业诊断", "INDUSTRY", "企业数、工人数、活跃项目、产量", renderIndustryTable(index), false),
      panel("银行资产负债表", "BANK", "现金、贷款、存款、权益与坏账", renderBankTable(index), false),
      panel("政府预算", "GOVERNMENT", "税收、转移、支出、赤字、债务、央行货币", renderGovernmentTable(index), false),
      panel("库存", "INVENTORY", "库存量、需求和覆盖月数", renderInventoryTable(index), false),
      panel("价格带上下轨", "PRICE BAND", "现价在下轨与上轨之间的位置", renderBandTable(index), false),
      panel("三制度对比 · 同一月份", "REGIME COMPARE", "三种制度在同一月份的真实输出；点击行切换制度", renderComparisonTable(index), true),
      panel("异常与提示", "ISSUES", "引擎告警与账户一致性检查", renderIssues(index), true)
    ].join("");
  }

  /* ------------------------------------------------------------------ */
  /* 人口与代际                                                          */
  /* ------------------------------------------------------------------ */
  function drawPopulationPyramid(host, index) {
    var buckets = ageBuckets();
    var counts = buckets.map(function (bucket) { return ageAt(bucket, index); });
    var total = counts.reduce(function (a, b) { return a + b; }, 0);
    var totalEl = document.getElementById("pyramid-total");
    if (totalEl) totalEl.textContent = fmtInt(total) + " 人";
    if (!buckets.length) {
      host.innerHTML = '<div class="pyramid-empty">暂无人口数据</div>';
      return;
    }
    var max = Math.max.apply(null, counts.concat([1]));
    host.innerHTML = buckets.slice().reverse().map(function (bucket, reversedIndex) {
      var count = counts[buckets.length - 1 - reversedIndex];
      var width = Math.max(0, Math.min(100, count / max * 100));
      return '<div class="pyramid-row">' +
        '<span class="pyramid-age">' + escapeHtml(bucket) + '</span>' +
        '<div class="pyramid-track"><div class="pyramid-bar" style="width:' + width.toFixed(2) + '%"></div></div>' +
        '<span class="pyramid-count">' + fmtInt(count) + '</span>' +
        '</div>';
    }).join("");
  }

  function factRows(items) {
    return items.map(function (item) {
      return '<div class="fact"><span>' + escapeHtml(item[0]) + '</span><strong title="' +
        escapeHtml(item[1]) + '">' + escapeHtml(item[1]) + '</strong></div>';
    }).join("");
  }

  function renderDemoLegend(id, keys, index) {
    var host = document.getElementById(id);
    if (!host) return;
    host.innerHTML = keys.map(function (key) {
      var meta = MULTI_META[key] || { label: key, color: "var(--series-3)", format: "money" };
      return '<span class="legend-item"><span class="legend-key" style="--legend-color:' +
        meta.color + '"></span>' + escapeHtml(meta.label) +
        ' <span class="legend-value">' + fmtValue(scalarAt(key, index), meta.format) +
        '</span></span>';
    }).join("");
  }

  function renderDemography(index) {
    drawPopulationPyramid(document.getElementById("population-pyramid"), index);
    renderDemoLegend("birth-legend", ["births", "deaths"], index);
    renderDemoLegend("dependency-legend", ["dependency_ratio", "old_age_dependency"], index);
    renderDemoLegend("pension-legend", ["pension_revenue", "pension_spending", "pension_fund"], index);
    var facts = document.getElementById("demography-facts");
    if (facts) {
      facts.innerHTML = factRows([
        ["出生 / 死亡", fmtInt(scalarAt("births", index)) + " / " + fmtInt(scalarAt("deaths", index))],
        ["出生率 / 死亡率", fmtPct(scalarAt("birth_rate", index), 2) + " / " + fmtPct(scalarAt("death_rate", index), 2)],
        ["儿童 / 劳动 / 退休", fmtInt(scalarAt("children", index)) + " / " +
          fmtInt(scalarAt("working_age", index)) + " / " + fmtInt(scalarAt("retirees", index))],
        ["平均 / 中位年龄", fmtNum(scalarAt("average_age", index), 1) + " / " +
          fmtNum(scalarAt("median_age", index), 1) + " 岁"],
        ["总 / 老年抚养比", fmtPct(scalarAt("dependency_ratio", index), 1) + " / " +
          fmtPct(scalarAt("old_age_dependency", index), 1)],
        ["养老金领取者", fmtInt(scalarAt("pension_recipients", index)) + " 人"]
      ]);
    }
    var pension = document.getElementById("pension-facts");
    if (pension) {
      pension.innerHTML = factRows([
        ["基金余额", fmtCompact(scalarAt("pension_fund", index)) + " 元"],
        ["本月收入", fmtCompact(scalarAt("pension_revenue", index)) + " 元"],
        ["本月支出", fmtCompact(scalarAt("pension_spending", index)) + " 元"],
        ["本月结余", fmtSigned(scalarAt("pension_balance", index), "money") + " 元"],
        ["缴费", fmtCompact(scalarAt("pension_contributions", index)) + " 元"],
        ["领取者", fmtInt(scalarAt("pension_recipients", index)) + " 人"]
      ]);
    }
  }

  /* ------------------------------------------------------------------ */
  /* 渲染调度                                                            */
  /* ------------------------------------------------------------------ */
  var scheduled = false;
  function scheduleRender() {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(function () {
      scheduled = false;
      try { renderAll(); }
      catch (error) { reportError("渲染失败：" + (error && error.stack || error)); }
    });
  }

  function renderAll() {
    if (!currentRun() || !state.booted) return;
    updateControls();
    var index = clamp(state.month - 1, 0, MONTHS - 1);
    renderKpis(index);
    renderMacroGrid(index);
    renderGovPanel(index);
    renderPriceGrid(index);
    renderProductionGrid(index);
    renderDemography(index);
    renderDiagnostics(index);
    mountCharts();
  }

  function initComparisonDelegates() {
    refs.diagnosticsGrid.addEventListener("click", function (event) {
      var retryCompare = event.target.closest("[data-retry-compare]");
      if (retryCompare) {
        loadCompare();
        return;
      }
      var row = event.target.closest("[data-compare-regime]");
      if (!row || state.pending) return;
      switchRegime(row.getAttribute("data-compare-regime")).catch(function () {});
    });
    refs.diagnosticsGrid.addEventListener("keydown", function (event) {
      if (event.key !== "Enter" && event.key !== " ") return;
      var row = event.target.closest("[data-compare-regime]");
      if (!row || state.pending) return;
      event.preventDefault();
      switchRegime(row.getAttribute("data-compare-regime")).catch(function () {});
    });
  }

  var resizeTimer = null;
  window.addEventListener("resize", function () {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(function () {
      if (!state.booted) return;
      try { mountCharts(); } catch (error) { reportError("窗口缩放重绘失败：" + error.message); }
    }, 120);
  });

  try {
    buildControls();
    updateControls();
    initComparisonDelegates();
    renderRuntimeBadges();
    boot();
  } catch (error) {
    reportError("初始化失败：" + (error && error.stack || error));
    showBoot("初始化失败", "请查看顶部错误横幅，或刷新页面重试。", null);
  }
})();
