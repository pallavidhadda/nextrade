// Calls the user's own model straight from the browser. The key lives in component state only: never stored,
// never put in a URL, never sent to NexTrade's servers. Only the digest (public facts) goes to the provider.
export type Provider = "gemini" | "anthropic" | "openai";

export type OwnModel = { provider: Provider; model: string; baseUrl: string; apiKey: string };

export const DEFAULT_MODELS: Record<Provider, string> = { gemini: "gemini-3.1-flash-lite", anthropic: "claude-haiku-5-5", openai: "" };

// What the person picks. Three wire formats cover everything: Gemini, Anthropic, and the OpenAI chat-completions
// format that OpenRouter, Ollama, LM Studio, Groq, vLLM, LiteLLM, Together and most gateways speak.
export type Preset = { id: string; label: string; provider: Provider; baseUrl: string; model: string; modelHint: string; keyNeeded: boolean; note?: string };

export const PRESETS: Preset[] = [
  { id: "gemini", label: "Gemini", provider: "gemini", baseUrl: "", model: DEFAULT_MODELS.gemini, modelHint: "gemini-3.1-flash-lite", keyNeeded: true },
  { id: "anthropic", label: "Claude", provider: "anthropic", baseUrl: "", model: DEFAULT_MODELS.anthropic, modelHint: "claude-haiku-5-5", keyNeeded: true },
  { id: "openai", label: "OpenAI", provider: "openai", baseUrl: "https://api.openai.com/v1", model: "", modelHint: "the model id from your OpenAI account", keyNeeded: true },
  { id: "openrouter", label: "OpenRouter", provider: "openai", baseUrl: "https://openrouter.ai/api/v1", model: "", modelHint: "vendor/model, for example google/gemma-3-27b-it", keyNeeded: true },
  { id: "ollama", label: "Ollama (on your computer)", provider: "openai", baseUrl: "http://localhost:11434/v1", model: "", modelHint: "a model you have pulled, for example gemma3", keyNeeded: false,
    note: "Ollama must allow this page to call it: start it with OLLAMA_ORIGINS set to this site's address." },
  { id: "lmstudio", label: "LM Studio (on your computer)", provider: "openai", baseUrl: "http://localhost:1234/v1", model: "", modelHint: "the model name shown in LM Studio", keyNeeded: false,
    note: "Turn on CORS in LM Studio's local server settings so this page can call it." },
  { id: "groq", label: "Groq", provider: "openai", baseUrl: "https://api.groq.com/openai/v1", model: "", modelHint: "a model id from your Groq console", keyNeeded: true },
  { id: "custom", label: "Any other (OpenAI-compatible)", provider: "openai", baseUrl: "", model: "", modelHint: "the model id your service expects", keyNeeded: false,
    note: "Works with any service that accepts the OpenAI chat-completions format: a gateway, vLLM, LiteLLM, Together, Mistral, a company proxy." },
];

export function destination(m: Pick<OwnModel, "provider" | "baseUrl">): string {
  if (m.provider === "gemini") return "generativelanguage.googleapis.com";
  if (m.provider === "anthropic") return "api.anthropic.com";
  try { return new URL(m.baseUrl).host; } catch { return "(invalid address)"; }
}

export type Completion = { text: string; inTokens?: number; outTokens?: number; truncated?: boolean };

// Models that think first count their reasoning against the output limit, so the limit has to leave room for the JSON itself.
const room = (n: number) => Math.max(n, 2048);

class HttpError extends Error { constructor(public status: number, msg: string) { super(msg); } }

async function post(url: string, headers: Record<string, string>, body: unknown): Promise<any> {
  let r: Response;
  try {
    r = await fetch(url, { method: "POST", headers, body: JSON.stringify(body), credentials: "omit", referrerPolicy: "no-referrer" });
  } catch {
    throw new Error("Could not reach the model provider from the browser. Check the address, your network, or that the provider allows browser calls.");
  }
  if (!r.ok) throw new HttpError(r.status, `The provider answered ${r.status}. Check the key, the model name and your quota.`);   // never echo the body or headers
  return r.json();
}

export async function complete(m: OwnModel, system: string, user: string, maxTokens: number): Promise<Completion> {
  if (m.provider === "gemini") {
    const j = await post(`https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(m.model)}:generateContent`,
      { "x-goog-api-key": m.apiKey, "content-type": "application/json" },
      { systemInstruction: { parts: [{ text: system }] }, contents: [{ role: "user", parts: [{ text: user }] }],
        generationConfig: { maxOutputTokens: room(maxTokens), temperature: 0, responseMimeType: "application/json" } });
    return { text: j.candidates?.[0]?.content?.parts?.[0]?.text ?? "", inTokens: j.usageMetadata?.promptTokenCount, outTokens: j.usageMetadata?.candidatesTokenCount, truncated: j.candidates?.[0]?.finishReason === "MAX_TOKENS" };
  }
  if (m.provider === "anthropic") {
    const j = await post("https://api.anthropic.com/v1/messages",
      { "x-api-key": m.apiKey, "anthropic-version": "2023-06-01", "anthropic-dangerous-direct-browser-access": "true", "content-type": "application/json" },
      { model: m.model, max_tokens: room(maxTokens), temperature: 0, system, messages: [{ role: "user", content: user }] });
    const text = (j.content ?? []).filter((b: any) => b.type === "text").map((b: any) => b.text).join("");
    return { text, inTokens: j.usage?.input_tokens, outTokens: j.usage?.output_tokens, truncated: j.stop_reason === "max_tokens" };
  }
  const base = m.baseUrl.replace(/\/+$/, "");
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (m.apiKey) headers.authorization = `Bearer ${m.apiKey}`;
  const body = { model: m.model, messages: [{ role: "system", content: system }, { role: "user", content: user }], max_tokens: room(maxTokens), temperature: 0 };
  let j: any;
  try {
    j = await post(`${base}/chat/completions`, headers, { ...body, response_format: { type: "json_object" } });
  } catch (err) {
    // Some compatible servers reject response_format; the answer is checked anyway, so ask again without it.
    if (err instanceof HttpError && err.status === 400) j = await post(`${base}/chat/completions`, headers, body);
    else throw err;
  }
  return { text: j.choices?.[0]?.message?.content ?? "", inTokens: j.usage?.prompt_tokens, outTokens: j.usage?.completion_tokens, truncated: j.choices?.[0]?.finish_reason === "length" };
}
