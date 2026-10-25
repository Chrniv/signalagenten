"""Strategy rules. Pure decisions from data known at the close of day i.

Stock strategies implement:  prepare(panel) once, then decide(i, positions) -> {ticker: weight}
    positions: {ticker: {"entry_i": int, ...}} as currently held (after any stop exits today)
    returned dict = the FULL desired holdings after tomorrow's trades (empty = all cash).
Fund strategies implement:   targets(levels, calendar) -> pd.Series of target asset per decision date
    ("SE_EQ" | "GLOBAL_EQ" | "CASH"); dates without a decision are absent.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import indicators as I

MIN_HISTORY = 252          # a stock must have a year of data before it can be traded
MIN_TURNOVER_SEK = 5e6     # 60-day median daily turnover


def eligible_mask(panel) -> pd.DataFrame:
    hist = I.history_count(panel.close)
    turn = I.median_turnover(panel.raw_close, panel.volume)
    return (hist >= MIN_HISTORY) & (turn >= MIN_TURNOVER_SEK) & panel.close.notna()


# ======================================================================= stocks
@dataclass
class MeanReversion:
    """S2: buy oversold dips in uptrending large caps, exit on bounce or after N days."""
    rsi_threshold: float = 10.0
    trend_ma: int = 200
    exit_ma: int = 5
    max_days: int = 5
    max_positions: int = 2
    stop: float = 0.08
    name: str = "S2_mean_reversion"
    kind: str = "stock"

    def params(self):
        return {"rsi_threshold": self.rsi_threshold, "trend_ma": self.trend_ma,
                "exit_ma": self.exit_ma, "max_days": self.max_days}

    def prepare(self, panel):
        c = panel.close
        self.c = c.to_numpy()
        self.rsi = I.rsi(c, 2).to_numpy()
        self.trend = I.sma(c, self.trend_ma).to_numpy()
        self.exit = I.sma(c, self.exit_ma).to_numpy()
        self.elig = eligible_mask(panel).to_numpy()
        self.tickers = list(c.columns)

    def decide(self, i, positions):
        keep = {}
        for t, p in positions.items():
            j = self.tickers.index(t)
            held = i - p["entry_i"] + 1
            if np.isnan(self.c[i, j]):
                continue
            if self.c[i, j] > self.exit[i, j] or held >= self.max_days:
                continue
            keep[t] = 1 / self.max_positions
        free = self.max_positions - len(keep)
        if free > 0:
            cand = []
            for j, t in enumerate(self.tickers):
                if t in keep or t in positions or not self.elig[i, j]:
                    continue
                if self.c[i, j] > self.trend[i, j] and self.rsi[i, j] < self.rsi_threshold:
                    cand.append((self.rsi[i, j], t))
            for _, t in sorted(cand)[:free]:
                keep[t] = 1 / self.max_positions
        return keep


@dataclass
class StockMomentum:
    """S3: hold the strongest 12-1 month stocks while the market is above its trend."""
    lookback: int = 252
    skip: int = 21
    market_ma: int = 200
    top_n: int = 2
    name: str = "S3_stock_momentum"
    kind: str = "stock"
    stop: float = 0.0

    def params(self):
        return {"lookback": self.lookback, "skip": self.skip, "market_ma": self.market_ma}

    def prepare(self, panel):
        c = panel.close
        self.mom = I.momentum(c, self.lookback, self.skip).to_numpy()
        self.elig = (eligible_mask(panel) & (I.history_count(c) >= self.lookback + 1)).to_numpy()
        # Market filter: equal-weight index of eligible stocks (no external data needed).
        r = c.pct_change(fill_method=None).where(eligible_mask(panel).shift(1, fill_value=False))
        mkt = (1 + r.mean(axis=1).fillna(0)).cumprod()
        self.mkt_ok = (mkt > I.sma(mkt, self.market_ma)).to_numpy()
        cal = c.index
        self.month_end = np.r_[cal.month[1:] != cal.month[:-1], True]
        self.tickers = list(c.columns)

    def decide(self, i, positions):
        cur = {t: 1 / self.top_n for t in positions}
        if not self.month_end[i] or i == len(self.month_end) - 1:
            return cur
        if not self.mkt_ok[i]:
            return {}
        cand = [(self.mom[i, j], t) for j, t in enumerate(self.tickers)
                if self.elig[i, j] and not np.isnan(self.mom[i, j])]
        return {t: 1 / self.top_n for _, t in sorted(cand, reverse=True)[: self.top_n]}


@dataclass
class RandomEntry:
    """S5 control: random stock entries with S2-like frequency and holding period."""
    seed: int = 0
    entry_prob: float = 0.08     # per free slot per day
    hold_days: int = 4
    max_positions: int = 2
    stop: float = 0.08
    name: str = "S5_random_control"
    kind: str = "stock"

    def params(self):
        return {"seed": self.seed}

    def prepare(self, panel):
        self.elig = eligible_mask(panel).to_numpy()
        self.tickers = list(panel.close.columns)
        rng = np.random.default_rng(self.seed)
        n = len(panel.calendar)
        self.draw = rng.random((n, self.max_positions))
        self.pick = rng.random((n, self.max_positions))

    def decide(self, i, positions):
        keep = {t: 1 / self.max_positions for t, p in positions.items()
                if i - p["entry_i"] + 1 < self.hold_days}
        pool = [t for j, t in enumerate(self.tickers) if self.elig[i, j] and t not in keep and t not in positions]
        for s in range(self.max_positions - len(keep)):
            if pool and self.draw[i, s] < self.entry_prob:
                t = pool[int(self.pick[i, s] * len(pool))]
                pool.remove(t)
                keep[t] = 1 / self.max_positions
        return keep


# ======================================================================= funds
def week_ends(cal: pd.DatetimeIndex) -> np.ndarray:
    iso = cal.isocalendar()
    wk = (iso["year"].astype(int) * 100 + iso["week"].astype(int)).to_numpy()
    return np.r_[wk[1:] != wk[:-1], True]


@dataclass
class FundRotation:
    """S1: weekly, hold the fund with the best momentum if it's above its trend, else cash."""
    lookback: int = 126
    trend_ma: int = 200
    assets: tuple = ("SE_EQ", "GLOBAL_EQ")
    name: str = "S1_fund_rotation"
    kind: str = "fund"

    def params(self):
        return {"lookback": self.lookback, "trend_ma": self.trend_ma}

    def targets(self, levels: pd.DataFrame, cal: pd.DatetimeIndex) -> pd.Series:
        lv = levels[list(self.assets)]
        mom = lv / lv.shift(self.lookback) - 1
        above = lv > I.sma(lv, self.trend_ma)
        we = week_ends(cal)
        out = {}
        for i, d in enumerate(cal):
            if not we[i]:
                continue
            m = mom.iloc[i]
            if m.isna().any() or I.sma(lv, self.trend_ma).iloc[i].isna().any():
                continue
            best = m.idxmax()
            out[d] = best if above.iloc[i][best] else "CASH"
        return pd.Series(out, dtype=object)


@dataclass
class TurnOfMonth:
    """S4: own the Swedish index fund from N days before month end to M days into the new month.

    Uses the trading calendar, which is known in advance (holidays are published).
    Decision at close of day i executes at the NEXT day's NAV, so to own the fund from the
    close of day -N we decide at day -(N+1).
    """
    days_before: int = 4
    days_after: int = 3
    name: str = "S4_turn_of_month"
    kind: str = "fund"

    def params(self):
        return {"days_before": self.days_before, "days_after": self.days_after}

    def targets(self, levels, cal):
        s = pd.Series(np.arange(len(cal)), index=cal)
        ym = cal.year * 12 + cal.month
        pos_from_end = s.groupby(ym).transform(lambda x: len(x) - 1 - (x - x.iloc[0]))  # 0 = last day
        pos_from_start = s.groupby(ym).transform(lambda x: x - x.iloc[0] + 1)           # 1 = first day
        out = {}
        for i, d in enumerate(cal[:-1]):
            nxt_end, nxt_start = pos_from_end.iloc[i + 1], pos_from_start.iloc[i + 1]
            # Will we want to hold the fund at the close of day i+1?
            want = (nxt_end <= self.days_before - 1) or (nxt_start <= self.days_after - 1)
            # days_before=4 -> hold at close of the last 4 days ( pos_from_end 3..0 )
            # days_after=3  -> hold at close of days 1..2, sell at NAV of day 3
            out[d] = "SE_EQ" if want else "CASH"
        return pd.Series(out, dtype=object)
