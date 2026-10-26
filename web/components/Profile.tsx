"use client";
import type { Profile } from "@/lib/types";


const GROUPS = [
  { key: "horizon", label: "How long you would hold", options: [{ v: "<1y", text: "Under 1 year" }, { v: "1-3y", text: "1 to 3 years" }, { v: "3-5y", text: "3 to 5 years" }, { v: "5y+", text: "5 years or more" }] },
  { key: "risk_tolerance", label: "Comfort with price swings", options: [{ v: "low", text: "Low" }, { v: "medium", text: "Medium" }, { v: "high", text: "High" }] },
  { key: "risk_capacity", label: "Ability to absorb a loss", options: [{ v: "low", text: "Low" }, { v: "medium", text: "Medium" }, { v: "high", text: "High" }] },
  { key: "experience", label: "Your experience", options: [{ v: "beginner", text: "Beginner" }, { v: "expert", text: "Experienced" }] },
] as const;

export default function ProfileChooser({ value, onChange }: { value: Profile; onChange: (p: Profile) => void }) {
  return (
    <details className="profile">
      <summary>Your profile, optional</summary>
      <p className="helper">Sets which factors weigh more. Skip it and a labelled default is used. Stays in this browser.</p>
      {GROUPS.map((g) => (
        <div className="group" key={g.key} role="group" aria-label={g.label}>
          <span>{g.label}</span>
          <div className="chips">
            {g.options.map((o) => {
              const on = (value as Record<string, string | undefined>)[g.key] === o.v;
              return (
                <button type="button" key={o.v} className="chip" aria-pressed={on}
                  onClick={() => onChange({ ...value, [g.key]: on ? undefined : o.v })}>{o.text}</button>
              );
            })}
          </div>
        </div>
      ))}
    </details>
  );
}
