/** Plain one- or two-sentence meanings for terms the report uses. Keys are matched case-insensitively against labels. */
export const FACTOR_MEANING: Record<string, string> = {
  value: "How cheap the share is against the others in the pool: price to earnings, price to book, EV/EBITDA and free-cash-flow yield. Higher means cheaper.",
  quality: "How well the business turns money into profit and how safely it is financed: return on equity and on capital, profit margin, debt. Higher is better.",
  growth: "How fast profit and sales grew: against a year earlier and on average over three years. Higher is faster.",
  momentum: "How the share price has moved: one-year return, return against the Nifty 50, distance from the 52-week high. Higher means a stronger recent record.",
  risk: "How bumpy the price has been: volatility, worst fall over three years, and beta against the market. Higher means calmer.",
};

export const TERMS: Record<string, string> = {
  "p/e": "Price to earnings: the share price divided by a year's earnings per share. How many years of current profit the price pays for.",
  "price to earnings": "The share price divided by a year's earnings per share. How many years of current profit the price pays for.",
  "price to book": "Market value divided by the accounting value of shareholders' equity.",
  "price to book value": "Market value divided by the accounting value of shareholders' equity.",
  "return on equity": "A year's profit divided by shareholders' equity: profit earned on the owners' money.",
  "return on assets": "A year's profit divided by everything the company holds. Used for banks, which run on borrowed money.",
  "return on capital employed": "Operating profit divided by the capital tied up in the business (ROCE). It ignores how the company is financed.",
  "ev/ebitda": "Enterprise value (market value plus net debt) divided by operating profit before depreciation. Compares companies with different debt levels.",
  "free cash flow": "Cash from operations minus spending on plant and equipment: the cash left over for owners and lenders.",
  "free cash flow yield": "Free cash flow divided by market value: the cash return at today's price.",
  "net debt to ebitda": "Debt minus cash, divided by a year's operating profit before depreciation: roughly how many years of profit would repay the debt.",
  "interest cover": "Operating profit divided by interest cost: how many times profit covers the interest bill.",
  "debt to equity": "Borrowings divided by shareholders' equity. Not meaningful for banks, whose deposits are their raw material.",
  "gross bad loans (npa)": "Loans that stopped paying for 90 days or more, as a share of all loans (gross non-performing assets). Reported in the bank's standalone results.",
  "net bad loans after provisions": "Bad loans minus the money already set aside for them, as a share of loans.",
  "core capital (cet1)": "Common equity tier 1: the bank's own highest-quality capital against its risk-weighted assets. A cushion for losses.",
  "net interest income to assets": "Interest earned minus interest paid, a year's worth, per rupee of assets. A stand-in for net interest margin.",
  "assets per rupee of equity": "Total assets divided by equity: how much the lender has built on each rupee of its own money.",
  "market value": "Share price times shares outstanding (market capitalisation).",
  "beta": "How much the share has tended to move when the Nifty 50 moves by 1%.",
  "drawdown": "The largest fall from a peak to a later low.",
};

export function meaning(label: string): string | undefined {
  const k = label.trim().toLowerCase();
  return TERMS[k] ?? Object.entries(TERMS).find(([t]) => k.startsWith(t + ",") || k.startsWith(t + " ("))?.[1];
}
