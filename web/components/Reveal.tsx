"use client";
import { useEffect, useRef, useState } from "react";
import { factorLabel } from "@/lib/format";
import type { Summary } from "@/lib/types";

/** Counts from 0 to `value` with an exponential ease-out; jumps straight to the value under reduced motion. */
export function CountUp({ value, decimals = 1, ms = 1800, delay = 350 }: { value: number; decimals?: number; ms?: number; delay?: number }) {
  const [v, setV] = useState(value);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { setV(value); return; }
    let raf = 0;
    setV(0);
    const t0 = performance.now() + delay;
    const tick = (now: number) => {
      const k = Math.max(0, Math.min(1, (now - t0) / ms));
      setV(value * (k === 1 ? 1 : 1 - Math.pow(2, -10 * k)));
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, ms, delay]);
  return <><span aria-hidden="true">{v.toFixed(decimals)}</span><span className="sr">{value.toFixed(decimals)}</span></>;
}

/** A headline whose words rise out of a mask one after another. Wrap a word in *asterisks* for the italic accent. */
export function SplitWords({ text, as: Tag = "span", base = 0, step = 70, className }: { text: string; as?: "h1" | "h2" | "p" | "span"; base?: number; step?: number; className?: string }) {
  const words = text.split(" ");
  return (
    <Tag className={`split${className ? ` ${className}` : ""}`} aria-label={text.replace(/\*/g, "")}>
      {words.map((w, i) => {
        const em = w.startsWith("*") && w.endsWith("*");
        const label = em ? w.slice(1, -1) : w;
        return <span key={i} aria-hidden="true"><span className="w"><span className={em ? "em" : undefined} style={{ ["--d" as string]: `${base + i * step}ms` }}>{label}</span></span>{i < words.length - 1 ? " " : ""}</span>;
      })}
    </Tag>
  );
}

/** A statement whose words light up as it scrolls through the viewport. */
export function Scrub({ text }: { text: string }) {
  const ref = useRef<HTMLParagraphElement>(null);
  const words = text.split(" ");
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const spans = Array.from(el.querySelectorAll<HTMLElement>(".sw"));
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) { spans.forEach((s) => s.classList.add("on")); return; }
    let raf = 0;
    const update = () => {
      raf = 0;
      const r = el.getBoundingClientRect(), vh = innerHeight;
      const p = Math.max(0, Math.min(1, (vh * 0.82 - r.top) / (r.height + vh * 0.32)));
      const n = Math.round(p * spans.length * 1.08);
      spans.forEach((s, i) => s.classList.toggle("on", i < n));
    };
    const onScroll = () => { if (!raf) raf = requestAnimationFrame(update); };
    update();
    addEventListener("scroll", onScroll, { passive: true }); addEventListener("resize", onScroll);
    return () => { removeEventListener("scroll", onScroll); removeEventListener("resize", onScroll); cancelAnimationFrame(raf); };
  }, []);
  return <p className="scrub" ref={ref} aria-label={text}>{words.map((w, i) => <span className="sw" aria-hidden="true" key={i}>{w} </span>)}</p>;
}

/** The headline reading: the score as a very large numeral, with its rank in the pool. */
export function ScoreNumber({ s }: { s: Summary }) {
  const sc = s.score;
  if (!sc || sc.overall === null) {
    return <p className="rank">No score for this run{sc?.reason ? `: ${sc.reason}` : ", because the company is not in the comparison pool"}.</p>;
  }
  return (
    <div className="readout">
      <p className="reading"><CountUp value={sc.overall} /><small>of 100</small></p>
      <p className="rank">Rank <strong className="num">{sc.rank}</strong> of <strong className="num">{sc.n}</strong> in {sc.pool ?? "the pool"}. It orders companies inside this pool and is not absolute quality.</p>
    </div>
  );
}

/** Smooth path through points (Catmull-Rom to Bezier). */
function smooth(p: [number, number][]): string {
  if (p.length === 0) return "";
  if (p.length === 1) return `M${p[0][0]},${p[0][1]}`;
  let d = `M${p[0][0].toFixed(1)},${p[0][1].toFixed(1)}`;
  for (let i = 0; i < p.length - 1; i++) {
    const p0 = p[i - 1] ?? p[i], p1 = p[i], p2 = p[i + 1], p3 = p[i + 2] ?? p2;
    const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6], c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += ` C${c1[0].toFixed(1)},${c1[1].toFixed(1)} ${c2[0].toFixed(1)},${c2[1].toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`;
  }
  return d;
}

/** The factors drawn as an elevation profile: a ridge line across the five factors, 0 to 100. */
export function ScoreFactors({ s }: { s: Summary }) {
  const sc = s.score;
  const [hover, setHover] = useState<number | null>(null);
  if (!sc || sc.overall === null) return null;
  const entries = Object.entries(sc.factors);
  const W = 640, H = 280, padX = 44, top = 34, base = 224;
  const n = entries.length;
  const xs = (i: number) => padX + (n === 1 ? 0 : (i * (W - 2 * padX)) / (n - 1));
  const ys = (v: number) => base - (v / 100) * (base - top);
  const pts = entries.map(([, f], i) => (f.score === null ? null : ([xs(i), ys(f.score)] as [number, number])));
  const real = pts.filter((p): p is [number, number] => p !== null);
  const line = smooth(real);
  const area = real.length > 1 ? `${line} L${real[real.length - 1][0]},${base} L${real[0][0]},${base} Z` : "";
  return (
    <figure className="profile-chart" aria-label="Score factors as an elevation profile">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={entries.map(([k, f]) => `${factorLabel(k)} ${f.score === null ? "not scored" : f.score.toFixed(0)}`).join(", ")}>
        <defs>
          <linearGradient id="ep-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="var(--color-accent)" stopOpacity="0.38" /><stop offset="1" stopColor="var(--color-accent)" stopOpacity="0" /></linearGradient>
        </defs>
        {[0, 25, 50, 75, 100].map((g) => (
          <g key={g}><line className="ep-grid" x1={padX - 12} x2={W - padX + 12} y1={ys(g)} y2={ys(g)} /><text className="ep-axis" x={4} y={ys(g) + 4}>{g}</text></g>
        ))}
        {area && <path className="ep-area" d={area} fill="url(#ep-fill)" />}
        {line && <path className="ep-line" d={line} pathLength={1} />}
        {entries.map(([k, f], i) => {
          const x = xs(i), p = pts[i];
          return (
            <g key={k} className={`ep-col${hover === i ? " on" : ""}`} style={{ ["--i" as string]: i }} onPointerEnter={() => setHover(i)} onPointerLeave={() => setHover(null)}>
              <rect x={x - 40} y={top - 20} width={80} height={base - top + 60} fill="transparent" />
              {p ? (
                <>
                  <line className="ep-drop" x1={x} x2={x} y1={p[1]} y2={base} />
                  <circle className="ep-dot" cx={x} cy={p[1]} r={5.5} />
                  <text className="ep-val" x={x} y={p[1] - 14} textAnchor="middle">{f.score!.toFixed(0)}</text>
                </>
              ) : (
                <>
                  <circle className="ep-dot hollow" cx={x} cy={base - 14} r={5} />
                  <text className="ep-val na" x={x} y={base - 30} textAnchor="middle">not scored</text>
                </>
              )}
              <text className="ep-lab" x={x} y={base + 30} textAnchor="middle">{factorLabel(k)}</text>
            </g>
          );
        })}
      </svg>
      <ul className="sr">{entries.map(([k, f]) => <li key={k}>{factorLabel(k)}: {f.score === null ? `not scored, ${f.reason || "not enough data"}` : `${f.score.toFixed(0)} of 100`}</li>)}</ul>
    </figure>
  );
}
