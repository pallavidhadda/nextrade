/** Companies the viewer saved, kept in this browser only (localStorage). Every access is guarded: storage can be missing or blocked. */
const KEY = "nextrade.saved";
const MAX = 20;
export type Saved = { t: string; n: string };

export function loadSaved(): Saved[] {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(v) ? v.filter((x) => x && typeof x.t === "string").slice(0, MAX) : [];
  } catch { return []; }
}

function store(list: Saved[]) {
  try { localStorage.setItem(KEY, JSON.stringify(list.slice(0, MAX))); } catch { /* storage unavailable: keep in memory only */ }
}

export function toggleSaved(item: Saved): Saved[] {
  const cur = loadSaved();
  const next = cur.some((x) => x.t === item.t) ? cur.filter((x) => x.t !== item.t) : [item, ...cur];
  store(next);
  return next;
}

const GUIDE = "nextrade.guide-seen";
export function guideSeen(): boolean {
  try { return localStorage.getItem(GUIDE) === "1"; } catch { return true; }
}
export function markGuideSeen() {
  try { localStorage.setItem(GUIDE, "1"); } catch { /* ignore */ }
}
