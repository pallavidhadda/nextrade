// Plain-English "how sure is this report" view model. Mirrors indiafacts/render.py exec_view so every surface says the same thing.
import type { Summary } from "./types";

export const SMALL_POOL = 12;
const FACTORS: Record<string, string> = { value: "Value", quality: "Quality", growth: "Growth", momentum: "Momentum", risk: "Risk" };
const fname = (k: string) => FACTORS[k] ?? k.charAt(0).toUpperCase() + k.slice(1);
const inr0 = (v: number) => `₹${Math.abs(v) >= 10 ? Math.round(v).toLocaleString("en-IN") : v.toFixed(2)}`;
const pct0 = (v: number) => `${Math.round(v * 100)}%`;

export function hasDirection(label: string): boolean {
  return !["No rating", "Insufficient evidence"].includes(label);
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

export function execView(s: Summary) {
  const st = s.debate?.stance;
  const label = st?.label ?? "No rating";
  const directional = hasDirection(label);
  const meaning = directional && st
    ? `${label} (confidence ${st.confidence}). ${st.reason.replace(/\.$/, "")}. A rule-based reading of the evidence, not advice.`
    : `Partial research snapshot — no rating: ${st ? st.reason.replace(/\.$/, "") : "no score could be computed"}.`;
  const comp = s.completeness ?? null;
  const pills = comp ? Object.values(comp.pillars).filter((p) => p.coverage_pct !== null).map((p) => ({ label: p.label, pct: p.coverage_pct as number })) : [];
  const missing = [...pills].sort((a, b) => a.pct - b.pct).slice(0, 3).map((p) => `${p.label}: ${Math.round(p.pct)}% covered`);
  const monitor = (s.explanation?.triggers ?? []).slice(0, 3).map((t) => t.text);
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
  const scenarioReason = s.scenario_reason || (!directional ? "no scenario plan: the evidence is not enough for a rating" : "");
  return {
    label, directional, meaning, missing, monitor, tone, rows, sentence, rankNotes, stampLine, scenarioReason, comp, pills, conflicts,
    total: rows.reduce((a, r) => a + r.contribution, 0),
  };
}
