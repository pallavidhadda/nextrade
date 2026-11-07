"use client";
import { useEffect, useRef } from "react";

type Props = {
  /** 0..1: how many contour lines are drawn. Eases toward the value, so a changing prop animates. */
  progress?: number;
  /** Horizontal position of the boundary ring, as a share of the width. */
  ringX?: number;
  /** Draw the boundary ring once the survey is nearly complete. */
  ring?: boolean;
  /** Start empty and draw in on mount. */
  intro?: boolean;
};

function cssVar(el: Element, name: string, fallback: string) {
  return getComputedStyle(el).getPropertyValue(name).trim() || fallback;
}

// A generated survey: smooth noise terrain traced into contour lines by marching squares.
function height(x: number, y: number): number {
  return (
    Math.sin(x * 1.7 + 0.6) * 0.55 + Math.sin(y * 1.3 + 2.1) * 0.5 + Math.sin((x + y) * 2.3 + 4.0) * 0.28 +
    Math.sin((x - y * 0.8) * 3.9 + 1.2) * 0.14 + Math.cos(x * 0.9 - y * 1.1) * 0.4
  );
}

type Built = { levels: { path: Path2D; water: boolean; strong: boolean }[]; ring: Path2D | null; tie: Path2D | null };

// Geometry is traced once per size; animation frames only stroke cached paths.
function build(w: number, h: number, ringX: number, withRing: boolean): Built {
  const step = 7;
  const cols = Math.ceil(w / step) + 1, rows = Math.ceil(h / step) + 1;
  const sx = 3.1 / cols, sy = 2.6 / rows;
  const grid: number[][] = [];
  for (let j = 0; j < rows; j++) { grid.push([]); for (let i = 0; i < cols; i++) grid[j].push(height(i * sx, j * sy)); }
  const levels: Built["levels"] = [];
  let idx = 0;
  for (let lv = -1.6; lv <= 1.7; lv += 0.16, idx++) {
    const path = new Path2D();
    for (let j = 0; j < rows - 1; j++) for (let i = 0; i < cols - 1; i++) {
      const a = grid[j][i], b = grid[j][i + 1], c = grid[j + 1][i + 1], d = grid[j + 1][i];
      const pts: [number, number][] = [];
      const lerp = (p: number, q: number) => (lv - p) / (q - p);
      if ((a < lv) !== (b < lv)) pts.push([(i + lerp(a, b)) * step, j * step]);
      if ((b < lv) !== (c < lv)) pts.push([(i + 1) * step, (j + lerp(b, c)) * step]);
      if ((d < lv) !== (c < lv)) pts.push([(i + lerp(d, c)) * step, (j + 1) * step]);
      if ((a < lv) !== (d < lv)) pts.push([i * step, (j + lerp(a, d)) * step]);
      if (pts.length >= 2) { path.moveTo(pts[0][0], pts[0][1]); path.lineTo(pts[1][0], pts[1][1]); }
      if (pts.length === 4) { path.moveTo(pts[2][0], pts[2][1]); path.lineTo(pts[3][0], pts[3][1]); }
    }
    levels.push({ path, water: lv < -1.0, strong: idx % 5 === 0 });
  }
  let ring: Path2D | null = null, tie: Path2D | null = null;
  if (withRing) {
    const cx = w * ringX, cy = h * 0.5, r = Math.min(w * 0.5, h) * 0.3;
    ring = new Path2D();
    for (let t = 0; t <= Math.PI * 2 + 0.05; t += 0.12) {
      const rr = r * (1 + 0.16 * Math.sin(t * 3 + 1) + 0.08 * Math.sin(t * 5));
      const x = cx + Math.cos(t) * rr * 1.25, y = cy + Math.sin(t) * rr;
      if (t === 0) ring.moveTo(x, y); else ring.lineTo(x, y);
    }
    ring.closePath();
    tie = new Path2D();
    tie.moveTo(w * 0.05, h * 0.9); tie.lineTo(cx - r, cy + r * 0.3);
  }
  return { levels, ring, tie };
}

const ease = (k: number) => Math.max(0, Math.min(1, k));

export default function ContourMap({ progress = 1, ringX = 0.56, ring = true, intro = true }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  const target = useRef(progress);
  const kick = useRef<() => void>(() => {});
  target.current = progress;

  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const box = c.parentElement!;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let shown = intro && !reduce ? 0 : target.current;
    let built: Built | null = null;
    let colors = { line: "#a67c52", water: "#6b8aa6", accent: "#f0803c", ink: "#222" };
    let w = 0, h = 0, raf = 0, last = 0;

    const paint = () => {
      if (!built) return;
      ctx.clearRect(0, 0, w, h);
      const n = built.levels.length;
      built.levels.forEach((lv, i) => {
        const a = ease((shown * (n + 2) - i) / 2);   // each line fades in as the tide reaches it
        if (a <= 0) return;
        ctx.strokeStyle = lv.water ? colors.water : colors.line;
        ctx.lineWidth = lv.strong ? 1.6 : 0.8;
        ctx.globalAlpha = (lv.strong ? 0.95 : 0.7) * a;
        ctx.stroke(lv.path);
      });
      const ra = ease((shown - 0.7) / 0.3);
      if (built.ring && ra > 0) {
        ctx.globalAlpha = ra;
        ctx.strokeStyle = colors.accent; ctx.lineWidth = 3; ctx.stroke(built.ring);
        if (built.tie) { ctx.setLineDash([2, 4]); ctx.strokeStyle = colors.ink; ctx.lineWidth = 1; ctx.stroke(built.tie); ctx.setLineDash([]); }
      }
      ctx.globalAlpha = 1;
    };

    const tick = (now: number) => {
      const dt = Math.min(64, now - last) / 1000; last = now;
      const diff = target.current - shown;
      if (Math.abs(diff) > 0.002) { shown += diff * (1 - Math.exp(-dt * 2.6)); paint(); raf = requestAnimationFrame(tick); }
      else { shown = target.current; paint(); raf = 0; }
    };
    kick.current = () => {
      if (reduce) { shown = target.current; paint(); return; }
      if (!raf) { last = performance.now(); raf = requestAnimationFrame(tick); }
    };

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = box.clientWidth; h = box.clientHeight;
      if (!w || !h) return;
      c.width = w * dpr; c.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      colors = {
        line: cssVar(box, "--color-contour", colors.line), water: cssVar(box, "--color-water", colors.water),
        accent: cssVar(box, "--color-accent", colors.accent), ink: cssVar(box, "--color-ink", colors.ink),
      };
      built = build(w, h, ringX, ring);
      paint();
      kick.current();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(box);
    return () => { ro.disconnect(); cancelAnimationFrame(raf); raf = 0; };
  }, [ringX, ring, intro]);

  useEffect(() => { kick.current(); }, [progress]);

  return <canvas ref={ref} aria-hidden="true" />;
}
