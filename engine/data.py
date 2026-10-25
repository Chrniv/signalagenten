"""Download (GitHub Actions) and load (anywhere) daily price data.

Files: data/<safe ticker>.csv.gz with columns
date, open, high, low, close, adj_close, volume, dividends, splits
plus data/manifest.json. Nothing is cleaned silently; warnings go in the manifest.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import universe as U


def safe_name(ticker: str) -> str:
    return ticker.replace("^", "IDX_").replace("=", "_")


# ------------------------------------------------------------------ download
def fetch_all(out_dir: str | Path, start: str = "1995-01-01", pause: float = 0.7) -> dict:
    import yfinance as yf  # only needed where we download

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"run_utc": datetime.now(timezone.utc).isoformat(), "yfinance": yf.__version__,
                "start": start, "files": {}, "failed": {}}
    for t in U.all_tickers():
        try:
            df = yf.Ticker(t).history(start=start, interval="1d", auto_adjust=False,
                                      actions=True, raise_errors=False)
        except Exception as e:  # noqa: BLE001
            manifest["failed"][t] = f"{type(e).__name__}: {e}"
            continue
        if df is None or df.empty:
            manifest["failed"][t] = "no data"
            continue
        df = df.rename(columns=str.lower).rename(columns={"adj close": "adj_close", "stock splits": "splits"})
        df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
        df.index.name = "date"
        df = df[~df.index.duplicated(keep="last")].sort_index()
        keep = [c for c in ["open", "high", "low", "close", "adj_close", "volume", "dividends", "splits"] if c in df]
        df[keep].to_csv(out / f"{safe_name(t)}.csv.gz", compression="gzip")
        manifest["files"][t] = {"rows": len(df), "first": str(df.index[0].date()),
                                "last": str(df.index[-1].date()), "warnings": quality(df)}
        time.sleep(pause)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def quality(df: pd.DataFrame) -> list[str]:
    w = []
    px = df["adj_close"] if "adj_close" in df else df["close"]
    r = px.pct_change(fill_method=None)
    big = r[r.abs() > 0.35]
    if len(big):
        w.append(f"{len(big)} daily moves >35%: " + ", ".join(d.strftime("%Y-%m-%d") for d in big.index[:5]))
    if df[["open", "high", "low", "close"]].isna().any(axis=1).sum():
        w.append("rows with missing OHLC")
    if ((df["open"] <= 0) | (df["close"] <= 0)).any():
        w.append("non-positive prices")
    return w


# ------------------------------------------------------------------ load
def load_ticker(data_dir: str | Path, ticker: str) -> pd.DataFrame | None:
    p = Path(data_dir) / f"{safe_name(ticker)}.csv.gz"
    if not p.exists():
        return None
    df = pd.read_csv(p, index_col="date", parse_dates=True)
    return df if len(df) else None


def adjusted_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    """Total-return-adjusted OHLC (dividends + splits). Open/high/low scaled by adj_close/close."""
    out = pd.DataFrame(index=df.index)
    f = (df["adj_close"] / df["close"]) if "adj_close" in df else 1.0
    for c in ["open", "high", "low", "close"]:
        out[c] = df[c] * f
    # Yahoo sometimes has open == 0 or missing for old Stockholm rows: fall back to close.
    bad_open = ~(out["open"] > 0)
    out.loc[bad_open, "open"] = out.loc[bad_open, "close"]
    out["high"] = out[["high", "open", "close"]].max(axis=1)
    out["low"] = out[["low", "open", "close"]].min(axis=1)
    out["volume"] = df.get("volume", np.nan)
    out["raw_close"] = df["close"]
    return out.dropna(subset=["close"])


class Panel:
    """Wide frames (date x ticker) for each field, on one trading calendar."""

    def __init__(self, frames: dict[str, pd.DataFrame], calendar: pd.DatetimeIndex):
        self.calendar = calendar
        fields = ["open", "high", "low", "close", "volume", "raw_close"]
        self.f = {k: pd.DataFrame({t: df[k] for t, df in frames.items()}).reindex(calendar)
                  for k in fields}
        self.tickers = list(frames)

    def __getattr__(self, k):
        if k in ("open", "high", "low", "close", "volume", "raw_close"):
            return self.f[k]
        raise AttributeError(k)

    def truncate(self, end) -> "Panel":
        """Copy with every price row after `end` removed (used by the look-ahead test)."""
        p = object.__new__(Panel)
        p.calendar = self.calendar
        p.tickers = self.tickers
        p.f = {}
        for k, v in self.f.items():
            v = v.copy()
            v.loc[v.index > end] = np.nan
            p.f[k] = v
        return p


def load_stock_panel(data_dir) -> Panel:
    frames = {}
    for t in U.STOCKS:
        df = load_ticker(data_dir, t)
        if df is not None:
            frames[t] = adjusted_ohlc(df)
    # Calendar = every day on which at least 3 of our stocks traded (the OMXS30 index on Yahoo
    # only starts in 2008, so it can't define the calendar).
    counts = pd.concat([f["close"].notna().rename(t) for t, f in frames.items()], axis=1).sum(axis=1)
    cal = pd.DatetimeIndex(counts[counts >= 3].index).sort_values()
    return Panel(frames, cal)


def fund_series(data_dir) -> tuple[pd.DataFrame, dict]:
    """Daily SEK total-return levels for each fund proxy, on the Swedish calendar.

    Returns (levels, info). Fund fees are NOT deducted here (the simulator does it).
    """
    info = {}
    se_cal = None
    levels = {}
    for key, spec in U.FUND_PROXIES.items():
        chosen = None
        for t in spec["candidates"]:
            df = load_ticker(data_dir, t)
            if df is not None and len(df) > 500:
                chosen = (t, df)
                break
        if chosen is None:
            info[key] = "missing"
            continue
        t, df = chosen
        px = (df["adj_close"] if "adj_close" in df else df["close"]).astype(float)
        is_tr = t.endswith("GI") or t.endswith("TR")
        note = f"{t} ({'total return' if is_tr else 'price index + assumed dividend yield'})"
        if not is_tr:
            daily = (1 + spec["price_index_div_yield"]) ** (1 / 252) - 1
            r = px.pct_change().fillna(0) + daily
            px = (1 + r).cumprod() * px.iloc[0]
        if spec["currency"] != "SEK":
            fx = load_ticker(data_dir, U.FX[spec["currency"]])
            if fx is None:
                info[key] = f"{t} but FX missing"
                continue
            fxc = fx["close"].replace(0, np.nan).ffill()
            # A few early Yahoo FX rows are garbage (e.g. 1.0); drop extreme jumps.
            jump = fxc.pct_change().abs() > 0.2
            fxc = fxc.mask(jump).ffill()
            px = (px * fxc.reindex(px.index).ffill()).dropna()
            note += f" x {U.FX[spec['currency']]}"
        levels[key] = px
        info[key] = note
        if key == "SE_EQ":
            se_cal = px.index
    if se_cal is None:
        raise RuntimeError("No Swedish equity proxy found")
    out = pd.DataFrame({k: v.reindex(se_cal).ffill() for k, v in levels.items()})
    return out.dropna(how="all"), info
