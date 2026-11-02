# Sentiment and news sources for India, and where finished reports can live (2026-11-02)
Everything below comes from web searches of third-party pages, not from the vendors' own documentation unless stated. Verify before relying on any limit, price or coverage claim. Research/education only; not financial, investment or trading advice.

## 1. Headline and sentiment sources for NSE/BSE companies
| Source | Free? | India coverage | Use for NexTrade | Verdict |
|---|---|---|---|---|
| Google News RSS (in use) | Yes, no key | Any search; we filter titles that name the symbol | Headline titles, dates, publishers; keyword sentiment hint | In use. Terms of use unverified: keep titles only, no article text |
| Yahoo Finance news via yfinance | Yes | Returned nothing for TCS.NS and RELIANCE.NS when tested | none | Kept as a first try, falls back to Google |
| EODHD | Free plan reported at 20 calls per day, end-of-day data only; news and sentiment reported on paid plans (EOD plan reported near 19.99 per month) | NSE coverage not confirmed in what I found | Possible paid upgrade for a sentiment score per headline | Check the exchange list and plan before paying |
| Marketaux | Free plan reported at 100 requests per day; entity sentiment from -1 to +1 | NSE/BSE tagging not confirmed | Candidate for a scored sentiment per ticker | Test one Indian ticker with a free key first |
| Alpha Vantage NEWS_SENTIMENT | Free about 25 requests per day | A secondary source says NSE/BSE symbols returned empty | none | Unlikely to work for India |
| Reddit API | Free for non-commercial use, about 100 requests per minute with OAuth; new access reportedly needs manual approval and commercial use needs a deal | Subreddits such as r/IndianStockMarket exist; data volume per stock is small | Mentions count and tone for large caps only | Possible for a non-commercial portfolio project; check current terms; many Indian stocks will have too few posts |
| X (Twitter) API | Free tier reportedly closed to new developers on 2026-02-06; pay per use, about 0.005 per post read | Cashtag handling for NSE symbols unverified | Cost is per post and adds up | Not recommended now |
| Tickertape Market Mood Index | Via an unofficial library (tickersnap) | Market-wide fear/greed gauge, not per stock | One market-level line in the report | Possible; unofficial API can break |
| Sentimatix (third-party project) | Reported free tier without a key | Claims NSE/BSE news sentiment | Candidate scorer | Unknown uptime and terms; not adopted |
| Google Trends search volume | Unofficial wrappers | Academic evidence for India is mixed | Attention proxy to test | Test before using |

**Recommended path (deterministic first, cheap):** keep Google News RSS titles plus the keyword hint now; add one market-level gauge (Market Mood Index) if its terms allow; then trial Marketaux for a per-ticker scored sentiment on 5 Indian tickers to see if it covers them; add Reddit mention counts for large caps if the free non-commercial terms fit. Every added source must be shown as unverified third-party data and never enter the score.

## 2. What `INDIAFACTS_PUBLIC_URL` is, and the alternatives
It is just the web address of our API, for example `https://nextrade-api-7z41.onrender.com`. Render gives every service one automatically (shown at the top of the service page). We use it only to print a link to the full interactive report in chat results. Reports live in the server's memory, so after a restart or sleep the link stops working.
Alternatives:
1. Do nothing: the link works while the server stays up (free tier sleeps after about 15 minutes idle).
2. Store each finished report in a private bucket and send a short-lived signed link: Supabase Storage or Cloudflare R2 (both reported to have free tiers; limits unverified). Supabase is already connected in this workspace. Reports contain public facts plus the profile choices, never keys.
3. Skip links: have the chat render the report text itself (what the 14-section narration already does).
4. If you move off Render: Cloudflare Tunnel or ngrok can expose a server on your own computer at a temporary public address (good for testing, not for always-on).
