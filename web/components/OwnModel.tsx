"use client";
import { useState } from "react";
import { validate } from "@/lib/api";
import { DEFAULT_MODELS, complete, destination, type Provider } from "@/lib/llm";
import type { PanelResult, Summary } from "@/lib/types";
import Info from "@/components/Info";

type Mode = "debate" | "panel" | "single";

type Props = { jobId: string; summary: Summary; onExplanation: (e: NonNullable<Summary["explanation"]>) => void; onPanel: (r: PanelResult[]) => void };

export default function OwnModelPanel({ jobId, summary, onExplanation, onPanel }: Props) {
  const [mode, setMode] = useState<Mode>(summary.llm?.debate?.length ? "debate" : "single");
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
      const steps = mode === "panel" ? llm.roles?.map((r) => ({ ...r, uses_notes: r.id === "manager" })) : mode === "debate" ? llm.debate : undefined;
      if (steps?.length) {
        const cfg = { provider, model: model.trim(), baseUrl, apiKey };
        const out: PanelResult[] = [];
        let notes = "";
        for (const role of steps) {
          const isManager = role.uses_notes;
          if (isManager && !notes) { out.push({ id: role.id, title: role.title, explanation: null, error: "no analyst produced a valid note to combine" }); break; }
          const user = isManager
            ? `DIGEST:\n${llm.digest}\n\nANALYST NOTES (already checked against the digest):\n${notes}\n\nWrite the JSON now.`
            : `DIGEST:\n${llm.digest}\n\nWrite the JSON now.`;
          setMsg({ kind: "ok", text: `Asking the ${role.title.toLowerCase()}...` });
          try {
            const c = await complete(cfg, role.system, user, 600);
            const v = await validate(jobId, c.text, model.trim());
            if (v.explanation) {
              out.push({ id: role.id, title: role.title, explanation: v.explanation, error: "" });
              const ex = v.explanation;
              notes += `- ${role.title}: ${ex.summary} ` + ex.claims.slice(0, 3).map((x) => `[${x.ids.join(", ")}] ${x.text}`).join(" ") + "\n";
            } else out.push({ id: role.id, title: role.title, explanation: null, error: `answer failed the checks: ${v.reasons.slice(0, 2).join("; ")}` });
          } catch (err) {
            out.push({ id: role.id, title: role.title, explanation: null, error: err instanceof Error ? err.message : "the model call failed" });
          }
          onPanel([...out]);
        }
        setMsg({ kind: "ok", text: `Done. ${out.filter((r) => r.explanation).length} of ${out.length} answers passed the checks.` });
        return;
      }
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
  const modes: { id: Mode; title: string; calls: number; ok: boolean; what: string }[] = [
    { id: "debate", title: "Bull vs bear debate", calls: llm.debate?.length ?? 3, ok: !!llm.debate?.length, what: "Three AI calls in a row. A bull advocate argues the case in favour, a bear advocate answers point by point and argues against, then a referee weighs both and says what is still uncertain. Each answer is checked against the facts before it is shown." },
    { id: "panel", title: "Analyst panel", calls: llm.roles?.length ?? 6, ok: !!llm.roles?.length, what: "Five analysts each read the same facts from one angle: fundamentals, price and momentum, ownership and flows, news, and risk. A research manager then combines their notes into one balanced reading. Each answer is checked against the facts." },
    { id: "single", title: "One explanation", calls: 1, ok: true, what: "A single AI call that rewrites the plain-English summary in your model's own words. It replaces the template summary on the Summary tab." },
  ];
  const chosen = modes.find((m) => m.id === mode)!;
  return (
    <section className="entry" data-r aria-labelledby="own-h">
      <header><h2 id="own-h">Run an AI analysis</h2><span className="note">your key, your model</span></header>
      <form className="body ai" onSubmit={run} autoComplete="off">
        <fieldset className="modes">
          <legend>What should the AI do?</legend>
          {modes.map((m) => (
            <div className={`mode${mode === m.id ? " on" : ""}${m.ok ? "" : " off"}`} key={m.id}>
              <label>
                <input type="radio" name="ai-mode" value={m.id} checked={mode === m.id} disabled={!m.ok} onChange={() => setMode(m.id)} />
                <span className="radio" aria-hidden="true" />
                <span className="mt">{m.title}</span>
                <span className="calls num">{m.calls} {m.calls === 1 ? "call" : "calls"}</span>
              </label>
              <Info label={m.title}>{m.what}</Info>
            </div>
          ))}
        </fieldset>
        <p className="helper mode-what" aria-live="polite">{chosen.what}</p>
        <p className="helper">The facts digest (about {Math.round(llm.user.length / 2.8)} tokens, no personal data) goes from your browser straight to <strong>{dest}</strong>. Your key is used once and cleared. NexTrade&rsquo;s servers never receive it; they only check the answer.</p>
        <div className="chips" role="group" aria-label="Provider" style={{ marginTop: "var(--space-md)" }}>
          {([["gemini", "Gemini"], ["anthropic", "Anthropic"], ["openai", "OpenAI-compatible"]] as [Provider, string][]).map(([p, label]) => (
            <button key={p} type="button" className="chip" aria-pressed={provider === p} onClick={() => pick(p)}>{label}</button>
          ))}
        </div>
        <div className="row" style={{ marginTop: "var(--space-md)" }}>
          <div className="field"><label htmlFor="own-model">Model</label><input id="own-model" name="model" value={model} onChange={(e) => setModel(e.target.value)} autoComplete="off" spellCheck={false} /></div>
          {provider === "openai" && <div className="field"><label htmlFor="own-base">Address</label><input id="own-base" name="base" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} autoComplete="off" spellCheck={false} inputMode="url" /></div>}
        </div>
        <div className="row" style={{ marginTop: "var(--space-sm)" }}>
          <div className="field"><label htmlFor="own-key">API key{provider === "openai" ? ", if needed" : ""}</label>
            <input id="own-key" name="own-key" type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} autoComplete="off" autoCapitalize="off" spellCheck={false} data-lpignore="true" data-1p-ignore="true" /></div>
          <button className="key primary" type="submit" disabled={busy || (provider !== "openai" && !apiKey)}><span>{busy ? "Asking" : mode === "debate" ? "Run the debate" : mode === "panel" ? "Run the panel" : "Explain"}</span></button>
        </div>
        <p className={`helper${msg?.kind === "err" ? " err" : ""}`} role={msg ? "status" : undefined} style={{ marginTop: "var(--space-xs)" }}>{msg?.text ?? ""}</p>
      </form>
    </section>
  );
}
