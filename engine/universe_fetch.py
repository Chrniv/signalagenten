"""Download the full Stockholm universe (runs in GitHub Actions).

universe/universe.csv            Nasdaq Stockholm main-market shares + Yahoo symbol + today's bid/ask
universe/prices/<sym>.csv.gz     daily OHLCV (raw + adjusted close) since 2005
universe/earnings.csv.gz         Yahoo earnings calendar: report timestamp, EPS estimate, reported EPS, surprise %
universe/manifest.json
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

from .data import safe_name

OUT = Path("universe")
URL = "https://api.nasdaq.com/api/nordic/screener/shares?category=MAIN_MARKET&tableonly=false&market=STO"
UA = {"User-Agent": "Mozilla/5.0 (research)", "Accept": "application/json, text/plain, */*"}


def num(s):
    try:
        return float(str(s).replace(",", ""))
    except ValueError:
        return None


def nasdaq_shares() -> pd.DataFrame:
    js = requests.get(URL, headers=UA, timeout=60).json()
    rows = []

    def walk(o):
        if isinstance(o, dict):
            if "symbol" in o and "fullName" in o:
                rows.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(js)
    df = pd.DataFrame([{
        "symbol": r["symbol"], "name": r.get("fullName"), "sector": r.get("sector"), "isin": r.get("isin"),
        "currency": r.get("currency"), "bid": num(r.get("bidPrice")), "ask": num(r.get("askPrice")),
        "last": num(r.get("lastSalePrice")), "turnover": num(r.get("turnover")),
    } for r in rows]).drop_duplicates("symbol")
    df["yahoo"] = df["symbol"].map(lambda s: re.sub(r"\s+", "-", s.strip()) + ".ST")
    mid = (df["bid"] + df["ask"]) / 2
    df["half_spread_now"] = (df["ask"] - df["bid"]) / 2 / mid
    return df


def download_prices(symbols: list[str], out: Path, start="2005-01-01") -> dict:
    out.mkdir(parents=True, exist_ok=True)
    got = {}
    for k in range(0, len(symbols), 40):
        chunk = symbols[k:k + 40]
        df = yf.download(chunk, start=start, auto_adjust=False, actions=True, group_by="ticker",
                         threads=True, progress=False)
        for s in chunk:
            try:
                d = df[s] if isinstance(df.columns, pd.MultiIndex) else df
            except KeyError:
                continue
            d = d.rename(columns=str.lower).rename(columns={"adj close": "adj_close", "stock splits": "splits"})
            d = d.dropna(subset=["close"])
            if d.empty:
                continue
            d.index = pd.to_datetime(d.index).tz_localize(None)
            d.index.name = "date"
            cols = [c for c in ["open", "high", "low", "close", "adj_close", "volume", "dividends", "splits"] if c in d]
            d[cols].round(5).to_csv(out / f"{safe_name(s)}.csv.gz", compression="gzip")
            got[s] = {"rows": len(d), "first": str(d.index[0].date()), "last": str(d.index[-1].date())}
        time.sleep(2)
    return got


def download_earnings(symbols: list[str]) -> pd.DataFrame:
    frames = []
    for s in symbols:
        try:
            ed = yf.Ticker(s).get_earnings_dates(limit=40)
        except Exception:  # noqa: BLE001
            ed = None
        if ed is not None and len(ed):
            ed = ed.reset_index()
            ed.columns = ["ts", "eps_estimate", "eps_reported", "surprise_pct"][: len(ed.columns)]
            ed["ts"] = ed["ts"].astype(str)
            ed.insert(0, "ticker", s)
            frames.append(ed)
        time.sleep(0.6)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main():
    OUT.mkdir(exist_ok=True)
    uni = nasdaq_shares()
    uni.to_csv(OUT / "universe.csv", index=False)
    syms = uni["yahoo"].tolist()
    print(len(syms), "shares on the list")
    prices = download_prices(syms, OUT / "prices")
    print(len(prices), "with prices")
    earn = download_earnings(list(prices))
    earn.to_csv(OUT / "earnings.csv.gz", index=False, compression="gzip")
    print(len(earn), "earnings rows for", earn["ticker"].nunique() if len(earn) else 0, "tickers")
    (OUT / "manifest.json").write_text(json.dumps({
        "run_utc": datetime.now(timezone.utc).isoformat(), "yfinance": yf.__version__,
        "listed": len(syms), "with_prices": len(prices), "missing_prices": sorted(set(syms) - set(prices)),
        "earnings_rows": len(earn), "earnings_tickers": int(earn["ticker"].nunique()) if len(earn) else 0,
        "prices": prices}, indent=1))


if __name__ == "__main__":
    main()
