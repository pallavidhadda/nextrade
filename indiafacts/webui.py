"""Pure helpers for the Streamlit app: validation, number formatting and HTML cards in the Furrow look.
Every dynamic string is escaped. No keys, no user data kept. Education only; not financial, investment or trading advice."""
from __future__ import annotations

import html
import threading
import time

from indiafacts.runner import TICKER, subprocess_runner
from indiafacts.render import DISCLAIMER

RUNNER = subprocess_runner                       # tests replace this
SLOTS = threading.BoundedSemaphore(2)            # at most two analyses at once on a small free host
CACHE: dict[str, tuple[float, dict]] = {}
CACHE_SECONDS = 3600
FACTORS = {"value": "Value", "quality": "Quality", "growth": "Growth", "momentum": "Momentum", "risk": "Risk"}
LABELS = {"price": "Price", "market_cap": "Market value", "revenue": "Revenue, latest quarter", "net_income": "Net profit, latest quarter",
          "eps_diluted": "Earnings per share", "pe_ttm": "Price to earnings", "pb": "Price to book", "roe": "Return on equity",
          "debt_to_equity": "Debt to equity"}
e = html.escape


def valid_ticker(raw: str) -> str | None:
    t = (raw or "").strip().upper()
    return t if TICKER.match(t) and not t.startswith("-") else None


def format_value(value, unit: str) -> str:
    if value is None:
        return "n/a"
    if unit == "INR":
        a = abs(value)
        if a >= 1e12:
            return f"₹{value / 1e12:.2f} lakh cr"
        if a >= 1e7:
            return f"₹{round(value / 1e7):,} cr"
        return f"₹{value:,.2f}"
    if unit == "INR_per_share":
        return f"₹{value:,.2f}"
    if unit == "percent":
        return f"{value:.2f}%"
    return f"{value:.2f}"


def metric_label(m: str) -> str:
    return LABELS.get(m, m.replace("_", " ").capitalize())


def _card(title: str, note: str, body: str, notebook: bool = False) -> str:
    cls = "entry notebook" if notebook else "entry"
    return (f'<section class="{cls}"><header><h2>{e(title)}</h2><span class="note">{e(note)}</span></header>'
            f'<div class="body">{body}</div></section>')


def score_html(s: dict) -> str:
    sc = s.get("score")
    if not sc or sc.get("overall") is None:
        return _card("Score inside the comparison pool", "0 to 100", f"<p>No score for this run{': ' + e(sc['reason']) if sc and sc.get('reason') else ''}.</p>", True)
    rows = ""
    for k, f in sc["factors"].items():
        name = FACTORS.get(k, k.capitalize())
        if f["score"] is None:
            rows += f'<div class="factor"><span>{e(name)}</span><span class="na">Not scored: {e(f.get("reason") or "not enough data")}</span></div>'
        else:
            rows += (f'<div class="factor"><span>{e(name)}</span><div class="bar-track" role="img" aria-label="{e(name)} {f["score"]:.0f} of 100">'
                     f'<div class="bar-fill" style="width:{max(2, f["score"]):.0f}%"></div></div><span class="num">{f["score"]:.0f}</span></div>')
    body = (f'<p class="reading">{sc["overall"]:.1f}<small>of 100</small></p>'
            f'<p class="rank">Rank {sc["rank"]} of {sc["n"]} in {e(sc.get("pool") or "the pool")}. It orders companies inside this pool and is not absolute quality.</p>'
            f'<div class="factors">{rows}</div>')
    return _card("Score inside the comparison pool", "0 to 100", body, True)


def health_html(s: dict) -> str:
    rows = [r for r in (s.get("fundamentals") or []) if r["status"] in ("ok", "unverified")]
    if not rows:
        return _card("Business health", "annual statements", "<p>Annual statements were not available for this run, so year figures, cash flow and EV/EBITDA are missing.</p>")
    body = "".join(f'<tr><td>{e(r["label"])}<span class="ids">{e(r["meaning"])}</span></td><td class="num">{e(r["display"])}'
                   + (f' <span class="tag">{e(r["reading"])}</span>' if r["reading"] else "")
                   + ('<span class="ids">vendor proxy, unverified</span>' if r["status"] == "unverified" else "") + "</td></tr>" for r in rows)
    return _card("Business health", "annual statements",
                 f'<table><thead><tr><th>Measure</th><th class="num">Value</th></tr></thead><tbody>{body}</tbody></table>'
                 '<p class="helper">Words like low or healthy describe the number against fixed bands. They are not advice.</p>')


def ownership_html(s: dict) -> str:
    o = s.get("ownership") or {}
    if not o.get("rows"):
        return _card("Who owns it", "no data", f"<p>No ownership data this run. {e(o.get('how_to', ''))}</p>")
    body = "".join(f'<tr><td>{e(r["label"])}<span class="ids">{e(r["change"] or r["meaning"])}</span></td><td class="num">{e(r["display"])}'
                   + (f' <span class="tag">{e(r["reading"])}</span>' if r["reading"] else "") + "</td></tr>" for r in o["rows"])
    note = f"NSE filing, as on {o['as_on']}" if o["source"] == "official" else "vendor estimate"
    hint = "" if o["source"] == "official" else f'<p class="helper">{e(o["how_to"])}</p>'
    return _card("Who owns it", note, f'<table><thead><tr><th>Holder</th><th class="num">Share</th></tr></thead><tbody>{body}</tbody></table>{hint}')


def flows_html(s: dict) -> str:
    f = s.get("market_flows")
    if not f:
        return ""
    cash = f.get("cash")
    cash_html = ""
    if cash:
        cb = "".join(f'<tr><td>{e(r["category"])}<span class="ids">{r["streak"]} session(s) in a row of {e(r["streak_word"])}; {r["window_net"]:+,.0f} over {r["sessions"]} sessions</span></td>'
                     f'<td class="num">{r["last_net"]:+,.0f}</td></tr>' for r in cash["rows"])
        cash_html = f'<h3>Cash market, rupees crore (latest {e(cash["as_of"])})</h3><table><thead><tr><th>Group</th><th class="num">Latest net</th></tr></thead><tbody>{cb}</tbody></table>'
    body = "".join(f'<tr><td>{e(r["participant"])}<span class="ids">{r["long_share"]:.0%} long'
                   + (f'; {r["change"]:+,} since {e(f["since"])}' if r["change"] is not None else "") + f'</span></td>'
                   f'<td class="num">{abs(r["net"]):,} <span class="tag">{e(r["stance"])}</span></td></tr>' for r in f["rows"])
    fut = f'<table><thead><tr><th>Who</th><th class="num">Index futures</th></tr></thead><tbody>{body}</tbody></table>' if body else ""
    return _card("Market flows", f"as of {f['as_of']}", fut + cash_html + f'<p class="helper">{e(f["note"] or (cash or {}).get("note", ""))}</p>')


PROVIDER_KEYS = {"Gemini": ("gemini", "GOOGLE_API_KEY", "gemini-3.1-flash-lite"),
                 "Anthropic": ("anthropic", "ANTHROPIC_API_KEY", "claude-haiku-5-5"),
                 "OpenAI-compatible": ("openai", "OPENAI_API_KEY", "")}


def _result_dict(title: str, ex, error: str = "") -> dict:
    if ex is None:
        return {"title": title, "summary": "", "claims": [], "uncertainty": "", "error": error or "no valid answer"}
    return {"title": title, "summary": ex.summary, "claims": [{"type": c.type, "text": c.text, "ids": c.ids} for c in ex.claims],
            "uncertainty": ex.uncertainty, "error": ""}


def ai_run(llm_block: dict, provider_label: str, model: str, base_url: str, key: str, panel: bool, post=None) -> dict:
    """Run the person's own model over the stored digest. The key lives only in this call: it is placed in a private dict for the
    client and never logged, cached or returned. Every answer is checked against the digest before it is shown."""
    from indiafacts.agents import run_panel
    from indiafacts.digest import Digest
    from indiafacts.llm import make_client, validate_llm_output

    provider, env_name, default_model = PROVIDER_KEYS[provider_label]
    env = {env_name: key}
    if provider == "openai":
        env["INDIAFACTS_LLM_BASE_URL"] = base_url.strip()
    client = make_client(provider, (model or default_model).strip() or None, env=env, post=post)
    digest = Digest(text=llm_block["digest"], ids={i: "" for i in llm_block["ids"]}, items={}, by_key={}, est_tokens=0)
    if not panel:
        res = client.complete(llm_block["system"], llm_block["user"], llm_block.get("max_tokens", 700))
        ex, reasons = validate_llm_output(res.text, digest)
        return {"mode": "single", "results": [_result_dict("Plain-English explanation", ex, "; ".join(reasons[:2]))],
                "tokens": (res.input_tokens or 0) + (res.output_tokens or 0)}
    results = run_panel(client, digest)
    return {"mode": "panel", "results": [_result_dict(r.title, r.explanation, r.error) for r in results],
            "tokens": sum(r.input_tokens + r.output_tokens for r in results)}


def ai_html(res: dict | None) -> str:
    if not res:
        return ""
    cards = ""
    for r in res["results"]:
        if r["error"]:
            cards += _card(r["title"], "not shown", f"<p>{e(r['error'])}. Nothing from this answer was shown.</p>")
            continue
        claims = "".join(f'<li><span class="tag {e(c["type"])}">{e(c["type"].capitalize())}</span> {e(c["text"])} <span class="ids">{e(", ".join(c["ids"]))}</span></li>' for c in r["claims"])
        unc = f'<p class="helper">{e(r["uncertainty"])}</p>' if r["uncertainty"] else ""
        cards += _card(r["title"], "checked against the facts", f'<p>{e(r["summary"])}</p><ul class="claims">{claims}</ul>{unc}')
    foot = f'<p class="helper">About {res["tokens"]:,} tokens used. Every claim cites a fact id and was checked against the digest; answers that failed the checks were dropped. Education only, not advice.</p>'
    return cards + foot


def glance_html(s: dict) -> str:
    st = (s.get("debate") or {}).get("stance")
    sc = s.get("score") or {}
    chk = s.get("checklist") or []
    known = [c for c in chk if c["result"] != "unavailable"]
    passed = sum(1 for c in known if c["result"] == "pass")
    cell = lambda k, v, sub: f'<div><span class="glance-k">{e(k)}</span><strong class="glance-v">{e(v)}</strong><span class="glance-s">{e(sub)}</span></div>'
    row = (cell("Educational rating", st["label"] if st else "No rating", f'{st["confidence"]} confidence. Rule-based, not advice.' if st else "Not enough data.")
           + cell("Score in pool", f'{sc["overall"]:.0f}/100' if sc.get("overall") is not None else "n/a", f'rank {sc["rank"]} of {sc["n"]}' if sc.get("rank") else "not scored")
           + cell("Checks passed", f"{passed}/{len(known)}" if known else "n/a", f"{len(chk) - len(known)} unavailable" if len(chk) > len(known) else "all measurable")
           + cell("Gaps to know about", str(len(s.get("gaps") or [])), "see the Gaps tab"))
    why = ""
    if s.get("debate"):
        li = lambda ps: "".join(f"<li>{e(p['text'])}</li>" for p in ps[:3]) or "<li>Nothing stands out.</li>"
        why = (f'<div class="glance-why"><div><h3>Working in its favour</h3><ul>{li(s["debate"]["bull"])}</ul></div>'
               f'<div><h3>Worth being careful about</h3><ul>{li(s["debate"]["bear"])}</ul></div></div>')
    return f'<section class="glance"><div class="glance-row">{row}</div>{why}</section>'


def checklist_html(s: dict) -> str:
    items = s.get("checklist") or []
    if not items:
        return _card("Nine-point checklist", "needs a score run", "<p>The checklist runs together with the score.</p>")
    word = {"pass": "Pass", "fail": "Fail", "unavailable": "Unavailable"}
    rows = ""
    for c in items:
        detail = f"{c['display']}, needs {c['threshold']}" if c.get("display") else c.get("reason", "")
        rows += (f'<tr><td>{e(c["label"])}<span class="ids">{e(detail)}</span></td>'
                 f'<td><span class="tag {e(c["result"])}">{word.get(c["result"], "")}</span></td></tr>')
    passed = sum(1 for c in items if c["result"] == "pass")
    body = f'<table><thead><tr><th>Test</th><th>Result</th></tr></thead><tbody>{rows}</tbody></table><p class="helper">Project-defined tests. Missing data shows as unavailable, never as a fail.</p>'
    return _card("Nine-point checklist", f"{passed} passed", body)


def facts_html(s: dict) -> str:
    kf = s.get("key_facts") or []
    if not kf:
        return _card("Facts with their period and source", "latest available", "<p>No verified figures came back for this company.</p>")
    rows = "".join(f'<tr><td>{e(metric_label(f["metric"]))}</td><td class="num">{e(format_value(f["value"], f["unit"]))}</td>'
                   f'<td>{e(f["period"])}</td><td>{e(f["source"])}, basis {e(f["basis"])}</td></tr>' for f in kf)
    return _card("Facts with their period and source", "latest available",
                 f'<table><thead><tr><th>Measure</th><th class="num">Value</th><th>Period</th><th>Source</th></tr></thead><tbody>{rows}</tbody></table>')


def explanation_html(s: dict) -> str:
    ex = s.get("explanation")
    if not ex:
        return _card("In plain English", "", "<p>No explanation was produced for this run.</p>")
    tag = {"fact": "Fact", "inference": "Inference", "hypothesis": "Hypothesis"}
    claims = "".join(f'<li><span class="tag {e(c["type"])}">{tag.get(c["type"], "")}</span><span>{e(c["text"])}'
                     f'<span class="ids">{e(", ".join(c["ids"]))}</span></span></li>' for c in ex["claims"])
    unc = f'<p><strong>What is uncertain.</strong> {e(ex["uncertainty"])}</p>' if ex.get("uncertainty") else ""
    note = "template, no model used" if ex["source"] == "template" else f"written by {ex['source']}"
    return _card("In plain English", note, f'<p>{e(ex["summary"])}</p><ul class="claims">{claims}</ul>{unc}')


def valuation_html(s: dict) -> str:
    v = s.get("valuation")
    if not v:
        return ""
    if not v["items"]:
        return _card("What the price implies", "arithmetic, not a forecast", f'<p>Not available: {e(v.get("unavailable_reason") or "")}.</p>')
    if v["method"] == "reverse_dcf_earnings":
        grid: dict[str, dict[str, float | None]] = {}
        for it in v["items"]:
            parts = it["metric"].split("_")
            if it["metric"].startswith("implied_growth") and len(parts) == 4:
                grid.setdefault(parts[2][1:], {})[parts[3][1:]] = it["value"]
        years = sorted({y for d in grid.values() for y in d}, key=int)
        head = "".join(f'<th class="num">{e(y)} years</th>' for y in years)
        rows = "".join(f'<tr><td>{e(r)}%</td>' + "".join(
            f'<td class="num">{"n/a" if grid[r].get(y) is None else f"{grid[r][y]:.1f}% a year"}</td>' for y in years) + "</tr>"
            for r in sorted(grid, key=int))
        body = ('<p>Yearly earnings growth the current price would need to be explained, if earnings were fully distributable. '
                'It says what is priced in, not what will happen.</p>'
                f'<table><thead><tr><th>Discount rate</th>{head}</tr></thead><tbody>{rows}</tbody></table>')
    else:
        vals = " to ".join(f"{i['value']:.2f}" for i in v["items"] if i["metric"].startswith("justified_pb"))
        body = f"<p>Price-to-book that the stated return on equity and assumptions would support: <span class=\"num\">{e(vals)}</span>.</p>"
    return _card("What the price implies", "arithmetic, not a forecast", body + f'<p class="helper">{e(v["assumptions"])}</p>')


def debate_html(s: dict) -> str:
    d = s.get("debate")
    if not d:
        return ""
    def col(title, pts):
        items = "".join(f"<li>{e(p['text'])}<span class='ids'>{e(p['evidence'])}</span></li>" for p in pts) or "<li>None found.</li>"
        return f"<div class='side'><h3>{e(title)}</h3><ul class='plain'>{items}</ul></div>"
    st = d["stance"]
    body = (f"<div class='debate'>{col('Bull case', d['bull'])}{col('Bear case', d['bear'])}</div>"
            f"<p class='stance'><span class='tag stance-tag'>{e(st['label'])}</span> Confidence {e(st['confidence'])}. {e(st['reason'])}.</p>"
            "<p class='helper'>Educational rating from a transparent rule applied to the evidence on this page. It ignores your own situation, "
            "is not a prediction, and is not a recommendation.</p>")
    return _card("Bull case versus bear case", "educational", body)


def levels_html(s: dict) -> str:
    lv, rp = s.get("levels"), s.get("risk_panel")
    if not lv or lv.get("last_close") is None:
        return ""
    inr = lambda v: f"₹{v:,.2f}"
    rows = f"<tr><td>Last close</td><td class='num'>{inr(lv['last_close'])}</td></tr>"
    rows += "".join(f"<tr><td>Support: {e(x['name'])}</td><td class='num'>{inr(x['price'])}</td></tr>" for x in lv["support"])
    rows += "".join(f"<tr><td>Resistance: {e(x['name'])}</td><td class='num'>{inr(x['price'])}</td></tr>" for x in lv["resistance"])
    if lv["applies"]:
        rows += f"<tr><td>Reference stop ({lv['risk_pct']:.1f}% below)</td><td class='num'>{inr(lv['stop'])}</td></tr>"
        rows += "".join(f"<tr><td>Reward-to-risk {t['r']:g}R</td><td class='num'>{inr(t['price'])}</td></tr>" for t in lv["targets"])
    body = f"<table><thead><tr><th>Level</th><th class='num'>Price</th></tr></thead><tbody>{rows}</tbody></table>"
    if not lv["applies"]:
        body += f"<p class='helper'>Stop and reward-to-risk levels are not shown: {e(lv['reason'])}.</p>"
    if rp:
        lens = ""
        for l in rp["lenses"]:
            fit = "Not applied" if l["fits"] is None else "Within limits" if l["fits"] else "Breaches"
            why = e(l["reason"]) if l["fits"] is None else e("; ".join(l["breaches"])) or "None"
            size = "n/a" if l["max_position_pct"] is None else f"{l['max_position_pct']:.1f}%"
            mark = " (your profile)" if l["name"] == rp["profile_lens"] else ""
            lens += f"<tr><td>{e(l['name'].capitalize())}{mark}</td><td>{fit}</td><td>{why}</td><td class='num'>{size}</td></tr>"
        body += ("<h3 style='margin-top:1rem'>Risk lenses</h3><table><thead><tr><th>Lens</th><th>Fit</th><th>Why</th><th class='num'>Position ceiling</th></tr></thead>"
                 f"<tbody>{lens}</tbody></table>")
        body += "".join(f"<p class='helper'>{e(n)}</p>" for n in rp["notes"])
    body += "<p class='helper'>Arithmetic on past closes. Not predictions, not price targets, not personal advice. Lens limits are proposals.</p>"
    return _card("Reference levels and risk lenses", "arithmetic", body)


def news_html(s: dict) -> str:
    items = s.get("news") or []
    if not items:
        return ""
    rows = "".join(f"<tr><td>{e(n.get('published') or 'undated')}</td><td>{e(n['publisher'])}</td><td>{e(n['title'])}</td>"
                   f"<td><span class='tag {e(n['sentiment_hint'] if n['sentiment_hint'] != 'neutral' else 'hypothesis')}'>{e(n['sentiment_hint'].capitalize())}</span></td></tr>"
                   for n in items)
    return _card("Recent headlines", "unverified, keyword hint only",
                 f"<table><thead><tr><th>Date</th><th>Source</th><th>Headline</th><th>Hint</th></tr></thead><tbody>{rows}</tbody></table>"
                 "<p class='helper'>Third-party headlines are not verified and are not facts about the company. The hint is a keyword guess, not analysis.</p>")


def gaps_html(s: dict) -> str:
    gaps = s.get("gaps") or []
    if not gaps:
        body = "<p>No missing periods or unavailable measures were found.</p>"
    else:
        rows = "".join(f'<tr><td>{e(metric_label(g["metric"]))}</td><td>{e(g["period"])}</td><td>{e(g["reason"])}</td></tr>' for g in gaps)
        body = f'<table><thead><tr><th>Measure</th><th>Period</th><th>Why</th></tr></thead><tbody>{rows}</tbody></table>'
    if s.get("notices"):
        body += '<ul class="claims">' + "".join(f"<li style='grid-template-columns:1fr'>{e(n)}</li>" for n in s["notices"]) + "</ul>"
    return _card("What could not be checked", f"{len(gaps)} items", body)


def run_analysis(opts: dict, progress) -> dict:
    """Cached for an hour per option set; at most two run at once."""
    key = repr(sorted(opts.items()))
    hit = CACHE.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    if not SLOTS.acquire(timeout=1):
        raise RuntimeError("The service is busy with other analyses; try again in a minute.")
    try:
        res = RUNNER(opts, progress)
    finally:
        SLOTS.release()
    now = time.time()
    for k in [k for k, (t, _) in CACHE.items() if now - t >= CACHE_SECONDS]:
        CACHE.pop(k, None)
    if len(CACHE) >= 200:                                                     # bounded memory on a small host
        CACHE.pop(min(CACHE, key=lambda k: CACHE[k][0]), None)
    CACHE[key] = (now, res)
    return res


CSS = """@import url('https://fonts.googleapis.com/css2?family=Red+Hat+Display:wght@600&family=Red+Hat+Text:wght@400;500&family=Red+Hat+Mono:wght@400;500&display=swap');
:root { --paper: #f6f1e7; --paper2: #fffdf8; --paper3: #ece5d4; --ink: #1b1815; --ink2: #3a342d; --muted: #6b6258; --rule: #e0d8c6;
  --accent: #f4793c; --accent-soft: #fbd9c4; --green: #2f6b45; --green-soft: #dcebdc; --grid: #e6dfcd; }
html, body, .stApp, .stApp p, .stApp label, .stApp input, .stApp button, .stApp textarea, .stApp li, .stApp td, .stApp th { font-family: 'Red Hat Text', system-ui, sans-serif; }
[data-testid="stIconMaterial"], .material-icons, span[class*="material"] { font-family: 'Material Symbols Rounded', 'Material Icons' !important; }
.stApp { background: var(--paper); color: var(--ink); }
#MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; height: 0; }
.block-container { max-width: 1180px; padding-top: 1rem; }
.bar { border-bottom: 1px solid var(--ink); padding: .6rem 0; margin-bottom: 1.5rem; display: flex; justify-content: space-between; align-items: center; }
.brand { font-family: 'Red Hat Display', sans-serif; font-weight: 600; font-size: 1.44rem; letter-spacing: -0.03em; }
.bar a { color: var(--ink2); font-size: .875rem; font-weight: 500; }
h1, .head h1 { font-family: 'Red Hat Display', sans-serif; font-weight: 600; letter-spacing: -0.035em; line-height: 1; }
.hero h1 { font-size: clamp(2.1rem, 4.5vw, 3.2rem); max-width: 14ch; margin: 0; }
.hero p.lead { color: var(--muted); max-width: 52ch; margin-top: 1rem; }
.entry { border-radius: 14px; background: var(--paper2); box-shadow: 0 0 0 1px var(--ink), 0 24px 44px -20px rgba(27,24,21,.35); overflow: hidden; margin-bottom: 1.25rem; }
.entry > header { background: var(--ink); color: var(--paper2); padding: .5rem 1rem; display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; }
.entry > header h2 { font-family: 'Red Hat Display', sans-serif; font-size: 1rem; font-weight: 600; margin: 0; padding: 0; color: inherit; }
.entry > header .note { font-size: .875rem; opacity: .78; }
.entry .body { padding: 1rem; }
.entry .body p { color: var(--ink); margin: 0 0 .5rem; }
.notebook { background: linear-gradient(var(--grid) 1px, transparent 1px) 0 0 / 8px 8px, linear-gradient(90deg, var(--grid) 1px, transparent 1px) 0 0 / 8px 8px, var(--paper2); }
.entry .body p.reading { font-family: 'Red Hat Display', sans-serif; font-weight: 600; font-size: clamp(3.4rem, 8vw, 5.4rem) !important; margin: 0 0 .5rem !important; letter-spacing: -0.04em; line-height: 1; font-variant-numeric: tabular-nums; }
.entry .body p.reading small { font-size: 1.2rem; color: var(--muted); letter-spacing: 0; font-weight: 500; margin-left: .25rem; }
.rank { color: var(--ink2); }
.factors { border-top: 1px solid var(--ink); margin-top: 1rem; }
.factor { display: grid; grid-template-columns: 7rem minmax(0,1fr) 3.5rem; gap: .75rem; align-items: center; padding: .5rem 0; border-bottom: 1px solid var(--rule); }
.bar-track { height: 10px; background: var(--paper3); border-radius: 2px; overflow: hidden; } .bar-fill { height: 100%; background: var(--accent); border-radius: 2px; }
.num { font-family: 'Red Hat Mono', monospace; font-variant-numeric: tabular-nums; font-size: .875rem; text-align: right; white-space: nowrap; }
.na { color: var(--muted); font-size: .875rem; grid-column: 2 / 4; }
.entry table { width: 100%; border-collapse: collapse; border: 0 !important; }
.entry th, .entry td { border-left: 0 !important; border-right: 0 !important; border-top: 0 !important; background: transparent !important; }
.entry th { text-align: left; font-weight: 500; font-size: .875rem; color: var(--muted); padding: .5rem .5rem .5rem 0; border-bottom: 1px solid var(--ink); white-space: nowrap; }
.entry td { padding: .5rem .5rem .5rem 0; border-bottom: 1px solid var(--rule); vertical-align: top; }
.entry td.num, .entry th.num { padding-right: 1rem; padding-left: .5rem; }
.tag { display: inline-block; min-width: 5.5rem; text-align: center; padding: 0 .5rem; border-radius: 4px; border: 1px solid var(--rule); font-size: .875rem; font-weight: 500; }
.tag.pass, .tag.fact { background: var(--green-soft); color: var(--green); border-color: var(--green); }
.tag.fail, .tag.inference { background: var(--accent-soft); color: var(--ink); border-color: var(--accent); }
.tag.unavailable, .tag.hypothesis { color: var(--muted); background: var(--paper3); }
.claims { list-style: none; margin: .75rem 0 0; padding: 0; border-top: 1px solid var(--ink); }
.claims li { display: grid; grid-template-columns: 6.5rem minmax(0,1fr); gap: .75rem; padding: .75rem 0; border-bottom: 1px solid var(--rule); align-items: start; }
.ids { font-family: 'Red Hat Mono', monospace; font-size: .75rem; color: var(--muted); display: block; margin-top: 2px; overflow-wrap: anywhere; }
.helper { color: var(--muted); font-size: .875rem; }
.head { border-bottom: 2px solid var(--ink); padding-bottom: 1rem; margin-bottom: 1rem; } .head h1 { font-size: 2.07rem; margin: 0; } .head .sub { color: var(--muted); margin: .25rem 0 0; }
.foot { border-top: 1px solid var(--ink); margin-top: 2rem; padding-top: 1rem; color: var(--muted); font-size: .875rem; max-width: 70ch; }
div[data-testid="stButton"] button[kind="primary"], div[data-testid="stFormSubmitButton"] button { background: var(--accent); color: var(--ink); border: 1px solid #c75d25; border-radius: 6px; font-weight: 500; min-height: 48px; box-shadow: inset 0 1px 0 rgba(255,255,255,.3); }
div[data-testid="stButton"] button { border-radius: 6px; min-height: 44px; font-weight: 500; }
div[data-testid="stTextInput"] input { font-family: 'Red Hat Mono', monospace; background: var(--paper2); border-radius: 6px; min-height: 52px; }
button[data-baseweb="tab"] { font-weight: 500; min-height: 44px; }
.debate { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
.debate h3 { font-family: 'Red Hat Display', sans-serif; font-weight: 600; font-size: 1rem; margin: 0 0 .25rem; border-bottom: 1px solid var(--ink); padding-bottom: .25rem; }
.plain { list-style: none; padding: 0; margin: 0; } .plain li { padding: .5rem 0; border-bottom: 1px solid var(--rule); }
.stance { margin-top: 1rem; } .stance-tag { background: var(--accent-soft); border-color: var(--accent); color: var(--ink); min-width: 9rem; }
@media (max-width: 640px) { .debate { grid-template-columns: 1fr; } }
@media (max-width: 640px) { .claims li { grid-template-columns: 1fr; } .factor { grid-template-columns: 5.5rem minmax(0,1fr) 3rem; } }

.glance{margin:1rem 0;border:1px solid var(--color-ink,#1d1b16);border-radius:12px;background:var(--color-sheet,#fff);padding:1rem}
.glance-row{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1rem}
.glance-k{display:block;font-size:.72rem;font-weight:500;color:#6b675e;text-transform:uppercase;letter-spacing:.04em}
.glance-v{display:block;font-size:1.25rem;margin-top:.15rem}.glance-s{display:block;font-size:.85rem;color:#6b675e;margin-top:.15rem}
.glance-why{display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;margin-top:1rem;padding-top:1rem;border-top:1px solid #d9d4c7}
.glance-why h3{font-size:.85rem;margin:0 0 .3rem}.glance-why ul{margin:0;padding-left:1.1em;font-size:.88rem}
@media(max-width:720px){.glance-row{grid-template-columns:1fr 1fr}.glance-why{grid-template-columns:1fr}}

"""
