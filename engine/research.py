"""Gate 2 research: run every pre-registered variant on the development period and write a report.

    python -m engine.research --data data --out reports            # development period only
    python -m engine.research --data data --out reports --holdout  # ONE run on held-out data,
                                                                   # needs research/HOLDOUT_UNLOCK.json
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import data as D
from . import metrics as M
from . import sim as S
from . import strategies as ST

DEV_END = "2018-12-31"
HOLDOUT = ("2019-01-01", "2026-09-30")

# Pre-registered defaults and +/-25 % neighbourhoods (SPEC_v2 section 4 / 6)
GRIDS = {
    "S1_fund_rotation": (ST.FundRotation, {"lookback": [95, 126, 158], "trend_ma": [150, 200, 250]}),
    "S2_mean_reversion": (ST.MeanReversion, {"rsi_threshold": [7.5, 10, 12.5], "trend_ma": [150, 200, 250],
                                             "exit_ma": [4, 5, 6], "max_days": [4, 5, 6]}),
    "S3_stock_momentum": (ST.StockMomentum, {"lookback": [189, 252, 315], "skip": [16, 21, 26],
                                             "market_ma": [150, 200, 250]}),
    "S4_turn_of_month": (ST.TurnOfMonth, {"days_before": [3, 4, 5], "days_after": [2, 3, 4]}),
}
DEFAULTS = {
    "S1_fund_rotation": {"lookback": 126, "trend_ma": 200},
    "S2_mean_reversion": {"rsi_threshold": 10, "trend_ma": 200, "exit_ma": 5, "max_days": 5},
    "S3_stock_momentum": {"lookback": 252, "skip": 21, "market_ma": 200},
    "S4_turn_of_month": {"days_before": 4, "days_after": 3},
}
THRESH = {"sharpe": 0.5, "sharpe_stock": 0.7, "pf": 1.2, "neighbours_positive": 0.8, "dsr": 0.90}
CONTROL_SEEDS = 20


def run(strategy, panel, levels, costs, start, end):
    if strategy.kind == "stock":
        return S.run_stocks(strategy, panel, costs, start, end)
    return S.run_funds(strategy, levels, costs, start, end)


def benchmark_for(kind, panel, levels, start, end) -> dict[str, pd.Series]:
    if kind == "stock":
        b = {"EW universe": S.equal_weight_universe(panel, start, end)}
    else:
        b = {}
    for a in levels.columns:
        b[f"B&H {a}"] = S.buy_hold_fund(levels, a, start, end)
    return b


def evaluate(panel, levels, start, end, period_label, only=None, n_trials_override=None):
    base = S.Costs()
    trials, detail, curves = [], {}, {}
    for name, (cls, grid) in GRIDS.items():
        if only and name not in only:
            continue
        keys = list(grid)
        for combo in itertools.product(*[grid[k] for k in keys]):
            params = dict(zip(keys, combo))
            res = run(cls(**params), panel, levels, base, start, end)
            st = M.stats(res.equity, res.trades, res.costs_paid, res.exposure)
            trials.append({"strategy": name, **params, "sharpe": st["sharpe"], "cagr": st["cagr"],
                           "max_dd": st["max_dd"], "trades": st["trades"],
                           "is_default": params == DEFAULTS[name]})
    tdf = pd.DataFrame(trials)
    n_trials = n_trials_override or len(tdf)
    sr_var = float(tdf["sharpe"].var()) if len(tdf) > 1 else 0.0

    for name, (cls, grid) in GRIDS.items():
        if only and name not in only:
            continue
        strat = cls(**DEFAULTS[name])
        res = run(strat, panel, levels, S.Costs(), start, end)
        st = M.stats(res.equity, res.trades, res.costs_paid, res.exposure)
        r = res.equity.pct_change().dropna()
        st["dsr"] = M.deflated_sharpe(r, n_trials, sr_var)
        if strat.kind == "stock":
            for label, c in {"start_class": S.Costs(courtage="start"), "cost_2x": S.Costs(mult=2),
                             "cost_3x": S.Costs(mult=3), "fill_next_close": S.Costs(fill="close")}.items():
                rr = run(cls(**DEFAULTS[name]), panel, levels, c, start, end)
                st[f"sharpe_{label}"] = M.sharpe(rr.equity.pct_change().dropna())
                st[f"cagr_{label}"] = M.stats(rr.equity)["cagr"]
        else:
            for label, c in {"settle_lag_0": S.Costs(settle_lag=0), "settle_lag_4": S.Costs(settle_lag=4),
                             "cash_yield_2pct": S.Costs(cash_yield=0.02)}.items():
                rr = run(cls(**DEFAULTS[name]), panel, levels, c, start, end)
                st[f"sharpe_{label}"] = M.sharpe(rr.equity.pct_change().dropna())
                st[f"cagr_{label}"] = M.stats(rr.equity)["cagr"]
            # funds have no trading costs; stress = the default case
            st["sharpe_cost_2x"] = st["sharpe"]
        nb = tdf[tdf.strategy == name]
        st["neighbours"] = int(len(nb))
        st["neighbours_positive"] = float((nb["sharpe"] > 0).mean())
        st["neighbours_min_sharpe"] = float(nb["sharpe"].min())
        st["neighbours_median_sharpe"] = float(nb["sharpe"].median())
        bm = benchmark_for(strat.kind, panel, levels, res.equity.index[0], res.equity.index[-1])
        st["benchmarks"] = {k: M.stats(v) for k, v in bm.items()}
        best_bm = max(v["sharpe"] for v in st["benchmarks"].values())
        st["best_benchmark_sharpe"] = best_bm
        st["checks"] = checks(st, strat.kind, best_bm)
        st["verdict"] = "SHORTLIST" if all(st["checks"].values()) else "REJECT"
        st["trades_sample"] = res.trades.tail(5).astype(str).to_dict("records") if len(res.trades) else []
        detail[name] = st
        curves[name] = res.equity / res.equity.iloc[0]
        for k, v in bm.items():
            curves[f"{name} | {k}"] = v / v.iloc[0]

    # Control: random entries, many seeds. It should NOT pass.
    if not only or "S5_random_control" in only:
        ctl = []
        for seed in range(CONTROL_SEEDS):
            res = S.run_stocks(ST.RandomEntry(seed=seed), panel, S.Costs(), start, end)
            st = M.stats(res.equity, res.trades, res.costs_paid, res.exposure)
            ctl.append(st)
        sh = [c["sharpe"] for c in ctl]
        bm = benchmark_for("stock", panel, levels, start, end)
        detail["S5_random_control"] = {
            "seeds": CONTROL_SEEDS, "sharpe_median": float(np.median(sh)), "sharpe_max": float(np.max(sh)),
            "sharpe_min": float(np.min(sh)), "trades_per_year_median": float(np.median([c["trades_per_year"] for c in ctl])),
            "cagr_median": float(np.median([c["cagr"] for c in ctl])),
            "share_passing_sharpe": float(np.mean([s > THRESH["sharpe_stock"] for s in sh])),
            "ew_universe_sharpe": M.stats(bm["EW universe"])["sharpe"],
        }
    return {"period": period_label, "start": str(start), "end": str(end), "n_trials": n_trials,
            "sharpe_var_across_trials": sr_var, "strategies": detail}, tdf, pd.DataFrame(curves)


def checks(st, kind, best_bm):
    need = THRESH["sharpe_stock"] if kind == "stock" else THRESH["sharpe"]
    pf = st.get("profit_factor", float("nan"))
    return {
        f"sharpe > {need}": bool(st["sharpe"] > need),
        "positive at 2x costs": bool(st.get("sharpe_cost_2x", float("nan")) > 0),
        f"profit factor > {THRESH['pf']}": bool(pf > THRESH["pf"]),
        f">= {int(THRESH['neighbours_positive'] * 100)}% of neighbours positive": bool(st["neighbours_positive"] >= THRESH["neighbours_positive"]),
        f"deflated Sharpe > {THRESH['dsr']}": bool((st["dsr"] or 0) > THRESH["dsr"]),
        "beats best benchmark Sharpe": bool(st["sharpe"] > best_bm),
    }


def affordability(data_dir) -> pd.DataFrame:
    rows = []
    for t in __import__("engine.universe", fromlist=["STOCKS"]).STOCKS:
        df = D.load_ticker(data_dir, t)
        if df is None:
            continue
        px = float(df["close"].iloc[-1])
        rows.append({"ticker": t, "last_date": str(df.index[-1].date()), "price": round(px, 2),
                     "shares_for_500kr": int(500 // px), "shares_for_1000kr": int(1000 // px)})
    return pd.DataFrame(rows).sort_values("price")


# ----------------------------------------------------------------------- report
def pct(x, d=1):
    return "–" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:.{d}f}%"


def num(x, d=2):
    if x is None or (isinstance(x, float) and (math.isnan(x))):
        return "–"
    if isinstance(x, float) and math.isinf(x):
        return "∞"
    return f"{x:.{d}f}"


def write_report(out: Path, res: dict, tdf: pd.DataFrame, curves: pd.DataFrame, info: dict,
                 manifest: dict | None, afford: pd.DataFrame | None, label: str):
    out.mkdir(parents=True, exist_ok=True)
    tdf.to_csv(out / f"trials_{label}.csv", index=False)
    curves.to_csv(out / f"equity_{label}.csv.gz", compression="gzip")
    (out / f"results_{label}.json").write_text(json.dumps(res, indent=2, default=str))
    L = [f"# Research report — {res['period']}", "",
         f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} · period {res['start']} → {res['end']} · "
         f"**{res['n_trials']} variants tested** (all counted in the deflated Sharpe).", "",
         "Base costs: Avanza Mini courtage (0.25 %, min 1 kr) + 0.10 % half-spread per side on stocks, "
         "fills at next day's open. Funds: no courtage, 0.15 %/yr fee, NAV of the next day, 2-day settlement on switches, "
         "0 % on cash. Capital 1,000 kr, fractional shares.", "",
         "Fund proxies: " + "; ".join(f"{k} = {v}" for k, v in info.items()), "",
         "## Summary", "",
         "| Strategy | CAGR | Sharpe | Max DD | Trades/yr | Win rate | Profit factor | Cost share | Sharpe 2× costs | Neighbours >0 | Deflated Sharpe | Best benchmark Sharpe | Verdict |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for n, s in res["strategies"].items():
        if n.startswith("S5"):
            continue
        L.append(f"| {n} | {pct(s['cagr'])} | {num(s['sharpe'])} | {pct(s['max_dd'])} | {num(s['trades_per_year'], 1)} | "
                 f"{pct(s['win_rate'], 0)} | {num(s['profit_factor'])} | {pct(s['cost_share'], 0)} | {num(s.get('sharpe_cost_2x'))} | "
                 f"{pct(s['neighbours_positive'], 0)} | {num(s['dsr'])} | {num(s['best_benchmark_sharpe'])} | **{s['verdict']}** |")
    c = res["strategies"].get("S5_random_control")
    if c:
        L += ["", f"**Control (random entries, {c['seeds']} seeds):** median Sharpe {num(c['sharpe_median'])} "
              f"(range {num(c['sharpe_min'])} to {num(c['sharpe_max'])}), median CAGR {pct(c['cagr_median'])}, "
              f"{num(c['trades_per_year_median'], 0)} trades/yr; {pct(c['share_passing_sharpe'], 0)} of seeds clear the stock Sharpe bar. "
              f"Equal-weight universe Sharpe: {num(c['ew_universe_sharpe'])}."]
    L += ["", "## Details"]
    for n, s in res["strategies"].items():
        if n.startswith("S5"):
            continue
        L += ["", f"### {n} — {s['verdict']}", "",
              f"{s['start']} → {s['end']} ({s['years']} yrs) · CAGR {pct(s['cagr'])} · vol {pct(s['vol'])} · Sharpe {num(s['sharpe'])} · "
              f"Sortino {num(s['sortino'])} · max DD {pct(s['max_dd'])} · longest drawdown {s['dd_days']} trading days · "
              f"time invested {pct(s['exposure'], 0)} · {s['trades']} trades · avg trade {pct(s['avg_trade'], 2)}", ""]
        sens = {k: v for k, v in s.items() if k.startswith("sharpe_") and k != "sharpe_cost_2x"}
        if sens:
            L.append("Sensitivity (Sharpe): " + " · ".join(f"{k[7:]} {num(v)}" for k, v in sens.items()))
        L.append(f"Neighbourhood ({s['neighbours']} variants): {pct(s['neighbours_positive'], 0)} positive, "
                 f"median Sharpe {num(s['neighbours_median_sharpe'])}, worst {num(s['neighbours_min_sharpe'])}")
        L.append("Benchmarks: " + " · ".join(f"{k}: CAGR {pct(v['cagr'])}, Sharpe {num(v['sharpe'])}, max DD {pct(v['max_dd'])}"
                                             for k, v in s["benchmarks"].items()))
        L += ["", "| Check | Pass |", "|---|---|"] + [f"| {k} | {'✅' if v else '❌'} |" for k, v in s["checks"].items()]
    if afford is not None and len(afford):
        L += ["", "## Whole shares at today's prices", "",
              "Stocks priced above 500 kr can't be bought with half of a 1,000 kr budget (S2 uses 2 slots).", "",
              "| Ticker | Price | Shares for 500 kr | Shares for 1,000 kr |", "|---|---|---|---|"]
        for _, r in afford.iterrows():
            L.append(f"| {r.ticker} | {r.price} | {r.shares_for_500kr} | {r.shares_for_1000kr} |")
    if manifest:
        L += ["", "## Data", "", f"Downloaded {manifest.get('run_utc', '?')}; {len(manifest.get('files', {}))} tickers ok, "
              f"failed: {', '.join(manifest.get('failed', {})) or 'none'}."]
        warn = {t: f["warnings"] for t, f in manifest.get("files", {}).items() if f.get("warnings")}
        if warn:
            L.append("Data warnings: " + "; ".join(f"{t}: {', '.join(w)}" for t, w in list(warn.items())[:15]))
    L += ["", "*Survivorship: Yahoo has no delisted Swedish stocks, so S2/S3 and the EW universe are biased upward. "
          "S2/S3 need Sharpe > 0.7 and must beat the EW universe of the same stocks.*",
          "*No numbers here are forecasts. Development-period results are used only to shortlist; "
          "the held-out period decides.*"]
    (out / f"report_{label}.md").write_text("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="reports")
    ap.add_argument("--holdout", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    data_dir, out = Path(a.data), Path(a.out)
    manifest = json.loads((data_dir / "manifest.json").read_text()) if (data_dir / "manifest.json").exists() else None
    panel = D.load_stock_panel(data_dir)
    levels, info = D.fund_series(data_dir)

    if not a.holdout:
        res, tdf, curves = evaluate(panel, levels, None, DEV_END, "development (in-sample)")
        write_report(out, res, tdf, curves, info, manifest, affordability(data_dir), "dev")
        print((out / "report_dev.md").read_text()[:3000])
        return

    unlock = Path("research/HOLDOUT_UNLOCK.json")
    if not unlock.exists():
        raise SystemExit("Held-out run is locked. Create research/HOLDOUT_UNLOCK.json with the approved strategies.")
    u = json.loads(unlock.read_text())
    log = Path("research/holdout_log.json")
    if log.exists() and not a.force:
        raise SystemExit(f"Held-out data was already used ({log.read_text().strip()}). Refusing a second look.")
    dev_trials = pd.read_csv(out / "trials_dev.csv")
    res, tdf, curves = evaluate(panel, levels, HOLDOUT[0], HOLDOUT[1], "HELD-OUT (single run)",
                                only=u["strategies"], n_trials_override=len(dev_trials))
    log.write_text(json.dumps({"run_utc": datetime.now(timezone.utc).isoformat(), "strategies": u["strategies"],
                               "forced": a.force}))
    write_report(out, res, tdf, curves, info, manifest, None, "holdout")
    print((out / "report_holdout.md").read_text()[:3000])


if __name__ == "__main__":
    main()
