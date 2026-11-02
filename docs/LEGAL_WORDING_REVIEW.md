# Legal wording review (2026-10-31) — NOT legal advice
I am an AI assistant, not a lawyer. This is a risk map built from secondary sources found by web search (law-firm and tax-portal summaries, not the SEBI text itself). A qualified Indian securities lawyer must confirm before any public launch. Citations are leads to verify on sebi.org.in.

## What the sources say (unverified against primary text)
- SEBI (Research Analysts) Regulations, 2014 (in force from December 2014; amended, including a Third Amendment on 16 December 2024): a person who issues research reports or research analysis must be registered. Secondary FAQs say certain items are excluded (for example generic technical analysis of sector demand and supply, comments on general market trends). The exact definitions of "research report" and "research analysis" were not in what I could read.
- Circular SEBI/HO/MIRSD/MIRSD-PoD-1/P/CIR/2025/003 (8 January 2025): registered RAs and IAs using AI tools must disclose it, and stay responsible for client data security and the output. SEBI FAQs reportedly say research material, including AI-generated content, must state the publisher's SEBI registration details. This applies to registered entities; whether it reaches an unregistered educational tool is a question for the lawyer.
- Incidental advice as part of another primary business may not need registration; stock-specific recommendations beyond that reportedly do.
- I found nothing confirming an exemption for "educational" content or for finfluencer-style tools. Do not assume one exists.

## Where NexTrade is exposed (highest first)
1. **A public, stock-specific "score" and "rank" can be read as a rating or research output.** Mitigation now: labelled "percentile inside a pool, not absolute quality"; no buy/sell/hold, no target prices, banned-word filter on model output. Open question for the lawyer: is a ranked score of named listed companies "research analysis" even without a recommendation?
2. **Personalisation.** The investor profile changes factor weights. Personalised output based on a user's risk profile is where "investment advice" rules (suitability) tend to start. Today the profile only reweights factors and the report says so; there is no "fit" or "suitable for you" statement (I removed an old placeholder line that implied a fit score). Safer product choice if the lawyer is cautious: make the profile optional and present weightings as "how the pool score changes", or drop personalisation from the public site.
3. **Name and positioning.** "Research assistant" avoids the protected-sounding "research analyst" and "investment adviser". Keep the words "analyst", "advisor", "advisory", "recommendation", "signals" and "tips" off the site and out of the app name and domain.
4. **AI disclosure.** Even if not required of us, say plainly on every result which parts were written by a model, by the visitor's own model, or by a template. The app already shows the source of the explanation.
5. **Accuracy and sources.** Free Yahoo data is unofficial. Keep the "may be late, incomplete or wrong; check primary sources" line, the gap list and the as-of date on every output.
6. **Data licences.** NSE/BSE pages and TejHQ data have their own terms; not reviewed. Do not redistribute exchange files; attribute TejHQ.
7. **Personal data.** The design stores none (key in browser, profile in the tab). Keep it that way and say it; if analytics are ever added, India's DPDP Act applies (not reviewed).

## Wording rules adopted
Allowed: facts with source and period; "the price implies X growth"; "scores X inside this pool"; "could not be checked".
Not allowed: buy, sell, hold, accumulate, avoid, target, upside, "good/bad stock", "suitable for you", "we recommend", return predictions, "guaranteed", "AI analyst".
Every screen and export keeps the disclaimer. The tests already enforce banned words in model output and the disclaimer in outputs.

## Questions to put to a lawyer (copy as is)
1. Does a public tool that ranks named listed companies on a formula, with no recommendation, require research-analyst registration?
2. Does reweighting a score by a user-entered risk profile make it investment advice?
3. Does the bring-your-own-model feature change who is the "publisher" of the explanation?
4. Is an unregistered educational disclaimer effective, and what must it say?
5. Any restriction on showing exchange-derived data and third-party datasets (NSE, BSE, TejHQ) in a public app?

## Update 2026-11-02: bull/bear debate, educational stance and headlines were added at the owner's direction
The owner chose to include a bull case versus bear case, a decision-like "educational stance" and recent headlines, relying on a disclaimer. My assessment, unchanged: a disclaimer does not change how a regulator classifies an activity. A stance on named listed companies, published to the public, is the feature most likely to be treated as a research report or a recommendation under the SEBI research analyst rules (not verified against the primary text). It is safe for private and portfolio use; get the five questions answered by a securities lawyer before public launch.
Design choices that reduce, not remove, the risk: the stance is a transparent rule on the score and the evidence points (no model judgement), labelled "Positive lean / Neutral / Negative lean" and not buy/sell/hold, always shown with confidence and reason, never personalised, never with a price target; the narrator may not turn it into an instruction; it shows "No stance" when data is thin. Headlines are unverified third-party titles from Google News RSS (terms of use not verified), kept as titles only with a rough keyword hint.
