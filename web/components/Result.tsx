"use client";
import { factorLabel, formatValue, metricLabel } from "@/lib/format";
import type { Summary } from "@/lib/types";

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
    <section className="entry" aria-labelledby="chk-h">
      <header><h2 id="chk-h">Nine-point checklist</h2><span className="note">{s.checklist.length ? `${pass} passed` : "needs a score run"}</span></header>
      <div className="body">
        {s.checklist.length === 0 ? <p>The checklist runs together with the score.</p> : (
          <table>
            <thead><tr><th>Test</th><th>Result</th></tr></thead>
            <tbody>
              {s.checklist.map((c) => (
                <tr key={c.label}>
                  <td>{c.label}<span className="ids">{c.display ? `${c.display}, needs ${c.threshold}` : c.reason}</span></td>
                  <td><span className={`tag ${c.result}`}>{c.result === "unavailable" ? "Unavailable" : c.result === "pass" ? "Pass" : "Fail"}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="helper" style={{ marginTop: "var(--space-sm)" }}>Project-defined tests. Missing data shows as unavailable, never as a fail.</p>
      </div>
    </section>
  );
}

export function KeyFacts({ s }: { s: Summary }) {
  return (
    <section className="entry" aria-labelledby="kf-h">
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
    <section className="entry" aria-labelledby="ex-h">
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
    <section className="entry" aria-labelledby="gp-h">
      <header><h2 id="gp-h">What could not be checked</h2><span className="note">{s.gaps.length} items</span></header>
      <div className="body">
        {s.gaps.length === 0 ? <p>No missing periods or unavailable measures were found.</p> : (
          <table>
            <thead><tr><th>Measure</th><th>Period</th><th>Why</th></tr></thead>
            <tbody>{s.gaps.map((g, i) => (<tr key={i}><td>{metricLabel(g.metric)}</td><td className="num" style={{ textAlign: "left" }}>{g.period}</td><td>{g.reason}</td></tr>))}</tbody>
          </table>
        )}
        {s.notices.length > 0 && <ul className="claims">{s.notices.map((n, i) => <li key={i} style={{ gridTemplateColumns: "1fr" }}>{n}</li>)}</ul>}
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
    <section className="entry" aria-labelledby="val-h">
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
  const col = (title: string, pts: { text: string; evidence: string }[]) => (
    <div>
      <h3>{title}</h3>
      <ul className="plain">{pts.length === 0 ? <li>None found.</li> : pts.map((p, i) => <li key={i}>{p.text}<span className="ids">{p.evidence}</span></li>)}</ul>
    </div>
  );
  return (
    <section className="entry" aria-labelledby="deb-h">
      <header><h2 id="deb-h">Bull case versus bear case</h2><span className="note">educational</span></header>
      <div className="body">
        <div className="debate">{col("Bull case", d.bull)}{col("Bear case", d.bear)}</div>
        <p className="stance"><span className="tag stance-tag">{d.stance.label}</span> Confidence {d.stance.confidence}. {d.stance.reason}.</p>
        <p className="helper">Educational rating from a transparent rule applied to the evidence on this page. It ignores your own situation, is not a prediction, and is not a recommendation.</p>
      </div>
    </section>
  );
}

export function News({ s }: { s: Summary }) {
  if (!s.news || s.news.length === 0) return null;
  return (
    <section className="entry" aria-labelledby="news-h">
      <header><h2 id="news-h">Recent headlines</h2><span className="note">unverified, keyword hint only</span></header>
      <div className="body">
        <table>
          <thead><tr><th>Date</th><th>Source</th><th>Headline</th><th>Hint</th></tr></thead>
          <tbody>{s.news.map((n, i) => (
            <tr key={i}><td>{n.published ?? "undated"}</td><td>{n.publisher}</td><td>{n.title}</td>
              <td><span className={`tag ${n.sentiment_hint === "neutral" ? "hypothesis" : n.sentiment_hint === "positive" ? "fact" : "fail"}`}>{n.sentiment_hint}</span></td></tr>
          ))}</tbody>
        </table>
        <p className="helper" style={{ marginTop: "var(--space-sm)" }}>Third-party headlines are not verified and are not facts about the company. The hint is a keyword guess, not analysis.</p>
      </div>
    </section>
  );
}

export function Levels({ s }: { s: Summary }) {
  const lv = s.levels, rp = s.risk_panel;
  if (!lv || lv.last_close === null) return null;
  const inr = (v: number) => `₹${v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  return (
    <section className="entry" aria-labelledby="lev-h">
      <header><h2 id="lev-h">Reference levels and risk lenses</h2><span className="note">arithmetic</span></header>
      <div className="body">
        <table>
          <thead><tr><th>Level</th><th className="num">Price</th></tr></thead>
          <tbody>
            <tr><td>Last close</td><td className="num">{inr(lv.last_close)}</td></tr>
            {lv.support.map((x) => <tr key={x.name}><td>Support: {x.name}</td><td className="num">{inr(x.price)}</td></tr>)}
            {lv.resistance.map((x) => <tr key={x.name}><td>Resistance: {x.name}</td><td className="num">{inr(x.price)}</td></tr>)}
            {lv.applies && lv.stop !== null && <tr><td>Reference stop ({lv.risk_pct?.toFixed(1)}% below)</td><td className="num">{inr(lv.stop)}</td></tr>}
            {lv.applies && lv.targets.map((t) => <tr key={t.r}><td>Reward-to-risk {t.r}R</td><td className="num">{inr(t.price)}</td></tr>)}
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
    <section className="entry" aria-labelledby="health-h">
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

const REASONS = 3;
export function AtAGlance({ s, onTab }: { s: Summary; onTab: (t: string) => void }) {
  const st = s.debate?.stance;
  const pass = s.checklist.filter((c) => c.result === "pass").length;
  const known = s.checklist.filter((c) => c.result !== "unavailable").length;
  const bull = s.debate?.bull.slice(0, REASONS) ?? [];
  const bear = s.debate?.bear.slice(0, REASONS) ?? [];
  return (
    <section className="glance" aria-labelledby="glance-h">
      <h2 id="glance-h" className="sr">At a glance</h2>
      <div className="glance-row">
        <div><span className="glance-k">Educational rating</span><strong className="glance-v">{st ? st.label : "No rating"}</strong><span className="glance-s">{st ? `${st.confidence} confidence. A rule-based reading, not advice.` : "Not enough data."}</span></div>
        <div><span className="glance-k">Score in pool</span><strong className="glance-v">{s.score?.overall != null ? `${s.score.overall.toFixed(0)}/100` : "n/a"}</strong><span className="glance-s">{s.score?.rank ? `rank ${s.score.rank} of ${s.score.n}` : "not scored"}</span></div>
        <div><span className="glance-k">Checks passed</span><strong className="glance-v">{known ? `${pass}/${known}` : "n/a"}</strong><span className="glance-s">{s.checklist.length - known > 0 ? `${s.checklist.length - known} unavailable` : "all measurable"}</span></div>
        <div><span className="glance-k">Gaps to know about</span><strong className="glance-v">{s.gaps.length}</strong><span className="glance-s"><button type="button" className="linkish" onClick={() => onTab("gaps")}>see what is missing</button></span></div>
      </div>
      {(bull.length > 0 || bear.length > 0) && (
        <div className="glance-why">
          <div><h3>Working in its favour</h3><ul>{bull.map((p) => <li key={p.text}>{p.text}</li>)}{bull.length === 0 && <li>Nothing stands out.</li>}</ul></div>
          <div><h3>Worth being careful about</h3><ul>{bear.map((p) => <li key={p.text}>{p.text}</li>)}{bear.length === 0 && <li>Nothing stands out.</li>}</ul></div>
        </div>
      )}
    </section>
  );
}
