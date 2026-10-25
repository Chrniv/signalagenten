"""Synthetic market data in the same file format as data.fetch_all, for tests."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from engine import universe as U
from engine.data import safe_name


def make_ohlc(n, seed, start_px=100.0, drift=0.0003, vol=0.015, cal=None):
    rng = np.random.default_rng(seed)
    r = rng.normal(drift, vol, n)
    close = start_px * np.exp(np.cumsum(r))
    opn = close * np.exp(rng.normal(0, vol / 3, n))
    hi = np.maximum(opn, close) * (1 + np.abs(rng.normal(0, vol / 2, n)))
    lo = np.minimum(opn, close) * (1 - np.abs(rng.normal(0, vol / 2, n)))
    return pd.DataFrame({"open": opn, "high": hi, "low": lo, "close": close, "adj_close": close,
                         "volume": 1e6, "dividends": 0.0, "splits": 0.0}, index=cal)


def write_synthetic(d: Path, n=1500, n_stocks=8) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    cal = pd.bdate_range("2010-01-01", periods=n, name="date")
    files = {}
    for k, t in enumerate(U.STOCKS[:n_stocks]):
        df = make_ohlc(n, k, start_px=50 + 30 * k, cal=cal)
        if k == 1:              # a late listing
            df.iloc[:400] = np.nan
        df.dropna().to_csv(d / f"{safe_name(t)}.csv.gz", compression="gzip")
        files[t] = {"warnings": []}
    for t, seed in [("^OMX", 101), ("^SP500TR", 102)]:
        make_ohlc(n, seed, 1000, cal=cal).to_csv(d / f"{safe_name(t)}.csv.gz", compression="gzip")
        files[t] = {"warnings": []}
    fx = make_ohlc(n, 103, 9.0, drift=0, vol=0.004, cal=cal)
    fx.to_csv(d / f"{safe_name('SEK=X')}.csv.gz", compression="gzip")
    (d / "manifest.json").write_text(json.dumps({"run_utc": "synthetic", "files": files, "failed": {}}))
    return d
