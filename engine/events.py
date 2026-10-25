"""Event strategies S6 (report drift) and S7 (volume-surge drift), and their random control.

All decisions are taken at the close of day i from data up to and including day i, and executed
at the next open by the simulator. See research/PREREG_S6_S7.md for the rules.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import indicators as I

EV_MIN_HISTORY = 120
EV_MIN_TURNOVER = 1e6
STOCKHOLM = "Europe/Stockholm"


def event_eligible(panel) -> np.ndarray:
    hist = I.history_count(panel.close)
    turn = I.median_turnover(panel.raw_close, panel.volume)
    return ((hist >= EV_MIN_HISTORY) & (turn >= EV_MIN_TURNOVER) & panel.close.notna()).to_numpy()


def ew_market_return(panel) -> np.ndarray:
    """Equal-weight daily return of eligible stocks (eligibility as of the previous day)."""
    r = panel.close.pct_change(fill_method=None)
    m = pd.DataFrame(event_eligible(panel), index=r.index, columns=r.columns).shift(1, fill_value=False)
    return r.where(m).mean(axis=1).fillna(0).to_numpy()


# ------------------------------------------------------------------ report calendar -> events
def report_events(earnings: pd.DataFrame, calendar: pd.DatetimeIndex, tickers: list[str]) -> pd.DataFrame:
    """One row per usable report: ticker, column j, reaction-day index, surprise %.

    Reaction day = the report date if published before 09:00 Stockholm time, else the next trading day.
    """
    e = earnings.copy()
    e = e[e["ticker"].isin(tickers)]
    e = e.dropna(subset=["surprise_pct", "eps_estimate", "eps_reported"])
    e = e[e["eps_estimate"] > 0]
    ts = pd.to_datetime(e["ts"], utc=True).dt.tz_convert(STOCKHOLM)
    local_date = ts.dt.tz_localize(None).dt.normalize()
    before_open = ts.dt.hour < 9
    cal = calendar
    idx_same = cal.searchsorted(local_date.to_numpy(), side="left")       # first trading day >= date
    idx_next = cal.searchsorted(local_date.to_numpy(), side="right")      # first trading day > date
    react = np.where(before_open.to_numpy(), idx_same, idx_next)
    out = pd.DataFrame({"ticker": e["ticker"].to_numpy(), "react_i": react,
                        "surprise": e["surprise_pct"].astype(float).to_numpy(),
                        "report_ts": ts.astype(str).to_numpy()})
    out = out[out["react_i"] < len(cal)]
    col = {t: j for j, t in enumerate(tickers)}
    out["j"] = out["ticker"].map(col)
    return out.drop_duplicates(["ticker", "react_i"]).reset_index(drop=True)


# ------------------------------------------------------------------ strategies
@dataclass
class _EventBase:
    hold: int = 30
    stop: float = 0.10
    max_positions: int = 2
    kind: str = "stock"

    def _setup(self, panel):
        self.tickers = list(panel.close.columns)
        self.elig = event_eligible(panel)
        n = len(panel.calendar)
        self.cands = [[] for _ in range(n)]       # per day: list of (score, ticker)

    def decide(self, i, positions):
        keep = {t: 1 / self.max_positions for t, p in positions.items() if i - p["entry_i"] + 1 < self.hold}
        free = self.max_positions - len(keep)
        if free > 0 and self.cands[i]:
            for _, t in sorted(self.cands[i], reverse=True):
                if t in keep or t in positions:
                    continue
                keep[t] = 1 / self.max_positions
                free -= 1
                if free == 0:
                    break
        return keep


@dataclass
class ReportDrift(_EventBase):
    """S6: positive EPS surprise confirmed by the market on the reaction day."""
    surprise_min: float = 10.0
    reaction_min: float = 0.02
    earnings: pd.DataFrame = field(default=None, repr=False)
    name: str = "S6_report_drift"

    def params(self):
        return {"surprise_min": self.surprise_min, "reaction_min": self.reaction_min,
                "hold": self.hold, "stop": self.stop}

    def prepare(self, panel):
        self._setup(panel)
        C = panel.close.to_numpy()
        r = np.full_like(C, np.nan)
        r[1:] = C[1:] / C[:-1] - 1
        mkt = ew_market_return(panel)
        ev = report_events(self.earnings, panel.calendar, self.tickers)
        ev = ev[ev["surprise"] >= self.surprise_min]
        for row in ev.itertuples():
            i, j = row.react_i, row.j
            if not self.elig[i, j] or np.isnan(r[i, j]):
                continue
            if r[i, j] - mkt[i] >= self.reaction_min:
                self.cands[i].append((row.surprise, self.tickers[j]))


@dataclass
class VolumeSurge(_EventBase):
    """S7: a big market-beating up-day on unusually heavy volume."""
    excess_min: float = 0.04
    vol_mult: float = 3.0
    name: str = "S7_volume_surge"

    def params(self):
        return {"excess_min": self.excess_min, "vol_mult": self.vol_mult, "hold": self.hold, "stop": self.stop}

    def prepare(self, panel):
        self._setup(panel)
        c = panel.close
        r = c.pct_change(fill_method=None).to_numpy()
        mkt = ew_market_return(panel)
        v = panel.volume
        avg = v.shift(1).rolling(50, min_periods=40).mean()
        ratio = (v / avg).to_numpy()
        hit = (r - mkt[:, None] >= self.excess_min) & (ratio >= self.vol_mult) & self.elig
        ii, jj = np.nonzero(np.nan_to_num(hit, nan=0).astype(bool))
        for i, j in zip(ii, jj):
            self.cands[i].append((ratio[i, j], self.tickers[j]))


@dataclass
class RandomEvents(_EventBase):
    """Control: random entries into eligible stocks, same hold/stop/slots."""
    seed: int = 0
    rate: float = 0.06            # expected new candidates per day
    name: str = "CTRL_random_events"

    def params(self):
        return {"seed": self.seed}

    def prepare(self, panel):
        self._setup(panel)
        rng = np.random.default_rng(self.seed)
        for i in range(len(panel.calendar)):
            if rng.random() < self.rate:
                js = np.nonzero(self.elig[i])[0]
                if len(js):
                    j = int(rng.choice(js))
                    self.cands[i].append((rng.random(), self.tickers[j]))
