"use client";
import { useState } from "react";
import { validate } from "@/lib/api";
import { DEFAULT_MODELS, complete, destination, type Provider } from "@/lib/llm";
import type { Summary } from "@/lib/types";

type Props = { jobId: string; summary: Summary; onExplanation: (e: NonNullable<Summary["explanation"]>) => void };

export default function OwnModelPanel({ jobId, summary, onExplanation }: Props) {
  const [provider, setProvider] = useState<Provider>("gemini");
  const [model, setModel] = useState(DEFAULT_MODELS.gemini);
  const [baseUrl, setBaseUrl] = useState("http://localhost:11434/v1");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const llm = summary.llm;
  const dest = destination({ provider, baseUrl });

  function pick(p: Provider) { setProvider(p); setModel(DEFAULT_MODELS[p]); setMsg(null); }

  async function run(e: React.FormEvent) {
    e.preventDefault();
    if (!llm) return;
    if (!model.trim()) { setMsg({ kind: "err", text: "Enter the model name." }); return; }
    setBusy(true); setMsg(null);
    try {
      const c = await complete({ provider, model: model.trim(), baseUrl, apiKey }, llm.system, llm.user, llm.max_tokens);
      const v = await validate(jobId, c.text, model.trim());
      if (!v.explanation) { setMsg({ kind: "err", text: `Your model's answer failed the checks: ${v.reasons.join("; ") || "unknown reason"}. Nothing was shown from it.` }); return; }
      onExplanation({ ...v.explanation, usage: { in: c.inTokens ?? 0, out: c.outTokens ?? 0 } });
      setMsg({ kind: "ok", text: `Done. ${v.reasons.length ? `${v.reasons.length} claim(s) were removed by the checks.` : "Every claim passed the checks."}` });
    } catch (err) {
      setMsg({ kind: "err", text: err instanceof Error ? err.message : "Something went wrong." });
    } finally {
      setApiKey("");                                   // the key never outlives the request
      setBusy(false);
    }
  }

  if (!llm) return null;
  return (
    <section className="entry" aria-labelledby="own-h">
      <header><h2 id="own-h">Explain with your own model</h2><span className="note">optional</span></header>
      <form className="body" onSubmit={run} autoComplete="off">
        <p className="helper">The facts digest (about {Math.round(llm.user.length / 2.8)} tokens, no personal data) goes from your browser straight to <strong>{dest}</strong>. Your key is used once and cleared. NexTrade&rsquo;s servers never receive it; they only check the answer.</p>
        <div className="chips" role="group" aria-label="Provider" style={{ marginTop: "var(--space-sm)" }}>
          {([["gemini", "Gemini"], ["anthropic", "Anthropic"], ["openai", "OpenAI-compatible"]] as [Provider, string][]).map(([p, label]) => (
            <button key={p} type="button" className="chip" aria-pressed={provider === p} onClick={() => pick(p)}>{label}</button>
          ))}
        </div>
        <div className="row" style={{ marginTop: "var(--space-sm)" }}>
          <div className="field"><label htmlFor="own-model">Model</label><input id="own-model" name="model" value={model} onChange={(e) => setModel(e.target.value)} autoComplete="off" spellCheck={false} /></div>
          {provider === "openai" && <div className="field"><label htmlFor="own-base">Address</label><input id="own-base" name="base" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} autoComplete="off" spellCheck={false} inputMode="url" /></div>}
        </div>
        <div className="row" style={{ marginTop: "var(--space-sm)" }}>
          <div className="field"><label htmlFor="own-key">API key{provider === "openai" ? ", if needed" : ""}</label>
            <input id="own-key" name="own-key" type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} autoComplete="off" autoCapitalize="off" spellCheck={false} data-lpignore="true" data-1p-ignore="true" /></div>
          <button className="key primary" type="submit" disabled={busy || (provider !== "openai" && !apiKey)}>{busy ? "Asking" : "Explain"}</button>
        </div>
        <p className={`helper${msg?.kind === "err" ? " err" : ""}`} role={msg ? "status" : undefined} style={{ marginTop: "var(--space-xs)" }}>{msg?.text ?? ""}</p>
      </form>
    </section>
  );
}
