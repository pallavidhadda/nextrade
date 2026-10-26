// Calls the user's own model straight from the browser. The key lives in component state only: never stored,
// never put in a URL, never sent to NexTrade's servers. Only the digest (public facts) goes to the provider.
export type Provider = "gemini" | "anthropic" | "openai";

export type OwnModel = { provider: Provider; model: string; baseUrl: string; apiKey: string };

export const DEFAULT_MODELS: Record<Provider, string> = { gemini: "gemini-3.1-flash-lite", anthropic: "claude-haiku-5-5", openai: "" };

export function destination(m: Pick<OwnModel, "provider" | "baseUrl">): string {
  if (m.provider === "gemini") return "generativelanguage.googleapis.com";
  if (m.provider === "anthropic") return "api.anthropic.com";
  try { return new URL(m.baseUrl).host; } catch { return "(invalid address)"; }
}

export type Completion = { text: string; inTokens?: number; outTokens?: number };

async function post(url: string, headers: Record<string, string>, body: unknown): Promise<any> {
  let r: Response;
  try {
    r = await fetch(url, { method: "POST", headers, body: JSON.stringify(body), credentials: "omit", referrerPolicy: "no-referrer" });
  } catch {
    throw new Error("Could not reach the model provider from the browser. Check the address, your network, or that the provider allows browser calls.");
  }
  if (!r.ok) throw new Error(`The provider answered ${r.status}. Check the key, the model name and your quota.`);   // never echo the body or headers
  return r.json();
}

export async function complete(m: OwnModel, system: string, user: string, maxTokens: number): Promise<Completion> {
  if (m.provider === "gemini") {
    const j = await post(`https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(m.model)}:generateContent`,
      { "x-goog-api-key": m.apiKey, "content-type": "application/json" },
      { systemInstruction: { parts: [{ text: system }] }, contents: [{ role: "user", parts: [{ text: user }] }],
        generationConfig: { maxOutputTokens: maxTokens, temperature: 0, responseMimeType: "application/json" } });
    return { text: j.candidates?.[0]?.content?.parts?.[0]?.text ?? "", inTokens: j.usageMetadata?.promptTokenCount, outTokens: j.usageMetadata?.candidatesTokenCount };
  }
  if (m.provider === "anthropic") {
    const j = await post("https://api.anthropic.com/v1/messages",
      { "x-api-key": m.apiKey, "anthropic-version": "2023-06-01", "anthropic-dangerous-direct-browser-access": "true", "content-type": "application/json" },
      { model: m.model, max_tokens: maxTokens, temperature: 0, system, messages: [{ role: "user", content: user }] });
    const text = (j.content ?? []).filter((b: any) => b.type === "text").map((b: any) => b.text).join("");
    return { text, inTokens: j.usage?.input_tokens, outTokens: j.usage?.output_tokens };
  }
  const base = m.baseUrl.replace(/\/+$/, "");
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (m.apiKey) headers.authorization = `Bearer ${m.apiKey}`;
  const j = await post(`${base}/chat/completions`, headers,
    { model: m.model, messages: [{ role: "system", content: system }, { role: "user", content: user }], max_tokens: maxTokens, temperature: 0, response_format: { type: "json_object" } });
  return { text: j.choices?.[0]?.message?.content ?? "", inTokens: j.usage?.prompt_tokens, outTokens: j.usage?.completion_tokens };
}
