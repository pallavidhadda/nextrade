# Deploying NexTrade (not done yet; needs your accounts)

## Which free host (limits from third-party pages, checked 2026-10-31; verify before relying)
| Host | Fit for our 1 to 3 minute analysis jobs | Catch |
|---|---|---|
| **Oracle Cloud Always Free VM** | Best: always on, large RAM, persistent disk for caches, our job-and-poll design works unchanged | You run the server (Docker, TLS); sign-up approval can fail; ARM CPU |
| Render free web service | Easiest start | Sleeps after about 15 minutes, about a minute to wake; 512 MB RAM and a small CPU share; job state is lost on sleep. UI must say "waking up" |
| Koyeb free | No sleep reported by one guide (unverified) | 0.1 vCPU: our 40 s job becomes minutes |
| Google Cloud Run | Generous free quota | CPU is throttled between requests and instances scale to zero, which breaks background jobs unless the API streams the result in one long request |
| Railway | Trial credit about 5 dollars a month | Not free for an always-on service |
| Hugging Face Spaces | Free CPU 2 vCPU 16 GB, sleeps after 48 h | Docker Spaces reportedly need a paid plan |
| Fly.io | Sources disagree | Likely paid |

**My pick:** Oracle Always Free for the API if you can accept the setup work; otherwise Render free for a demo with the sleeping behaviour. Web app on Vercel Hobby either way.


**API (Python, long jobs):** any container host with a free or cheap tier that allows a process running 1 to 3 minutes: Render, Fly.io, Railway or a small VPS. Vercel functions are not suitable (short time limits, no local cache). I have not verified any host's current free-tier limits.
```bash
docker build -t nextrade-api . && docker run -p 8000:8000 -e INDIAFACTS_CORS=https://YOUR-WEB-URL nextrade-api
```
Env: `INDIAFACTS_CORS` (comma list of allowed web origins), `INDIAFACTS_TRUST_PROXY=1` behind a proxy (already set in the image), optional `INDIAFACTS_LABELS` (path to an NSE index CSV for sector pools; do not ship NSE files without checking terms).
Add a persistent volume for `/home/app/.indiafacts` (price and TejHQ caches) to keep repeat runs fast. Do not put any LLM key on the server: the web app uses the visitor's own key in their browser.

**Web (Next.js):** import the `web/` folder in Vercel, set `NEXT_PUBLIC_API_BASE=https://YOUR-API-URL`. Commits are authored with the GitHub noreply address so the Hobby plan accepts them.

**Before going public:** independent review, SEBI/legal wording check, NSE/TejHQ terms, rate limits tuned to the host.
