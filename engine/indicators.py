"""Causal indicators: every value at date t uses only data up to and including t."""
from __future__ import annotations

import pandas as pd


def sma(x: pd.DataFrame | pd.Series, n: int):
    return x.rolling(n, min_periods=n).mean()


def rsi(close: pd.DataFrame | pd.Series, n: int = 2):
    """Wilder RSI."""
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = up / dn
    out = 100 - 100 / (1 + rs)
    return out.where(dn > 0, 100.0).where(up.notna())


def momentum(close, lookback: int, skip: int = 0):
    """Return from t-lookback to t-skip."""
    return close.shift(skip) / close.shift(lookback) - 1


def history_count(close: pd.DataFrame) -> pd.DataFrame:
    return close.notna().cumsum()


def median_turnover(raw_close: pd.DataFrame, volume: pd.DataFrame, n: int = 60):
    return (raw_close * volume).rolling(n, min_periods=n // 2).median()
