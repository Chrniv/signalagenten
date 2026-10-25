"""Research for S6 (report drift) and S7 (volume-surge drift). Rules: research/PREREG_S6_S7.md

    python -m engine.research_events --universe universe --data data --out reports
    python -m engine.research_events ... --holdout     # one run, needs research/HOLDOUT_UNLOCK_EVENTS.json
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
from . import events as E
from . import metrics as M
from . import sim as S
from .research import THRESH, num, pct

PRIOR_TRIALS = 126           # S1–S4 variants already tested in this project
PERIODS = {
    "S6_report_drift": {"dev": ("2020-11-01", "2023-12-31"), "holdout": ("2024-01-01", "2026-09-30")},
    "S7_volume_surge": {"dev": ("2006-01-02", "2018-12-31"), "holdout": ("2019-01-01", "2026-09-30")},
}
GRIDS = {
    "S6_report_drift": {"surprise_min": [7.5, 10, 12.5], "reaction_min": [0.015, 0.02, 0.025],
                        "hold": [22, 30, 38], "stop": [0.075, 0.10, 0.125]},
    "S7_volume_surge": {"excess_min": [0.03, 0.04, 0.05], "vol_mult": [2.25, 3.0, 3.75],
                        "hold": [22, 30, 38], "stop": [0.075, 0.10, 0.125]},
}
DEFAULTS = {
    "S6_report_drift": {"surprise_min": 10, "reaction_min": 0.02, "hold": 30, "stop": 0.10},
    "S7_volume_surge": {"excess_min": 0.04, "vol_mult": 3.0, "hold": 30, "stop": 0.10},
}
N_TRIALS = PRIOR_TRIALS + sum(int(np.prod([len(v) for v in g.values()])) for g in GRIDS.values())
BASE = dict(courtage="start", tiered=True)
SEEDS = 20


def make(name, params, earnings):
    if name == "S6_report_drift":
        return E.ReportDrift(earnings=earnings, **params)
    return E.VolumeSurge(**params)


def ew_universe(panel, start, end) -> pd.Series:
    r = panel.close.pct_change(fill_method=None)
    m = pd.DataFrame(E.event_eligible(panel), index=r.index, columns=r.columns).shift(1, fill_value=False)
    ew = r.where(m).mean(axis=1).fillna(0).loc[start:end]
    return (1 + ew).cumprod().rename("EW universe")


def evaluate(panel, earnings, levels, which: str, names: list[str]):
    out, trials, curves = {}, [], {}
    for name in names:
        start, end = PERIODS[name][which]
        grid = GRIDS[name]
        for combo in itertools.product(*grid.values()):
            p = dict(zip(grid, combo))
            res = S.run_stocks(make(name, p, earnings), panel, S.Costs(**BASE), start, end)
            st = M.stats(res.equity, res.trades, res.costs_paid, res.exposure)
            trials.append({"strategy": name, **p, "sharpe": st["sharpe"], "cagr": st["cagr"], "max_dd": st["max_dd"],
                           "trades": st["trades"], "is_default": p == DEFAULTS[name]})
    tdf = pd.DataFrame(trials)

    for name in names:
        start, end = PERIODS[name][which]
        strat = make(name, DEFAULTS[name], earnings)
        res = S.run_stocks(strat, panel, S.Costs(**BASE), start, end)
        st = M.stats(res.equity, res.trades, res.costs_paid, res.exposure)
        fam = tdf[tdf.strategy == name]
        st["dsr"] = M.deflated_sharpe(res.equity.pct_change().dropna(), N_TRIALS, float(fam["sharpe"].var()))
        st["dsr_trials"] = N_TRIALS
        for label, c in {"cost_2x": dict(BASE, mult=2), "cost_3x": dict(BASE, mult=3),
                         "mini_courtage": dict(courtage="mini", tiered=True),
                         "fill_next_close": dict(BASE, fill="close")}.items():
            rr = S.run_stocks(make(name, DEFAULTS[name], earnings), panel, S.Costs(**c), start, end)
            st[f"sharpe_{label}"] = M.sharpe(rr.equity.pct_change().dropna())
            st[f"cagr_{label}"] = M.stats(rr.equity)["cagr"]
        st["neighbours"] = len(fam)
        st["neighbours_positive"] = float((fam["sharpe"] > 0).mean())
        st["neighbours_median_sharpe"] = float(fam["sharpe"].median())
        st["neighbours_min_sharpe"] = float(fam["sharpe"].min())
        bms = {"EW universe": ew_universe(panel, res.equity.index[0], res.equity.index[-1]),
               "B&H SE_EQ": S.buy_hold_fund(levels, "SE_EQ", res.equity.index[0], res.equity.index[-1])}
        st["benchmarks"] = {}
        for k, v in bms.items():
            b = M.stats(v)
            b["strategy_sharpe_same_period"] = M.sharpe(res.equity.loc[v.index[0]:v.index[-1]].pct_change().dropna())
            st["benchmarks"][k] = b
        beats = all(b["strategy_sharpe_same_period"] > b["sharpe"] for b in st["benchmarks"].values())
        pf = st.get("profit_factor", float("nan"))
        st["checks"] = {
            f"Sharpe > {THRESH['sharpe_stock']}": bool(st["sharpe"] > THRESH["sharpe_stock"]),
            "positive at 2x costs": bool(st["sharpe_cost_2x"] > 0),
            f"profit factor > {THRESH['pf']}": bool(pf > THRESH["pf"]),
            ">= 80% of neighbours positive": bool(st["neighbours_positive"] >= THRESH["neighbours_positive"]),
            f"deflated Sharpe > {THRESH['dsr']} (N={N_TRIALS})": bool((st["dsr"] or 0) > THRESH["dsr"]),
            "beats EW universe and Swedish index fund (Sharpe, same dates)": bool(beats),
        }
        st["verdict"] = "SHORTLIST" if all(st["checks"].values()) else "REJECT"
        st["why_exits"] = res.trades["why"].value_counts().to_dict() if len(res.trades) else {}
        st["recent_trades"] = res.trades.tail(8).assign(
            entry=lambda d: d.entry.astype(str).str[:10], exit=lambda d: d.exit.astype(str).str[:10],
            ret=lambda d: d.ret.round(4))[["ticker", "entry", "exit", "why", "ret"]].to_dict("records") if len(res.trades) else []
        # control with a similar opportunity rate
        cand_days = sum(1 for c in strat.cands[panel.calendar.searchsorted(pd.Timestamp(start)):
                                                 panel.calendar.searchsorted(pd.Timestamp(end), side="right")] if c)
        n_days = len(res.equity)
        rate = max(cand_days / max(n_days, 1), 0.01)
        ctl = []
        for seed in range(SEEDS):
            cr = S.run_stocks(E.RandomEvents(seed=seed, rate=rate), panel, S.Costs(**BASE), start, end)
            ctl.append(M.stats(cr.equity, cr.trades, cr.costs_paid, cr.exposure))
        sh = [c["sharpe"] for c in ctl]
        st["control"] = {"rate": rate, "sharpe_median": float(np.median(sh)), "sharpe_min": float(np.min(sh)),
                         "sharpe_max": float(np.max(sh)), "cagr_median": float(np.median([c["cagr"] for c in ctl])),
                         "trades_per_year_median": float(np.median([c["trades_per_year"] for c in ctl])),
                         "share_clearing_sharpe_bar": float(np.mean([s > THRESH["sharpe_stock"] for s in sh]))}
        out[name] = st
        curves[name] = res.equity / res.equity.iloc[0]
        for k, v in bms.items():
            curves[f"{name} | {k}"] = v / v.iloc[0]
    return out, tdf, curves


def diagnostics(panel, earnings, univ_dir) -> dict:
    d = {}
    ev = E.report_events(earnings, panel.calendar, list(panel.close.columns))
    ts = pd.to_datetime(ev["report_ts"], utc=True).dt.tz_convert(E.STOCKHOLM)
    d["reports_usable"] = int(len(ev))
    d["tickers_with_reports"] = int(ev["ticker"].nunique())
    d["first_report"] = str(ts.min())[:10]
    d["share_before_open"] = float((ts.dt.hour < 9).mean())
    d["surprise_ge_10"] = int((ev["surprise"] >= 10).sum())
    # Descriptive: average 30-day excess return after reports by surprise bucket (all reports, no costs)
    C = panel.close.to_numpy()
    mkt = np.cumprod(1 + E.ew_market_return(panel))
    rows = []
    for r in ev.itertuples():
        i, j = r.react_i, r.j
        if i + 31 >= len(C) or np.isnan(C[i, j]) or np.isnan(C[i + 31, j]):
            continue
        stock = C[i + 31, j] / C[i + 1, j] - 1 if not np.isnan(C[i + 1, j]) else np.nan
        rows.append({"surprise": r.surprise, "excess_30d": stock - (mkt[i + 31] / mkt[i + 1] - 1)})
    x = pd.DataFrame(rows).dropna()
    if len(x):
        x["bucket"] = pd.cut(x["surprise"], [-1e9, -10, -2, 2, 10, 1e9],
                             labels=["< -10%", "-10..-2%", "-2..+2%", "+2..+10%", "> +10%"])
        d["drift_by_surprise"] = x.groupby("bucket", observed=True)["excess_30d"].agg(["count", "mean", "median"]).round(4).reset_index().astype(str).to_dict("records")
    # Spread model vs today's actual bid/ask
    uni = pd.read_csv(Path(univ_dir) / "universe.csv")
    turn = (panel.raw_close * panel.volume).rolling(60, min_periods=20).median().iloc[-1]
    uni["tier_half_spread"] = uni["yahoo"].map(lambda t: float(S.tier_half_spread(np.array([turn.get(t, 0.0) or 0.0]))[0]))
    uni["turnover_60d"] = uni["yahoo"].map(turn)
    uni = uni.dropna(subset=["half_spread_now", "turnover_60d"])
    uni = uni[(uni.half_spread_now > 0) & (uni.half_spread_now < 0.2)]
    d["spread_check"] = uni.groupby("tier_half_spread").agg(
        stocks=("yahoo", "count"), actual_median=("half_spread_now", "median"),
        actual_p75=("half_spread_now", lambda s: s.quantile(0.75))).round(5).reset_index().to_dict("records")
    return d


def write(out_dir: Path, label: str, res: dict, tdf, curves, diag: dict, period_note: str):
    out_dir.mkdir(parents=True, exist_ok=True)
    tdf.to_csv(out_dir / f"trials_events_{label}.csv", index=False)
    pd.DataFrame(curves).to_csv(out_dir / f"equity_events_{label}.csv.gz", compression="gzip")
    (out_dir / f"results_events_{label}.json").write_text(json.dumps({"results": res, "diagnostics": diag}, indent=2, default=str))
    L = [f"# Report drift (S6) and volume-surge drift (S7) — {period_note}", "",
         f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}. Rules: research/PREREG_S6_S7.md (committed before this run). "
         f"Deflated Sharpe uses N = {N_TRIALS} (every variant tested in the project).", "",
         "Costs: Avanza Start (0 kr courtage), half-spread by liquidity tier, fills at the next open, 1,000 kr, 2 slots.", "",
         "| Strategy | Period | CAGR | Sharpe | Max DD | Trades/yr | Win rate | Profit factor | Avg trade | Sharpe 2× spread | Sharpe w/ Mini | Neighbours >0 | Deflated Sharpe | EW universe Sharpe | Index fund Sharpe | Verdict |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for n, s in res.items():
        b = s["benchmarks"]
        L.append(f"| {n} | {s['start']} → {s['end']} | {pct(s['cagr'])} | {num(s['sharpe'])} | {pct(s['max_dd'])} | "
                 f"{num(s['trades_per_year'], 1)} | {pct(s['win_rate'], 0)} | {num(s['profit_factor'])} | {pct(s['avg_trade'], 2)} | "
                 f"{num(s['sharpe_cost_2x'])} | {num(s['sharpe_mini_courtage'])} | {pct(s['neighbours_positive'], 0)} | {num(s['dsr'])} | "
                 f"{num(b['EW universe']['sharpe'])} | {num(b['B&H SE_EQ']['sharpe'])} | **{s['verdict']}** |")
    for n, s in res.items():
        c = s["control"]
        L += ["", f"### {n} — {s['verdict']}", "",
              f"CAGR {pct(s['cagr'])} · vol {pct(s['vol'])} · Sharpe {num(s['sharpe'])} · Sortino {num(s['sortino'])} · max DD {pct(s['max_dd'])} · "
              f"longest drawdown {s['dd_days']} days · invested {pct(s['exposure'], 0)} of the time · {s['trades']} trades · exits: {s['why_exits']}",
              "",
              "Sensitivity: " + " · ".join(f"{k[7:]}: Sharpe {num(v)}" for k, v in s.items() if k.startswith("sharpe_")),
              f"Neighbourhood ({s['neighbours']}): {pct(s['neighbours_positive'], 0)} positive, median {num(s['neighbours_median_sharpe'])}, worst {num(s['neighbours_min_sharpe'])}",
              "Benchmarks (same dates): " + " · ".join(f"{k}: CAGR {pct(v['cagr'])}, Sharpe {num(v['sharpe'])} (strategy {num(v['strategy_sharpe_same_period'])}), max DD {pct(v['max_dd'])}" for k, v in s["benchmarks"].items()),
              f"Random control ({SEEDS} seeds, same opportunity rate): median Sharpe {num(c['sharpe_median'])} (range {num(c['sharpe_min'])} to {num(c['sharpe_max'])}), "
              f"median CAGR {pct(c['cagr_median'])}, {num(c['trades_per_year_median'], 0)} trades/yr, {pct(c['share_clearing_sharpe_bar'], 0)} clear the Sharpe bar.",
              "", "| Check | Pass |", "|---|---|"] + [f"| {k} | {'✅' if v else '❌'} |" for k, v in s["checks"].items()]
        if s["recent_trades"]:
            L += ["", "Last trades in the period: " + "; ".join(f"{t['ticker']} {t['entry']}→{t['exit']} {t['why']} {pct(t['ret'])}" for t in s["recent_trades"])]
    if diag:
        L += ["", "## Data checks", "",
              f"Usable reports: {diag['reports_usable']} from {diag['tickers_with_reports']} companies, first {diag['first_report']}; "
              f"{pct(diag['share_before_open'], 0)} published before 09:00; {diag['surprise_ge_10']} with surprise ≥ +10 %."]
        if diag.get("drift_by_surprise"):
            L += ["", "Average 30-day return after the reaction day, versus equal-weight market, by EPS surprise (all reports, before costs — descriptive only):", "",
                  "| Surprise | Reports | Mean excess | Median excess |", "|---|---|---|---|"]
            for r in diag["drift_by_surprise"]:
                L.append(f"| {r['bucket']} | {r['count']} | {pct(float(r['mean']))} | {pct(float(r['median']))} |")
        L += ["", "Spread model vs today's real bid/ask (Nasdaq, half-spread):", "",
              "| Model tier | Stocks | Actual median | Actual 75th pct |", "|---|---|---|---|"]
        for r in diag["spread_check"]:
            L.append(f"| {pct(r['tier_half_spread'], 2)} | {r['stocks']} | {pct(r['actual_median'], 2)} | {pct(r['actual_p75'], 2)} |")
    L += ["", "*Survivorship: the universe is today's listed companies. Delisted companies are missing, which flatters both "
          "strategies and the EW benchmark. Nothing here is a forecast.*"]
    (out_dir / f"report_events_{label}.md").write_text("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", default="universe")
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="reports")
    ap.add_argument("--holdout", action="store_true")
    a = ap.parse_args()
    panel = D.load_universe_panel(a.universe)
    earnings = D.load_earnings(a.universe)
    levels, _ = D.fund_series(a.data)
    names = list(GRIDS)
    if not a.holdout:
        res, tdf, curves = evaluate(panel, earnings, levels, "dev", names)
        write(Path(a.out), "dev", res, tdf, curves, diagnostics(panel, earnings, a.universe), "development period")
        print((Path(a.out) / "report_events_dev.md").read_text()[:2500])
        return
    unlock = Path("research/HOLDOUT_UNLOCK_EVENTS.json")
    log = Path("research/holdout_log_events.json")
    if not unlock.exists():
        raise SystemExit("Held-out run locked: create research/HOLDOUT_UNLOCK_EVENTS.json")
    if log.exists():
        raise SystemExit(f"Held-out data already used: {log.read_text()}")
    names = json.loads(unlock.read_text())["strategies"]
    res, tdf, curves = evaluate(panel, earnings, levels, "holdout", names)
    log.write_text(json.dumps({"run_utc": datetime.now(timezone.utc).isoformat(), "strategies": names}))
    write(Path(a.out), "holdout", res, tdf, curves, {}, "HELD-OUT (single run)")
    print((Path(a.out) / "report_events_holdout.md").read_text()[:2500])


if __name__ == "__main__":
    main()
