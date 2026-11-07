"use client";
import { useId, useMemo, useState } from "react";
import { suggest } from "@/lib/search";

type Props = { value: string; onChange: (v: string) => void; error?: string; helpId: string };

/** Text box with a dropdown of matching companies. Forgives typos ("infosis" offers Infosys). Arrow keys, Enter and Escape work. */
export default function TickerBox({ value, onChange, error, helpId }: Props) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const t = value.trim();
  const items = useMemo(() => (t.length >= 2 && !/\.(NS|BO)$/i.test(t) ? suggest(t, 6) : []), [t]);
  const show = open && items.length > 0;

  function choose(i: number) {
    const c = items[i];
    if (!c) return;
    onChange(`${c.s}.NS`);
    setOpen(false);
    setActive(-1);
  }

  function onKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!show) { if (e.key === "ArrowDown" && items.length) { setOpen(true); setActive(0); e.preventDefault(); } return; }
    if (e.key === "ArrowDown") { setActive((a) => (a + 1) % items.length); e.preventDefault(); }
    else if (e.key === "ArrowUp") { setActive((a) => (a <= 0 ? items.length - 1 : a - 1)); e.preventDefault(); }
    else if (e.key === "Enter" && active >= 0) { choose(active); e.preventDefault(); }
    else if (e.key === "Escape") { setOpen(false); setActive(-1); }
  }

  return (
    <div className="field combo">
      <label htmlFor={`${id}-in`}>Company or ticker</label>
      <input
        id={`${id}-in`} name="ticker" value={value} role="combobox" aria-expanded={show} aria-controls={`${id}-list`} aria-autocomplete="list"
        aria-activedescendant={active >= 0 ? `${id}-opt-${active}` : undefined} aria-describedby={helpId} aria-invalid={!!error}
        onChange={(e) => { onChange(e.target.value); setOpen(true); setActive(-1); }} onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)} onKeyDown={onKey}
        autoComplete="off" autoCapitalize="characters" spellCheck={false} placeholder="Company name or ticker"
      />
      {show && (
        <ul className="combo-list" id={`${id}-list`} role="listbox" aria-label="Matching companies">
          {items.map((c, i) => (
            <li key={c.s} id={`${id}-opt-${i}`} role="option" aria-selected={i === active} className={i === active ? "on" : ""}
                onMouseDown={(e) => { e.preventDefault(); choose(i); }} onMouseEnter={() => setActive(i)}>
              <span>{c.n}</span><span className="mono sym">{c.s}.NS</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
