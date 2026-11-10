"use client";
import { factorLabel, formatValue, metricLabel } from "@/lib/format";
import type { Summary } from "@/lib/types";
import { execView, levelFormula, YAHOO_DOWN_LINE } from "@/lib/exec";

export function Decomposition({ s }: { s: Summary }) {
  const x = execView(s);
  if (x.rows.length === 0 && x.rankNotes.length === 0 && !x.comparison) return null;
  const overall = s.score?.overall;
  return (
    <>
      {x.rows.length > 0 && (
        <table style={{ marginTop: "var(--space-md)" }}>
          <caption className="sr">How the overall score is built</caption>
          <thead><tr><th>Factor</th><th className="num">Score</th><th className="num">Base weight</th><th className="num">Effective weight</th><th className="num">Contribution</th></tr></thead>
          <tbody>
            {x.rows.map((r) => <tr key={r.name}><td>{r.name}</td><td className="num">{r.score.toFixed(1)}</td><td className="num">{Math.round(r.base_weight * 100)}%</td><td className="num">{Math.round(r.effective_weight * 100)}%</td><td className="num">{r.contribution.toFixed(1)}</td></tr>)}
            <tr><td><strong>Sum of contributions</strong></td><td /><td /><td /><td className="num"><strong>{x.total.toFixed(1)}</strong>{overall != null ? ` = overall ${overall.toFixed(1)}` : ""}</td></tr>
          </tbody>
        </table>
      )}
      {x.sentence && <p className="helper">{x.sentence}</p>}
      {x.rankNotes.map((n) => <p className="helper" key={n}>{n}</p>)}
      {x.comparison && x.comparison.sources.length > 0 && (
        <>
          <h3>Where each measure comes from</h3>
          <p className="helper">The same source is used for every company compared.</p>
          <ul className="plain">{x.comparison.sources.map((t) => <li key={t}>{t}</li>)}</ul>
        </>
      )}
    </>
  );
}

export function CompBadge({ s }: { s: Summary }) {
  const x = execView(s);
  const c = x.comp;
  if (!c) return null;
  return <p className="comp-badge"><span className={`light ${x.tone}`}>Data: {c.level}</span> {x.words}</p>;
}

function RatingTag({ x }: { x: ReturnType<typeof execView> }) {
  return <><span className={`tag stance-tag${x.directional ? "" : " neutral"}`}>{x.label}</span>{x.insufficient && <span className="light warn">Insufficient evidence</span>}</>;
}

export function Executive({ s }: { s: Summary }) {
  const x = execView(s);
  const c = x.comp;
  const list = (items: string[], empty: string) => <ul className="plain">{(items.length ? items : [empty]).map((i) => <li key={i}>{i}</li>)}</ul>;
  return (
    <>
      <section className="entry" data-r aria-labelledby="exec-h">
        <header><h2 id="exec-h">In plain English</h2><span className="note">read this first</span></header>
        <div className="body">
          <h3>What this means</h3>
          <p><RatingTag x={x} /> {x.meaning}</p>
          <h3>What is missing</h3>{list(x.missing, "nothing flagged")}
          <h3>What to monitor</h3>{list(x.monitor, "nothing specific to watch")}
        </div>
      </section>
      {c && (
        <section className="entry" data-r aria-labelledby="comp-h">
          <header><h2 id="comp-h">How complete is the data</h2><span className="note">{c.level}</span></header>
          <div className="body">
            <p>{x.words}</p>
            <ul className="plain pillars">{x.items.map(([n, st]) => <li key={n}>{n}: {st}</li>)}</ul>
            {x.stale && <p className="helper">{x.stale}</p>}
            {x.verification && <p className="helper">{x.verification}</p>}
            {x.conflicts.length > 0 && (<><h3>Conflicting figures</h3><ul className="plain">{x.conflicts.map((t) => <li key={t}>{t}</li>)}</ul></>)}
          </div>
        </section>
      )}
    </>
  );
}

export function Score({ s }: { s: Summary }) {
  const sc = s.score;
  return (
    <section className="entry notebook" aria-labelledby="score-h">
      <header><h2 id="score-h">Score inside the comparison pool</h2><span className="note">0 to 100</span></header>
      <div className="body">
        {sc && sc.overall !== null ? (
          <>
            <p className="reading">{sc.overall.toFixed(1)}<small>of 100</small></p>
            <p className="rank">Rank {sc.rank} of {sc.n} in {sc.pool ?? "the pool"}. It orders companies inside this pool and is not absolute quality.</p>
            <div className="factors">
              {Object.entries(sc.factors).map(([k, f]) => (
                <div className="factor" key={k}>
                  <span>{factorLabel(k)}</span>
                  {f.score === null ? <span className="na">Not scored: {f.reason || "not enough data"}</span> : (
                    <>
                      <div className="bar-track" role="img" aria-label={`${factorLabel(k)} ${f.score.toFixed(0)} of 100`}><div className="bar-fill" style={{ width: `${Math.max(2, f.score)}%` }} /></div>
                      <span className="num">{f.score.toFixed(0)}</span>
                    </>
                  )}
                </div>
              ))}
            </div>
            <Decomposition s={s} />
          </>
        ) : (
          <p>No score for this run{sc?.reason ? `: ${sc.reason}` : ", because the company is not in the comparison pool"}.</p>
        )}
      </div>
    </section>
  );
}

export function Checklist({ s }: { s: Summary }) {
  const pass = s.checklist.filter((c) => c.result === "pass").length;
  return (
    <section className="entry" data-r aria-labelledby="chk-h">
      <header><h2 id="chk-h">Nine-point checklist</h2><span className="note">{s.checklist.length ? `${pass} passed` : "needs a score run"}</span></header>
      <div className="body">
        {s.checklist.length === 0 ? <p>The checklist runs together with the score.</p> : (
          <>
          <div className="meter" role="img" aria-label={`${pass} of ${s.checklist.length} checks passed`}>
            {s.checklist.map((c, i) => <i key={c.label} className={c.result} style={{ ["--i" as string]: i }} />)}
          </div>
          {(s.checklist_groups?.length ? s.checklist_groups : [{ group: "", text: "" }]).map((g) => (
            <div key={g.group}>
              {g.group && <h3>{g.group}: {g.text}</h3>}
              <table>
                <thead><tr><th>Test</th><th>Result</th></tr></thead>
                <tbody>
                  {s.checklist.filter((c) => !g.group || c.group === g.group).map((c, i) => (
                    <tr key={c.label}>
                      <td>{c.label}<span className="ids">{c.display ? `${c.display}, needs ${c.threshold}` : c.reason}</span></td>
                      <td><span className={`tag resolve ${c.result}`} style={{ ["--i" as string]: i }}>{c.result === "unavailable" ? "Unavailable" : c.result === "pass" ? "Pass" : "Fail"}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
          </>
        )}
        <p className="helper" style={{ marginTop: "var(--space-sm)" }}>Project-defined tests, grouped for reading. Each counts once; there are no weights. Missing data shows as unavailable, never as a fail.</p>
      </div>
    </section>
  );
}

const fmtPeer = (v: number | null) => (v === null ? "n/a" : Number(v.toPrecision(3)).toString());

export function PeerSpread({ s }: { s: Summary }) {
  const p = s.peers;
  if (!p) return null;
  const cmp = execView(s).comparison;
  return (
    <section className="entry" data-r aria-labelledby="peer-h">
      <header><h2 id="peer-h">{cmp?.heading ?? "Peer comparison"}</h2><span className="note">{p.n_peers} peers used</span></header>
      <div className="body">
        {p.unavailable_reason || p.n_peers === 0 ? <p>No comparison companies could be matched for this report.</p> : (
          <>
            {p.approximate && <p className="helper"><strong>Approximate peers:</strong> a diversified group compared with single-business companies.</p>}
            {p.few_peers && <p className="helper"><strong>Only {p.n_peers} peer(s) used</strong>, fewer than 5. Treat this as rough.</p>}
            <table>
              <thead><tr><th>Metric</th><th className="num">{s.ticker}</th><th className="num">Median</th><th className="num">Q1</th><th className="num">Q3</th><th>Where it sits</th><th className="num">n</th></tr></thead>
              <tbody>
                {p.metrics.map((m) => (
                  <tr key={m.metric}>
                    <td>{metricLabel(m.metric)}{m.status !== "ok" && <span className="ids">{m.reason}</span>}</td>
                    <td className="num">{fmtPeer(m.target)}</td><td className="num">{fmtPeer(m.median)}</td><td className="num">{fmtPeer(m.q1)}</td><td className="num">{fmtPeer(m.q3)}</td>
                    <td>{m.position ?? "n/a"}</td><td className="num">{m.n}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="helper">Q1 and Q3 are the 25th and 75th percentiles of valid peer values. Peers: {p.picks.map((k) => k.ticker).join(", ")}. A place in the spread is not a verdict.</p>
            {p.notes.filter((n) => !n.startsWith("approximate peers") && !n.startsWith("only ")).map((n) => <p className="helper" key={n}>{n}</p>)}
          </>
        )}
      </div>
    </section>
  );
}

export function KeyFacts({ s }: { s: Summary }) {
  return (
    <section className="entry" data-r aria-labelledby="kf-h">
      <header><h2 id="kf-h">Facts with their period and source</h2><span className="note">latest available</span></header>
      <div className="body">
        {s.key_facts.length === 0 ? <p>No verified figures came back for this company.</p> : (
          <table>
            <thead><tr><th>Measure</th><th className="num">Value</th><th>Period</th><th>Source</th></tr></thead>
            <tbody>
              {s.key_facts.map((f) => (
                <tr key={f.fact_id}>
                  <td>{metricLabel(f.metric)}</td>
                  <td className="num">{formatValue(f.value, f.unit)}</td>
                  <td>{f.period}</td>
                  <td>{f.source}, basis {f.basis}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

export function Explanation({ s }: { s: Summary }) {
  const ex = s.explanation;
  return (
    <section className="entry" data-r aria-labelledby="ex-h">
      <header><h2 id="ex-h">In plain English</h2><span className="note">{ex ? (ex.source === "template" ? "template, no model used" : ex.source === "your model" ? "written by your model, checked here" : `written by ${ex.source}`) : ""}</span></header>
      <div className="body">
        {!ex ? <p>No explanation was produced for this run.</p> : (
          <>
            <p>{ex.summary}</p>
            <ul className="claims">
              {ex.claims.map((c, i) => (
                <li key={i}>
                  <span className={`tag ${c.type}`}>{c.type === "fact" ? "Fact" : c.type === "inference" ? "Inference" : "Hypothesis"}</span>
                  <span>{c.text}<span className="ids">{c.ids.join(", ")}</span></span>
                </li>
              ))}
            </ul>
            {ex.uncertainty && <p style={{ marginTop: "var(--space-sm)" }}><strong>What is uncertain.</strong> {ex.uncertainty}</p>}
          </>
        )}
      </div>
    </section>
  );
}

export function Gaps({ s }: { s: Summary }) {
  return (
    <section className="entry" data-r aria-labelledby="gp-h">
      <header><h2 id="gp-h">What could not be checked</h2><span className="note">{s.gaps.length} items</span></header>
      <div className="body">
        {s.gaps.length === 0 ? <p>No missing periods or unavailable measures were found.</p> : (
          <table>
            <thead><tr><th>Measure</th><th>Period</th><th>Why</th></tr></thead>
            <tbody>{s.gaps.map((g, i) => (<tr key={i}><td>{metricLabel(g.metric)}</td><td className="num" style={{ textAlign: "left" }}>{g.period}</td><td>{g.reason}</td></tr>))}</tbody>
          </table>
        )}
        {s.yahoo_unavailable && <p className="helper">{YAHOO_DOWN_LINE}</p>}
        {s.notices.filter((n) => n !== YAHOO_DOWN_LINE).length > 0 && <ul className="claims">{s.notices.filter((n) => n !== YAHOO_DOWN_LINE).map((n, i) => <li key={i} style={{ gridTemplateColumns: "1fr" }}>{n}</li>)}</ul>}
      </div>
    </section>
  );
}

export function Valuation({ s }: { s: Summary }) {
  const v = s.valuation;
  if (!v) return null;
  const grid: Record<string, Record<string, number | null>> = {};
  for (const it of v.items) {
    const m = it.metric.match(/^implied_growth_r(\d+)_n(\d+)$/);
    if (m) (grid[m[1]] ??= {})[m[2]] = it.value;
  }
  const rates = Object.keys(grid).sort((a, b) => Number(a) - Number(b));
  const years = Array.from(new Set(rates.flatMap((r) => Object.keys(grid[r])))).sort((a, b) => Number(a) - Number(b));
  const pb = v.items.filter((i) => i.metric.startsWith("justified_pb"));
  return (
    <section className="entry" data-r aria-labelledby="val-h">
      <header><h2 id="val-h">What the price implies</h2><span className="note">arithmetic, not a forecast</span></header>
      <div className="body">
        {v.unavailable_reason && v.items.length === 0 ? <p>Not available: {v.unavailable_reason}.</p> : v.method === "reverse_dcf_earnings" ? (
          <>
            <p>Yearly earnings growth the current price would need to be explained, if earnings were fully distributable. It says what is priced in, not what will happen.</p>
            <table style={{ marginTop: "var(--space-sm)" }}>
              <thead><tr><th>Discount rate</th>{years.map((y) => <th className="num" key={y}>{y} years</th>)}</tr></thead>
              <tbody>{rates.map((r) => (
                <tr key={r}><td>{r}%</td>{years.map((y) => <td className="num" key={y}>{grid[r][y] == null ? "n/a" : `${grid[r][y]!.toFixed(1)}% a year`}</td>)}</tr>
              ))}</tbody>
            </table>
          </>
        ) : (
          <p>Price-to-book that the stated return on equity and assumptions would support: <span className="num" style={{ textAlign: "left" }}>{pb.map((i) => i.value?.toFixed(2)).join(" to ")}</span>.</p>
        )}
        <p className="helper" style={{ marginTop: "var(--space-sm)" }}>{v.assumptions}</p>
      </div>
    </section>
  );
}

export function Debate({ s }: { s: Summary }) {
  const d = s.debate;
  if (!d) return null;
  const hasDir = execView(s).directional;
  const col = (title: string, pts: { text: string; evidence: string }[]) => (
    <div>
      <h3>{title}</h3>
      <ul className="plain">{pts.length === 0 ? <li>None found.</li> : pts.map((p, i) => <li key={i}>{p.text}<span className="ids">{p.evidence}</span></li>)}</ul>
    </div>
  );
  return (
    <section className="entry" data-r aria-labelledby="deb-h">
      <header><h2 id="deb-h">Bull case versus bear case</h2><span className="note">educational</span></header>
      <div className="body">
        {s.prose && (<><p>{s.prose.favour}</p><p>{s.prose.against}</p><p><strong>{s.prose.weighing}</strong></p></>)}
        {d.bull.length + d.bear.length > 0 && (
          <div className="balance" role="img" aria-label={`${d.bull.length} points in favour, ${d.bear.length} points against`}>
            <b style={{ flexGrow: d.bull.length || 0.0001 }}>{d.bull.length}</b><b className="bear" style={{ flexGrow: d.bear.length || 0.0001 }}>{d.bear.length}</b>
          </div>
        )}
        <div className="debate">{col("Bull case", d.bull)}{col("Bear case", d.bear)}</div>
        <p className="stance"><RatingTag x={execView(s)} /> {hasDir ? `Confidence ${d.stance.confidence}. ` : ""}{d.stance.reason.replace(/\.$/, "")}.</p>
        <p className="helper">Educational rating from a transparent rule applied to the evidence on this page. It ignores your own situation, is not a prediction, and is not a recommendation.</p>
      </div>
    </section>
  );
}

export function News({ s }: { s: Summary }) {
  if (!s.news || s.news.length === 0) return null;
  return (
    <section className="entry" data-r aria-labelledby="news-h">
      <header><h2 id="news-h">Recent news</h2><span className="note">NSE announcements first; keyword hints only</span></header>
      <div className="body">
        <table>
          <thead><tr><th>Date</th><th>Source</th><th>Headline</th><th>Event type (keyword guess)</th><th>Hint</th></tr></thead>
          <tbody>{s.news.map((n, i) => (
            <tr key={i}><td>{n.published ?? "undated"}</td><td>{n.publisher}{n.source_kind === "exchange" && n.category ? ` (${n.category})` : ""}</td><td>{n.title}</td><td>{n.event_type ?? "other"}</td>
              <td><span className={`tag ${n.sentiment_hint === "neutral" ? "hypothesis" : n.sentiment_hint === "positive" ? "fact" : "fail"}`}>{n.sentiment_hint}</span></td></tr>
          ))}</tbody>
        </table>
        <p className="helper" style={{ marginTop: "var(--space-sm)" }}>Third-party headlines are not verified and are not facts about the company; only those naming the company are kept. The event type and the hint are keyword guesses, not analysis.</p>
      </div>
    </section>
  );
}

export function Levels({ s }: { s: Summary }) {
  const lv = s.levels, rp = s.risk_panel;
  if (!lv || lv.last_close === null) return null;
  const x = execView(s);
  if (!x.directional) {
    return (
      <section className="entry" data-r aria-labelledby="lev-h">
        <header><h2 id="lev-h">Reference levels (not targets)</h2><span className="note">not shown</span></header>
        <div className="body"><p>Not shown: {x.scenarioReason}.</p></div>
      </section>
    );
  }
  const fm = (v: number) => levelFormula(v, lv.last_close, lv.stop, lv.targets, lv.notes);
  const inr = (v: number) => `₹${v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  return (
    <section className="entry" data-r aria-labelledby="lev-h">
      <header><h2 id="lev-h">Reference levels (not targets) and risk lenses</h2><span className="note">arithmetic</span></header>
      <div className="body">
        {x.evidenceNote && <p className="helper">{x.evidenceNote}</p>}
        <table>
          <thead><tr><th>Level</th><th className="num">Price</th></tr></thead>
          <tbody>
            <tr><td>Last close</td><td className="num">{inr(lv.last_close)}</td></tr>
            {lv.support.map((x) => <tr key={x.name}><td>Support: {x.name}</td><td className="num">{inr(x.price)}</td></tr>)}
            {lv.resistance.map((x) => <tr key={x.name}><td>Resistance: {x.name}</td><td className="num">{inr(x.price)}</td></tr>)}
            {lv.applies && lv.stop !== null && <tr><td>Reference stop ({lv.risk_pct?.toFixed(1)}% below)<span className="ids">{fm(lv.stop)}</span></td><td className="num">{inr(lv.stop)}</td></tr>}
            {lv.applies && lv.targets.map((t) => <tr key={t.r}><td>Reference level at {t.r}x the risk<span className="ids">{fm(t.price)}</span></td><td className="num">{inr(t.price)}</td></tr>)}
          </tbody>
        </table>
        {!lv.applies && <p className="helper">Stop and reward-to-risk levels are not shown: {lv.reason}.</p>}
        {rp && (
          <>
            <h3 style={{ marginTop: "var(--space-md)" }}>Risk lenses</h3>
            <table>
              <thead><tr><th>Lens</th><th>Fit</th><th>Why</th><th className="num">Position ceiling</th></tr></thead>
              <tbody>{rp.lenses.map((l) => (
                <tr key={l.name}>
                  <td>{l.name[0].toUpperCase() + l.name.slice(1)}{l.name === rp.profile_lens ? " (your profile)" : ""}</td>
                  <td>{l.fits === null ? "Not applied" : l.fits ? "Within limits" : "Breaches"}</td>
                  <td>{l.fits === null ? l.reason : l.breaches.join("; ") || "None"}</td>
                  <td className="num">{l.max_position_pct === null ? "n/a" : `${l.max_position_pct.toFixed(1)}%`}</td>
                </tr>
              ))}</tbody>
            </table>
            {rp.notes.map((n, i) => <p className="helper" key={i}>{n}</p>)}
          </>
        )}
        <p className="helper">Arithmetic on past closes. Not predictions, not price targets, not personal advice. Lens limits are proposals.</p>
      </div>
    </section>
  );
}

export function Health({ s }: { s: Summary }) {
  const rows = (s.fundamentals ?? []).filter((r) => r.status === "ok" || r.status === "unverified");
  const missing = (s.fundamentals ?? []).filter((r) => r.status !== "ok" && r.status !== "unverified");
  return (
    <section className="entry" data-r aria-labelledby="health-h">
      <header><h2 id="health-h">Business health</h2><span className="note">annual statements</span></header>
      <div className="body">
        {rows.length === 0 ? <p>Annual statements were not available for this run, so year figures, cash flow and EV/EBITDA are missing.</p> : (
          <table>
            <thead><tr><th>Measure</th><th>Value</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.metric}>
                  <td>{r.label}<span className="ids">{r.meaning}</span></td>
                  <td><span className="num">{r.display}</span>{r.reading ? <span className="tag">{r.reading}</span> : null}{r.status === "unverified" ? <span className="ids">vendor proxy, unverified</span> : null}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {missing.length > 0 && <p className="helper" style={{ marginTop: "var(--space-sm)" }}>Not available: {missing.map((m) => m.label).join("; ")}.</p>}
        <p className="helper" style={{ marginTop: "var(--space-sm)" }}>Words like low or healthy describe the number against fixed bands. They are not advice.</p>
      </div>
    </section>
  );
}

const pctS = (v: number) => `${v >= 0 ? "+" : "-"}${Math.abs(v * 100).toFixed(1)}%`;
const rupee = (v: number) => `₹${v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const crore = (v: number) => (v >= 1e12 ? `₹${(v / 1e12).toFixed(2)} lakh crore` : `₹${Math.round(v / 1e7).toLocaleString("en-IN")} crore`);
export function AtAGlance({ s }: { s: Summary; onTab?: (t: string) => void }) {
  const x = execView(s);
  const st = s.debate?.stance;
  const kf = (m: string) => s.key_facts.find((k) => k.metric === m && k.value !== null);
  const fact = (m: string) => {
    const f = (s.facts ?? []).filter((q) => q.metric === m && q.status === "ok" && q.value !== null).sort((a, b) => a.period_end.localeCompare(b.period_end)).pop();
    return f ? Number(f.value) : null;
  };
  const price = kf("price"), cap = kf("market_cap"), pe = kf("pe_ttm");
  // key_facts always reaches the page; the full facts list is stripped from the job response, so use it only as a fallback
  const kv = (m: string) => { const k = kf(m); return k ? Number(k.value) : fact(m); };
  const r1 = kv("return_1y"), rel = kv("relative_return_1y");
  const rated = !!st && x.label !== "No rating";
  const tiles: { k: string; v: string | null; sub: string; extra?: boolean }[] = [
    { k: "Last price", v: price ? rupee(price.value as number) : null, sub: price ? `as of ${price.period}` : "" },
    { k: "Price over 1 year", v: r1 === null ? null : pctS(r1), sub: rel === null ? "" : `${pctS(rel)} against the Nifty 50` },
    { k: "P/E", v: pe ? (pe.value as number).toFixed(1) : null, sub: pe ? "price relative to yearly earnings" : "" },
    { k: "Market value", v: cap ? crore(cap.value as number) : null, sub: "" },
    { k: "Rating", v: rated ? x.label : null, sub: rated ? `${st!.confidence} confidence` : "", extra: x.insufficient },
  ];
  return (
    <section className="glance" data-r aria-labelledby="glance-h">
      <h2 id="glance-h" className="sr">At a glance</h2>
      <div className="glance-row">
        {tiles.map((t) => (
          <div key={t.k} title={t.v === null ? "not available" : undefined}>
            <span className="glance-k">{t.k}</span>
            <strong className="glance-v">{t.v ?? "—"}</strong>
            <span className="glance-s">{t.sub}{t.extra && <span className="light warn">Insufficient evidence</span>}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

export function Ownership({ s }: { s: Summary }) {
  const o = s.ownership;
  if (!o) return null;
  return (
    <section className="entry" data-r aria-labelledby="own-h">
      <header><h2 id="own-h">Who owns it</h2><span className="note">{o.source === "official" ? `NSE filing, as on ${o.as_on}` : "vendor estimate"}</span></header>
      <div className="body">
        {o.rows.length === 0 ? <p>Ownership data is not available for this report.</p> : (
          <table>
            <thead><tr><th>Holder</th><th>Share</th></tr></thead>
            <tbody>
              {o.rows.map((r) => (
                <tr key={r.metric}>
                  <td>{r.label}<span className="ids">{r.change ?? r.meaning}</span></td>
                  <td><span className="num">{r.display}</span>{r.reading ? <span className="tag">{r.reading}</span> : null}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {o.source === "proxy" && <p className="helper" style={{ marginTop: "var(--space-sm)" }}>Official shareholding not available yet; showing a data vendor&apos;s estimate.</p>}
      </div>
    </section>
  );
}

export function MarketFlows({ s }: { s: Summary }) {
  const f = s.market_flows;
  if (!f) return null;
  return (
    <section className="entry" data-r aria-labelledby="flow-h">
      <header><h2 id="flow-h">Market flows</h2><span className="note">as of {f.as_of}</span></header>
      <div className="body">
        {f.rows.length > 0 && <table>
          <thead><tr><th>Who</th><th>Index futures</th></tr></thead>
          <tbody>
            {f.rows.map((r) => (
              <tr key={r.participant}>
                <td>{r.participant}<span className="ids">{Math.round(r.long_share * 100)}% of positions long{r.change !== null ? `; ${r.change >= 0 ? "+" : ""}${r.change.toLocaleString("en-IN")} since ${f.since}` : ""}</span></td>
                <td><span className="num">{Math.abs(r.net).toLocaleString("en-IN")}</span><span className="tag">{r.stance}</span></td>
              </tr>
            ))}
          </tbody>
        </table>}
        {f.cash && (
          <table style={{ marginTop: "var(--space-sm)" }}>
            <thead><tr><th>Cash market, ₹ crore</th><th>Latest net</th></tr></thead>
            <tbody>
              {f.cash.rows.map((r) => (
                <tr key={r.category}>
                  <td>{r.category}<span className="ids">{r.streak} session(s) in a row of {r.streak_word}; {r.window_net.toLocaleString("en-IN")} over {r.sessions} sessions</span></td>
                  <td><span className="num">{r.last_net.toLocaleString("en-IN")}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="helper" style={{ marginTop: "var(--space-sm)" }}>{f.note || f.cash?.note}</p>
      </div>
    </section>
  );
}

export function AnalystPanel({ results }: { results: import("@/lib/types").PanelResult[] }) {
  if (results.length === 0) return null;
  return (
    <>
      {results.map((r) => (
        <section className="entry" data-r key={r.id} aria-label={r.title}>
          <header><h2>{r.title}</h2><span className="note">{r.explanation ? "checked against the facts" : "not shown"}</span></header>
          <div className="body">
            {r.explanation ? (
              <>
                <p>{r.explanation.summary}</p>
                <ul className="claims">
                  {r.explanation.claims.map((c) => (
                    <li key={c.text}><span className={`tag ${c.type}`}>{c.type}</span> {c.text} <span className="ids">{c.ids.join(", ")}</span></li>
                  ))}
                </ul>
                {r.explanation.uncertainty && <p className="helper">{r.explanation.uncertainty}</p>}
              </>
            ) : <p>{r.error || "No valid answer."} Nothing from this answer was shown.</p>}
          </div>
        </section>
      ))}
    </>
  );
}

export function ScenarioPlan({ s }: { s: Summary }) {
  const sc = s.scenario;
  if (!sc) {
    const why = execView(s).scenarioReason;
    return why ? (
      <section className="entry" data-r aria-labelledby="scn-h">
        <header><h2 id="scn-h">Scenario plan</h2><span className="note">not shown</span></header>
        <div className="body"><p>Not shown: {why}.</p></div>
      </section>
    ) : null;
  }
  const lvs = s.levels;
  const fm = (v: number) => (lvs ? levelFormula(v, lvs.last_close, lvs.stop, lvs.targets, lvs.notes) : "");
  const list = (title: string, items: string[]) => items.length > 0 && (<><h3 style={{ marginTop: "var(--space-sm)" }}>{title}</h3><ul className="plain">{items.map((x) => <li key={x}>{x}</li>)}</ul></>);
  return (
    <section className="entry" data-r aria-labelledby="scn-h">
      <header><h2 id="scn-h">Scenario plan</h2><span className="note">{sc.tone}, educational</span></header>
      <div className="body">
        {sc.evidence_note && <p className="helper">{sc.evidence_note}</p>}
        <p><strong>{sc.headline}</strong></p>
        <p>{sc.summary}</p>
        <table style={{ marginTop: "var(--space-sm)" }}>
          <thead><tr><th>Reference levels (not targets)</th><th>Price</th></tr></thead>
          <tbody>{sc.levels.map((l) => <tr key={l.label}><td>{l.label}<span className="ids">{l.meaning}</span>{fm(l.price) && <span className="ids">{fm(l.price)}</span>}</td><td><span className="num">₹{l.price.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span></td></tr>)}</tbody>
        </table>
        <table style={{ marginTop: "var(--space-sm)" }}>
          <thead><tr><th>Staged exposure</th><th>Size</th></tr></thead>
          <tbody>{sc.stages.map((g) => <tr key={g.label}><td>{g.label}<span className="ids">{g.condition}</span></td><td><span className="num">{g.pct === null ? "depends on your ceiling" : `up to ${g.pct.toFixed(1)}% of a portfolio`}</span></td></tr>)}</tbody>
        </table>
        {list("Would turn more positive if these improve", sc.more_positive_if)}
        {list("Would turn more cautious if these fade", sc.more_cautious_if)}
        {list("Dates and things to watch", sc.watch)}
        {sc.notes.map((n) => <p className="helper" key={n}>{n}</p>)}
        <p className="helper">Educational arithmetic on measured prices and stated risk limits. Not a forecast, not a price target, not advice.</p>
      </div>
    </section>
  );
}
