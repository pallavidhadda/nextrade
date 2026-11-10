// Plain-English "how sure is this report" view model. Mirrors indiafacts/render.py exec_view so every surface says the same thing.
import type { Summary } from "./types";

export const SMALL_POOL = 12;
const FACTORS: Record<string, string> = { value: "Value", quality: "Quality", growth: "Growth", momentum: "Momentum", risk: "Risk" };
const fname = (k: string) => FACTORS[k] ?? k.charAt(0).toUpperCase() + k.slice(1);
const inr0 = (v: number) => `₹${Math.abs(v) >= 10 ? Math.round(v).toLocaleString("en-IN") : v.toFixed(2)}`;
const pct0 = (v: number) => `${Math.round(v * 100)}%`;

export function hasDirection(label: string): boolean {
  return !["No rating", "Insufficient evidence"].includes(label);   // the second is a legacy label from older saved summaries
}

export function levelFormula(price: number, last: number | null, stop: number | null, targets: { r: number; price: number }[], notes: string[] = [], mult = 3): string {
  if (last === null || stop === null || stop >= last) return "";
  const held = notes.some((n) => n.includes("held at the 52-week low"));
  if (Math.abs(price - stop) < 0.005) {
    if (held) return `${inr0(stop)} = the 52-week low (the volatility-based stop would sit below it)`;
    return `${inr0(stop)} = last close ${inr0(last)} − ${mult} × average daily move ${inr0((last - stop) / mult)}`;
  }
  const t = targets.find((x) => Math.abs(x.price - price) < 0.005);
  return t ? `${inr0(t.price)} = last close ${inr0(last)} + ${t.r} × the stop distance ${inr0(last - stop)}` : "";
}

const joinAnd = (xs: string[]) => (xs.length === 1 ? xs[0] : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);

type Comp = NonNullable<Summary["completeness"]>;
const LEVEL_WORDS: Record<string, string> = {
  High: "Nearly all the figures we look for were found",
  Medium: "Most figures were found; some are missing",
  Low: "About half the figures are missing",
  Insufficient: "Key figures are missing, so read the rating with care",
};
const AREAS: Record<string, [string, string]> = {
  price_history: ["Price history (returns, 52-week range, volatility)", "the trend and risk readings are limited"],
  fundamentals: ["Company results (sales, profit, earnings per share)", "growth and profitability are hard to judge"],
  valuation: ["Valuation (P/E, price-to-book, market value)", "we can't say whether the price is high or low for what the company earns"],
  balance_sheet: ["Balance sheet (debt, cash, assets)", "we can't judge how much debt the company carries"],
  ownership: ["Ownership (who holds the shares)", ""],
  news: ["News", ""],
};
const SHORT: Record<string, string> = { price_history: "Price history", fundamentals: "Company results", valuation: "Valuation", balance_sheet: "Balance sheet", ownership: "Ownership", news: "News" };
const SKIP = ["filings"];
const REAL_GAP_PCT = 60;

function areaStatus(p: Comp["pillars"][string]): string {
  const pct = p.coverage_pct;
  if (p.vendor_only) return "Vendor estimate only";
  if (pct === null) return "";
  if (pct >= 99.95) return "Complete";
  const n = p.expected_n ?? 0;
  const got = p.fresh_ok ?? Math.round((pct / 100) * n);
  return pct <= 0 ? "Not found" : n ? `Partly found (${got} of ${n})` : "Partly found";
}

function areaItems(comp: Comp | null): [string, string][] {
  if (!comp) return [];
  return Object.entries(comp.pillars).filter(([k]) => !SKIP.includes(k)).map(([k, v]) => [SHORT[k] ?? v.label, areaStatus(v)] as [string, string]).filter(([, st]) => st);
}

function missingItems(comp: Comp | null): string[] {
  if (!comp) return [];
  const rows: [number, string][] = [];
  for (const [k, p] of Object.entries(comp.pillars)) {
    if (SKIP.includes(k) || p.coverage_pct === null) continue;
    const [name, effect] = AREAS[k] ?? [p.label, ""];
    if (p.vendor_only) rows.push([p.coverage_pct - 0.5, k === "ownership" ? "Ownership: only a data vendor's estimate, not the official exchange filing." : `${name}: only a data vendor's estimate.`]);
    else if (p.coverage_pct <= REAL_GAP_PCT) rows.push([p.coverage_pct, `${name}: ${p.coverage_pct <= 0 ? "not available" : "only partly found"}${effect ? `, so ${effect}.` : "."}`]);
  }
  return rows.sort((a, b) => a[0] - b[0]).map((r) => r[1]).slice(0, 4);
}

export function execView(s: Summary) {
  const st = s.debate?.stance;
  const label = st?.label ?? "No rating";
  const directional = hasDirection(label);
  const note = directional ? st?.evidence_note ?? "" : "";
  const insufficient = directional && !!st && (!!st.partial || !!note);
  const why = (st?.reason ?? "").trim().replace(/\.$/, "");
  const meaning = directional && st
    ? `Rule-based rating: ${label}, ${st.confidence.toLowerCase()} confidence.${note ? ` ${note}` : ""}`
    : label === "No rating" && why ? `${why.charAt(0).toUpperCase()}${why.slice(1)}.` : "No rating: the score could not be computed.";
  const comp = s.completeness ?? null;
  const missing = missingItems(comp);
  const items = areaItems(comp);
  // same order as indiafacts/render.py monitor_items: check boundaries, next results date, scenario trigger prices
  const scen = s.scenario;
  const rupees = (v: number) => `₹${v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const monitor = Array.from(new Set([
    ...(s.explanation?.triggers ?? []).map((t) => t.text).filter((t) => !t.startsWith("Needs data")),
    ...(scen?.watch ?? []).filter((w) => w.includes("results are due")),
    ...(scen?.levels ?? []).filter((l) => l.label.toLowerCase().includes("trigger") && l.price != null)
      .map((l) => { const m = (l.meaning ?? "").trim().replace(/\.$/, ""); return `${l.label} at ${rupees(l.price)}${m ? `: ${m}` : ""}`; }),
  ])).slice(0, 4);
  const stale = (comp?.stale_total ?? 0) > 0 ? `${comp!.stale_total} figure${comp!.stale_total === 1 ? " is" : "s are"} out of date` : "";
  const words = LEVEL_WORDS[comp?.level ?? ""] ?? "";
  const verification = comp?.verification?.label ?? "";
  const conflicts = (comp?.conflicts ?? []).map((c) => {
    const base = `${c.metric} (${c.period}): used ${c.chosen.value} from ${c.chosen.source}`
      + (c.alternative ? `; other source ${c.alternative.source} says ${c.alternative.value}` : "; no second value to compare");
    return c.reason ? `${base}. ${c.reason}` : base;
  });
  const tone = ({ High: "good", Medium: "warn", Low: "bad", Insufficient: "bad" } as Record<string, string>)[comp?.level ?? ""] ?? "warn";
  const sc = s.score;
  const rows = Object.entries(sc?.contributions ?? {}).map(([k, c]) => ({ name: fname(k), ...c }));
  const miss = sc?.missing_factors ?? [];
  const sentence = miss.length
    ? `${joinAnd(miss.map((m) => `${fname(m.factor)} (${pct0(m.base_weight)})`))} could not be scored: ${miss.length === 1 ? "its" : "their"} weight moved to the remaining factors.`
    : "";
  const rankNotes: string[] = [];
  const n = sc?.n ?? 0, failed = sc?.pool_failed ?? 0;
  if (sc?.rank && n && n < SMALL_POOL) rankNotes.push(`rank ${sc.rank} of ${n} in a comparison set of ${n} (small: rank is unstable)`);
  if (failed) rankNotes.push(`${failed} of ${n + failed} comparison companies could not be loaded`);
  const sp = s.stamp;
  const stampLine = sp ? `Report ${sp.report_id} · data as of ${sp.as_of} · rules ${sp.params_hash} · build ${sp.commit}${sp.llm_model ? ` · model ${sp.llm_model}` : ""}` : "";
  const scenarioReason = s.scenario_reason || (!directional ? "no scenario plan without a rating" : "");
  return {
    label, directional, insufficient, evidenceNote: note, meaning, missing, monitor, tone, rows, sentence, rankNotes, stampLine, scenarioReason, comp, items, stale, words, verification, conflicts,
    total: rows.reduce((a, r) => a + r.contribution, 0),
  };
}
