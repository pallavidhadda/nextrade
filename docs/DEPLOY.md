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

## Claude Plugins page (web, desktop, mobile chat): what it needs
Official docs (claude.com/docs/plugins/overview, checked 2026-10-31): a plugin can bundle skills and remote connectors, and chat on the web, desktop and mobile loads them; shell commands and hooks do not run in chat, which is why the old slash commands only work in Claude Code. Users add a marketplace from **Customize > Plugins > Add > Add marketplace** with `pallavidhadda/nextrade`; a private GitHub repo works after connecting GitHub and installing the Claude GitHub App on it. Connectors are added from the plugin's Connectors tab. Custom connector limits by plan (for example one on the Free plan) come from third-party pages; verify.

What is built: a remote MCP endpoint at `/mcp` on the same API (tools `start_analysis` and `get_analysis`, stateless, no keys, no user data stored) and the skill `skills/indian-stock-research`. Claude itself narrates the digest in the user's own chat, so we pay no model tokens.

To switch it on after the API has a public HTTPS address:
1. Set `INDIAFACTS_MCP_HOSTS=your-api-host` on the server (turns on host and origin checks) and optionally `INDIAFACTS_POOL_SIZE=12` for speed.
2. `cp connector/mcp.json.example .mcp.json`, put the real URL (`https://your-api-host/mcp`) in it, commit, push.
3. In claude.ai: Customize > Plugins > Add > Add marketplace > `pallavidhadda/nextrade`, install NexTrade, open its Connectors tab, add and connect the connector. Ask: "Analyse TCS.NS".
Claude connects from Anthropic's cloud, so the API must be publicly reachable over valid HTTPS. That favours Render (HTTPS included) over a bare Oracle VM, which would need a domain and a certificate or a tunnel. A sleeping free host will make the first tool call slow or fail; the skill tells Claude to retry.

## Optional lock on the connector (recommended until public launch; full steps in docs/CONNECTOR_LOCK.md)
Without a lock, anyone who knows `/mcp` can use the connector and spend the free server's CPU (the app also limits requests per minute and runs one analysis at a time). To lock it: in Render set `INDIAFACTS_MCP_TOKEN` to a long random string. Then in claude.ai Customize > Connectors > nextrade > Request headers add `Authorization` = `Bearer <the same string>`. `/api/health` stays open. Do not commit the token anywhere. To open the connector to everyone later, delete the variable.

## Report link in chat results
Set `INDIAFACTS_PUBLIC_URL` on Render to the service address (for example `https://nextrade-api-7z41.onrender.com`). Finished chat results then include a link to the interactive HTML report (charts and tables). Reports live in server memory for a few hours and vanish when the free server restarts.
