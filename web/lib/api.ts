import type { Job, Profile } from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8765";

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

async function readError(r: Response): Promise<string> {
  try {
    const body = await r.json();
    const d = body.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d[0]?.msg) return String(d[0].msg).replace(/^Value error, /, "");
  } catch { /* fall through */ }
  return `The service answered ${r.status}.`;
}

export async function submit(ticker: string, profile: Profile): Promise<string> {
  const r = await fetch(`${API_BASE}/api/analyze`, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ ticker, ...profile }),
  }).catch(() => { throw new ApiError("Could not reach the analysis service. Is it running?", 0); });
  if (!r.ok) throw new ApiError(await readError(r), r.status);
  return (await r.json()).job_id as string;
}

export async function poll(jobId: string): Promise<Job> {
  const r = await fetch(`${API_BASE}/api/jobs/${encodeURIComponent(jobId)}`, { cache: "no-store" })
    .catch(() => { throw new ApiError("Lost contact with the analysis service.", 0); });
  if (r.status === 404) throw new ApiError("This result is no longer stored. Run the analysis again.", 404);
  if (!r.ok) throw new ApiError(await readError(r), r.status);
  return r.json();
}

export const reportUrl = (jobId: string) => `${API_BASE}/api/jobs/${encodeURIComponent(jobId)}/report`;
export const reportDownloadUrl = (jobId: string) => `${reportUrl(jobId)}?download=1`;

export type Validated = { explanation: import("./types").Summary["explanation"]; reasons: string[] };

// Sends only the model's answer text. No key, no profile, no holdings.
export async function validate(jobId: string, raw: string, model: string): Promise<Validated> {
  const r = await fetch(`${API_BASE}/api/jobs/${encodeURIComponent(jobId)}/validate`, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ raw, model }), credentials: "omit",
  }).catch(() => { throw new ApiError("Could not reach the analysis service.", 0); });
  if (!r.ok) throw new ApiError(await readError(r), r.status);
  return r.json();
}
