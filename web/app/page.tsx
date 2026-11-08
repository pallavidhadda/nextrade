"use client";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import ContourMap from "@/components/ContourMap";
import TickerBox from "@/components/TickerBox";
import ProfileChooser from "@/components/Profile";
import OwnModelPanel from "@/components/OwnModel";
import { AnalystPanel, AtAGlance, ScenarioPlan, Checklist, Debate, Health, MarketFlows, Ownership, Explanation, Gaps, KeyFacts, Levels, News, Valuation } from "@/components/Result";
import { Scrub, ScoreFactors, ScoreNumber, SplitWords } from "@/components/Reveal";
import companies from "@/lib/companies.json";
import { ApiError, poll, reportDownloadUrl, reportUrl, submit } from "@/lib/api";
import type { Job, PanelResult, Profile, Summary } from "@/lib/types";

const EXAMPLES = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ITC.NS"];
const TAPE: [string, string][] = [["Reliance Industries", "RELIANCE"], ["Tata Consultancy Services", "TCS"], ["HDFC Bank", "HDFCBANK"], ["Infosys", "INFY"], ["ITC", "ITC"], ["ICICI Bank", "ICICIBANK"], ["Larsen & Toubro", "LT"], ["Bharti Airtel", "BHARTIARTL"], ["Asian Paints", "ASIANPAINT"], ["Maruti Suzuki", "MARUTI"]];
const DISCLAIMER = "Research and education only. Not financial, investment or trading advice. Data may be late, incomplete or wrong; check primary sources.";
const TABS = [{ id: "summary", label: "Summary" }, { id: "report", label: "Full report" }, { id: "gaps", label: "Gaps" }] as const;
const COMPANIES = companies as { s: string; n: string; i: string }[];
const HOW = [
  { k: "collect", title: "Collect", text: "Every figure carries its period, unit and source." },
  { k: "gaps", title: "Name the gaps", text: "Missing quarters are stated, never filled in." },
  { k: "compare", title: "Compare with peers", text: "A score against a comparison pool, and nine plain checks." },
  { k: "explain", title: "Explain plainly", text: "Facts and inferences are labelled apart." },
] as const;

/** Turn what a person typed (a symbol or part of a company name) into a ticker, or return it unchanged. */
function resolveTicker(raw: string): string {
  const t = raw.trim();
  const up = t.toUpperCase();
  if (!t || /\.(NS|BO)$/.test(up) || COMPANIES.some((c) => c.s === up)) return up;
  const q = t.toLowerCase();
  const hit = COMPANIES.find((c) => c.n.toLowerCase() === q) ?? COMPANIES.find((c) => c.n.toLowerCase().startsWith(q));
  return hit ? `${hit.s}.NS` : up;
}
/** "[4/30] BAJFINANCE.NS" -> "Comparing with other companies: 4 of 30 done". */
function progressText(raw: string): string {
  const m = raw.match(/\[(\d+)\/(\d+)\]/);
  return m ? `The first run is slowest; repeat runs are quicker.` : `Comparing, step ${raw}`;
}
/** "[4/30] BAJFINANCE.NS" -> how far the survey has got, so the map can draw itself to match. */
function progressRatio(raw: string | undefined): { done: number; total: number; p: number } | null {
  const m = raw?.match(/\[(\d+)\/(\d+)\]/);
  if (!m) return null;
  const done = Number(m[1]), total = Math.max(1, Number(m[2]));
  return { done, total, p: Math.min(1, 0.08 + 0.92 * (done / total)) };
}
const PROFILE_KEY = "nextrade.profile";

function Mark() {
  return (
    <svg className="mark" viewBox="0 0 32 32" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
      <path d="M3 22c5-1 7-9 13-9s8 8 13 6" /><path d="M3 16c5-1 7-8 13-8s8 7 13 5" opacity="0.6" /><circle cx="21.5" cy="17.2" r="2.6" fill="var(--color-accent)" stroke="none" />
    </svg>
  );
}

function Arrow() {
  return (
    <svg className="arrow" viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M4 10h11M11 5l5 5-5 5" /></svg>
  );
}

function Shell({ children, home }: { children: React.ReactNode; home?: boolean }) {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const on = () => setScrolled(scrollY > 40);
    on();
    addEventListener("scroll", on, { passive: true });
    return () => removeEventListener("scroll", on);
  }, []);
  return (
    <>
      <a className="skip" href="#main">Skip to content</a>
      <header className="bar" data-scrolled={scrolled || undefined}>
        <div className="container">
          <a className="brand" href="/" aria-label="NexTrade home"><Mark /><span>NexTrade</span></a>
          <nav aria-label="Primary">
            {home && <a className="navlink" href="#how">How it reads</a>}
            <a className="pill-note" href="#disclaimer">Education only, not advice</a>
          </nav>
        </div>
      </header>
      <main id="main">{children}</main>
      <footer className="foot" id="disclaimer">
        <div className="container">
          <p className="foot-text">{DISCLAIMER} NexTrade does not store your profile, holdings or keys on its servers.</p>
          <p className="foot-mark" aria-hidden="true">NexTrade</p>
        </div>
      </footer>
    </>
  );
}

function HowGlyph({ kind }: { kind: string }) {
  const common = { viewBox: "0 0 200 110", fill: "none", stroke: "currentColor", strokeWidth: 1.6, strokeLinecap: "round" as const, className: "glyph", "aria-hidden": true };
  if (kind === "collect") return (
    <svg {...common}>{[22, 55, 88].map((y, i) => <g key={y}><path pathLength={1} d={`M14 ${y}H${150 - i * 24}`} style={{ ["--i" as string]: i }} /><circle cx={162 - i * 24} cy={y} r="4" fill="var(--color-accent)" stroke="none" style={{ ["--i" as string]: i }} /></g>)}</svg>
  );
  if (kind === "gaps") return (
    <svg {...common}><path pathLength={1} d="M12 55H72" /><path pathLength={1} d="M128 55H188" style={{ ["--i" as string]: 2 }} /><path d="M82 55H118" strokeDasharray="2 7" className="dash" /><circle cx="100" cy="55" r="9" className="hole" /></svg>
  );
  if (kind === "compare") return (
    <svg {...common}>{[[24, 70], [46, 52], [62, 80], [84, 40], [104, 64], [124, 30], [146, 58], [164, 44]].map(([x, y], i) => <circle key={i} className="dot" cx={x} cy={y} r="4" fill="currentColor" stroke="none" style={{ ["--i" as string]: i }} />)}<circle className="pick" cx="104" cy="64" r="12" style={{ ["--i" as string]: 9 }} /></svg>
  );
  return (
    <svg {...common}><rect pathLength={1} x="14" y="20" width="74" height="30" rx="15" /><rect pathLength={1} x="62" y="62" width="104" height="30" rx="15" style={{ ["--i" as string]: 1 }} /><circle cx="30" cy="35" r="4" fill="var(--color-accent)" stroke="none" /><circle cx="78" cy="77" r="4" fill="var(--color-ember)" stroke="none" /></svg>
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
  const [ring, setRing] = useState(0.78);
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
    const t = resolveTicker(ticker);
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

  function pick(sym: string) {
    setTicker(sym);
    setFieldError("");
    scrollTo({ top: 0, behavior: "smooth" });
    setTimeout(() => document.querySelector<HTMLInputElement>('input[name="ticker"]')?.focus({ preventScroll: true }), 350);
  }

  const summary: Summary | undefined = job?.status === "done" ? job.summary : undefined;
  const running = !!jobId && (!job || job.status === "queued" || job.status === "running") && !error;
  const failed = error ?? (job?.status === "error" ? job.error ?? "The analysis failed." : null);

  if (summary && jobId) return <Shell><ResultView s={summary} jobId={jobId} tab={tab} onTab={(t) => setUrl({ tab: t })} onNew={() => router.replace("/")} /></Shell>;

  if (running) {
    const pr = progressRatio(job?.progress);
    const name = params.get("t") || ticker || "the company";
    const steps = [
      { label: "Fetching facts", state: pr ? "done" : "active" },
      { label: "Checking gaps", state: pr ? "done" : "wait" },
      { label: pr ? `Comparing with ${pr.total} companies` : "Comparing with a pool of companies", state: pr ? "active" : "wait" },
    ];
    return (
      <Shell>
        <section className="stage stage-run" aria-busy="true">
          <div className="stage-map"><ContourMap progress={pr ? pr.p : 0.3} ringX={0.72} /></div>
          <div className="container stage-in">
            <SplitWords as="h1" text={`Reading ${name}`} />
            <ol className="steps" aria-label="Progress">
              {steps.map((st) => <li key={st.label} data-state={st.state}><i aria-hidden="true" /><span>{st.label}</span></li>)}
            </ol>
            {pr && (
              <div className="count" role="status">
                <span className="n num">{String(pr.done).padStart(2, "0")}</span><span className="of">of {pr.total} compared</span>
                <span className="track" aria-hidden="true"><b style={{ transform: `scaleX(${pr.done / pr.total})` }} /></span>
              </div>
            )}
            <p className="progress" role="status">{job?.progress ? progressText(job.progress) : "Starting. A first run takes about a minute; repeat runs are quicker."}</p>
          </div>
        </section>
      </Shell>
    );
  }

  return (
    <Shell home>
      <section className="stage">
        <div className="stage-map"><ContourMap ringX={ring} /></div>
        <div className="callouts" aria-hidden="true">
          <span className="callout c1">Period, unit and source on every figure</span>
          <span className="callout c2">Gaps stated, never filled</span>
          <span className="callout c3">Scored against a peer pool</span>
        </div>
        <div className="container stage-in">
          <SplitWords as="h1" text="Read an Indian stock from its *facts*" />
          <p className="lead rise" style={{ ["--d" as string]: "520ms" }}>NexTrade collects the numbers behind an NSE or BSE company, shows the period and source of each, says what is missing, and compares it with peers. It never says buy or sell.</p>
          <form className="form rise" style={{ ["--d" as string]: "680ms" }} onSubmit={onSubmit} noValidate>
            <div className="console">
              <TickerBox value={ticker} onChange={setTicker} error={fieldError} helpId="ticker-help" />
              <button className="key primary" data-magnetic type="submit" disabled={busy}><span>{busy ? "Starting" : "Analyse"}</span><Arrow /></button>
            </div>
            <p id="ticker-help" className={`helper${fieldError ? " err" : ""}`} role={fieldError ? "alert" : undefined}>{fieldError || "Type a company name (for example Infosys, even misspelled) or a ticker. Add .BO for BSE; NSE is the default."}</p>
            <div className="chips" aria-label="Example tickers">
              {EXAMPLES.map((x, i) => <button key={x} type="button" className="chip mono" style={{ ["--i" as string]: i }} onClick={() => setTicker(x)} onPointerEnter={() => setRing(0.62 + (i % 3) * 0.1)} onPointerLeave={() => setRing(0.78)}>{x}</button>)}
            </div>
            <ProfileChooser value={profile} onChange={setProfile} />
          </form>
          {failed && <div className="state" role="alert"><h2>That did not work</h2><p>{failed}</p></div>}
        </div>
        <div className="tape" aria-label="Companies you can try">
          <div className="tape-run">
            {[0, 1].map((dup) => (
              <ul key={dup} aria-hidden={dup === 1 || undefined}>
                {TAPE.map(([n, sym]) => <li key={sym}><button type="button" tabIndex={dup === 1 ? -1 : 0} onClick={() => pick(sym)}>{n}<i className="mono">{sym}</i></button></li>)}
              </ul>
            ))}
          </div>
        </div>
      </section>

      <section className="how" id="how">
        <div className="container">
          <h2 className="how-title" data-r>How a reading is made</h2>
          <ol className="how-list">
            {HOW.map((h, i) => (
              <li className="how-row" data-r style={{ ["--d" as string]: `${i * 60}ms` }} key={h.k}>
                <span className="how-n num" aria-hidden="true">{String(i + 1).padStart(2, "0")}</span>
                <div className="how-t"><h3>{h.title}</h3><p>{h.text}</p></div>
                <HowGlyph kind={h.k} />
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="statement">
        <div className="container">
          <Scrub text="NexTrade never says buy or sell. It lays out the facts, the gaps and the arithmetic, so the decision stays with you." />
          <p className="privacy" data-r>Nothing about you is stored on our servers. Your profile choices live in this browser tab only.</p>
        </div>
      </section>
    </Shell>
  );
}

function ResultView({ s: base, jobId, tab, onTab, onNew }: { s: Summary; jobId: string; tab: string; onTab: (t: string) => void; onNew: () => void }) {
  const [own, setOwn] = useState<Summary["explanation"]>(null);
  const [panel, setPanel] = useState<PanelResult[]>([]);
  const s: Summary = own ? { ...base, explanation: own } : base;
  const name = s.name ?? COMPANIES.find((c) => `${c.s}.NS` === s.ticker)?.n ?? s.ticker;
  return (
    <>
      <section className="stage band">
        <div className="stage-map"><ContourMap ringX={0.8} interactive /></div>
        <div className="container band-in">
          <div className="band-head">
            <div>
              <SplitWords as="h1" text={name} />
              <p className="sub rise" style={{ ["--d" as string]: "300ms" }}>{[s.name ? s.ticker : null, s.industry ?? s.sector, s.isin].filter(Boolean).join(", ")}. Profile: {s.profile.horizon}, {s.profile.risk} risk, {s.profile.experience}.</p>
            </div>
            <div className="actions rise" style={{ ["--d" as string]: "420ms" }}>
              <a className="key primary" data-magnetic href={reportDownloadUrl(jobId)} download><span>Download report</span></a>
              <button className="key" type="button" onClick={() => window.print()}>Print or save PDF</button>
              <button className="key" type="button" onClick={onNew}>Analyse another</button>
            </div>
          </div>
          <div className="band-read"><ScoreNumber s={s} /><ScoreFactors s={s} /></div>
        </div>
      </section>
      <div className="subnav">
        <div className="container">
          <div className="tabs" role="tablist" aria-label="Result sections">
            {TABS.map((t) => (
              <button key={t.id} className="tab" role="tab" aria-selected={tab === t.id} type="button" onClick={() => onTab(t.id)}>
                {t.id === "gaps" ? `Gaps (${s.gaps.length})` : t.label}
              </button>
            ))}
          </div>
          <span className="subnav-name">{name}</span>
        </div>
      </div>
      <div className="container body-pad" key={tab}>
        {tab === "summary" && <AtAGlance s={s} onTab={onTab} />}
        {tab === "report" ? (
          <iframe className="report" title={`Full report for ${s.ticker}`} src={reportUrl(jobId)} sandbox="allow-scripts" />
        ) : tab === "gaps" ? (
          <div className="stack"><Gaps s={s} /></div>
        ) : (
          <div className="stack">
            <Explanation s={s} /><Debate s={s} /><Checklist s={s} /><Health s={s} /><Valuation s={s} /><Ownership s={s} /><ScenarioPlan s={s} /><Levels s={s} /><MarketFlows s={s} /><News s={s} /><KeyFacts s={s} />
            <OwnModelPanel jobId={jobId} summary={base} onExplanation={setOwn} onPanel={setPanel} /><AnalystPanel results={panel} />
          </div>
        )}
      </div>
    </>
  );
}

export default function Page() {
  return <Suspense fallback={null}><Home /></Suspense>;
}
