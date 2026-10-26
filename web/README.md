# NexTrade web

Next.js front end for the `indiafacts` analysis API. Education only; not financial, investment or trading advice.

```bash
# terminal 1: API (from the repo root)
INDIAFACTS_CORS=http://localhost:3000 .venv/bin/uvicorn indiafacts.api:app --port 8765
# terminal 2: web
cd web && npm install && npm run dev      # http://localhost:3000
```
Set `NEXT_PUBLIC_API_BASE` if the API is elsewhere (default `http://localhost:8765`).

## Privacy design
- No accounts, no database of users. The API keeps finished analyses in memory for a few hours and never stores profile, holdings or keys.
- Profile choices (horizon, risk) are sent only as analysis options, and kept in this browser tab's sessionStorage.
- "Explain with your own model": the browser calls the provider directly with the public facts digest. The key lives in component state, is cleared after the request and is never stored, put in a URL or sent to NexTrade. The API only validates the model's answer text against the digest.
- Portfolio holdings are not collected in this version. If added, they stay in the browser.
