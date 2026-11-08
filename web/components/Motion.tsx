"use client";
import { useEffect, useRef } from "react";

/** Page-wide motion: scroll reveals for [data-r], scroll progress (--sp), a soft cursor halo and magnetic buttons. Renders one decorative node. */
export default function Motion() {
  const halo = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = document.documentElement;
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

    // reveals: anything marked data-r fades up once it enters the viewport
    const io = new IntersectionObserver((es) => {
      for (const e of es) if (e.isIntersecting) { (e.target as HTMLElement).classList.add("in"); io.unobserve(e.target); }
    }, { rootMargin: "0px 0px -6% 0px", threshold: 0.06 });
    const seenEls = new WeakSet<Element>();
    const scan = () => document.querySelectorAll<HTMLElement>("[data-r]:not(.in)").forEach((el) => { if (!seenEls.has(el)) { seenEls.add(el); io.observe(el); } });
    scan();
    const mo = new MutationObserver(scan);
    mo.observe(document.body, { childList: true, subtree: true });

    // scroll progress for the thin line under the bar
    let ticking = false;
    const onScroll = () => {
      if (ticking) return; ticking = true;
      requestAnimationFrame(() => {
        const max = root.scrollHeight - innerHeight;
        root.style.setProperty("--sp", String(max > 0 ? Math.min(1, scrollY / max) : 0));
        ticking = false;
      });
    };
    addEventListener("scroll", onScroll, { passive: true });
    onScroll();

    // halo + magnetic: fine pointers only
    const fine = matchMedia("(hover: hover) and (pointer: fine)").matches && !reduce;
    let raf = 0, hx = 0, hy = 0, tx = 0, ty = 0, seen = false;
    let mag: HTMLElement | null = null;
    const h = halo.current;
    const onMove = (e: PointerEvent) => {
      tx = e.clientX; ty = e.clientY;
      if (!seen && h) { seen = true; hx = tx; hy = ty; h.dataset.on = "1"; }
      const t = e.target as Element | null;
      if (h) h.dataset.state = t?.closest("a,button,summary,[role=option],[data-magnetic]") ? "link" : t?.closest("input,textarea") ? "text" : "";
      const m = (t?.closest("[data-magnetic]") as HTMLElement | null) ?? null;
      if (mag && mag !== m) { mag.style.transform = ""; mag = null; }
      if (m) {
        mag = m;
        const r = m.getBoundingClientRect();
        const dx = Math.max(-10, Math.min(10, (e.clientX - (r.left + r.width / 2)) * 0.22));
        const dy = Math.max(-8, Math.min(8, (e.clientY - (r.top + r.height / 2)) * 0.22));
        m.style.transform = `translate(${dx}px, ${dy}px)`;
      }
    };
    const loop = () => {
      hx += (tx - hx) * 0.18; hy += (ty - hy) * 0.18;
      if (h) h.style.transform = `translate3d(${hx}px, ${hy}px, 0)`;
      raf = requestAnimationFrame(loop);
    };
    const onLeave = () => { if (h) h.dataset.on = ""; seen = false; };
    if (fine) { addEventListener("pointermove", onMove, { passive: true }); document.addEventListener("pointerleave", onLeave); raf = requestAnimationFrame(loop); }

    return () => {
      io.disconnect(); mo.disconnect(); removeEventListener("scroll", onScroll);
      if (fine) { removeEventListener("pointermove", onMove); document.removeEventListener("pointerleave", onLeave); cancelAnimationFrame(raf); }
    };
  }, []);

  return <div ref={halo} className="halo" aria-hidden="true"><i /></div>;
}
