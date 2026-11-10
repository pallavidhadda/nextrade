"""Source drift check: is today's Market Lens universe, NSE API list shape and pool_metrics.json still what the code expects?

Compares against a baseline (data/source_schema.json) and against yesterday's published copies. Output is drift_report.json:
{generated_at, status: ok|warning|breaking, checks: [{source, check, field, severity, detail}], disabled_fields}.
Severity: breaking (missing required field, unit jump, row count drop, out-of-range, anchor failure), warning (placeholder, smaller shifts),
info (a known placeholder, or a check that could not run). disabled_fields lists "marketlens.<field>" / "pool_metrics.<metric>"
placeholders that must not be scored that day; marketlens.py reads them via INDIAFACTS_DRIFT_REPORT.

CLI: python -m indiafacts.drift check|summary|issues ...  (stdlib only). Education only; not financial advice."""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

SCHEMA_PATH = Path(__file__).parent / "data" / "source_schema.json"
SOURCES = ("marketlens", "pool_metrics", "nse_api")
RANK = {"info": 0, "warning": 1, "breaking": 2}


def load_schema(path: Path | None = None) -> dict:
    return json.loads((path or SCHEMA_PATH).read_text(encoding="utf-8"))


def _chk(source: str, check: str, field: str | None, severity: str, detail: str) -> dict:
    return {"source": source, "check": check, "field": field, "severity": severity, "detail": detail}


def _isnum(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v


def _median(vals: list[float]) -> float | None:
    vals = [v for v in vals if v > 0]
    return statistics.median(vals) if vals else None


# ---- generic table checks (rows = list of dicts) -------------------------------------------------------------------

def _table_checks(source: str, rows: list[dict], spec: dict, prev: list[dict] | None, th: dict, disabled: list[str],
                  count_null_placeholder: bool) -> list[dict]:
    out: list[dict] = []
    n = len(rows)
    req = spec.get("required") or {}
    req = req if isinstance(req, dict) else {f: "num" for f in req}
    present_min = th["min_present"]
    absent: set[str] = set()
    for f, typ in req.items():
        have = [r[f] for r in rows if f in r]
        if n and len(have) / n < present_min:
            out.append(_chk(source, "required_field", f, "breaking", f"present in {len(have)} of {n} rows (need {present_min:.0%})"))
            absent.add(f)
            continue
        bad = [v for v in have if v is not None and not (_isnum(v) if typ == "num" else isinstance(v, str))]
        if n and len(bad) / n > 1 - present_min:
            out.append(_chk(source, "type", f, "breaking", f"{len(bad)} of {n} rows are not {typ} (e.g. {bad[0]!r})"))
    if n < th["min_rows_for_stats"]:
        return out
    for f, (lo, hi) in (spec.get("ranges") or {}).items():
        vals = [r[f] for r in rows if _isnum(r.get(f))]
        if not vals or f in absent:
            continue
        outside = [v for v in vals if not (lo <= v <= hi)]
        share = len(outside) / len(vals)
        if share > th["range_breaking_share"]:
            out.append(_chk(source, "range", f, "breaking", f"{len(outside)} of {len(vals)} values outside {lo}..{hi} (e.g. {outside[0]})"))
        elif share > th["range_warning_share"]:
            out.append(_chk(source, "range", f, "warning", f"{len(outside)} of {len(vals)} values outside {lo}..{hi} (e.g. {outside[0]})"))
    known = set(spec.get("expected_placeholders") or [])
    for f in spec.get("watch") or []:
        if f in absent or not any(f in r for r in rows):
            continue
        vals = [r.get(f) for r in rows]
        nums = [v for v in vals if _isnum(v)]
        zero_or_null = sum(1 for v in vals if v is None or (_isnum(v) and v == 0)) if count_null_placeholder else sum(1 for v in nums if v == 0)
        mode = Counter(nums).most_common(1)
        mode_n = mode[0][1] if mode else 0
        why = None
        if zero_or_null / n > th["placeholder_share"]:
            why = f"0 or null in {zero_or_null} of {n} rows"
        elif mode_n / n > th["placeholder_share"] and len(nums) / n > th["placeholder_share"]:
            why = f"the single value {mode[0][0]} in {mode_n} of {n} rows"
        if why:
            out.append(_chk(source, "placeholder", f, "info" if f in known else "warning", why + "; not scored today"))
            disabled.append(f"{source}.{f}")
    if prev is not None:
        for f in spec.get("unit_check") or []:
            a = _median([r[f] for r in rows if _isnum(r.get(f))])
            b = _median([r[f] for r in prev if _isnum(r.get(f))])
            if a and b:
                ratio = a / b
                if ratio > th["unit_jump"] or ratio < 1 / th["unit_jump"]:
                    out.append(_chk(source, "unit_change", f, "breaking", f"median {b:g} yesterday, {a:g} today ({ratio:.2g}x): likely a unit change"))
    return out


def _row_count(source: str, label: str, today: int, yday: int, th: dict) -> list[dict]:
    if yday <= 0:
        return []
    change = (today - yday) / yday
    if change < -th["row_change"]:
        return [_chk(source, "row_count", label, "breaking", f"{yday} yesterday, {today} today ({change:+.0%})")]
    if change > th["row_change"]:
        return [_chk(source, "row_count", label, "warning", f"{yday} yesterday, {today} today ({change:+.0%})")]
    return []


# ---- sources --------------------------------------------------------------------------------------------------------

def _rows_of(ml: dict | None) -> dict[str, dict]:
    rows = (ml or {}).get("rows") if isinstance(ml, dict) else None
    return {k: v for k, v in rows.items() if isinstance(v, dict)} if isinstance(rows, dict) else {}


def check_marketlens(today: dict | None, yesterday: dict | None, schema: dict, anchors: dict[str, float] | None,
                     disabled: list[str]) -> list[dict]:
    """today / yesterday: the marketlens.json shape ({fetched_at, problems, rows: {SYM: row}}). anchors: {SYM: our market cap in INR}."""
    spec, th, src = schema["marketlens"], schema["thresholds"], "marketlens"
    rows_d, prev_d = _rows_of(today), _rows_of(yesterday)
    if not rows_d:
        return [_chk(src, "row_count", "all", "breaking", "no rows in today's Market Lens file")]
    rows, prev = list(rows_d.values()), (list(prev_d.values()) if prev_d else None)
    out = _table_checks(src, rows, spec, prev, th, disabled, count_null_placeholder=True)
    if prev:
        out += _row_count(src, "all sectors", len(rows), len(prev), th)
        t_sec, y_sec = Counter(r.get("sector") for r in rows), Counter(r.get("sector") for r in prev)
        for sec, y in sorted(y_sec.items(), key=lambda kv: str(kv[0])):
            if y >= th["min_sector_rows"] and sec:
                out += _row_count(src, f"sector {sec}", t_sec.get(sec, 0), y, th)
    a_f, b_f = spec.get("holdings_sum") or (None, None)
    if a_f:
        pairs = [(r[a_f], r[b_f]) for r in rows if _isnum(r.get(a_f)) and _isnum(r.get(b_f)) and r[b_f] > 0]
        off = [p for p in pairs if abs(p[0] + p[1] - 100) > th["holdings_tolerance"]]
        if pairs and len(off) / len(pairs) > th["range_warning_share"]:
            out.append(_chk(src, "holdings_sum", f"{a_f}+{b_f}", "warning", f"{len(off)} of {len(pairs)} rows do not sum to 100 +/- {th['holdings_tolerance']}"))
    out += check_anchors(rows_d, anchors, spec.get("anchors") or [], th["anchor_tolerance"])
    return out


def check_anchors(rows: dict[str, dict], ours: dict[str, float] | None, names: list[str], tol: float) -> list[dict]:
    if not ours:
        return [_chk("marketlens", "anchor", None, "info", "anchor check skipped: no reference market caps supplied")]
    out = []
    for sym in names:
        ref = ours.get(sym) or ours.get(sym + ".NS")
        if not _isnum(ref) or ref <= 0:
            continue
        ml = (rows.get(sym) or {}).get("marketCap")
        if not _isnum(ml) or ml <= 0:
            out.append(_chk("marketlens", "anchor", sym, "breaking", f"{sym} market cap missing from Market Lens (ours {ref:.4g})"))
        elif abs(ml / ref - 1) > tol:
            out.append(_chk("marketlens", "anchor", sym, "breaking", f"{sym} market cap {ml:.4g} vs ours {ref:.4g} ({ml / ref - 1:+.1%}, limit {tol:.0%})"))
    return out


def _pool_rows(store: dict | None) -> list[dict]:
    m = (store or {}).get("metrics") if isinstance(store, dict) else None
    if not isinstance(m, dict):
        return []
    return [{k: (v.get("value") if isinstance(v, dict) else None) for k, v in d.items()} for t, d in m.items() if not t.startswith("^") and isinstance(d, dict)]


def check_pool_metrics(today: dict | None, yesterday: dict | None, schema: dict, disabled: list[str]) -> list[dict]:
    spec, th, src = schema["pool_metrics"], schema["thresholds"], "pool_metrics"
    rows, prev = _pool_rows(today), _pool_rows(yesterday)
    if not rows:
        return [_chk(src, "row_count", "all", "breaking", "no companies in today's pool_metrics.json")]
    spec = {**spec, "required": {m: "num" for m in spec.get("required") or []}}
    # a metric a company lacks is simply absent from its row, so "required" asks for 50% coverage here, not 90%
    out = _table_checks(src, rows, spec, prev or None, {**th, "min_present": 0.5}, disabled, count_null_placeholder=False)
    out += _row_count(src, "companies", len(rows), len(prev), th) if prev else []
    return out


def check_nse_api(responses: dict[str, object] | None, schema: dict) -> list[dict]:
    """responses: {endpoint name: parsed JSON}. Each list response must keep its required row fields."""
    out, th = [], schema["thresholds"]
    for name, payload in (responses or {}).items():
        spec = (schema["nse_api"] or {}).get(name)
        if not spec:
            continue
        src = f"nse_api:{name}"
        cont = spec.get("container")
        if cont == "dict":
            rows = [payload] if isinstance(payload, dict) else []
        else:
            rows = payload.get(cont) if cont and isinstance(payload, dict) else payload
        rows = [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
        if not rows:
            out.append(_chk(src, "shape", None, "breaking", "response is empty or no longer a list of records"))
            continue
        for f in spec["required"]:
            have = sum(1 for r in rows if f in r)
            if have / len(rows) < th["min_present"]:
                out.append(_chk(src, "required_field", f, "breaking", f"present in {have} of {len(rows)} rows"))
    return out


# ---- report ---------------------------------------------------------------------------------------------------------

def build_report(marketlens: dict | None = None, marketlens_prev: dict | None = None, pool: dict | None = None, pool_prev: dict | None = None,
                 nse_api: dict | None = None, anchors: dict[str, float] | None = None, schema: dict | None = None,
                 now: datetime | None = None) -> dict:
    schema = schema or load_schema()
    disabled: list[str] = []
    checks: list[dict] = []
    if marketlens is not None:
        checks += check_marketlens(marketlens, marketlens_prev, schema, anchors, disabled)
    if pool is not None:
        checks += check_pool_metrics(pool, pool_prev, schema, disabled)
    if nse_api:
        checks += check_nse_api(nse_api, schema)
    worst = max((RANK[c["severity"]] for c in checks), default=0)
    status = "breaking" if worst == 2 else "warning" if worst == 1 else "ok"
    return {"generated_at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"), "status": status, "checks": checks,
            "disabled_fields": sorted(set(disabled))}


def breaking_sources(report: dict) -> list[str]:
    return sorted({c["source"] for c in report.get("checks", []) if c["severity"] == "breaking"})


def strip_disabled_pool(store: dict, disabled: list[str]) -> dict:
    """Pool metrics that were placeholders today are removed from the published file, so nothing scores them."""
    names = {d.split(".", 1)[1] for d in disabled if d.startswith("pool_metrics.")}
    if not names:
        return store
    metrics = {t: {m: v for m, v in d.items() if m not in names} for t, d in store.get("metrics", {}).items()}
    return {**store, "metrics": metrics}


def disabled_marketlens_fields(report_path: str | Path | None) -> frozenset[str]:
    """Market Lens field names to ignore today, from a drift_report.json (path or file:// URI). Never raises."""
    try:
        p = str(report_path or "")
        if not p:
            return frozenset()
        if p.startswith("file:"):
            from urllib.parse import unquote, urlparse
            p = unquote(urlparse(p).path)
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        return frozenset(x.split(".", 1)[1] for x in d.get("disabled_fields", []) if x.startswith("marketlens."))
    except Exception:
        return frozenset()


# ---- issues and summary ---------------------------------------------------------------------------------------------

# ---- gaps per report ------------------------------------------------------------------------------------------------
GAPS_MANY = 5                 # a report with more gaps than this counts as thin
GAPS_MEDIAN_RISE = 2          # median gaps per report up by this much since yesterday: breaking (opens an issue)
GAPS_SHARE_RISE = 0.10        # share of thin reports up by this much since yesterday: breaking


def gap_stats(summaries: dict[str, dict]) -> dict:
    """{reports, median, p90, max, share_over, over, worst: [[ticker, n]], top_metrics: [[metric, reports]]} from report summaries."""
    counts = {t: len(s.get("gaps") or []) for t, s in summaries.items()}
    vals = sorted(counts.values())
    if not vals:
        return {"reports": 0}
    by_metric: dict[str, int] = {}
    for s in summaries.values():
        for m in {g.get("metric") for g in s.get("gaps") or [] if isinstance(g, dict)}:
            by_metric[m] = by_metric.get(m, 0) + 1
    over = sum(1 for v in vals if v > GAPS_MANY)
    return {"reports": len(vals), "median": float(statistics.median(vals)), "p90": float(vals[min(len(vals) - 1, int(0.9 * len(vals)))]),
            "max": vals[-1], "over": GAPS_MANY, "share_over": round(over / len(vals), 4),
            "worst": [[t, n] for t, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]],
            "top_metrics": [[m, n] for m, n in sorted(by_metric.items(), key=lambda kv: (-kv[1], kv[0] or ""))[:8]]}


def gap_checks(today: dict, yesterday: dict | None) -> list[dict]:
    """Breaking when the median gaps per report or the share of thin reports rose sharply since yesterday; info otherwise."""
    if not today.get("reports"):
        return []
    line = f"median {today['median']:g} gaps per report, {today['share_over']:.0%} of {today['reports']} reports have more than {GAPS_MANY}"
    if not yesterday or not yesterday.get("reports"):
        return [_chk("reports", "gaps_per_report", None, "info", line + " (no earlier figure)")]
    dm, ds = today["median"] - yesterday["median"], today["share_over"] - yesterday["share_over"]
    was = f"; yesterday median {yesterday['median']:g}, {yesterday['share_over']:.0%} thin"
    if dm >= GAPS_MEDIAN_RISE or ds >= GAPS_SHARE_RISE:
        return [_chk("reports", "gaps_per_report", None, "breaking", line + was)]
    return [_chk("reports", "gaps_per_report", None, "info", line + was)]


def add_gap_stats(report: dict, summaries: dict[str, dict], yesterday: dict | None) -> dict:
    """The drift report with `gaps` (today's stats) and a gaps_per_report check; status recomputed."""
    stats = gap_stats(summaries)
    checks = [c for c in report.get("checks", []) if c.get("check") != "gaps_per_report"] + gap_checks(stats, yesterday)
    worst = max((RANK[c["severity"]] for c in checks), default=0)
    return {**report, "checks": checks, "gaps": stats, "status": "breaking" if worst == 2 else "warning" if worst == 1 else "ok"}


def issue_title(source: str) -> str:
    return f"Source drift: {source}"


def issue_body(source: str, report: dict, run_url: str = "") -> str:
    rows = [c for c in report.get("checks", []) if c["source"] == source and c["severity"] in ("breaking", "warning")]
    kept = ("The reports were published; look at which figures went missing (top metrics below) and which source stopped supplying them."
            if source == "reports" else "Yesterday's published file was kept; scores keep using it until this is fixed.")
    lines = [f"The daily drift check found a breaking change in `{source}` ({report.get('generated_at', '')}).", kept, "",
             "| severity | check | field | detail |", "| --- | --- | --- | --- |"]
    for c in sorted(rows, key=lambda c: -RANK[c["severity"]]):
        lines.append(f"| {c['severity']} | {c['check']} | {c.get('field') or ''} | {str(c['detail']).replace('|', '/')} |")
    if report.get("disabled_fields"):
        lines += ["", "Fields not scored today: " + ", ".join(report["disabled_fields"])]
    if source == "reports" and (report.get("gaps") or {}).get("reports"):
        g = report["gaps"]
        lines += ["", "Most-missing figures: " + ", ".join(f"{m} ({n})" for m, n in g.get("top_metrics", [])),
                  "Thinnest reports: " + ", ".join(f"{t} ({n})" for t, n in g.get("worst", []))]
    if run_url:
        lines += ["", f"Run: {run_url}"]
    return "\n".join(lines)


def issue_plan(report: dict, run_url: str = "") -> list[tuple[str, str]]:
    return [(issue_title(s), issue_body(s, report, run_url)) for s in breaking_sources(report)]


def run_issues(report: dict, dry_run: bool = False, run_url: str = "", run: Callable = subprocess.run, log=print) -> int:
    """Open, or comment on, one GitHub issue per breaking source, deduplicated by exact title. Uses `gh` with GH_TOKEN."""
    for title, body in issue_plan(report, run_url):
        if dry_run:
            log(f"[dry run] would open or update issue: {title}\n{body}\n")
            continue
        found = run(["gh", "issue", "list", "--state", "open", "--search", f'"{title}" in:title', "--json", "number,title"],
                    capture_output=True, text=True)
        existing = [i for i in (json.loads(found.stdout or "[]") if found.returncode == 0 else []) if i.get("title") == title]
        if existing:
            run(["gh", "issue", "comment", str(existing[0]["number"]), "--body", body], check=True)
            log(f"updated issue #{existing[0]['number']}: {title}")
        else:
            run(["gh", "issue", "create", "--title", title, "--body", body], check=True)
            log(f"opened issue: {title}")
    return 0


def summary_markdown(report: dict) -> str:
    lines = [f"### Source drift: {report.get('status', 'unknown')}", ""]
    rows = [c for c in report.get("checks", []) if c["severity"] != "info"]
    if not rows:
        lines.append("No drift found.")
    for c in rows:
        lines.append(f"- **{c['severity']}** {c['source']} / {c['check']}" + (f" / {c['field']}" if c.get("field") else "") + f": {c['detail']}")
    if report.get("disabled_fields"):
        lines.append("\nNot scored today: " + ", ".join(report["disabled_fields"]))
    g = report.get("gaps") or {}
    if g.get("reports"):
        lines += ["", f"### Gaps per report: median {g['median']:g}, 90th percentile {g['p90']:g}, max {g['max']}, "
                      f"{g['share_over']:.0%} of {g['reports']} reports have more than {g['over']}",
                  "Most-missing figures: " + ", ".join(f"{m} ({n})" for m, n in g.get("top_metrics", []))]
    return "\n".join(lines) + "\n"


# ---- CLI ------------------------------------------------------------------------------------------------------------

def _load(path: str | None) -> dict | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")) if path else None
    except (OSError, ValueError):
        return None


def load_nse_dir(path: str | None) -> dict:
    out: dict = {}
    for f in sorted(Path(path).glob("nse_*.json")) if path else []:
        name = f.stem.removeprefix("nse_").rsplit("_", 1)[0]
        d = _load(str(f))
        if d is not None:
            out[name] = d
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m indiafacts.drift", description="Source drift check (education only).")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--marketlens"), c.add_argument("--marketlens-prev"), c.add_argument("--pool"), c.add_argument("--pool-prev")
    c.add_argument("--nse-dir", help="folder of nse_<endpoint>_<SYMBOL>.json samples"), c.add_argument("--out", default="drift_report.json")
    sub.add_parser("summary").add_argument("report")
    i = sub.add_parser("issues")
    i.add_argument("report"), i.add_argument("--dry-run", action="store_true"), i.add_argument("--run-url", default="")
    a = p.parse_args(argv)
    if a.cmd == "check":
        rep = build_report(_load(a.marketlens), _load(a.marketlens_prev), _load(a.pool), _load(a.pool_prev), load_nse_dir(a.nse_dir))
        Path(a.out).write_text(json.dumps(rep, indent=1), encoding="utf-8")
        print(summary_markdown(rep))
        return 0
    rep = _load(a.report) or {}
    if a.cmd == "summary":
        print(summary_markdown(rep))
        return 0
    return run_issues(rep, a.dry_run, a.run_url)


if __name__ == "__main__":
    sys.exit(main())
