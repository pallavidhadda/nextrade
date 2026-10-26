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
