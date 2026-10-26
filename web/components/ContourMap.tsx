"use client";
import { useEffect, useRef } from "react";

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

function draw(canvas: HTMLCanvasElement) {
  const box = canvas.parentElement!;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = box.clientWidth, h = box.clientHeight;
  canvas.width = w * dpr; canvas.height = h * dpr;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);
  const line = cssVar(box, "--color-contour", "#a67c52");
  const water = cssVar(box, "--color-water", "#6b8aa6");
  const accent = cssVar(box, "--color-accent", "#f0803c");
  const ink = cssVar(box, "--color-ink", "#222");
  const step = 7;
  const cols = Math.ceil(w / step) + 1, rows = Math.ceil(h / step) + 1;
  const sx = 3.1 / cols, sy = 2.6 / rows;
  const grid: number[][] = [];
  for (let j = 0; j < rows; j++) { grid.push([]); for (let i = 0; i < cols; i++) grid[j].push(height(i * sx, j * sy)); }
  const levels: number[] = [];
  for (let l = -1.6; l <= 1.7; l += 0.16) levels.push(l);
  levels.forEach((lv, idx) => {
    ctx.beginPath();
    ctx.strokeStyle = lv < -1.0 ? water : line;
    ctx.lineWidth = idx % 5 === 0 ? 1.6 : 0.8;
    ctx.globalAlpha = idx % 5 === 0 ? 0.95 : 0.7;
    for (let j = 0; j < rows - 1; j++) for (let i = 0; i < cols - 1; i++) {
      const a = grid[j][i], b = grid[j][i + 1], c = grid[j + 1][i + 1], d = grid[j + 1][i];
      const pts: [number, number][] = [];
      const lerp = (p: number, q: number) => (lv - p) / (q - p);
      if ((a < lv) !== (b < lv)) pts.push([(i + lerp(a, b)) * step, j * step]);
      if ((b < lv) !== (c < lv)) pts.push([(i + 1) * step, (j + lerp(b, c)) * step]);
      if ((d < lv) !== (c < lv)) pts.push([(i + lerp(d, c)) * step, (j + 1) * step]);
      if ((a < lv) !== (d < lv)) pts.push([i * step, (j + lerp(a, d)) * step]);
      if (pts.length >= 2) { ctx.moveTo(pts[0][0], pts[0][1]); ctx.lineTo(pts[1][0], pts[1][1]); }
      if (pts.length === 4) { ctx.moveTo(pts[2][0], pts[2][1]); ctx.lineTo(pts[3][0], pts[3][1]); }
    }
    ctx.stroke();
  });
  ctx.globalAlpha = 1;
  // the holding: an irregular boundary edged in tangerine, like a title plan
  const cx = w * 0.56, cy = h * 0.46, r = Math.min(w, h) * 0.26;
  ctx.beginPath();
  for (let t = 0; t <= Math.PI * 2 + 0.05; t += 0.12) {
    const rr = r * (1 + 0.16 * Math.sin(t * 3 + 1) + 0.08 * Math.sin(t * 5));
    const x = cx + Math.cos(t) * rr * 1.25, y = cy + Math.sin(t) * rr;
    if (t === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  ctx.closePath();
  ctx.strokeStyle = accent; ctx.lineWidth = 3; ctx.stroke();
  ctx.setLineDash([2, 4]); ctx.strokeStyle = ink; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(w * 0.05, h * 0.9); ctx.lineTo(cx - r, cy + r * 0.3); ctx.stroke();
}

export default function ContourMap() {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    let raf = 0;
    const run = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(() => draw(c)); };
    run();
    const ro = new ResizeObserver(run);
    ro.observe(c.parentElement!);
    return () => { ro.disconnect(); cancelAnimationFrame(raf); };
  }, []);
  return <canvas ref={ref} aria-hidden="true" />;
}
