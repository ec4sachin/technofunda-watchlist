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
  --up:#16794A; --up-soft:#E3F3EA; --down:#BE3329; --down-soft:#FBE7E5; --warn:#9A6408; --warn-soft:#FBF0DA; --e10:#16A34A; --e20:#DC2626; --e50:#2563EB; --e200:#EA580C;
  --f-display:"Archivo","Arial Narrow",system-ui,sans-serif;
  --f-body:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  --f-mono:"IBM Plex Mono",ui-monospace,"SF Mono",Menlo,monospace;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0D131B; --surface:#151D28; --ink:#E5EAF1; --muted:#93A0B1; --line:#253142;
  --accent:#93A8FF; --accent-soft:#1E2A4D;
  --up:#4FC48D; --up-soft:#15301F; --down:#F1786C; --down-soft:#3A1A17; --warn:#E5B456; --warn-soft:#352813; --e10:#4ADE80; --e20:#F87171; --e50:#60A5FA; --e200:#FB923C;
  color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#0D131B; --surface:#151D28; --ink:#E5EAF1; --muted:#93A0B1; --line:#253142;
  --accent:#93A8FF; --accent-soft:#1E2A4D;
  --up:#4FC48D; --up-soft:#15301F; --down:#F1786C; --down-soft:#3A1A17; --warn:#E5B456; --warn-soft:#352813; --e10:#4ADE80; --e20:#F87171; --e50:#60A5FA; --e200:#FB923C;
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
.acts{display:flex;flex-direction:column;gap:6px;align-items:flex-end}
.acts .r1,.acts .r2{display:flex;gap:6px}
.btn.buy,.btn.sell{color:#fff;font:800 13px var(--f-display);justify-content:center;letter-spacing:.02em}
.acts .btn.buy,.acts .btn.sell{width:32px;height:28px;padding:0;border-radius:7px}
.btn.buy{background:#15803D;border-color:#15803D}.btn.sell{background:#C62828;border-color:#C62828}
.btn.buy:hover{background:#166534}.btn.sell:hover{background:#B71C1C}
.pos{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:4px 18px;align-items:baseline;border-top:1px dashed var(--line);padding-top:8px;font-size:13px;color:var(--muted);cursor:pointer;
  background:none;border-left:0;border-right:0;border-bottom:0;text-align:left;font-family:inherit}
.pos b{font:600 13.5px var(--f-mono);color:var(--ink)}
.pos .pl{font:700 13.5px var(--f-mono)}
.pos .tag{font:700 11px var(--f-body);letter-spacing:.06em;text-transform:uppercase;color:var(--accent)}
.pgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;margin-bottom:12px}
.order{position:fixed;z-index:26;left:50%;top:50%;transform:translate(-50%,-50%);width:min(420px,calc(100vw - 24px));max-height:calc(100vh - 24px);overflow:auto;
  background:var(--surface);border:1px solid var(--line);border-radius:14px;box-shadow:0 18px 50px rgba(0,0,0,.3)}
.order .oh{padding:14px 16px;color:#fff;display:flex;justify-content:space-between;align-items:center;gap:10px}
.order .oh.buy{background:#15803D}.order .oh.sell{background:#C62828}
.order .oh h3{margin:0;font:700 18px var(--f-display)}
.order .oh .x{background:rgba(255,255,255,.15);border-color:rgba(255,255,255,.35);color:#fff}
.order .ob{padding:14px 16px;display:flex;flex-direction:column;gap:12px}
.order .fr{display:grid;grid-template-columns:120px 1fr;gap:8px;align-items:center}
.order .fr label{font-size:13px;color:var(--muted)}
.order .seg{display:flex;gap:4px;flex-wrap:wrap}
.order .seg button{appearance:none;flex:1;border:1px solid var(--line);background:var(--bg);color:var(--ink);border-radius:8px;padding:7px 8px;font:600 13px var(--f-body);cursor:pointer}
.order .seg button[aria-pressed="true"]{background:var(--ink);color:var(--surface);border-color:var(--ink)}
.order .est{display:flex;justify-content:space-between;font-size:14px;border-top:1px solid var(--line);padding-top:10px}
.order .est b{font-family:var(--f-mono)}
.order .place{width:100%;justify-content:center;padding:11px;font-size:15px}
.order .place:disabled{opacity:.5;cursor:not-allowed}
.order .note{font-size:12.5px;color:var(--muted);margin:0}
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
.perf{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.l2{margin-top:12px}
.yrsplit{margin-bottom:8px;grid-template-columns:repeat(2,minmax(0,1fr))}.yrsplit .v{font-size:22px}
@media (max-width:520px){.yrsplit{grid-template-columns:1fr}}
tr.best td{background:var(--up-soft)}
tr.avg td{background:var(--bg)}
.st-note.mood.pos{background:var(--up-soft)}.st-note.mood.neg{background:var(--down-soft)}
.capc{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-bottom:10px;background:var(--accent-soft);border-radius:8px;padding:10px}
.capc .k{font-size:11.5px;color:var(--muted)}.capc .v{font:700 17px var(--f-mono)}.capc .mut{font-size:11.5px}
@media (max-width:520px){.capc{grid-template-columns:1fr}}
.pcol{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px;min-width:0}
.ph2{font-weight:700;margin-bottom:8px}.ph2 .mut{font-weight:400;font-size:12.5px}
.kv small{font-size:12px}
.eq{width:100%;height:120px;margin-top:10px;display:block}
.eq polyline{fill:none;stroke-width:2;vector-effect:non-scaling-stroke}.eqU{stroke:var(--up)}.eqD{stroke:var(--down)}
.eq0{stroke:var(--line);stroke-width:1;vector-effect:non-scaling-stroke;stroke-dasharray:4 3}
.eqlab{display:flex;justify-content:space-between;font:11.5px var(--f-mono);color:var(--muted)}
.ready{list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:4px;font-size:13.5px}
#v-strategy td.num{white-space:nowrap}
#v-strategy .ra{text-align:right}
.yrs{display:flex;flex-wrap:wrap;gap:6px}
.yrc{font:500 12.5px var(--f-mono);padding:3px 8px;border-radius:7px;border:1px solid var(--line)}
.yrc.pos{background:var(--up-soft);color:var(--up)}.yrc.neg{background:var(--down-soft);color:var(--down)}
details.bt{margin-top:10px}details.bt summary{cursor:pointer;font-weight:600;color:var(--accent)}
@media (max-width:820px){.perf{grid-template-columns:1fr}}
.st-head{display:flex;justify-content:space-between;align-items:flex-end;gap:10px;flex-wrap:wrap;margin-bottom:10px}
.st-note{background:var(--warn-soft);color:var(--ink);border:1px solid var(--line);border-radius:10px;padding:10px 12px;font-size:13.5px;margin-bottom:12px}
.st-form{display:flex !important;flex-direction:column;gap:10px;margin-bottom:12px}
.st-form .fr{display:flex;flex-direction:column;gap:4px}.st-form label{font-size:12.5px;color:var(--muted)}
.st-form input,.st-form select{width:100%;max-width:420px}
.st-acts{display:flex;gap:8px;flex-wrap:wrap}
.st-list{display:flex;flex-direction:column;gap:8px}
.st{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px 14px;display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:10px 16px;align-items:center}
.st.on{border-left:4px solid var(--up)}
.st-name{font-weight:700;font-size:15.5px}
.st-state{margin-top:6px;font-size:13px;color:var(--muted);display:flex;gap:8px;align-items:center}
.st-btns{display:flex;gap:6px}
.sw{position:relative;width:52px;height:30px;flex:none;cursor:pointer}
.sw input{position:absolute;opacity:0;width:100%;height:100%;margin:0;cursor:pointer}
.sw span{position:absolute;inset:0;border-radius:999px;background:var(--line);transition:background .2s}
.sw span::after{content:"";position:absolute;top:3px;left:3px;width:24px;height:24px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.3);transition:transform .2s}
.sw input:checked+span{background:var(--up)}.sw input:checked+span::after{transform:translateX(22px)}
.sw input:focus-visible+span{outline:2px solid var(--accent);outline-offset:2px}
@media (max-width:720px){.st{grid-template-columns:minmax(0,1fr) auto}.st-btns{grid-column:1/-1}}
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
  .row .acts{grid-column:1/-1;order:4;flex-direction:row;align-items:center;justify-content:flex-start}
  .row .pricecol{text-align:right}
}
@media (prefers-reduced-motion:no-preference){.bar i{transition:width .4s ease}}
/* Stock viewer: opens inside the page (75% of a laptop screen), stock card on top, chart below */
.scrim{position:fixed;inset:0;z-index:20;background:rgba(10,14,20,.45)}
main.wide{max-width:max(1080px,80vw)}
.pcard{background:var(--surface);border:1px solid var(--line);border-radius:10px;margin-top:10px}
.pbar{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:6px 12px;padding:0 8px;border-bottom:1px solid var(--line)}
.pcard .ptabs{margin-top:0;flex:0 1 auto;min-width:0}
.pn{display:flex;gap:6px;align-items:center;padding:6px 0;margin-left:auto}
.pn .cnt{font:500 12.5px var(--f-mono);color:var(--muted);min-width:70px;text-align:center;white-space:nowrap}
.pn .btn{padding:6px 10px;font-size:13px}
.codes{display:inline-flex;flex-wrap:wrap;gap:4px;vertical-align:middle}
.xc{font:600 11.5px var(--f-mono);padding:1px 6px;border-radius:5px;border:1px solid var(--line);color:var(--ink);background:var(--bg);white-space:nowrap}
.xc em{font-style:normal;color:var(--muted);font-weight:500;margin-right:3px}
@media (max-width:720px){.pn{width:100%;justify-content:space-between;border-top:1px solid var(--line)}.pcard .ptabs{width:100%}}
.ph{background:var(--surface);border-bottom:1px solid var(--line);padding:14px max(16px,env(safe-area-inset-right,0px)) 0 16px}
.ph-top{display:flex;gap:12px;align-items:flex-start;justify-content:space-between}
.ph h3{font:700 19px/1.2 var(--f-display);margin:0}
.ph .meta{margin-top:4px}
.x{appearance:none;border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:8px;width:36px;height:36px;font-size:18px;cursor:pointer;flex:none}
.ph-stats{display:flex;flex-wrap:wrap;gap:6px 16px;margin:10px 0 4px;font-size:13px;color:var(--muted)}
.ph-stats b{color:var(--ink);font:600 14px var(--f-mono)}
.ptabs{display:flex;gap:2px;margin-top:6px;overflow-x:auto;scrollbar-width:none}
.ptabs::-webkit-scrollbar{display:none}
.ptabs .tab{padding:10px 12px 12px}
@media (max-width:420px){.tabs .tab{padding:10px 9px 12px}.tab b{margin-left:4px;padding:1px 5px}.ptabs .tab{padding:10px 8px 12px}}
.pb{padding:14px 16px 20px}
.ranges{display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap;align-items:center}
.rg{appearance:none;font:600 12.5px var(--f-body);padding:5px 10px;border-radius:999px;border:1px solid var(--line);background:var(--surface);color:var(--muted);cursor:pointer}
.rg[aria-pressed="true"]{background:var(--ink);color:var(--surface);border-color:var(--ink)}
.legend{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12.5px;color:var(--muted);margin-left:auto}
.legend i{display:inline-block;width:14px;height:3px;border-radius:2px;vertical-align:middle;margin-right:5px}
.legend button{appearance:none;border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:999px;padding:3px 9px;font:500 12px var(--f-body);cursor:pointer}
.legend button[aria-pressed="false"]{opacity:.45;text-decoration:line-through}
.ohlc{position:absolute;left:8px;top:6px;z-index:3;pointer-events:none;font:500 12.5px/1.45 var(--f-mono);color:var(--ink);
  background:color-mix(in srgb,var(--surface) 82%,transparent);padding:3px 8px;border-radius:6px;max-width:calc(100% - 90px)}
.ohlc .t{color:var(--muted);font-family:var(--f-body)}
.ohlc .t .cp{color:var(--ink);font:600 12.5px var(--f-mono)}
.ohlc em{font-style:normal;color:var(--muted);margin:0 2px 0 6px}
.ohlc em:first-child{margin-left:0}
.ohlc .u{color:var(--muted);font-family:var(--f-body);font-size:11.5px}
.chartbox{position:relative;height:clamp(360px,64vh,820px);background:var(--surface);border:1px solid var(--line);border-radius:10px;overflow:hidden}
.kgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px}
.kv{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:8px 10px}
.kv .k{font-size:11.5px;color:var(--muted)}
.kv .v{font:600 15px var(--f-mono);font-variant-numeric:tabular-nums}
.grp{font:700 12px var(--f-display);text-transform:uppercase;letter-spacing:.07em;color:var(--muted);margin:16px 0 6px}
.grp:first-child{margin-top:0}
.qt table{min-width:520px}
.qt td,.qt th{text-align:right;font-family:var(--f-mono);font-size:12.5px;white-space:nowrap}
.qt td:first-child,.qt th:first-child{text-align:left;font-family:var(--f-body)}
.tlinks{display:flex;flex-wrap:wrap;gap:6px;margin-left:auto}
.tlinks .btn{padding:5px 10px;font-size:12.5px}
@media (max-width:720px){.tlinks{margin-left:0;width:100%}.tlinks .lg{display:none}}
.plinks{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}
.src{color:var(--muted);font-size:12px;margin-top:10px}
/* Compact layout while a chart is open (laptop): everything fits on one screen */
@media (min-width:721px){
  body.viewing #note{display:none}
  body.viewing .hrow{padding-block:6px 2px}
  body.viewing h1{font-size:18px}
  body.viewing .tabs .tab{padding:5px 12px 7px}
  body.viewing main.wide{padding-block:8px 6px}
  body.viewing #p-row .row{padding:7px 12px;gap:6px 16px}
  body.viewing #p-row .acts{flex-direction:row;align-items:center}
  body.viewing .pcard{margin-top:6px}
  body.viewing .pcard .ptabs .tab{padding:7px 10px 8px}
  body.viewing .pn{padding:3px 0}
  body.viewing .pn .btn{padding:4px 9px}
  body.viewing .pb{padding:8px 12px 6px}
  body.viewing .ranges{margin-bottom:5px}
  body.viewing .rg,body.viewing .legend button{padding:3px 9px}
  body.viewing .tlinks .btn{padding:3px 9px}
  body.viewing .src{margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
}
@media (max-width:720px){.chartbox{height:clamp(320px,58vh,560px)}.pb{padding:12px 10px 16px}}
.aform{display:flex;flex-wrap:wrap;gap:8px;align-items:center;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px}
.aform input{width:130px}
.cmd{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:10px}
.cmd code{font:500 14px var(--f-mono);background:var(--surface);border:1px dashed var(--accent);color:var(--ink);padding:8px 10px;border-radius:8px;user-select:all;overflow-wrap:anywhere}
.ctx{position:fixed;z-index:30;min-width:250px;max-width:calc(100vw - 24px);background:var(--surface);border:1px solid var(--line);border-radius:10px;
  box-shadow:0 10px 30px rgba(0,0,0,.22);padding:6px;display:flex;flex-direction:column}
.ctx .hd{font:600 12px var(--f-mono);color:var(--muted);padding:6px 10px 4px}
.ctx button{appearance:none;border:0;background:none;color:var(--ink);text-align:left;font:500 14px var(--f-body);padding:9px 10px;border-radius:7px;cursor:pointer}
.ctx button:hover,.ctx button:focus-visible{background:var(--accent-soft);outline:none}
.toast{position:fixed;z-index:31;left:50%;transform:translateX(-50%);bottom:max(20px,env(safe-area-inset-bottom,0px));background:var(--ink);color:var(--surface);
  border-radius:10px;padding:10px 12px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;max-width:calc(100vw - 32px);font-size:14px;box-shadow:0 8px 24px rgba(0,0,0,.25)}
.toast code{font:600 13px var(--f-mono)}
.toast a{color:var(--surface);font-weight:700}
.ev .btn{grid-column:2;justify-self:end}
.steps{margin:12px 0 0;padding-left:20px;color:var(--muted);font-size:13.5px;display:flex;flex-direction:column;gap:4px}

</style>

<header><div class="wrap">
  <div class="hrow"><h1>TechnoFunda <span>Watchlist</span></h1><div class="runline" id="runline"></div></div>
  <nav class="tabs" role="tablist" aria-label="Lists">
    <button class="tab" role="tab" data-v="sp" id="t-sp">SP<b id="c-sp">0</b></button>
    <button class="tab" role="tab" data-v="dt" id="t-dt">DT<b id="c-dt">0</b></button>
    <button class="tab" role="tab" data-v="today" id="t-today">Today<b id="c-today">0</b></button>
    <button class="tab" role="tab" data-v="history" id="t-history">History</button>
    <button class="tab" role="tab" data-v="alerts" id="t-alerts">Alerts<b id="c-alerts">0</b></button>
    <button class="tab" role="tab" data-v="strategy" id="t-strategy">Strategy<b id="c-strategy">0</b></button>
  </nav>
</div></header>

<main class="wrap">
  <section class="strip" id="strip" aria-label="Summary"></section>
  <section id="v-list">
    <div class="tools">
      <input id="q" type="search" placeholder="Search name, NSE or BSE code" aria-label="Search name or symbol">
      <select id="sort" aria-label="Sort by">
        <option value="marks">Highest marks</option>
        <option value="ema">Closest to EMA</option>
        <option value="new">Newest added</option>
        <option value="name">Name A–Z</option>
      </select>
    </div>
    <div class="list" id="list"></div>
  </section>
  <section id="v-today" hidden></section>
  <section id="v-alerts" hidden></section>
  <section id="v-strategy" hidden></section>
  <section class="viewer" id="panel" hidden aria-label="Stock chart and details">
    <div class="list" id="p-row"></div>
    <div class="pcard">
      <div class="pbar">
      <nav class="ptabs" role="tablist" aria-label="Stock details">
        <button class="tab" role="tab" data-p="chart">Chart</button>
        <button class="tab" role="tab" data-p="fund">Screener</button>
        <button class="tab" role="tab" data-p="marks">Marks</button>
        <button class="tab" role="tab" data-p="alert">🔔 Alert</button>
        <button class="tab" role="tab" data-p="pos">Position</button>
      </nav>
      <div class="pn"><button class="btn" id="p-close" title="Back to the list (Esc)">← Back to <span id="p-back">list</span></button>
        <button class="btn" id="p-prev" aria-label="Previous stock" title="Previous stock (← key)">◀ Prev</button><span class="cnt" id="p-count" aria-live="polite"></span><button class="btn" id="p-next" aria-label="Next stock" title="Next stock (→ key)">Next ▶</button></div>
      </div>
      <div class="pb" id="p-body"></div>
    </div>
  </section>
  <section id="v-history" hidden><div class="tbl"><table><thead><tr><th>Date</th><th>Stock</th><th>Change</th><th>Reason</th></tr></thead><tbody id="hist"></tbody></table></div></section>
  <p class="note" id="note"></p>
</main>

<div class="scrim" id="oscrim" hidden style="z-index:25"></div>
<div class="order" id="order" role="dialog" aria-modal="true" aria-labelledby="o-title" hidden></div>
<div class="ctx" id="ctx" role="menu" hidden></div>
<div class="toast" id="toast" role="status" hidden></div>
<div class="scrim" id="scrim" hidden></div>

<script>
const D = __DATA__;
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const num = v => { const n = parseFloat(v); return isFinite(n) ? n : null; };
const FULL = D.cfg.full, PASS = D.cfg.pass_monthly;
const fmtINR = n => "₹" + n.toLocaleString("en-IN", {maximumFractionDigits: 2});

function marksOf(r){ const m = String(r.fund_result||"").match(/^([\d.]+)\s*\/\s*([\d.]+)/); return m ? +m[1] : null; }
// NSE symbol and BSE code (from the Screener page); before the robot reads them, the list symbol is shown
function codesHTML(r){
  const nse = r.nse || (/^\d+$/.test(r.symbol) ? "" : r.symbol), bse = r.bse || (/^\d+$/.test(r.symbol) ? r.symbol : "");
  return `<span class="codes">${nse ? `<span class="xc"><em>NSE</em>${esc(nse)}</span>` : ""}${bse ? `<span class="xc"><em>BSE</em>${esc(bse)}</span>` : ""}</span>`;
}
const emaN = r => String(r.ema_basis) === "20" ? 20 : 200;
function emaGap(r){ const c = num(r.last_close), e = num(r.ema200); return (c && e) ? (c - e) / e * 100 : null; }

function stockRow(r, list){
  const mk = marksOf(r), gap = emaGap(r), c = num(r.last_close);
  const pct = mk == null ? 0 : Math.min(100, mk / FULL * 100);
  return `<article class="row ${list === "DT" ? "dt" : ""}">
    <div><button class="nm linkish" data-open="${esc(r.symbol)}" data-tab="chart">${esc(r.name || r.symbol)}</button>
      <div class="meta">${codesHTML(r)}</div></div>
    <div class="pricecol"><div class="px">${c ? fmtINR(c) : "—"}</div>
      <div class="ema ${gap == null ? "mut" : gap >= 0 ? "up" : "down"}">${gap == null ? (c ? "New listing: under 200 days" : "200 EMA n/a") : (gap >= 0 ? "▲ " : "▼ ") + Math.abs(gap).toFixed(1) + "% " + (gap >= 0 ? "above" : "below") + " " + emaN(r) + " EMA" + (emaN(r) === 20 ? " · new listing" : "")}</div></div>
    <div class="mk"><div class="top"><span>Marks${r.last_fund_check ? " · " + esc(r.last_fund_check) : ""}</span><b>${mk == null ? "not marked yet" : mk + " / " + FULL}</b></div>
      <div class="bar ${mk != null && mk < PASS ? "low" : ""}" role="img" aria-label="${mk == null ? "No marks yet" : mk + " of " + FULL + " marks, pass mark " + PASS}"><i style="width:${pct}%"></i><u style="left:${PASS / FULL * 100}%"></u></div></div>
    <div class="acts"><div class="r1"><button class="btn pri" data-open="${esc(r.symbol)}" data-tab="chart">Chart</button><button class="btn" data-open="${esc(r.symbol)}" data-tab="fund">Screener</button></div>
      <div class="r2"><button class="btn buy" data-order="BUY" data-sym="${esc(r.symbol)}" aria-label="Buy ${esc(r.name || r.symbol)}" title="Buy">B</button><button class="btn sell" data-order="SELL" data-sym="${esc(r.symbol)}" aria-label="Sell ${esc(r.name || r.symbol)}" title="Sell">S</button></div></div>
    ${posStrip(r)}
  </article>`;
}

let view = "sp";
// The stocks of a list in the same order as on screen (search + sort), also used by Prev / Next
function listRows(key){
  const q = document.getElementById("q").value.trim().toLowerCase();
  let rows = D[key].filter(r => [r.symbol, r.name, r.nse, r.bse].join(" ").toLowerCase().includes(q));
  const s = document.getElementById("sort").value;
  const by = {marks: r => -(marksOf(r) ?? -1), ema: r => Math.abs(emaGap(r) ?? 999), new: r => -Date.parse(r.added_on || 0), name: r => (r.name || r.symbol).toLowerCase()}[s];
  rows.sort((a, b) => { const x = by(a), y = by(b); return x < y ? -1 : x > y ? 1 : 0; });
  return rows;
}
function drawList(){
  const key = view === "dt" ? "DT" : "SP", q = document.getElementById("q").value.trim().toLowerCase();
  const rows = listRows(key);
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
    evBlock("New listings (under 200 trading days → judged on the 20 EMA)", "New listing", "p-sp", r.new_listing),
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
let emaOn = {10: true, 20: true, 50: true, 200: true};
try { emaOn = Object.assign(emaOn, JSON.parse(localStorage.getItem("tf-ema") || "{}")); } catch (e) {}
const chartCache = {};
function loadLW(){
  if (window.LightweightCharts) return Promise.resolve();
  if (!lwLoad) lwLoad = new Promise((ok, fail) => { const sc = document.createElement("script"); sc.src = LW_URL; sc.onload = ok;
    sc.onerror = e => { lwLoad = null; sc.remove(); fail(e); }; document.head.appendChild(sc); });
  return lwLoad;
}
function loadChart(sym){
  if (D.charts) return Promise.resolve(D.charts[sym]);
  if (!chartCache[sym]) chartCache[sym] = fetch("charts/" + encodeURIComponent(sym) + ".json", {cache: "no-cache"})
    .then(r => r.ok ? r.json() : null).catch(() => { delete chartCache[sym]; throw new Error("net"); });
  return chartCache[sym];
}
const findRow = sym => { for (const k of ["SP", "DT"]) { const r = D[k].find(x => x.symbol === sym); if (r) return [r, k]; } return [null, null]; };
const tok = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const alpha = (hex, a) => /^#[0-9a-f]{6}$/i.test(hex) ? hex + Math.round(a * 255).toString(16).padStart(2, "0") : hex;
const fmtN = (v, d = 2) => v == null || !isFinite(v) ? "—" : Number(v).toLocaleString("en-IN", {maximumFractionDigits: d});

let VSEQ = [], VLIST = "SP", backY = 0;
function openPanel(sym, tab){
  const [r, list] = findRow(sym); if (!r) return;
  const wasOpen = !!cur;
  if (!wasOpen || !VSEQ.includes(sym)) {
    // Prev / Next walk through the list this stock is in, in the order shown on screen
    VLIST = list; VSEQ = listRows(list).map(x => x.symbol);
    if (!VSEQ.includes(sym)) VSEQ = D[list].map(x => x.symbol);
  }
  if (!wasOpen) backY = window.scrollY;
  closeMenu();
  cur = {r, list}; curTab = tab || curTab || "chart";
  for (const id of ["v-list", "v-today", "v-history", "v-alerts", "v-strategy", "strip"]) document.getElementById(id).hidden = true;
  document.getElementById("panel").hidden = false;
  document.querySelector("main").classList.add("wide"); document.body.classList.add("viewing");
  drawHead();
  drawPanel();
  if (!wasOpen) { window.scrollTo(0, 0); try { history.pushState({viewer: 1}, ""); } catch (e) {} }
}
// Back button (phone or browser) and Esc / "Back to SP" all return to the list the same way
function requestClose(){ if (history.state && history.state.viewer) history.back(); else closePanel(); }
window.addEventListener("popstate", () => { if (cur) closePanel(); });
function drawHead(){
  if (!cur) return;
  const i = VSEQ.indexOf(cur.r.symbol), n = VSEQ.length;
  document.getElementById("p-count").textContent = n ? `${i + 1} of ${n} · ${VLIST}` : "";
  document.getElementById("p-back").textContent = {sp: "SP", dt: "DT", today: "Today", history: "History", alerts: "Alerts", strategy: "Strategy"}[view] || "list";
  document.getElementById("p-prev").disabled = document.getElementById("p-next").disabled = n < 2;
  document.getElementById("p-row").innerHTML = stockRow(cur.r, cur.list);
}
function stepStock(d){
  if (!cur || VSEQ.length < 2) return;
  const i = VSEQ.indexOf(cur.r.symbol);
  openPanel(VSEQ[(i + d + VSEQ.length) % VSEQ.length], curTab);
}
function closePanel(){
  closeMenu();
  if (chartObj) { chartObj.remove(); chartObj = null; }
  document.getElementById("panel").hidden = true;
  document.getElementById("strip").hidden = false;
  document.querySelector("main").classList.remove("wide"); document.body.classList.remove("viewing");
  cur = null;
  show(view);
  window.scrollTo(0, backY);
}
function drawPanel(){
  document.querySelectorAll("[data-p]").forEach(t => { t.setAttribute("aria-selected", t.dataset.p === curTab);
    if (t.dataset.p === curTab && t.scrollIntoView) t.scrollIntoView({block: "nearest", inline: "nearest"}); });
  if (chartObj) { chartObj.remove(); chartObj = null; }
  const body = document.getElementById("p-body"), r = cur.r;
  const links = `<div class="plinks"><a class="btn" href="${esc(r.chart)}" target="_blank" rel="noopener">Open in TradingView ↗</a><a class="btn" href="${esc(r.screener)}" target="_blank" rel="noopener">Open full Screener page ↗</a></div>`;
  if (curTab === "chart") {
    const topLinks = `<span class="tlinks"><a class="btn" href="${esc(r.chart)}" target="_blank" rel="noopener"><span class="lg">Open in </span>TradingView ↗</a><a class="btn" href="${esc(r.screener)}" target="_blank" rel="noopener"><span class="lg">Open full </span>Screener<span class="lg"> page</span> ↗</a></span>`;
    body.innerHTML = `<div class="ranges" role="group" aria-label="Candle size">${[["D", "Daily"], ["W", "Weekly"], ["M", "Monthly"]].map(([k, l]) =>
        `<button class="rg" data-tf="${k}" aria-pressed="${k === curTf}">${l}</button>`).join("")}${topLinks}</div>
      <div class="ranges" role="group" aria-label="Period">${[["3M", 63], ["6M", 126], ["1Y", 260], ["3Y", 780], ["5Y", 1300], ["All", 0]].map(([l, n]) =>
        `<button class="rg" data-range="${n}" aria-pressed="${n === curRange}">${l}</button>`).join("")}
      <div class="legend" id="legend"></div></div>
      <div class="chartbox" id="chartbox"><div class="empty" style="border:0">Loading chart…</div></div>
      <div class="src"><span id="chartsrc"></span> <b>Tip:</b> right-click the chart (long-press on a phone) to set a price alert.</div>`;
    drawChart();
  } else if (curTab === "fund") {
    body.innerHTML = fundHTML(D.fund[r.symbol]) + links;
  } else if (curTab === "pos") {
    body.innerHTML = posHTML(r) + links;
  } else if (curTab === "alert") {
    body.innerHTML = alertHTML(r) + links;
    const upd = () => {
      const op = document.getElementById("a-op").value, v = document.getElementById("a-price").value.trim(), box = document.getElementById("a-cmd");
      if (box) box.textContent = `/alert ${r.symbol} ${op} ${v || "PRICE"}`;
    };
    document.getElementById("a-op").addEventListener("change", upd);
    document.getElementById("a-price").addEventListener("input", upd);
    document.getElementById("a-price").addEventListener("keydown", e => { if (e.key === "Enter")
      saveAlert(r.symbol, r.name, document.getElementById("a-op").value, e.target.value); });
    upd();
  } else {
    let checks = []; try { checks = JSON.parse(r.marks_detail || "[]"); } catch (e) {}
    body.innerHTML = (checks.length ? `<div class="checks">${checks.map(([l, g, o, d]) =>
      `<div class="ck"><span class="ic ${+g > 0 ? "up" : "down"}">${+g > 0 ? "✓" : "✕"}</span><div><div>${esc(l)} <span class="num mut">${esc(g)}/${esc(o)}</span></div>${d ? `<div class="d">${esc(d)}</div>` : ""}</div></div>`).join("")}</div>
      <p class="src">Marks ${esc(r.fund_result || "")} · checked ${esc(r.last_fund_check || "—")} · pass mark ${PASS} / ${FULL}</p>`
      : `<div class="empty">Not marked yet. Marks appear after the next robot run.</div>`) + links;
  }
}
// Group daily candles into weekly or monthly ones
function resample(h, tf){
  const n = h.t.length, hasOHLC = !!(h.o && h.h && h.l), out = [];
  const key = t => { if (tf === "M") return t.slice(0, 7);
    const d = new Date(t + "T00:00:00Z"), day = (d.getUTCDay() + 6) % 7; d.setUTCDate(d.getUTCDate() - day); return d.toISOString().slice(0, 10); };
  let prev = null;
  for (let i = 0; i < n; i++) {
    const c = h.c[i]; if (c == null) continue;
    // No open/high/low (BSE/NSE SME stocks): each day's candle runs from the previous close to this close
    const o = hasOHLC && h.o[i] != null ? h.o[i] : (prev ?? c);
    const hi = hasOHLC && h.h[i] != null ? h.h[i] : Math.max(o, c), lo = hasOHLC && h.l[i] != null ? h.l[i] : Math.min(o, c);
    const approx = !(hasOHLC && h.o[i] != null && h.h[i] != null && h.l[i] != null);
    prev = c;
    const v = h.v ? (h.v[i] || 0) : 0, k = tf === "D" ? h.t[i] : key(h.t[i]), last = out[out.length - 1];
    if (last && last.k === k) { last.high = Math.max(last.high, hi); last.low = Math.min(last.low, lo); last.close = c; last.v += v; last.end = h.t[i]; last.approx = last.approx || approx; }
    else out.push({k, time: h.t[i], open: o, high: hi, low: lo, close: c, v, end: h.t[i], approx});
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
  catch (e) { box.innerHTML = `<div class="empty" style="border:0">The chart library could not load. Check your internet connection and tap Chart again, or use Open in TradingView.</div>`; return; }
  if (!cur || cur.r.symbol !== sym || curTab !== "chart") return;
  if (chartObj) { chartObj.remove(); chartObj = null; }
  if (!h || !h.t || !h.t.length) { box.innerHTML = `<div class="empty" style="border:0">Chart appears after the next robot run (7 AM).</div>`; return; }
  box.innerHTML = "";
  fitChart();
  const bars = resample(h, curTf), nApprox = bars.filter(b => b.approx).length, candles = nApprox === 0;
  const ink = tok("--muted"), line = tok("--line"), up = tok("--up"), dn = tok("--down");
  chartObj = LightweightCharts.createChart(box, {
    autoSize: true,
    layout: {background: {type: "solid", color: tok("--surface")}, textColor: ink, fontFamily: tok("--f-body"), fontSize: 11},
    grid: {vertLines: {color: alpha(line, .6)}, horzLines: {color: alpha(line, .6)}},
    rightPriceScale: {borderColor: line, scaleMargins: {top: .14, bottom: .24}}, timeScale: {borderColor: line},
    localization: {priceFormatter: p => p < 0 ? "" : "₹" + Number(p).toLocaleString("en-IN", {maximumFractionDigits: 2})},
    handleScroll: {vertTouchDrag: false},
  });
  const main = chartObj.addCandlestickSeries({upColor: up, downColor: dn, borderVisible: false, wickUpColor: up, wickDownColor: dn, priceLineVisible: false});
  main.setData(bars.map(b => ({time: b.time, open: b.open, high: b.high, low: b.low, close: b.close})));
  if (h.v) {
    const vol = chartObj.addHistogramSeries({priceFormat: {type: "volume"}, priceScaleId: "", lastValueVisible: false, priceLineVisible: false});
    vol.priceScale().applyOptions({scaleMargins: {top: .8, bottom: 0}});
    vol.setData(bars.map(b => ({time: b.time, value: b.v, color: alpha(b.close >= b.open ? up : dn, .35)})));
  }
  const closes = bars.map(b => b.close), tfName = {D: "daily", W: "weekly", M: "monthly"}[curTf];
  // EMA lines: 10, 20, 50, 200 - each can be switched on/off with the chips above the chart
  const EMAS = [[10, "--e10", 1.5, 0], [20, "--e20", 1.5, 0], [50, "--e50", 1.5, 0], [200, "--e200", 2.5, 0]];
  const chips = [];
  for (const [p, col, w, style] of EMAS) {
    const ok = bars.length >= p, on = emaOn[p] !== false;
    chips.push(`<button data-ema="${p}" aria-pressed="${on}" ${ok ? "" : "disabled title=\"Needs " + p + " candles\""}><i style="background:var(${col})"></i>EMA ${p}</button>`);
    if (!ok || !on) continue;
    const e = ema(closes, p);
    chartObj.addLineSeries({color: tok(col), lineWidth: w, lineStyle: style, priceLineVisible: false, lastValueVisible: p === 200,
      crosshairMarkerVisible: false}).setData(bars.map((b, i) => ({time: b.time, value: e[i]})));
  }
  document.getElementById("legend").innerHTML = chips.join("");
  drawOHLC(box, bars, main, candles);
  const first = h.t[0], lastT = h.t[h.t.length - 1];
  document.getElementById("chartsrc").textContent =
    `Candles from ${first} to ${lastT} (${tfName}). ` +
    (curTf === "D" ? "" : `EMA lines here are on ${tfName} candles; the robot's SP/DT rule uses the daily ${emaN(cur.r)} EMA. `) +
    (candles ? "" : nApprox === bars.length ? "High/low not available yet for this stock: each candle runs from the previous close to the close (≈) until the robot has downloaded the exchange price files. "
                 : `${nApprox} older candle(s) are still approximate (≈); the robot fills in real high/low a few months at a time. `) +
    (bars.length < 200 ? "EMA 200 appears once there are 200 candles." : "");
  cur.bars = bars; cur.main = main;
  for (const a of [...activeAlerts(), ...AL.pending].filter(x => x.symbol === sym))
    main.createPriceLine({price: +a.price, color: tok("--accent"), lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "🔔 " + String(a.op).slice(0, 6)});
  attachMenu(box);
  setRange();
}
// Top-left box: date, O H L C, % change for the candle under the mouse (latest candle otherwise), and the cursor price
function drawOHLC(box, bars, main, real){
  const ov = document.createElement("div"); ov.className = "ohlc"; box.appendChild(ov);
  const M = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const day = t => { const [y, m, d] = t.split("-"); return `${+d} ${M[+m - 1]} ${y}`; };
  const when = b => curTf === "M" ? `${M[+b.end.slice(5, 7) - 1]} ${b.end.slice(0, 4)}` : curTf === "W" ? `Week ${day(b.time)} – ${day(b.end)}` : day(b.time);
  const unit = {D: "day", W: "week", M: "month"}[curTf];
  const f = v => Number(v).toLocaleString("en-IN", {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const show = (i, price) => {
    const b = bars[i]; if (!b) return;
    const pc = i > 0 ? bars[i - 1].close : b.open, ch = pc ? (b.close - pc) / pc * 100 : 0, abs = b.close - pc;
    const cls = ch >= 0 ? "up" : "down", ap = b.approx ? "≈" : "";
    ov.innerHTML = `<div class="t">${when(b)}${price != null ? ` · <span class="cp">₹${f(price)}</span>` : ""}</div>` +
      `<div><em>O</em>${ap}${f(b.open)} <em>H</em>${ap}${f(b.high)} <em>L</em>${ap}${f(b.low)} <em>C</em><span class="${cls}">${f(b.close)}</span> ` +
      `<span class="${cls}">${ch >= 0 ? "+" : ""}${f(abs)} (${ch >= 0 ? "+" : ""}${ch.toFixed(2)}%)</span> <span class="u">1 ${unit}</span></div>`;
  };
  show(bars.length - 1, null);
  chartObj.subscribeCrosshairMove(p => {
    if (!p || !p.point || p.logical == null) { show(bars.length - 1, null); return; }
    const i = Math.max(0, Math.min(bars.length - 1, Math.round(p.logical)));
    show(i, main.coordinateToPrice(p.point.y));
  });
}
// Laptop: chart fills the rest of the screen, so header + stock card + chart are all visible without scrolling
function fitChart(){
  const box = document.getElementById("chartbox");
  if (!box || !cur) return;
  if (innerWidth <= 720) { box.style.height = ""; return; }
  const top = box.getBoundingClientRect().top + window.scrollY;
  box.style.height = Math.max(260, Math.floor(innerHeight - top - 40)) + "px";
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
// ---------------- Alerts: one-click saving through the user's own GitHub key (kept only in this browser)
const AL = D.alerts || {active: [], done: [], bot: ""};
AL.pending = []; AL.deleting = new Set();
const REPO = D.cfg.repo || (location.hostname.endsWith(".github.io") && location.pathname.split("/")[1]
  ? location.hostname.split(".")[0] + "/" + location.pathname.split("/")[1] : "");
let GH = ""; try { GH = localStorage.getItem("tf-gh-token") || ""; } catch (e) {}
const connected = () => !!(GH && REPO);
const botLink = "";
async function gh(path, opts = {}){
  const r = await fetch("https://api.github.com" + path, Object.assign({}, opts, {headers: Object.assign({
    Authorization: "Bearer " + GH, Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}, opts.headers || {})}));
  if (!r.ok) { const e = new Error("GitHub said " + r.status); e.status = r.status; throw e; }
  return r.status === 204 ? null : (opts.raw ? r.text() : r.json());
}
// The alert is sent to the "Price Alerts" robot as a run request. The key only needs permission to start
// that robot (Actions), so it can never change the files or code in the repository.
async function sendRequest(obj){
  await gh(`/repos/${REPO}/actions/workflows/alerts.yml/dispatches`, {method: "POST",
    body: JSON.stringify({ref: "main", inputs: {request: JSON.stringify(obj)}})});
}
function saveError(e){
  const why = e.status === 401 ? "the GitHub key is wrong or has expired" : e.status === 403 ? "the GitHub key is missing a permission"
    : e.status === 404 ? "the GitHub key can't see this repository" : "GitHub could not be reached";
  showToast(`⚠️ Alert not saved: ${why}. Open the <b>Alerts</b> tab → <b>Connect</b> to fix it.`);
}
async function saveAlert(sym, name, op, price){
  price = +(+price).toFixed(2);
  if (!(price > 0)) { showToast("Type a price first."); return; }
  if (!connected()) { needConnect(); return; }
  showToast(`Saving alert: ${esc(name || sym)} ${op} ₹${fmtN(price)}…`);
  try {
    await sendRequest({action: "add", symbol: sym, name: name || sym, op, price});
    AL.pending.push({symbol: sym, name: name || sym, op, price});
    if (cur && cur.r.symbol === sym && cur.main) cur.main.createPriceLine({price, color: tok("--accent"), lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "🔔 " + op});
    showToast(`✅ Alert saved: <b>${esc(name || sym)}</b> ${op} ₹${fmtN(price)}.`);
    redrawAlertViews();
    laterRefresh();
  } catch (e) { saveError(e); }
}
async function deleteAlert(id, btn){
  if (btn && btn.dataset.armed !== "1") { btn.dataset.armed = "1"; btn.textContent = "Tap again to delete";
    setTimeout(() => { if (btn.isConnected) { btn.dataset.armed = ""; btn.textContent = "Delete"; } }, 3000); return; }
  try { await sendRequest({action: "delete", id}); AL.deleting.add(id);
    showToast(`🗑 Alert ${id} deleted.`); redrawAlertViews(); laterRefresh(); }
  catch (e) { saveError(e); }
}
function needConnect(){
  showToast(`🔔 To save alerts from the chart, connect this dashboard once (2 minutes). <a href="#alerts" data-goto-alerts>Connect now</a>`);
}
function laterRefresh(){ for (const ms of [60000, 150000, 300000, 420000]) setTimeout(refreshAlerts, ms); }
async function refreshAlerts(){
  if (!REPO) return;
  try {
    const txt = await fetch(`https://raw.githubusercontent.com/${REPO}/main/data/alerts.json?t=${Date.now()}`, {cache: "no-store"})
      .then(r => r.ok ? r.text() : Promise.reject(r.status));
    const st = JSON.parse(txt), items = st.alerts || [];
    AL.active = items.filter(a => a.status === "active");
    AL.done = items.filter(a => a.status === "triggered").slice(-10).reverse();
    AL.bot = AL.bot || st.bot_username || "";
    AL.pending = AL.pending.filter(p => !AL.active.some(a => a.symbol === p.symbol && a.op === p.op && +a.price === +p.price));
    for (const id of [...AL.deleting]) if (!AL.active.some(a => a.id === id)) AL.deleting.delete(id);
    AL.live = true; redrawAlertViews();
  } catch (e) {}
}
function redrawAlertViews(){
  drawAlerts();
  document.getElementById("c-alerts").textContent = activeAlerts().length + AL.pending.length;
  if (cur && curTab === "alert") drawPanel();
}
const activeAlerts = () => (AL.active || []).filter(a => !AL.deleting.has(a.id));
function alertRows(list, canDelete){
  return list.map(a => `<div><div><b>${esc(a.name || a.symbol)}</b> <span class="sym mut">${esc(a.symbol)}</span></div>` +
    `<span class="pill ${a.status === "triggered" ? "p-add" : a.pending ? "p-warn" : "p-sp"}">${a.status === "triggered" ? "Hit ₹" + fmtN(a.hit_price) : a.pending ? "Saving…" : "#" + a.id}</span>` +
    `<div class="why">${esc(a.op)} ₹${fmtN(a.price)} · ${a.status === "triggered" ? "triggered " + esc(a.hit_at || "") : a.pending ? "sent from this dashboard" : "set " + esc(a.created || "")}</div>` +
    (canDelete && a.status === "active" && !a.pending && connected() ? `<button class="btn" data-del-alert="${esc(a.id)}">Delete</button>` : "") + `</div>`).join("");
}
function alertHTML(r){
  const c = num(r.last_close);
  const mine = [...activeAlerts().filter(a => a.symbol === r.symbol), ...AL.pending.filter(a => a.symbol === r.symbol).map(a => Object.assign({pending: true, status: "active"}, a))];
  const form = `<div class="aform"><label for="a-op">Alert me when the price is</label>
      <select id="a-op"><option value="above">at or above</option><option value="below">at or below</option></select>
      <span>₹</span><input id="a-price" type="number" inputmode="decimal" step="0.05" min="0" placeholder="${c ? Math.round(c) : "price"}" aria-label="Alert price">
      <button class="btn pri" data-save-alert>🔔 Set alert</button></div>`;
  const how = connected()
    ? `<p class="src">Tip: you can also right-click on the chart (long-press on a phone) and pick a price.</p>`
    : `<p class="src">⚠️ Connect this dashboard once to save alerts: <a href="#alerts" data-goto-alerts>Alerts tab → Connect</a>.</p>`;
  return form + how +
    (mine.length ? `<h2>Alerts for this stock<span class="cnt">${mine.length}</span></h2><div class="ev">${alertRows(mine, true)}</div>` : "") +
    `<p class="src">Prices are checked every 15 minutes, Mon–Fri 9:15 AM–3:30 PM, and can be up to about 15 minutes late. Last close ${c ? fmtINR(c) : "—"}.</p>`;
}
function connectBox(){
  if (!REPO) return `<div class="aform" style="display:block">One-click alerts need the dashboard's GitHub address. They will switch on after the next daily robot run.</div>`;
  if (connected()) return `<div class="aform" style="display:flex;justify-content:space-between">
      <span>✅ <b>Alerts can be saved</b> from this device (connected to <span class="sym">${esc(REPO)}</span>).</span>
      <button class="btn" data-gh-disconnect>Disconnect</button></div>`;
  return `<div class="aform" style="display:block"><b>Connect this dashboard to save alerts (once per phone or computer)</b>
    <ol class="steps"><li>Open <a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noopener">GitHub → new fine-grained token ↗</a></li>
      <li>Token name: <b>watchlist dashboard</b>. Expiration: <b>1 year</b>.</li>
      <li>Repository access: <b>Only select repositories</b> → <b>${esc(REPO.split("/")[1] || "technofunda-watchlist")}</b>.</li>
      <li>Permissions → Repository: <b>Actions: Read and write</b> only (nothing else).</li>
      <li><b>Generate token</b>, copy it, paste it here and tap Connect.</li></ol>
    <div class="cmd"><input id="gh-key" type="password" autocomplete="off" placeholder="github_pat_…" aria-label="GitHub token" style="flex:1;min-width:0">
      <button class="btn pri" data-gh-connect>Connect</button></div>
    <p class="src">The key is stored only in this browser and is sent only to GitHub. It can only start the Price Alerts robot of this one repository — it cannot change any file. Disconnect any time, or delete the token on GitHub.</p></div>`;
}
function drawAlerts(){
  const act = [...activeAlerts(), ...AL.pending.map(a => Object.assign({pending: true, status: "active"}, a))], done = AL.done || [];
  document.getElementById("v-alerts").innerHTML = connectBox() +
    `<div class="aform" style="display:block;margin-top:10px"><b>Set an alert:</b> open any stock's chart and <b>right-click</b> on it (on a phone: press and hold),
      then choose the price. Or use the stock's <b>🔔 Alert</b> tab. When the price is reached you get a Telegram message with a voice note.</div>` +
    `<h2>Active alerts<span class="cnt">${act.length}</span></h2>` + (act.length ? `<div class="ev">${alertRows(act, true)}</div>` : `<div class="empty">No active alerts.</div>`) +
    (done.length ? `<h2>Recently triggered<span class="cnt">${done.length}</span></h2><div class="ev">${alertRows(done)}</div>` : "") +
    `<p class="src">${AL.live ? "Live list." : "List from the last daily update" + (AL.as_of ? " (" + esc(AL.as_of) + ")" : "") + "."}</p>`;
}
async function ghConnect(){
  const inp = document.getElementById("gh-key"), key = (inp.value || "").trim();
  if (!key) { showToast("Paste the GitHub token first."); return; }
  GH = key;
  try { await gh(`/repos/${REPO}`); try { localStorage.setItem("tf-gh-token", key); } catch (e) {}
    showToast("✅ Connected. Right-click on any chart to set an alert."); refreshAlerts(); redrawAlertViews(); }
  catch (e) { GH = ""; showToast(`⚠️ That key did not work (${e.status === 401 ? "wrong or expired" : e.status === 404 ? "no access to " + esc(REPO) : "GitHub error " + (e.status || "")}).`); }
}
function ghDisconnect(){ GH = ""; try { localStorage.removeItem("tf-gh-token"); } catch (e) {} showToast("Disconnected on this device."); redrawAlertViews(); }

// ---------------- Right-click (or long-press) on the chart -> set an alert at that price
const tick = p => Math.round(p * 20) / 20;  // NSE tick size 0.05
function attachMenu(box){
  if (box.dataset.menu) return; box.dataset.menu = "1";
  const priceAt = (x, y) => { const r = box.getBoundingClientRect(); const p = cur && cur.main ? cur.main.coordinateToPrice(y - r.top) : null;
    return p != null && isFinite(p) && p > 0 ? tick(p) : null; };
  box.addEventListener("contextmenu", e => { e.preventDefault(); const p = priceAt(e.clientX, e.clientY); if (p) openMenu(e.clientX, e.clientY, p); });
  let timer = null, sx = 0, sy = 0;
  box.addEventListener("touchstart", e => { const t = e.touches[0]; sx = t.clientX; sy = t.clientY;
    timer = setTimeout(() => { const p = priceAt(sx, sy); if (p) openMenu(sx, sy, p); }, 550); }, {passive: true});
  box.addEventListener("touchmove", e => { const t = e.touches[0]; if (Math.hypot(t.clientX - sx, t.clientY - sy) > 10) clearTimeout(timer); }, {passive: true});
  box.addEventListener("touchend", () => clearTimeout(timer));
}
function openMenu(x, y, price){
  const m = document.getElementById("ctx"), c = num(cur.r.last_close), up = !c || price >= c;
  const item = (op, label) => `<button role="menuitem" data-alert-op="${op}" data-alert-price="${price}">🔔 ${label} ₹${fmtN(price)}</button>`;
  m.innerHTML = `<div class="hd">${esc(cur.r.symbol)} · ₹${fmtN(price)}${c ? " · last close ₹" + fmtN(c) : ""}</div>` +
    (up ? item("above", "Alert when price goes above") + item("below", "Alert when price falls below")
        : item("below", "Alert when price falls below") + item("above", "Alert when price goes above")) +
    `<button role="menuitem" data-alert-custom="${price}">✏️ Alert at a different price…</button>`;
  m.hidden = false;
  const w = m.offsetWidth, h = m.offsetHeight;
  m.style.left = Math.max(8, Math.min(x, innerWidth - w - 8)) + "px";
  m.style.top = Math.max(8, Math.min(y, innerHeight - h - 8)) + "px";
  m.querySelector("button").focus();
}
function closeMenu(){ document.getElementById("ctx").hidden = true; }
let toastTimer = null;
function showToast(html){
  const t = document.getElementById("toast"); t.innerHTML = html; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.hidden = true, 9000);
}

// ---------------- Buy / Sell order ticket (ready for the broker connection later)
const ORD = {side: "BUY", sym: "", type: "MARKET", product: "CNC", broker: "ZERODHA", qty: 1, price: ""};
try { Object.assign(ORD, JSON.parse(localStorage.getItem("tf-order") || "{}")); } catch (e) {}
const BROKER_READY = false;  // switches to true when Zerodha / Angel One is connected through the VPS
function openOrder(sym, side){
  const [r] = findRow(sym); if (!r) return;
  Object.assign(ORD, {side, sym, price: ""});
  if (side === "SELL" && POS[sym] && POS[sym].qty > 0) ORD.qty = POS[sym].qty;
  drawOrder(r);
  document.getElementById("oscrim").hidden = false; document.getElementById("order").hidden = false;
  document.getElementById("o-qty").focus();
}
function closeOrder(){ document.getElementById("order").hidden = true; document.getElementById("oscrim").hidden = true; }
function drawOrder(r){
  const c = num(r.last_close), buy = ORD.side === "BUY";
  const seg = (key, opts) => `<div class="seg" role="group">${opts.map(([v, l]) => `<button data-oset="${key}" data-val="${v}" aria-pressed="${ORD[key] === v}">${l}</button>`).join("")}</div>`;
  document.getElementById("order").innerHTML = `
    <div class="oh ${buy ? "buy" : "sell"}"><div><h3 id="o-title">${buy ? "BUY" : "SELL"} · ${esc(r.name || r.symbol)}</h3>
      <div style="font-size:12.5px;opacity:.9">${esc(r.symbol)} · last close ${c ? fmtINR(c) : "—"}</div></div>
      <button class="x" data-oclose aria-label="Close">✕</button></div>
    <div class="ob">
      <div class="fr"><label>Broker</label>${seg("broker", [["ZERODHA", "Zerodha"], ["ANGEL", "Angel One"]])}</div>
      <div class="fr"><label>Product</label>${seg("product", [["CNC", "Delivery"], ["MIS", "Intraday"]])}</div>
      <div class="fr"><label>Order type</label>${seg("type", [["MARKET", "Market"], ["LIMIT", "Limit"]])}</div>
      <div class="fr"><label for="o-qty">Quantity</label><input id="o-qty" type="number" inputmode="numeric" min="1" step="1" value="${ORD.qty}"></div>
      <div class="fr" ${ORD.type === "LIMIT" ? "" : "hidden"}><label for="o-price">Limit price ₹</label><input id="o-price" type="number" inputmode="decimal" min="0" step="0.05" value="${ORD.price || (c || "")}"></div>
      <div class="est"><span>Approx. value</span><b id="o-est">—</b></div>
      <button class="btn place ${buy ? "buy" : "sell"}" data-oplace ${BROKER_READY ? "" : "disabled"}>${buy ? "Place BUY order" : "Place SELL order"}</button>
      <p class="note">${BROKER_READY ? "The order goes to your broker immediately." : "🔒 No broker is connected yet, so no order can be placed from here. This button will work once Zerodha / Angel One is connected through your VPS. Your choices above are remembered."}</p>
    </div>`;
  const est = () => { const q = +document.getElementById("o-qty").value || 0, pi = document.getElementById("o-price");
    const pr = ORD.type === "LIMIT" ? (+pi.value || 0) : (c || 0); ORD.qty = q > 0 ? q : ORD.qty; if (ORD.type === "LIMIT") ORD.price = pi.value;
    document.getElementById("o-est").textContent = q && pr ? fmtINR(Math.round(q * pr * 100) / 100) : "—";
    try { localStorage.setItem("tf-order", JSON.stringify({type: ORD.type, product: ORD.product, broker: ORD.broker, qty: ORD.qty})); } catch (e) {} };
  document.getElementById("o-qty").addEventListener("input", est);
  document.getElementById("o-price").addEventListener("input", est);
  est();
}

// ---------------- My positions (kept only on this device until a broker is connected)
let POS = {}; try { POS = JSON.parse(localStorage.getItem("tf-pos") || "{}") || {}; } catch (e) {}
const savePos = () => { try { localStorage.setItem("tf-pos", JSON.stringify(POS)); return true; } catch (e) { return false; } };
function posCalc(r){
  const p = POS[r.symbol]; if (!p || !(p.qty > 0) || !(p.avg > 0)) return null;
  const ltp = num(r.last_close), inv = p.qty * p.avg, val = ltp ? p.qty * ltp : null, pl = val != null ? val - inv : null;
  return {qty: p.qty, avg: p.avg, inv, val, pl, pct: pl != null ? pl / inv * 100 : null, ltp};
}
const signed = (v, d = 2) => (v > 0 ? "+" : v < 0 ? "−" : "") + "₹" + Math.abs(v).toLocaleString("en-IN", {maximumFractionDigits: d});
function posStrip(r){
  const p = posCalc(r); if (!p) return "";
  const cls = p.pl == null ? "" : p.pl >= 0 ? "up" : "down";
  return `<button class="pos" data-open="${esc(r.symbol)}" data-tab="pos" aria-label="My position in ${esc(r.name || r.symbol)}">
    <span class="tag">My position</span>
    <span>Qty <b>${fmtN(p.qty, 0)}</b></span><span>Avg <b>${fmtINR(p.avg)}</b></span><span>Invested <b>${fmtINR(Math.round(p.inv))}</b></span>
    <span>P&amp;L <span class="pl ${cls}">${p.pl == null ? "—" : signed(p.pl, 0)}</span></span>
    <span class="pl ${cls}">${p.pct == null ? "" : (p.pct >= 0 ? "▲ " : "▼ ") + Math.abs(p.pct).toFixed(2) + "%"}</span></button>`;
}
function posHTML(r){
  const p = posCalc(r), have = POS[r.symbol] || {};
  const kv = (k, v, cls = "") => `<div class="kv"><div class="k">${k}</div><div class="v ${cls}">${v}</div></div>`;
  const cls = p && p.pl != null ? (p.pl >= 0 ? "up" : "down") : "";
  return (p ? `<div class="pgrid">${kv("Quantity", fmtN(p.qty, 0))}${kv("Avg buy price", fmtINR(p.avg))}${kv("Invested", fmtINR(Math.round(p.inv)))}
      ${kv("Current value", p.val != null ? fmtINR(Math.round(p.val)) : "—")}${kv("Profit / Loss", p.pl != null ? signed(p.pl, 0) : "—", cls)}
      ${kv("Gain / Loss %", p.pct != null ? (p.pct >= 0 ? "+" : "") + p.pct.toFixed(2) + "%" : "—", cls)}</div>` : "") +
    `<div class="aform"><label for="p-qty">Quantity</label><input id="p-qty" type="number" inputmode="numeric" min="0" step="1" value="${have.qty || ""}" placeholder="e.g. 50">
      <label for="p-avg">Avg buy price ₹</label><input id="p-avg" type="number" inputmode="decimal" min="0" step="0.01" value="${have.avg || ""}" placeholder="e.g. 285.40">
      <button class="btn pri" data-pos-save>Save</button>${p ? `<button class="btn" data-pos-del>Remove</button>` : ""}</div>
    <p class="src">Copy quantity and average price from your Zerodha / Angel One holdings. Profit and loss use the last closing price
      (${p && p.ltp ? fmtINR(p.ltp) : "—"}). Saved only on this device and never uploaded. When your broker is connected, positions fill in automatically.</p>`;
}
function totalsStat(){
  let inv = 0, val = 0, n = 0;
  for (const k of ["SP", "DT"]) for (const r of D[k]) { const p = posCalc(r); if (p && p.val != null) { inv += p.inv; val += p.val; n++; } }
  if (!n) return "";
  const pl = val - inv, pct = pl / inv * 100;
  return `<div class="stat"><div class="k">My positions · ${n}</div><div class="v ${pl >= 0 ? "up" : "down"}">${signed(pl, 0)}<small>${(pct >= 0 ? "+" : "") + pct.toFixed(2)}% on ${fmtINR(Math.round(inv))}</small></div></div>`;
}
function posChanged(){ drawList(); drawStrip(); if (cur) { drawHead(); if (curTab === "pos") drawPanel(); } }

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
  if (e.target.closest("[data-pos-save]") && cur) { const q = +document.getElementById("p-qty").value, a = +document.getElementById("p-avg").value;
    if (!(q > 0) || !(a > 0)) { showToast("Enter both quantity and average price."); return; }
    POS[cur.r.symbol] = {qty: q, avg: a, updated: new Date().toISOString().slice(0, 10)};
    showToast(savePos() ? "✅ Position saved on this device." : "⚠️ This browser is blocking storage, so the position can't be saved."); posChanged(); return; }
  if (e.target.closest("[data-pos-del]") && cur) { delete POS[cur.r.symbol]; savePos(); showToast("Position removed."); posChanged(); return; }
  const ob = e.target.closest("[data-order]"); if (ob) { openOrder(ob.dataset.sym, ob.dataset.order); return; }
  const os = e.target.closest("[data-oset]"); if (os) { ORD[os.dataset.oset] = os.dataset.val; const [r] = findRow(ORD.sym); if (r) drawOrder(r); return; }
  if (e.target.closest("[data-oclose]") || e.target.id === "oscrim") { closeOrder(); return; }
  const ai = e.target.closest("[data-alert-op]"); if (ai) { closeMenu(); saveAlert(cur.r.symbol, cur.r.name, ai.dataset.alertOp, +ai.dataset.alertPrice); return; }
  const sv = e.target.closest("[data-save-alert]"); if (sv && cur) { if (!connected()) { needConnect(); return; } saveAlert(cur.r.symbol, cur.r.name, document.getElementById("a-op").value, document.getElementById("a-price").value); return; }
  const da = e.target.closest("[data-del-alert]"); if (da) { deleteAlert(+da.dataset.delAlert, da); return; }
  if (e.target.closest("[data-gh-connect]")) { ghConnect(); return; }
  if (e.target.closest("[data-st-new]")) { if (!connected()) { needConnect(); return; } stForm = {}; drawStrategies(); document.getElementById("st-name").focus(); return; }
  if (e.target.closest("[data-st-migrate]")) { migrateLocal(); return; }
  if (e.target.closest("[data-st-forget]")) { LOCAL_ST = []; try { localStorage.removeItem("tf-strategies"); } catch (x) {} drawStrategies(); return; }
  if (e.target.closest("[data-st-cancel]")) { stForm = null; drawStrategies(); return; }
  if (e.target.closest("[data-st-save]")) { saveStrategy(); return; }
  const se = e.target.closest("[data-st-edit]"); if (se) { if (!connected()) { needConnect(); return; } const x = STRAT.find(t => t.id === se.dataset.stEdit); stForm = Object.assign({}, x); drawStrategies(); return; }
  const sd = e.target.closest("[data-st-del]"); if (sd) { delStrategy(sd.dataset.stDel, sd); return; }
  if (e.target.closest("[data-gh-disconnect]")) { ghDisconnect(); return; }
  if (e.target.closest("[data-goto-alerts]")) { e.preventDefault(); closePanel(); location.hash = "alerts"; show("alerts"); return; }
  const ac = e.target.closest("[data-alert-custom]"); if (ac) { closeMenu(); const pr = ac.dataset.alertCustom; curTab = "alert"; drawPanel();
    const inp = document.getElementById("a-price"); inp.value = pr; inp.dispatchEvent(new Event("input")); inp.focus(); return; }
  if (!e.target.closest("#ctx")) closeMenu();
  const cp = e.target.closest("[data-copy]"); if (cp) { const t = document.getElementById(cp.dataset.copy).textContent;
    const done = () => { cp.textContent = "Copied"; setTimeout(() => cp.textContent = "Copy", 1500); };
    try { navigator.clipboard.writeText(t).then(done, () => { getSelection().selectAllChildren(document.getElementById(cp.dataset.copy)); }); }
    catch (x) { getSelection().selectAllChildren(document.getElementById(cp.dataset.copy)); } return; }
  const em = e.target.closest("[data-ema]"); if (em) { const p = +em.dataset.ema; emaOn[p] = emaOn[p] === false;
    try { localStorage.setItem("tf-ema", JSON.stringify(emaOn)); } catch (x) {} drawChart(); return; }
  const tf = e.target.closest("[data-tf]"); if (tf) { curTf = tf.dataset.tf;
    document.querySelectorAll("[data-tf]").forEach(b => b.setAttribute("aria-pressed", b === tf)); drawChart(); return; }
  const rg = e.target.closest("[data-range]"); if (rg) { curRange = +rg.dataset.range;
    document.querySelectorAll("[data-range]").forEach(b => b.setAttribute("aria-pressed", b === rg)); setRange(); return; }
});
document.getElementById("p-close").addEventListener("click", requestClose);
document.getElementById("p-prev").addEventListener("click", () => stepStock(-1));
document.getElementById("p-next").addEventListener("click", () => stepStock(1));
document.addEventListener("keydown", e => {
  if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && !e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey && cur && document.getElementById("order").hidden && document.getElementById("ctx").hidden
      && !e.target.closest("input,select,textarea")) { e.preventDefault(); stepStock(e.key === "ArrowLeft" ? -1 : 1); return; }
  if (e.key !== "Escape") return; if (!document.getElementById("ctx").hidden) { closeMenu(); return; }
  if (e.target.closest("input,select,textarea") && document.getElementById("order").hidden) { e.target.blur(); return; }
  if (!document.getElementById("order").hidden) { closeOrder(); return; } if (cur) requestClose(); });
document.addEventListener("scroll", closeMenu, true);

// ---------------- Strategies: settings are saved in GitHub (data/strategies.json) through the Price Alerts robot,
// so every device and the trading robot see the same list. Paper trading until a broker is connected.
const SD = D.strat || {settings: [], setups: {}, open: [], closed: []};
let STRAT = (SD.settings || []).map(x => Object.assign({}, x)), stForm = null, stPending = {};
let LOCAL_ST = []; try { LOCAL_ST = JSON.parse(localStorage.getItem("tf-strategies") || "[]"); if (!Array.isArray(LOCAL_ST)) LOCAL_ST = []; } catch (e) {}
LOCAL_ST = LOCAL_ST.filter(l => !STRAT.some(t => t.name.toLowerCase() === String(l.name || "").toLowerCase()));
const LISTS = {SP: "SP", DT: "DT", BOTH: "SP + DT"}, TYPES = {swing: "Swing Strategy rules", positional: "Positional Trading rules", switch: "Smart Switch (Smallcap 100 decides the exits)", none: "Rules not added yet"};
const RULED = t => t.type === "swing" || t.type === "positional" || t.type === "switch";
const inr0 = v => v == null || !isFinite(v) ? "—" : "₹" + Number(v).toLocaleString("en-IN", {maximumFractionDigits: 0});
const inr2 = v => v == null || !isFinite(v) ? "—" : "₹" + Number(v).toLocaleString("en-IN", {maximumFractionDigits: 2});
const sgn0 = v => (v >= 0 ? "+" : "−") + inr0(Math.abs(v));
async function sendStrategy(obj, okMsg){
  if (!connected()) { needConnect(); return false; }
  try { await sendRequest(obj); showToast(okMsg + " <span class='mut'>(saved to GitHub in about a minute)</span>"); laterRefreshStrat(); return true; }
  catch (e) { saveError(e); return false; }
}
function laterRefreshStrat(){ for (const ms of [60000, 150000, 300000]) setTimeout(refreshStrat, ms); }
async function refreshStrat(){
  if (!REPO) return;
  try {
    const st = await fetch(`https://raw.githubusercontent.com/${REPO}/main/data/strategies.json?t=${Date.now()}`, {cache: "no-store"}).then(r => r.ok ? r.json() : Promise.reject(r.status));
    if (Array.isArray(st.strategies)) {
      // built-in strategies added in an update (e.g. Positional Trading) stay visible until removed
      const gone = new Set(st.deleted || []), have = new Set(st.strategies.map(x => x.id));
      STRAT = [...st.strategies, ...(SD.settings || []).filter(x => !have.has(x.id) && !gone.has(x.id))]; stPending = {}; if (view === "strategy" && !stForm) drawStrategies(); else document.getElementById("c-strategy").textContent = STRAT.filter(t => t.on).length; }
  } catch (e) {}
}
function tradeRows(list, open){
  if (!list.length) return `<div class="empty">${open ? "No open trades." : "No closed trades yet."}</div>`;
  return `<div class="tbl"><table><thead><tr><th>Stock</th><th>Entry</th><th class="ra">Qty</th><th class="ra">Entry ₹</th>${open
      ? `<th class="ra">Stop</th><th class="ra">Target</th><th class="ra">Now</th><th class="ra">P&amp;L</th>` : `<th>Exit</th><th class="ra">P&amp;L</th>`}</tr></thead><tbody>` +
    list.map(t => {
      const ltp = num(t.ltp), unreal = open && ltp ? (ltp - t.entry) * t.remaining : 0, pl = (t.pnl || 0) + unreal;
      const exits = (t.exits || []).map(x => `${esc(x.date)}: ${x.qty} @ ${inr2(x.price)} — ${esc(x.reason)}`).join("<br>");
      return `<tr><td><b>${esc(t.name || t.symbol)}</b><br><span class="sym mut">${esc(t.symbol)}</span></td><td class="num">${esc(t.entry_date)}</td>
        <td class="num ra">${open ? t.remaining + (t.remaining !== t.qty ? " / " + t.qty : "") : t.qty}</td><td class="num ra">${inr2(t.entry)}</td>` +
        (open ? `<td class="num ra">${inr2(t.stop)}${t.signal_low ? `<br><span class="mut">trail ${inr2(t.signal_low)}</span>` : ""}</td>
                 <td class="num ra">${t.booked ? "50% booked" : inr2(t.target)}</td><td class="num ra">${ltp ? inr2(ltp) : "—"}</td>`
              : `<td class="why">${exits}</td>`) +
        `<td class="num ra ${pl >= 0 ? "up" : "down"}"><b>${sgn0(pl)}</b></td></tr>`;
    }).join("") + `</tbody></table></div>`;
}
// ---- performance report (paper trading and backtest) and the trade log
function curveSVG(curve){
  if (!curve || curve.length < 2) return "";
  const W = 640, H = 140, P = 6, ys = [0, ...curve.map(c => c[1])], lo = Math.min(...ys), hi = Math.max(...ys), span = hi - lo || 1;
  const x = i => P + i * (W - 2 * P) / (curve.length - 1), y = v => H - P - (v - lo) * (H - 2 * P) / span;
  const pts = curve.map((c, i) => `${x(i).toFixed(1)},${y(c[1]).toFixed(1)}`).join(" ");
  const end = curve[curve.length - 1][1];
  return `<svg class="eq" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Profit growing trade by trade, ending at ${esc(sgn0(end))}">
    <line x1="0" x2="${W}" y1="${y(0)}" y2="${y(0)}" class="eq0"/><polyline points="${pts}" class="${end >= 0 ? "eqU" : "eqD"}"/></svg>
    <div class="eqlab"><span>${esc(curve[0][0])}</span><span>${esc(curve[curve.length - 1][0])}</span></div>`;
}
function perfTable(r, extra){
  if (!r || !r.trades) return `<div class="empty">${extra || "No closed trades yet."}</div>`;
  const row = (k, v, cls) => `<div class="kv"><div class="k">${k}</div><div class="v ${cls || ""}">${v}</div></div>`;
  const pf = r.profit_factor, wr = r.win_rate;
  return `<div class="kgrid">` +
    row("Closed trades", r.trades + (r.open ? ` <small class="mut">+${r.open} open</small>` : "")) +
    row("Win rate", wr == null ? "—" : wr + "%", "") +
    row("Total P&amp;L", sgn0(r.total_pnl), r.total_pnl >= 0 ? "up" : "down") +
    row("Avg win", r.avg_win == null ? "—" : sgn0(r.avg_win), "up") +
    row("Avg loss", r.avg_loss == null ? "—" : sgn0(r.avg_loss), "down") +
    row("Profit factor", pf == null ? "—" : pf, pf == null ? "" : pf >= 1.5 ? "up" : pf < 1 ? "down" : "") +
    row("Avg P&amp;L per trade", r.expectancy == null ? "—" : sgn0(r.expectancy), r.expectancy >= 0 ? "up" : "down") +
    row("Avg return per trade", r.avg_return_pct == null ? "—" : r.avg_return_pct + "%") +
    row("Max drawdown", inr0(r.max_drawdown), "down") +
    row("Avg holding", r.avg_hold_days == null ? "—" : r.avg_hold_days + " days") +
    row("Best / worst", `${sgn0(r.best)} / ${sgn0(r.worst)}`) +
    (r.open ? row("Open trades now", sgn0(r.open_pnl || 0), (r.open_pnl || 0) >= 0 ? "up" : "down") : "") +
    (r.without_best != null ? row("Without the best trade", sgn0(r.without_best), r.without_best >= 0 ? "up" : "down") : "") +
    `</div>` + curveSVG(r.curve);
}
function readiness(r){
  const n = r ? r.trades : 0, pf = r && r.profit_factor, wr = r && r.win_rate;
  const ck = (ok, txt) => `<li class="${ok ? "up" : "mut"}">${ok ? "✓" : "○"} ${txt}</li>`;
  return `<ul class="ready">` +
    ck(n >= 30, `At least 30 closed paper trades <b>(${n} of 30)</b> — enough trades to judge`) +
    ck(pf != null && pf >= 1.5 && n >= 10, `Profit factor 1.5 or more <b>(${pf == null ? "—" : pf})</b> — winners clearly bigger than losers${n < 10 ? " · counts after 10 trades" : ""}`) +
    ck(r && r.total_pnl > 0 && n >= 10, `Total paper P&amp;L positive <b>(${r ? sgn0(r.total_pnl || 0) : "—"})</b>${n < 10 ? " · counts after 10 trades" : ""}`) +
    ck(r && r.max_drawdown != null && n >= 10 && r.max_drawdown <= Math.max(1, r.total_pnl), `Worst fall (drawdown) smaller than the total profit`) +
    `</ul><p class="src">These are common checks before trading a system with real money; they are not a guarantee.
    Paper results leave out brokerage, taxes and slippage (roughly 0.3–0.5% per round trip in small caps).</p>`;
}
function yearTable(months){
  const ys = {}; for (const [m, v] of Object.entries(months || {})) ys[m.slice(0, 4)] = (ys[m.slice(0, 4)] || 0) + v;
  const ks = Object.keys(ys).sort().reverse(); if (!ks.length) return "";
  return `<div class="ph2" style="margin-top:12px">Profit by year</div><div class="yrs">${ks.map(k =>
    `<span class="yrc ${ys[k] >= 0 ? "pos" : "neg"}"><b>${k}</b> ${sgn0(ys[k])}</span>`).join("")}</div>`;
}
function logTable(rows, sid){
  const mine = rows.filter(r => !sid || r.strategy === sid || r.trade_id.startsWith(sid + "-"));
  const csv = REPO ? `https://raw.githubusercontent.com/${REPO}/main/data/trade_log.csv` : "";
  return (mine.length ? `<div class="tbl"><table><thead><tr><th>Date</th><th>Action</th><th>Stock</th><th class="ra">Qty</th><th class="ra">Price</th><th>Reason</th><th class="ra">P&amp;L</th><th class="ra">Days</th></tr></thead><tbody>` +
    mine.slice(0, 200).map(r => `<tr><td class="num">${esc(r.date)}</td><td><span class="pill ${r.action === "BUY" ? "p-sp" : +r.pnl >= 0 ? "p-add" : "p-dt"}">${esc(r.action)}</span></td>
      <td><b>${esc(r.name)}</b><br><span class="sym mut">${esc(r.symbol)}</span></td><td class="num ra">${esc(r.qty)}</td><td class="num ra">${inr2(+r.price)}</td>
      <td class="why">${esc(r.reason)}</td><td class="num ra ${+r.pnl >= 0 ? "up" : "down"}">${r.pnl === "" ? "" : sgn0(+r.pnl) + (r.pnl_pct !== "" ? `<br><span class="mut">${esc(r.pnl_pct)}%</span>` : "")}</td>
      <td class="num ra">${esc(r.hold_days)}</td></tr>`).join("") + `</tbody></table></div>`
    : `<div class="empty">No trades yet. Every paper BUY and SELL will be written here with date, price, reason and P&amp;L.</div>`) +
    (csv ? `<p class="src"><a href="${esc(csv)}" target="_blank" rel="noopener" download>⬇ Download the full trade log (opens in Excel)</a> — every trade is kept permanently in <span class="sym">data/trade_log.csv</span>.</p>` : "");
}
function btTrades(list){
  if (!list || !list.length) return "";
  return `<details class="bt"><summary>Show the ${list.length} backtest trades</summary><div class="tbl"><table><thead><tr><th>Stock</th><th>Entry</th><th class="ra">Entry ₹</th><th>Exits</th><th class="ra">P&amp;L</th><th class="ra">Days</th></tr></thead><tbody>` +
    list.map(t => `<tr><td><b>${esc(t.name)}</b><br><span class="sym mut">${esc(t.symbol)}</span></td><td class="num">${esc(t.entry_date)}</td><td class="num ra">${inr2(t.entry)}</td>
      <td class="why">${t.status === "closed" ? (t.exits || []).map(x => `${esc(x.date)}: ${esc(x.reason)} @ ${inr2(x.price)}`).join("<br>") : "still open"}</td>
      <td class="num ra ${(t.status === "closed" ? t.pnl : t.open_pnl || 0) >= 0 ? "up" : "down"}">${sgn0(t.status === "closed" ? t.pnl : t.open_pnl || 0)}${t.pnl_pct != null ? `<br><span class="mut">${esc(t.pnl_pct)}%</span>` : ""}</td>
      <td class="num ra">${esc(t.hold_days ?? "")}</td></tr>`).join("") + `</tbody></table></div></details>`;
}
function capitalCard(c){
  if (!c) return "";
  const g = c.equity - c.start;
  return `<div class="capc"><div><div class="k">Paper capital now</div><div class="v ${g >= 0 ? "up" : "down"}">${inr0(c.equity)}</div>
      <div class="mut">started ${inr0(c.start)} · ${g >= 0 ? "+" : "−"}${(Math.abs(g) / c.start * 100).toFixed(1)}%</div></div>
    <div><div class="k">In open trades</div><div class="v">${inr0(c.invested)}</div><div class="mut">free cash ${inr0(c.cash)}</div></div>
    <div><div class="k">Next trade size</div><div class="v">${inr0(c.equity * c.pct / 100)}</div><div class="mut">${esc(c.pct)}% of current capital</div></div></div>`;
}
function monthChips(months){
  const ks = Object.keys(months || {}).sort(); if (!ks.length) return "";
  const M = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return `<div class="yrs">${ks.map(k => `<span class="yrc ${months[k] >= 0 ? "pos" : "neg"}"><b>${M[+k.slice(5) - 1]} ${k.slice(2, 4)}</b> ${sgn0(months[k])}</span>`).join("")}</div>`;
}
function yearSplit(bt){
  const y2 = bt.year2, y1 = bt.year1; if (!y2 && !y1) return "";
  const cell = (lab, y) => !y ? "" : `<div class="kv"><div class="k">${lab}</div><div class="v ${y.profit >= 0 ? "up" : "down"}">${y.return_pct >= 0 ? "+" : ""}${esc(y.return_pct)}%</div>
    <div class="mut" style="font-size:12px">${inr0(y.capital)} → ${inr0(y.final)} · ${esc(y.trades)} trades · ${esc(y.win_rate ?? "—")}% in profit · worst fall ${esc(y.max_drawdown_pct)}%</div></div>`;
  return `<div class="kgrid yrsplit">${cell("2nd last year (" + esc(y2 && y2.start) + " →)", y2)}${cell("Last year (" + esc(y1 && y1.start) + " →)", y1)}</div>`;
}
function compareHTML(){
  const rows = STRAT.filter(RULED).map(t => ({t, b: (SD.backtest || {})[t.id] || {}})).filter(x => x.b.last2y);
  if (rows.length < 2) return "";
  const best = rows.reduce((a, x) => (x.b.last2y.return_pct > a.b.last2y.return_pct ? x : a), rows[0]);
  const pc = y => !y ? "—" : `<span class="${y.return_pct >= 0 ? "up" : "down"}">${y.return_pct >= 0 ? "+" : ""}${esc(y.return_pct)}%</span>`;
  return `<h2>Which strategy did best? · last 2 years</h2><div class="tbl"><table><thead><tr><th>Strategy</th><th class="ra">2nd last year</th><th class="ra">Last year</th>
    <th class="ra">2 years</th><th class="ra">₹10 lakh became</th><th class="ra">Trades</th><th class="ra">In profit</th><th class="ra">Worst fall</th></tr></thead><tbody>` +
    rows.map(({t, b}) => `<tr${t.id === best.t.id ? ' class="best"' : ""}><td><b>${esc(t.name)}</b>${t.id === best.t.id ? ' <span class="pill p-add">best</span>' : ""}</td>
      <td class="num ra">${pc(b.year2)}</td><td class="num ra">${pc(b.year1)}</td><td class="num ra"><b>${pc(b.last2y)}</b></td>
      <td class="num ra">${inr0(b.last2y.final * 1000000 / b.last2y.capital)}</td><td class="num ra">${esc(b.last2y.trades)}</td>
      <td class="num ra">${esc(b.last2y.win_rate ?? "—")}%</td><td class="num ra down">${esc(b.last2y.max_drawdown_pct)}%</td></tr>`).join("") +
    `</tbody></table></div><p class="src">Each strategy: ₹10,00,000 paper capital, every trade 10% of the capital at that moment, costs included, open trades valued at today's price.
    Uses the stocks in the list today, so real results would likely be lower.</p>`;
}
function yearsHTML(){
  const bt = SD.backtest || {}, mk = ((bt._market || {}).years) || {};
  const strats = STRAT.filter(RULED).filter(t => (bt[t.id] || {}).by_year);
  if (!strats.length) return "";
  const years = Object.keys(bt[strats[0].id].by_year).sort().reverse();
  const tag = {bull: '<span class="pill p-add">bull</span>', bear: '<span class="pill p-dt">bear</span>', sideways: '<span class="pill p-warn">sideways</span>'};
  const cell = y => !y || !y.trades ? '<span class="mut">no trades</span>' :
    `<span class="${y.return_pct >= 0 ? "up" : "down"}">${y.return_pct >= 0 ? "+" : ""}${esc(y.return_pct)}%</span> <span class="mut">(${esc(y.trades)})</span>`;
  const sum = {bull: {}, bear: {}, sideways: {}};
  for (const yr of years) { const m = mk[yr]; if (!m || m.partial) continue;
    for (const t of strats) { const y = bt[t.id].by_year[yr]; if (!y || !y.trades) continue;
      const g = (sum[m.phase][t.id] = sum[m.phase][t.id] || {n: 0, f: 1}); g.n++; g.f *= 1 + y.return_pct / 100; } }
  const avgRow = ph => `<tr class="avg"><td colspan="2"><b>Average ${ph} year</b></td>` + strats.map(t => { const g = sum[ph][t.id];
    if (!g) return '<td class="num ra mut">—</td>'; const a = (Math.pow(g.f, 1 / g.n) - 1) * 100;
    return `<td class="num ra"><b class="${a >= 0 ? "up" : "down"}">${a >= 0 ? "+" : ""}${a.toFixed(1)}%</b> <span class="mut">${g.n} yr</span></td>`; }).join("") + `</tr>`;
  const hist = bt[strats[0].id].stocks_with_history || {};
  return `<h2>Bull vs bear markets · last 10 years</h2><div class="tbl"><table><thead><tr><th>Year</th><th>Smallcap 100</th>${strats.map(t =>
      `<th class="ra">${esc(t.name)}</th>`).join("")}<th class="ra">Stocks with history</th></tr></thead><tbody>` +
    years.map(yr => { const m = mk[yr];
      return `<tr><td class="num">${esc(yr)}${m && m.partial ? " <span class='mut'>(so far)</span>" : ""}</td>
        <td>${m ? `${tag[m.phase]} <span class="num ${m.change >= 0 ? "up" : "down"}">${m.change >= 0 ? "+" : ""}${esc(m.change)}%</span>` : '<span class="mut">index not loaded yet</span>'}</td>` +
        strats.map(t => `<td class="num ra">${cell(bt[t.id].by_year[yr])}</td>`).join("") + `<td class="num ra mut">${esc(hist[yr] ?? "")}</td></tr>`; }).join("") +
    ["bull", "sideways", "bear"].map(avgRow).join("") +
    `</tbody></table></div><p class="src">Each year starts again with ₹10,00,000 (10% per trade, costs included); number of trades in brackets.
    Bull = Smallcap 100 up 15% or more in the year, bear = down 10% or more. Only stocks in your list today are tested, and many listed recently
    (see "Stocks with history"), so older years have few trades. The 10-year index history fills in over the next 2–3 robot runs.</p>`;
}
function last2HTML(p){
  if (!p || !p.trades) return "";
  const curve = (p.curve || []).map(([m, v]) => [m, v - p.capital]);
  return `<div class="pcol l2"><div class="ph2">📅 Last 2 years with ${inr0(p.capital)} <span class="mut">(each trade ${esc(p.pct)}% of the capital at that moment, costs included, from ${esc(p.start)})</span></div>
    <div class="kgrid">
      <div class="kv"><div class="k">Capital now</div><div class="v ${p.profit >= 0 ? "up" : "down"}">${inr0(p.final)}</div></div>
      <div class="kv"><div class="k">Profit</div><div class="v ${p.profit >= 0 ? "up" : "down"}">${sgn0(p.profit)} <small>(${p.return_pct >= 0 ? "+" : ""}${esc(p.return_pct)}%)</small></div></div>
      <div class="kv"><div class="k">Trades taken</div><div class="v">${esc(p.trades)}${p.open_trades ? ` <small class="mut">${esc(p.open_trades)} still open, valued at today's price</small>` : ""}${p.skipped ? ` <small class="mut">${esc(p.skipped)} skipped (no free cash)</small>` : ""}</div></div>
      <div class="kv"><div class="k">Ended in profit</div><div class="v">${esc(p.win_rate ?? "—")}%</div></div>
      <div class="kv"><div class="k">Worst fall</div><div class="v down">${esc(p.max_drawdown_pct)}%</div></div>
    </div>${curveSVG(curve)}<div class="ph2" style="margin-top:12px">Profit by month</div>${monthChips(p.months)}</div>`;
}
function moodHTML(t){
  if (t.type !== "switch") return "";
  const m = (SD.mood || {})[t.id];
  if (!m) return `<div class="st-note">🧭 Nifty Smallcap 100 not checked yet — it appears after the next robot run.</div>`;
  return `<div class="st-note mood ${m.above ? "pos" : "neg"}">🧭 <b>Nifty Smallcap 100 ${inr0(m.close).slice(1)}</b> is <b>${m.above ? "above" : "below"}</b> its EMA 50 (${inr0(m.ema50).slice(1)}) on ${esc(m.date)}
    → open trades follow the <b>${esc(m.rules)}</b> exit rules today (${m.rules === "Positional" ? "50% at +30%, rest on 2 closes below EMA 50" : "50% at +20%, EMA 10 trail, 10-day time stop"}).
    The robot checks the index every day, so a trade switches rules when small caps turn strong or weak.</div>`;
}
function perfHTML(t){
  const live = (SD.live || {})[t.id], bt = (SD.backtest || {})[t.id] || {};
  return moodHTML(t) + `<h2>${esc(t.name)} · is it working?</h2>
    <div class="perf">
      <div class="pcol"><div class="ph2">📝 Paper trading <span class="mut">(real days since you switched it ON)</span></div>
        ${capitalCard((SD.capital || {})[t.id])}
        ${perfTable(live, t.on ? "No closed paper trades yet — they appear here as the strategy trades." : "Switch the strategy ON to start paper trading.")}
        <div class="ph2" style="margin-top:12px">Ready for real money?</div>${readiness(live)}</div>
      <div class="pcol"><div class="ph2">🧪 Backtest · last 2 years <span class="mut">(same rules on the past prices of ${esc(bt.stocks || 0)} stocks in ${LISTS[t.list] || "SP"}, ₹1,00,000 per trade, costs included${bt.as_of ? ", " + esc(bt.as_of) : ""})</span></div>
        ${perfTable(bt.report, "Backtest appears after the next robot run.")}
        <p class="src">Backtest uses the stocks in the list <b>today</b> (they are strong now), so it looks better than real trading would have. Use it to compare rule changes; trust the paper trading log for the real decision.</p>
        ${btTrades(bt.trades)}</div>
    </div>
    ${last2HTML(bt.last2y).replace('<div class="kgrid">', yearSplit(bt) + '<div class="kgrid">')}
    <h2>${esc(t.name)} · trade log</h2>${logTable(SD.log || [], t.id)}`;
}
function setupRows(list){
  if (!list || !list.length) return `<div class="empty">No setups today. When a stock meets all entry rules it appears here with its buy-stop price.</div>`;
  return `<div class="tbl"><table><thead><tr><th>Stock</th><th class="ra">Buy above</th><th class="ra">Stop</th><th class="ra">Risk</th><th class="ra">Qty</th><th class="ra">Amount</th><th class="ra">Base range</th></tr></thead><tbody>` +
    list.map(x => `<tr><td><b>${esc(x.name)}</b><br><span class="sym mut">${esc(x.symbol)}</span></td><td class="num ra"><b>${inr2(x.buy_above)}</b></td>
      <td class="num ra">${inr2(x.stop)}</td><td class="num ra">${esc(x.risk_pct)}%</td><td class="num ra">${esc(x.qty)}</td><td class="num ra">${inr0(x.amount)}</td><td class="num ra">${esc(x.range_pct)}%</td></tr>`).join("") +
    `</tbody></table></div>`;
}
function drawStrategies(){
  const on = STRAT.filter(t => t.on).length;
  document.getElementById("c-strategy").textContent = on;
  const f = stForm;
  const form = f ? `<div class="aform st-form">
      <b>${f.id ? "Edit strategy" : "New strategy"}</b>
      <div class="fr"><label for="st-name">Name</label><input id="st-name" maxlength="40" placeholder="e.g. 52W High Breakout" value="${esc(f.name || "")}"></div>
      <div class="fr"><label for="st-type">Rules</label><select id="st-type">${Object.entries(TYPES).map(([k, l]) =>
        `<option value="${k}" ${(f.type || "none") === k ? "selected" : ""}>${l}</option>`).join("")}</select></div>
      <div class="fr"><label for="st-list">Stocks to scan</label><select id="st-list">${Object.entries(LISTS).map(([k, l]) =>
        `<option value="${k}" ${(f.list || "SP") === k ? "selected" : ""}>${l}</option>`).join("")}</select></div>
      <div class="fr"><label for="st-cap">Paper capital (₹)</label><input id="st-cap" type="number" inputmode="numeric" min="10000" step="10000" value="${esc(f.capital || 1000000)}"></div>
      <div class="fr"><label for="st-pct">Per trade (% of current capital)</label><input id="st-pct" type="number" inputmode="decimal" min="1" max="100" step="1" value="${esc(f.pct || 10)}"></div>
      <div class="fr"><label for="st-note">Notes (optional)</label><input id="st-note" maxlength="120" placeholder="Entry / exit idea in your words" value="${esc(f.note || "")}"></div>
      <div class="st-acts"><button class="btn pri" data-st-save>${f.id ? "Save changes" : "Add strategy"}</button><button class="btn" data-st-cancel>Cancel</button></div>
    </div>` : "";
  const cards = STRAT.map(t => {
    const opens = (SD.open || []).filter(x => x.strategy === t.id), closed = (SD.closed || []).filter(x => x.strategy === t.id);
    const realized = closed.reduce((a, x) => a + (x.pnl || 0), 0), wins = closed.filter(x => x.pnl > 0).length;
    const pend = stPending[t.id];
    const state = !RULED(t) ? `<span class="pill p-warn">${t.on ? "ON" : "OFF"}</span> Rules not added yet`
      : t.on ? `<span class="pill p-add">ON</span> Paper trading · ${opens.length} open · ${closed.length} closed${closed.length ? ` · win ${Math.round(wins / closed.length * 100)}% · ${sgn0(realized)}` : ""}`
      : `<span class="pill p-warn">OFF</span> Switch ON to start paper trading`;
    return `<article class="st ${t.on ? "on" : ""}">
      <div class="st-main"><div class="st-name">${esc(t.name)}</div>
        <div class="meta">${esc(TYPES[t.type] || TYPES.none)} · scans <b>${LISTS[t.list] || "SP"}</b> · capital ${inr0(t.capital || 1000000)} · ${esc(t.pct || 10)}% per trade${t.note ? " · " + esc(t.note) : ""}</div>
        <div class="st-state">${pend ? `<span class="pill p-sp">Saving…</span> ` : ""}${state}</div></div>
      <label class="sw" title="${t.on ? "Switch OFF" : "Switch ON"}"><input type="checkbox" data-st-toggle="${esc(t.id)}" ${t.on ? "checked" : ""} aria-label="${esc(t.name)} ON / OFF"><span></span></label>
      <div class="st-btns"><button class="btn" data-st-edit="${esc(t.id)}">Edit</button><button class="btn" data-st-del="${esc(t.id)}">Remove</button></div>
    </article>`;
  }).join("");
  const swing = STRAT.filter(RULED);
  const detail = swing.map(t => {
    const opens = (SD.open || []).filter(x => x.strategy === t.id), closed = (SD.closed || []).filter(x => x.strategy === t.id);
    return perfHTML(t) + `<h2>${esc(t.name)} · setups for today<span class="cnt">${((SD.setups || {})[t.id] || []).length}</span></h2>${setupRows((SD.setups || {})[t.id])}
      <h2>${esc(t.name)} · open trades<span class="cnt">${opens.length}</span></h2>${tradeRows(opens, true)}
      <h2>${esc(t.name)} · closed trades<span class="cnt">${closed.length}</span></h2>${tradeRows(closed, false)}`;
  }).join("");
  const local = LOCAL_ST.length ? `<div class="st-note">📱 ${LOCAL_ST.length} strateg${LOCAL_ST.length > 1 ? "ies were" : "y was"} saved only on this device earlier
      (${LOCAL_ST.map(l => esc(l.name)).join(", ")}). <button class="btn" data-st-migrate>Save to GitHub</button> <button class="btn" data-st-forget>Forget</button></div>` : "";
  document.getElementById("v-strategy").innerHTML = `
    <div class="st-head"><div><h2 style="margin:0">Strategies<span class="cnt">${STRAT.length}</span></h2>
      <div class="meta">${on} ON · data of ${esc((D.run || {}).price_date || "—")}</div></div>
      ${f ? "" : `<button class="btn pri" data-st-new>+ Add strategy</button>`}</div>
    <div class="st-note">📝 <b>Paper trading.</b> Strategies that are ON record the trades they would take (as buy-stop orders at the
      "buy above" price) and send them on Telegram each morning. Real orders start when your broker (Zerodha / Angel One) is connected through the VPS.</div>
    ${local}${form}
    <div class="st-list">${cards || (f ? "" : `<div class="empty">No strategies yet. Tap <b>+ Add strategy</b> to create one.</div>`)}</div>
    ${compareHTML()}
    ${yearsHTML()}
    ${detail}
    <p class="src">ON / OFF and changes are saved to your GitHub (needs the dashboard connected, see the Alerts tab). Prices and paper trades update with the 7 AM robot run.</p>`;
}
function saveStrategy(){
  const name = document.getElementById("st-name").value.trim();
  if (!name) { showToast("Type a name for the strategy."); return; }
  if (STRAT.some(t => t.name.toLowerCase() === name.toLowerCase() && t.id !== stForm.id)) { showToast("A strategy with this name already exists."); return; }
  const s = {id: stForm.id || "s" + Date.now().toString(36), name, type: document.getElementById("st-type").value, list: document.getElementById("st-list").value,
    capital: Math.max(10000, +document.getElementById("st-cap").value || 1000000), pct: Math.min(100, Math.max(1, +document.getElementById("st-pct").value || 10)), note: document.getElementById("st-note").value.trim(), on: !!stForm.on};
  sendStrategy({action: "strategy_save", strategy: s}, `✅ Strategy saved: <b>${esc(name)}</b>`).then(ok => {
    if (!ok) return;
    const i = STRAT.findIndex(t => t.id === s.id); if (i >= 0) STRAT[i] = Object.assign({}, STRAT[i], s); else STRAT.push(s);
    stPending[s.id] = 1; stForm = null; drawStrategies();
  });
}
function delStrategy(id, btn){
  if (btn.dataset.armed !== "1") { btn.dataset.armed = "1"; btn.textContent = "Tap again to remove";
    setTimeout(() => { if (btn.isConnected) { btn.dataset.armed = ""; btn.textContent = "Remove"; } }, 3000); return; }
  const t = STRAT.find(x => x.id === id);
  sendStrategy({action: "strategy_delete", id}, `🗑 Strategy removed: ${esc(t ? t.name : "")}`).then(ok => {
    if (ok) { STRAT = STRAT.filter(x => x.id !== id); drawStrategies(); } });
}
document.addEventListener("change", e => {
  const tg = e.target.closest("[data-st-toggle]"); if (!tg) return;
  const t = STRAT.find(x => x.id === tg.dataset.stToggle); if (!t) return;
  const want = tg.checked;
  tg.checked = !want;  // stays as it was until GitHub accepts the change
  sendStrategy({action: "strategy_save", strategy: Object.assign({}, t, {on: want})},
    want ? (RULED(t) ? `▶️ <b>${esc(t.name)}</b> is ON — paper trading starts with the next 7 AM run.`
                               : `▶️ <b>${esc(t.name)}</b> is ON. It will trade once its rules are added.`)
         : `⏸ <b>${esc(t.name)}</b> is OFF.`).then(ok => { if (ok) { t.on = want; stPending[t.id] = 1; drawStrategies(); } });
});
async function migrateLocal(){
  if (!connected()) { needConnect(); return; }
  for (const l of LOCAL_ST) {
    const s = {id: "s" + Date.now().toString(36) + Math.random().toString(36).slice(2, 5), name: String(l.name || "Strategy").slice(0, 40),
      type: "none", list: LISTS[l.list] ? l.list : "SP", capital: 1000000, pct: 10, note: String(l.note || "").slice(0, 120), on: false};
    try { await sendRequest({action: "strategy_save", strategy: s}); STRAT.push(s); stPending[s.id] = 1; } catch (e) { saveError(e); return; }
  }
  LOCAL_ST = []; try { localStorage.removeItem("tf-strategies"); } catch (e) {}
  showToast("✅ Saved to GitHub."); laterRefreshStrat(); drawStrategies();
}

function show(v){
  if (!["sp", "dt", "today", "history", "alerts", "strategy"].includes(v)) v = "sp";
  view = v;
  if (cur) { if (chartObj) { chartObj.remove(); chartObj = null; } cur = null; document.getElementById("panel").hidden = true;
    document.getElementById("strip").hidden = false; document.querySelector("main").classList.remove("wide"); document.body.classList.remove("viewing"); }
  document.querySelectorAll(".tabs .tab").forEach(t => t.setAttribute("aria-selected", t.dataset.v === v));
  document.getElementById("v-list").hidden = !(v === "sp" || v === "dt");
  document.getElementById("v-today").hidden = v !== "today";
  document.getElementById("v-history").hidden = v !== "history";
  document.getElementById("v-alerts").hidden = v !== "alerts";
  document.getElementById("v-strategy").hidden = v !== "strategy";
  if (v === "sp" || v === "dt") drawList();
  if (v === "strategy") drawStrategies();
}

let drawStrip = () => {};
(function init(){
  const r = D.run || {};
  const changes = ["added", "to_dt", "to_sp", "removed"].reduce((n, k) => n + ((r[k] || []).length), 0);
  document.getElementById("c-sp").textContent = D.SP.length;
  document.getElementById("c-dt").textContent = D.DT.length;
  document.getElementById("c-today").textContent = changes;
  document.getElementById("runline").textContent = r.run_at ? "Last run " + r.run_at + (r.price_date ? " · prices of " + r.price_date : "") : "Waiting for first run";
  const stat = (k, v, sub, cls) => `<div class="stat"><div class="k">${k}</div><div class="v ${cls || ""}">${v}${sub ? `<small>${sub}</small>` : ""}</div></div>`;
  const avg = l => { const m = l.map(marksOf).filter(x => x != null); return m.length ? (m.reduce((a, b) => a + b, 0) / m.length).toFixed(1) : "—"; };
  drawStrip = () => { document.getElementById("strip").innerHTML =
    stat("SP · above 200 EMA", D.SP.length, "stocks") +
    stat("DT · below 200 EMA", D.DT.length, "stocks", D.DT.length ? "down" : "") +
    stat("Changes in last run", changes, (r.added || []).length ? `${r.added.length} added` : "") +
    stat("Average marks (SP)", avg(D.SP), "/ " + FULL) + totalsStat(); };
  drawStrip();
  document.getElementById("note").textContent =
    `New stocks need ${D.cfg.pass_new} of ${FULL} marks to enter SP; SP and DT stocks need ${PASS} of ${FULL} on the monthly review (1st of each month). ` +
    `The black line on each marks bar is the pass mark. Marks shown are the automatic part of the TechnoFunda system, scaled to ${FULL}.` + (D.cfg.banner ? " " + D.cfg.banner : "");
  drawToday(); drawHistory(); drawAlerts(); drawStrategies();
  document.getElementById("c-alerts").textContent = (AL.active || []).length;
  refreshAlerts(); refreshStrat();
  document.querySelectorAll(".tabs .tab").forEach(t => t.addEventListener("click", () => { location.hash = t.dataset.v; show(t.dataset.v); }));
  document.getElementById("q").addEventListener("input", drawList);
  document.getElementById("sort").addEventListener("change", drawList);
  window.addEventListener("hashchange", () => show(location.hash.slice(1)));
  window.addEventListener("resize", fitChart);
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


def _alerts_view(store):
    store = store or {}
    items = store.get("alerts", [])
    return {"bot": store.get("bot_username", ""), "as_of": store.get("as_of", ""),
            "active": [a for a in items if a.get("status") == "active"],
            "done": [a for a in items if a.get("status") == "triggered"][-10:][::-1]}


def _strategy_view(strategies, sp, dt):
    if not strategies:
        return {"settings": [], "setups": {}, "open": [], "closed": []}
    book = strategies.get("book") or {}
    last = {s: (sp.get(s) or dt.get(s) or {}).get("last_close") for s in set(sp) | set(dt)}
    opens = [{**t, "ltp": last.get(t["symbol"])} for t in book.get("open", [])]
    import strategy as _stg
    live = {}
    for st in (strategies.get("settings") or {}).get("strategies", []):
        mine = [t for t in book.get("open", []) + book.get("closed", []) if t.get("strategy") == st.get("id")]
        rep = _stg.report([dict(t, open_pnl=round((float(last.get(t["symbol"]) or t["entry"]) - t["entry"]) * t["remaining"], 2))
                           if t.get("status") != "closed" else t for t in mine])
        live[st.get("id")] = rep
    return {"settings": (strategies.get("settings") or {}).get("strategies", []), "setups": book.get("setups", {}),
            "open": opens, "closed": book.get("closed", [])[-100:][::-1], "live": live,
            "backtest": strategies.get("backtest") or {}, "log": (strategies.get("log") or [])[-400:][::-1],
            "capital": {st.get("id"): _stg.capital_of(st, book) for st in (strategies.get("settings") or {}).get("strategies", [])},
            "mood": book.get("mood", {})}


def page_data(sp, dt, run, history, rules_cfg, banner="", snaps=None, charts=None, alerts=None, strategies=None):
    def rows(items):
        return [{**items[s], "symbol": s, "chart": chart_url(s),
                 "screener": screener_url(s, items[s].get("consolidated", "yes"))} for s in sorted(items)]
    return {
        "SP": rows(sp), "DT": rows(dt), "run": run or {}, "history": history or [],
        "fund": {k: v for k, v in (snaps or {}).items() if k in sp or k in dt},
        "alerts": _alerts_view(alerts),
        "strat": _strategy_view(strategies, sp, dt),
        "charts": charts,  # None on the live site: the page loads charts/SYMBOL.json instead
        "cfg": {"full": rules_cfg.get("full_marks", 11), "pass_new": rules_cfg.get("new_stock_pass", 7),
                "pass_monthly": rules_cfg.get("monthly_pass", 7), "banner": banner,
                "repo": rules_cfg.get("_repo", "")},
    }


def render_fragment(data):
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return FRAGMENT.replace("__DATA__", blob)


def build(sp, dt, run, history, rules_cfg, out=None, snaps=None, charts=None, alerts=None, strategies=None):
    """Write the dashboard page. charts (price history) goes to charts.json next to it, loaded when a chart opens."""
    out = out or OUT
    os.makedirs(os.path.dirname(out), exist_ok=True)
    page = FULL_PAGE.replace("{fragment}", render_fragment(page_data(sp, dt, run, history, rules_cfg, snaps=snaps, alerts=alerts, strategies=strategies)))
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
