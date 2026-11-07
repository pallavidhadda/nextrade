"""NexTrade, Streamlit edition. Research and education only; not financial, investment or trading advice.
Runs the analysis in-process on the server. It never asks for or stores API keys; for your own model use the Claude connector."""
import json
import sys
from pathlib import Path

# Always run the checked-out source, never a copy installed earlier. On Streamlit Cloud the package is built once and a later
# "Updated app" pulls new files without rebuilding, which left a new page calling functions the old installed copy lacked.
_ROOT = str(Path(__file__).resolve().parent)
if _ROOT not in sys.path[:1]:
    sys.path.insert(0, _ROOT)
for _name in [m for m in sys.modules if m == "indiafacts" or m.startswith("indiafacts.")]:
    _f = getattr(sys.modules[_name], "__file__", "") or ""
    if _f and not _f.startswith(_ROOT):
        del sys.modules[_name]

import streamlit as st
import streamlit.components.v1 as components

from indiafacts import companies, webui
from indiafacts.render import DISCLAIMER

st.set_page_config(page_title="NexTrade: research assistant for Indian stocks", page_icon="📈", layout="wide")
st.markdown(f"<style>{webui.CSS}</style>", unsafe_allow_html=True)
st.markdown('<div class="bar"><span class="brand">NexTrade</span><a href="#disclaimer">Education only, not advice</a></div>', unsafe_allow_html=True)

EXAMPLES = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ITC.NS"]
GROUPS = {
    "horizon": ("How long you would hold", ["<1y", "1-3y", "3-5y", "5y+"]),
    "risk_tolerance": ("Comfort with price swings", ["low", "medium", "high"]),
    "risk_capacity": ("Ability to absorb a loss", ["low", "medium", "high"]),
    "experience": ("Your experience", ["beginner", "expert"]),
}
ss = st.session_state


def start(ticker: str, profile: dict) -> None:
    box = st.status(f"Reading {ticker}", expanded=True)
    box.write("Fetching facts, checking gaps and comparing with a pool of companies. A first run can take a few minutes.")
    try:
        res = webui.run_analysis({"ticker": ticker, **profile}, lambda p: box.update(label=f"Reading {ticker}, step {p.split()[0]}"))
    except Exception as exc:                                              # never show a traceback or a path
        box.update(label="That did not work", state="error")
        st.error(str(exc) if isinstance(exc, (ValueError, TimeoutError, RuntimeError)) else f"The analysis failed ({type(exc).__name__}).")
        return
    box.update(label=f"Finished {ticker}", state="complete", expanded=False)
    ss["result"] = res
    st.rerun()


def _pick(ticker: str) -> None:
    """Button callback: put the chosen ticker in the box and run it on the next pass."""
    ss["q"] = ticker
    ss["run_now"] = True


def _ai_submit() -> None:
    """Button callback: take the typed key out of the widget at once, so it is never kept in the page state after this run."""
    ss["_ai_pending"] = {"provider": ss.get("ai_provider"), "model": ss.get("ai_model", ""), "base": ss.get("ai_base", ""),
                         "key": ss.get("ai_key", ""),
                         "mode": "panel" if str(ss.get("ai_mode", "")).startswith("Analyst") else "debate" if str(ss.get("ai_mode", "")).startswith("Bull") else "single"}
    ss["ai_key"] = ""


def ai_panel(s: dict) -> None:
    """Optional: the person's own model explains the digest, alone or as a panel of analysts. The key is used for one call only."""
    llm = s.get("llm")
    if not llm:
        st.info("This result has no digest to send to a model.")
        return
    st.markdown("#### Use your own AI model")
    st.caption("A model only narrates the facts already collected (about 2,000 tokens in). Its answer is checked against those facts; any claim with an "
               "unknown id, an invented number or advice wording is dropped. Your key is used for this one request, is not stored or logged, and the "
               "field is cleared right after you press Run. This is a shared server, so use a key with a spending limit, or run the app on your own machine.")
    c1, c2 = st.columns(2)
    c1.selectbox("Provider", list(webui.PROVIDER_KEYS), key="ai_provider")
    c2.text_input("Model (blank for the default)", key="ai_model", placeholder="gemini-3.1-flash-lite")
    st.text_input("Address, for OpenAI-compatible only", key="ai_base", placeholder="http://localhost:11434/v1")
    st.text_input("API key (paste it here)", type="password", key="ai_key", autocomplete="off", placeholder="Paste your key")
    st.radio("What to run", ["One plain-English explanation (1 call, about 2.5k tokens)",
                             "Bull versus bear debate: a bull advocate, a bear advocate who answers it, then a referee (3 calls, about 8k tokens)",
                             "Analyst panel: fundamentals, price, ownership, news, risk, then a manager (6 calls, about 15k tokens)"], key="ai_mode")
    st.button("Run", type="primary", key="ai_run", on_click=_ai_submit)
    job = ss.pop("_ai_pending", None)
    if job:
        if not job["key"] and job["provider"] != "OpenAI-compatible":
            st.error("The key box was empty. Paste your API key, then press Run.")
        else:
            try:
                with st.spinner("Asking your model..."):
                    ss["ai"] = {s["ticker"]: webui.ai_run(llm, job["provider"], job["model"], job["base"], job["key"], mode=job["mode"])}
            except Exception as exc:                                  # never echo the key or a path
                st.error(str(exc) if isinstance(exc, ValueError) else f"The model call failed ({type(exc).__name__}). Check the key, model name and address.")
            finally:
                job["key"] = ""
    shown = (ss.get("ai") or {}).get(s["ticker"])
    if shown:
        st.markdown(webui.ai_html(shown), unsafe_allow_html=True)


def result_view(res: dict) -> None:
    s = res["summary"]
    sub = ", ".join(x for x in [s["ticker"] if s.get("name") else None, s.get("industry") or s.get("sector"), s.get("isin")] if x)
    p = s["profile"]
    st.markdown(f'<div class="head"><h1>{webui.e(s.get("name") or s["ticker"])}</h1><p class="sub">{webui.e(sub)}. Profile: '
                f'{webui.e(p["horizon"])}, {webui.e(p["risk"])} risk, {webui.e(p["experience"])}.</p></div>', unsafe_allow_html=True)
    c1, c2, c3, _ = st.columns([2, 2, 2, 5])
    stamp = str(s.get("retrieved_at", ""))[:10] or "report"
    base = f"{s['ticker'].split('.')[0]}_{stamp}"
    c1.download_button("Download report (HTML)", res["html"], file_name=f"nextrade_{base}.html", mime="text/html", type="primary",
                       help="One self-contained file with the charts and every source. Open it in any browser; print it to save as PDF.")
    c2.download_button("Download data (JSON)", json.dumps(s, default=str, indent=1), file_name=f"nextrade_{base}.json", mime="application/json",
                       help="The same facts, scores and gaps as structured data.")
    if c3.button("Analyse another"):
        ss.pop("result", None)
        st.rerun()
    t1, t2, t3, t4 = st.tabs(["Summary", "Full report", f"Gaps ({len(s['gaps'])})", "AI analysts"])
    with t1:
        st.markdown(webui.glance_html(s), unsafe_allow_html=True)
        a, b = st.columns(2)
        a.markdown(webui.score_html(s) + webui.debate_html(s) + webui.scenario_html(s) + webui.health_html(s) + webui.ownership_html(s) + webui.levels_html(s) + webui.valuation_html(s) + webui.checklist_html(s), unsafe_allow_html=True)
        b.markdown(webui.explanation_html(s) + webui.news_html(s) + webui.flows_html(s) + webui.facts_html(s), unsafe_allow_html=True)
    with t2:
        try:
            components.html(res["html"], height=800, scrolling=True)
        except (AttributeError, TypeError):                      # components.html is being removed from Streamlit
            st.iframe(res["html"], height=800)
    with t3:
        st.markdown(webui.gaps_html(s), unsafe_allow_html=True)
    with t4:
        ai_panel(s)


if "result" in ss:
    result_view(ss["result"])
else:
    left, right = st.columns([5, 4])
    with left:
        st.markdown('<div class="hero"><h1>Read an Indian stock from its facts</h1><p class="lead">NexTrade collects the numbers behind an NSE or BSE '
                    'company, shows the period and source of each, says what is missing, and compares it with peers. It never says buy or sell.</p></div>',
                    unsafe_allow_html=True)
        with st.expander("Your profile, optional"):
            st.caption("Sets which factors weigh more. Skip it and a labelled default is used. Kept only for this browser session.")
            for key, (label, options) in GROUPS.items():
                st.pills(label, options, key=f"p_{key}")
        q = st.text_input("Company name or ticker", key="q", placeholder="Infosys or INFY.NS", max_chars=40,
                          help="Type a company name, even with a typo, or a ticker. Add .BO for BSE; NSE is the default. Press Enter to see matches.")
        chosen, sugg = companies.resolve(q)
        if q.strip() and chosen is None and sugg:
            st.caption(f'No exact match for "{q.strip()}". Did you mean:')
            for i, m in enumerate(sugg[:5]):
                st.button(f"{m.name}  ·  {m.ticker}", key=f"sg_{i}", on_click=_pick, args=(m.ticker,))
        elif q.strip() and chosen and not q.strip().upper().endswith((".NS", ".BO")):
            names = companies.search(chosen.split(".")[0], 1)
            st.caption(f"Will analyse {names[0].name} ({chosen})" if names else f"Will analyse {chosen}")
        go = st.button("Analyse", type="primary")
        st.caption("Quick picks")
        cols = st.columns(len(EXAMPLES))
        for c, x in zip(cols, EXAMPLES):
            c.button(x, key=f"ex_{x}", on_click=_pick, args=(x,))
        profile = {k: ss.get(f"p_{k}") for k in GROUPS if ss.get(f"p_{k}")}
        if ss.pop("run_now", False):
            go = True
        if go:
            if chosen is None:
                if sugg:
                    st.error(f'"{q.strip()}" is not a listed name or ticker. Pick one of the matches above.')
                else:
                    st.error("Enter a company name such as Infosys, or a ticker such as RELIANCE or TCS.NS.")
            else:
                ss["ticker"] = chosen
                start(chosen, profile)
        st.markdown('<p class="helper">Nothing about you is stored on our servers. No API keys are requested here; for your own model, use the Claude connector.</p>', unsafe_allow_html=True)
    with right:
        st.markdown("""<section class="entry notebook"><header><h2>What a result contains</h2><span class="note">read before you run</span></header><div class="body">
<ul class="claims"><li><span class="tag fact">Fact</span><span>Every figure carries its period, unit and source.</span></li>
<li><span class="tag unavailable">Gap</span><span>Missing quarters are stated, never filled in.</span></li>
<li><span class="tag inference">Score</span><span>A percentile inside a comparison pool, and nine plain checks.</span></li>
<li><span class="tag hypothesis">Implied</span><span>What the price implies, as arithmetic under stated assumptions.</span></li></ul></div></section>""", unsafe_allow_html=True)

st.markdown(f'<div class="foot" id="disclaimer">{webui.e(DISCLAIMER)}</div>', unsafe_allow_html=True)
