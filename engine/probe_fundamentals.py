"""One-off probe (runs in GitHub Actions): what free data exists for Stockholm stocks?

1. A full list of Stockholm-listed shares (Nasdaq Nordic), mapped to Yahoo symbols.
2. For a sample, which fundamentals Yahoo returns, how many quarters, and earnings dates/surprises.
Writes probe/probe.json and probe/probe.md.
"""
from __future__ import annotations

import json
import re
import time
import traceback
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

from . import universe as U

OUT = Path("probe")
UA = {"User-Agent": "Mozilla/5.0 (research probe)", "Accept": "application/json, text/plain, */*"}
INFO_KEYS = ["longName", "sector", "industry", "marketCap", "currency", "trailingPE", "forwardPE", "priceToBook",
             "enterpriseToEbitda", "enterpriseToRevenue", "returnOnEquity", "returnOnAssets", "profitMargins",
             "operatingMargins", "debtToEquity", "freeCashflow", "operatingCashflow", "totalDebt", "totalCash",
             "earningsQuarterlyGrowth", "revenueGrowth", "dividendYield", "trailingEps", "bookValue",
             "averageVolume", "sharesOutstanding", "mostRecentQuarter", "lastFiscalYearEnd"]


def nasdaq_list() -> dict:
    """Try a few public Nasdaq Nordic endpoints for the Stockholm share list."""
    tries = {
        "api.nasdaq.com screener": "https://api.nasdaq.com/api/nordic/screener/shares?category=MAIN_MARKET&tableonly=false&market=STO",
        "api.nasdaq.com screener (all)": "https://api.nasdaq.com/api/nordic/screener/shares?tableonly=false&market=STO",
        "nasdaqomxnordic listed companies": "https://www.nasdaqomxnordic.com/shares/listed-companies/stockholm",
    }
    res = {}
    for name, url in tries.items():
        try:
            r = requests.get(url, headers=UA, timeout=30)
            res[name] = {"status": r.status_code, "bytes": len(r.content), "head": r.text[:300]}
            if r.ok and "json" in r.headers.get("content-type", ""):
                res[name]["json"] = r.json()
        except Exception as e:  # noqa: BLE001
            res[name] = {"error": repr(e)}
    return res


def extract_symbols(raw: dict) -> list[dict]:
    """Best effort: pull (symbol, name, segment) rows out of whatever JSON came back."""
    rows = []
    for v in raw.values():
        js = v.get("json")
        if not js:
            continue
        txt = json.dumps(js)
        # generic walk for dicts that look like share rows
        def walk(o):
            if isinstance(o, dict):
                keys = {k.lower(): k for k in o}
                if "symbol" in keys and ("fullname" in keys or "name" in keys or "companyname" in keys):
                    rows.append({k: o[k] for k in o if isinstance(o[k], (str, int, float))})
                for x in o.values():
                    walk(x)
            elif isinstance(o, list):
                for x in o:
                    walk(x)
        walk(js)
        if rows:
            break
    return rows


def to_yahoo(sym: str) -> str:
    return re.sub(r"\s+", "-", sym.strip()) + ".ST"


def probe_ticker(t: str) -> dict:
    out = {"ticker": t}
    tk = yf.Ticker(t)
    try:
        info = tk.info or {}
        out["info"] = {k: info.get(k) for k in INFO_KEYS}
        out["info_present"] = sum(info.get(k) is not None for k in INFO_KEYS)
    except Exception as e:  # noqa: BLE001
        out["info_error"] = repr(e)
    for attr in ["quarterly_income_stmt", "quarterly_balance_sheet", "quarterly_cashflow", "income_stmt"]:
        try:
            df = getattr(tk, attr)
            out[attr] = {"periods": [str(c.date()) for c in df.columns] if df is not None and not df.empty else [],
                         "rows": list(df.index[:40]) if df is not None and not df.empty else []}
        except Exception as e:  # noqa: BLE001
            out[attr] = {"error": repr(e)}
    try:
        ed = tk.get_earnings_dates(limit=24)
        if ed is not None and len(ed):
            ed = ed.reset_index()
            out["earnings_dates"] = {"rows": len(ed), "columns": list(map(str, ed.columns)),
                                     "with_reported_eps": int(ed.filter(like="Reported").notna().any(axis=1).sum()),
                                     "first": str(ed.iloc[-1, 0]), "last": str(ed.iloc[0, 0]),
                                     "sample": ed.head(6).astype(str).to_dict("records")}
        else:
            out["earnings_dates"] = {"rows": 0}
    except Exception as e:  # noqa: BLE001
        out["earnings_dates"] = {"error": repr(e)}
    return out


def main():
    OUT.mkdir(exist_ok=True)
    report = {"yfinance": yf.__version__}
    raw = nasdaq_list()
    report["nasdaq_raw"] = {k: {kk: vv for kk, vv in v.items() if kk != "json"} for k, v in raw.items()}
    rows = extract_symbols(raw)
    report["nasdaq_rows"] = len(rows)
    report["nasdaq_sample"] = rows[:5]
    if rows:
        pd.DataFrame(rows).to_csv(OUT / "stockholm_shares_raw.csv", index=False)

    sample = list(U.STOCKS[:20])
    # add a few mid/small caps if the list worked
    if rows:
        symkey = next(k for k in rows[0] if k.lower() == "symbol")
        extra = [to_yahoo(r[symkey]) for r in rows[::max(1, len(rows) // 15)]][:15]
        sample += [e for e in extra if e not in sample]
    report["tickers"] = []
    for t in sample:
        try:
            report["tickers"].append(probe_ticker(t))
        except Exception:  # noqa: BLE001
            report["tickers"].append({"ticker": t, "error": traceback.format_exc()[-500:]})
        time.sleep(1.0)
    (OUT / "probe.json").write_text(json.dumps(report, indent=2, default=str))

    L = ["# Free data probe", "", f"yfinance {yf.__version__}", "", "## Stockholm share list", ""]
    for k, v in report["nasdaq_raw"].items():
        L.append(f"- {k}: {v.get('status', v.get('error'))}, {v.get('bytes', 0)} bytes")
    L += [f"- rows extracted: {len(rows)}", "", "## Yahoo per ticker", "",
          "| Ticker | info fields (of %d) | Q income periods | Q balance periods | annual periods | earnings dates | with reported EPS |" % len(INFO_KEYS),
          "|---|---|---|---|---|---|---|"]
    for t in report["tickers"]:
        ed = t.get("earnings_dates", {})
        L.append(f"| {t['ticker']} | {t.get('info_present', 'err')} | {len(t.get('quarterly_income_stmt', {}).get('periods', []))} | "
                 f"{len(t.get('quarterly_balance_sheet', {}).get('periods', []))} | {len(t.get('income_stmt', {}).get('periods', []))} | "
                 f"{ed.get('rows', 'err')} | {ed.get('with_reported_eps', '–')} |")
    (OUT / "probe.md").write_text("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
