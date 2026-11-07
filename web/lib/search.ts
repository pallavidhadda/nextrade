import companies from "@/lib/companies.json";

export type Company = { s: string; n: string; i: string };
const ALL = companies as Company[];
const ALIASES: Record<string, string> = {
  sbi: "SBIN", "state bank": "SBIN", airtel: "BHARTIARTL", hul: "HINDUNILVR", unilever: "HINDUNILVR", larsen: "LT", "l&t": "LT",
  kotak: "KOTAKBANK", zomato: "ETERNAL", paytm: "PAYTM", maruti: "MARUTI", "tata motors": "TMPV", infosys: "INFY", jio: "RELIANCE",
};
const STOP = new Set(["ltd", "limited", "the", "of", "india", "and", "corporation", "company", "co", "pvt", "private"]);
const norm = (s: string) => s.toLowerCase().replace(/&/g, " and ").replace(/[^a-z0-9 ]/g, " ").split(/\s+/).filter(Boolean).join(" ");

function lev(a: string, b: string): number {
  const d = Array.from({ length: a.length + 1 }, (_, i) => [i, ...Array(b.length).fill(0)]);
  for (let j = 1; j <= b.length; j++) d[0][j] = j;
  for (let i = 1; i <= a.length; i++)
    for (let j = 1; j <= b.length; j++)
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
  return d[a.length][b.length];
}
const sim = (a: string, b: string) => (a || b ? 1 - lev(a, b) / Math.max(a.length, b.length) : 1);

function score(q: string, c: Company): number {
  const sym = c.s.toLowerCase();
  const name = norm(c.n);
  if (q === sym || q === name) return 1;
  if (name.startsWith(q) || sym.startsWith(q)) return q.length >= 3 ? 0.95 : 0.7;
  if (q.length >= 3 && (name.includes(q) || sym.includes(q))) return 0.85;
  const toks = name.split(" ").filter((t) => !STOP.has(t));
  let best = Math.max(sim(q, name) * 0.95, sim(q, sym) * 0.9, ...toks.map((t) => sim(q, t)));
  if (q.includes(" ") && q.split(" ").every((p) => Math.max(...toks.map((t) => sim(p, t))) >= 0.75)) best = Math.max(best, 0.8);
  return best;
}

/** Companies whose name or symbol resembles what was typed, best first. Tolerates typos such as "infosis". */
export function suggest(raw: string, limit = 5): Company[] {
  const q = norm(raw);
  if (q.length < 2) return [];
  const bySym = new Map(ALL.map((c) => [c.s, c]));
  const scored = new Map<string, number>();
  for (const [k, sym] of Object.entries(ALIASES)) if ((q === k || (q.length >= 3 && k.startsWith(q)) || sim(q, k) >= 0.85) && bySym.has(sym)) scored.set(sym, 0.9);
  for (const c of ALL) { const s = score(q, c); if (s >= 0.62 && s > (scored.get(c.s) ?? 0)) scored.set(c.s, s); }
  return [...scored.entries()].sort((a, b) => b[1] - a[1]).slice(0, limit).map(([s]) => bySym.get(s)!);
}
