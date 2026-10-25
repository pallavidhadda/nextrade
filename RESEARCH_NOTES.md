# R&D notes: what four open-source finance-agent repos actually do
Read from shallow clones (source, not READMEs only) on 2026-10-25. Not run; behaviour inferred from code and docs. Scratch clones are in the job tmp dir, not kept.

## ai-hedge-fund (virattt) — package `hedge_fund`
- Architecture: each "investor" (Buffett, Graham, Lynch, Munger, Druckenmiller) is a **single system prompt** over a point-in-time fundamentals snapshot (`signals/buffett.py`, `signals/llm_agent.py`). Output is strict JSON `{signal, confidence, reasoning}`. Quant models (`signals/pead.py`, post-earnings drift) share the same Signal interface in pure Python.
- Blending and sizing are deterministic: `portfolio/construction.py` (conviction-weighted, long-only / long-short / dollar-neutral), then `risk/limits.py` clamps max position and gross exposure; "conviction requests, risk disposes", clamps logged, removed exposure goes to cash.
- `llm/cache.py`: every LLM decision cached on disk by hash(agent, model, prompt) => backtests re-run at $0, and it doubles as audit trail.
- `scorecard/analysts.py`: grades each analyst by hit rate, slugging and rank IC (Spearman) vs benchmark. Abstention is a first-class outcome ("data insufficient -> neutral").
- Strategies are YAML fund specs (`strategies/*.yaml`). Paper trading ledger and backtests included. Providers incl. TypeSafe (Jev), Gemini, Anthropic.
- Steal: single-call personas, JSON contract, cache, deterministic sizing + risk, scorecard, abstain.
- Caveat: data from Financial Datasets (US-focused, paid key).

## FinRobot (AI4Finance)
- V2 "desktop" is the production line: lead agent + 5 pipeline agents + bull/bear/judge, but the core claim is **"numbers are code-calculated, narratives are LLM-assisted"**: 32 pure-Python operators (DCF, DDM, LBO, WACC, comps, Monte Carlo, SOTP...) in `engine/compute/operators/`.
- Audit layer (`engine/models/numeric_claim.py`): each number is a NumericClaim with provenance and findings (`info` / `review` / `blocked_field`). A bad number withholds that figure and any price target derived from it, never the whole verdict. Report status: publishable / caveated / unpublishable.
- Cross-provider validator (`engine/data/validator.py`): compares two data providers on revenue/net income/market cap and warns on disagreement; documents which fields NOT to compare (caliber differences). 7 providers with failover.
- 13-chapter report with price target + range + confidence; ~184k lines total.
- Steal: operator library for valuation, NumericClaim ledger, caveat-not-refuse gating, provider failover. Caveat: heavy (Tauri desktop, large stack); copy the ideas, not the stack. Licence/trademark policy to check before reuse.

## TradingAgents (Tauric) — our baseline
- 12 agents, LangGraph; reports pasted whole into 8+ downstream prompts; full debate history resent each turn. Our run: 13 calls, ~39k tokens (2 analysts, flash-lite).
- Weak spots found: fundamentals blind for Indian tickers (point-in-time guard), targets/stops are just SMA/Bollinger levels, no real portfolio context, no scorecard in the default run.
- Strengths: point-in-time discipline against look-ahead bias, memory log of past decisions, wide provider support (Ollama, OpenAI-compatible, Gemini).

## OpenBB (platform)
- Data-platform, not an agent: ~20 providers (FRED, IMF, OECD, ECB, SEC, EIA, ...), extensions for equity/economy/technical/quantitative, REST + Python.
- `extensions/mcp_server`: exposes routes as MCP tools with **tool discovery** so the agent sees a few search/call tools instead of the full catalog => explicit token-bloat fix.
- IMF and OECD providers could cover India macro and world data (India coverage not verified). Technical/quantitative extensions = deterministic indicators and stats we should call, not prompt an LLM for.
- Steal: provider/extension pattern, lazy tool discovery, IMF/OECD macro as the World Bank alternative to evaluate.

## Synthesis (R&D view)
Biggest token wins come from architecture, not prompt trimming:
1. Move all arithmetic and indicators to code (FinRobot, OpenBB).
2. Replace debates with one JSON call per lens (ai-hedge-fund).
3. Cache by prompt hash (ai-hedge-fund).
4. Deterministic funnel before any LLM call.
5. Lazy tool exposure (OpenBB MCP).
Biggest trust wins: provenance + audit gating (FinRobot), scorecard (ai-hedge-fund), explicit "no data" (all three, missing in our baseline).
Open questions: India fundamentals source with dated filings; licences of any code we reuse (read each LICENSE before copying); whether IMF/OECD via OpenBB gives usable India series.
