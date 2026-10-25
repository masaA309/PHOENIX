"""QUADRANT / Q: isolated, fictional, offline read-only showcase.
Run with Python standard library only. Writes exactly one sibling HTML file.
"""
import json
import math
from pathlib import Path
from html.parser import HTMLParser

ROWS = [
    dict(code="7203", name="トヨタ自動車", side="LONG", execution="CASH", entry=2800, current=2960, stop=2890, quantity=200, risk=100, status="V-LOCK", score=92, signal="TREND CONTINUATION", holding="6 sessions", entry_time="SAMPLE D−6 / 09:15 JST"),
    dict(code="6758", name="ソニーグループ", side="SHORT", execution="MARGIN", entry=3400, current=3210, stop=3290, quantity=100, risk=120, status="V-LOCK", score=89, signal="DOWNTREND", holding="4 sessions", entry_time="SAMPLE D−4 / 09:30 JST"),
    dict(code="8306", name="三菱UFJフィナンシャルG", side="LONG", execution="CASH", entry=1800, current=1854, stop=1785, quantity=300, risk=60, status="TRAILING", score=85, signal="MOMENTUM", holding="3 sessions", entry_time="SAMPLE D−3 / 10:00 JST"),
    dict(code="8035", name="東京エレクトロン", side="SHORT", execution="MARGIN", entry=25000, current=25400, stop=25900, quantity=100, risk=900, status="HOLDING", score=81, signal="PULLBACK", holding="2 sessions", entry_time="SAMPLE D−2 / 09:45 JST"),
    dict(code="9432", name="NTT", side="LONG", execution="CASH", entry=160, current=156, stop=152, quantity=1000, risk=8, status="HOLDING", score=78, signal="BASE WATCH", holding="1 session", entry_time="SAMPLE D−1 / 10:15 JST"),
    dict(code="9984", name="ソフトバンクグループ", side="SHORT", execution="MARGIN", entry=9800, current=9510, stop=9870, quantity=100, risk=400, status="TRAILING", score=76, signal="WEAKNESS", holding="5 sessions", entry_time="SAMPLE D−5 / 09:20 JST"),
]
for p in ROWS:
    direction = 1 if p["side"] == "LONG" else -1
    change = direction * (p["current"] - p["entry"])
    p.update(pnl=change*p["quantity"], pct=change/p["entry"]*100,
             r=change/p["risk"], distance=abs(p["current"]-p["stop"]),
             distance_pct=abs(p["current"]-p["stop"])/p["current"]*100,
             strategy="SAMPLE / " + p["signal"],
             trailing="ACTIVE" if p["status"] in ("TRAILING", "V-LOCK") else "INACTIVE",
             profit_lock="SECURED" if p["status"] == "V-LOCK" else "NOT LOCKED")
    p["series"] = [round(p["entry"]+(p["current"]-p["entry"])*i/31
                        + math.sin(i*1.7)*p["risk"]*.23*math.sin(math.pi*i/31), 2)
                   for i in range(32)]

def audit_data():
    assert {p["code"] for p in ROWS} == {"7203","6758","8306","8035","9432","9984"}
    assert {p["status"] for p in ROWS} == {"HOLDING","TRAILING","V-LOCK"}
    assert {p["side"] for p in ROWS} == {"LONG","SHORT"}
    assert {p["execution"] for p in ROWS} == {"CASH","MARGIN"}
    assert any(p["pnl"] > 0 for p in ROWS) and any(p["pnl"] < 0 for p in ROWS)
    for p in ROWS:
        d = 1 if p["side"] == "LONG" else -1
        delta = d*(p["current"]-p["entry"])
        assert p["pnl"] == delta*p["quantity"]
        assert math.isclose(p["pct"], delta/p["entry"]*100)
        assert math.isclose(p["r"], delta/p["risk"])
        assert p["pnl"]*p["pct"] > 0 and p["pnl"]*p["r"] > 0
        assert p["distance"] == abs(p["current"]-p["stop"])
        assert math.isclose(p["distance_pct"], p["distance"]/p["current"]*100)
        assert d*(p["current"]-p["stop"]) > 0
        if p["status"] == "V-LOCK":
            assert p["pnl"] > 0 and d*(p["stop"]-p["entry"]) > 0
        assert p["series"][0] == p["entry"] and p["series"][-1] == p["current"]
    print("DATA INVARIANTS: PASS / 6 fictional positions")

TEMPLATE = r'''<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src 'none'; font-src 'none'; media-src 'none'; object-src 'none'; frame-src 'none'; worker-src 'none'; base-uri 'none'; form-action 'none'">
<title>QUADRANT / Q — READ ONLY SHOWCASE</title>
<style>
:root{color-scheme:dark;--bg:#0e1219;--panel:#141b26;--line:#293343;--text:#ecf0f6;--muted:#a5afc0;--blue:#80b7ff;--red:#ff8590;--green:#68dba5;--gold:#efcc7c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 "Segoe UI","Yu Gothic UI",Meiryo,sans-serif}
button{font:inherit;color:var(--text);background:#202b3c;border:1px solid #3c4c62;border-radius:5px;padding:7px 12px;cursor:pointer}
button:hover{background:#30405a;border-color:#95a8c3}button:focus-visible{outline:2px solid var(--blue);outline-offset:3px}
header{position:sticky;top:0;z-index:10;display:flex;align-items:center;justify-content:space-between;gap:15px;padding:19px 32px;background:#101620;border-bottom:1px solid var(--line)}
.brand{font-size:23px;letter-spacing:3px;font-weight:700}.ro{font-size:11px;letter-spacing:2px;color:var(--muted);margin-left:20px}
.safety{display:flex;gap:12px;flex-wrap:wrap;font-size:11px;font-weight:700;letter-spacing:1.5px}.demo{color:var(--gold);border:1px solid #685736;padding:5px 10px}.noorder{padding:5px 0;color:var(--muted)}
main{max-width:1520px;margin:auto;padding:28px 32px 40px}.intro{display:flex;justify-content:space-between;gap:20px;align-items:baseline;margin-bottom:24px}
h1{font-size:25px;font-weight:500;margin:0 0 5px}p{margin:0;color:var(--muted)}.eyebrow{font-size:11px;letter-spacing:2px;color:var(--muted);margin-bottom:7px}
section{margin-bottom:28px}.sectionhead{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:12px}
h2{font-size:15px;letter-spacing:1.8px;margin:0;font-weight:650}.sub{color:var(--muted);font-size:12px}
.tablewrap{overflow:auto;border:1px solid var(--line);border-radius:8px;background:var(--panel)}
table{width:100%;border-collapse:collapse;white-space:nowrap}th{text-align:left;font-size:10px;color:var(--muted);letter-spacing:1.2px;font-weight:500;background:#18202d;padding:12px 16px}
td{padding:13px 16px;border-top:1px solid var(--line);font-size:13px}tbody tr:hover{background:#1a2433}.num{text-align:right;font-variant-numeric:tabular-nums}.code{font-weight:700;letter-spacing:.6px}
.rank{color:var(--muted);font-size:12px}.side{display:inline-block;min-width:62px;text-align:center;border:1px solid;border-radius:4px;padding:3px 8px;font-size:11px;font-weight:700;letter-spacing:1px}
.long{color:var(--blue);border-color:#598ac2}.short{color:var(--red);border-color:#ba5965}.positive{color:var(--green)}.negative{color:var(--red)}.pnl{font-weight:650}
.status{font-size:11px;letter-spacing:.7px;font-weight:650}.holding{color:#c2cada}.trailing{color:var(--blue)}.v-lock,.gold{color:var(--gold)}.secured{display:block;font-size:8px;letter-spacing:1px;color:var(--gold);margin-top:2px}
.actions{display:flex;gap:7px}.actions button{padding:5px 10px;font-size:12px}.score{font-size:17px;font-weight:650}.signal{font-size:10px;letter-spacing:.5px;color:#c2ccdc}
.legend{display:flex;gap:22px;font-size:11px;color:var(--muted);margin-top:12px;flex-wrap:wrap}footer{border-top:1px solid var(--line);padding-top:16px;font-size:11px;color:var(--muted)}
.overlay{position:fixed;inset:0;background:#05080ec9;z-index:20}.overlay[hidden]{display:none}.drawer{position:absolute;right:0;top:0;bottom:0;width:min(460px,100%);overflow:auto;background:#151d29;border-left:1px solid #415169;padding:25px 28px}
.dialogtop{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:20px}.dialogtop .eyebrow{margin:0}.dialogname{font-size:23px;letter-spacing:1px;margin:0 0 4px}.company{font-size:16px;margin:0 0 15px}
.badges{display:flex;align-items:center;gap:15px;margin-bottom:24px}.metrics{display:grid;grid-template-columns:1.25fr 1fr 1fr;gap:8px;padding:17px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.metrics small{display:block;color:var(--muted);font-size:10px;margin-bottom:5px}.metrics strong{font-size:21px;font-variant-numeric:tabular-nums;white-space:nowrap}
.block{margin-top:24px}.block h3{font-size:11px;letter-spacing:1.6px;color:var(--muted);margin:0 0 12px}.protection{padding:16px;border:1px solid #52677d;border-radius:6px;background:#1b2939}
dl{margin:0}dl>div{display:flex;justify-content:space-between;gap:16px;padding:7px 0}dt{color:var(--muted);font-size:12px}dd{margin:0;text-align:right;font-size:13px}dd.emphasis{font-size:20px;font-weight:650;color:var(--blue)}
.note{font-size:10px;color:var(--muted);margin-top:12px;line-height:1.7}.modal{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:min(960px,94vw);max-height:92vh;overflow:auto;padding:25px;background:#151d29;border:1px solid #43536c;border-radius:10px}
.chartlegend{display:flex;gap:22px;margin:18px 0;font-size:11px;flex-wrap:wrap}.chartlegend span:before{content:"";display:inline-block;width:20px;height:2px;background:currentColor;margin:0 7px 3px 0}.price{color:#dce7f8}.entry{color:#929fb7}.stop{color:var(--blue);font-weight:700}
svg{display:block;width:100%;height:auto;background:#101823;border:1px solid var(--line);border-radius:6px}
.modal .chartfoot{display:flex;justify-content:space-between;margin-top:12px;gap:15px;font-size:11px;color:var(--muted)}
@media(max-width:760px){header{padding:14px 16px;align-items:flex-start;flex-direction:column;gap:8px}.brand{font-size:19px}.ro{margin-left:12px}main{padding:22px 16px}.intro{display:block}.intro .sub{margin-top:8px}td,th{padding:12px}.sectionhead{gap:10px}.metrics strong{font-size:18px}.drawer{padding:20px}.modal{padding:16px}}
</style>
</head>
<body>
<header><div><span class="brand">QUADRANT / Q</span><span class="ro">READ ONLY</span></div><div class="safety"><span class="demo">DEMO / SAMPLE DATA</span><span class="noorder">NO ORDER EXECUTION</span></div></header>
<main id="main">
<div class="intro"><div><div class="eyebrow">QUADRANT READ ONLY SHOWCASE</div><h1>候補とポジションを、一目で。</h1><p>すべて架空のサンプルです。実市場価格・実績を示すものではありません。</p></div><span class="sub">OFFLINE / SAMPLE SESSION</span></div>
<section aria-labelledby="screen-title"><div class="sectionhead"><h2 id="screen-title">MORNING SCREENING</h2><span class="sub">朝の候補 · SAMPLE / 6 CANDIDATES</span></div>
<div class="tablewrap"><table id="screening"><thead><tr><th>RANK</th><th>CODE</th><th>NAME</th><th>SIDE</th><th class="num">SCORE</th><th>SIGNAL</th><th>操作</th></tr></thead><tbody></tbody></table></div></section>
<section aria-labelledby="positions-title"><div class="sectionhead"><h2 id="positions-title">POSITIONS</h2><span class="sub">6 SAMPLE POSITIONS · JPY</span></div>
<div class="tablewrap"><table id="positions"><thead><tr><th>CODE</th><th>NAME</th><th>SIDE</th><th class="num">CURRENT</th><th class="num">P/L</th><th class="num">P/L %</th><th class="num">R</th><th>STATUS</th><th>HOLDING</th><th>操作</th></tr></thead><tbody></tbody></table></div>
<div class="legend"><span>HOLDING · 保有中</span><span>TRAILING · ストップ追随中</span><span class="gold">V-LOCK · PROFIT SECURED</span><span>損益は価格差による架空の評価損益</span></div></section>
<footer>DEMO / SAMPLE DATA · NO ORDER EXECUTION<br>CASH / MARGINはサンプル表示です。正式なLONGの執行方式を確定するものではありません。</footer>
</main>
<div id="detail-overlay" class="overlay" hidden><aside id="drawer" class="drawer" role="dialog" aria-modal="true" aria-labelledby="detail-name" tabindex="-1"></aside></div>
<div id="chart-overlay" class="overlay" hidden><div id="chart-modal" class="modal" role="dialog" aria-modal="true" aria-labelledby="chart-name" tabindex="-1"></div></div>
<script id="sample-data" type="application/json">__DATA__</script>
<script>
"use strict";
const samples=JSON.parse(document.getElementById("sample-data").textContent);
const byCode=Object.fromEntries(samples.map(p=>[p.code,p]));
const fmt=n=>Number(n).toLocaleString("en-US",{maximumFractionDigits:2});
const signed=(n,d=0)=>(n<0?"−":"+")+Math.abs(n).toLocaleString("en-US",{minimumFractionDigits:d,maximumFractionDigits:d});
const tone=p=>p.pnl<0?"negative":"positive";
const side=p=>'<span class="side '+p.side.toLowerCase()+'">'+p.side+'</span>';
const status=p=>'<span class="status '+p.status.toLowerCase()+'">'+p.status+'</span>'+(p.status==="V-LOCK"?'<span class="secured">PROFIT SECURED</span>':'');
const actions=(p,scope)=>'<div class="actions"><button data-action="detail" data-code="'+p.code+'" aria-label="'+scope+' '+p.code+' 詳細">詳細</button><button data-action="chart" data-code="'+p.code+'" aria-label="'+scope+' '+p.code+' チャート">チャート</button></div>';
document.querySelector("#screening tbody").innerHTML=samples.map((p,i)=>'<tr><td class="rank">'+String(i+1).padStart(2,"0")+'</td><td class="code">'+p.code+'</td><td>'+p.name+'</td><td>'+side(p)+'</td><td class="num score">'+p.score+'</td><td class="signal">'+p.signal+'</td><td>'+actions(p,"screening")+'</td></tr>').join("");
document.querySelector("#positions tbody").innerHTML=samples.map(p=>'<tr><td class="code">'+p.code+'</td><td>'+p.name+'</td><td>'+side(p)+'</td><td class="num">'+fmt(p.current)+'</td><td class="num pnl '+tone(p)+'">'+signed(p.pnl)+'</td><td class="num '+tone(p)+'">'+signed(p.pct,2)+'%</td><td class="num '+tone(p)+'">'+signed(p.r,2)+'R</td><td>'+status(p)+'</td><td class="sub">'+p.holding+'</td><td>'+actions(p,"positions")+'</td></tr>').join("");
const detailOverlay=document.getElementById("detail-overlay"),chartOverlay=document.getElementById("chart-overlay");
let activeOverlay=null,returnFocus=null;
function openOverlay(overlay,trigger){returnFocus=trigger;activeOverlay=overlay;overlay.hidden=false;document.getElementById("main").inert=true;document.body.style.overflow="hidden";overlay.querySelector('[data-close]').focus();}
function closeOverlay(){if(!activeOverlay)return;activeOverlay.hidden=true;activeOverlay=null;document.getElementById("main").inert=false;document.body.style.overflow="";if(returnFocus)returnFocus.focus();}
const pair=(a,b,c="")=>'<div><dt>'+a+'</dt><dd class="'+c+'">'+b+'</dd></div>';
function detail(p,trigger){
 document.getElementById("drawer").innerHTML='<div class="dialogtop"><span class="eyebrow">DEMO / SAMPLE DATA</span><button data-close aria-label="Close detail">Close ×</button></div><h2 class="dialogname" id="detail-name">'+p.code+'</h2><p class="company">'+p.name+'</p><div class="badges">'+side(p)+(p.status==="V-LOCK"?'<div>'+status(p)+'</div>':'')+'</div><div class="metrics '+tone(p)+'"><div><small>P/L · JPY</small><strong>'+signed(p.pnl)+'</strong></div><div><small>P/L %</small><strong>'+signed(p.pct,2)+'%</strong></div><div><small>Current R</small><strong>'+signed(p.r,2)+'R</strong></div></div><div class="block protection"><h3>CURRENT PROTECTION</h3><dl>'+pair("Current Stop","¥"+fmt(p.stop),"emphasis")+pair("Distance","¥"+fmt(p.distance)+" / "+p.distance_pct.toFixed(2)+"%")+pair("Trailing",p.trailing)+pair("Profit Lock",p.profit_lock,p.status==="V-LOCK"?"gold":"")+'</dl></div><div class="block"><h3>POSITION</h3><dl>'+pair("Execution",p.execution+" · SAMPLE")+pair("Entry","¥"+fmt(p.entry))+pair("Current","¥"+fmt(p.current))+pair("Quantity",fmt(p.quantity)+" shares")+'</dl><p class="note">Executionは架空例です。正式なLONGの執行方式を確定しません。</p></div><div class="block"><h3>TRADE</h3><dl>'+pair("Entry Time",p.entry_time)+pair("Holding Period",p.holding)+pair("Strategy",p.strategy)+'</dl></div><p class="note">NO ORDER EXECUTION · 架空のサンプルセッション</p>';
 openOverlay(detailOverlay,trigger);
}
function chart(p,trigger){
 const low=Math.min(...p.series,p.entry,p.stop),high=Math.max(...p.series,p.entry,p.stop),pad=(high-low)*.22;
 const min=low-pad,max=high+pad,y=v=>330-(v-min)/(max-min)*285;
 const points=p.series.map((v,i)=>(35+i*650/31).toFixed(2)+','+y(v).toFixed(2)).join(" ");
 const grid=Array.from({length:5},(_,i)=>{const v=min+(max-min)*i/4;return '<line x1="35" x2="685" y1="'+y(v)+'" y2="'+y(v)+'" stroke="#253245"/><text x="35" y="'+(y(v)-7)+'" fill="#8290a6" font-size="10">'+fmt(v)+'</text>';}).join("");
 const line=(value,label,color,dash)=>'<g data-level="'+label+'" data-value="'+value+'"><line x1="35" x2="685" y1="'+y(value)+'" y2="'+y(value)+'" stroke="'+color+'" stroke-width="'+(label==="CURRENT STOP"?2:1)+'" stroke-dasharray="'+dash+'"/><text x="702" y="'+(y(value)-5)+'" fill="'+color+'" font-size="10" font-weight="700">'+label+'</text><text x="702" y="'+(y(value)+13)+'" fill="'+color+'" font-size="14">'+fmt(value)+'</text></g>';
 const svg='<svg viewBox="0 0 840 380" role="img" aria-label="'+p.code+' sample price chart"><title>'+p.name+' — fictional price series</title>'+grid+'<polyline data-series="PRICE" points="'+points+'" fill="none" stroke="#dce7f8" stroke-width="2.5" stroke-linejoin="round"/>'+line(p.entry,"ENTRY","#929fb7","5 5")+line(p.stop,"CURRENT STOP","#80b7ff","7 4")+'<circle cx="685" cy="'+y(p.current)+'" r="4" fill="#dce7f8"/>'+(p.status==="V-LOCK"?'<text data-v-lock="true" x="666" y="'+(y(p.stop)-10)+'" fill="#efcc7c" font-size="23" font-weight="700">V</text>':'')+'<text x="35" y="362" fill="#a5afc0" font-size="10">SAMPLE SERIES / START</text><text x="606" y="362" fill="#a5afc0" font-size="10">SAMPLE / END</text></svg>';
 document.getElementById("chart-modal").innerHTML='<div class="dialogtop"><div><div class="eyebrow">DEMO / SAMPLE DATA · NO ORDER EXECUTION</div><h2 id="chart-name">'+p.code+' / '+p.name+'</h2></div><button data-close aria-label="Close chart">Close ×</button></div>'+side(p)+'<div class="chartlegend"><span class="price">PRICE · '+fmt(p.current)+'</span><span class="entry">ENTRY · '+fmt(p.entry)+'</span><span class="stop">CURRENT STOP · '+fmt(p.stop)+'</span></div>'+svg+'<div class="chartfoot"><span>架空の価格系列 · JPY · 時間軸はサンプル観測順</span><span class="gold">'+(p.status==="V-LOCK"?"V · PROFIT SECURED":"")+'</span></div>';
 openOverlay(chartOverlay,trigger);
}
document.addEventListener("click",e=>{const b=e.target.closest("button");if(b?.hasAttribute("data-close"))return closeOverlay();if(b?.dataset.action){const p=byCode[b.dataset.code];if(b.dataset.action==="detail")detail(p,b);else chart(p,b);}});
[detailOverlay,chartOverlay].forEach(o=>o.addEventListener("click",e=>{if(e.target===o)closeOverlay();}));
document.addEventListener("keydown",e=>{if(!activeOverlay)return;if(e.key==="Escape"){e.preventDefault();closeOverlay();}else if(e.key==="Tab"){const all=activeOverlay.querySelectorAll("button");if(all.length===1){e.preventDefault();all[0].focus();}}});
</script>
</body></html>
'''

class AuditHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.external = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for key in ("src", "href", "action", "srcset"):
            if key in a:
                self.external.append((tag, key, a[key]))
        assert tag not in ("iframe", "form", "object", "embed", "link")

def main():
    audit_data()
    html = TEMPLATE.replace("__DATA__", json.dumps(ROWS, ensure_ascii=False))
    parser = AuditHTML()
    parser.feed(html)
    assert not parser.external
    for forbidden in ("fetch(", "XMLHttpRequest", "WebSocket", "http://", "https://",
                      "Initial Stop", "TODAY", "LIVE", "onclick="):
        assert forbidden not in html, forbidden
    assert "connect-src 'none'" in html
    target = Path(__file__).resolve().with_name("quadrant_showcase.html")
    target.write_text(html, encoding="utf-8")
    assert target.read_text(encoding="utf-8") == html
    print("HTML / ISOLATION STATIC AUDIT: PASS")
    print(target)

if __name__ == "__main__":
    main()

