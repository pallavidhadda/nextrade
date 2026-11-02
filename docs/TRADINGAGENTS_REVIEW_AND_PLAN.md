# How TradingAgents is built, and where NexTrade replaces AI with code (2026-11-02)
Research/education only; not financial, investment or trading advice. Read from the source of TauricResearch/TradingAgents at v0.7.1 (commit c454491, pulled 2026-11-02, Apache-2.0). Token numbers come from our own baseline run (RELIANCE.NS, 2026-10-23, Gemini free tier, only the market and fundamentals analysts selected): 13 LLM calls, 32,825 input and 6,046 output tokens. A run with all four analysts was NOT measured and would cost more.

## 1. The pipeline (graph/setup.py)
Analysts (up to 4, each its own tool-calling loop, up to `max_tool_rounds` = 20) -> Bull and Bear researchers (debate, `max_debate_rounds` = 1) -> Research Manager (deep model, structured rating) -> Trader (proposal) -> Aggressive, Conservative and Neutral risk debaters (`max_risk_discuss_rounds` = 1) -> Portfolio Manager (deep model, final rating on a 5-point scale Buy/Overweight/Hold/Underweight/Sell). A memory log settles past decisions against realised returns and feeds lessons back into prompts. Data goes through a vendor router (Yahoo, Alpha Vantage, SEC EDGAR, FRED, Reddit, StockTwits, Polymarket). It also has a backtest module and structured-output schemas.

## 2. Where the tokens go (measured, our baseline)
| Call group | Calls | Input tokens | Why it is big |
|---|---|---|---|
| Market and fundamentals analysts (tool loops) | calls 1-6 | about 15.3k | each tool result is pasted back into the next model turn |
| Bull and Bear researchers | 2 | about 6.4k | every turn resends all analyst reports plus the debate so far |
| Research Manager, Trader | 2 | about 4.3k | the whole debate history again |
| Three risk debaters | 3 | about 7.5k | reports, plan and the growing risk history again |
| Portfolio Manager | 1 | 4.3k | everything again |
The cost is structural: the same reports are re-read by 8 or more later calls, and arithmetic and fetching are done by a model.

## 3. Component by component: what needs AI, what is code
| TradingAgents part | Does AI add value? | NexTrade today | Status / next |
|---|---|---|---|
| Market analyst: calls price and indicator tools, writes prose | No: returns, drawdown, volatility, beta, 52-week range are arithmetic | `pricemetrics.py` facts with window rules and corporate-action flags | Done. Gap: classic indicators (SMA, RSI, MACD, Bollinger) not yet computed; add as deterministic facts |
| Fundamentals analyst | No for numbers; the prose adds little | Typed facts with period, unit, source, basis, gaps, TTM, NSE filing and XBRL import | Done (data depth limited by free sources) |
| News analyst | Partly: fetching and de-duplicating is code; summarising is language work | Google News RSS titles, dedupe, age limit, noise filter, keyword hint; narration is optional and uses the user's own model | Done v1 |
| Sentiment analyst (Reddit, StockTwits) | Counting posts and tagged sentiment is code | none for India | Not built: needs an Indian source (StockTwits India coverage and Reddit relevance unverified) |
| Bull and Bear researchers | Argument writing is the one place a model helps readability | Rule-based BULL and BEAR lists, each point tied to evidence; the model only narrates | Done v1 (rules); optional one-call LLM debate not built |
| Research Manager | No: weighing is a rule | Educational stance from score plus point balance, with confidence | Done v1; thresholds are proposals to backtest |
| Trader (entry, stop, target) | No, and targets are risky | Not produced on purpose | Intentional gap |
| Risk debaters (3 calls) | No: risk is volatility, drawdown, beta versus a stated tolerance | Risk factor, drawdown and volatility facts and bear points | Done as facts; a deterministic risk panel by profile is not built |
| Portfolio Manager | Final wording only | Stance line plus one narration call | Done |
| Memory log and reflection | The settlement maths is code; reflection text is optional | `brain.db` stores each run and what changed | Not built: record each stance, settle it against later price returns, show hit rates (the ai-hedge-fund scorecard idea) |
| Backtest | code | price-signal scorecard on TejHQ data | Partly; the stance itself is untested |
| Provider flexibility | n/a | Gemini, any OpenAI-compatible URL (OpenRouter, Ollama, LM Studio), Anthropic | Done; OpenRouter live not tested (no key) |

## 4. Resulting token budget
Code does fetching, maths, checks, bull/bear lists and the stance. A model is called at most once per report, on a digest of about 1.2k to 1.9k tokens, and it may be the user's own chat model. Measured earlier: 1.1k to 1.2k input plus about 0.4k output (about 1.6k) for an explanation, against 39k for the baseline run (not like-for-like: the baseline did more narrative work). That fits free Gemini quotas and free OpenRouter models. To use OpenRouter: set `INDIAFACTS_LLM_BASE_URL=https://openrouter.ai/api/v1`, `OPENAI_API_KEY` to your OpenRouter key, and pass `--llm openai --llm-model <model id>` (model names change; check OpenRouter's list; untested here).

## 5. What "improving TradingAgents" can mean from here
A. Keep NexTrade as its own engine (current) and publish the comparison and the code.
B. Build a LangGraph adapter so a TradingAgents user can replace the analyst nodes with `indiafacts` nodes (zero LLM calls) and feed the compact digest to the existing researchers and managers. Smallest change to their repo: a new analyst spec plus a data vendor. Measured benefit would come from skipping the 6 tool-loop calls and shrinking the report text that is resent 8 times.
C. Contribute the pieces upstream (an India vendor, deterministic verified snapshot, provenance gaps). Needs the maintainers' agreement.
Recommended order: finish the deterministic parts still missing (indicators, risk panel, stance journal with settlement), then do B and measure a like-for-like run (same ticker, same date, same free model) so the claim is evidence, not a ratio between different jobs.
