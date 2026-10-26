"""Self-contained HTML report: inline SVG charts built only from Facts and score results.

Follows the dataviz rules: one axis per chart, thin marks, solid hairline grid, selective labels, legend for 2+ series,
tooltips that never gate (every chart has a table twin), text in ink tokens, status colours only with icon + label.
Untrusted strings (company names, reasons) are HTML-escaped; tooltips are filled with textContent.
Research and education only; not financial, investment or trading advice."""
from __future__ import annotations

import html as _html
import json
import math
import re
from datetime import date, datetime
from decimal import Decimal

from indiafacts.analysis import prefer_sources
from indiafacts.models import Fact, FactSet, PeriodType, Status
from indiafacts.render import DISCLAIMER
from indiafacts.units import format_inr

W = 760          # full-width chart viewBox width
HALF = 520       # half-width cards use a narrower canvas so text is not scaled down


def esc(x) -> str:
    return _html.escape("" if x is None else str(x), quote=True)


def _json(obj) -> str:
    return json.dumps(obj, separators=(",", ":")).replace("<", "\\u003c").replace("&", "\\u0026")


def nice_ticks(lo: float, hi: float, n: int = 4) -> list[float]:
    if hi == lo:
        hi = lo + 1
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    start = math.floor(lo / step) * step
    ticks, v = [], start
    while v <= hi + step * 0.5 and len(ticks) < 12:
        ticks.append(round(v, 10))
        v += step
    return ticks


def _fmt_pct(v: float, signed: bool = True) -> str:
    return f"{v:+.1%}" if signed else f"{v:.1%}"


CSS = """
:root{color-scheme:light;--surface:#fcfcfb;--page:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;
--axis:#c3c2b7;--s1:#2a78d6;--s2:#eb6834;--good:#006300;--bad:#d03b3b;--hair:rgba(11,11,11,.10)}
@media (prefers-color-scheme: dark){:root:where(:not([data-theme="light"])){color-scheme:dark;--surface:#1a1a19;--page:#0d0d0d;
--ink:#f0efec;--ink2:#c3c2b7;--grid:#2c2c2a;--axis:#383835;--s1:#3987e5;--s2:#d95926;--good:#0ca30c;--hair:rgba(255,255,255,.10)}}
:root[data-theme="dark"]{color-scheme:dark;--surface:#1a1a19;--page:#0d0d0d;--ink:#f0efec;--ink2:#c3c2b7;--grid:#2c2c2a;
--axis:#383835;--s1:#3987e5;--s2:#d95926;--good:#0ca30c;--hair:rgba(255,255,255,.10)}
*{box-sizing:border-box}html,body{margin:0}
body{background:var(--page);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1100px;margin:0 auto;padding:16px}
h1{font-size:22px;margin:0 0 4px;font-weight:600}h2{font-size:16px;margin:0 0 2px;font-weight:600}
.sub{color:var(--ink2);font-size:13px;margin:0 0 8px}.muted{color:var(--muted)}
.banner{background:var(--surface);border:1px solid var(--hair);border-radius:10px;padding:10px 14px;font-size:13px;color:var(--ink2);margin:10px 0}
.top{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap}
button{font:inherit;font-size:13px;background:var(--surface);color:var(--ink);border:1px solid var(--hair);border-radius:8px;padding:6px 10px;cursor:pointer}
button:focus-visible,[tabindex]:focus-visible,summary:focus-visible{outline:2px solid var(--s1);outline-offset:2px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px;margin:12px 0}
.tile{background:var(--surface);border:1px solid var(--hair);border-radius:10px;padding:12px 14px}
.tile .label{font-size:13px;color:var(--ink2)}.tile .value{font-size:28px;font-weight:600;line-height:1.2}
.tile .note{font-size:12px;color:var(--muted)}
.grid{display:grid;grid-template-columns:1fr;gap:12px}
@media(min-width:900px){.grid.two{grid-template-columns:1fr 1fr}}
.card{background:var(--surface);border:1px solid var(--hair);border-radius:10px;padding:14px;min-width:0}
svg{width:100%;height:auto;display:block;overflow:visible}
svg text{font:11px system-ui,sans-serif;fill:var(--muted)}svg text.ink{fill:var(--ink2)}svg text.val{fill:var(--ink);font-weight:600}
.gridline{stroke:var(--grid);stroke-width:1}.axisline{stroke:var(--axis);stroke-width:1}
.line1{fill:none;stroke:var(--s1);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.line2{fill:none;stroke:var(--s2);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.area{fill:var(--s1);opacity:.10}.bar{fill:var(--s1)}.bar:hover,.bar:focus{opacity:.8}
.track{fill:var(--grid)}.enddot{stroke:var(--surface);stroke-width:2}
.dot.peer{fill:var(--muted);stroke:var(--surface);stroke-width:2}.dot.target{fill:var(--s1);stroke:var(--surface);stroke-width:2}
.median{stroke:var(--ink2);stroke-width:2}.cross{stroke:var(--axis);stroke-width:1;display:none}
.hit{fill:transparent}
.legend{display:flex;gap:16px;font-size:13px;color:var(--ink2);margin:4px 0 6px;flex-wrap:wrap}
.key{display:inline-block;width:16px;height:0;border-top:2px solid;vertical-align:middle;margin-right:6px}
.k1{border-color:var(--s1)}.k2{border-color:var(--s2)}
ul.checks{list-style:none;margin:6px 0 0;padding:0}
.check{display:grid;grid-template-columns:22px 1fr auto;gap:8px;padding:6px 0;border-top:1px solid var(--grid);font-size:14px}
.check:first-child{border-top:0}.check .icon{font-weight:700}.check.pass .icon{color:var(--good)}.check.fail .icon{color:var(--bad)}
.check.na .icon{color:var(--muted)}.check .val{color:var(--ink2);font-size:13px;text-align:right}
.check .state{font-size:12px;color:var(--muted);margin-left:6px}
details{margin-top:8px}summary{cursor:pointer;color:var(--ink2);font-size:13px}
table{border-collapse:collapse;width:100%;font-size:13px;margin-top:6px}
.tablewrap{overflow-x:auto;max-width:100%}.grid>*{min-width:0}.banner,.sub,.tile{overflow-wrap:anywhere}
th,td{text-align:left;padding:4px 8px;border-top:1px solid var(--grid);vertical-align:top}th{color:var(--ink2);font-weight:600}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
#tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--surface);font-size:12px;padding:6px 8px;border-radius:6px;
display:none;max-width:280px;z-index:9;line-height:1.35}
#tip b{font-size:13px}
.badge{display:inline-block;font-size:11px;border:1px solid var(--hair);border-radius:6px;padding:0 6px;margin-right:6px;color:var(--ink2)}
.chip{display:inline-block;font-size:11px;color:var(--ink2);border:1px solid var(--hair);border-radius:6px;padding:0 5px;margin-left:4px;cursor:default}
ul.claims{padding-left:0;list-style:none;margin:6px 0}ul.claims li{padding:5px 0;border-top:1px solid var(--grid)}ul.claims li:first-child{border-top:0}
.empty{color:var(--ink2);font-size:14px;padding:18px 0}
footer{margin:18px 0 8px;font-size:12px;color:var(--muted)}
@media print{#theme-toggle{display:none}}
"""

JS = """
(function(){
var tip=document.getElementById('tip');
function show(t,x,y){tip.textContent='';String(t).split('\\n').forEach(function(l,i){var e=document.createElement(i?'span':'b');
e.textContent=l;tip.appendChild(e);tip.appendChild(document.createElement('br'));});
tip.style.display='block';var r=tip.getBoundingClientRect();tip.style.left=Math.min(x+12,innerWidth-r.width-8)+'px';
tip.style.top=Math.max(8,y-r.height-10)+'px';}
function hide(){tip.style.display='none';}
document.querySelectorAll('[data-tip]').forEach(function(el){
el.addEventListener('pointermove',function(e){show(el.getAttribute('data-tip'),e.clientX,e.clientY)});
el.addEventListener('pointerleave',hide);
el.addEventListener('focus',function(){var r=el.getBoundingClientRect();show(el.getAttribute('data-tip'),r.left+r.width/2,r.top)});
el.addEventListener('blur',hide);});
document.querySelectorAll('svg[data-lines]').forEach(function(svg){
var d=JSON.parse(document.getElementById(svg.getAttribute('data-lines')).textContent);
var cross=svg.querySelector('.cross'),hit=svg.querySelector('.hit');
var x0=+svg.getAttribute('data-x0'),x1=+svg.getAttribute('data-x1');
function at(e){var p=svg.createSVGPoint();p.x=e.clientX;p.y=e.clientY;var q=p.matrixTransform(svg.getScreenCTM().inverse());
var f=Math.max(0,Math.min(1,(q.x-x0)/(x1-x0)));var t=d.t0+f*(d.t1-d.t0),best=0,bd=1e18;
d.ts.forEach(function(v,i){var dd=Math.abs(v-t);if(dd<bd){bd=dd;best=i}});
var cx=x0+(d.ts[best]-d.t0)/(d.t1-d.t0)*(x1-x0);cross.setAttribute('x1',cx);cross.setAttribute('x2',cx);cross.style.display='block';
var lines=[d.dates[best]];d.names.forEach(function(n,i){if(d.series[i].length)lines.push(n+': '+d.series[i][best].toFixed(1))});
show(lines.join('\\n'),e.clientX,e.clientY);}
hit.addEventListener('pointermove',at);hit.addEventListener('pointerleave',function(){hide();cross.style.display='none'});});
var tb=document.getElementById('theme-toggle'),modes=['auto','light','dark'],i=0;
tb.addEventListener('click',function(){i=(i+1)%3;var m=modes[i];
if(m==='auto')delete document.documentElement.dataset.theme;else document.documentElement.dataset.theme=m;tb.textContent='Theme: '+m;});
})();
"""


class _Ctx:
    def __init__(self):
        self.used: dict[str, Fact] = {}

    def use(self, f: Fact) -> str:
        self.used[f.fact_id] = f
        return f.fact_id


def _table(headers: list[str], rows: list[list[str]], caption: str = "", num: tuple[int, ...] = ()) -> str:
    h = "".join(f'<th class="{"num" if i in num else ""}">{esc(x)}</th>' for i, x in enumerate(headers))
    body = "".join("<tr>" + "".join(f'<td class="{"num" if i in num else ""}">{esc(c)}</td>' for i, c in enumerate(r)) + "</tr>"
                   for r in rows)
    cap = f"<caption class=\"muted\">{esc(caption)}</caption>" if caption else ""
    return f'<div class="tablewrap"><table>{cap}<thead><tr>{h}</tr></thead><tbody>{body}</tbody></table></div>'


def _card(ident: str, title: str, sub: str, inner: str, twin: str = "", cls: str = "") -> str:
    twin_html = f"<details><summary>Table view</summary>{twin}</details>" if twin else ""
    return (f'<section class="card {cls}" id="{ident}"><h2>{esc(title)}</h2><p class="sub">{esc(sub)}</p>'
            f"{inner}{twin_html}</section>")


# ---------------------------------------------------------------- line charts
def _price_card(charts: dict, facts: list[Fact], name: str) -> str:
    c = (charts or {}).get("price") or {}
    if not c or len(c.get("dates", [])) < 2:
        return _card("chart-price", "Price against the Nifty 50", "Rebased to 100 at the start of the window.",
                     '<p class="empty">Price history unavailable for this run (not loaded, or too short).</p>')
    L, R, T, B, H = 48, 60, 12, 26, 300
    dates = [date.fromisoformat(d) for d in c["dates"]]
    t = [d.toordinal() for d in dates]
    series = [c["stock"], c["bench"]]
    vals = [v for s in series for v in s]
    lo, hi = min(vals), max(vals)
    ticks = nice_ticks(lo, hi)
    lo, hi = min(lo, ticks[0]), max(hi, ticks[-1])
    X = lambda v: L + (v - t[0]) / (t[-1] - t[0]) * (W - L - R)
    Y = lambda v: T + (hi - v) / (hi - lo) * (H - T - B)
    g = "".join(f'<line class="gridline" x1="{L}" x2="{W - R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}"/>'
                f'<text x="{L - 6}" y="{Y(v) + 4:.1f}" text-anchor="end">{v:g}</text>' for v in ticks)
    years = sorted({d.year for d in dates})
    xt = ""
    for y in years:
        first = next((i for i, d in enumerate(dates) if d.year == y), None)
        if first is not None and (first > 0 or len(years) == 1):
            xt += f'<text x="{X(t[first]):.1f}" y="{H - 8}" text-anchor="middle">{y}</text>'
    lines = ""
    for s, cls in zip(series, ("line1", "line2")):
        if s:
            pts = " ".join(f"{X(a):.1f},{Y(b):.1f}" for a, b in zip(t, s))
            lines += f'<polyline class="{cls}" points="{pts}"/>'
    ends = ""
    ylab = []
    for s, col in zip(series, ("var(--s1)", "var(--s2)")):
        if s:
            ends += f'<circle class="enddot" cx="{X(t[-1]):.1f}" cy="{Y(s[-1]):.1f}" r="4" style="fill:{col}"/>'
            ylab.append((Y(s[-1]), f"{s[-1]:.1f}"))
    labels = ""
    if len(ylab) == 2 and abs(ylab[0][0] - ylab[1][0]) < 14:
        ylab = []                       # converging ends: legend carries identity, no stacked labels
    for y, txt in ylab:
        labels += f'<text class="val" x="{W - R + 8}" y="{y + 4:.1f}">{txt}</text>'
    payload = {"t0": t[0], "t1": t[-1], "ts": t, "dates": c["dates"], "names": [name, "Nifty 50"], "series": series}
    svg = (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Line chart: {esc(name)} and the Nifty 50 price index, both '
           f'rebased to 100 at {esc(c["start"])}" data-lines="d-price" data-x0="{L}" data-x1="{W - R}">'
           f'{g}<line class="axisline" x1="{L}" x2="{W - R}" y1="{H - T - B + T}" y2="{H - T - B + T}"/>{xt}{lines}{ends}{labels}'
           f'<line class="cross" x1="0" x2="0" y1="{T}" y2="{H - B}"/>'
           f'<rect class="hit" x="{L}" y="{T}" width="{W - L - R}" height="{H - T - B}"/></svg>'
           f'<script type="application/json" id="d-price">{_json(payload)}</script>')
    legend = (f'<div class="legend"><span><i class="key k1"></i>{esc(name)}</span>'
              f'<span><i class="key k2"></i>Nifty 50 (price index)</span></div>')
    pf = {f.metric: f for f in facts if (f.source_field or "").startswith("series:")}
    rows = []
    for n in (1, 3, 5):
        cells = []
        for m in (f"return_{n}y", f"benchmark_return_{n}y", f"relative_return_{n}y", f"max_drawdown_{n}y"):
            f = pf.get(m)
            cells.append(_fmt_pct(float(f.value)) if f is not None and f.value is not None else "unavailable")
        rows.append([f"{n} year", *cells])
    twin = _table(["Window", name, "Nifty 50", "Relative", "Worst fall"], rows,
                  f"Price returns (dividends excluded); series {c['series_id']}, basis {c['basis']}", num=(1, 2, 3, 4))
    return _card("chart-price", "Price against the Nifty 50",
                 f"Both rebased to 100 at {c['start']}. Price returns only: dividends are excluded and past prices are "
                 "split-adjusted to today's share count.", legend + svg, twin)


def _drawdown_card(charts: dict) -> str:
    c = (charts or {}).get("price") or {}
    if not c or len(c.get("dates", [])) < 2:
        return _card("chart-drawdown", "Fall from the previous high", "Stock only.",
                     '<p class="empty">Price history unavailable for this run.</p>')
    L, R, T, B, H = 48, 60, 8, 26, 180
    dates = [date.fromisoformat(d) for d in c["dates"]]
    t = [d.toordinal() for d in dates]
    dd = c["drawdown"]
    lo = min(dd)
    lo = min(lo, -0.05)
    X = lambda v: L + (v - t[0]) / (t[-1] - t[0]) * (W - L - R)
    Y = lambda v: T + (0 - v) / (0 - lo) * (H - T - B)
    ticks = [0] + [round(x, 2) for x in nice_ticks(lo, 0, 3) if lo <= x < 0]
    g = "".join(f'<line class="gridline" x1="{L}" x2="{W - R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}"/>'
                f'<text x="{L - 6}" y="{Y(v) + 4:.1f}" text-anchor="end">{v:.0%}</text>' for v in ticks)
    pts = [f"{X(a):.1f},{Y(b):.1f}" for a, b in zip(t, dd)]
    area = f'<path class="area" d="M{X(t[0]):.1f},{Y(0):.1f} L{" L".join(pts)} L{X(t[-1]):.1f},{Y(0):.1f} Z"/>'
    line = f'<polyline class="line1" points="{" ".join(pts)}"/>'
    wi = dd.index(min(dd))
    lab = (f'<circle class="enddot" cx="{X(t[wi]):.1f}" cy="{Y(dd[wi]):.1f}" r="4" style="fill:var(--s1)"/>'
           f'<text class="val" x="{X(t[wi]):.1f}" y="{Y(dd[wi]) + 16:.1f}" text-anchor="middle">{dd[wi]:.1%} ({esc(c["dates"][wi])})</text>')
    svg = (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Area chart: fall from the previous high, worst {dd[wi]:.1%}">'
           f"{g}{area}{line}{lab}</svg>")
    twin = _table(["Worst fall in window", "Date", "Latest"], [[f"{dd[wi]:.1%}", c["dates"][wi], f"{dd[-1]:.1%}"]],
                  "Stock drawdown over the chart window")
    return _card("chart-drawdown", "Fall from the previous high",
                 f"How far the stock sat below its own earlier peak (worst fall {dd[wi]:.1%}).", svg, twin)


# ------------------------------------------------------------------ bar charts
def _round_top_path(x: float, y0: float, y1: float, w: float, r: float = 4) -> str:
    """Vertical bar from baseline y0 to data end y1; data end rounded, baseline square."""
    top, bot = min(y0, y1), max(y0, y1)
    r = min(r, (bot - top) / 2, w / 2)
    if y1 <= y0:    # up: round the top
        return (f"M{x:.1f},{y0:.1f} V{top + r:.1f} Q{x:.1f},{top:.1f} {x + r:.1f},{top:.1f} H{x + w - r:.1f} "
                f"Q{x + w:.1f},{top:.1f} {x + w:.1f},{top + r:.1f} V{y0:.1f} Z")
    return (f"M{x:.1f},{y0:.1f} V{bot - r:.1f} Q{x:.1f},{bot:.1f} {x + r:.1f},{bot:.1f} H{x + w - r:.1f} "
            f"Q{x + w:.1f},{bot:.1f} {x + w:.1f},{bot - r:.1f} V{y0:.1f} Z")


def _quarter_card(ident: str, title: str, metric: str, facts: list[Fact], ctx: _Ctx) -> str:
    W = HALF
    qs = prefer_sources([f for f in facts if f.metric == metric and f.period_type == PeriodType.Q
                         and f.source != "computed"])
    if not qs:
        return _card(ident, title, "Quarterly, as reported.", '<p class="empty">No quarterly data for this metric.</p>')
    qs.sort(key=lambda f: f.period_end)
    L, R, T, B, H = 64, 16, 22, 40, 230
    have = [float(f.value) for f in qs if f.value is not None]
    lo, hi = min(have + [0.0]), max(have + [0.0])
    ticks = nice_ticks(lo, hi, 3)
    lo, hi = min(lo, ticks[0]), max(hi, ticks[-1])
    Y = lambda v: T + (hi - v) / (hi - lo) * (H - T - B)
    slot = (W - L - R) / len(qs)
    bw = min(24.0, slot * 0.5)
    g = "".join(f'<line class="gridline" x1="{L}" x2="{W - R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}"/>'
                f'<text x="{L - 6}" y="{Y(v) + 4:.1f}" text-anchor="end">{esc(format_inr(Decimal(str(v))) if v else "0")}</text>'
                for v in ticks)
    marks, rows = "", []
    for i, f in enumerate(qs):
        cx = L + slot * (i + 0.5)
        lab = f.fiscal_label or f.period_end.isoformat()
        marks += f'<text x="{cx:.1f}" y="{H - 22}" text-anchor="middle">{esc(lab)}</text>'
        if f.value is None:
            marks += (f'<text x="{cx:.1f}" y="{Y(0) - 6:.1f}" text-anchor="middle">no data</text>'
                      f'<line class="axisline" x1="{cx - 8:.1f}" x2="{cx + 8:.1f}" y1="{Y(0):.1f}" y2="{Y(0):.1f}"/>')
            rows.append([lab, "no data", f.reason or f.status.value])
            continue
        v = float(f.value)
        tip = f"{lab}: {format_inr(f.value)}\nsource: {f.source}" + ("\nunverified" if f.status == Status.unverified else "")
        fid = ctx.use(f)
        d = _round_top_path(cx - bw / 2, Y(0), Y(v), bw)
        marks += (f'<path class="bar" d="{d}" tabindex="0" data-tip="{esc(tip)}" data-fact="{fid}" '
                  f'aria-label="{esc(lab)} {esc(format_inr(f.value))}"/>')
        if i == len(qs) - 1:
            marks += f'<text class="val" x="{cx:.1f}" y="{(Y(v) - 6) if v >= 0 else (Y(v) + 14):.1f}" text-anchor="middle">{esc(format_inr(f.value))}</text>'
        rows.append([lab, format_inr(f.value), f.source + (" (unverified)" if f.status == Status.unverified else "")])
    base = f'<line class="axisline" x1="{L}" x2="{W - R}" y1="{Y(0):.1f}" y2="{Y(0):.1f}"/>'
    svg = (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Bar chart: {esc(title)} by quarter, '
           f'{sum(1 for f in qs if f.value is not None)} of {len(qs)} quarters have data">{g}{base}{marks}</svg>')
    twin = _table(["Quarter", "Value", "Source"], rows, f"{title} (INR)", num=(1,))
    return _card(ident, title, "Quarterly, in rupees. A gap means the source returned no figure for that quarter.", svg, twin)


def _hbars(rows: list[tuple[str, float | None, str, str, str | None]], lo: float, hi: float, fmt, zero_line: float | None = None) -> str:
    """rows: (label, value|None, tip, note_if_none, fact_id). Horizontal bars, <= 24px thick."""
    W = HALF
    L, R, rowh = 112, 84, 34
    H = rowh * len(rows) + 8
    X = lambda v: L + (v - lo) / (hi - lo) * (W - L - R)
    out = ""
    if zero_line is not None:
        out += (f'<line class="axisline" x1="{X(zero_line):.1f}" x2="{X(zero_line):.1f}" y1="0" y2="{H - 8}"/>'
                f'<text x="{X(zero_line):.1f}" y="{H + 4}" text-anchor="middle">pool middle</text>')
    for i, (lab, v, tip, note, fid) in enumerate(rows):
        y = i * rowh + 4
        out += f'<text class="ink" x="{L - 8}" y="{y + 19:.1f}" text-anchor="end">{esc(lab)}</text>'
        if v is None:
            out += f'<text x="{L}" y="{y + 19:.1f}">{esc(note)}</text>'
            continue
        x0 = X(max(lo, min(0, v)) if lo < 0 else lo)
        x1 = X(v)
        w = max(2.0, abs(x1 - x0))
        left = min(x0, x1)
        rx = min(4.0, w / 2)
        d = (f"M{left:.1f},{y + 6} H{left + w - rx:.1f} Q{left + w:.1f},{y + 6} {left + w:.1f},{y + 6 + rx:.1f} "
             f"V{y + 22 - rx:.1f} Q{left + w:.1f},{y + 22} {left + w - rx:.1f},{y + 22} H{left:.1f} Z")
        attrs = f' data-fact="{fid}"' if fid else ""
        out += (f'<path class="bar" d="{d}" tabindex="0" data-tip="{esc(tip)}"{attrs} aria-label="{esc(lab)} {esc(fmt(v))}"/>'
                f'<text class="val" x="{left + w + 6:.1f}" y="{y + 19:.1f}">{esc(fmt(v))}</text>')
    return f'<svg viewBox="0 0 {W} {H + 12}" role="img" aria-label="Horizontal bar chart">{out}</svg>'


def _score_card(sc: dict | None) -> str:
    if not sc or sc.get("result") is None:
        return _card("chart-scores", "Score inside the comparison pool", "Percentile ranks, 0 to 100.",
                     '<p class="empty">No score for this run (run with --score, or the company is not in the pool).</p>')
    r = sc["result"]
    rows = []
    for fac, fs_ in sorted(r.factors.items()):
        if fs_.score is None:
            rows.append((fac, None, "", f"n/a: {fs_.reason}", None))
        else:
            rows.append((fac, fs_.score, f"{fac}: {fs_.score:.1f}/100\ncoverage {fs_.coverage:.0%}", "", None))
    if r.status == "ok":
        rows.append(("overall", r.overall, f"overall: {r.overall:.1f}/100\nrank {r.rank} of {sc['n']}", "", None))
    else:
        rows.append(("overall", None, "", f"abstain: {r.reason}", None))
    inner = _hbars(rows, 0, 100, lambda v: f"{v:.0f}", zero_line=50)
    tr = [[a, "n/a" if v is None else f"{v:.1f}", (n if v is None else "")] for a, v, _, n, _ in rows]
    twin = _table(["Factor", "Score", "Note"], tr, f"config {r.config_hash}; {sc['n']} companies in the pool", num=(1,))
    sub = (f"Percentile rank among {sc['n']} companies in the pool ({sc.get('pool_label') or sc.get('pool')}). "
           "It orders companies inside this pool; it is not absolute quality.")
    return _card("chart-scores", "Score inside the comparison pool", sub, inner, twin)


def _checklist_card(sc: dict | None) -> str:
    if not sc:
        return _card("checklist", "Nine-point checklist", "", '<p class="empty">Run with --score to see the checklist.</p>')
    items = ""
    for c in sc["checklist"]:
        cls, icon, word = {"pass": ("pass", "✓", "pass"), "fail": ("fail", "✗", "fail"),
                           "unavailable": ("na", "–", "unavailable")}[c.result]
        val = f"{c.display}, needs {c.threshold}" if c.value is not None else c.reason
        items += (f'<li class="check {cls}"><span class="icon" aria-hidden="true">{icon}</span>'
                  f'<span>{esc(c.label)}<span class="state">{word}</span></span><span class="val">{esc(val)}</span></li>')
    twin = _table(["Test", "Result", "Value"], [[c.label, c.result, c.display or c.reason] for c in sc["checklist"]])
    return _card("checklist", f"Nine-point checklist: {sc['checklist_summary']}",
                 "Project-defined pass/fail tests (not the Piotroski score). Missing data shows as unavailable, never as a fail.",
                 f'<ul class="checks">{items}</ul>', twin)


def _peer_card(sc: dict | None, metric: str, target: str) -> str:
    ident = f"chart-peers-{metric}"
    title = {"pe_ttm": "P/E against peers", "pb": "Price-to-book against peers"}[metric]
    cmp_ = next((c for c in (sc or {}).get("peer_comparisons", []) if c.metric == metric), None)
    if cmp_ is None or cmp_.status != "ok":
        why = (cmp_.reason if cmp_ else ((sc or {}).get("peers").unavailable_reason if (sc or {}).get("peers") else "no peer comparison"))
        return _card(ident, title, "Peers are chosen by rule from the pool.", f'<p class="empty">Unavailable: {esc(why)}</p>')
    W = HALF
    L, R, H = 30, 30, 120
    vals = [v for _, v in cmp_.peer_values] + [cmp_.peer_median] + ([cmp_.target_value] if cmp_.target_value is not None else [])
    lo, hi = min(vals), max(vals)
    ticks = nice_ticks(max(0, lo - (hi - lo) * 0.1), hi + (hi - lo) * 0.1)
    lo, hi = min(lo, ticks[0]), max(hi, ticks[-1])
    X = lambda v: L + (v - lo) / (hi - lo) * (W - L - R)
    g = "".join(f'<line class="gridline" x1="{X(v):.1f}" x2="{X(v):.1f}" y1="14" y2="{H - 28}"/>'
                f'<text x="{X(v):.1f}" y="{H - 10}" text-anchor="middle">{v:g}</text>' for v in ticks)
    dots = ""
    for i, (tk, v) in enumerate(cmp_.peer_values):
        cy = 40 + (i % 3) * 20
        dots += (f'<g tabindex="0" data-tip="{esc(f"{tk}: {v:.3g}")}"><circle class="hit" cx="{X(v):.1f}" cy="{cy}" r="12"/>'
                 f'<circle class="dot peer" cx="{X(v):.1f}" cy="{cy}" r="5"/></g>')
    med = (f'<line class="median" x1="{X(cmp_.peer_median):.1f}" x2="{X(cmp_.peer_median):.1f}" y1="14" y2="{H - 28}"/>'
           f'<text class="ink" x="{X(cmp_.peer_median):.1f}" y="10" text-anchor="middle">median {cmp_.peer_median:.3g}</text>')
    tgt = ""
    if cmp_.target_value is not None:
        tgt = (f'<g tabindex="0" data-tip="{esc(f"{target}: {cmp_.target_value:.3g}")}"><circle class="hit" cx="{X(cmp_.target_value):.1f}" cy="{H - 52}" r="14"/>'
               f'<circle class="dot target" cx="{X(cmp_.target_value):.1f}" cy="{H - 52}" r="7"/></g>'
               f'<text class="val" x="{X(cmp_.target_value):.1f}" y="{H - 34}" text-anchor="middle">{esc(target)} {cmp_.target_value:.3g}</text>')
    svg = (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Dot plot: {esc(title)}; median {cmp_.peer_median:.3g}">'
           f"{g}{med}{dots}{tgt}</svg>")
    prem = f"{cmp_.premium:+.1%} against the peer median" if cmp_.premium is not None else ""
    rows = [[tk, f"{v:.3g}"] for tk, v in cmp_.peer_values] + [[f"median ({cmp_.n} peers)", f"{cmp_.peer_median:.3g}"],
                                                                [target, f"{cmp_.target_value:.3g}" if cmp_.target_value is not None else "n/a"]]
    return _card(ident, title, f"Grey dots are peers; the blue dot is {target}. {prem} Peers with a P/E above 75 are left out of the median.",
                 svg, _table(["Company", "Value"], rows, num=(1,)))


def _segment_cards(facts: list[Fact], ctx: _Ctx) -> str:
    out = ""
    for kind, title in (("segment_revenue", "Segment revenue"), ("segment_result", "Segment result before interest and tax")):
        fs_ = [f for f in facts if f.metric.startswith(kind + "_") and f.value is not None]
        if not fs_:
            continue
        rows = []
        for f in sorted(fs_, key=lambda f: -float(f.value)):
            label = re.sub(r"\s*\[.*$", "", f.source_field or f.metric)
            rows.append((label, float(f.value) / 1e7, f"{label}: {format_inr(f.value)}\n{f.fiscal_label} {f.basis.value}", "", ctx.use(f)))
        lo = min(0.0, min(v for _, v, *_ in rows))
        hi = max(v for _, v, *_ in rows)
        svg = _hbars(rows, lo, hi * 1.05, lambda v: f"₹{v:,.0f} cr", zero_line=0 if lo < 0 else None)
        twin = _table(["Segment", "₹ crore"], [[r[0], f"{r[1]:,.0f}"] for r in rows], num=(1,))
        out += _card(f"chart-seg-{'revenue' if kind.endswith('revenue') else 'result'}", title,
                     f"{fs_[0].fiscal_label}, {fs_[0].basis.value}; from the official filing.", svg, twin)
    return out


# ------------------------------------------------------------------- the page
def _tile(label: str, value: str, note: str) -> str:
    return f'<div class="tile"><div class="label">{esc(label)}</div><div class="value">{esc(value)}</div><div class="note">{esc(note)}</div></div>'


def _explanation_card(ex, digest) -> str:
    if ex is None:
        return ""
    chip = lambda i: (f'<span class="chip" tabindex="0" data-tip="{esc(digest.items[i].text)}">{esc(i)}</span>' if i in digest.items else
                      f'<span class="chip">{esc(i)}</span>')
    claims = "".join(f'<li><span class="badge {esc(c.type)}">{esc(c.type)}</span>{esc(c.text)}{"".join(chip(i) for i in c.ids)}</li>' for c in ex.claims)
    trig = "".join(f'<li>{esc(t.text)}{"".join(chip(i) for i in t.ids)}</li>' for t in ex.triggers)
    notes = "".join(f'<p class="sub">Note: {esc(n)}</p>' for n in ex.notes)
    u = ex.usage
    use = ("no LLM call (deterministic template)" if not u else ("cached response: 0 new tokens" if u.get("cached") else f"LLM call: in {u['in']}, out {u['out']} tokens"))
    used = sorted({i for c in ex.claims for i in c.ids} | {i for t in ex.triggers for i in t.ids}, key=lambda x: int(x[1:]))
    twin = _table(["Id", "Evidence"], [[i, digest.items[i].text] for i in used if i in digest.items])
    body = (f'<p>{esc(ex.summary)}</p><ul class="claims">{claims}</ul>'
            + (f'<h2>What would change the picture</h2><ul class="claims">{trig}</ul>' if trig else "")
            + f'<div class="banner"><b>Uncertainty.</b> {esc(ex.uncertainty)}</div>{notes}'
            + f'<p class="sub">Digest about {digest.est_tokens} estimated tokens; {esc(use)}.</p>')
    return _card("explanation", "In plain words", f"Generated by {ex.source}. Every claim cites evidence ids; hover an id to see the line. Research only, not a recommendation.",
                 body, twin)


def build_html(fs: FactSet, profile=None, profile_is_default: bool = False, view: str = "pro", scorecard: dict | None = None,
               as_of: date | None = None, now: datetime | None = None, explanation=None, digest=None) -> str:
    e = fs.entity
    now = now or datetime.now()
    ctx = _Ctx()
    facts = fs.facts
    by = {f.metric: f for f in facts if f.value is not None}
    price_facts = [f for f in facts if (f.source_field or "").startswith("series:")]
    r = (scorecard or {}).get("result")

    tiles = ""
    if r is not None and r.status == "ok":
        tiles += _tile("Overall score in the pool", f"{r.overall:.0f}/100", f"rank {r.rank} of {scorecard['n']}")
    if scorecard:
        tiles += _tile("Nine-point checklist", scorecard["checklist_summary"].split(" passed")[0] + " passed", "pass/fail tests")
    r1, rel = by.get("return_1y"), by.get("relative_return_1y")
    if r1 is not None:
        tiles += _tile("Price, last year", _fmt_pct(float(r1.value)),
                       f"{_fmt_pct(float(rel.value))} against the Nifty 50" if rel is not None else "Nifty 50 comparison unavailable")
    pe = next((c for c in (scorecard or {}).get("peer_comparisons", []) if c.metric == "pe_ttm" and c.status == "ok"), None)
    if by.get("pe_ttm") is not None:
        tiles += _tile("P/E (trailing)", f"{float(by['pe_ttm'].value):.1f}",
                       f"peer median {pe.peer_median:.1f}" if pe else "no peer median available")

    charts = _price_card(fs.charts, price_facts, e.ticker) + _drawdown_card(fs.charts)
    q = _quarter_card("chart-q-net_income", "Net profit by quarter", "net_income", facts, ctx) + \
        _quarter_card("chart-q-revenue", "Revenue by quarter", "revenue", facts, ctx)
    sc_block = _score_card(scorecard) + _checklist_card(scorecard)
    peers = _peer_card(scorecard, "pe_ttm", e.ticker) + _peer_card(scorecard, "pb", e.ticker) if scorecard else ""
    peer_note = ""
    if scorecard and scorecard.get("peers") and scorecard["peers"].picks:
        g = scorecard["peers"]
        peer_note = ('<p class="sub">Peers picked by rule: ' + esc("; ".join(
            f"{p.ticker} ({'same industry' if p.tier == 1 else 'same sector'}, {p.size_ratio:.2f}x size)" for p in g.picks))
            + (". " + esc("; ".join(g.notes)) if g.notes else "") + "</p>")
    seg = _segment_cards(facts, ctx)

    bad = [f for f in facts if f.status in (Status.gap, Status.unavailable, Status.conflict, Status.unverified)]
    dq_rows = [[f.metric, f.fiscal_label or f.period_end.isoformat(), f.status.value, f.reason] for f in bad[:60]]
    dq = _card("data-quality", f"Data quality: {len(bad)} item(s) need attention",
               "Gaps, unavailable values, conflicts and unverified figures are listed instead of hidden.",
               _table(["Metric", "Period", "Status", "Reason"], dq_rows) if dq_rows else '<p class="empty">None.</p>')
    src_rows = [[fid, f.metric, f.fiscal_label or f.period_end.isoformat(), format_inr(f.value) if f.unit == "INR" else str(f.value),
                 f"{f.source}:{f.source_field or ''}", str(f.retrieved_at.date())] for fid, f in ctx.used.items()]
    sources = (f'<section class="card" id="sources"><h2>Sources for plotted figures</h2>'
               f'<p class="sub">Every bar carries a fact id (data-fact). This table maps each id to its source.</p>'
               f'{_table(["Fact id", "Metric", "Period", "Value", "Source", "Retrieved"], src_rows, num=(3,))}</section>')

    prof = ""
    if profile is not None:
        prof = (f'<div class="banner">Profile: horizon {esc(profile.horizon)}, goal {esc(profile.goal)}, effective risk '
                f'{esc(profile.effective_risk)}, view {esc(view)}, profile {esc(profile.profile_hash)}'
                + (" (default profile, not set by you)" if profile_is_default else "") + "</div>")
    notices = "".join(f"<li>{esc(n)}</li>" for n in fs.notices)
    notices = f'<div class="banner"><ul style="margin:0;padding-left:18px">{notices}</ul></div>' if notices else ""
    when = (as_of or fs.retrieved_at.date()).isoformat()
    last_bar = (fs.charts.get("price") or {}).get("dates", [None])[-1] if fs.charts else None
    meta = " · ".join(x for x in [esc(e.name) if e.name else "", f"ISIN {esc(e.isin.value)}" if e.isin.value else "",
                                  esc(e.sector) if e.sector else "",
                                  "basis " + esc(", ".join(sorted({f.basis.value for f in facts}))) if facts else ""] if x)
    title = f"{e.ticker} research summary"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title><link rel="icon" href="data:,"><style>{CSS}</style></head><body><main>
<div class="top"><div><h1>{esc(title)}</h1><p class="sub">{meta}</p>
<p class="sub">Data as of {esc(when)}{' · latest price bar ' + esc(last_bar) if last_bar else ''} · generated {esc(now.strftime('%Y-%m-%d %H:%M'))}</p></div>
<button id="theme-toggle" type="button">Theme: auto</button></div>
<div class="banner"><b>{esc(DISCLAIMER)}</b></div>
{prof}{notices}
<div class="tiles">{tiles}</div>
{_explanation_card(explanation, digest)}
<div class="grid">{charts}</div>
<div class="grid two">{q}</div>
<div class="grid two">{sc_block}</div>
{peer_note}<div class="grid two">{peers}</div>
<div class="grid two">{seg}</div>
<div class="grid">{dq}{sources}</div>
<footer>{esc(DISCLAIMER)} Price charts use Yahoo Finance data (unofficial) and, where enabled, TejHQ open data; results pages are
NSE filings you supplied. No chart implies a forecast.</footer></main>
<div id="tip" role="status"></div><script>{JS}</script></body></html>"""
