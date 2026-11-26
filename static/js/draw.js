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

/* draw.js — drawing tools layer on top of the chart (TradingView-style).
 *
 * Own canvas layer above the chart container: lightweight-charts 4.x has no
 * drawing primitives, so we take coordinates from the chart itself:
 *   X: timeScale().timeToCoordinate(time) / logicalToCoordinate(logical)
 *   Y: series.priceToCoordinate(price)
 * Points are stored as {time, price, logical}; `logical` covers the empty area
 * to the right of the last bar, where no time exists yet.
 *
 * GROUPS: cursor · lines · shapes · fib · marks · measure · delete
 * PLUS: ruler (measure), magnet to OHLC, undo/redo, style panel for the
 * selected shape (colour / width / dash / duplicate / delete), Del, Ctrl+Z/Y.
 *
 * Storage: localStorage `rtd_draw_v1::<symbol>|<tf>` — markup is per
 * symbol × timeframe. Local to the browser; nothing is sent to the server.
 * Strings come from i18n.js (window.t), so the layer follows en/ru/es.
 */
(function () {
  'use strict';

  const PREFIX = 'rtd_draw_v1';
  const PALETTE = ['#3b82f6', '#ef5350', '#26a69a', '#f0b90b', '#cfd6e3',
                   '#a855f7', '#f97316', '#22d3ee'];
  const FIB = [
    { l: 0.000, c: '#9aa4b2' }, { l: 0.236, c: '#f23645' },
    { l: 0.382, c: '#ff9800' }, { l: 0.500, c: '#4caf50' },
    { l: 0.618, c: '#089981' }, { l: 0.786, c: '#2962ff' },
    { l: 1.000, c: '#9aa4b2' },
  ];
  const FIB_EXT = [0, 0.618, 1, 1.618, 2.618];
  const FIB_TIME = [0.382, 0.5, 0.618, 1, 1.618, 2.618];

  // ── описания инструментов ────────────────────────────────────
  const T = {
    select:   { icon: '↖', key: 'select',        need: 1 },
    trend:    { icon: '╱', key: 'trend',       need: 2 },
    ray:      { icon: '➚', key: 'ray',                   need: 2 },
    extline:  { icon: '↔', key: 'extline',      need: 2 },
    hline:    { icon: '─', key: 'hline',  need: 1 },
    vline:    { icon: '│', key: 'vline',    need: 1 },
    hray:     { icon: '⇥', key: 'hray',    need: 1 },
    arrow:    { icon: '➜', key: 'arrow',               need: 2 },
    channel:  { icon: '║', key: 'channel',    need: 3 },
    rect:     { icon: '▭', key: 'rect',         need: 2 },
    ellipse:  { icon: '◯', key: 'ellipse',                need: 2 },
    triangle: { icon: '△', key: 'triangle',           need: 3 },
    brush:    { icon: '✎', key: 'brush',                 need: 'brush' },
    fib:      { icon: 'F', key: 'fib',        need: 2 },
    fibext:   { icon: 'F', key: 'fibext',       need: 3 },
    fibfan:   { icon: 'F', key: 'fibfan',             need: 2 },
    fibtime:  { icon: 'F', key: 'fibtime',   need: 2 },
    text:     { icon: 'T', key: 'text',                 need: 1 },
    callout:  { icon: '◧', key: 'callout',               need: 1 },
    priceLabel: { icon: '▮', key: 'priceLabel',          need: 1 },
    arrowUp:  { icon: '▲', key: 'arrowUp',         need: 1 },
    arrowDown:{ icon: '▼', key: 'arrowDown',          need: 1 },
    ruler:    { icon: '⇔', key: 'ruler',               need: 2 },
    erase:    { icon: '⌫', key: 'erase',                need: 1 },
  };

  const GROUPS = [
    { id: 'cursor',  icon: '↖', gkey: 'gCursor',    tools: ['select'] },
    { id: 'lines',   icon: '╱', gkey: 'gLines',     tools: ['trend', 'ray', 'extline', 'hline', 'vline', 'hray', 'arrow', 'channel'] },
    { id: 'shapes',  icon: '▭', gkey: 'gShapes',    tools: ['rect', 'ellipse', 'triangle', 'brush'] },
    { id: 'fib',     icon: 'F', gkey: 'gFib', tools: ['fib', 'fibext', 'fibfan', 'fibtime'] },
    { id: 'marks',   icon: 'T', gkey: 'gMarks',     tools: ['text', 'callout', 'priceLabel', 'arrowUp', 'arrowDown'] },
    { id: 'measure', icon: '⇔', gkey: 'gMeasure', tools: ['ruler'] },
    { id: 'del',     icon: '⌫', gkey: 'gDel',  tools: ['erase'] },
  ];

  // ── состояние ────────────────────────────────────────────────
  let chart = null, series = null, host = null, cv = null, ctx = null, dpr = 1;
  let items = [], key = null, bars = [];
  let tool = 'none', color = PALETTE[0], width = 1.6, dash = false;
  let draft = null;          // {type, color, width, dash, pts:[...]}
  let sel = null;            // выделенная фигура
  let drag = null;           // перетаскивание
  let measure = null;        // {a, b} — линейка (не сохраняется)
  let hover = null, down = null, raf = 0;
  let magnet = true;
  let undoStack = [], redoStack = [];
  let bar = null, selPanel = null, drop = null;

  // ── локализация ──────────────────────────────────────────────
  // Строки берём из i18n.js; если движка нет — падаем на английский список.
  const FALLBACK = {
    'draw.select': 'Cursor / selection', 'draw.trend': 'Trend line', 'draw.ray': 'Ray',
    'draw.extline': 'Extended line', 'draw.hline': 'Horizontal line',
    'draw.vline': 'Vertical line', 'draw.hray': 'Horizontal ray',
    'draw.arrow': 'Arrow', 'draw.channel': 'Parallel channel',
    'draw.rect': 'Rectangle', 'draw.ellipse': 'Ellipse', 'draw.triangle': 'Triangle',
    'draw.brush': 'Brush', 'draw.fib': 'Fib retracement', 'draw.fibext': 'Fib extension',
    'draw.fibfan': 'Fib fan', 'draw.fibtime': 'Fib time zones', 'draw.text': 'Text',
    'draw.callout': 'Callout', 'draw.priceLabel': 'Price label',
    'draw.arrowUp': 'Arrow up', 'draw.arrowDown': 'Arrow down',
    'draw.ruler': 'Ruler', 'draw.erase': 'Eraser',
    'draw.gCursor': 'Cursor', 'draw.gLines': 'Lines', 'draw.gShapes': 'Shapes',
    'draw.gFib': 'Fibonacci', 'draw.gMarks': 'Marks', 'draw.gMeasure': 'Measure',
    'draw.gDel': 'Delete',
    'draw.label': 'drawing:', 'draw.width': 'Line width',
    'draw.dash': 'Dashed', 'draw.magnet': 'Magnet to OHLC',
    'draw.undo': 'Undo (Ctrl+Z)', 'draw.redo': 'Redo (Ctrl+Y)',
    'draw.clear': 'Clear all drawings',
    'draw.clearAsk': 'Delete all drawings ({n}) on {key}?',
    'draw.textAsk': 'Text on chart:', 'draw.calloutAsk': 'Callout text:',
    'draw.copy': 'Duplicate', 'draw.del': 'Delete (Del)',
    'draw.pick': 'choose', 'draw.on': 'on', 'draw.off': 'off',
    'draw.bars': '{n} {word}',
    'draw.bar.one': 'bar', 'draw.bar.few': 'bars',
    'draw.bar.many': 'bars', 'draw.bar.other': 'bars',
    'draw.durMin': '{v} min', 'draw.durHour': '{v} h', 'draw.durDay': '{v} d',
  };
  function tr(k, v) {
    let s2 = null;
    try { if (typeof window.t === 'function') s2 = window.t(k, v); } catch (e) { s2 = null; }
    if (s2 == null || s2 === k) s2 = FALLBACK[k] != null ? FALLBACK[k] : k;
    if (v) s2 = s2.replace(/\{(\w+)\}/g, (m, kk) => (v[kk] != null ? v[kk] : m));
    return s2;
  }
  const lang = () => {
    try { return (window.RTD_I18N && window.RTD_I18N.lang) || 'en'; } catch (e) { return 'en'; }
  };

  const $W = () => host.clientWidth;
  const $H = () => host.clientHeight;
  const ts = () => chart.timeScale();
  const need = t => T[t] ? T[t].need : 2;

  function curKey() {
    try { return (current.symbol || '?') + '|' + (current.tf || '?'); } catch (e) { return '?'; }
  }
  function load() {
    try { items = JSON.parse(localStorage.getItem(PREFIX + '::' + key) || '[]'); } catch (e) { items = []; }
    if (!Array.isArray(items)) items = [];
    undoStack = []; redoStack = [];
  }
  function save() {
    try { localStorage.setItem(PREFIX + '::' + key, JSON.stringify(items)); } catch (e) {}
  }
  const uid = () => 'd' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  const snap = () => JSON.stringify(items);

  function history() {
    undoStack.push(snap());
    if (undoStack.length > 80) undoStack.shift();
    redoStack = [];
    updateBarState();
  }
  function undo() {
    if (!undoStack.length) return;
    redoStack.push(snap());
    items = JSON.parse(undoStack.pop());
    sel = null; save(); updateStylePanel(); updateBarState(); schedule();
  }
  function redo() {
    if (!redoStack.length) return;
    undoStack.push(snap());
    items = JSON.parse(redoStack.pop());
    sel = null; save(); updateStylePanel(); updateBarState(); schedule();
  }

  // ── координаты ───────────────────────────────────────────────
  function xOf(p) {
    if (!p) return null;
    let x = null;
    if (p.time != null) { try { x = ts().timeToCoordinate(p.time); } catch (e) { x = null; } }
    if (x == null && p.logical != null) { try { x = ts().logicalToCoordinate(p.logical); } catch (e) { x = null; } }
    return x;
  }
  function yOf(p) {
    if (!p || p.price == null) return null;
    try { return series.priceToCoordinate(p.price); } catch (e) { return null; }
  }
  function ptFromXY(x, y) {
    let t = null, lg = null, pr = null;
    try { t = ts().coordinateToTime(x); } catch (e) { t = null; }
    try { lg = ts().coordinateToLogical(x); } catch (e) { lg = null; }
    try { pr = series.coordinateToPrice(y); } catch (e) { pr = null; }

    // магнит: тянем цену к ближайшему OHLC бара под курсором
    if (magnet && bars && bars.length && lg != null) {
      const i = Math.round(lg);
      const b = bars[i];
      if (b) {
        let best = null, bestD = 9;   // px
        for (const v of [b.o, b.h, b.l, b.c]) {
          const cy = series.priceToCoordinate(v);
          if (cy == null) continue;
          const d = Math.abs(cy - y);
          if (d < bestD) { bestD = d; best = v; }
        }
        if (best != null) pr = best;
        if (b.t != null) t = Math.floor(b.t / 1000);
      }
    }
    return { time: t, price: pr, logical: lg };
  }

  // ── отрисовка ────────────────────────────────────────────────
  function schedule() { if (!raf) raf = requestAnimationFrame(() => { raf = 0; paint(); }); }

  function paint() {
    if (!ctx) return;
    const k = curKey();
    if (k !== key) { key = k; draft = null; drag = null; sel = null; measure = null; load(); updateStylePanel(); updateBarState(); }
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, cv.width, cv.height);
    ctx.scale(dpr, dpr);
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';

    for (const it of items) drawOne(it, false);
    if (draft) drawOne(draftObj(), true);
    if (measure) drawMeasure();
    if (sel) drawSelection(sel);

    if (hover && tool !== 'none' && tool !== 'select' && tool !== 'erase' && !measure) {
      ctx.strokeStyle = 'rgba(150,180,255,0.55)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(hover[0] - 7, hover[1]); ctx.lineTo(hover[0] + 7, hover[1]);
      ctx.moveTo(hover[0], hover[1] - 7); ctx.lineTo(hover[0], hover[1] + 7);
      ctx.stroke();
    }
  }

  function anchors(it) {
    return (it.pts || []).map(p => {
      const x = xOf(p), y = yOf(p);
      return (x == null || y == null) ? null : [x, y];
    });
  }

  // черновик: pts + живая точка под курсором
  function draftObj() {
    const d = { id: 'draft', type: draft.type, color: draft.color, width: draft.width, dash: draft.dash, draft: true, pts: draft.pts.slice() };
    if (hover) {
      const p = ptFromXY(hover[0], hover[1]);
      if (d.type === 'brush') d.pts = d.pts.concat([p]);
      else if (d.pts.length < (need(d.type) === 'brush' ? 999 : need(d.type))) d.pts = d.pts.concat([p]);
    }
    return d;
  }

  function style(ctx, it) {
    ctx.strokeStyle = it.color || PALETTE[0];
    ctx.fillStyle = it.color || PALETTE[0];
    ctx.lineWidth = it.draft ? Math.max(1.2, (it.width || 1.6) - 0.4) : (it.width || 1.6);
    ctx.setLineDash(it.draft ? [6, 4] : (it.dash ? [5, 4] : []));
  }

  function drawOne(it, isDraft) {
    const a = anchors(it).filter(Boolean);
    if (!a.length) return;
    const W = $W(), H = $H();
    ctx.save();
    style(ctx, it);

    switch (it.type) {
      case 'hline': {
        const y = a[0][1];
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
        ctx.setLineDash([]); ctx.font = '11px system-ui, sans-serif';
        tagRight(it.pts[0].price, y);
        break;
      }
      case 'vline': {
        const x = a[0][0];
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke();
        break;
      }
      case 'hray': {
        const x = a[0][0], y = a[0][1];
        ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(W, y); ctx.stroke();
        ctx.setLineDash([]); tagRight(it.pts[0].price, y);
        break;
      }
      case 'trend':
      case 'ray':
      case 'extline':
      case 'arrow': {
        if (a.length < 2) { dot(a[0]); break; }
        let [x1, y1] = a[0], [x2, y2] = a[1];
        const dx = x2 - x1, dy = y2 - y1;
        let ex1 = x1, ey1 = y1;
        if (it.type === 'ray' && Math.abs(dx) > 0.5) {
          const k = ((dx > 0 ? W : 0) - x1) / dx;
          x2 = x1 + dx * k; y2 = y1 + dy * k;
        } else if (it.type === 'extline' && Math.abs(dx) > 0.5) {
          // продлеваем в обе стороны до краёв
          const k1 = (0 - x1) / dx, k2 = (W - x1) / dx;
          const p1 = [x1 + dx * k1, y1 + dy * k1], p2 = [x1 + dx * k2, y1 + dy * k2];
          ex1 = p1[0]; ey1 = p1[1]; x2 = p2[0]; y2 = p2[1];
        }
        ctx.beginPath(); ctx.moveTo(ex1, ey1); ctx.lineTo(x2, y2); ctx.stroke();
        if (it.type === 'arrow') arrowHead(a[0], [x2, y2]);
        if (!isDraft) handles(a);
        break;
      }
      case 'channel': {
        if (a.length < 2) { dot(a[0]); break; }
        const A = a[0], B = a[1], C = a[2] || a[1];
        let ux = B[0] - A[0], uy = B[1] - A[1];
        const L = Math.hypot(ux, uy) || 1;
        ux /= L; uy /= L;
        const vx = C[0] - A[0], vy = C[1] - A[1];
        const proj = vx * ux + vy * uy;
        const off = [vx - proj * ux, vy - proj * uy];
        const A2 = [A[0] + off[0], A[1] + off[1]], B2 = [B[0] + off[0], B[1] + off[1]];
        ctx.globalAlpha = 0.10;
        ctx.beginPath(); ctx.moveTo(A[0], A[1]); ctx.lineTo(B[0], B[1]); ctx.lineTo(B2[0], B2[1]); ctx.lineTo(A2[0], A2[1]); ctx.closePath(); ctx.fill();
        ctx.globalAlpha = 1;
        ctx.beginPath(); ctx.moveTo(A[0], A[1]); ctx.lineTo(B[0], B[1]); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(A2[0], A2[1]); ctx.lineTo(B2[0], B2[1]); ctx.stroke();
        if (!isDraft) handles(a);
        break;
      }
      case 'rect': {
        if (a.length < 2) { dot(a[0]); break; }
        const x = Math.min(a[0][0], a[1][0]), y = Math.min(a[0][1], a[1][1]);
        const w = Math.abs(a[1][0] - a[0][0]), h = Math.abs(a[1][1] - a[0][1]);
        ctx.globalAlpha = 0.12; ctx.fillRect(x, y, w, h); ctx.globalAlpha = 1;
        ctx.strokeRect(x, y, w, h);
        if (!isDraft) handles(a);
        break;
      }
      case 'ellipse': {
        if (a.length < 2) { dot(a[0]); break; }
        const cx = (a[0][0] + a[1][0]) / 2, cy = (a[0][1] + a[1][1]) / 2;
        const rx = Math.abs(a[1][0] - a[0][0]) / 2, ry = Math.abs(a[1][1] - a[0][1]) / 2;
        ctx.beginPath(); ctx.ellipse(cx, cy, Math.max(rx, 1), Math.max(ry, 1), 0, 0, Math.PI * 2);
        ctx.globalAlpha = 0.10; ctx.fill(); ctx.globalAlpha = 1; ctx.stroke();
        if (!isDraft) handles(a);
        break;
      }
      case 'triangle': {
        if (a.length < 3) { a.forEach(dot); break; }
        ctx.beginPath(); ctx.moveTo(a[0][0], a[0][1]);
        ctx.lineTo(a[1][0], a[1][1]); ctx.lineTo(a[2][0], a[2][1]); ctx.closePath();
        ctx.globalAlpha = 0.10; ctx.fill(); ctx.globalAlpha = 1; ctx.stroke();
        if (!isDraft) handles(a);
        break;
      }
      case 'brush': {
        if (a.length < 2) { dot(a[0]); break; }
        ctx.beginPath(); ctx.moveTo(a[0][0], a[0][1]);
        for (let i = 1; i < a.length; i++) ctx.lineTo(a[i][0], a[i][1]);
        ctx.stroke();
        break;
      }
      case 'fib': {
        if (a.length < 2 || it.pts[1].price == null) { dot(a[0]); break; }
        const [x1, y1] = a[0], [x2, y2] = a[1];
        const xa = Math.min(x1, x2), xb = Math.max(x1, x2);
        ctx.font = '11px system-ui, sans-serif';
        for (const f of FIB) {
          const y = y1 + (y2 - y1) * f.l;
          ctx.strokeStyle = f.c; ctx.globalAlpha = 0.85;
          ctx.beginPath(); ctx.moveTo(xa, y); ctx.lineTo(xb, y); ctx.stroke();
          ctx.globalAlpha = 1; ctx.fillStyle = f.c;
          const pr = it.pts[0].price + (it.pts[1].price - it.pts[0].price) * f.l;
          ctx.fillText(`${(f.l * 100).toFixed(1)}%  ${short(pr)}`, xb + 4, y + 3);
        }
        ctx.strokeStyle = it.color;
        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
        if (!isDraft) handles(a);
        break;
      }
      case 'fibext': {
        if (a.length < 3) { a.forEach(dot); break; }
        const [, ] = a[0];
        const A = a[0], B = a[1], C = a[2];
        const dpr = it.pts[1].price - it.pts[0].price;
        const base = it.pts[2].price;
        ctx.font = '11px system-ui, sans-serif';
        for (const r of FIB_EXT) {
          const pr = base + dpr * r;
          const y = series.priceToCoordinate(pr);
          if (y == null) continue;
          ctx.strokeStyle = r === 0 ? '#9aa4b2' : (r === 1 ? '#089981' : it.color);
          ctx.globalAlpha = 0.8;
          ctx.beginPath(); ctx.moveTo(Math.min(B[0], C[0]), y); ctx.lineTo($W(), y); ctx.stroke();
          ctx.globalAlpha = 1; ctx.fillStyle = ctx.strokeStyle;
          ctx.fillText(`${r.toFixed(3)}  ${short(pr)}`, Math.min(B[0], C[0]) + 4, y - 3);
        }
        ctx.strokeStyle = it.color; ctx.globalAlpha = 1;
        ctx.beginPath(); ctx.moveTo(A[0], A[1]); ctx.lineTo(B[0], B[1]); ctx.stroke();
        if (!isDraft) handles(a);
        break;
      }
      case 'fibfan': {
        if (a.length < 2 || it.pts[1].price == null) { dot(a[0]); break; }
        const [x1, y1] = a[0];
        const x2 = a[1][0];
        const dprc = it.pts[1].price - it.pts[0].price;
        const xEnd = Math.max(x2, x1) + 40;
        ctx.font = '11px system-ui, sans-serif';
        for (const f of FIB) {
          const pr = it.pts[0].price + dprc * f.l;
          const y2 = series.priceToCoordinate(pr);
          if (y2 == null) continue;
          ctx.strokeStyle = f.c; ctx.globalAlpha = 0.8;
          ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(xEnd, y2); ctx.stroke();
          ctx.globalAlpha = 1;
        }
        if (!isDraft) handles(a);
        break;
      }
      case 'fibtime': {
        if (a.length < 2) { dot(a[0]); break; }
        const x1 = a[0][0], x2 = a[1][0];
        const step = x2 - x1;
        ctx.font = '10px system-ui, sans-serif';
        for (const f of FIB_TIME) {
          const x = x1 + step * f;
          if (x < -50 || x > $W() + 50) continue;
          ctx.globalAlpha = 0.75;
          ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, $H()); ctx.stroke();
          ctx.globalAlpha = 1;
          ctx.fillText(f.toFixed(3), x + 3, 12);
        }
        ctx.beginPath(); ctx.moveTo(x1, 0); ctx.lineTo(x1, $H()); ctx.stroke();
        if (!isDraft) handles(a);
        break;
      }
      case 'text': {
        if (!a[0]) break;
        ctx.font = '12px system-ui, sans-serif';
        const t = it.text || '';
        const w = ctx.measureText(t).width;
        ctx.globalAlpha = 0.18; ctx.fillRect(a[0][0] - 3, a[0][1] - 13, w + 8, 18); ctx.globalAlpha = 1;
        ctx.fillText(t, a[0][0], a[0][1] + 1);
        if (!isDraft) { ctx.strokeRect(a[0][0] - 3, a[0][1] - 13, w + 8, 18); handles(a); }
        break;
      }
      case 'callout': {
        if (!a[0]) break;
        ctx.font = '12px system-ui, sans-serif';
        const t = it.text || '';
        const w = Math.max(60, ctx.measureText(t).width + 16);
        const bx = a[0][0] + 12, by = a[0][1] - 46;
        ctx.beginPath(); ctx.moveTo(a[0][0], a[0][1]); ctx.lineTo(bx + 10, by + 34); ctx.stroke();
        ctx.globalAlpha = 0.92; ctx.fillStyle = '#131a24';
        rr(bx, by, w, 34, 6); ctx.fill();
        ctx.globalAlpha = 1; ctx.strokeStyle = it.color; rr(bx, by, w, 34, 6); ctx.stroke();
        ctx.fillStyle = it.color; ctx.fillText(t, bx + 8, by + 21);
        if (!isDraft) { handles(a); }
        break;
      }
      case 'priceLabel': {
        if (it.pts[0].price == null) break;
        tagRight(it.pts[0].price, a[0] ? a[0][1] : 30, true);
        break;
      }
      case 'arrowUp':
      case 'arrowDown': {
        if (!a[0]) break;
        const [x, y] = a[0];
        const s = 7, dir = it.type === 'arrowUp' ? -1 : 1;
        ctx.beginPath();
        ctx.moveTo(x, y); ctx.lineTo(x - s, y - dir * 13); ctx.lineTo(x + s, y - dir * 13);
        ctx.closePath(); ctx.globalAlpha = 0.9; ctx.fill(); ctx.globalAlpha = 1; ctx.stroke();
        break;
      }
      default:
        dot(a[0]);
    }
    ctx.restore();
  }

  function dot(p) { if (!p) return; ctx.beginPath(); ctx.arc(p[0], p[1], 2.5, 0, Math.PI * 2); ctx.fill(); }

  function handles(a) {
    ctx.save(); ctx.setLineDash([]);
    for (const p of a) {
      if (!p) continue;
      ctx.fillStyle = '#0e1117'; ctx.strokeStyle = 'rgba(180,200,255,0.9)'; ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.arc(p[0], p[1], 3, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    }
    ctx.restore();
  }

  function drawSelection(it) {
    const a = anchors(it).filter(Boolean);
    if (!a.length) return;
    ctx.save();
    ctx.setLineDash([3, 3]); ctx.strokeStyle = 'rgba(255,255,255,0.55)'; ctx.lineWidth = 1;
    const xs = a.map(p => p[0]), ys = a.map(p => p[1]);
    const x1 = Math.min(...xs) - 5, x2 = Math.max(...xs) + 5;
    const y1 = Math.min(...ys) - 5, y2 = Math.max(...ys) + 5;
    if (it.type === 'hline' || it.type === 'vline' || it.type === 'hray' || it.type === 'priceLabel') {
      // для бесконечных линий рамку не рисуем — только хэндлы
    } else {
      ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
    }
    ctx.restore();
    handles(a);
  }

  function arrowHead(from, to) {
    const ang = Math.atan2(to[1] - from[1], to[0] - from[0]);
    const L = 11, sp = 0.42;
    ctx.beginPath();
    ctx.moveTo(to[0], to[1]);
    ctx.lineTo(to[0] - L * Math.cos(ang - sp), to[1] - L * Math.sin(ang - sp));
    ctx.moveTo(to[0], to[1]);
    ctx.lineTo(to[0] - L * Math.cos(ang + sp), to[1] - L * Math.sin(ang + sp));
    ctx.stroke();
  }

  function rr(x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  function tagRight(price, y, big) {
    if (price == null || y == null) return;
    const txt = short(price);
    ctx.save(); ctx.setLineDash([]);
    ctx.font = (big ? 'bold 11px' : '11px') + ' system-ui, sans-serif';
    const w = ctx.measureText(txt).width + 10;
    const light = document.body.classList.contains('light');
    ctx.fillStyle = light ? 'rgba(37,99,235,0.92)' : 'rgba(59,130,246,0.92)';
    ctx.fillRect($W() - w, y - 9, w, 18);
    ctx.fillStyle = '#fff'; ctx.fillText(txt, $W() - w + 5, y + 4);
    ctx.restore();
  }

  function short(v) {
    if (v == null) return '—';
    const av = Math.abs(v);
    if (av >= 1000) return v.toLocaleString('ru-RU', { maximumFractionDigits: 1 });
    if (av >= 1) return v.toFixed(2);
    if (av >= 0.01) return v.toFixed(4);
    return v.toPrecision(4);
  }

  // ── линейка ──────────────────────────────────────────────────
  function drawMeasure() {
    const a = measure.a, b = measure.b;
    if (!a || !b) return;
    const x1 = xOf(a), y1 = yOf(a), x2 = xOf(b), y2 = yOf(b);
    if (x1 == null || y1 == null || x2 == null || y2 == null) return;

    const up = a.price <= b.price;
    const col = up ? '#26a69a' : '#ef5350';
    ctx.save();
    ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineWidth = 1.4;
    ctx.setLineDash([]);
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();

    ctx.globalAlpha = 0.10;
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y1); ctx.lineTo(x2, y2); ctx.closePath(); ctx.fill();
    ctx.globalAlpha = 1;

    ctx.setLineDash([3, 3]); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y1); ctx.moveTo(x2, y1); ctx.lineTo(x2, y2); ctx.stroke();
    ctx.setLineDash([]);

    const dPrice = b.price - a.price;
    const dPct = a.price ? (dPrice / a.price) * 100 : 0;
    const dBars = Math.abs((b.logical ?? 0) - (a.logical ?? 0));
    const dTime = (a.time != null && b.time != null) ? Math.abs(b.time - a.time) : null;

    const lines = [
      `${dPrice >= 0 ? '+' : ''}${short(dPrice)}  (${dPct >= 0 ? '+' : ''}${dPct.toFixed(2)}%)`,
      barsTxt(Math.round(dBars)) + (dTime != null ? ` · ${fmtDur(dTime)}` : ''),
    ];

    ctx.font = 'bold 12px system-ui, sans-serif';
    const w = Math.max(...lines.map(l => ctx.measureText(l).width)) + 16;
    const h = 40;
    let bx = x2 + 12, by = y2 + 12;
    if (bx + w > $W()) bx = x2 - w - 12;
    if (by + h > $H()) by = y2 - h - 12;
    ctx.fillStyle = up ? 'rgba(38,166,154,0.95)' : 'rgba(239,83,80,0.95)';
    rr(bx, by, w, h, 5); ctx.fill();
    ctx.fillStyle = '#fff';
    ctx.fillText(lines[0], bx + 8, by + 17);
    ctx.font = '11px system-ui, sans-serif';
    ctx.fillText(lines[1], bx + 8, by + 32);

    for (const p of [[x1, y1], [x2, y2]]) {
      ctx.beginPath(); ctx.arc(p[0], p[1], 3.2, 0, Math.PI * 2); ctx.fillStyle = '#fff'; ctx.fill();
      ctx.strokeStyle = col; ctx.lineWidth = 1.5; ctx.stroke();
    }
    ctx.restore();
  }

  // «5 bars» / «5 баров» / «5 barras» — форма выбирается по правилам языка
  function plural(n, base) {
    let form = 'other';
    try {
      if (typeof Intl !== 'undefined' && Intl.PluralRules) {
        form = new Intl.PluralRules(lang()).select(n);
      }
    } catch (e) { form = 'other'; }
    return tr('draw.' + base + '.' + form);
  }
  function barsTxt(n) {
    return tr('draw.bars', { n: n, word: plural(n, 'bar') });
  }
  function fmtDur(sec) {
    if (sec < 3600) return tr('draw.durMin', { v: Math.round(sec / 60) });
    if (sec < 86400) return tr('draw.durHour', { v: (sec / 3600).toFixed(1) });
    return tr('draw.durDay', { v: (sec / 86400).toFixed(1) });
  }

  // ── попадания ────────────────────────────────────────────────
  function distSeg(px, py, x1, y1, x2, y2) {
    const dx = x2 - x1, dy = y2 - y1, L = dx * dx + dy * dy;
    let t = L ? ((px - x1) * dx + (py - y1) * dy) / L : 0;
    t = Math.max(0, Math.min(1, t));
    return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
  }

  function hitTest(x, y, tol) {
    tol = tol || 7;
    for (let i = items.length - 1; i >= 0; i--) {
      const it = items[i], a = anchors(it).filter(Boolean);
      for (let j = 0; j < a.length; j++) {
        if (a[j] && Math.hypot(x - a[j][0], y - a[j][1]) <= tol + 3) return { item: it, idx: j };
      }
      const t = it.type;
      if (t === 'hline' && a[0] && Math.abs(y - a[0][1]) <= tol) return { item: it, idx: null };
      if ((t === 'vline') && a[0] && Math.abs(x - a[0][0]) <= tol) return { item: it, idx: null };
      if (t === 'hray' && a[0] && Math.abs(y - a[0][1]) <= tol && x >= a[0][0] - 4) return { item: it, idx: null };
      if ((t === 'trend' || t === 'extline' || t === 'arrow') && a[0] && a[1] && distSeg(x, y, a[0][0], a[0][1], a[1][0], a[1][1]) <= tol) return { item: it, idx: null };
      if (t === 'ray' && a[0] && a[1]) {
        let [x1, y1] = a[0], [x2, y2] = a[1];
        const dx = x2 - x1;
        if (Math.abs(dx) > 0.5) {
          const k = ((dx > 0 ? $W() : 0) - x1) / dx;
          x2 = x1 + dx * k; y2 = y1 + (y2 - y1) * k;
        }
        if (distSeg(x, y, x1, y1, x2, y2) <= tol) return { item: it, idx: null };
      }
      if (t === 'channel' && a[0] && a[1]) {
        if (distSeg(x, y, a[0][0], a[0][1], a[1][0], a[1][1]) <= tol) return { item: it, idx: null };
        if (a[2]) {
          if (distSeg(x, y, a[0][0], a[0][1], a[1][0], a[1][1]) <= tol) return { item: it, idx: null };
        }
      }
      if (t === 'rect' && a[0] && a[1]) {
        const x1 = Math.min(a[0][0], a[1][0]), x2 = Math.max(a[0][0], a[1][0]);
        const y1 = Math.min(a[0][1], a[1][1]), y2 = Math.max(a[0][1], a[1][1]);
        if (x >= x1 && x <= x2 && y >= y1 && y <= y2) return { item: it, idx: null };
      }
      if (t === 'ellipse' && a[0] && a[1]) {
        const cx = (a[0][0] + a[1][0]) / 2, cy = (a[0][1] + a[1][1]) / 2;
        const rx = Math.abs(a[1][0] - a[0][0]) / 2, ry = Math.abs(a[1][1] - a[0][1]) / 2;
        const v = ((x - cx) / Math.max(rx, 1)) ** 2 + ((y - cy) / Math.max(ry, 1)) ** 2;
        if (v <= 1.15) return { item: it, idx: null };
      }
      if (t === 'triangle' && a.length >= 3) {
        if (inPoly(x, y, a.slice(0, 3))) return { item: it, idx: null };
      }
      if (t === 'brush' && a.length >= 2) {
        for (let j = 1; j < a.length; j++) {
          if (distSeg(x, y, a[j - 1][0], a[j - 1][1], a[j][0], a[j][1]) <= tol) return { item: it, idx: null };
        }
      }
      if ((t === 'fib' || t === 'fibfan' || t === 'fibtime' || t === 'fibext') && a[0] && a[1]) {
        const xa = Math.min(a[0][0], a[1][0]) - 6, xb = Math.max(a[0][0], a[1][0]) + 6;
        if (x >= xa && x <= xb) {
          for (const f of FIB) {
            const yl = a[0][1] + (a[1][1] - a[0][1]) * f.l;
            if (Math.abs(y - yl) <= tol) return { item: it, idx: null };
          }
          if (distSeg(x, y, a[0][0], a[0][1], a[1][0], a[1][1]) <= tol) return { item: it, idx: null };
        }
      }
      if (t === 'text' && a[0]) {
        ctx.save(); ctx.font = '12px system-ui, sans-serif';
        const w = ctx.measureText(it.text || '').width + 8;
        ctx.restore();
        if (x >= a[0][0] - 4 && x <= a[0][0] + w && y >= a[0][1] - 14 && y <= a[0][1] + 5) return { item: it, idx: null };
      }
      if (t === 'callout' && a[0]) {
        if (Math.hypot(x - a[0][0], y - a[0][1]) <= 14) return { item: it, idx: null };
      }
      if ((t === 'arrowUp' || t === 'arrowDown') && a[0]) {
        if (Math.hypot(x - a[0][0], y - a[0][1]) <= 12) return { item: it, idx: null };
      }
    }
    return null;
  }

  function inPoly(x, y, a) {
    let inside = false;
    for (let i = 0, j = a.length - 1; i < a.length; j = i++) {
      const xi = a[i][0], yi = a[i][1], xj = a[j][0], yj = a[j][1];
      if (((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi)) inside = !inside;
    }
    return inside;
  }

  // ── взаимодействие ───────────────────────────────────────────
  function xy(e) {
    const r = host.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  }

  function setTool(t) {
    if (t === tool) { tool = 'none'; }
    else { tool = t; }
    draft = null; drag = null; down = null; measure = null; sel = null; hover = null;
    closeDropdown();
    cv.style.cursor = (tool === 'none') ? 'default' : (tool === 'erase' ? 'not-allowed' : 'crosshair');
    updateBarState(); updateStylePanel();
    schedule();
  }

  function onDown(e) {
    if (!chart || !cv) return;
    if (tool === 'none') { sel = null; updateStylePanel(); return; }

    const [x, y] = xy(e);
    const p = ptFromXY(x, y);

    // ── ластик ──
    if (tool === 'erase') {
      const h = hitTest(x, y, 9);
      if (h) { history(); items = items.filter(z => z !== h.item); save(); schedule(); }
      e.stopPropagation(); e.preventDefault();
      return;
    }

    // ── выбор/перетаскивание ──
    if (tool === 'select') {
      const h = hitTest(x, y, 9);
      if (!h) { sel = null; updateStylePanel(); schedule(); return; }
      e.stopPropagation(); e.preventDefault();
      sel = h.item;
      updateStylePanel();
      drag = { item: h.item, idx: h.idx, x0: x, y0: y, origXY: anchors(h.item), moved: false };
      schedule();
      return;
    }

    // ── измерения ──
    if (tool === 'ruler') {
      e.stopPropagation(); e.preventDefault();
      measure = { a: p, b: p };
      down = { x, y, mode: 'ruler' };
      schedule();
      return;
    }

    // ── инструменты с текстом ──
    if (tool === 'text' || tool === 'callout') {
      e.stopPropagation(); e.preventDefault();
      const t = prompt(tool === 'text' ? tr('draw.textAsk') : tr('draw.calloutAsk'), '');
      if (t && t.trim()) {
        history();
        items.push({ id: uid(), type: tool, color, width, dash, text: t.trim(), pts: [p] });
        save();
      }
      schedule();
      return;
    }

    // ── кисть ──
    if (tool === 'brush') {
      e.stopPropagation(); e.preventDefault();
      draft = { type: 'brush', color, width, dash, pts: [p] };
      down = { x, y, mode: 'brush' };
      hover = [x, y];
      schedule();
      return;
    }

    // ── одиночные клики ──
    if (need(tool) === 1) {
      e.stopPropagation(); e.preventDefault();
      history();
      items.push({ id: uid(), type: tool, color, width, dash, pts: [p] });
      save(); schedule();
      return;
    }

    // ── многоточечные (клик-клик или протяжка) ──
    e.stopPropagation(); e.preventDefault();
    if (!draft) {
      draft = { type: tool, color, width, dash, pts: [p] };
      down = { x, y, mode: 'multi', moved: false };
    } else {
      draft.pts.push(p);
      if (draft.pts.length >= need(draft.type)) commit();
    }
    hover = [x, y];
    schedule();
  }

  function onMove(e) {
    if (!chart) return;
    const [mx, my] = xy(e);

    if (tool === 'select') {
      if (!drag) return;
      e.stopPropagation();
      const it = drag.item;
      if (it.pts.length === 1) {
        it.pts[0] = ptFromXY(mx, my);
      } else if (drag.idx != null) {
        it.pts[drag.idx] = ptFromXY(mx, my);
      } else {
        const dx = mx - drag.x0, dy = my - drag.y0;
        for (let k = 0; k < it.pts.length; k++) {
          const o = drag.origXY[k];
          if (!o) continue;
          it.pts[k] = ptFromXY(o[0] + dx, o[1] + dy);
        }
      }
      drag.moved = true;
      schedule(); return;
    }

    if (tool === 'none') { if (hover) { hover = null; schedule(); } return; }

    if (tool === 'erase') { hover = [mx, my]; schedule(); return; }

    if (tool === 'ruler' && measure && down && down.mode === 'ruler') {
      e.stopPropagation();
      measure.b = ptFromXY(mx, my);
      schedule(); return;
    }

    if (draft && down && down.mode === 'brush') {
      e.stopPropagation();
      const p = ptFromXY(mx, my);
      const last = draft.pts[draft.pts.length - 1];
      const lp = last ? [xOf(last), yOf(last)] : null;
      if (!lp || Math.hypot(lp[0] - mx, lp[1] - my) > 2) draft.pts.push(p);
      hover = [mx, my];
      schedule(); return;
    }

    if (draft && down && down.mode === 'multi') {
      e.stopPropagation();
      if (Math.hypot(mx - down.x, my - down.y) > 5) down.moved = true;
      hover = [mx, my];
      schedule(); return;
    }

    hover = [mx, my];
    schedule();
  }

  function onUp(e) {
    if (!chart) return;
    if (drag) {
      if (drag.moved) { history(); save(); }
      drag = null;
      return;
    }
    if (tool === 'ruler' && down && down.mode === 'ruler') {
      down = null;
      // клик без протяжки — линейка не нужна
      if (measure && (xOf(measure.a) === xOf(measure.b))) measure = null;
      schedule(); return;
    }
    if (draft && down) {
      const mode = down.mode;
      if (mode === 'brush') { commit(); down = null; return; }
      if (mode === 'multi' && down.moved) {
        // протяжка: если точек меньше нужного — добавляем конечную
        const [mx, my] = xy(e);
        const p = ptFromXY(mx, my);
        while (draft && draft.pts.length < need(draft.type)) draft.pts.push(p);
        if (draft) commit();
        down = null;
      } else if (mode === 'multi' && !down.moved) {
        // обычный клик — ждём следующую точку
      }
    }
    down = null;
  }

  function commit() {
    if (!draft) return;
    if (draft.pts.length < Math.min(2, need(draft.type) === 'brush' ? 2 : need(draft.type))) {
      if (need(draft.type) !== 1) { draft = null; schedule(); return; }
    }
    history();
    items.push({ id: uid(), type: draft.type, color: draft.color, width: draft.width, dash: draft.dash, text: draft.text, pts: draft.pts.slice() });
    draft = null; hover = null;
    save(); schedule();
  }

  function onKey(e) {
    const tag = (e.target && e.target.tagName) || '';
    if (/INPUT|TEXTAREA|SELECT/.test(tag)) return;

    if (e.key === 'Escape') {
      if (draft) { draft = null; schedule(); }
      else if (measure) { measure = null; schedule(); }
      else if (sel) { sel = null; updateStylePanel(); schedule(); }
      else if (tool !== 'none') setTool('none');
      closeDropdown();
      return;
    }
    if ((e.key === 'Delete' || e.key === 'Backspace') && sel) {
      history();
      items = items.filter(z => z !== sel);
      sel = null; save(); updateStylePanel(); updateBarState(); schedule();
      e.preventDefault(); return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
      e.preventDefault();
      if (e.shiftKey) redo(); else undo();
      return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') {
      e.preventDefault(); redo(); return;
    }
    if (e.altKey && e.key.toLowerCase() === 'z') { e.preventDefault(); undo(); }
    if (e.altKey && e.key.toLowerCase() === 'y') { e.preventDefault(); redo(); }
  }

  // ── панель инструментов ──────────────────────────────────────
  function buildBar() {
    bar = document.createElement('div');
    bar.className = 'drawbar';

    const st = document.createElement('style');
    st.textContent = `
      .drawbar{display:flex;align-items:center;gap:3px;padding:4px 10px;background:var(--panel);
        border-bottom:1px solid var(--line);flex-shrink:0;overflow:visible;position:relative;z-index:8}
      .drawbar .lbl{font-size:11px;color:var(--mut);margin-right:3px;white-space:nowrap}
      .drawbar .grp{position:relative;display:flex;flex:0 0 auto}
      .drawbar button{width:28px;height:25px;padding:0;display:flex;align-items:center;justify-content:center;
        font-size:15px;line-height:1;border-radius:5px;background:var(--ctrl);color:var(--txt);
        border:1px solid transparent;cursor:pointer;flex:0 0 auto;position:relative}
      .drawbar button.act{background:var(--acc);color:#fff;border-color:var(--acc)}
      .drawbar button.hasvar::after{content:'';position:absolute;right:2px;bottom:1px;
        border-left:3px solid transparent;border-bottom:3px solid var(--mut)}
      .drawbar .sep{width:1px;height:18px;background:var(--line);margin:0 4px;flex:0 0 auto}
      .drawbar .sw{display:flex;gap:4px;align-items:center;flex:0 0 auto}
      .drawbar .sw i{width:13px;height:13px;border-radius:3px;cursor:pointer;
        border:1px solid rgba(255,255,255,.25);flex:0 0 auto}
      .drawbar .sw i.act{outline:2px solid var(--txt);outline-offset:1px}
      .drawbar .clr{color:#ef5350}
      .drawbar .spacer{flex:1 1 auto}
      /* толщина линии: кнопка «≣ N» + список с реальными линиями */
      .drawbar button.wbtn,.dstyle button.wbtn{width:auto;min-width:40px;gap:4px;padding:0 6px;font-size:13px}
      .wbtn .wnum{font-size:11px;font-weight:600;line-height:1}
      .wmenu{position:fixed;z-index:9999;background:var(--panel);border:1px solid var(--line);
        border-radius:7px;padding:5px;min-width:158px;box-shadow:0 10px 30px rgba(0,0,0,.45);
        display:flex;flex-direction:column;gap:2px}
      .wmenu b{font-size:10px;color:var(--mut);font-weight:600;padding:2px 6px;text-transform:uppercase}
      .wmenu a{display:flex;align-items:center;gap:10px;padding:6px 8px;border-radius:5px;
        font-size:12px;color:var(--txt);cursor:pointer;white-space:nowrap}
      .wmenu a:hover{background:var(--hover)}
      .wmenu a.act{background:var(--acc);color:#fff}
      .wmenu a .ln{width:54px;flex:0 0 auto;background:currentColor;border-radius:2px;min-height:1px}
      /* выпадающее меню группы */
      .dmenu{position:fixed;z-index:9999;background:var(--panel);border:1px solid var(--line);
        border-radius:7px;padding:4px;min-width:196px;box-shadow:0 10px 30px rgba(0,0,0,.45);
        display:flex;flex-direction:column;gap:1px}
      .dmenu b{font-size:10px;color:var(--mut);font-weight:600;padding:3px 8px;text-transform:uppercase}
      .dmenu a{display:flex;align-items:center;gap:8px;padding:6px 8px;border-radius:5px;
        font-size:12px;color:var(--txt);text-decoration:none;cursor:pointer;white-space:nowrap}
      .dmenu a:hover{background:var(--hover)}
      .dmenu a.act{background:var(--acc);color:#fff}
      .dmenu a span.i{width:18px;text-align:center;font-size:14px}
      /* панель стиля выделенной фигуры */
      .dstyle{display:none;align-items:center;gap:4px;flex:0 0 auto;padding:2px 6px;
        border:1px solid var(--acc);border-radius:6px;background:rgba(59,130,246,.10)}
      .dstyle.on{display:flex}
      .dstyle .nm{font-size:11px;color:var(--mut);white-space:nowrap;max-width:96px;overflow:hidden;text-overflow:ellipsis}
      .dstyle button.wbtn{min-width:34px}
      @media (max-width:1200px),(pointer:coarse){
        .drawbar{padding:4px 6px;gap:2px;overflow-x:auto;scrollbar-width:none}
        .drawbar .lbl{display:none}
        .drawbar button{width:34px;height:32px;font-size:16px}
        .drawbar button.wbtn{width:auto;min-width:44px;font-size:13px}
        .dmenu a{padding:10px 10px;font-size:14px}
        .dstyle .nm{display:none}
      }`;
    document.head.appendChild(st);

    const lbl = document.createElement('span');
    lbl.className = 'lbl'; lbl.textContent = tr('draw.label');
    bar.appendChild(lbl);

    for (const g of GROUPS) {
      const wrap = document.createElement('div');
      wrap.className = 'grp';
      const b = document.createElement('button');
      b.dataset.group = g.id;
      b.textContent = g.icon;
      b.title = tr('draw.' + g.gkey) + (g.tools.length > 1 ? ' (▾)' : '');
      if (g.tools.length > 1) b.classList.add('hasvar');
      b.onclick = ev => {
        ev.stopPropagation();
        if (g.tools.length === 1) { setTool(g.tools[0]); return; }
        openDropdown(g, b);
      };
      wrap.appendChild(b);
      bar.appendChild(wrap);
    }

    const sep1 = document.createElement('span'); sep1.className = 'sep'; bar.appendChild(sep1);

    const sw = document.createElement('div');
    sw.className = 'sw';
    PALETTE.forEach((c, i) => {
      const s = document.createElement('i');
      s.style.background = c;
      s.dataset.c = c;
      if (i === 0) s.classList.add('act');
      s.onclick = ev => {
        ev.stopPropagation();
        applyColor(c);
      };
      sw.appendChild(s);
    });
    bar.appendChild(sw);

    const sep2 = document.createElement('span'); sep2.className = 'sep'; bar.appendChild(sep2);

    // толщина линии — кнопка «≣ N» с выпадающим списком 1–4 px
    const widBtn = document.createElement('button');
    widBtn.className = 'wbtn';
    widBtn.dataset.role = 'width';
    widBtn.title = tr('draw.width') + ' (1–4 px)';
    widBtn.innerHTML = '≣<span class="wnum">2</span>';
    widBtn.onclick = ev => { ev.stopPropagation(); openWidthMenu(widBtn); };
    bar.appendChild(widBtn);

    const dBtn = document.createElement('button');
    dBtn.textContent = '┈'; dBtn.title = tr('draw.dash');
    dBtn.dataset.dash = '1';
    dBtn.onclick = ev => { ev.stopPropagation(); applyDash(); };
    bar.appendChild(dBtn);

    const magBtn = document.createElement('button');
    magBtn.textContent = '🧲'; magBtn.dataset.role = 'magnet';
    magBtn.title = tr('draw.magnet') + ' (' + tr('draw.on') + ')';
    magBtn.classList.add('act');
    magBtn.onclick = ev => {
      ev.stopPropagation();
      magnet = !magnet;
      magBtn.classList.toggle('act', magnet);
      magBtn.title = tr('draw.magnet') + ' (' + (magnet ? tr('draw.on') : tr('draw.off')) + ')';
    };
    bar.appendChild(magBtn);

    const sep3 = document.createElement('span'); sep3.className = 'sep'; bar.appendChild(sep3);

    const undoBtn = document.createElement('button');
    undoBtn.textContent = '↶'; undoBtn.title = tr('draw.undo');
    undoBtn.dataset.undo = '1'; undoBtn.dataset.role = 'undo';
    undoBtn.onclick = ev => { ev.stopPropagation(); undo(); };
    bar.appendChild(undoBtn);

    const redoBtn = document.createElement('button');
    redoBtn.textContent = '↷'; redoBtn.title = tr('draw.redo'); redoBtn.dataset.role = 'redo';
    redoBtn.dataset.redo = '1';
    redoBtn.onclick = ev => { ev.stopPropagation(); redo(); };
    bar.appendChild(redoBtn);

    const clr = document.createElement('button');
    clr.className = 'clr'; clr.textContent = '🗑'; clr.title = tr('draw.clear');
    clr.dataset.role = 'clear';
    clr.onclick = ev => {
      ev.stopPropagation();
      if (!items.length) return;
      if (!confirm(tr('draw.clearAsk', { n: items.length, key: curKey() }))) return;
      history(); items = []; sel = null; save(); updateStylePanel(); updateBarState(); schedule();
    };
    bar.appendChild(clr);

    const spacer = document.createElement('span'); spacer.className = 'spacer'; bar.appendChild(spacer);

    // панель стиля
    selPanel = document.createElement('div');
    selPanel.className = 'dstyle';
    selPanel.onclick = ev => ev.stopPropagation();
    const nm = document.createElement('span'); nm.className = 'nm'; nm.dataset.nm = '1';
    selPanel.appendChild(nm);

    const cSel = document.createElement('div'); cSel.className = 'sw';
    PALETTE.forEach(c => {
      const s = document.createElement('i'); s.style.background = c; s.style.width = '11px'; s.style.height = '11px';
      s.dataset.c = c;
      s.onclick = ev => { ev.stopPropagation(); applyColor(c); };
      cSel.appendChild(s);
    });
    selPanel.appendChild(cSel);

    const widSel = document.createElement('button');
    widSel.className = 'wbtn';
    widSel.dataset.role = 'widthSel';
    widSel.title = tr('draw.width') + ' (1–4 px)';
    widSel.innerHTML = '≣<span class="wnum">2</span>';
    widSel.onclick = ev => { ev.stopPropagation(); openWidthMenu(widSel); };
    selPanel.appendChild(widSel);

    const dashSel = document.createElement('button');
    dashSel.textContent = '┈'; dashSel.title = tr('draw.dash');
    dashSel.onclick = ev => { ev.stopPropagation(); applyDash(); };
    selPanel.appendChild(dashSel);

    const dupBtn = document.createElement('button');
    dupBtn.textContent = '⧉'; dupBtn.title = tr('draw.copy'); dupBtn.dataset.role = 'dup';
    dupBtn.onclick = ev => {
      ev.stopPropagation();
      if (!sel) return;
      history();
      const c = JSON.parse(JSON.stringify(sel));
      c.id = uid();
      for (const p of c.pts) { if (p.logical != null) p.logical += 4; }
      items.push(c); sel = c; save(); updateStylePanel(); schedule();
    };
    selPanel.appendChild(dupBtn);

    const delBtn = document.createElement('button');
    delBtn.textContent = '✕'; delBtn.title = tr('draw.del'); delBtn.className = 'clr';
    delBtn.dataset.role = 'del';
    delBtn.onclick = ev => {
      ev.stopPropagation();
      if (!sel) return;
      history();
      items = items.filter(z => z !== sel);
      sel = null; save(); updateStylePanel(); updateBarState(); schedule();
    };
    selPanel.appendChild(delBtn);

    bar.appendChild(selPanel);

    // строка — над графиком
    host.parentElement.insertBefore(bar, host);
  }

  let wdrop = null;
  function openWidthMenu(btn) {
    closeWidthMenu();
    if (drop) closeDropdown();
    const cur = Math.round((sel && sel.width) || width || 2);
    wdrop = document.createElement('div');
    wdrop.className = 'wmenu';
    const wcap = document.createElement('b');
    wcap.textContent = tr('draw.width');
    wdrop.appendChild(wcap);
    [1, 2, 3, 4].forEach(w => {
      const a = document.createElement('a');
      a.dataset.w = w;
      if (cur === w) a.classList.add('act');
      a.innerHTML = `<span class="ln" style="height:${w}px"></span>${w} px`;
      a.onclick = ev => { ev.stopPropagation(); applyWidth(w); closeWidthMenu(); };
      wdrop.appendChild(a);
    });
    document.body.appendChild(wdrop);
    const r = btn.getBoundingClientRect(), dr = wdrop.getBoundingClientRect();
    let left = r.left, top = r.bottom + 4;
    if (left + dr.width > window.innerWidth - 8) left = Math.max(8, window.innerWidth - dr.width - 8);
    if (top + dr.height > window.innerHeight - 8) top = Math.max(8, r.top - dr.height - 4);
    wdrop.style.left = left + 'px';
    wdrop.style.top = top + 'px';
    setTimeout(() => document.addEventListener('pointerdown', wclose, true), 0);
  }
  function wclose(e) { if (wdrop && !wdrop.contains(e.target)) closeWidthMenu(); }
  function closeWidthMenu() {
    if (wdrop) { wdrop.remove(); wdrop = null; }
    document.removeEventListener('pointerdown', wclose, true);
  }

  function openDropdown(g, btn) {
    closeDropdown();
    drop = document.createElement('div');
    drop.className = 'dmenu';
    const cap = document.createElement('b');
    cap.textContent = tr('draw.' + g.gkey);
    drop.appendChild(cap);
    for (const t of g.tools) {
      const a = document.createElement('a');
      a.dataset.t = t;
      if (t === tool) a.classList.add('act');
      const ic = document.createElement('span');
      ic.className = 'i'; ic.textContent = T[t].icon;
      a.appendChild(ic);
      a.appendChild(document.createTextNode(tr('draw.' + T[t].key)));
      a.onclick = ev => { ev.stopPropagation(); setTool(t); closeDropdown(); };
      drop.appendChild(a);
    }
    document.body.appendChild(drop);
    const r = btn.getBoundingClientRect();
    const dr = drop.getBoundingClientRect();
    let left = r.left, top = r.bottom + 4;
    if (left + dr.width > window.innerWidth - 8) left = window.innerWidth - dr.width - 8;
    if (top + dr.height > window.innerHeight - 8) top = Math.max(8, r.top - dr.height - 4);
    drop.style.left = left + 'px';
    drop.style.top = top + 'px';
    setTimeout(() => document.addEventListener('pointerdown', outsideClose, true), 0);
  }
  function outsideClose(e) {
    if (drop && !drop.contains(e.target)) closeDropdown();
  }
  function closeDropdown() {
    if (drop) { drop.remove(); drop = null; }
    document.removeEventListener('pointerdown', outsideClose, true);
  }

  // смена языка: переписать все подписи слоя (словари строятся один раз)
  function relabel() {
    if (!bar) return;
    const lbl = bar.querySelector('.lbl');
    if (lbl) lbl.textContent = tr('draw.label');
    const byRole = r => bar.querySelector(`[data-role="${r}"]`);
    const w1 = byRole('width'); if (w1) w1.title = tr('draw.width') + ' (1–4 px)';
    const w2 = byRole('widthSel'); if (w2) w2.title = tr('draw.width') + ' (1–4 px)';
    const dsh = bar.querySelector('button[data-dash]');
    if (dsh) dsh.title = tr('draw.dash');
    const dsh2 = selPanel && selPanel.querySelector('button[data-dash]');
    if (dsh2) dsh2.title = tr('draw.dash');
    const mg = byRole('magnet');
    if (mg) mg.title = tr('draw.magnet') + ' (' + (magnet ? tr('draw.on') : tr('draw.off')) + ')';
    const un = byRole('undo'); if (un) un.title = tr('draw.undo');
    const re = byRole('redo'); if (re) re.title = tr('draw.redo');
    const cl = byRole('clear'); if (cl) cl.title = tr('draw.clear');
    const dp = byRole('dup'); if (dp) dp.title = tr('draw.copy');
    const dl = byRole('del'); if (dl) dl.title = tr('draw.del');
    updateBarState();
    updateStylePanel();
  }

  function updateBarState() {
    if (!bar) return;
    for (const g of GROUPS) {
      const btn = bar.querySelector(`button[data-group="${g.id}"]`);
      if (!btn) continue;
      const inGroup = g.tools.includes(tool);
      btn.classList.toggle('act', inGroup);
      if (g.tools.length > 1) {
        // показываем иконку активного под-инструмента
        btn.textContent = inGroup ? T[tool].icon : g.icon;
        btn.title = tr('draw.' + g.gkey) + ' — ' +
          (inGroup ? tr('draw.' + T[tool].key) : tr('draw.pick')) + ' (▾)';
      } else {
        btn.textContent = g.icon;
        btn.title = inGroup ? (tr('draw.' + T[tool].key) + ' (' + tr('draw.on') + ')')
                            : tr('draw.' + g.gkey);
      }
    }
    const r = bar.querySelector('button[data-redo]');
    if (r) { r.style.opacity = redoStack.length ? '1' : '.4'; }
    const u = bar.querySelector('button[data-undo]');
    if (u) { u.style.opacity = undoStack.length ? '1' : '.4'; }
  }

  function updateStylePanel() {
    if (!selPanel) return;
    const on = !!(sel && tool === 'select');
    selPanel.classList.toggle('on', on);
    if (!on) return;
    const nm = selPanel.querySelector('[data-nm]');
    if (nm) nm.textContent = (T[sel.type] ? tr('draw.' + T[sel.type].key) : sel.type);
    selPanel.querySelectorAll('.sw i').forEach(i => i.classList.toggle('act', i.dataset.c === sel.color));
    const wn = selPanel.querySelector('button.wbtn .wnum');
    if (wn) wn.textContent = Math.round(sel.width || 2);
    const db = selPanel.querySelector('button[data-dash]');
    if (db) db.classList.toggle('act', !!sel.dash);
  }

  function applyColor(c) {
    color = c;
    if (bar) bar.querySelectorAll(':scope > .sw i').forEach(i => i.classList.toggle('act', i.dataset.c === c));
    if (sel) {
      history(); sel.color = c; save(); updateStylePanel(); schedule();
    }
    if (draft) { draft.color = c; schedule(); }
  }
  function applyWidth(w) {
    width = Math.min(4, Math.max(1, w));
    // цифра на кнопке «≣ N» всегда показывает текущую толщину
    if (bar) bar.querySelectorAll('button.wbtn .wnum').forEach(n => { n.textContent = width; });
    if (sel) {
      history(); sel.width = width; save(); updateStylePanel(); schedule();
    }
    if (draft) { draft.width = width; schedule(); }
  }
  function applyDash() {
    dash = !dash;
    if (bar) { const b = bar.querySelector('button[data-dash]'); if (b) b.classList.toggle('act', dash); }
    if (sel) {
      history(); sel.dash = dash; save(); updateStylePanel(); schedule();
    }
    if (draft) { draft.dash = dash; schedule(); }
  }

  // ── init / API ───────────────────────────────────────────────
  function init(opts) {
    chart = opts.chart; series = opts.series; host = opts.host;
    if (!chart || !series || !host) return;

    cv = document.createElement('canvas');
    cv.className = 'drawcanvas';
    cv.style.cssText = 'position:absolute;inset:0;z-index:4;pointer-events:none;touch-action:none';
    host.appendChild(cv);
    ctx = cv.getContext('2d');

    key = curKey(); load();
    buildBar();
    size();

    ts().subscribeVisibleLogicalRangeChange(() => schedule());
    new ResizeObserver(() => { size(); schedule(); }).observe(host);

    host.addEventListener('pointerdown', onDown, true);
    host.addEventListener('pointermove', onMove, true);
    window.addEventListener('pointerup', onUp, true);
    window.addEventListener('pointercancel', onUp, true);
    window.addEventListener('keydown', onKey);
    window.addEventListener('resize', () => { size(); schedule(); });

    updateBarState();
  }

  function size() {
    if (!cv || !host) return;
    dpr = window.devicePixelRatio || 1;
    const w = $W(), h = $H();
    cv.width = Math.max(1, Math.round(w * dpr));
    cv.height = Math.max(1, Math.round(h * dpr));
    cv.style.width = w + 'px';
    cv.style.height = h + 'px';
  }

  window.DrawTools = {
    init,
    setBars(b) { bars = b || []; },
    relabel,
    refresh(b) {
      if (b) bars = b;
      size();
      schedule();
    },
    paint: schedule,
  };
})();
