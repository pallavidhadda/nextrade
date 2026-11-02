export type Profile = {
  horizon?: "<1y" | "1-3y" | "3-5y" | "5y+";
  risk_tolerance?: "low" | "medium" | "high";
  risk_capacity?: "low" | "medium" | "high";
  experience?: "beginner" | "expert";
};

export type KeyFact = { metric: string; value: number | null; unit: string; period: string; source: string; basis: string; fact_id: string };
export type Check = { label: string; result: "pass" | "fail" | "unavailable"; display: string; threshold: string; reason: string };
export type Gap = { metric: string; period: string; status: string; reason: string };
export type Claim = { type: "fact" | "inference" | "hypothesis"; text: string; ids: string[] };
export type Summary = {
  ticker: string; name: string | null; sector: string | null; industry: string | null; isin: string | null; retrieved_at: string;
  profile: { horizon: string; risk: string; experience: string };
  key_facts: KeyFact[];
  score: null | {
    status: string; overall: number | null; rank: number | null; n: number | null; reason: string; pool: string | null; flags: string[];
    factors: Record<string, { score: number | null; coverage: number; reason: string }>;
  };
  checklist: Check[]; gaps: Gap[]; notices: string[]; changes: string[];
  valuation: null | { method: "reverse_dcf_earnings" | "justified_pb"; assumptions: string; unavailable_reason: string | null; items: { metric: string; value: number | null; unit: string; fact_id: string }[] };
  debate: null | { bull: { text: string; evidence: string }[]; bear: { text: string; evidence: string }[]; stance: { label: string; confidence: string; reason: string } };
  news: { title: string; publisher: string; published: string | null; url: string; sentiment_hint: "positive" | "negative" | "neutral" }[];
  explanation: null | { source: string; summary: string; uncertainty: string; claims: Claim[]; triggers: { text: string; ids: string[] }[]; usage: Record<string, number> };
  llm: null | { system: string; user: string; max_tokens: number; ids: string[]; digest: string };
  disclaimer: string;
};
export type Job = { status: "queued" | "running" | "done" | "error"; progress?: string; summary?: Summary; error?: string };
