// ══════════════════════════════════════════════════════════════════
//  app.js — Deriv Bot Dashboard (Firebase Web)
//  Lê operações do Firestore (coll: "operacoes") e ticks do RTDB
//  (path: "ticks/R_100") e renderiza todos os gráficos via Plotly.
// ══════════════════════════════════════════════════════════════════

// ─── Firebase config ──────────────────────────────────────────────
// IMPORTANTE: substitua YOUR_API_KEY e YOUR_APP_ID pelos valores reais.
// Firebase Console → Configurações do Projeto → Seus Aplicativos → </> Web
const FIREBASE_CONFIG = {
  apiKey:            "AIzaSyB2V6OexEutzvKDvoInBNXFveD_WTfDCCg",
  authDomain:        "standeriv.firebaseapp.com",
  databaseURL:       "https://standeriv-default-rtdb.firebaseio.com",
  projectId:         "standeriv",
  storageBucket:     "standeriv.firebasestorage.app",
  messagingSenderId: "490830442652",
  appId:             "1:490830442652:web:abfb2524f54361bfd03d59",
  measurementId:     "G-CLMQ8LBWL0",
};

const SYMBOL    = "R_100";   // mesmo que config.py → SYMBOL
const MAX_OPS   = 500;       // máximo de operações carregadas
const EMA_FAST  = 9;
const EMA_SLOW  = 21;
const BB_PERIOD = 20;
const BB_STD    = 2.0;

// ─── Estado global ────────────────────────────────────────────────
let allOps   = [];   // Array de operações do Firestore
let allTicks = [];   // Array de ticks do RTDB
let tickN    = 500;  // controlado pelo slider

// ─── Plotly layout base (dark) ────────────────────────────────────
const LAYOUT_BASE = {
  paper_bgcolor: "#161B22",
  plot_bgcolor:  "#0D1117",
  font:  { color: "#8B949E", family: "'Segoe UI', system-ui, sans-serif", size: 12 },
  margin: { t: 20, r: 20, b: 40, l: 50 },
  xaxis: { gridcolor: "#21262D", zerolinecolor: "#30363D" },
  yaxis: { gridcolor: "#21262D", zerolinecolor: "#30363D" },
};
const CONFIG_PLOT = { displayModeBar: false, responsive: true };

// ═══════════════════════════════════════════════════════════════════
//  Indicadores JS (equivalente a indicators.py)
// ═══════════════════════════════════════════════════════════════════

function emaSeries(prices, period) {
  if (prices.length < period) return [];
  const k = 2 / (period + 1);
  const result = new Array(prices.length).fill(null);
  let val = prices[0];
  for (let i = 0; i < prices.length; i++) {
    val = prices[i] * k + val * (1 - k);
    if (i >= period - 1) result[i] = val;
  }
  return result;
}

function bollingerSeries(prices, period = 20, std = 2.0) {
  const mid = [], upper = [], lower = [];
  for (let i = 0; i < prices.length; i++) {
    if (i < period - 1) {
      mid.push(null); upper.push(null); lower.push(null);
      continue;
    }
    const window = prices.slice(i - period + 1, i + 1);
    const mean = window.reduce((a, b) => a + b, 0) / period;
    const variance = window.reduce((a, b) => a + (b - mean) ** 2, 0) / period;
    const sd = Math.sqrt(variance);
    mid.push(mean);
    upper.push(mean + std * sd);
    lower.push(mean - std * sd);
  }
  return { mid, upper, lower };
}

// ═══════════════════════════════════════════════════════════════════
//  Helpers
// ═══════════════════════════════════════════════════════════════════

function fmtUSD(v) {
  const n = Number(v);
  if (isNaN(n)) return "—";
  return (n >= 0 ? "+" : "") + "$" + n.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function fmtPct(v) {
  const n = Number(v);
  return isNaN(n) ? "—" : n.toFixed(1) + "%";
}

function fmtTime(ts) {
  if (!ts) return "—";
  const d = ts instanceof Date ? ts : new Date(ts.seconds ? ts.seconds * 1000 : ts);
  return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function fmtDate(ts) {
  if (!ts) return "—";
  const d = ts instanceof Date ? ts : new Date(ts.seconds ? ts.seconds * 1000 : ts);
  return d.toLocaleDateString("pt-BR");
}

function toDate(ts) {
  if (!ts) return null;
  if (ts instanceof Date) return ts;
  if (ts && ts.seconds) return new Date(ts.seconds * 1000);
  return new Date(ts);
}

function opToDate(op) { return toDate(op.timestamp); }

function tsKey(op) {
  const d = opToDate(op);
  return d ? d.toISOString().slice(0, 10) : "";
}

// Filtra operações com os filtros da aba Histórico
function applyFilters(ops) {
  const sym  = document.getElementById("f-symbol").value;
  const dir  = document.getElementById("f-dir").value;
  const res  = document.getElementById("f-result").value;
  const from = document.getElementById("f-date-from").value;
  const to   = document.getElementById("f-date-to").value;

  return ops.filter(op => {
    if (sym  && op.symbol    !== sym)  return false;
    if (dir  && op.direction !== dir)  return false;
    if (res  && op.result    !== res)  return false;
    const d = opToDate(op);
    if (from && d && d < new Date(from)) return false;
    if (to   && d && d > new Date(to + "T23:59:59")) return false;
    return true;
  });
}

// ═══════════════════════════════════════════════════════════════════
//  Sidebar — status e info
// ═══════════════════════════════════════════════════════════════════

function updateSidebarStatus(source, ok) {
  const el = document.getElementById(`status-${source}`);
  if (!el) return;
  const dot = el.querySelector(".dot");
  dot.className = "dot " + (ok ? "dot-win" : "dot-loss");
}

function updateSidebarInfo() {
  const opsInfo  = document.getElementById("ops-info");
  const tickInfo = document.getElementById("ticks-info");
  if (opsInfo)  opsInfo.textContent  = `${allOps.length} operações carregadas`;
  if (tickInfo) tickInfo.textContent = `${allTicks.length} ticks carregados`;
}

// ═══════════════════════════════════════════════════════════════════
//  Tab 1: Overview
// ═══════════════════════════════════════════════════════════════════

function renderOverview() {
  if (allOps.length === 0) {
    document.getElementById("kpi-grid").innerHTML =
      '<div class="kpi-placeholder">Nenhuma operação encontrada no Firestore.</div>';
    return;
  }

  const ops = [...allOps].sort((a, b) => (opToDate(a) || 0) - (opToDate(b) || 0));
  const today = new Date().toISOString().slice(0, 10);
  const opsToday = ops.filter(op => tsKey(op) === today);

  const wins       = ops.filter(op => op.result === "WIN").length;
  const losses     = ops.filter(op => op.result === "LOSS").length;
  const total      = ops.length;
  const winRate    = total ? (wins / total * 100) : 0;
  const totalProfit = ops.reduce((s, op) => s + (Number(op.profit) || 0), 0);
  const lastBal    = Number(ops[ops.length - 1].balance_after) || 0;
  const initBal    = Number(ops[0].balance_before) || 0;
  const maxDD      = Math.max(...ops.map(op => Number(op.drawdown_pct) || 0));
  const profitToday = opsToday.reduce((s, op) => s + (Number(op.profit) || 0), 0);

  const profitColor  = totalProfit  >= 0 ? "var(--clr-win)" : "var(--clr-loss)";
  const profitTColor = profitToday  >= 0 ? "var(--clr-win)" : "var(--clr-loss)";
  const winClass     = winRate >= 55 ? "win" : winRate >= 45 ? "" : "loss";

  document.getElementById("kpi-grid").innerHTML = `
    <div class="kpi-card win">
      <div class="kpi-label">💰 Saldo Atual</div>
      <div class="kpi-value">$${lastBal.toLocaleString("pt-BR", {minimumFractionDigits: 2})}</div>
      <div class="kpi-delta" style="color:var(--clr-muted)">Inicial: $${initBal.toLocaleString("pt-BR", {minimumFractionDigits: 2})}</div>
    </div>
    <div class="kpi-card ${totalProfit >= 0 ? 'win' : 'loss'}">
      <div class="kpi-label">📈 P/L Total</div>
      <div class="kpi-value" style="color:${profitColor}">${fmtUSD(totalProfit)}</div>
      <div class="kpi-delta" style="color:${profitTColor}">Hoje: ${fmtUSD(profitToday)}</div>
    </div>
    <div class="kpi-card ${winClass}">
      <div class="kpi-label">📊 Win Rate</div>
      <div class="kpi-value">${fmtPct(winRate)}</div>
      <div class="kpi-delta" style="color:var(--clr-muted)">${wins}W / ${losses}L</div>
    </div>
    <div class="kpi-card blue">
      <div class="kpi-label">📅 Operações Hoje</div>
      <div class="kpi-value">${opsToday.length}</div>
      <div class="kpi-delta" style="color:var(--clr-muted)">Total: ${total}</div>
    </div>
    <div class="kpi-card ${maxDD > 20 ? 'loss' : 'gold'}">
      <div class="kpi-label">🔻 Drawdown Máx</div>
      <div class="kpi-value" style="color:${maxDD > 20 ? 'var(--clr-loss)' : 'var(--clr-ema9)'}">${fmtPct(maxDD)}</div>
      <div class="kpi-delta" style="color:var(--clr-muted)">limite: 25%</div>
    </div>
  `;

  // Curva de saldo
  const times  = ops.map(op => opToDate(op));
  const bals   = ops.map(op => Number(op.balance_after));
  Plotly.react("chart-balance", [
    {
      x: times, y: bals,
      type: "scatter", mode: "lines", name: "Saldo",
      line: { color: "#00C9A7", width: 2 },
      fill: "tozeroy", fillcolor: "rgba(0,201,167,0.07)",
    },
    {
      x: [times[0], times[times.length - 1]], y: [initBal, initBal],
      type: "scatter", mode: "lines", name: "Inicial",
      line: { color: "#8B949E", width: 1, dash: "dot" },
    }
  ], { ...LAYOUT_BASE, height: 280, showlegend: false }, CONFIG_PLOT);

  // Tabela de recentes (últimas 20)
  const recent = ops.slice(-20).reverse();
  document.getElementById("recent-tbody").innerHTML = recent.map(op => {
    const profit = Number(op.profit);
    const pColor = profit >= 0 ? "var(--clr-win)" : "var(--clr-loss)";
    const resBadge = op.result === "WIN"
      ? '<span class="badge badge-win">WIN</span>'
      : '<span class="badge badge-loss">LOSS</span>';
    const dirBadge = op.direction === "BUY"
      ? '<span class="badge badge-buy">BUY</span>'
      : '<span class="badge badge-sell">SELL</span>';
    return `<tr>
      <td>${fmtTime(op.timestamp)}</td>
      <td>${op.symbol || "—"}</td>
      <td>${dirBadge}</td>
      <td>$${Number(op.stake).toFixed(2)}</td>
      <td>${op.duration}t</td>
      <td>${resBadge}</td>
      <td style="color:${pColor};font-weight:600">${fmtUSD(profit)}</td>
      <td>$${Number(op.balance_after).toFixed(2)}</td>
    </tr>`;
  }).join("");
}

// ═══════════════════════════════════════════════════════════════════
//  Tab 2: Histórico
// ═══════════════════════════════════════════════════════════════════

function populateSymbolFilter() {
  const sel = document.getElementById("f-symbol");
  const syms = [...new Set(allOps.map(op => op.symbol).filter(Boolean))].sort();
  sel.innerHTML = '<option value="">Todos</option>' +
    syms.map(s => `<option value="${s}">${s}</option>`).join("");
}

function populateDateFilters() {
  if (allOps.length === 0) return;
  const dates = allOps.map(op => opToDate(op)).filter(Boolean).sort((a, b) => a - b);
  const fmt = d => d.toISOString().slice(0, 10);
  document.getElementById("f-date-from").value = fmt(dates[0]);
  document.getElementById("f-date-to").value   = fmt(dates[dates.length - 1]);
}

function renderHistorico() {
  const filtered = applyFilters(allOps);
  const ops = [...filtered].sort((a, b) => (opToDate(a) || 0) - (opToDate(b) || 0));

  if (ops.length === 0) return;

  // ── Operações por dia (stacked bar) ────────────────────────────
  const dayWin = {}, dayLoss = {};
  ops.forEach(op => {
    const k = tsKey(op);
    if (!k) return;
    if (op.result === "WIN")  dayWin[k]  = (dayWin[k]  || 0) + 1;
    else                      dayLoss[k] = (dayLoss[k] || 0) + 1;
  });
  const days = [...new Set([...Object.keys(dayWin), ...Object.keys(dayLoss)])].sort();
  Plotly.react("chart-by-day", [
    { x: days, y: days.map(d => dayWin[d]  || 0), type: "bar", name: "WIN",
      marker: { color: "#00C9A7" } },
    { x: days, y: days.map(d => dayLoss[d] || 0), type: "bar", name: "LOSS",
      marker: { color: "#FF4B4B" } },
  ], { ...LAYOUT_BASE, height: 250, barmode: "stack", showlegend: true,
    legend: { bgcolor: "transparent" } }, CONFIG_PLOT);

  // ── P/L Acumulado ───────────────────────────────────────────────
  let cum = 0;
  const cumX = [], cumY = [];
  ops.forEach(op => {
    cum += Number(op.profit) || 0;
    cumX.push(opToDate(op));
    cumY.push(cum);
  });
  Plotly.react("chart-pl-cum", [
    { x: cumX, y: cumY, type: "scatter", mode: "lines",
      line: { color: "#00AAFF", width: 2 }, fill: "tozeroy",
      fillcolor: "rgba(0,170,255,0.07)" },
    { x: [cumX[0], cumX[cumX.length - 1]], y: [0, 0],
      type: "scatter", mode: "lines",
      line: { color: "#8B949E", width: 1, dash: "dot" } },
  ], { ...LAYOUT_BASE, height: 250, showlegend: false }, CONFIG_PLOT);

  // ── AI Confidence × Lucro (scatter) ────────────────────────────
  const winOps  = ops.filter(op => op.result === "WIN");
  const lossOps = ops.filter(op => op.result === "LOSS");
  Plotly.react("chart-ai-scatter", [
    { x: winOps.map(op => op.ai_confidence),  y: winOps.map(op => Number(op.profit)),
      mode: "markers", name: "WIN",
      marker: { color: "#00C9A7", size: 6, opacity: 0.7 } },
    { x: lossOps.map(op => op.ai_confidence), y: lossOps.map(op => Number(op.profit)),
      mode: "markers", name: "LOSS",
      marker: { color: "#FF4B4B", size: 6, opacity: 0.7 } },
    { x: [0, 1], y: [0, 0], mode: "lines",
      line: { color: "#8B949E", dash: "dot", width: 1 }, showlegend: false },
  ], {
    ...LAYOUT_BASE, height: 280, showlegend: true,
    legend: { bgcolor: "transparent" },
    xaxis: { ...LAYOUT_BASE.xaxis, title: "AI Confidence" },
    yaxis: { ...LAYOUT_BASE.yaxis, title: "Lucro (USD)" },
  }, CONFIG_PLOT);
}

// ═══════════════════════════════════════════════════════════════════
//  Tab 3: Análise Técnica
// ═══════════════════════════════════════════════════════════════════

function renderTecnico() {
  const ticks = allTicks.slice(-tickN);
  if (ticks.length < 30) return;

  const prices = ticks.map(t => t.price);
  const times  = ticks.map(t => t.datetime ? new Date(t.datetime) : null);

  const ema9arr  = emaSeries(prices, EMA_FAST);
  const ema21arr = emaSeries(prices, EMA_SLOW);
  const { mid: bbMid, upper: bbUp, lower: bbLo } = bollingerSeries(prices, BB_PERIOD, BB_STD);

  // Operações na janela de tempo (para marcadores)
  const firstTime = times[0];
  const lastTime  = times[times.length - 1];
  const opsInRange = allOps.filter(op => {
    const d = opToDate(op);
    return d && firstTime && lastTime && d >= firstTime && d <= lastTime;
  });

  const winOps  = opsInRange.filter(op => op.result === "WIN");
  const lossOps = opsInRange.filter(op => op.result === "LOSS");

  // Bollinger fill (toself)
  const bbXfill = [...times, ...[...times].reverse()];
  const bbYfill = [...bbUp.map((v, i) => v ?? bbMid[i] ?? prices[i]),
                   ...[...bbLo.map((v, i) => v ?? bbMid[i] ?? prices[i])].reverse()];

  Plotly.react("chart-price", [
    // BB fill
    { x: bbXfill, y: bbYfill, fill: "toself",
      fillcolor: "rgba(255,255,255,0.05)", line: { color: "transparent" },
      name: "Bollinger", showlegend: true },
    // BB mid
    { x: times, y: bbMid, mode: "lines", name: "BB Mid",
      line: { color: "rgba(255,255,255,0.2)", width: 1, dash: "dot" } },
    // Preço
    { x: times, y: prices, mode: "lines", name: "Preço",
      line: { color: "#E6EDF3", width: 1.5 } },
    // EMA 9
    { x: times, y: ema9arr, mode: "lines", name: "EMA 9",
      line: { color: "#F6C90E", width: 1.5 } },
    // EMA 21
    { x: times, y: ema21arr, mode: "lines", name: "EMA 21",
      line: { color: "#00AAFF", width: 1.5 } },
    // WIN markers
    { x: winOps.map(op => opToDate(op)),
      y: winOps.map(() => prices[prices.length - 1]),
      mode: "markers", name: "WIN",
      marker: { color: "#00C9A7", symbol: "triangle-up", size: 12 } },
    // LOSS markers
    { x: lossOps.map(op => opToDate(op)),
      y: lossOps.map(() => prices[prices.length - 1]),
      mode: "markers", name: "LOSS",
      marker: { color: "#FF4B4B", symbol: "triangle-down", size: 12 } },
  ], {
    ...LAYOUT_BASE, height: 360,
    showlegend: true, legend: { bgcolor: "transparent", orientation: "h", y: 1.08 },
  }, CONFIG_PLOT);

  // ── Gauges (baseados na última operação) ───────────────────────
  const lastOp = allOps.length ? allOps[allOps.length - 1] : null;
  const rsi  = lastOp ? Number(lastOp.rsi)       : 50;
  const adx  = lastOp ? Number(lastOp.adx)       : 0;
  const macdH = lastOp ? Number(lastOp.macd_hist) : 0;

  renderGauge("gauge-rsi", rsi, "RSI", 0, 100,
    [0, 35, 65, 100], ["#FF4B4B", "#00C9A7", "#FF4B4B"]);

  renderGauge("gauge-adx", adx, "ADX", 0, 60,
    [0, 20, 40, 60], ["#FF4B4B", "#F6C90E", "#00C9A7"]);

  // MACD Hist como gauge simétrico
  const macdAbs = Math.abs(macdH);
  const macdMax = Math.max(1, macdAbs * 2);
  Plotly.react("gauge-macd", [{
    type: "indicator", mode: "gauge+number",
    value: macdH,
    number: { valueformat: ".4f", font: { color: macdH >= 0 ? "#00C9A7" : "#FF4B4B", size: 28 } },
    gauge: {
      axis: { range: [-macdMax, macdMax], tickfont: { color: "#8B949E" } },
      bar:  { color: macdH >= 0 ? "#00C9A7" : "#FF4B4B" },
      bgcolor: "#0D1117",
      bordercolor: "#30363D",
      steps: [
        { range: [-macdMax, 0], color: "rgba(255,75,75,0.08)" },
        { range: [0, macdMax],  color: "rgba(0,201,167,0.08)" },
      ],
    },
  }], { ...LAYOUT_BASE, height: 200, margin: { t: 20, r: 20, b: 10, l: 20 } }, CONFIG_PLOT);
}

function renderGauge(elId, value, title, min, max, thresholds, colors) {
  const steps = colors.map((c, i) => ({ range: [thresholds[i], thresholds[i + 1]], color: c + "22" }));
  Plotly.react(elId, [{
    type: "indicator", mode: "gauge+number",
    value,
    number: { font: { color: "#E6EDF3", size: 28 } },
    gauge: {
      axis: { range: [min, max], tickfont: { color: "#8B949E" } },
      bar:  { color: "#FFFFFF", thickness: 0.25 },
      bgcolor: "#0D1117",
      bordercolor: "#30363D",
      steps,
    },
  }], { ...LAYOUT_BASE, height: 200, margin: { t: 20, r: 20, b: 10, l: 20 } }, CONFIG_PLOT);
}

// ═══════════════════════════════════════════════════════════════════
//  Tab 4: IA & Risco
// ═══════════════════════════════════════════════════════════════════

function renderIaRisco() {
  if (allOps.length === 0) return;

  const ops = [...allOps].sort((a, b) => (opToDate(a) || 0) - (opToDate(b) || 0));

  // ── Win Rate por faixa de confiança ────────────────────────────
  const bins   = ["0.5-0.55", "0.55-0.60", "0.60-0.65", "0.65-0.70", "0.70-0.75", "0.75+"];
  const edges  = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 1.01];
  const wrBin  = bins.map(() => ({ w: 0, t: 0 }));
  ops.forEach(op => {
    const conf = Number(op.ai_confidence) || 0;
    for (let i = 0; i < edges.length - 1; i++) {
      if (conf >= edges[i] && conf < edges[i + 1]) {
        wrBin[i].t++;
        if (op.result === "WIN") wrBin[i].w++;
        break;
      }
    }
  });
  const wrVals = wrBin.map(b => b.t ? (b.w / b.t * 100) : null);
  Plotly.react("chart-wr-bin", [{
    x: bins, y: wrVals, type: "bar",
    marker: {
      color: wrVals.map(v =>
        v === null ? "#30363D" : v >= 60 ? "#00C9A7" : v >= 50 ? "#F6C90E" : "#FF4B4B"
      ),
    },
  }], {
    ...LAYOUT_BASE, height: 250,
    yaxis: { ...LAYOUT_BASE.yaxis, title: "Win Rate (%)", range: [0, 100] },
    xaxis: { ...LAYOUT_BASE.xaxis, title: "Faixa de Confiança" },
    showlegend: false,
  }, CONFIG_PLOT);

  // ── WIN/LOSS por Direção (grouped) ─────────────────────────────
  const dirs = ["BUY", "SELL"];
  const dirWin  = dirs.map(d => ops.filter(op => op.direction === d && op.result === "WIN").length);
  const dirLoss = dirs.map(d => ops.filter(op => op.direction === d && op.result === "LOSS").length);
  Plotly.react("chart-dir-hist", [
    { x: dirs, y: dirWin,  type: "bar", name: "WIN",  marker: { color: "#00C9A7" } },
    { x: dirs, y: dirLoss, type: "bar", name: "LOSS", marker: { color: "#FF4B4B" } },
  ], {
    ...LAYOUT_BASE, height: 250, barmode: "group",
    showlegend: true, legend: { bgcolor: "transparent" },
  }, CONFIG_PLOT);

  // ── Timeline de Risco (multi-eixo) ─────────────────────────────
  const riskTimes = ops.map(op => opToDate(op));
  const dd    = ops.map(op => Number(op.drawdown_pct) || 0);
  const wr    = ops.map(op => Number(op.win_rate_recent) || 0);
  const cl    = ops.map(op => Number(op.consec_losses)  || 0);
  Plotly.react("chart-risk-timeline", [
    { x: riskTimes, y: dd, mode: "lines", name: "Drawdown (%)",
      line: { color: "#FF4B4B", width: 2 }, yaxis: "y1" },
    { x: riskTimes, y: wr, mode: "lines", name: "Win Rate Recente (%)",
      line: { color: "#00C9A7", width: 2 }, yaxis: "y2" },
    { x: riskTimes, y: cl, type: "bar", name: "Losses Consec.",
      marker: { color: "rgba(246,201,14,0.4)" }, yaxis: "y1" },
  ], {
    ...LAYOUT_BASE, height: 300,
    yaxis: { ...LAYOUT_BASE.yaxis, title: "Drawdown / Consec." },
    yaxis2: {
      title: "Win Rate (%)",
      overlaying: "y", side: "right",
      gridcolor: "transparent", zerolinecolor: "#30363D",
      tickfont: { color: "#8B949E" }, titlefont: { color: "#8B949E" },
    },
    showlegend: true, legend: { bgcolor: "transparent", orientation: "h", y: 1.1 },
  }, CONFIG_PLOT);
}

// ═══════════════════════════════════════════════════════════════════
//  Renderização principal (chamada ao receber dados)
// ═══════════════════════════════════════════════════════════════════

function renderAll() {
  renderOverview();
  renderHistorico();
  renderTecnico();
  renderIaRisco();
  updateSidebarInfo();
}

function renderActiveTab() {
  const active = document.querySelector(".tab-content.active");
  if (!active) return;
  const id = active.id;
  if (id === "tab-overview")  renderOverview();
  if (id === "tab-historico") renderHistorico();
  if (id === "tab-tecnico")   renderTecnico();
  if (id === "tab-ia-risco")  renderIaRisco();
}

// ═══════════════════════════════════════════════════════════════════
//  Tab switching
// ═══════════════════════════════════════════════════════════════════

document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
    btn.classList.add("active");
    const tabId = "tab-" + btn.dataset.tab;
    document.getElementById(tabId).classList.add("active");
    // Pequeño delay para o flex:1 funcionar antes de Plotly medir height
    setTimeout(renderActiveTab, 50);
  });
});

// ═══════════════════════════════════════════════════════════════════
//  Slider de ticks
// ═══════════════════════════════════════════════════════════════════

const tickSlider = document.getElementById("tick-slider");
const tickSliderVal = document.getElementById("tick-slider-val");
tickSlider.addEventListener("input", () => {
  tickN = parseInt(tickSlider.value, 10);
  tickSliderVal.textContent = tickN;
});
tickSlider.addEventListener("change", () => {
  if (document.getElementById("tab-tecnico").classList.contains("active")) {
    renderTecnico();
  }
});

// ═══════════════════════════════════════════════════════════════════
//  Filtros — Tab Histórico
// ═══════════════════════════════════════════════════════════════════

document.getElementById("btn-filter").addEventListener("click", renderHistorico);
document.getElementById("btn-clear").addEventListener("click", () => {
  document.getElementById("f-symbol").value = "";
  document.getElementById("f-dir").value    = "";
  document.getElementById("f-result").value = "";
  populateDateFilters();
  renderHistorico();
});

// ═══════════════════════════════════════════════════════════════════
//  Firebase init e listeners de dados em tempo real
// ═══════════════════════════════════════════════════════════════════

let firebaseApp  = null;
let firestoreDB  = null;
let realtimeDB   = null;
let firebaseAuth = null;

try {
  firebaseApp  = firebase.initializeApp(FIREBASE_CONFIG);
  firestoreDB  = firebase.firestore();
  realtimeDB   = firebase.database();
  firebaseAuth = firebase.auth();
} catch (e) {
  console.error("[Firebase] Falha na inicialização:", e);
}

// ── Firestore: coleção "operacoes" ────────────────────────────────
if (firestoreDB) {
  firestoreDB.collection("operacoes")
    .orderBy("timestamp")
    .limitToLast(MAX_OPS)
    .onSnapshot(
      snap => {
        allOps = snap.docs.map(doc => ({ id: doc.id, ...doc.data() }));
        allOps.sort((a, b) => (toDate(a.timestamp) || 0) - (toDate(b.timestamp) || 0));
        updateSidebarStatus("firestore", true);
        populateSymbolFilter();
        populateDateFilters();
        renderAll();
      },
      err => {
        console.error("[Firestore]", err);
        updateSidebarStatus("firestore", false);
      }
    );
}

// ── RTDB: ticks/{SYMBOL} ─────────────────────────────────────────
if (realtimeDB) {
  realtimeDB.ref(`ticks/${SYMBOL}`)
    .limitToLast(2000)
    .on("value",
      snap => {
        const val = snap.val();
        if (!val) { allTicks = []; return; }
        allTicks = Object.values(val)
          .filter(t => t && t.price != null)
          .sort((a, b) => (a.epoch || 0) - (b.epoch || 0));
        updateSidebarStatus("rtdb", true);
        if (document.getElementById("tab-tecnico").classList.contains("active")) {
          renderTecnico();
        }
      },
      err => {
        console.error("[RTDB]", err);
        updateSidebarStatus("rtdb", false);
      }
    );

  // ── RTDB: status do bot (leitura pública) ─────────────────────
  realtimeDB.ref("bot_control/status").on("value", snap => {
    _updateBotStatusUI(snap.val());
  });
}

// ═══════════════════════════════════════════════════════════════════
//  Bot status UI — atualizada por listener RTDB em tempo real
// ═══════════════════════════════════════════════════════════════════

function _updateBotStatusUI(status) {
  const dot       = document.getElementById("bot-dot");
  const text      = document.getElementById("bot-status-text");
  const heartbeat = document.getElementById("bot-heartbeat");
  const lastAct   = document.getElementById("bot-last-action");
  const startForm = document.getElementById("bot-start-form");
  const stopBtn   = document.getElementById("btn-stop-bot");
  if (!dot) return;

  if (!status) {
    dot.className    = "dot dot-loading";
    text.textContent = "Agente offline";
    if (heartbeat) heartbeat.textContent = "";
    return;
  }

  const running = !!status.running;
  dot.className    = "dot " + (running ? "dot-win" : "dot-loss");
  text.textContent = running ? `Rodando (PID ${status.pid || "?"})` : "Parado";

  if (heartbeat && status.last_heartbeat) {
    const d = new Date(status.last_heartbeat);
    heartbeat.textContent = `Heartbeat: ${d.toLocaleTimeString("pt-BR")}`;
  }
  if (lastAct && status.last_action) {
    lastAct.textContent = status.last_action;
  }

  // ── Saldo ao vivo (puxado da API Deriv pelo bot_agent) ──────────────
  const balVal = document.getElementById("rc-balance-val");
  const balCur = document.getElementById("rc-balance-cur");
  if (balVal) {
    if (status.balance_ok && status.balance != null) {
      balVal.textContent = `$${Number(status.balance).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`;
      balVal.style.color = "var(--clr-win)";
    } else {
      balVal.textContent = "⏳ aguardando agente…";
      balVal.style.color = "var(--clr-muted)";
    }
  }
  if (balCur && status.currency) balCur.textContent = status.currency;

  if (startForm && stopBtn) {
    startForm.style.display = running ? "none"  : "block";
    stopBtn.style.display   = running ? "block" : "none";
  }
}

// ═══════════════════════════════════════════════════════════════════
//  Autenticação Firebase — Email/Password
// ═══════════════════════════════════════════════════════════════════

if (firebaseAuth) {
  firebaseAuth.onAuthStateChanged(user => {
    const authPrompt  = document.getElementById("bot-auth-prompt");
    const botControls = document.getElementById("bot-controls");
    if (user) {
      if (authPrompt)  authPrompt.style.display  = "none";
      if (botControls) botControls.style.display = "flex";
    } else {
      if (authPrompt)  authPrompt.style.display  = "block";
      if (botControls) botControls.style.display = "none";
    }
  });
}

// ── Helpers de modal ─────────────────────────────────────────────
function _openLoginModal() {
  document.getElementById("login-modal").style.display = "flex";
  setTimeout(() => document.getElementById("login-email").focus(), 80);
}
function _closeLoginModal() {
  document.getElementById("login-modal").style.display = "none";
  document.getElementById("login-error").textContent   = "";
}
function _loginError(msg) {
  document.getElementById("login-error").textContent = msg;
}

// ── Login modal ───────────────────────────────────────────────────
document.getElementById("btn-login").addEventListener("click", _openLoginModal);
document.getElementById("btn-cancel-login").addEventListener("click", _closeLoginModal);

// Fechar clicando no overlay
document.getElementById("login-modal").addEventListener("click", e => {
  if (e.target === document.getElementById("login-modal")) _closeLoginModal();
});

// ── Google Sign-In ───────────────────────────────────────────────
document.getElementById("btn-google-login").addEventListener("click", async () => {
  if (!firebaseAuth) return;
  _loginError("");
  try {
    const provider = new firebase.auth.GoogleAuthProvider();
    provider.setCustomParameters({ prompt: "select_account" });
    await firebaseAuth.signInWithPopup(provider);
    _closeLoginModal();
  } catch (e) {
    const msgs = {
      "auth/popup-closed-by-user":   "Login cancelado.",
      "auth/popup-blocked":          "Popup bloqueado pelo navegador. Permita popups para este site.",
      "auth/account-exists-with-different-credential":
                                     "Já existe uma conta com outro provedor para este email.",
    };
    _loginError(msgs[e.code] || e.message);
  }
});

// ── Email/Password ────────────────────────────────────────────────
document.getElementById("btn-do-login").addEventListener("click", async () => {
  const email    = document.getElementById("login-email").value.trim();
  const password = document.getElementById("login-password").value;
  _loginError("");
  if (!email || !password) { _loginError("Preencha email e senha."); return; }
  try {
    await firebaseAuth.signInWithEmailAndPassword(email, password);
    _closeLoginModal();
  } catch (e) {
    const msgs = {
      "auth/user-not-found":     "Usuário não encontrado.",
      "auth/wrong-password":     "Senha incorreta.",
      "auth/invalid-email":      "Email inválido.",
      "auth/too-many-requests":  "Muitas tentativas. Aguarde.",
      "auth/invalid-credential": "Email ou senha incorretos.",
    };
    _loginError(msgs[e.code] || e.message);
  }
});

document.getElementById("login-password").addEventListener("keydown", e => {
  if (e.key === "Enter") document.getElementById("btn-do-login").click();
});

document.getElementById("btn-logout").addEventListener("click", () => {
  firebaseAuth.signOut();
});

// ═══════════════════════════════════════════════════════════════════
//  Controle do bot — envio de comandos via RTDB
// ═══════════════════════════════════════════════════════════════════

async function sendBotCommand(action, args = {}) {
  if (!firebaseAuth || !firebaseAuth.currentUser) {
    alert("Você precisa estar autenticado para controlar o bot.");
    return;
  }
  if (!realtimeDB) return;
  try {
    await realtimeDB.ref("bot_control/commands").push({
      action,
      args,
      timestamp: firebase.database.ServerValue.TIMESTAMP,
      executed:  false,
      sent_by:   firebaseAuth.currentUser.email,
    });
    console.log(`[Dashboard] Comando enviado: ${action}`);
  } catch (e) {
    console.error("[Dashboard] Erro:", e);
    alert("Erro ao enviar comando: " + e.message);
  }
}

document.getElementById("rc-mode").addEventListener("change", function () {
  document.getElementById("rc-real-warn").style.display =
    this.value === "real" ? "block" : "none";
});

document.getElementById("btn-start-bot").addEventListener("click", () => {
  const mode = document.getElementById("rc-mode").value;
  if (mode === "real" &&
      !confirm("⚠️ Modo REAL: isso usará DINHEIRO REAL na sua conta Deriv. Confirmar?")) return;
  // balance não é enviado — bot_agent usa o saldo real da API Deriv
  sendBotCommand("start", {
    mode,
    hist_count:    parseInt(document.getElementById("rc-hist").value)       || 500,
    min_ticks:     parseInt(document.getElementById("rc-min-ticks").value)  || 500,
    retrain_min:   parseInt(document.getElementById("rc-retrain").value)    || 10,
    skip_collect:  document.getElementById("rc-skip-collect").checked,
    force_retrain: document.getElementById("rc-force-retrain").checked,
    no_scan:       document.getElementById("rc-no-scan").checked,
  });
});

document.getElementById("btn-stop-bot").addEventListener("click", () => {
  if (!confirm("Parar o bot agora?")) return;
  sendBotCommand("stop");
});
