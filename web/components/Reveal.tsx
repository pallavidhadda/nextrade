"use client";
import { useEffect, useState } from "react";
import { factorLabel } from "@/lib/format";
import type { Summary } from "@/lib/types";

/** Counts from 0 to `value` with an exponential ease-out; jumps straight to the value under reduced motion. */
export function CountUp({ value, decimals = 1, ms = 1600 }: { value: number; decimals?: number; ms?: number }) {
  const [v, setV] = useState(value);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { setV(value); return; }
    let raf = 0;
    const t0 = performance.now();
    const tick = (now: number) => {
      const k = Math.min(1, (now - t0) / ms);
      setV(value * (k === 1 ? 1 : 1 - Math.pow(2, -10 * k)));
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    setV(0);
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, ms]);
  return <><span aria-hidden="true">{v.toFixed(decimals)}</span><span className="sr">{value.toFixed(decimals)}</span></>;
}

/** The headline reading: the score as a very large numeral, with its rank in the pool. */
export function ScoreNumber({ s }: { s: Summary }) {
  const sc = s.score;
  if (!sc || sc.overall === null) {
    return <p className="rank">No score for this run{sc?.reason ? `: ${sc.reason}` : ", because the company is not in the comparison pool"}.</p>;
  }
  return (
    <div>
      <p className="reading"><CountUp value={sc.overall} /><small>of 100</small></p>
      <p className="rank">Rank {sc.rank} of {sc.n} in {sc.pool ?? "the pool"}. It orders companies inside this pool and is not absolute quality.</p>
    </div>
  );
}

/** The factors behind the score, drawn in one after another. */
export function ScoreFactors({ s }: { s: Summary }) {
  const sc = s.score;
  if (!sc || sc.overall === null) return null;
  return (
    <div className="factors" aria-label="Score factors">
      {Object.entries(sc.factors).map(([k, f], i) => (
        <div className="factor" key={k}>
          <span>{factorLabel(k)}</span>
          {f.score === null ? <span className="na">Not scored: {f.reason || "not enough data"}</span> : (
            <>
              <div className="bar-track" role="img" aria-label={`${factorLabel(k)} ${f.score.toFixed(0)} of 100`}>
                <div className="bar-fill" style={{ width: `${Math.max(2, f.score)}%`, ["--i" as string]: i }} />
              </div>
              <span className="num">{f.score.toFixed(0)}</span>
            </>
          )}
        </div>
      ))}
    </div>
  );
}
