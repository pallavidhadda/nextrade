"""NexTrade, Streamlit edition. Research and education only; not financial, investment or trading advice.
Runs the analysis in-process on the server. It never asks for or stores API keys; for your own model use the Claude connector."""
import streamlit as st
import streamlit.components.v1 as components

from indiafacts import webui
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


def result_view(res: dict) -> None:
    s = res["summary"]
    sub = ", ".join(x for x in [s["ticker"] if s.get("name") else None, s.get("industry") or s.get("sector"), s.get("isin")] if x)
    p = s["profile"]
    st.markdown(f'<div class="head"><h1>{webui.e(s.get("name") or s["ticker"])}</h1><p class="sub">{webui.e(sub)}. Profile: '
                f'{webui.e(p["horizon"])}, {webui.e(p["risk"])} risk, {webui.e(p["experience"])}.</p></div>', unsafe_allow_html=True)
    if st.button("Analyse another"):
        ss.pop("result", None)
        st.rerun()
    t1, t2, t3 = st.tabs(["Summary", "Full report", f"Gaps ({len(s['gaps'])})"])
    with t1:
        a, b = st.columns(2)
        a.markdown(webui.score_html(s) + webui.debate_html(s) + webui.valuation_html(s) + webui.checklist_html(s), unsafe_allow_html=True)
        b.markdown(webui.explanation_html(s) + webui.news_html(s) + webui.facts_html(s), unsafe_allow_html=True)
    with t2:
        components.html(res["html"], height=800, scrolling=True)
    with t3:
        st.markdown(webui.gaps_html(s), unsafe_allow_html=True)


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
        with st.form("analyse"):
            ticker = st.text_input("Ticker", value=ss.get("ticker", ""), placeholder="RELIANCE.NS", max_chars=24,
                                   help="Add .NS for NSE or .BO for BSE. Without a suffix, NSE is assumed.")
            go = st.form_submit_button("Analyse", type="primary")
        cols = st.columns(len(EXAMPLES))
        for c, x in zip(cols, EXAMPLES):
            if c.button(x, key=f"ex_{x}"):
                ss["ticker"] = x
                st.rerun()
        profile = {k: ss.get(f"p_{k}") for k in GROUPS if ss.get(f"p_{k}")}
        if go:
            t = webui.valid_ticker(ticker)
            if t is None:
                st.error("Enter a ticker such as RELIANCE or TCS.NS (letters, digits, & or -, optional .NS or .BO).")
            else:
                ss["ticker"] = t
                start(t, profile)
        st.markdown('<p class="helper">Nothing about you is stored on our servers. No API keys are requested here; for your own model, use the Claude connector.</p>', unsafe_allow_html=True)
    with right:
        st.markdown("""<section class="entry notebook"><header><h2>What a result contains</h2><span class="note">read before you run</span></header><div class="body">
<ul class="claims"><li><span class="tag fact">Fact</span><span>Every figure carries its period, unit and source.</span></li>
<li><span class="tag unavailable">Gap</span><span>Missing quarters are stated, never filled in.</span></li>
<li><span class="tag inference">Score</span><span>A percentile inside a comparison pool, and nine plain checks.</span></li>
<li><span class="tag hypothesis">Implied</span><span>What the price implies, as arithmetic under stated assumptions.</span></li></ul></div></section>""", unsafe_allow_html=True)

st.markdown(f'<div class="foot" id="disclaimer">{webui.e(DISCLAIMER)}</div>', unsafe_allow_html=True)
