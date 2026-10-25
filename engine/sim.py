"""Daily simulators. Decisions at the close of day i are executed on day i+1.

Stocks: fill at next open (or next close), slippage = half-spread, courtage per Avanza class,
        resting stop-loss checked intraday (gap -> fill at open). Fractional shares (see README:
        split-adjusted history makes whole-share simulation meaningless; affordability is checked
        on today's prices instead).
Funds:  order placed before the 15:00 cut-off on day i+1 -> NAV of day i+1. A switch sells on
        day i+1 and buys `settle_lag` trading days later, when the sale proceeds are available.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

COURTAGE = {
    "mini": {"rate": 0.0025, "min_fee": 1.0},    # Avanza Mini: 0.25 %, min 1 kr (isk-guiden, Jun 2026)
    "start": {"rate": 0.0, "min_fee": 0.0},      # Avanza Start: 0 kr (Stockholm, < 50k savings)
}


@dataclass
class Costs:
    courtage: str = "mini"
    half_spread: float = 0.0010      # 0.10 % per side for large caps (assumption)
    mult: float = 1.0                # stress multiplier on courtage rate and spread
    fill: str = "open"               # "open" or "close" of the next day
    cash_yield: float = 0.0          # annual, on idle cash (conservative default)
    settle_lag: int = 2              # trading days between a fund sale and the buy it funds (assumption)
    tiered: bool = False             # half-spread by liquidity tier instead of the flat half_spread

    def fee(self, notional: float) -> float:
        c = COURTAGE[self.courtage]
        if c["rate"] == 0:
            return 0.0
        return max(c["min_fee"], c["rate"] * self.mult * notional)

    @property
    def slip(self) -> float:
        return self.half_spread * self.mult


# Half-spread per side by 60-day median daily turnover in SEK (assumption, PREREG_S6_S7.md)
SPREAD_TIERS = [(100e6, 0.0005), (20e6, 0.0010), (5e6, 0.0020), (0, 0.0040)]


def tier_half_spread(turnover: np.ndarray) -> np.ndarray:
    out = np.full(turnover.shape, SPREAD_TIERS[-1][1])
    for lo, hs in reversed(SPREAD_TIERS):
        out = np.where(turnover >= lo, hs, out)
    return out


@dataclass
class Result:
    equity: pd.Series
    trades: pd.DataFrame
    costs_paid: float
    exposure: float
    meta: dict = field(default_factory=dict)


# ======================================================================= stocks
def run_stocks(strategy, panel, costs: Costs, start=None, end=None, capital=1000.0) -> Result:
    strategy.prepare(panel)
    cal = panel.calendar
    O, H, L, C = (panel.open.to_numpy(), panel.high.to_numpy(), panel.low.to_numpy(), panel.close.to_numpy())
    tick = list(panel.close.columns)
    col = {t: j for j, t in enumerate(tick)}
    i0 = 0 if start is None else int(cal.searchsorted(pd.Timestamp(start)))
    i1 = len(cal) - 1 if end is None else int(cal.searchsorted(pd.Timestamp(end), side="right")) - 1

    cash, pos = capital, {}           # pos[t] = dict(shares, entry_px, entry_i, cost_in, stop_px)
    pending = None                    # (desired holdings, equity at decision)
    equity, trades, costs_paid, invested_days = [], [], 0.0, 0
    stop = getattr(strategy, "stop", 0.0) or 0.0
    if costs.tiered:
        turn = (panel.raw_close * panel.volume).rolling(60, min_periods=20).median().shift(1).to_numpy()
        HS = tier_half_spread(np.nan_to_num(turn, nan=0.0)) * costs.mult

        def slip(i, j):
            return HS[i, j]
    else:
        def slip(i, j):
            return costs.slip

    def close_pos(t, px, i, why):
        nonlocal cash, costs_paid
        p = pos.pop(t)
        sl = slip(i, col[t])
        fill = px * (1 - sl)
        notional = p["shares"] * fill
        fee = costs.fee(notional)
        cash += notional - fee
        costs_paid += fee + p["shares"] * px * sl
        trades.append({"ticker": t, "entry": cal[p["entry_i"]], "exit": cal[i], "why": why,
                       "entry_px": p["entry_px"], "exit_px": fill, "shares": p["shares"],
                       "pnl": notional - fee - p["cost_in"], "ret": (notional - fee) / p["cost_in"] - 1})

    daily_cash = (1 + costs.cash_yield) ** (1 / 252) - 1
    for i in range(i0, i1 + 1):
        cash *= (1 + daily_cash)
        # 1) execute yesterday's decision
        if pending is not None:
            want, eq_dec = pending
            px_row = O[i] if costs.fill == "open" else C[i]
            for t in list(pos):
                if t not in want:
                    px = px_row[col[t]]
                    if np.isnan(px):
                        px = C[i - 1, col[t]]
                    close_pos(t, px, i, "signal")
            for t, w in want.items():
                if t in pos or eq_dec < 20:        # below 20 kr the account is treated as ruined
                    continue
                px = px_row[col[t]]
                if np.isnan(px) or px <= 0:
                    continue
                sl = slip(i, col[t])
                fill = px * (1 + sl)
                budget = min(w * eq_dec, cash)
                if budget <= 0:
                    continue
                fee = costs.fee(budget)
                notional = budget - fee
                if notional <= 0:
                    continue
                sh = notional / fill
                cash -= notional + fee
                costs_paid += fee + sh * px * sl
                pos[t] = {"shares": sh, "entry_px": fill, "entry_i": i, "cost_in": notional + fee,
                          "stop_px": fill * (1 - stop) if stop > 0 else None}
            pending = None
        # 2) resting stop-loss orders (also on the entry day after an open fill)
        for t in list(pos):
            sp = pos[t]["stop_px"]
            if sp is None:
                continue
            j = col[t]
            entered_today = pos[t]["entry_i"] == i
            if entered_today and costs.fill == "close":
                continue
            o, lo = O[i, j], L[i, j]
            if np.isnan(lo):
                continue
            if not entered_today and o <= sp:
                close_pos(t, o, i, "stop_gap")
            elif lo <= sp:
                close_pos(t, sp, i, "stop")
        # 3) mark to market
        val = cash + sum(p["shares"] * (C[i, col[t]] if not np.isnan(C[i, col[t]]) else p["entry_px"])
                         for t, p in pos.items())
        equity.append(val)
        if pos:
            invested_days += 1
        # 4) decide for tomorrow
        if i < i1:
            want = strategy.decide(i, {t: {"entry_i": p["entry_i"]} for t, p in pos.items()})
            if set(want) != set(pos):
                pending = (want, val)
    # close everything at the end for trade statistics (no costs: it's bookkeeping)
    for t in list(pos):
        p = pos.pop(t)
        px = C[i1, col[t]]
        trades.append({"ticker": t, "entry": cal[p["entry_i"]], "exit": cal[i1], "why": "end",
                       "entry_px": p["entry_px"], "exit_px": px, "shares": p["shares"],
                       "pnl": p["shares"] * px - p["cost_in"], "ret": p["shares"] * px / p["cost_in"] - 1})
    eq = pd.Series(equity, index=cal[i0:i1 + 1], name=strategy.name)
    return Result(eq, pd.DataFrame(trades), costs_paid, invested_days / max(1, len(eq)))


# ======================================================================= funds
FUND_FEES = {"SE_EQ": 0.0015, "GLOBAL_EQ": 0.0015}


def signal_view(levels: pd.DataFrame) -> pd.DataFrame:
    """What is KNOWN at 18:30 Stockholm on day t: foreign closes (US) arrive later, so lag them."""
    v = levels.copy()
    if "GLOBAL_EQ" in v:
        v["GLOBAL_EQ"] = v["GLOBAL_EQ"].shift(1)
    return v


def run_funds(strategy, levels: pd.DataFrame, costs: Costs, start=None, end=None,
              capital=1000.0, fees=None) -> Result:
    fees = fees or FUND_FEES
    cal = levels.index
    tg = strategy.targets(signal_view(levels), cal)
    i0 = 0 if start is None else int(cal.searchsorted(pd.Timestamp(start)))
    i1 = len(cal) - 1 if end is None else int(cal.searchsorted(pd.Timestamp(end), side="right")) - 1
    lv = levels.to_numpy()
    cols = {c: k for k, c in enumerate(levels.columns)}
    tg_i = {int(cal.get_loc(d)): a for d, a in tg.items()}

    cash, units, held = capital, {}, "CASH"
    sell_at, buy_at = None, None            # (i, asset)
    entry = None                            # (asset, i, value_in)
    equity, trades, invested = [], [], 0
    daily_cash = (1 + costs.cash_yield) ** (1 / 252) - 1

    for i in range(i0, i1 + 1):
        # fees accrue on fund holdings
        for a in units:
            units[a] *= (1 - fees.get(a, 0) / 252)
        cash *= (1 + daily_cash)
        # executions at today's NAV
        if sell_at and sell_at[0] == i:
            a = sell_at[1]
            if a in units:
                val = units.pop(a) * lv[i, cols[a]]
                cash += val
                if entry:
                    trades.append({"ticker": a, "entry": cal[entry[1]], "exit": cal[i], "why": "signal",
                                   "pnl": val - entry[2], "ret": val / entry[2] - 1})
                    entry = None
            sell_at = None
        if buy_at and buy_at[0] == i:
            a = buy_at[1]
            px = lv[i, cols[a]]
            if not np.isnan(px) and cash > 0:
                units[a] = cash / px
                entry = (a, i, cash)
                cash = 0.0
            buy_at = None
        val = cash + sum(u * lv[i, cols[a]] for a, u in units.items())
        equity.append(val)
        if units:
            invested += 1
        # decision at today's close
        if i < i1 and i in tg_i and sell_at is None and buy_at is None:
            want = tg_i[i]
            if want != held:
                if held != "CASH":
                    sell_at = (i + 1, held)
                if want != "CASH":
                    # buying from cash: next day's NAV; switching: wait for the sale to settle
                    lag = 1 + costs.settle_lag if held != "CASH" else 1
                    buy_at = (i + lag, want) if i + lag <= i1 else None
                held = want
    if units and entry:
        a = entry[0]
        v = units[a] * lv[i1, cols[a]]
        trades.append({"ticker": a, "entry": cal[entry[1]], "exit": cal[i1], "why": "end",
                       "pnl": v - entry[2], "ret": v / entry[2] - 1})
    eq = pd.Series(equity, index=cal[i0:i1 + 1], name=strategy.name)
    return Result(eq, pd.DataFrame(trades), 0.0, invested / max(1, len(eq)))


# ======================================================================= benchmarks
def buy_hold_fund(levels, asset, start=None, end=None, fee=0.0015) -> pd.Series:
    s = levels[asset].loc[start:end].dropna()
    r = s.pct_change().fillna(0) - fee / 252
    return (1 + r).cumprod().rename(f"B&H {asset}")


def equal_weight_universe(panel, start=None, end=None) -> pd.Series:
    """Costless daily-rebalanced equal weight of eligible stocks (same survivorship bias as the strategies)."""
    from .strategies import eligible_mask
    r = panel.close.pct_change(fill_method=None)
    m = eligible_mask(panel).shift(1, fill_value=False)
    ew = r.where(m).mean(axis=1).fillna(0)
    ew = ew.loc[start:end]
    return (1 + ew).cumprod().rename("EW universe")
