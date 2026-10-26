const CRORE = 1e7;
const LAKH_CRORE = 1e12;

export function formatValue(value: number | null, unit: string): string {
  if (value === null || Number.isNaN(value)) return "n/a";
  if (unit === "INR") {
    const abs = Math.abs(value);
    if (abs >= LAKH_CRORE) return `₹${(value / LAKH_CRORE).toFixed(2)} lakh cr`;
    if (abs >= CRORE) return `₹${Math.round(value / CRORE).toLocaleString("en-IN")} cr`;
    return `₹${value.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
  }
  if (unit === "INR_per_share") return `₹${value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  if (unit === "percent") return `${value.toFixed(2)}%`;
  if (unit === "ratio") return value.toFixed(2);
  return value.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

const LABELS: Record<string, string> = {
  price: "Price", market_cap: "Market value", revenue: "Revenue, latest quarter", net_income: "Net profit, latest quarter",
  eps_diluted: "Earnings per share", pe_ttm: "Price to earnings", pb: "Price to book", roe: "Return on equity", debt_to_equity: "Debt to equity",
};
export const metricLabel = (m: string) => LABELS[m] ?? m.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

export const FACTOR_LABELS: Record<string, string> = {
  value: "Value", quality: "Quality", growth: "Growth", momentum: "Momentum", risk: "Risk",
};
export const factorLabel = (f: string) => FACTOR_LABELS[f] ?? f.replace(/^./, (c) => c.toUpperCase());
