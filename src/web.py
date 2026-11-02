"""Builds docs/index.html - the one-page TechnoFunda Watchlist dashboard.

The page has everything built in (no server needed): SP and DT lists with marks,
200 EMA position and Chart buttons, today's changes, and the full history.
It is rebuilt after every robot run, so the hosted page always shows the latest data.
"""
import json
import os

from telegram import chart_url

OUT = os.path.join(os.path.dirname(__file__), "..", "docs", "index.html")

FRAGMENT = r"""<title>TechnoFunda Watchlist</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@75..100,600..800&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
/* Layout: sticky ledger header -> summary strip -> 4 tabs (SP · DT · Today · History) -> stock rows */
:root{
  --bg:#F2F4F7; --surface:#FFFFFF; --ink:#152033; --muted:#5D6878; --line:#DDE2E9;
  --accent:#2C47B8; --accent-soft:#E6EBFA;
  --up:#16794A; --up-soft:#E3F3EA; --down:#BE3329; --down-soft:#FBE7E5; --warn:#9A6408; --warn-soft:#FBF0DA;
  --f-display:"Archivo","Arial Narrow",system-ui,sans-serif;
  --f-body:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  --f-mono:"IBM Plex Mono",ui-monospace,"SF Mono",Menlo,monospace;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0D131B; --surface:#151D28; --ink:#E5EAF1; --muted:#93A0B1; --line:#253142;
  --accent:#93A8FF; --accent-soft:#1E2A4D;
  --up:#4FC48D; --up-soft:#15301F; --down:#F1786C; --down-soft:#3A1A17; --warn:#E5B456; --warn-soft:#352813;
  color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#0D131B; --surface:#151D28; --ink:#E5EAF1; --muted:#93A0B1; --line:#253142;
  --accent:#93A8FF; --accent-soft:#1E2A4D;
  --up:#4FC48D; --up-soft:#15301F; --down:#F1786C; --down-soft:#3A1A17; --warn:#E5B456; --warn-soft:#352813;
  color-scheme:dark}
*{box-sizing:border-box}
[hidden]{display:none!important}
body{background:var(--bg);color:var(--ink);font:15px/1.5 var(--f-body);margin:0}
body::before{content:"";position:fixed;inset:0 0 auto;height:env(safe-area-inset-top,0px);z-index:10;background:var(--surface)}
.wrap{max-width:1040px;margin:0 auto;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
header{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;background:var(--surface);border-bottom:1px solid var(--line)}
.hrow{display:flex;flex-wrap:wrap;gap:6px 16px;align-items:baseline;justify-content:space-between;padding-block:14px 10px}
h1{font:800 22px/1.1 var(--f-display);font-stretch:85%;letter-spacing:.01em;margin:0;text-transform:uppercase}
h1 span{color:var(--accent)}
.runline{color:var(--muted);font-size:12.5px;font-family:var(--f-mono)}
.tabs{display:flex;gap:2px;overflow-x:auto;scrollbar-width:none}
.tab{appearance:none;border:0;background:none;color:var(--muted);font:600 14px var(--f-body);padding:10px 14px 12px;cursor:pointer;border-bottom:3px solid transparent;white-space:nowrap}
.tab[aria-selected="true"]{color:var(--ink);border-bottom-color:var(--accent)}
.tab:focus-visible,button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.tab b{font:500 12px var(--f-mono);margin-left:6px;padding:1px 7px;border-radius:999px;background:var(--bg);color:var(--ink)}
main{padding-block:18px 56px}
.strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:18px}
.stat{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.stat .k{font-size:11.5px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted)}
.stat .v{font:700 26px/1.2 var(--f-display);font-variant-numeric:tabular-nums}
.stat .v small{font:500 13px var(--f-body);color:var(--muted);margin-left:4px}
.tools{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}
.tools input{flex:1 1 220px;min-width:0}
input,select{font:15px var(--f-body);color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:9px 11px}
.list{display:flex;flex-direction:column;gap:8px}
.row{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px 14px;display:grid;grid-template-columns:minmax(0,1.5fr) minmax(0,1fr) minmax(0,1.1fr) auto;gap:10px 18px;align-items:center}
.row.dt{border-left:4px solid var(--down)}
.nm{font-weight:600;line-height:1.3}
.linkish{appearance:none;border:0;background:none;padding:0;color:var(--ink);font:inherit;font-weight:600;text-align:left;cursor:pointer}
.linkish:hover{color:var(--accent)}
.meta{color:var(--muted);font-size:12.5px;margin-top:2px}
.sym{font-family:var(--f-mono);font-size:12.5px;color:var(--ink)}
.chips{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px}
.chip{font-size:11.5px;padding:1px 8px;border-radius:999px;background:var(--accent-soft);color:var(--accent);white-space:nowrap}
.num{font-family:var(--f-mono);font-variant-numeric:tabular-nums}
.px{font:500 15px var(--f-mono)}
.ema{font-size:12.5px;margin-top:2px}
.up{color:var(--up)}.down{color:var(--down)}.warn{color:var(--warn)}.mut{color:var(--muted)}
.mk{display:flex;flex-direction:column;gap:5px;min-width:0}
.mk .top{display:flex;justify-content:space-between;gap:8px;font-size:12.5px;color:var(--muted)}
.mk .top b{font:600 14px var(--f-mono);color:var(--ink)}
.bar{position:relative;height:8px;border-radius:4px;background:var(--bg);border:1px solid var(--line);overflow:hidden}
.bar i{position:absolute;inset:0 auto 0 0;background:var(--accent);border-radius:3px}
.bar.low i{background:var(--down)}
.bar u{position:absolute;top:-2px;bottom:-2px;width:2px;background:var(--ink);opacity:.55}
.acts{display:flex;gap:6px;justify-content:flex-end}
.btn{display:inline-flex;align-items:center;gap:4px;font:600 13px var(--f-body);padding:7px 11px;border-radius:8px;text-decoration:none;border:1px solid var(--line);color:var(--ink);background:var(--surface);cursor:pointer;white-space:nowrap}
.btn.pri{background:var(--accent);border-color:var(--accent);color:var(--surface)}
details{grid-column:1/-1}
summary{cursor:pointer;color:var(--muted);font-size:12.5px;list-style:none}
summary::-webkit-details-marker{display:none}
summary::before{content:"▸ ";}
details[open] summary::before{content:"▾ "}
.checks{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:6px;margin-top:8px}
.ck{display:flex;gap:8px;align-items:flex-start;font-size:13px;padding:7px 9px;border-radius:8px;background:var(--bg)}
.ck .ic{font-weight:700;width:16px;flex:none;text-align:center}
.ck .d{color:var(--muted);font-size:12px;font-family:var(--f-mono)}
.empty{background:var(--surface);border:1px dashed var(--line);border-radius:10px;padding:28px 16px;text-align:center;color:var(--muted)}
h2{font:700 15px var(--f-display);text-transform:uppercase;letter-spacing:.05em;margin:22px 0 8px;display:flex;gap:8px;align-items:center}
h2 .cnt{font:500 12px var(--f-mono);padding:1px 8px;border-radius:999px;background:var(--surface);border:1px solid var(--line)}
.ev{background:var(--surface);border:1px solid var(--line);border-radius:10px;display:flex;flex-direction:column}
.ev>div{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 12px;padding:10px 14px;border-top:1px solid var(--line);align-items:center}
.ev>div:first-child{border-top:0}
.ev .why{grid-column:1/2;color:var(--muted);font-size:12.5px;font-family:var(--f-mono);overflow-wrap:anywhere}
.pill{font:600 11px var(--f-body);letter-spacing:.04em;text-transform:uppercase;padding:2px 8px;border-radius:999px;white-space:nowrap}
.p-add{background:var(--up-soft);color:var(--up)}.p-dt{background:var(--down-soft);color:var(--down)}
.p-sp{background:var(--accent-soft);color:var(--accent)}.p-rem{background:var(--down-soft);color:var(--down)}
.p-warn{background:var(--warn-soft);color:var(--warn)}
.tbl{overflow-x:auto;background:var(--surface);border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%;min-width:640px;font-size:13.5px}
th,td{text-align:left;padding:9px 12px;border-top:1px solid var(--line);vertical-align:top}
th{border-top:0;font-size:11.5px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);font-weight:600}
td.r{color:var(--muted);font-family:var(--f-mono);font-size:12.5px}
.note{color:var(--muted);font-size:12.5px;margin-top:22px;max-width:70ch}
@media (max-width:720px){
  .row{grid-template-columns:minmax(0,1fr) auto}
  .row .mk{grid-column:1/-1;order:3}
  .row .acts{grid-column:1/-1;order:4;justify-content:flex-start}
  .row .pricecol{text-align:right}
}
@media (prefers-reduced-motion:no-preference){.bar i{transition:width .4s ease}}
/* Stock panel: slides in from the right on desktop, full screen on phones */
.scrim{position:fixed;inset:0;z-index:20;background:rgba(10,14,20,.45)}
.panel{position:fixed;z-index:21;top:0;right:0;bottom:0;width:min(760px,100%);background:var(--bg);display:flex;flex-direction:column;
  box-shadow:-12px 0 32px rgba(0,0,0,.18);padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
.ph{background:var(--surface);border-bottom:1px solid var(--line);padding:14px max(16px,env(safe-area-inset-right,0px)) 0 16px}
.ph-top{display:flex;gap:12px;align-items:flex-start;justify-content:space-between}
.ph h3{font:700 19px/1.2 var(--f-display);margin:0}
.ph .meta{margin-top:4px}
.x{appearance:none;border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:8px;width:36px;height:36px;font-size:18px;cursor:pointer;flex:none}
.ph-stats{display:flex;flex-wrap:wrap;gap:6px 16px;margin:10px 0 4px;font-size:13px;color:var(--muted)}
.ph-stats b{color:var(--ink);font:600 14px var(--f-mono)}
.ptabs{display:flex;gap:2px;margin-top:6px}
.pb{flex:1;overflow-y:auto;padding:16px max(16px,env(safe-area-inset-right,0px)) 24px 16px}
.ranges{display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap;align-items:center}
.rg{appearance:none;font:600 12.5px var(--f-body);padding:5px 10px;border-radius:999px;border:1px solid var(--line);background:var(--surface);color:var(--muted);cursor:pointer}
.rg[aria-pressed="true"]{background:var(--ink);color:var(--surface);border-color:var(--ink)}
.legend{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12.5px;color:var(--muted);margin-left:auto}
.legend i{display:inline-block;width:14px;height:3px;border-radius:2px;vertical-align:middle;margin-right:5px}
.chartbox{height:min(380px,52vh);background:var(--surface);border:1px solid var(--line);border-radius:10px;overflow:hidden}
.kgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px}
.kv{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:8px 10px}
.kv .k{font-size:11.5px;color:var(--muted)}
.kv .v{font:600 15px var(--f-mono);font-variant-numeric:tabular-nums}
.grp{font:700 12px var(--f-display);text-transform:uppercase;letter-spacing:.07em;color:var(--muted);margin:16px 0 6px}
.grp:first-child{margin-top:0}
.qt table{min-width:520px}
.qt td,.qt th{text-align:right;font-family:var(--f-mono);font-size:12.5px;white-space:nowrap}
.qt td:first-child,.qt th:first-child{text-align:left;font-family:var(--f-body)}
.plinks{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}
.src{color:var(--muted);font-size:12px;margin-top:10px}
@media (max-width:720px){.panel{width:100%;box-shadow:none}}

</style>

<header><div class="wrap">
  <div class="hrow"><h1>TechnoFunda <span>Watchlist</span></h1><div class="runline" id="runline"></div></div>
  <nav class="tabs" role="tablist" aria-label="Lists">
    <button class="tab" role="tab" data-v="sp" id="t-sp">SP<b id="c-sp">0</b></button>
    <button class="tab" role="tab" data-v="dt" id="t-dt">DT<b id="c-dt">0</b></button>
    <button class="tab" role="tab" data-v="today" id="t-today">Today<b id="c-today">0</b></button>
    <button class="tab" role="tab" data-v="history" id="t-history">History</button>
  </nav>
</div></header>

<main class="wrap">
  <section class="strip" id="strip" aria-label="Summary"></section>
  <section id="v-list">
    <div class="tools">
      <input id="q" type="search" placeholder="Search name or symbol" aria-label="Search name or symbol">
      <select id="sort" aria-label="Sort by">
        <option value="marks">Highest marks</option>
        <option value="ema">Closest to 200 EMA</option>
        <option value="new">Newest added</option>
        <option value="name">Name A–Z</option>
      </select>
    </div>
    <div class="list" id="list"></div>
  </section>
  <section id="v-today" hidden></section>
  <section id="v-history" hidden><div class="tbl"><table><thead><tr><th>Date</th><th>Stock</th><th>Change</th><th>Reason</th></tr></thead><tbody id="hist"></tbody></table></div></section>
  <p class="note" id="note"></p>
</main>

<div class="scrim" id="scrim" hidden></div>
<aside class="panel" id="panel" role="dialog" aria-modal="true" aria-labelledby="p-name" hidden>
  <div class="ph">
    <div class="ph-top"><div style="min-width:0"><h3 id="p-name"></h3><div class="meta" id="p-meta"></div></div>
      <button class="x" id="p-close" aria-label="Close">✕</button></div>
    <div class="ph-stats" id="p-stats"></div>
    <nav class="ptabs" role="tablist" aria-label="Stock details">
      <button class="tab" role="tab" data-p="chart">Chart</button>
      <button class="tab" role="tab" data-p="fund">Screener numbers</button>
      <button class="tab" role="tab" data-p="marks">Marks</button>
    </nav>
  </div>
  <div class="pb" id="p-body"></div>
</aside>

<script>
const D = __DATA__;
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const num = v => { const n = parseFloat(v); return isFinite(n) ? n : null; };
const FULL = D.cfg.full, PASS = D.cfg.pass_monthly;
const fmtINR = n => "₹" + n.toLocaleString("en-IN", {maximumFractionDigits: 2});

function marksOf(r){ const m = String(r.fund_result||"").match(/^([\d.]+)\s*\/\s*([\d.]+)/); return m ? +m[1] : null; }
function emaGap(r){ const c = num(r.last_close), e = num(r.ema200); return (c && e) ? (c - e) / e * 100 : null; }

function stockRow(r, list){
  const mk = marksOf(r), gap = emaGap(r), c = num(r.last_close);
  const pct = mk == null ? 0 : Math.min(100, mk / FULL * 100);
  const srcs = String(r.source||"").split(",").map(s => s.trim()).filter(Boolean);
  return `<article class="row ${list === "DT" ? "dt" : ""}">
    <div><button class="nm linkish" data-open="${esc(r.symbol)}" data-tab="chart">${esc(r.name || r.symbol)}</button>
      <div class="meta"><span class="sym">${esc(r.symbol)}</span> · added ${esc(r.added_on || "—")}</div>
      ${srcs.length ? `<div class="chips">${srcs.map(s => `<span class="chip">${esc(s)}</span>`).join("")}</div>` : ""}</div>
    <div class="pricecol"><div class="px">${c ? fmtINR(c) : "—"}</div>
      <div class="ema ${gap == null ? "mut" : gap >= 0 ? "up" : "down"}">${gap == null ? (c ? "New listing: under 200 days" : "200 EMA n/a") : (gap >= 0 ? "▲ " : "▼ ") + Math.abs(gap).toFixed(1) + "% " + (gap >= 0 ? "above" : "below") + " 200 EMA"}</div></div>
    <div class="mk"><div class="top"><span>Marks${r.last_fund_check ? " · " + esc(r.last_fund_check) : ""}</span><b>${mk == null ? "not marked yet" : mk + " / " + FULL}</b></div>
      <div class="bar ${mk != null && mk < PASS ? "low" : ""}" role="img" aria-label="${mk == null ? "No marks yet" : mk + " of " + FULL + " marks, pass mark " + PASS}"><i style="width:${pct}%"></i><u style="left:${PASS / FULL * 100}%"></u></div></div>
    <div class="acts"><button class="btn pri" data-open="${esc(r.symbol)}" data-tab="chart">Chart</button><button class="btn" data-open="${esc(r.symbol)}" data-tab="fund">Screener</button></div>
  </article>`;
}

let view = "sp";
function drawList(){
  const key = view === "dt" ? "DT" : "SP", q = document.getElementById("q").value.trim().toLowerCase();
  let rows = D[key].filter(r => (r.symbol + " " + r.name).toLowerCase().includes(q));
  const s = document.getElementById("sort").value;
  const by = {marks: r => -(marksOf(r) ?? -1), ema: r => Math.abs(emaGap(r) ?? 999), new: r => -Date.parse(r.added_on || 0), name: r => (r.name || r.symbol).toLowerCase()}[s];
  rows.sort((a, b) => { const x = by(a), y = by(b); return x < y ? -1 : x > y ? 1 : 0; });
  document.getElementById("list").innerHTML = rows.length ? rows.map(r => stockRow(r, key)).join("")
    : `<div class="empty">${q ? "No stock matches “" + esc(q) + "”." : key === "DT" ? "No stock is below its 200 EMA right now." : "SP is empty. Stocks that pass your marks will appear here after the next run."}</div>`;
}

function evBlock(title, pill, cls, items){
  if (!items || !items.length) return "";
  return `<h2>${title}<span class="cnt">${items.length}</span></h2><div class="ev">${items.map(([s, n, why]) =>
    `<div><div><b>${esc(n || s)}</b> <span class="sym mut">${esc(s)}</span></div><span class="pill ${cls}">${pill}</span>${why ? `<div class="why">${esc(why)}</div>` : ""}</div>`).join("")}</div>`;
}
function drawToday(){
  const r = D.run || {};
  const warn = [...(r.warnings || []).map(w => ["", "Robot", w]), ...(r.no_price || []).map(([s, n]) => [s, n, "No price data, 200 EMA not checked"]), ...(r.unchecked || [])];
  const html = [
    evBlock("Added to SP", "Added", "p-add", r.added),
    evBlock("Moved SP → DT", "Below EMA", "p-dt", r.to_dt),
    evBlock("Back to SP", "Above EMA", "p-sp", r.to_sp),
    evBlock("Removed in monthly review", "Removed", "p-rem", r.removed),
    evBlock("Marks updated (added by hand, or data was missing before)", "Marked", "p-sp", r.first_marked),
    evBlock("New listings (under 200 trading days, 200 EMA not possible yet)", "New listing", "p-sp", r.new_listing),
    evBlock("Checked but below pass marks", "Not added", "p-warn", r.rejected),
    evBlock("Needs attention", "Check", "p-warn", warn),
  ].join("");
  document.getElementById("v-today").innerHTML = html || `<div class="empty">No changes in the last run.</div>`;
}
function drawHistory(){
  document.getElementById("hist").innerHTML = D.history.length ? D.history.map(h =>
    `<tr><td class="num">${esc(h.date)}</td><td><b>${esc(h.name || h.symbol)}</b><br><span class="sym mut">${esc(h.symbol)}</span></td><td>${esc(h.action)}</td><td class="r">${esc(h.reason)}</td></tr>`).join("")
    : `<tr><td colspan="4" class="mut">No changes recorded yet.</td></tr>`;
}

// ---------------- Stock panel (Chart · Screener numbers · Marks), all inside this page
const LW_URL = "https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js";
let lwLoad = null, chartObj = null, cur = null, curTab = "chart", curRange = 260, curTf = "D";
const chartCache = {};
function loadLW(){
  if (window.LightweightCharts) return Promise.resolve();
  if (!lwLoad) lwLoad = new Promise((ok, fail) => { const sc = document.createElement("script"); sc.src = LW_URL; sc.onload = ok; sc.onerror = fail; document.head.appendChild(sc); });
  return lwLoad;
}
function loadChart(sym){
  if (D.charts) return Promise.resolve(D.charts[sym]);
  if (!chartCache[sym]) chartCache[sym] = fetch("charts/" + encodeURIComponent(sym) + ".json", {cache: "no-cache"})
    .then(r => r.ok ? r.json() : null).catch(() => null);
  return chartCache[sym];
}
const findRow = sym => { for (const k of ["SP", "DT"]) { const r = D[k].find(x => x.symbol === sym); if (r) return [r, k]; } return [null, null]; };
const tok = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const alpha = (hex, a) => /^#[0-9a-f]{6}$/i.test(hex) ? hex + Math.round(a * 255).toString(16).padStart(2, "0") : hex;
const fmtN = (v, d = 2) => v == null || !isFinite(v) ? "—" : Number(v).toLocaleString("en-IN", {maximumFractionDigits: d});

function openPanel(sym, tab){
  const [r, list] = findRow(sym); if (!r) return;
  cur = {r, list}; curTab = tab || "chart";
  const gap = emaGap(r), c = num(r.last_close), mk = marksOf(r);
  document.getElementById("p-name").textContent = r.name || r.symbol;
  document.getElementById("p-meta").innerHTML = `<span class="sym">${esc(r.symbol)}</span> · in <b>${list}</b> · added ${esc(r.added_on || "—")}`;
  document.getElementById("p-stats").innerHTML =
    `<span>Close <b>${c ? fmtINR(c) : "—"}</b></span>` +
    `<span>200 EMA <b>${num(r.ema200) ? fmtINR(num(r.ema200)) : "—"}</b></span>` +
    `<span class="${gap == null ? "" : gap >= 0 ? "up" : "down"}">${gap == null ? (c ? "New listing" : "") : (gap >= 0 ? "▲ " : "▼ ") + Math.abs(gap).toFixed(1) + "% vs EMA"}</span>` +
    `<span>Marks <b>${mk == null ? "—" : mk + " / " + FULL}</b></span>`;
  document.getElementById("scrim").hidden = false;
  document.getElementById("panel").hidden = false;
  document.body.style.overflow = "hidden";
  drawPanel();
  document.getElementById("p-close").focus();
}
function closePanel(){
  if (chartObj) { chartObj.remove(); chartObj = null; }
  document.getElementById("panel").hidden = true;
  document.getElementById("scrim").hidden = true;
  document.body.style.overflow = "";
  cur = null;
}
function drawPanel(){
  document.querySelectorAll("[data-p]").forEach(t => t.setAttribute("aria-selected", t.dataset.p === curTab));
  if (chartObj) { chartObj.remove(); chartObj = null; }
  const body = document.getElementById("p-body"), r = cur.r;
  const links = `<div class="plinks"><a class="btn" href="${esc(r.chart)}" target="_blank" rel="noopener">Open in TradingView ↗</a><a class="btn" href="${esc(r.screener)}" target="_blank" rel="noopener">Open full Screener page ↗</a></div>`;
  if (curTab === "chart") {
    body.innerHTML = `<div class="ranges" role="group" aria-label="Candle size">${[["D", "Daily"], ["W", "Weekly"], ["M", "Monthly"]].map(([k, l]) =>
        `<button class="rg" data-tf="${k}" aria-pressed="${k === curTf}">${l}</button>`).join("")}</div>
      <div class="ranges" role="group" aria-label="Period">${[["3M", 63], ["6M", 126], ["1Y", 260], ["3Y", 780], ["5Y", 1300], ["All", 0]].map(([l, n]) =>
        `<button class="rg" data-range="${n}" aria-pressed="${n === curRange}">${l}</button>`).join("")}
      <div class="legend" id="legend"></div></div>
      <div class="chartbox" id="chartbox"><div class="empty" style="border:0">Loading chart…</div></div>
      <div class="src" id="chartsrc"></div>` + links;
    drawChart();
  } else if (curTab === "fund") {
    body.innerHTML = fundHTML(D.fund[r.symbol]) + links;
  } else {
    let checks = []; try { checks = JSON.parse(r.marks_detail || "[]"); } catch (e) {}
    body.innerHTML = (checks.length ? `<div class="checks">${checks.map(([l, g, o, d]) =>
      `<div class="ck"><span class="ic ${g > 0 ? "up" : "down"}">${g > 0 ? "✓" : "✕"}</span><div><div>${esc(l)} <span class="num mut">${g}/${o}</span></div>${d ? `<div class="d">${esc(d)}</div>` : ""}</div></div>`).join("")}</div>
      <p class="src">Marks ${esc(r.fund_result || "")} · checked ${esc(r.last_fund_check || "—")} · pass mark ${PASS} / ${FULL}</p>`
      : `<div class="empty">Not marked yet. Marks appear after the next robot run.</div>`) + links;
  }
}
// Group daily candles into weekly or monthly ones
function resample(h, tf){
  const n = h.t.length, hasOHLC = !!(h.o && h.h && h.l), out = [];
  const key = t => { if (tf === "M") return t.slice(0, 7);
    const d = new Date(t + "T00:00:00Z"), day = (d.getUTCDay() + 6) % 7; d.setUTCDate(d.getUTCDate() - day); return d.toISOString().slice(0, 10); };
  for (let i = 0; i < n; i++) {
    const c = h.c[i]; if (c == null) continue;
    const o = hasOHLC && h.o[i] != null ? h.o[i] : c, hi = hasOHLC && h.h[i] != null ? h.h[i] : c, lo = hasOHLC && h.l[i] != null ? h.l[i] : c;
    const v = h.v ? (h.v[i] || 0) : 0, k = tf === "D" ? h.t[i] : key(h.t[i]), last = out[out.length - 1];
    if (last && last.k === k) { last.high = Math.max(last.high, hi); last.low = Math.min(last.low, lo); last.close = c; last.v += v; last.end = h.t[i]; }
    else out.push({k, time: tf === "D" ? h.t[i] : h.t[i], open: o, high: hi, low: lo, close: c, v, end: h.t[i]});
  }
  return out;
}
// Same EMA formula the robot uses (pandas ewm, adjust=True)
function ema(vals, span){
  const a = 2 / (span + 1); let num = 0, den = 0; return vals.map(v => { num = v + (1 - a) * num; den = 1 + (1 - a) * den; return num / den; });
}
async function drawChart(){
  const box = document.getElementById("chartbox"), sym = cur.r.symbol;
  let h;
  try { h = await loadChart(sym); await loadLW(); }
  catch (e) { box.innerHTML = `<div class="empty" style="border:0">The chart library could not load. Check your internet connection, or use Open in TradingView below.</div>`; return; }
  if (!cur || cur.r.symbol !== sym || curTab !== "chart") return;
  if (chartObj) { chartObj.remove(); chartObj = null; }
  if (!h || !h.t || !h.t.length) { box.innerHTML = `<div class="empty" style="border:0">Chart appears after the next robot run (7 AM).</div>`; return; }
  box.innerHTML = "";
  const candles = !!(h.o && h.h && h.l), bars = resample(h, curTf);
  const ink = tok("--muted"), line = tok("--line"), up = tok("--up"), dn = tok("--down");
  chartObj = LightweightCharts.createChart(box, {
    autoSize: true,
    layout: {background: {type: "solid", color: tok("--surface")}, textColor: ink, fontFamily: tok("--f-body"), fontSize: 11},
    grid: {vertLines: {color: alpha(line, .6)}, horzLines: {color: alpha(line, .6)}},
    rightPriceScale: {borderColor: line, scaleMargins: {top: .06, bottom: .24}}, timeScale: {borderColor: line},
    localization: {priceFormatter: p => p < 0 ? "" : "₹" + Number(p).toLocaleString("en-IN", {maximumFractionDigits: 2})},
    handleScroll: {vertTouchDrag: false},
  });
  let main;
  if (candles) {
    main = chartObj.addCandlestickSeries({upColor: up, downColor: dn, borderVisible: false, wickUpColor: up, wickDownColor: dn, priceLineVisible: false});
    main.setData(bars.map(b => ({time: b.time, open: b.open, high: b.high, low: b.low, close: b.close})));
  } else {
    main = chartObj.addAreaSeries({lineColor: tok("--accent"), topColor: alpha(tok("--accent"), .28), bottomColor: alpha(tok("--accent"), 0), lineWidth: 2, priceLineVisible: false});
    main.setData(bars.map(b => ({time: b.time, value: b.close})));
  }
  if (h.v) {
    const vol = chartObj.addHistogramSeries({priceFormat: {type: "volume"}, priceScaleId: "", lastValueVisible: false, priceLineVisible: false});
    vol.priceScale().applyOptions({scaleMargins: {top: .8, bottom: 0}});
    vol.setData(bars.map(b => ({time: b.time, value: b.v, color: alpha(b.close >= b.open ? up : dn, .35)})));
  }
  const closes = bars.map(b => b.close), tfName = {D: "daily", W: "weekly", M: "monthly"}[curTf];
  const lines = [];
  if (bars.length >= 200) { const e = ema(closes, 200);
    chartObj.addLineSeries({color: tok("--warn"), lineWidth: 2, priceLineVisible: false}).setData(bars.map((b, i) => ({time: b.time, value: e[i]}))); lines.push(["--warn", "200 EMA"]); }
  if (bars.length >= 50) { const e = ema(closes, 50);
    chartObj.addLineSeries({color: ink, lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false}).setData(bars.map((b, i) => ({time: b.time, value: e[i]}))); lines.push(["--muted", "50 EMA"]); }
  document.getElementById("legend").innerHTML = (candles ? "" : `<span><i style="background:var(--accent)"></i>Close</span>`) +
    lines.map(([c, l]) => `<span><i style="background:var(${c})"></i>${l}</span>`).join("");
  const first = h.t[0], lastT = h.t[h.t.length - 1];
  document.getElementById("chartsrc").textContent =
    `${candles ? "Candles" : "Closing prices"} from ${first} to ${lastT} (${tfName}). ` +
    (curTf === "D" ? "" : `EMA lines here are on ${tfName} candles; the robot's SP/DT rule uses the daily 200 EMA. `) +
    (candles ? "" : "Open/high/low prices are not available for this stock, so a line chart is shown. ") +
    (bars.length < 200 ? "200 EMA appears once there are 200 candles." : "");
  cur.bars = bars;
  setRange();
}
function setRange(){
  if (!chartObj || !cur || !cur.bars || !cur.bars.length) return;
  const b = cur.bars, n = b.length;
  if (!curRange) { chartObj.timeScale().fitContent(); return; }
  const lastDay = new Date(b[n - 1].end + "T00:00:00Z"), from = new Date(lastDay);
  from.setUTCDate(from.getUTCDate() - Math.round(curRange * 7 / 5));
  const fromStr = from.toISOString().slice(0, 10), i = b.findIndex(x => x.end >= fromStr);
  chartObj.timeScale().setVisibleRange({from: b[Math.max(0, i)].time, to: b[n - 1].time});
}
function fundHTML(f){
  if (!f) return `<div class="empty">Screener numbers appear after the next robot run (7 AM).</div>`;
  const pc = v => v == null ? "—" : fmtN(v, 1) + "%";
  const kv = (k, v) => `<div class="kv"><div class="k">${k}</div><div class="v">${v}</div></div>`;
  const grp = (t, items) => `<div class="grp">${t}</div><div class="kgrid">${items.join("")}</div>`;
  const half = f.result_period_months === 6;
  let html =
    grp("Price & valuation", [kv("Market cap", f.market_cap != null ? "₹" + fmtN(f.market_cap, 0) + " Cr" : "—"),
      kv("Current price", f.price != null ? fmtINR(f.price) : "—"), kv("52W high / low", f.high_52w != null ? fmtN(f.high_52w, 0) + " / " + fmtN(f.low_52w, 0) : "—"),
      kv("Stock P/E", fmtN(f.pe, 1)), kv("Book value", f.book_value != null ? fmtINR(f.book_value) : "—"), kv("Dividend yield", pc(f.dividend_yield))]) +
    grp("Returns", [kv("ROCE", pc(f.roce)), kv("ROE", pc(f.roe)), kv("ROE 3 years", pc(f.roe_3y))]) +
    grp("Growth", [kv("Sales TTM", pc(f.sales_growth_ttm)), kv("Sales 3 years", pc(f.sales_growth_3y)), kv("Sales 5 years", pc(f.sales_growth_5y)),
      kv("Profit TTM", pc(f.profit_growth_ttm)), kv("Profit 3 years", pc(f.profit_growth_3y)), kv("Profit 5 years", pc(f.profit_growth_5y)),
      kv(half ? "Sales, latest half vs LY" : "Sales, latest qtr vs LY", pc(f.sales_growth_qtr_yoy)), kv(half ? "Profit, latest half vs LY" : "Profit, latest qtr vs LY", pc(f.profit_growth_qtr_yoy))]) +
    grp("Health", [kv("Debt / Equity", fmtN(f.debt_to_equity)), kv("Interest cover", f.interest_coverage == null ? "—" : f.interest_coverage >= 999 ? "No interest" : fmtN(f.interest_coverage, 1) + "×"),
      kv("CFO / Profit 5Y", fmtN(f.cfo_to_profit_5y)), kv("Debtor days", fmtN(f.debtor_days, 0)), kv("Working cap. days", fmtN(f.working_capital_days, 0)),
      kv("OPM latest " + (half ? "half" : "qtr"), pc(f.opm_latest_qtr)), kv("OPM last year", pc(f.opm_last_year)), kv("Net profit TTM", f.net_profit_ttm != null ? "₹" + fmtN(f.net_profit_ttm, 1) + " Cr" : "—")]) +
    grp("Shareholding", [kv("Promoters", pc(f.promoter_holding)), kv("Promoter change 1Y", f.promoter_change_1y != null ? (f.promoter_change_1y > 0 ? "+" : "") + fmtN(f.promoter_change_1y) + " pts" : "—"),
      kv("FII + DII", pc(f.fii_dii_latest)), kv("Shareholders", fmtN(f.shareholders_latest, 0))]);
  const q = f.quarters;
  if (q && q.t && q.t.length) {
    const row = (lab, arr, suf = "") => `<tr><td>${lab}</td>${q.t.map((_, i) => `<td>${arr && arr[i] != null ? fmtN(arr[i], 2) + suf : "—"}</td>`).join("")}</tr>`;
    html += `<div class="grp">${half ? "Half-yearly" : "Quarterly"} results (₹ Cr)</div><div class="tbl qt"><table><thead><tr><th></th>${q.t.map(t => `<th>${esc(t)}</th>`).join("")}</tr></thead><tbody>` +
      row("Sales", q.sales) + row("Net profit", q.profit) + row("OPM", q.opm, "%") + row("EPS (₹)", q.eps) + `</tbody></table></div>`;
  }
  return html + `<p class="src">From Screener.in · ${esc(f.basis || "")} figures · updated ${esc(f.as_of || "—")}</p>`;
}
document.addEventListener("click", e => {
  const o = e.target.closest("[data-open]"); if (o) { openPanel(o.dataset.open, o.dataset.tab); return; }
  const pt = e.target.closest("[data-p]"); if (pt && cur) { curTab = pt.dataset.p; drawPanel(); return; }
  const tf = e.target.closest("[data-tf]"); if (tf) { curTf = tf.dataset.tf;
    document.querySelectorAll("[data-tf]").forEach(b => b.setAttribute("aria-pressed", b === tf)); drawChart(); return; }
  const rg = e.target.closest("[data-range]"); if (rg) { curRange = +rg.dataset.range;
    document.querySelectorAll("[data-range]").forEach(b => b.setAttribute("aria-pressed", b === rg)); setRange(); return; }
});
document.getElementById("p-close").addEventListener("click", closePanel);
document.getElementById("scrim").addEventListener("click", closePanel);
document.addEventListener("keydown", e => { if (e.key === "Escape" && cur) closePanel(); });

function show(v){
  if (!["sp", "dt", "today", "history"].includes(v)) v = "sp";
  view = v;
  document.querySelectorAll(".tab").forEach(t => t.setAttribute("aria-selected", t.dataset.v === v));
  document.getElementById("v-list").hidden = !(v === "sp" || v === "dt");
  document.getElementById("v-today").hidden = v !== "today";
  document.getElementById("v-history").hidden = v !== "history";
  if (v === "sp" || v === "dt") drawList();
}

(function init(){
  const r = D.run || {};
  const changes = ["added", "to_dt", "to_sp", "removed"].reduce((n, k) => n + ((r[k] || []).length), 0);
  document.getElementById("c-sp").textContent = D.SP.length;
  document.getElementById("c-dt").textContent = D.DT.length;
  document.getElementById("c-today").textContent = changes;
  document.getElementById("runline").textContent = r.run_at ? "Last run " + r.run_at + (r.price_date ? " · prices of " + r.price_date : "") : "Waiting for first run";
  const stat = (k, v, sub, cls) => `<div class="stat"><div class="k">${k}</div><div class="v ${cls || ""}">${v}${sub ? `<small>${sub}</small>` : ""}</div></div>`;
  const avg = l => { const m = l.map(marksOf).filter(x => x != null); return m.length ? (m.reduce((a, b) => a + b, 0) / m.length).toFixed(1) : "—"; };
  document.getElementById("strip").innerHTML =
    stat("SP · above 200 EMA", D.SP.length, "stocks") +
    stat("DT · below 200 EMA", D.DT.length, "stocks", D.DT.length ? "down" : "") +
    stat("Changes in last run", changes, (r.added || []).length ? `${r.added.length} added` : "") +
    stat("Average marks (SP)", avg(D.SP), "/ " + FULL);
  document.getElementById("note").textContent =
    `New stocks need ${D.cfg.pass_new} of ${FULL} marks to enter SP; SP and DT stocks need ${PASS} of ${FULL} on the monthly review (1st of each month). ` +
    `The black line on each marks bar is the pass mark. Marks shown are the automatic part of the TechnoFunda system, scaled to ${FULL}.` + (D.cfg.banner ? " " + D.cfg.banner : "");
  drawToday(); drawHistory();
  document.querySelectorAll(".tab").forEach(t => t.addEventListener("click", () => { location.hash = t.dataset.v; show(t.dataset.v); }));
  document.getElementById("q").addEventListener("input", drawList);
  document.getElementById("sort").addEventListener("change", drawList);
  window.addEventListener("hashchange", () => show(location.hash.slice(1)));
  show(location.hash.slice(1));
})();
</script>
"""

FULL_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
</head><body>
{fragment}
</body></html>
"""


def screener_url(symbol, consolidated="yes"):
    return f"https://www.screener.in/company/{symbol}/" + ("consolidated/" if consolidated != "no" else "")


def page_data(sp, dt, run, history, rules_cfg, banner="", snaps=None, charts=None):
    def rows(items):
        return [{**items[s], "symbol": s, "chart": chart_url(s),
                 "screener": screener_url(s, items[s].get("consolidated", "yes"))} for s in sorted(items)]
    return {
        "SP": rows(sp), "DT": rows(dt), "run": run or {}, "history": history or [],
        "fund": {k: v for k, v in (snaps or {}).items() if k in sp or k in dt},
        "charts": charts,  # None on the live site: the page loads charts/SYMBOL.json instead
        "cfg": {"full": rules_cfg.get("full_marks", 11), "pass_new": rules_cfg.get("new_stock_pass", 7),
                "pass_monthly": rules_cfg.get("monthly_pass", 7), "banner": banner},
    }


def render_fragment(data):
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return FRAGMENT.replace("__DATA__", blob)


def build(sp, dt, run, history, rules_cfg, out=None, snaps=None, charts=None):
    """Write the dashboard page. charts (price history) goes to charts.json next to it, loaded when a chart opens."""
    out = out or OUT
    os.makedirs(os.path.dirname(out), exist_ok=True)
    page = FULL_PAGE.replace("{fragment}", render_fragment(page_data(sp, dt, run, history, rules_cfg, snaps=snaps)))
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    if charts is not None:
        # one file per stock (docs/charts/SYMBOL.json), loaded only when that stock's chart is opened
        folder = os.path.join(os.path.dirname(out), "charts")
        os.makedirs(folder, exist_ok=True)
        for sym, hist in charts.items():
            if sym in sp or sym in dt:
                with open(os.path.join(folder, f"{sym}.json"), "w", encoding="utf-8") as f:
                    json.dump(hist, f, separators=(",", ":"))
        for name in os.listdir(folder):  # remove charts of stocks no longer in SP or DT
            if name.endswith(".json") and name[:-5] not in sp and name[:-5] not in dt:
                os.remove(os.path.join(folder, name))
        old = os.path.join(os.path.dirname(out), "charts.json")
        if os.path.exists(old):
            os.remove(old)
