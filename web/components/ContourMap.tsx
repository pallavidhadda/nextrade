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
  /** Terrain rises under the pointer. */
  interactive?: boolean;
};

const L0 = -1.6, DL = 0.16, NL = 30;

// A generated survey: smooth noise terrain that drifts slowly, traced into contour lines by marching squares.
function field(x: number, y: number, t: number): number {
  return (
    Math.sin(x * 1.7 + 0.6 + t) * 0.55 + Math.sin(y * 1.3 + 2.1 - t * 0.8) * 0.5 + Math.sin((x + y) * 2.3 + 4.0 + t * 0.6) * 0.28 +
    Math.sin((x - y * 0.8) * 3.9 + 1.2 - t * 0.5) * 0.14 + Math.cos(x * 0.9 - y * 1.1 + t * 0.4) * 0.4
  );
}

const clamp01 = (k: number) => Math.max(0, Math.min(1, k));
function cssVar(el: Element, name: string, fallback: string) { return getComputedStyle(el).getPropertyValue(name).trim() || fallback; }

export default function ContourMap({ progress = 1, ringX = 0.56, ring = true, intro = true, interactive = true }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  const target = useRef(progress);
  const ringTarget = useRef(ringX);
  const kick = useRef<() => void>(() => {});
  target.current = progress;
  ringTarget.current = ringX;

  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const box = c.parentElement!;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    let shown = intro && !reduce ? 0 : target.current;
    let ringNow = ringTarget.current;
    let colors = { line: "#7fa595", water: "#6aa0b8", accent: "#d6f36b", ink: "#eef2e2" };
    let w = 0, h = 0, cols = 0, rows = 0, step = 10, grid = new Float32Array(0);
    let raf = 0, last = 0, visible = true, running = false;
    let px = -1e4, py = -1e4, tpx = -1e4, tpy = -1e4, hot = 0, hotT = 0;

    const draw = (now: number) => {
      const t = reduce ? 0 : now * 0.00011;
      const sx = 3.1 / cols, sy = 2.6 / rows;
      const R = 190 / step;                       // pointer reach, in cells
      const ci = px / step, cj = py / step;
      for (let j = 0; j < rows; j++) for (let i = 0; i < cols; i++) {
        let v = field(i * sx, j * sy, t);
        if (hot > 0.01) { const dx = i - ci, dy = j - cj, d2 = dx * dx + dy * dy; if (d2 < R * R * 5) v += 1.35 * hot * Math.exp(-d2 / (R * R * 0.9)); }
        grid[j * cols + i] = v;
      }
      const paths: Path2D[] = Array.from({ length: NL }, () => new Path2D());
      for (let j = 0; j < rows - 1; j++) for (let i = 0; i < cols - 1; i++) {
        const a = grid[j * cols + i], b = grid[j * cols + i + 1], cc = grid[(j + 1) * cols + i + 1], d = grid[(j + 1) * cols + i];
        const mn = Math.min(a, b, cc, d), mx = Math.max(a, b, cc, d);
        const k0 = Math.max(0, Math.ceil((mn - L0) / DL)), k1 = Math.min(NL - 1, Math.floor((mx - L0) / DL));
        for (let k = k0; k <= k1; k++) {
          const lv = L0 + k * DL, p = paths[k];
          const pts: number[] = [];
          if ((a < lv) !== (b < lv)) pts.push((i + (lv - a) / (b - a)) * step, j * step);
          if ((b < lv) !== (cc < lv)) pts.push((i + 1) * step, (j + (lv - b) / (cc - b)) * step);
          if ((d < lv) !== (cc < lv)) pts.push((i + (lv - d) / (cc - d)) * step, (j + 1) * step);
          if ((a < lv) !== (d < lv)) pts.push(i * step, (j + (lv - a) / (d - a)) * step);
          if (pts.length >= 4) { p.moveTo(pts[0], pts[1]); p.lineTo(pts[2], pts[3]); }
          if (pts.length === 8) { p.moveTo(pts[4], pts[5]); p.lineTo(pts[6], pts[7]); }
        }
      }
      ctx.clearRect(0, 0, w, h);
      for (let k = 0; k < NL; k++) {
        const a = clamp01((shown * (NL + 2) - k) / 2);
        if (a <= 0) continue;
        const strong = k % 5 === 0, water = k < 4;
        ctx.strokeStyle = water ? colors.water : colors.line;
        ctx.lineWidth = strong ? 1.5 : 0.8;
        ctx.globalAlpha = (strong ? 0.9 : 0.55) * a;
        ctx.stroke(paths[k]);
      }
      const ra = clamp01((shown - 0.7) / 0.3);
      if (ring && ra > 0) {
        const cx = w * ringNow, cy = h * 0.5, r = Math.min(w * 0.095, h * 0.17);
        const rp = new Path2D();
        for (let a = 0; a <= Math.PI * 2 + 0.05; a += 0.1) {
          const rr = r * (1 + 0.16 * Math.sin(a * 3 + 1 + t * 6) + 0.08 * Math.sin(a * 5 - t * 4));
          const x = cx + Math.cos(a) * rr * 1.25, y = cy + Math.sin(a) * rr;
          if (a === 0) rp.moveTo(x, y); else rp.lineTo(x, y);
        }
        rp.closePath();
        ctx.save();
        ctx.globalAlpha = ra; ctx.strokeStyle = colors.accent; ctx.lineWidth = 2.5; ctx.shadowColor = colors.accent; ctx.shadowBlur = 16;
        ctx.stroke(rp);
        ctx.restore();
        if (!reduce) {                              // a slow pulse leaves the ring like a sonar ping
          const f = (now / 3200) % 1;
          ctx.save();
          ctx.translate(cx, cy); ctx.scale(1 + f * 0.45, 1 + f * 0.45); ctx.translate(-cx, -cy);
          ctx.globalAlpha = ra * (1 - f) * 0.5; ctx.strokeStyle = colors.accent; ctx.lineWidth = 1.2 / (1 + f * 0.45);
          ctx.stroke(rp);
          ctx.restore();
        }
        ctx.globalAlpha = ra; ctx.fillStyle = colors.accent;
        ctx.beginPath(); ctx.arc(cx, cy, 3.5, 0, Math.PI * 2); ctx.fill();
        ctx.setLineDash([2, 5]); ctx.strokeStyle = colors.ink; ctx.lineWidth = 1; ctx.globalAlpha = ra * 0.7;
        ctx.beginPath(); ctx.moveTo(w * 0.05, h * 0.92); ctx.lineTo(cx - r * 0.9, cy + r * 0.4); ctx.stroke(); ctx.setLineDash([]);
      }
      ctx.globalAlpha = 1;
    };

    const tick = (now: number) => {
      raf = 0;
      if (!visible || document.hidden) { running = false; return; }
      raf = requestAnimationFrame(tick);
      if (now - last < 33) return;                 // 30 fps is plenty for contours
      const dt = Math.min(0.1, (now - last) / 1000); last = now;
      shown += (target.current - shown) * (1 - Math.exp(-dt * 2.4));
      if (Math.abs(target.current - shown) < 0.002) shown = target.current;
      ringNow += (ringTarget.current - ringNow) * (1 - Math.exp(-dt * 3));
      px += (tpx - px) * (1 - Math.exp(-dt * 9)); py += (tpy - py) * (1 - Math.exp(-dt * 9));
      hot += (hotT - hot) * (1 - Math.exp(-dt * 5));
      draw(now);
    };
    const start = () => { if (reduce) { shown = target.current; ringNow = ringTarget.current; draw(0); return; } if (!running) { running = true; last = 0; raf = requestAnimationFrame(tick); } };
    kick.current = start;

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      w = box.clientWidth; h = box.clientHeight;
      if (!w || !h) return;
      c.width = w * dpr; c.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      step = w > 1100 ? 11 : 9;
      cols = Math.ceil(w / step) + 1; rows = Math.ceil(h / step) + 1;
      grid = new Float32Array(cols * rows);
      colors = {
        line: cssVar(box, "--map-line", colors.line), water: cssVar(box, "--map-water", colors.water),
        accent: cssVar(box, "--map-accent", colors.accent), ink: cssVar(box, "--map-ink", colors.ink),
      };
      start();
      if (reduce) draw(0);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(box);
    const vis = new IntersectionObserver(([e]) => { visible = e.isIntersecting; if (visible) start(); });
    vis.observe(box);
    const onVis = () => { if (!document.hidden) start(); };
    document.addEventListener("visibilitychange", onVis);

    const onMove = (e: PointerEvent) => {
      const r = box.getBoundingClientRect();
      const x = e.clientX - r.left, y = e.clientY - r.top;
      if (x < 0 || y < 0 || x > r.width || y > r.height) { hotT = 0; return; }
      if (hot < 0.02) { px = x; py = y; }
      tpx = x; tpy = y; hotT = 1;
    };
    const onOut = () => { hotT = 0; };
    if (interactive && !reduce) { addEventListener("pointermove", onMove, { passive: true }); document.addEventListener("pointerleave", onOut); }

    return () => {
      ro.disconnect(); vis.disconnect(); cancelAnimationFrame(raf); running = false;
      document.removeEventListener("visibilitychange", onVis);
      removeEventListener("pointermove", onMove); document.removeEventListener("pointerleave", onOut);
    };
  }, [ring, intro, interactive]);

  useEffect(() => { kick.current(); }, [progress, ringX]);

  return <canvas ref={ref} aria-hidden="true" />;
}
