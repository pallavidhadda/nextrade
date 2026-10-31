# Deploying NexTrade (not done yet; needs your accounts)

**API (Python, long jobs):** any container host with a free or cheap tier that allows a process running 1 to 3 minutes: Render, Fly.io, Railway or a small VPS. Vercel functions are not suitable (short time limits, no local cache). I have not verified any host's current free-tier limits.
```bash
docker build -t nextrade-api . && docker run -p 8000:8000 -e INDIAFACTS_CORS=https://YOUR-WEB-URL nextrade-api
```
Env: `INDIAFACTS_CORS` (comma list of allowed web origins), `INDIAFACTS_TRUST_PROXY=1` behind a proxy (already set in the image), optional `INDIAFACTS_LABELS` (path to an NSE index CSV for sector pools; do not ship NSE files without checking terms).
Add a persistent volume for `/home/app/.indiafacts` (price and TejHQ caches) to keep repeat runs fast. Do not put any LLM key on the server: the web app uses the visitor's own key in their browser.

**Web (Next.js):** import the `web/` folder in Vercel, set `NEXT_PUBLIC_API_BASE=https://YOUR-API-URL`. Commits are authored with the GitHub noreply address so the Hobby plan accepts them.

**Before going public:** independent review, SEBI/legal wording check, NSE/TejHQ terms, rate limits tuned to the host.
