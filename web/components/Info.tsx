"use client";
import { useEffect, useId, useRef, useState } from "react";

/** A small "i" button that explains a term in a sentence or two. Opens on hover, focus or tap; Escape closes. */
export default function Info({ label, children }: { label: string; children: React.ReactNode }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const off = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", off); document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", off); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <span className="info" ref={box} onPointerEnter={(e) => { if (e.pointerType === "mouse") setOpen(true); }} onPointerLeave={(e) => { if (e.pointerType === "mouse") setOpen(false); }}>
      <button type="button" className="info-btn" aria-label={`What is ${label}?`} aria-expanded={open} aria-describedby={open ? id : undefined} onClick={() => setOpen(true)} onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}>
        <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"><circle cx="8" cy="8" r="6.6" /><path d="M8 7.2v4" /><circle cx="8" cy="4.9" r="0.4" fill="currentColor" /></svg>
      </button>
      {open && <span role="tooltip" id={id} className="tip">{children}</span>}
    </span>
  );
}
