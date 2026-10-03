/*
 * Copyright 2026 Andrei Maltsev (Rawanga)
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
// app.js — Rawanga Trading Desk UI (candlestick chart + instruments list)
const API = '';
// t2: i18n alias usable where a local `t` variable shadows the global t().
function t2(k, v) { return window.t(k, v); }
let chart, candleSeries, volumeSeries, overlays = {}, indLine = {};
const oscCharts = {};  // separate oscillator charts below the main chart
let current = { symbol: 'BTC', tf: '1h', strategy: 'rawa_system' };
let lastInd = null;

function themeColor() {
  const cs = getComputedStyle(document.body);
  const g = n => cs.getPropertyValue(n).trim();
  return { bg: g('--bg'), panel: g('--panel'), txt: g('--txt'), grid: g('--grid'),
           up: g('--up'), dn: g('--dn') };
}

function applyChartTheme() {
  const c = themeColor();
  const layout = { background: { color: 'transparent' },
                   textColor: c.txt };
  const grid = { vertLines: { color: c.grid }, horzLines: { color: c.grid } };
  if (chart) chart.applyOptions({ layout, grid });
  if (candleSeries) candleSeries.applyOptions({
    upColor: c.up, downColor: c.dn, wickUpColor: c.up, wickDownColor: c.dn,
  });
  if (typeof drawHorizontalVol === 'function') drawHorizontalVol();
}

function toggleTheme() {
  document.body.classList.toggle('light');
  const light = document.body.classList.contains('light');
  localStorage.setItem('tv_theme', light ? 'light' : 'dark');
  document.getElementById('themebtn').textContent = light ? '☀' : '🌙';
  applyChartTheme();
  if (lastInd && lastInd.bars) loadIndicators();
}

function initTheme() {
  if (localStorage.getItem('tv_theme') === 'light') document.body.classList.add('light');
  document.getElementById('themebtn').textContent =
    document.body.classList.contains('light') ? '☀' : '🌙';
}

const catTitles = { crypto: 'cat.crypto', stocks: 'cat.stocks', energy: 'cat.energy', metals: 'cat.metals', indices: 'cat.indices' };

function initChart() {
  const el = document.getElementById('chart');
  chart = LightweightCharts.createChart(el, {
    layout: { background: { color: 'transparent' }, textColor: themeColor().txt },
    grid: { vertLines: { color: themeColor().grid }, horzLines: { color: themeColor().grid } },
    timeScale: { timeVisible: true, secondsVisible: false, borderColor: '#232b36' },
    rightPriceScale: { borderColor: '#232b36', scaleMargins: { top: 0.08, bottom: 0.08 } },
    handleScale: { axisPressedMouseMove: { price: true, time: true }, mouseWheel: true },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
  });
  chart.timeScale().applyOptions({ rightOffset: 4 });
  initMainSync();
  const c = themeColor();
  candleSeries = chart.addCandlestickSeries({
    upColor: c.up, downColor: c.dn, borderVisible: false,
    wickUpColor: c.up, wickDownColor: c.dn,
  });
  // Volume — separate pane below the candles (as in terminals)
  volumeSeries = chart.addHistogramSeries({
    priceFormat: { type: 'volume' },
    priceScaleId: '',
  });  volumeSeries.priceScale().applyOptions({
    scaleMargins: { top: 0.78, bottom: 0 },
  });
  const hc = ensureHvolCanvas(el);
  hc.chart = chart;
  chart.timeScale().subscribeVisibleLogicalRangeChange(drawHorizontalVol);
  chart.timeScale().subscribeVisibleTimeRangeChange(drawHorizontalVol);
  new ResizeObserver(() => { chart.applyOptions({ width: el.clientWidth, height: el.clientHeight }); syncHvolSize(); drawHorizontalVol(); }).observe(el);
}

// ── Horizontal volume profile (canvas overlay above the chart) ──────
// Classic Volume Profile: total volume per price bin.
// Normalised on every load. Mouse-transparent.
function ensureHvolCanvas(el) {
  let cv = el.querySelector('.hvolcanvas');
  if (!cv) {
    cv = document.createElement('canvas');
    cv.className = 'hvolcanvas';
    el.appendChild(cv);
  }
  cv._bins = [];
  return cv;
}

function syncHvolSize() {
  const el = document.getElementById('chart');
  const cv = el && el.querySelector('.hvolcanvas');
  if (!el || !cv) return;
  const dpr = window.devicePixelRatio || 1;
  cv.width = el.clientWidth * dpr;
  cv.height = el.clientHeight * dpr;
  cv.style.width = el.clientWidth + 'px';
  cv.style.height = el.clientHeight + 'px';
}

function computeBins(bars) {
  let lo = Infinity, hi = -Infinity;
  for (const b of bars) { if (b.l < lo) lo = b.l; if (b.h > hi) hi = b.h; }
  if (!(hi > lo)) return [];
  const NB = 50, step = (hi - lo) / NB;
  const v = new Array(NB).fill(0);
  for (const b of bars) {
    const a = Math.max(0, Math.min(NB - 1, Math.floor((b.l - lo) / step)));
    const c = Math.max(0, Math.min(NB - 1, Math.floor((b.h - lo) / step)));
    const vol = Number(b.v) || 0;
    const w = 1 / (c - a + 1);
    for (let i = a; i <= c; i++) v[i] += vol * w;
  }
  return { lo, step, v };
}

function drawHorizontalVol() {
  const el = document.getElementById('chart');
  const cv = el && el.querySelector('.hvolcanvas');
  if (!cv || !cv.chart || !cv._bins || !cv._bins.v || !cv._bins.v.length) return;
  const on = document.getElementById('i-hvol')?.checked;
  const ctx = cv.getContext('2d');
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, cv.width, cv.height);
  if (!on) return;
  const dpr = window.devicePixelRatio || 1;
  const ser = candleSeries, ts = cv.chart.timeScale();
  const { lo, step, v } = cv._bins;
  const maxv = Math.max(...v) || 1;
  const W = el.clientWidth, H = el.clientHeight;
  const maxW = Math.min(0.42 * W, 240);
  ctx.scale(dpr, dpr);
  const dark = !document.body.classList.contains('light');
  for (let i = 0; i < v.length; i++) {
    if (v[i] <= 0) continue;
    const yTop = ser.priceToCoordinate(lo + (i + 1) * step);
    const yBot = ser.priceToCoordinate(lo + i * step);
    if (yTop == null || yBot == null) continue;
    const h = Math.abs(yBot - yTop);
    const w = (v[i] / maxv) * maxW;
    ctx.fillStyle = dark ? 'rgba(120,160,255,0.28)' : 'rgba(37,99,235,0.22)';
    ctx.fillRect(0, Math.min(yTop, yBot), w, Math.max(h, 1));
    ctx.strokeStyle = dark ? 'rgba(150,185,255,0.45)' : 'rgba(37,99,235,0.45)';
    ctx.beginPath(); ctx.moveTo(0, Math.min(yTop, yBot)); ctx.lineTo(w, Math.min(yTop, yBot)); ctx.stroke();
  }
}

function toBars(bars) {
  return bars.map(b => ({ time: Math.floor(b.t / 1000), open: b.o, high: b.h, low: b.l, close: b.c }));
}

function toVolume(bars) {
  return bars.map(b => ({
    time: Math.floor(b.t / 1000),
    value: b.v,
    color: b.c >= b.o ? 'rgba(38,166,154,0.55)' : 'rgba(239,83,80,0.55)',
  }));
}

function mkLine(color, width = 1, style = 0, scaleId = 'right') {
  return chart.addLineSeries({
    color, lineWidth: width, lineStyle: style, priceScaleId: scaleId,
    lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false,
  });
}

function seriesFrom(arr, times, color, width = 1, style = 0, scaleId = 'right') {
  const s = mkLine(color, width, style, scaleId);
  const data = [];
  for (let i = 0; i < arr.length; i++) {
    if (arr[i] != null) data.push({ time: Math.floor(times[i] / 1000), value: arr[i] });
  }
  s.setData(data);
  return s;
}

function clearOverlays() {
  for (const k in indLine) { chart.removeSeries(indLine[k]); }
  indLine = {};
}

async function loadIndicators() {
  const { symbol, tf } = current;
  const r = await fetch(`${API}/api/indicators/${symbol}?tf=${tf}&limit=500`);
  const j = await r.json();
  lastInd = j;
  clearOverlays();
  const t = j.time;
  const show = id => document.getElementById(id)?.checked;
  if (show('i-ema'))  indLine.ema = seriesFrom(j.ema200, t, '#2962ff', 2);
  if (show('i-sma50'))  indLine.sma50 = seriesFrom(j.sma50, t, '#e0403d', 2);
  if (show('i-sma200')) indLine.sma200 = seriesFrom(j.sma200, t, '#7e57c2', 2);
  if (show('i-st')) {
    indLine.st = seriesFrom(j.supertrend, t, '#ff9800', 2);
  }
  if (show('i-don')) {
    indLine.donH = seriesFrom(j.donchian_hi, t, '#26a69a', 1, 2);
    indLine.donL = seriesFrom(j.donchian_lo, t, '#ef5350', 1, 2);
  }
  if (show('i-bb')) {
    indLine.bbU = seriesFrom(j.bb_upper, t, 'rgba(120,144,240,0.7)');
    indLine.bbM = seriesFrom(j.bb_mid, t, 'rgba(120,144,240,0.4)');
    indLine.bbL = seriesFrom(j.bb_lower, t, 'rgba(120,144,240,0.7)');
  }
  if (show('i-vma')) indLine.vma = seriesFrom(j.vol_ma20, t, '#f0b90b', 1, 0, 'vol');
  // Oscillators — separate mini-charts below the main chart
  renderOsc('rsi', j, t, show('i-rsi'));
  renderOsc('macd', j, t, show('i-macd'));
  renderOsc('adx', j, t, show('i-adx'));
  await loadSignals();
}

// ── Separate oscillator panes below the main chart ──────────────────
// Separate mini-charts in #pane-* containers. Created only when the container
// is visible (.on) and explicitly resized — otherwise the canvas is 0×0.
const oscColors = { rsi: '#b388ff', macd: '#2962ff', adx: '#ffd54f' };
let oscSyncLock = false;

function ensureOscChart(kind, el) {
  if (!oscCharts[kind]) {
    const c = LightweightCharts.createChart(el, {
      layout: { background: { color: 'transparent' }, textColor: themeColor().txt },
      grid: { vertLines: { color: themeColor().grid }, horzLines: { color: themeColor().grid } },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: '#232b36', visible: kind === 'adx' },
      rightPriceScale: { borderColor: '#232b36', scaleMargins: { top: 0.12, bottom: 0.08 } },
      leftPriceScale: { visible: false },
      crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
      handleScale: { axisPressedMouseMove: { time: true, price: false }, mouseWheel: false },
      handleScroll: { mouseWheel: false, pressedMouseMove: false, horzTouchDrag: false, vertTouchDrag: false },
      localization: { priceFormatter: p => (Math.abs(p) >= 1000 ? p.toFixed(0) : p.toFixed(2)) },
    });
    oscCharts[kind] = c;
    oscCharts[kind]._series = [];
    // Oscillators are mirror-only: they do not take the mouse (the main chart does).
    // Sync is driven ONLY by the main chart (initMainSync), one-way —
    // so there is no loop and an oscillator cannot hijack the chart control.
    new ResizeObserver(() => {
      if (el.clientHeight > 0) c.applyOptions({ width: el.clientWidth, height: el.clientHeight });
    }).observe(el);
  }
  return oscCharts[kind];
}

// Main chart → oscillators (the direction that was missing before)
function initMainSync() {
  chart.timeScale().subscribeVisibleLogicalRangeChange(r => {
    if (oscSyncLock || !r) return;
    oscSyncLock = true;
    try {
      for (const k in oscCharts) oscCharts[k].timeScale().setVisibleLogicalRange(r);
    } catch (e) {}
    oscSyncLock = false;
  });
}

// Main chart → oscillators
function renderOsc(kind, j, t, on) {
  const el = document.getElementById('pane-' + kind);
  if (!el) return;
  el.classList.toggle('on', !!on);
  if (!on) return;
  try {
    const c = ensureOscChart(kind, el);
    // the container just became visible — let the browser re-layout and resize explicitly
    requestAnimationFrame(() => {
      try { c.applyOptions({ width: el.clientWidth, height: el.clientHeight }); } catch (e) {}
    });
    c._series.forEach(s => c.removeSeries(s));
    c._series = [];
    const color = oscColors[kind];
    if (kind === 'rsi') {
      c._series.push(c.addLineSeries({ color, lineWidth: 2 }).setData(seriesData(j.rsi14, t)));
    } else if (kind === 'macd') {
      const hist = [];
      for (let i = 0; i < (j.macd_hist || []).length; i++) {
        const v = j.macd_hist[i];
        if (v == null) continue;
        hist.push({ time: Math.floor(t[i] / 1000), value: v,
          color: v >= 0 ? 'rgba(38,166,154,0.6)' : 'rgba(239,83,80,0.6)' });
      }
      c._series.push(c.addHistogramSeries({}).setData(hist));
      c._series.push(c.addLineSeries({ color: '#2962ff', lineWidth: 1 }).setData(seriesData(j.macd, t)));
      c._series.push(c.addLineSeries({ color: '#ff6d00', lineWidth: 1 }).setData(seriesData(j.macd_signal, t)));
    } else if (kind === 'adx') {
      c._series.push(c.addLineSeries({ color, lineWidth: 2 }).setData(seriesData(j.adx, t)));
    }
    // sync ONLY the time range (visible logical range) with the main chart.
    // Do NOT touch rightOffset/bars and send no reverse events — the chart would drift.
    const lr = chart.timeScale().getVisibleLogicalRange();
    if (lr) c.timeScale().setVisibleLogicalRange(lr);
  } catch (e) {
    // a rendering defect of one oscillator must not break the rest (journal, chart)
    console.error('renderOsc(' + kind + ') error:', e);
  }
}

function seriesData(arr, times) {
  const out = [];
  for (let i = 0; i < arr.length; i++) {
    if (arr[i] != null) out.push({ time: Math.floor(times[i] / 1000), value: arr[i] });
  }
  return out;
}

async function loadSignals() {
  const { symbol, tf } = current;
  const showStv3 = document.getElementById('s-stv3')?.checked === true;
  const showRawa = document.getElementById('s-rawa')?.checked !== false;
  const active = current.strategy;
  const fmt = v => (v == null ? '—' : (Math.abs(v) >= 1000 ? v.toFixed(0) : v.toFixed(2)));

  // load both strategies
  const stratColor = { stv3: '#42a5f5', rawa_system: '#ffb300' };
  const stratLabel = { stv3: 'STv3', rawa_system: 'Rawa' };
  const want = [];
  if (showRawa) want.push('rawa_system');
  if (showStv3) want.push('stv3');
  // the active strategy is always loaded (for the journal)
  if (!want.includes(active)) want.push(active);

  const markers = [];
  const allTrades = {};

  for (const st of want) {
    const r = await fetch(`${API}/api/signals/${symbol}?strategy=${st}&tf=${tf}&limit=500`);
    const j = await r.json();
    const col = stratColor[st] || '#9e9e9e';
    const visible = st === active || (st === 'stv3' && showStv3) || (st === 'rawa_system' && showRawa);
    // SPREAD strategies vertically so markers do not overlap on one bar
    const isRawa = st === 'rawa_system';
    const inPos = (isL) => isL
      ? (isRawa ? 'belowBar' : 'belowBar')
      : (isRawa ? 'aboveBar' : 'aboveBar');
    // offset: Rawa is drawn with size 2, STv3 with size 1
    const msize = isRawa ? 2 : 1;
    // draw REAL trades (entry→exit). One bar — ONE marker.
    // Build a bar→events map to collapse exit+entry into one "reversal".
    const trades = j.trades || [];
    const byTime = new Map();
    const put = (tm, kind, side, label) => {
      const cur = byTime.get(tm) || [];
      cur.push({ kind, side, label });
      byTime.set(tm, cur);
    };
    for (const t of trades) {
      const tIn = Math.floor(t.entry_ts / 1000);
      const tOut = t.exit_ts ? Math.floor(t.exit_ts / 1000) : null;
      put(tIn, 'in', t.side, 'L');
      if (tOut) put(tOut, 'out', t.side, '✕');
    }
    if (j.open) put(Math.floor(j.open.entry_ts / 1000), 'in', j.open.side, 'L');

    for (const [tm, evs] of byTime) {
      const ins = evs.filter(e => e.kind === 'in');
      const outs = evs.filter(e => e.kind === 'out');
      const hasIn = ins.length > 0, hasOut = outs.length > 0;
      const side = (ins[0] || outs[0]).side;
      const isL = side === 'long';
      if (hasIn && hasOut) {
        // reversal: exit and entry on the same bar — one reversal marker
        if (visible) markers.push({
          time: tm, position: isL ? 'belowBar' : 'aboveBar',
          color: col, shape: 'circle', text: `${stratLabel[st]} ⟳ ${isL ? 'L' : 'S'}`, size: msize,
        });
      } else if (hasIn) {
        if (visible) markers.push({
          time: tm, position: isL ? 'belowBar' : 'aboveBar',
          color: col, shape: isL ? 'arrowUp' : 'arrowDown',
          text: `${stratLabel[st]} ${isL ? 'L' : 'S'}`, size: msize,
        });
      } else if (hasOut) {
        if (visible) markers.push({
          time: tm, position: isL ? 'aboveBar' : 'belowBar',
          color: col, shape: 'square', text: `${stratLabel[st]} ✕`, size: msize,
        });
      }
    }
    allTrades[st] = j;
  }
  window._signalMarkers = markers.sort((a, b) => a.time - b.time);
  candleSeries.setMarkers([...window._signalMarkers, ...(pineOverlay.markers || [])].sort((a, b) => a.time - b.time));
  renderTradeLines();

  const inp = document.getElementById('sigcapt');
  if (inp && allTrades[active]) {
    const ls = allTrades[active].signals;
    const last = ls.length ? ls[ls.length - 1] : null;
    if (last) inp.value = t('misc.lastSignal', { side: last.side.toUpperCase(), close: fmt(last.close), entry: fmt(last.entry ?? last.close), stop: fmt(last.stop) });
  }
}

// ── Dotted trade lines (entry→exit) ────────────────
let tradeLines = [];
let journalTrades = [];
let highlightedIdx = null;

function clearTradeLines() {
  tradeLines.forEach(l => { try { candleSeries.removePriceLine(l); } catch (e) {} });
  tradeLines = [];
}

function renderTradeLines() {
  clearTradeLines();
  if (!journalTrades.length) return;
  // show only trades of the visible (active) strategy
  journalTrades.forEach((tr, i) => {
    if (tr.entry == null || tr.exit == null) return;
    const isL = tr.side === 'long';
    const isSel = i === highlightedIdx;
    const col = isSel ? (isL ? '#00e5a0' : '#ff5b5b') : (isL ? 'rgba(38,166,154,.6)' : 'rgba(239,83,80,.6)');
    const w = isSel ? 2 : 1;
    tradeLines.push(candleSeries.createPriceLine({
      price: tr.entry, color: col, lineWidth: w,
      lineStyle: LightweightCharts.LineStyle.Dotted,
      axisLabelVisible: isSel, title: `${t2('misc.entry')} ${isL ? 'L' : 'S'}`,
    }));
    tradeLines.push(candleSeries.createPriceLine({
      price: tr.exit, color: isSel ? '#e0e6ef' : 'rgba(158,158,158,.5)', lineWidth: w,
      lineStyle: LightweightCharts.LineStyle.Dotted,
      axisLabelVisible: isSel, title: `${t2('misc.exit')} ${isL ? 'L' : 'S'}`,
    }));
  });
}

function highlightTrade(i) {
  if (highlightedIdx === i) { highlightedIdx = null; selectTradeRow(-1); }
  else { highlightedIdx = i; selectTradeRow(i); }
  renderTradeLines();
}

function selectTradeRow(i) {
  document.querySelectorAll('.jtrade').forEach(e => e.classList.remove('selrow'));
  if (i < 0) return;
  const r = document.getElementById('jt-' + i);
  if (r) { r.classList.add('selrow'); r.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }
}

async function loadInstruments() {
  const r = await fetch(`${API}/api/instruments`);
  const { instruments } = await r.json();
  const byCat = {};
  instruments.forEach(i => (byCat[i.category] ||= []).push(i));
  const list = document.getElementById('list');
  list.innerHTML = '';
  for (const [cat, items] of Object.entries(byCat)) {
    const hdr = document.createElement('div');
    hdr.className = 'cat-hdr';
    hdr.innerHTML = `<span class="cat">${catTitles[cat] ? t(catTitles[cat]) : cat}</span><span class="plus" title="${t('misc.add')}">+</span>`;
    hdr.querySelector('.plus').onclick = () => { document.getElementById('insCat').value = cat; openModal('modalInst'); };
    list.appendChild(hdr);
    for (const it of items) {
      const d = document.createElement('div');
      d.className = 'inst' + (it.symbol === current.symbol ? ' active' : '');
      d.dataset.symbol = it.symbol;
      d.innerHTML = `<span class="sym">${it.symbol}</span><span><span class="px" data-px="${it.symbol}">—</span> <span class="del" title="${t('misc.delete')}">✕</span></span>`;
      d.onclick = (e) => { if (e.target.classList.contains('del')) return; selectSymbol(it.symbol); };
      d.querySelector('.del').onclick = (e) => { e.stopPropagation(); removeInstrument(it.symbol); };
      list.appendChild(d);
    }
  }
  instruments.forEach(i => refreshPrice(i));
}

function openModal(id) { document.getElementById(id).classList.add('open'); }
function closeModal(id) { document.getElementById(id).classList.remove('open'); }

async function openParams() {
  const s = current.strategy;
  const r = await fetch(`${API}/api/strategy-params/${s}?symbol=${encodeURIComponent(current.symbol)}&tf=${current.tf}`);
  const j = await r.json();
  document.getElementById('paramsTitle').textContent = `${t('params.title')}: ${s}`;
  document.getElementById('paramsScope').textContent =
    t('params.scope', { scope: `${current.symbol} · ${current.tf} · ${s}` });
  const form = document.getElementById('paramsForm');
  form.innerHTML = '';
  const riskKeys = ['use_tp', 'tp_pct', 'use_trail', 'trail_pct'];
  const renderRow = (k, v) => {
    const row = document.createElement('div');
    row.className = 'prow';
    const lbl = document.createElement('label');
    lbl.textContent = `${v.name} (${k})`;
    const inp = document.createElement('input');
    inp.dataset.key = k; inp.dataset.kind = v.kind;
    if (v.kind === 'bool') { inp.type = 'checkbox'; inp.checked = !!v.value; }
    else { inp.type = v.kind === 'int' || v.kind === 'float' ? 'number' : 'text'; inp.value = v.value; }
    if (j.saved && j.saved[k] !== undefined) {
      if (v.kind === 'bool') inp.checked = !!j.saved[k]; else inp.value = j.saved[k];
    }
    // ★ — save for the current instrument+TF only
    const star = document.createElement('button');
    star.type = 'button'; star.className = 'star'; star.textContent = '★';
    star.title = t('params.scope', { scope: `${k} · ${current.symbol} · ${current.tf}` });
    star.onclick = () => saveOneParam(k, v.kind, star);
    row.appendChild(lbl); row.appendChild(inp); row.appendChild(star);
    form.appendChild(row);
  };
  // main strategy parameters
  for (const [k, v] of Object.entries(j.params)) {
    if (riskKeys.includes(k)) continue;
    renderRow(k, v);
  }
  // risk add-ons (TP/trailing) — separate block
  const sep = document.createElement('div');
  sep.className = 'psep';
  sep.textContent = t('params.risk');
  form.appendChild(sep);
  for (const k of riskKeys) {
    if (j.params[k]) renderRow(k, j.params[k]);
  }
  openModal('modalParams');
}

// ★ — save ONE parameter for the current symbol×tf×strategy
async function saveOneParam(key, kind, btn) {
  const inp = document.querySelector(`#paramsForm input[data-key="${key}"]`);
  if (!inp) return;
  let val;
  if (kind === 'bool') val = inp.checked;
  else if (kind === 'int') val = parseInt(inp.value);
  else if (kind === 'float') val = parseFloat(inp.value);
  else val = inp.value;
  // take the already saved ones for this cell so the rest are not lost
  const rr = await fetch(`${API}/api/strategy-params/${current.strategy}?symbol=${encodeURIComponent(current.symbol)}&tf=${current.tf}`);
  const jj = await rr.json();
  const merged = Object.assign({}, jj.saved || {});
  merged[key] = val;
  await fetch(`${API}/api/strategy-params/${current.strategy}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol: current.symbol, tf: current.tf, params: merged }),
  });
  btn.classList.add('on');
  setTimeout(() => btn.classList.remove('on'), 900);
  await loadSignals();
  await refreshJournalIfOpen();
}

async function saveParams() {
  const params = {};
  document.querySelectorAll('#paramsForm input').forEach(i => {
    if (i.dataset.kind === 'bool') params[i.dataset.key] = i.checked;
    else if (i.dataset.kind === 'int') params[i.dataset.key] = parseInt(i.value);
    else if (i.dataset.kind === 'float') params[i.dataset.key] = parseFloat(i.value);
    else params[i.dataset.key] = i.value;
  });
  await fetch(`${API}/api/strategy-params/${current.strategy}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol: current.symbol, tf: current.tf, params }),
  });
  closeModal('modalParams');
  await loadSignals();
  await refreshJournalIfOpen();
}

// Reload the journal if it is open (after params/TF/strategy change)
async function refreshJournalIfOpen() {
  const el = document.getElementById('journal');
  if (!el || !el.classList.contains('on')) return;
  await openJournal(current.symbol);
}

let whStrategies = [];

async function openWebhooks() {
  const sel = document.getElementById('whStrategy');
  const r = await fetch(`${API}/api/strategies`);
  const { strategies } = await r.json();
  whStrategies = strategies;
  sel.innerHTML = strategies.map(s => `<option value="${s.key}">${s.title}</option>`).join('');
  sel.value = current.strategy;
  await refreshWhList();
  openModal('modalWh');
}

function esc(v) { return String(v == null ? '' : v).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

function webhookRow(w) {
  const d = document.createElement('div');
  d.className = 'wh';
  d.innerHTML = `<span>#${w.id} <b>${esc(w.strategy)}</b> · ${esc(w.symbol)} · ${esc(w.tf)} · ${esc(w.chat_id) || '—'}${w.thread_id ? ' · th' + w.thread_id : ''} ${w.enabled ? '✅' : '⛔'}</span>`;
  const box = document.createElement('span');
  const edit = document.createElement('span');
  edit.className = 'icn'; edit.textContent = '✎'; edit.title = t('wh.edit');
  edit.onclick = () => startEditWebhook(d, w);
  const del = document.createElement('span');
  del.className = 'icn del'; del.textContent = '✕'; del.title = t('wh.del');
  del.onclick = async () => {
    if (!confirm(t('wh.delConfirm', { id: w.id, strategy: w.strategy, symbol: w.symbol }))) return;
    await fetch(`${API}/api/webhooks/${w.id}`, { method: 'DELETE' });
    refreshWhList();
  };
  box.append(edit, del);
  d.appendChild(box);
  return d;
}

function startEditWebhook(d, w) {
  const opts = whStrategies.map(s => `<option value="${s.key}" ${s.key === w.strategy ? 'selected' : ''}>${s.title}</option>`).join('');
  const tfV = w.tf || '*';
  d.innerHTML = `<div class="whedit">
    <label>${t('wh.strategy')}<select class="e-strategy">${opts}</select></label>
    <label>${t('wh.symbol')}<input class="e-symbol" value="${esc(w.symbol || '*')}"></label>
    <label>${t('wh.tf')}<input class="e-tf" value="${esc(tfV)}" placeholder="*|15m|1h|4h|1d|1w|1M"></label>
    <label>Chat ID<input class="e-chat" value="${esc(w.chat_id || '')}" placeholder="${t('wh.chatPh')}"></label>
    <label>Thread ID<input class="e-thread" value="${w.thread_id != null ? w.thread_id : ''}" placeholder=""></label>
    <label>${t('wh.enabled')}<select class="e-enabled"><option value="1" ${w.enabled ? 'selected' : ''}>${t('wh.yes')}</option><option value="0" ${!w.enabled ? 'selected' : ''}>${t('wh.no')}</option></select></label>
    <span class="whbtns"><button class="cancel">${t('btn.cancel')}</button><button class="ok" style="background:var(--acc);color:#fff">${t('btn.save')}</button></span>
  </div>`;
  d.querySelector('.cancel').onclick = () => refreshWhList();
  d.querySelector('.ok').onclick = async () => {
    const g = c => d.querySelector(c).value;
    const body = {
      strategy: g('.e-strategy'),
      symbol: (g('.e-symbol') || '*').toUpperCase(),
      tf: g('.e-tf') || '*',
      chat_id: g('.e-chat') || null,
      thread_id: g('.e-thread') ? parseInt(g('.e-thread')) : null,
      enabled: g('.e-enabled') === '1',
    };
    const r = await fetch(`${API}/api/webhooks/${w.id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const j = await r.json().catch(() => ({}));
    if (!j.ok) alert(t('misc.noSave') + JSON.stringify(j));
    refreshWhList();
  };
}

async function refreshWhList() {
  const r = await fetch(`${API}/api/webhooks`);
  const { webhooks } = await r.json();
  const el = document.getElementById('whList');
  if (!webhooks.length) { el.innerHTML = `<div class="badge">${t('wh.none')}</div>`; return; }
  el.innerHTML = '';
  webhooks.forEach(w => el.appendChild(webhookRow(w)));
}

async function addWebhook() {
  const body = {
    strategy: document.getElementById('whStrategy').value,
    symbol: document.getElementById('whSymbol').value || '*',
    thread_id: document.getElementById('whThread').value ? parseInt(document.getElementById('whThread').value) : null,
  };
  const chat = document.getElementById('whChat').value;
  if (chat) body.chat_id = chat;
  await fetch(`${API}/api/webhooks`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  refreshWhList();
}

async function addInstrument() {
  const body = {
    symbol: document.getElementById('insSymbol').value,
    title: document.getElementById('insTitle').value || document.getElementById('insSymbol').value,
    category: document.getElementById('insCat').value,
    kind: document.getElementById('insKind').value,
    yahoo: document.getElementById('insYahoo').value || document.getElementById('insSymbol').value + '-USD',
  };
  const r = await fetch(`${API}/api/instruments`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (r.ok) { closeModal('modalInst'); loadInstruments(); }
  else { alert(t('misc.failed') + (await r.json()).detail); }
}

async function removeInstrument(sym) {
  if (!confirm(t('misc.delConfirm', { sym: sym }))) return;
  await fetch(`${API}/api/instruments/${sym}`, { method: 'DELETE' });
  loadInstruments();
}

async function refreshPrice(it) {
  try {
    const r = await fetch(`${API}/api/bars/${it.symbol}?tf=15m&limit=2&refresh=false`);
    const j = await r.json();
    const last = j.bars[j.bars.length - 1];
    document.querySelectorAll(`[data-px="${it.symbol}"]`).forEach(e => {
      e.textContent = last ? last.c.toFixed(last.c >= 100 ? 2 : 4) : '—';
    });
  } catch (e) {}
}

// ── Trade journal (right panel) ──────────────────────
let journalPeriod = 'all';

function fmtPx(v) {
  if (v == null) return '—';
  return Math.abs(v) >= 1000 ? v.toFixed(2) : v.toFixed(4);
}

async function openJournal(sym) {
  const el = document.getElementById('journal');
  el.classList.add('on');
  el.innerHTML = `<h2>${t('journal.title', { sym: '…' })}</h2>`;
  const { symbol, tf, strategy } = current;
  try {
    const r = await fetch(`${API}/api/trades/${sym}?strategy=${strategy}&tf=${tf}&period=${journalPeriod}`);
    const j = await r.json();
    renderJournal(sym, j);
  } catch (e) {
    // a journal render failure must not break the panel
    console.error('journal error:', e);
    el.innerHTML = `<h2>${t('journal.title', { sym: sym })} <span class="cls" onclick="closeJournal()">✕</span></h2>`
      + `<div class="jtrade"><span></span><span class="pxs">${t('journal.loadErr')}</span><span></span></div>`;
  }
}

function renderJournal(sym, j) {
  const el = document.getElementById('journal');
  const s = j.selected_period;
  const plCls = (s.pl_pct_sum || 0) >= 0 ? 'pos' : 'neg';
  const plTxt = (s.pl_pct_sum == null ? '—' : (s.pl_pct_sum >= 0 ? '+' : '') + s.pl_pct_sum.toFixed(2) + '%');
  const periods = ['current_month', 'month', 'year', 'all'].map(k => [k, t('period.' + k)]);
  let html = `<h2>${t('journal.title', { sym: sym })} <span class="cls" onclick="closeJournal()">✕</span></h2>`;
  html += `<div class="jsum">
    <div class="big ${plCls}" style="color:var(--${plCls === 'pos' ? 'up' : 'dn'})">${plTxt}</div>
    <div class="rowline"><span>${t('journal.plPeriod')}</span><span>${t('journal.trades', { n: s.count })}</span></div>
    <div class="rowline"><span>${t('journal.winrate')}</span><span>${s.win_rate == null ? '—' : s.win_rate + '%'}</span></div>
    <div class="rowline"><span>${t('journal.bestWorst')}</span><span>${s.best_pct == null ? '—' : s.best_pct + '% / ' + s.worst_pct + '%'}</span></div>
    <div class="rowline"><span>profit factor</span><span>${s.profit_factor == null ? '—' : s.profit_factor}</span></div>
  </div>`;
  html += `<div class="jperiod">` + periods.map(([k, t]) =>
    `<button class="${k === journalPeriod ? 'active' : ''}" onclick="setJournalPeriod('${k}', '${sym}')">${t}</button>`).join('') + `</div>`;

  if (j.open) {
    const o = j.open;
    const toStop = ((o.side === 'long' ? 1 : -1) * (o.stop / o.entry - 1) * 100).toFixed(2);
    html += `<div class="jopen">${t('journal.openPos')} <b class="${o.side === 'long' ? 'pos' : 'neg'}" style="color:var(--${o.side === 'long' ? 'up' : 'dn'})">${o.side.toUpperCase()}</b> @ ${fmtPx(o.entry)}<br><span class="pxs">${t('journal.entry', { dt: o.entry_dt || '—', stop: fmtPx(o.stop), pct: toStop })}</span></div>`;
  }

  if (!j.trades.length) html += `<div class="jtrade"><span></span><span class="pxs">${t('journal.noTrades')}</span><span></span></div>`;
  j.trades.forEach((t, i) => {
    const isL = t.side === 'long';
    const pos = (t.pl_pct || 0) > 0;
    html += `<div class="jtrade" id="jt-${i}" onclick="highlightTrade(${i})" style="cursor:pointer">
      <span class="dir ${isL ? 'long' : 'short'}">${isL ? 'LONG' : 'SHORT'}</span>
      <span><span class="pxs">${fmtPx(t.entry)} → ${fmtPx(t.exit)}</span>
        <div class="pxs" style="font-size:10px">${t.entry_dt} → ${t.exit_dt}</div></span>
      <span class="pl ${pos ? 'pos' : 'neg'}">${(t.pl_pct >= 0 ? '+' : '') + t.pl_pct.toFixed(2)}%</span>
    </div>`;
  });
  el.innerHTML = html;
  journalTrades = j.trades;
}

function selectTradeRow(i) {
  document.querySelectorAll('.jtrade').forEach(e => e.classList.remove('selrow'));
  const r = document.getElementById('jt-' + i);
  if (r) { r.classList.add('selrow'); r.scrollIntoView({ block: 'nearest' }); }
}

function setJournalPeriod(p, sym) {
  journalPeriod = p;
  openJournal(sym);
  const el = document.getElementById('journal');
  if (el) el.classList.add('on');
}

function closeJournal() {
  document.getElementById('journal').classList.remove('on');
}

async function selectSymbol(sym) {
  current.symbol = sym;
  document.querySelectorAll('.inst').forEach(e => e.classList.toggle('active', e.dataset.symbol === sym));
  document.getElementById('status').textContent = t('misc.loading', { sym: sym });
  await loadBars(true);
  await openJournal(sym);
}

async function loadBars(refresh, keepView) {
  const { symbol, tf } = current;
  // keep the current visible range so auto-refresh does not reset zoom/offset
  let savedRange = null;
  if (keepView && chart) {
    const lr = chart.timeScale().getVisibleLogicalRange();
    if (lr) savedRange = { from: lr.from, to: lr.to };
  }
  const r = await fetch(`${API}/api/bars/${symbol}?tf=${tf}&limit=500&refresh=${refresh}`);
  const j = await r.json();
  candleSeries.setData(toBars(j.bars));
  const showVol = document.getElementById('i-vol').checked;
  volumeSeries.setData(showVol ? toVolume(j.bars) : []);
  // horizontal volume profile: recompute bins on new data
  const cv = document.querySelector('#chart .hvolcanvas');
  if (cv) { cv._bins = computeBins(j.bars); syncHvolSize(); drawHorizontalVol(); }
  if (keepView && savedRange) {
    chart.timeScale().setVisibleLogicalRange(savedRange);
  } else {
    chart.timeScale().fitContent();
  }
  document.getElementById('status').textContent = t('misc.bars', { symbol: symbol, title: j.title, count: j.count });
  document.getElementById('srcline').textContent = t('misc.source', { src: j.source });
  await loadIndicators();
}

function initTfBar() {
  const bar = document.getElementById('tfbar');
  ['15m', '1h', '4h', '1d', '1w', '1M'].forEach(t => {
    const b = document.createElement('div');
    b.className = 'tf' + (t === current.tf ? ' active' : '');
    b.textContent = t;
    b.onclick = () => {
      current.tf = t;
      document.querySelectorAll('.tf').forEach(e => e.classList.toggle('active', e.textContent === t));
      loadBars(true);
    };
    bar.appendChild(b);
  });
}

async function loadStrategies() {
  const r = await fetch(`${API}/api/strategies`);
  const { strategies } = await r.json();
  const sel = document.getElementById('stratsel');
  sel.innerHTML = '';
  strategies.forEach(s => {
    const o = document.createElement('option');
    o.value = s.key; o.textContent = s.title;
    sel.appendChild(o);
  });
  sel.value = current.strategy;
  sel.onchange = () => { current.strategy = sel.value; loadSignals(); };
}

// ── Strategy editor (Python) ───────────────────────────────
let STRAT_SAMPLES = {};
let STRAT_COMPILED = [];

async function openPine() {
  const sel = document.getElementById('pnLoad');
  try {
    const r = await fetch(`${API}/api/strategy/samples`);
    const j = await r.json();
    STRAT_SAMPLES = j.samples || {};
    sel.innerHTML = `<option value="">${t('editor.samplePh')}</option>` +
      Object.keys(STRAT_SAMPLES).map(k => `<option value="${esc(k)}">${esc(k)}</option>`).join('');
  } catch (e) {}
  await loadSavedStrategies();
  document.getElementById('pnDiag').innerHTML = '';
  openModal('modalPine');
}

async function loadSavedStrategies() {
  try {
    const r = await fetch(`${API}/api/strategy/compiled`);
    const j = await r.json();
    STRAT_COMPILED = j.compiled || [];
    const sel = document.getElementById('pnSaved');
    if (sel) sel.innerHTML = `<option value="">${t('editor.choose')}</option>` +
      STRAT_COMPILED.map(s => `<option value="${esc(s.key)}">${esc(s.title)}</option>`).join('');
  } catch (e) {}
}

function pineLoadSample(k) {
  if (!k) return;
  document.getElementById('pnSrc').value = STRAT_SAMPLES[k] || '';
  if (!document.getElementById('pnName').value) document.getElementById('pnName').value = k.replace(/ \(.*\)$/, '');
}

function pinePickSaved(key) {
  if (!key) return;
  fetch(`${API}/api/strategy/export/${encodeURIComponent(key)}`)
    .then(r => r.json())
    .then(j => {
      if (j.source) {
        document.getElementById('pnSrc').value = j.source;
        document.getElementById('pnName').value = j.title || key;
      }
    }).catch(() => {});
}

function pineRenderDiag(j) {
  const d = document.getElementById('pnDiag');
  let h = '';
  if (j.errors && j.errors.length) {
    h += j.errors.map(e => `<div style="color:var(--dn)">✖ ${t('editor.line', { n: e.line, msg: esc(e.msg) })}</div>`).join('');
  } else if (j.ok) {
    h += `<div style="color:var(--up)">${t('editor.checkOk')}</div>`;
  }
  if (j.dryrun) {
    const dr = j.dryrun;
    h += `<div style="color:var(--mut);margin-top:4px">${t('editor.dryrun', { symbol: dr.symbol, tf: dr.tf, bars: dr.bars, longs: dr.longs, shorts: dr.shorts, exits: dr.exits, trades: dr.trades, open: dr.has_open ? t('editor.open') : '' })}</div>`;
  }
  if (j.inputs && j.inputs.length) {
    h += `<div style="color:var(--mut);margin-top:4px">${t('editor.params', { list: j.inputs.map(i => esc(i.var) + '(' + esc(i.kind) + ')').join(', ') })}</div>`;
  }
  d.innerHTML = h;
}

async function pineValidate() {
  const body = { source: document.getElementById('pnSrc').value, symbol: current.symbol, tf: current.tf };
  const r = await fetch(`${API}/api/strategy/validate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  pineRenderDiag(j);
  return j;
}

// ── Render a strategy-indicator onto the chart ────────────────────
const pineOverlay = { lines: [], hlines: [], markers: [], active: null };

function pineClear() {
  for (const k in indLine) { try { chart.removeSeries(indLine[k]); } catch (e) {} }
  Object.keys(indLine).forEach(k => { if (k.startsWith('pine_')) delete indLine[k]; });
  pineOverlay.lines.forEach(s => { try { chart.removeSeries(s); } catch (e) {} });
  pineOverlay.lines = [];
  pineOverlay.hlines.forEach(s => { try { chart.removeSeries(s); } catch (e) {} });
  pineOverlay.hlines = [];
  pineOverlay.markers = [];
  pineOverlay.active = null;
  if (candleSeries) candleSeries.setMarkers((window._signalMarkers || []));
}

async function pineApply() {
  const src = document.getElementById('pnSrc').value;
  const d = document.getElementById('pnDiag');
  pineClear();
  const r = await fetch(`${API}/api/strategy/indicator`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source: src, symbol: current.symbol, tf: current.tf }),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok || !j.ok) {
    pineRenderDiag({ ok: false, errors: j.errors || [{ line: 0, msg: j.detail || 'error' }] });
    return;
  }
  const tt = j.time;
  let nLine = 0, nShape = 0, nHline = 0;
  const markers = [];
  for (const p of (j.plots || [])) {
    if (p.kind === 'line') {
      const s = (p.style === 'histogram')
        ? chart.addHistogramSeries({ color: p.color, priceLineVisible: false, lastValueVisible: false })
        : chart.addLineSeries({ color: p.color, lineWidth: p.width || 1, priceLineVisible: false, lastValueVisible: false });
      if (p.style === 'histogram') {
        s.setData(p.data.map((v, i) => v == null ? null : { time: Math.floor(tt[i] / 1000), value: v }).filter(Boolean));
      } else {
        s.setData(seriesData(p.data, tt));
      }
      pineOverlay.lines.push(s); nLine++;
    } else if (p.kind === 'shape') {
      const loc = p.location || 'abovebar';
      const below = ['belowbar', 'below_bar', 'bottom'].includes(loc);
      for (let i = 0; i < (p.data || []).length; i++) {
        if (!p.data[i]) continue;
        markers.push({
          time: Math.floor(tt[i] / 1000),
          position: below ? 'belowBar' : 'aboveBar',
          color: p.color,
          shape: p.shape === 'triangleup' ? 'arrowUp' : p.shape === 'triangledown' ? 'arrowDown'
               : p.shape === 'square' ? 'square' : 'circle',
          text: p.title || '',
        });
      }
      pineOverlay.markers.push(...markers); nShape++;
    } else if (p.kind === 'hline') {
      const s = chart.addLineSeries({ color: p.color, lineWidth: 1, lineStyle: 2,
        priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
      s.setData(tt.map(x => ({ time: Math.floor(x / 1000), value: p.value })));
      pineOverlay.hlines.push(s); nHline++;
    }
  }
  const base = window._signalMarkers || [];
  candleSeries.setMarkers([...base, ...markers].sort((a, b) => a.time - b.time));
  pineOverlay.active = document.getElementById('pnName').value.trim() || 'indicator';
  d.innerHTML = `<div style="color:var(--up)">${t('editor.added', { lines: nLine, shapes: nShape, hlines: nHline })}</div>`;
}

async function pineCompile() {
  const name = document.getElementById('pnName').value.trim() || 'Strategy';
  const src = document.getElementById('pnSrc').value;
  const v = await pineValidate();
  if (!v.ok) { alert(t('editor.checkFail')); return; }
  const r = await fetch(`${API}/api/strategy/compile`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, source: src }) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok || !j.ok) { pineRenderDiag({ ok: false, errors: j.errors || [{ line: 0, msg: j.detail || 'error' }] }); return; }
  pineRenderDiag({ ok: true, inputs: j.inputs });
  document.getElementById('pnDiag').innerHTML += `<div style="color:var(--up);margin-top:4px">${t('editor.compiled', { title: esc(j.title), key: esc(j.key) })}</div>`;
  await loadStrategies();
  await loadSavedStrategies();
}

// ── Strategy export / import (sharing) ───────────────────────
function exportStrategy() {
  const src = document.getElementById('pnSrc').value.trim();
  let name = document.getElementById('pnName').value.trim();
  if (!name && !src) { alert(t('editor.needName')); return; }
  if (!name) name = 'strategy';
  const key = name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'strategy';
  const chosen = document.getElementById('pnSaved').value;
  const useKey = (chosen && (!src || chosen === key)) ? chosen : key;
  window.open(`${API}/api/strategy/export/${encodeURIComponent(useKey)}`, '_blank');
}

function importStrategyFile(input) {
  const file = input.files && input.files[0];
  if (!file) return;
  const rd = new FileReader();
  rd.onload = async () => {
    let payload;
    try { payload = JSON.parse(rd.result); }
    catch (e) { alert(t('editor.importBad')); input.value = ''; return; }
    if (!payload || !payload.source) { alert(t('editor.importNoSource')); input.value = ''; return; }
    document.getElementById('pnSrc').value = payload.source;
    document.getElementById('pnName').value = payload.title || payload.name || 'imported';
    const r = await fetch(`${API}/api/strategy/import`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.ok) {
      pineRenderDiag({ ok: false, errors: j.errors || [{ line: 0, msg: j.detail || t('editor.importErr') }] });
    } else {
      pineRenderDiag({ ok: true, inputs: j.inputs });
      document.getElementById('pnDiag').innerHTML += `<div style="color:var(--up);margin-top:4px">${t('editor.imported', { title: esc(j.title), key: esc(j.key) })}</div>`;
      await loadStrategies();
      await loadSavedStrategies();
    }
    input.value = '';
  };
  rd.readAsText(file);
}

// ── Strategy documentation (per language) ────────────────────
function mdToHtml(md) {
  const lines = md.split('\n');
  let html = '', inCode = false, inList = false;
  const inline = s => esc(s)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  const closeList = () => { if (inList) { html += '</ul>'; inList = false; } };
  for (const raw of lines) {
    const ln = raw.replace(/\s+$/, '');
    if (ln.startsWith('```')) { closeList(); inCode = !inCode; html += inCode ? '<pre><code>' : '</code></pre>'; continue; }
    if (inCode) { html += esc(raw) + '\n'; continue; }
    let m;
    if ((m = ln.match(/^#{1,3}\s+(.*)$/))) { closeList(); const lv = m[1] ? ln.match(/^#+/)[0].length : 1; html += `<h${lv}>${inline(m[1])}</h${lv}>`; continue; }
    if (/^\s*(-|\*)\s+/.test(ln)) { if (!inList) { html += '<ul>'; inList = true; } html += `<li>${inline(ln.replace(/^\s*(-|\*)\s+/, ''))}</li>`; continue; }
    if (/^\s*\d+\.\s+/.test(ln)) { closeList(); html += `<div>${inline(ln.trim())}</div>`; continue; }
    if (ln.trim() === '---') { closeList(); html += '<hr>'; continue; }
    if (ln.trim() === '') { closeList(); continue; }
    closeList(); html += `<p>${inline(ln)}</p>`;
  }
  closeList();
  if (inCode) html += '</code></pre>';
  return html;
}

async function openDocs() {
  const lang = (window.RTD_I18N && window.RTD_I18N.lang) || 'en';
  const body = document.getElementById('docsBody');
  body.innerHTML = `<p>${t('status.loading')}</p>`;
  openModal('modalDocs');
  try {
    const r = await fetch(`${API}/api/docs?lang=${lang}`);
    const j = await r.json();
    body.innerHTML = mdToHtml(j.markdown || '');
  } catch (e) {
    body.innerHTML = `<p>error</p>`;
  }
}

// ── Real trading (BingX) ──────────────────────────────
let _wantLive = false;

async function loadTradeSettings() {
  const r = await fetch(`${API}/api/trade/settings`);
  const { settings, keys } = await r.json();
  window._tradeKeys = keys;
  const live = document.getElementById('t-live');
  if (live) live.checked = !!settings.live_enabled;
  return { settings, keys };
}

async function openTrade() {
  const { settings, keys } = await loadTradeSettings();
  const warn = document.getElementById('trWarn');
  warn.textContent = keys.has_keys
    ? t('trade.keysOk', { mask: keys.api_key_masked, fund: keys.has_fund_pw ? t('trade.fundPwSet') : '' })
    : t('trade.keysNo');
  warn.style.color = keys.has_keys ? 'var(--up)' : 'var(--dn)';
  document.getElementById('trKeyMask').textContent = keys.api_key_masked || '—';
  document.getElementById('trApiKey').value = '';
  document.getElementById('trSecret').value = '';
  document.getElementById('trFundPw').value = '';
  document.getElementById('trEnv').value = keys.env || 'live';
  document.getElementById('trLev').value = settings.leverage;
  document.getElementById('trPct').value = settings.entry_pct;
  // Real-trade alerts: bot token + recipient TG id
  document.getElementById('trTgMask').textContent = keys.notify_token_masked || '—';
  document.getElementById('trNotifyToken').value = '';
  document.getElementById('trNotifyChat').value = keys.notify_chat_id || '';
  // E-mail alerts (optional SMTP)
  document.getElementById('trMailMask').textContent = keys.has_mail_pass ? keys.mail_pass_masked : '—';
  document.getElementById('trSmtpHost').value = keys.smtp_host || '';
  document.getElementById('trSmtpPort').value = keys.smtp_port || '';
  document.getElementById('trSmtpUser').value = keys.smtp_user || '';
  document.getElementById('trSmtpPass').value = '';
  document.getElementById('trSmtpTls').checked = keys.smtp_tls !== '0' && keys.smtp_tls !== 'false';
  document.getElementById('trNotifyEmail').value = keys.notify_email || '';
  openModal('modalTrade');
}

async function saveTrade() {
  const body = {
    leverage: parseInt(document.getElementById('trLev').value) || 5,
    entry_pct: parseFloat(document.getElementById('trPct').value) || 10,
    env: document.getElementById('trEnv').value,
  };
  const ak = document.getElementById('trApiKey').value.trim();
  const sk = document.getElementById('trSecret').value.trim();
  const fp = document.getElementById('trFundPw').value;
  if (ak) body.api_key = ak;
  if (sk) body.secret_key = sk;
  if (fp) body.fund_password = fp;
  const nt = document.getElementById('trNotifyToken').value.trim();
  const nc = document.getElementById('trNotifyChat').value.trim();
  if (nt) body.notify_bot_token = nt;
  if (nc) body.notify_chat_id = nc;
  // E-mail (SMTP) — saved only when provided; empty fields do NOT wipe existing.
  const sh = document.getElementById('trSmtpHost').value.trim();
  const sp = document.getElementById('trSmtpPort').value.trim();
  const su = document.getElementById('trSmtpUser').value.trim();
  const sw = document.getElementById('trSmtpPass').value;
  const se = document.getElementById('trNotifyEmail').value.trim();
  if (sh) body.smtp_host = sh;
  if (sp) body.smtp_port = sp;
  if (su) body.smtp_user = su;
  if (sw) body.smtp_pass = sw;
  if (se) body.notify_email = se;
  body.smtp_tls = document.getElementById('trSmtpTls').checked ? '1' : '0';
  // live_enabled is sent ONLY on an explicit toggle (protection: saving
  // other settings does not require the fund password again once live is on).
  if (_wantLive) body.live_enabled = true;
  const r = await fetch(`${API}/api/trade/settings`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { alert(t('misc.noSave') + (j.detail || JSON.stringify(j))); return; }
  _wantLive = false;
  if (j.keys) window._tradeKeys = j.keys;
  closeModal('modalTrade');
  await loadTradeSettings();
  await loadTradeAccount();
}

async function testNotify() {
  const r = await fetch(`${API}/api/trade/test-notify`, { method: 'POST' });
  const j = await r.json().catch(() => ({}));
  const ch = j.channels || {};
  const lines = [];
  if (ch.telegram) lines.push((ch.telegram.sent ? '✅ ' : '❌ ') + 'Telegram: ' + (ch.telegram.sent ? ch.telegram.chat : (ch.telegram.error || 'error')));
  if (ch.email) lines.push((ch.email.sent ? '✅ ' : '❌ ') + 'E-mail: ' + (ch.email.sent ? ch.email.to : (ch.email.error || 'error')));
  if (!lines.length) { alert(t('trade.testFail', { err: j.error || 'no channel configured' })); return; }
  alert(lines.join('\n'));
}

async function clearKeys() {
  if (!confirm(t('trade.clearConfirm'))) return;
  await fetch(`${API}/api/trade/keys/clear`, { method: 'POST' });
  await loadTradeSettings();
  await loadTradeAccount();
}

function onLiveToggle() {
  const cb = document.getElementById('t-live');
  if (cb.checked) {
    cb.checked = false;
    _wantLive = true;
    openTrade();
  } else {
    fetch(`${API}/api/trade/settings`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ live_enabled: false }) })
      .then(() => loadTradeSettings());
  }
}

async function loadTradeAccount() {
  const el = document.getElementById('acctbal');
  if (!el) return;
  const r = await fetch(`${API}/api/trade/account`);
  const j = await r.json();
  if (!j.connected) { el.textContent = t('acct.balance'); el.className = 'badge bal'; el.title = j.error || ''; return; }
  const b = j.balance || {};
  const eq = b.equity != null ? b.equity : b.balance;
  const pnl = j.pnl_realized_total;
  el.textContent = t('acct.balanceLine', { eq: eq == null ? '—' : (+eq).toFixed(2), pnl: (pnl >= 0 ? '+' : '') + pnl });
  el.className = 'badge bal ' + (pnl > 0 ? 'pos' : pnl < 0 ? 'neg' : '');
  el.title = t('acct.tooltip', { pnl: b.unrealizedProfit || '—', margin: b.availableMargin || '—' });
}

async function openTickers() {
  await refreshTkList();
  const sel = document.getElementById('tkSym');
  sel.innerHTML = `<option value="">${t('misc.loadingOpt')}</option>`;
  const r = await fetch(`${API}/api/trade/available`);
  const j = await r.json().catch(() => ({}));
  if (j.detail) { sel.innerHTML = `<option value="">${j.detail}</option>`; return; }
  const cur = new Set(tkCache.map(t => t.symbol));
  const opts = (j.available || []).filter(x => x.available && !cur.has(x.symbol));
  sel.innerHTML = `<option value="">${t('tickers.choose')}</option>` +
    opts.map(x => `<option value="${x.symbol}">${x.symbol} · ${x.bingx_symbol}</option>`).join('');
  openModal('modalTickers');
}

let tkCache = [];
async function refreshTkList() {
  const r = await fetch(`${API}/api/trade/tickers`);
  const { tickers } = await r.json();
  tkCache = tickers || [];
  const el = document.getElementById('tkList');
  if (!tkCache.length) { el.innerHTML = `<div class="badge">${t('tickers.empty')}</div>`; return; }
  el.innerHTML = '';
  tkCache.forEach(t => {
    const d = document.createElement('div');
    d.className = 'tk' + (t.enabled ? '' : ' off');
    d.innerHTML = `<span>${t.enabled ? '✅' : '⛔'} <b>${t.symbol}</b> · ${t.bingx_symbol} · ${t.category || ''}</span>`;
    const box = document.createElement('span');
    const tg = document.createElement('span'); tg.className = 'icn'; tg.textContent = t.enabled ? '⏸' : '▶'; tg.title = t2('tickers.toggle');
    tg.onclick = async () => { await fetch(`${API}/api/trade/tickers/${t.symbol}/toggle`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled: !t.enabled }) }); refreshTkList(); };
    const del = document.createElement('span'); del.className = 'icn del'; del.textContent = '✕'; del.title = t2('misc.delete');
    del.onclick = async () => { if (!confirm(t2('tickers.remove', { sym: t.symbol }))) return; await fetch(`${API}/api/trade/tickers/${t.symbol}`, { method: 'DELETE' }); refreshTkList(); };
    box.append(tg, del); d.appendChild(box); el.appendChild(d);
  });
}

async function addTicker() {
  const sym = document.getElementById('tkSym').value;
  if (!sym) return;
  const r = await fetch(`${API}/api/trade/tickers`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ symbol: sym }) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { alert(t2('tickers.notAdded') + (j.detail || JSON.stringify(j))); return; }
  await refreshTkList();
  await openTickers();
}

// Re-render dynamic (JS-generated) content when the language changes.
window.onLangChange = () => {
  try { loadInstruments(); } catch (e) {}
  const jr = document.getElementById('journal');
  if (jr && jr.classList.contains('on')) openJournal(current.symbol);
  const docs = document.getElementById('modalDocs');
  if (docs && docs.classList.contains('open')) openDocs();
  renderTradeLines();
};

(async function main() {
  initTheme();
  initChart(); initTfBar();
  await loadInstruments();
  await loadStrategies();
  await loadBars(true);
  // indicator toggles
  ['i-vma','i-ema','i-st','i-don','i-bb','i-rsi','i-macd','i-adx','i-sma50','i-sma200'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('change', loadIndicators);
  });
  const hvEl = document.getElementById('i-hvol');
  if (hvEl) hvEl.addEventListener('change', drawHorizontalVol);
  // trade-display toggles (STv3 / Rawa separately)
  ['s-stv3','s-rawa'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('change', loadSignals);
  });
  const volEl = document.getElementById('i-vol');
  if (volEl) volEl.addEventListener('change', () => {
    if (lastInd && lastInd._bars) volumeSeries.setData(volEl.checked ? toVolume(lastInd._bars) : []);
    else loadBars(false);
  });
  const liveEl = document.getElementById('t-live');
  if (liveEl) liveEl.addEventListener('change', onLiveToggle);
  await loadTradeSettings();
  await loadTradeAccount();
  setInterval(loadTradeAccount, 60000);
  setInterval(() => loadBars(true, true), 60000);
})();
