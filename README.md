# NexTrade: a trustworthy AI research assistant for Indian stocks

**A product case study.** I took an open-source multi-agent stock tool (TradingAgents), found out where it fails for Indian retail investors, and built a different product: one that shows its sources, says what it does not know, costs about 4% as much to run, and never says buy or sell.

| | |
|---|---|
| **Role** | Product manager and builder (discovery, strategy, prioritisation, specs, build with AI assistance, measurement) |
| **Status** | Live and working, early. No external users yet and no outcome data yet (first settlement due about 8 Dec 2026). Both stated plainly below. |
| **Live** | [Streamlit app](https://nextrade.streamlit.app) · API and Claude connector on Render · Next.js web app · Claude Code plugin |
| **Stack** | Python (analysis engine, tested offline), Next.js, Streamlit, MCP connector, GitHub Actions |

> Research and education only. Not financial, investment or trading advice. Free data (Yahoo Finance) is unofficial and can be late, incomplete or wrong.

---

## 1. The problem

Retail investors in India who try "AI stock analysis" meet one of two things:

1. **Screeners** (Screener.in, Tickertape, Trendlyne) with deep fundamentals but no explanation, no synthesis and a steep learning curve.
2. **AI agents** (TradingAgents, ai-hedge-fund and similar) that produce confident, readable verdicts, but built for US tickers, with no way to check where a number came from.

I ran the best-known open-source agent, TradingAgents, on 27 Indian large caps. What I found:

- Its fundamentals analyst reported **no usable statements on 26 of 27 tickers**, so its ratings rested mostly on price charts.
- It gave **zero Underweight or Sell calls** (16 Overweight, 11 Hold): a quiet bullish lean.
- **68 of 175 numbers** in its final decisions appeared in none of its own reports.
- It crashed on Mahindra & Mahindra (`M&M.NS`) because the ticker contains an `&`.
- It cost about **16 model calls and 59k tokens per ticker**, which matters on free model tiers.

The product problem is not "build a smarter model". It is **"make an AI research answer something a beginner can verify."**

## 2. Who it is for

| Segment | Job to be done | What they get |
|---|---|---|
| **Curious beginner** (primary) | "Help me understand this company without being told what to buy." | Plain-English summary, a nine-point checklist, bull vs bear in prose, gaps called out |
| **DIY investor** | "Check a number I read in a tweet or video." | Claim checker: *"TCS EPS was 142.66"* is matched to a sourced fact, or flagged |
| **Power user with an AI key** | "Give me the full analyst debate, and keep my key private." | Optional six-call analyst panel or three-call bull/bear debate, key stays in the browser |

**Deliberately not served:** active traders wanting signals, anyone wanting order placement or tips.

## 3. Product principles (the bets)

1. **Provenance first.** Every figure carries period, unit, source and basis, or is marked unavailable with a reason. Missing quarters are flagged, never filled.
2. **Maths is code, the model only narrates.** Scores, ratios and levels are computed deterministically. A model writes prose over a ~2k-token digest, and its claims are machine-checked against that digest.
3. **India aware.** Renames (Zomato to Eternal), demergers (Tata Motors), official NSE shareholding patterns with pledges, a point-in-time liquid universe from open data.
4. **Private by design.** No accounts, no logins. A user's model key never leaves their browser.
5. **Education, not advice.** A rating exists, but it is labelled educational, carries a confidence level with visible reasons, and a test enforces that output avoids advice wording.

## 4. What I built

Per company, one report with:

- Source-linked facts and a list of data gaps
- A pool-relative score and a nine-point checklist
- What the price implies (reverse-DCF grid, never a target price)
- Business health from annual statements (free cash flow, net debt, EV/EBITDA, ROCE, 3-year growth, a lender metric set for banks)
- Ownership: official NSE shareholding pattern, pledges, quarter-on-quarter change, market-wide FII/DII positioning
- Bull vs bear case in readable prose, plus a scenario plan for every rating (levels, staged exposure ceiling, what would change the view)
- Educational rating (Buy / Overweight / Hold / Underweight / Sell) with confidence built from six visible ingredients
- Recent headlines, exchange filings, a **decision journal** that settles each past rating against the Nifty 50, and a **claim checker**

Surfaces: Streamlit app, Next.js web app, HTTP API, Claude connector (works in chat and Cowork), Claude Code plugin, CLI.

## 5. Key product decisions and trade-offs

| Decision | Alternatives considered | Why |
|---|---|---|
| Code computes, model narrates | Multi-agent debate for everything | ~26x fewer tokens, repeatable output, claims can be verified. Cost: less lively prose, so I later added an *optional* debate for users with their own key. |
| Educational rating kept, advice wording banned | No rating at all; or a plain Buy/Sell call | Users want a clear answer; a rating with confidence and reasons gives one without pretending to be advice. |
| No accounts, key stays in the browser | Accounts, saved portfolios | Removes the regulatory and security surface; trades away retention features. |
| Free data sources only | Paid data feeds | Zero cost to serve and run; trades away depth (about five quarters, unofficial feeds), which is why gaps are shown, not hidden. |
| Standalone product, not a TradingAgents fork | Adapter on top of it | Its architecture can't carry provenance or Indian identity. |
| Legal review deferred | Gate launch on a securities lawyer | Project is research and education; disclaimers stay on every surface. Revisit before any public or commercial launch. |

Full MoSCoW list with statuses: [docs/MOSCOW_PRIORITIES.md](docs/MOSCOW_PRIORITIES.md). Items I chose **not** to build (order placement, broker links, a target-price DCF, multi-round debates by default) are listed there with reasons.

## 6. Evidence: what was measured

Head-to-head against TradingAgents on 27 Indian tickers, same Gemini key and model, one run per ticker ([full write-up](docs/HEAD_TO_HEAD_2026-11-06.md)):

| | TradingAgents | NexTrade |
|---|---|---|
| Model calls per ticker (mean) | 16.3 | 1 |
| Tokens per ticker (mean) | 58,923 | 2,293 |
| Seconds per ticker (mean) | 90 | 18 |
| Tickers with no usable fundamentals | 26 of 27 | 0 of 27 |
| Handles every Indian ticker (`M&M.NS`) | no | yes |
| Rating mix | 0 Buy, 16 Overweight, 11 Hold, 0 negative | 4 Buy, 8 Overweight, 13 Hold, 2 Underweight |
| Agree on direction | 44% of tickers | |

**Where TradingAgents is still better, by my own table:** a concrete entry/stop/size plan and a more readable two-sided argument. I closed both gaps next (scenario plan for every rating, prose bull/bear, optional three-call debate), at about 8k tokens against its 59k.

**Also tested:** a ten-year backtest of simple price signals on 470 to 500 Indian stocks ([result](docs/2026-10-26-backtest-result.md)). Momentum kept a small positive edge out of sample; low volatility and the composite faded. I treat it as a hint, not evidence, and say so on the report.

## 7. A metric I got wrong, and fixed

In the head-to-head, NexTrade's confidence label read **"High" on 26 of 27 tickers**. It only counted how many score factors had data, so it said almost nothing. I caught it in my own results, did not ship around it, and rebuilt confidence from six visible ingredients: factors with data, comparison-pool size, checks measured, distance from a rating boundary, whether score and evidence agree, and whether annual data is present. Fewer than four factors is always Low. A 12-ticker re-run gave **6 High and 6 Medium**, and the reason line states what decided it.

## 8. What I do not know yet (honest limits)

- **Whether either system's ratings are accurate.** Outcomes are unmeasured. The decision journal settles each rating against the Nifty 50 after 21 trading sessions; first read is about 8 December 2026.
- **Whether real users want this.** No user tests yet. Discovery with 5 to 8 beginner investors is the next step, not something I can claim done.
- **Whether NexTrade's four Buys are artefacts.** They sit in a 12-company comparison pool and all outperformed the Nifty over a year, so they may be momentum.
- **Data depth.** Free data means thin history compared with Screener.in or Trendlyne. Bank NIM and NPA are still missing.
- **Legal.** Not reviewed by a securities lawyer. Required before any public or commercial launch.

## 9. What I would do next

1. **Run the 21-session settlement** and publish both systems' hit rates against the Nifty 50. This decides whether the rating is worth keeping.
2. **Moderated sessions with beginners**: can they find the verdict, explain a gap, and check a claim? Measure time to first useful answer and comprehension, not clicks.
3. **Expand the comparison pool** from 12 to 25+ companies to make ranks (and confidence) meaningful.
4. **Bank metrics (NIM, NPA)**, the largest gap for the biggest Indian sector.
5. **Persistent saved reports and a shareable link**, the first retention feature that doesn't require accounts.

Roadmap: [docs/ROADMAP.md](docs/ROADMAP.md) · Quality and UX review: [docs/QUALITY_AND_UX_REVIEW_2026-11-07.md](docs/QUALITY_AND_UX_REVIEW_2026-11-07.md) · Competitive brief: [COMPETITIVE_BRIEF.md](COMPETITIVE_BRIEF.md) · Product review: [docs/PRODUCT_REVIEW.md](docs/PRODUCT_REVIEW.md)

## 10. Skills this project shows

Problem framing from a competitor teardown · segmentation and jobs-to-be-done · MoSCoW prioritisation and explicit won't-haves · trade-off documentation · writing specs for engineering (see `docs/`) · defining and challenging metrics · experiment design (head-to-head, backtest, decision journal) · AI product cost modelling (tokens per report) · responsible-AI and compliance-aware wording · shipping across web, API and chat surfaces.

---

## Try it

```bash
uv venv --python 3.12 && uv pip install -e ".[dev,api]"
python -m indiafacts RELIANCE.NS --score --explain --html report.html     # terminal and HTML report
python -m indiafacts.claims TCS.NS eps 142.66 --unit per_share            # check a stated figure against sourced facts
python -m indiafacts.journal settle                                      # score past educational ratings against the Nifty 50
python -m indiafacts.journal board                                       # scoreboard by rating
python -m indiafacts.backtest --from-year 2016 --oos-start 2023-01-01     # price-signal scorecard
python -m indiafacts TCS.NS --shareholding SHP_file.xml --flows        # ownership from a saved NSE file, plus market flows
python -m indiafacts TCS.NS --announcements                              # latest exchange filings from NSE's public RSS feed
streamlit run streamlit_app.py                                           # the Streamlit app
```
Web app (Next.js): [web/README.md](web/README.md) · Streamlit deploy: [docs/DEPLOY_STREAMLIT.md](docs/DEPLOY_STREAMLIT.md) · API and connector hosting: [docs/DEPLOY.md](docs/DEPLOY.md) · Connector lock: [docs/CONNECTOR_LOCK.md](docs/CONNECTOR_LOCK.md) · Token accounting: [docs/TOKEN_COMPARISON.md](docs/TOKEN_COMPARISON.md)

Claude Code plugin (private repo for now):
```
/plugin install indiafacts --marketplace pallavidhadda/nextrade
/indiafacts:analyze RELIANCE.NS          # uses the NexTrade connector (works in chat and Cowork)
/indiafacts:analyze-local RELIANCE.NS    # Claude Code only: runs locally, needs network and uv
```

## Licence
Apache-2.0 (see `LICENSE`, `NOTICE`). Real NSE/BSE files and third-party datasets are not included and keep their own terms. TejHQ data: attribute TejHQ.
