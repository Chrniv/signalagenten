"""Performance statistics and the Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014)."""
from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np
import pandas as pd

N = NormalDist()
EULER = 0.5772156649


def stats(equity: pd.Series, trades: pd.DataFrame | None = None, costs_paid: float = 0.0,
          exposure: float | None = None) -> dict:
    eq = equity.dropna()
    r = eq.pct_change().dropna()
    years = max(len(r) / 252, 1e-9)
    out = {
        "start": str(eq.index[0].date()), "end": str(eq.index[-1].date()), "years": round(years, 1),
        "cagr": (eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1 if eq.iloc[-1] > 0 else -1.0,
        "vol": r.std() * math.sqrt(252),
        "sharpe": sharpe(r),
        "sortino": (r.mean() / r[r < 0].std() * math.sqrt(252)) if (r < 0).sum() > 1 else float("nan"),
    }
    dd = eq / eq.cummax() - 1
    out["max_dd"] = dd.min()
    # longest time under water, in trading days
    under = (dd < 0).astype(int).to_numpy()
    longest = cur = 0
    for u in under:
        cur = cur + 1 if u else 0
        longest = max(longest, cur)
    out["dd_days"] = longest
    out["exposure"] = exposure
    if trades is not None and len(trades):
        pnl = trades["pnl"]
        wins, losses = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
        out.update({
            "trades": int(len(trades)),
            "trades_per_year": len(trades) / years,
            "win_rate": float((pnl > 0).mean()),
            "profit_factor": float(wins / losses) if losses > 0 else float("inf"),
            "avg_trade": float(trades["ret"].mean()),
        })
        gross = (eq.iloc[-1] - eq.iloc[0]) + costs_paid
        out["cost_share"] = costs_paid / gross if gross > 0 else float("nan")
    else:
        out.update({"trades": 0, "trades_per_year": 0, "win_rate": float("nan"),
                    "profit_factor": float("nan"), "avg_trade": float("nan"), "cost_share": float("nan")})
    return out


def sharpe(r: pd.Series) -> float:
    s = r.std()
    return float(r.mean() / s * math.sqrt(252)) if s > 0 else float("nan")


def deflated_sharpe(r: pd.Series, n_trials: int, sr_var_annual: float) -> float:
    """Probability that the true Sharpe > 0 after selecting the best of n_trials.

    r: daily returns of the chosen strategy. sr_var_annual: variance of ANNUALISED Sharpe ratios
    across all trials. Works in per-period units internally.
    """
    r = r.dropna()
    t = len(r)
    if t < 30 or r.std() == 0:
        return float("nan")
    sr = r.mean() / r.std()
    skew = float(((r - r.mean()) ** 3).mean() / r.std() ** 3)
    kurt = float(((r - r.mean()) ** 4).mean() / r.std() ** 4)
    var_p = sr_var_annual / 252.0
    if n_trials <= 1 or var_p <= 0:
        sr0 = 0.0
    else:
        sr0 = math.sqrt(var_p) * ((1 - EULER) * N.inv_cdf(1 - 1 / n_trials)
                                  + EULER * N.inv_cdf(1 - 1 / (n_trials * math.e)))
    denom = 1 - skew * sr + (kurt - 1) / 4 * sr ** 2
    if denom <= 0:
        return float("nan")
    z = (sr - sr0) * math.sqrt(t - 1) / math.sqrt(denom)
    return N.cdf(z)
