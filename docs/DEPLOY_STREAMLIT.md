# Deploy the Streamlit app free from GitHub (Streamlit Community Cloud)
Limits below come from third-party pages, checked 2026-10-31; verify on streamlit.io: about 1 GB or more of memory, sleeps after about 12 hours idle, one private app on the free plan, hosted in the US.

1. Go to https://share.streamlit.io and sign in with GitHub (`pallavidhadda`). Allow access to the private repo `nextrade` when asked.
2. New app > Deploy from a repository. Repository `pallavidhadda/nextrade`, branch `main`, main file path `streamlit_app.py`.
3. Advanced settings: Python 3.12 (the code needs 3.12 or newer). Under Secrets, add nothing: the app needs no keys.
4. Optional environment settings: put `INDIAFACTS_POOL_SIZE = "12"` in Secrets (they are exposed as environment variables) for faster first runs.
5. Deploy. The first build installs `requirements.txt`. You get an address like `https://nextrade.streamlit.app`.
6. Open it and analyse `TCS.NS`. A first run can take a few minutes; the app caches results for an hour per ticker.

Notes
- Streamlit runs our Python on its server, so this app does not ask for an AI key. Use the Claude connector for the bring-your-own-model route.
- The app starts the analysis as a child process (`python -m indiafacts`), at most two at once.
- Updates: push to `main` and the app redeploys.
- Untested: the Community Cloud build itself (done locally only: unit tests with Streamlit's AppTest, and a real run in a browser against Yahoo data).
