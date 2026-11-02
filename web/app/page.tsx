"use client";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import ContourMap from "@/components/ContourMap";
import ProfileChooser from "@/components/Profile";
import OwnModelPanel from "@/components/OwnModel";
import { Checklist, Debate, Explanation, Gaps, KeyFacts, Levels, News, Score, Valuation } from "@/components/Result";
import { ApiError, poll, reportUrl, submit } from "@/lib/api";
import type { Job, Profile, Summary } from "@/lib/types";

const EXAMPLES = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ITC.NS"];
const DISCLAIMER = "Research and education only. Not financial, investment or trading advice. Data may be late, incomplete or wrong; check primary sources.";
const TABS = [{ id: "summary", label: "Summary" }, { id: "report", label: "Full report" }, { id: "gaps", label: "Gaps" }] as const;
const PROFILE_KEY = "nextrade.profile";

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <>
      <header className="bar"><div className="container">
        <a className="brand" href="/" aria-label="NexTrade home">NexTrade</a>
        <a className="link" href="#disclaimer">Education only, not advice</a>
      </div></header>
      <main><div className="container">{children}</div></main>
      <footer className="foot" id="disclaimer"><div className="container"><p>{DISCLAIMER} NexTrade does not store your profile, holdings or keys on its servers.</p></div></footer>
    </>
  );
}

function Home() {
  const router = useRouter();
  const params = useSearchParams();
  const jobId = params.get("job");
  const tab = (params.get("tab") ?? "summary") as (typeof TABS)[number]["id"];
  const [ticker, setTicker] = useState(params.get("t") ?? "");
  const [profile, setProfile] = useState<Profile>({});
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    try { const p = sessionStorage.getItem(PROFILE_KEY); if (p) setProfile(JSON.parse(p)); } catch { /* storage may be unavailable */ }
  }, []);
  useEffect(() => {
    try { sessionStorage.setItem(PROFILE_KEY, JSON.stringify(profile)); } catch { /* ignore */ }
  }, [profile]);

  const setUrl = useCallback((q: Record<string, string | null>) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(q)) { if (v === null) next.delete(k); else next.set(k, v); }
    router.replace(`/?${next.toString()}`, { scroll: false });
  }, [params, router]);

  useEffect(() => {
    if (!jobId) { setJob(null); return; }
    let stop = false;
    const tick = async () => {
      try {
        const j = await poll(jobId);
        if (stop) return;
        setJob(j);
        if (j.status === "queued" || j.status === "running") timer.current = setTimeout(tick, 2000);
      } catch (e) {
        if (!stop) { setError(e instanceof ApiError ? e.message : "Something went wrong."); setJob(null); }
      }
    };
    setError(null);
    tick();
    return () => { stop = true; if (timer.current) clearTimeout(timer.current); };
  }, [jobId]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const t = ticker.trim().toUpperCase();
    if (!t) { setFieldError("Enter a ticker such as RELIANCE or TCS.NS."); return; }
    setFieldError(""); setError(null); setBusy(true);
    try {
      const id = await submit(t, Object.fromEntries(Object.entries(profile).filter(([, v]) => v)) as Profile);
      setUrl({ job: id, t, tab: "summary" });
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Something went wrong.";
      if (err instanceof ApiError && err.status === 422) setFieldError(msg); else setError(msg);
    } finally { setBusy(false); }
  }

  const summary: Summary | undefined = job?.status === "done" ? job.summary : undefined;
  const running = !!jobId && (!job || job.status === "queued" || job.status === "running") && !error;
  const failed = error ?? (job?.status === "error" ? job.error ?? "The analysis failed." : null);

  if (summary && jobId) return <Shell><ResultView s={summary} jobId={jobId} tab={tab} onTab={(t) => setUrl({ tab: t })} onNew={() => router.replace("/")} /></Shell>;

  if (running) return (
    <Shell>
      <div className="head"><div><h1>Reading {ticker || params.get("t") || "the company"}</h1><p className="sub">Fetching facts, checking gaps and comparing with a pool of companies.</p></div></div>
      <div className="grid" aria-busy="true">
        <div className="skel" style={{ height: 300 }} /><div className="stack"><div className="skel" style={{ height: 140 }} /><div className="skel" style={{ height: 160 }} /></div>
      </div>
      <p className="progress" role="status">{job?.progress ? `Comparing, step ${job.progress}` : "Starting. A first run takes about a minute; repeat runs are quicker."}</p>
    </Shell>
  );

  return (
    <Shell>
      <div className="start">
        <div>
          <h1>Read an Indian stock from its facts</h1>
          <p className="lead">NexTrade collects the numbers behind an NSE or BSE company, shows the period and source of each, says what is missing, and compares it with peers. It never says buy or sell.</p>
          <form className="form" onSubmit={onSubmit} noValidate>
            <div className="row">
              <div className="field">
                <label htmlFor="ticker">Ticker</label>
                <input id="ticker" name="ticker" value={ticker} onChange={(e) => setTicker(e.target.value)} autoComplete="off" autoCapitalize="characters" spellCheck={false} placeholder="RELIANCE.NS" aria-describedby="ticker-help" aria-invalid={!!fieldError} />
              </div>
              <button className="key primary" type="submit" disabled={busy}>{busy ? "Starting" : "Analyse"}</button>
            </div>
            <p id="ticker-help" className={`helper${fieldError ? " err" : ""}`} role={fieldError ? "alert" : undefined}>{fieldError || "Add .NS for NSE or .BO for BSE. Without a suffix, NSE is assumed."}</p>
            <div className="chips" aria-label="Example tickers">{EXAMPLES.map((x) => <button key={x} type="button" className="chip mono" onClick={() => setTicker(x)}>{x}</button>)}</div>
            <ProfileChooser value={profile} onChange={setProfile} />
          </form>
          {failed && <div className="state" role="alert" style={{ marginTop: "var(--space-lg)" }}><h2>That did not work</h2><p>{failed}</p></div>}
          <ul className="ruled">
            <li>Every figure carries its period, unit and source.</li>
            <li>Missing quarters are stated, never filled in.</li>
            <li>A score against a comparison pool, and nine plain checks.</li>
            <li>Facts and inferences are labelled apart.</li>
          </ul>
          <p className="privacy">Nothing about you is stored on our servers. Your profile choices live in this browser tab only.</p>
        </div>
        <figure className="map" style={{ margin: 0 }}><ContourMap /><figcaption>Generated survey map</figcaption></figure>
      </div>
    </Shell>
  );
}

function ResultView({ s: base, jobId, tab, onTab, onNew }: { s: Summary; jobId: string; tab: string; onTab: (t: string) => void; onNew: () => void }) {
  const [own, setOwn] = useState<Summary["explanation"]>(null);
  const s: Summary = own ? { ...base, explanation: own } : base;
  return (
    <>
      <div className="head">
        <div>
          <h1>{s.name ?? s.ticker}</h1>
          <p className="sub">{[s.name ? s.ticker : null, s.industry ?? s.sector, s.isin].filter(Boolean).join(", ")}. Profile: {s.profile.horizon}, {s.profile.risk} risk, {s.profile.experience}.</p>
        </div>
        <button className="key" type="button" onClick={onNew}>Analyse another</button>
      </div>
      <div className="tabs" role="tablist" aria-label="Result sections">
        {TABS.map((t) => (
          <button key={t.id} className="tab" role="tab" aria-selected={tab === t.id} type="button" onClick={() => onTab(t.id)}>
            {t.id === "gaps" ? `Gaps (${s.gaps.length})` : t.label}
          </button>
        ))}
      </div>
      {tab === "report" ? (
        <div style={{ marginTop: "var(--space-lg)" }}>
          <iframe className="report" title={`Full report for ${s.ticker}`} src={reportUrl(jobId)} sandbox="allow-scripts" />
        </div>
      ) : tab === "gaps" ? (
        <div style={{ marginTop: "var(--space-lg)", maxWidth: 900 }}><Gaps s={s} /></div>
      ) : (
        <div className="grid">
          <div className="stack"><Score s={s} /><Debate s={s} /><Levels s={s} /><Valuation s={s} /><Checklist s={s} /></div>
          <div className="stack"><Explanation s={s} /><News s={s} /><OwnModelPanel jobId={jobId} summary={base} onExplanation={setOwn} /><KeyFacts s={s} /></div>
        </div>
      )}
    </>
  );
}

export default function Page() {
  return <Suspense fallback={null}><Home /></Suspense>;
}
