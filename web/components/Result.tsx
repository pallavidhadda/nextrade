"use client";
import { factorLabel, formatValue, metricLabel } from "@/lib/format";
import type { Summary } from "@/lib/types";
import { execView, levelFormula } from "@/lib/exec";

export function Decomposition({ s }: { s: Summary }) {
  const x = execView(s);
  if (x.rows.length === 0 && x.rankNotes.length === 0) return null;
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
    </>
  );
}

export function CompBadge({ s }: { s: Summary }) {
  const x = execView(s);
  const c = x.comp;
  if (!c) return null;
  const mark = ({ good: "✓", warn: "!", bad: "✕" } as Record<string, string>)[x.tone];
  return <p className="comp-badge"><span className={`light ${x.tone}`}><span aria-hidden="true">{mark}</span> Data completeness: {c.level}</span> overall coverage {Math.round(c.overall_coverage_pct)}% · stale figures: {c.stale_total}</p>;
}

export function Executive({ s }: { s: Summary }) {
  const x = execView(s);
  const c = x.comp;
  const mark = ({ good: "✓", warn: "!", bad: "✕" } as Record<string, string>)[x.tone];
  const list = (items: string[], empty: string) => <ul className="plain">{(items.length ? items : [empty]).map((i) => <li key={i}>{i}</li>)}</ul>;
  return (
    <>
      <section className="entry" data-r aria-labelledby="exec-h">
        <header><h2 id="exec-h">At a glance, in plain English</h2><span className="note">read this first</span></header>
        <div className="body">
          <h3>What this means</h3>
          <p><span className={`tag stance-tag${x.directional ? "" : " neutral"}`}>{x.label}</span> {x.meaning}</p>
          <h3>What is missing</h3>{list(x.missing, "nothing flagged")}
          <h3>What to monitor</h3>{list(x.monitor, "nothing specific flagged")}
        </div>
      </section>
      {c && (
        <section className="entry" data-r aria-labelledby="comp-h">
          <header><h2 id="comp-h">Data completeness</h2><span className="note">{c.level}</span></header>
          <div className="body">
            <p><span className={`light ${x.tone}`}><span aria-hidden="true">{mark}</span> {c.level}</span> overall coverage {Math.round(c.overall_coverage_pct)}% · stale figures: {c.stale_total}</p>
            <p className="helper">{c.reason}</p>
            <ul className="plain pillars">{x.pills.map((p) => <li key={p.label}>{p.label}: {Math.round(p.pct)}%</li>)}</ul>
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
  return (
    <section className="entry" data-r aria-labelledby="peer-h">
      <header><h2 id="peer-h">Peer comparison</h2><span className="note">{p.n_peers} peers used</span></header>
      <div className="body">
        {p.unavailable_reason ? <p>No peer comparison: {p.unavailable_reason}.</p> : (
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
        <p className="stance"><span className={`tag stance-tag${hasDir ? "" : " neutral"}`}>{d.stance.label}</span> {hasDir ? `Confidence ${d.stance.confidence}. ` : "Partial research snapshot; no rating is given. "}{d.stance.reason}.</p>
        <p className="helper">Educational rating from a transparent rule applied to the evidence on this page. It ignores your own situation, is not a prediction, and is not a recommendation.</p>
      </div>
    </section>
  );
}

export function News({ s }: { s: Summary }) {
  if (!s.news || s.news.length === 0) return null;
  return (
    <section className="entry" data-r aria-labelledby="news-h">
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

const REASONS = 3;
export function AtAGlance({ s, onTab }: { s: Summary; onTab: (t: string) => void }) {
  const st = s.debate?.stance;
  const pass = s.checklist.filter((c) => c.result === "pass").length;
  const known = s.checklist.filter((c) => c.result !== "unavailable").length;
  const bull = s.debate?.bull.slice(0, REASONS) ?? [];
  const bear = s.debate?.bear.slice(0, REASONS) ?? [];
  return (
    <section className="glance" data-r aria-labelledby="glance-h">
      <h2 id="glance-h" className="sr">At a glance</h2>
      <div className="glance-row">
        <div><span className="glance-k">Educational rating</span><strong className="glance-v">{st ? st.label : "No rating"}</strong><span className="glance-s">{st ? (execView(s).directional ? `${st.confidence} confidence. A rule-based reading, not advice.` : "Partial snapshot: no rating given.") : "Not enough data."}</span></div>
        <div><span className="glance-k">Score in pool</span><strong className="glance-v">{s.score?.overall != null ? `${s.score.overall.toFixed(0)}/100` : "n/a"}</strong><span className="glance-s">{s.score?.rank ? `rank ${s.score.rank} of ${s.score.n}${(s.score.n ?? 99) < 12 ? " (small set: unstable)" : ""}` : "not scored"}</span></div>
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

export function Ownership({ s }: { s: Summary }) {
  const o = s.ownership;
  if (!o) return null;
  return (
    <section className="entry" data-r aria-labelledby="own-h">
      <header><h2 id="own-h">Who owns it</h2><span className="note">{o.source === "official" ? `NSE filing, as on ${o.as_on}` : "vendor estimate"}</span></header>
      <div className="body">
        {o.rows.length === 0 ? <p>No ownership data this run.</p> : (
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
        {o.source !== "official" && <p className="helper" style={{ marginTop: "var(--space-sm)" }}>{o.how_to}</p>}
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
