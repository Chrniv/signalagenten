"""Daily live run (GitHub Actions, weekdays after the Stockholm close).

Forward test WITHOUT money: every strategy runs a 1,000 kr paper portfolio from FORWARD_START,
following its rules exactly (decision at the close, fill at the next open, Start courtage,
spread by liquidity). The whole paper history is recomputed from market data every day, so
there is no state that can drift. Output: live/state.json (read by the phone app) and an
optional push via ntfy.sh (env NTFY_TOPIC).

    python -m engine.live --out live            # downloads fresh data
    python -m engine.live --out live --universe universe   # use already downloaded data (tests)
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import data as D
from . import events as E
from . import metrics as M
from . import sim as S
from . import strategies as ST
from . import universe as U

FORWARD_START = "2026-10-23"          # first decision at this close -> first paper fills Monday 26 Oct
CAPITAL = 1000.0
APP_URL = "https://chrniv.github.io/signalagenten/"
TZ = ZoneInfo("Europe/Stockholm")
COSTS = S.Costs(courtage="start", tiered=True)

STRATEGIES = {
    "S2": {"name": "Dippköp", "universe": "large",
           "how": "Köper storbolag i upptrend (över 200-dagars snitt) efter en kraftig dipp (RSI(2) under 10). "
                  "Säljer när kursen studsar över 5-dagars snitt eller efter 5 dagar. Stop-loss −8 %. Max 2 aktier.",
           "backtest": "Underkänd i backtest 2006–2018: Sharpe 0,63 med Start-courtage (kravet var 0,7) och förlust med Mini.",
           "make": lambda earn: ST.MeanReversion()},
    "S3": {"name": "Momentum", "universe": "large",
           "how": "Vid varje månadsskifte: håll de 2 storbolag som gått bäst senaste 12 månaderna (exkl. sista månaden), "
                  "men bara när marknaden ligger över sitt 200-dagars snitt.",
           "backtest": "Underkänd i backtest 2006–2018: Sharpe 0,52, sämre än att bara äga alla aktierna (0,60).",
           "make": lambda earn: ST.StockMomentum()},
    "S6": {"name": "Rapportdrift", "universe": "all",
           "how": "Köper dagen efter en kvartalsrapport som slagit analytikernas vinstförväntan med minst 10 % "
                  "och där aktien slagit marknaden med minst 2 % på rapportdagen. Håller 30 handelsdagar, stop-loss −10 %. Max 2 aktier.",
           "backtest": "Underkänd i backtest 2020–2023: Sharpe 0,25. Efter starka rapporter har svenska aktier i snitt inte fortsatt uppåt.",
           "make": lambda earn: E.ReportDrift(earnings=earn)},
    "S7": {"name": "Volymlyft", "universe": "all",
           "how": "Köper dagen efter att en aktie slagit marknaden med minst 4 % på minst 3 gånger normal volym. "
                  "Håller 30 handelsdagar, stop-loss −10 %. Max 2 aktier.",
           "backtest": "Underkänd i backtest 2006–2018: Sharpe 0,04, sämre än slumpen.",
           "make": lambda earn: E.VolumeSurge()},
    "SLUMP": {"name": "Slumpen", "universe": "all",
              "how": "Kontrollgrupp: köper slumpvisa aktier, håller 30 dagar, stop-loss −10 %. "
                     "En strategi som inte slår Slumpen över tid har ingen fördel.",
              "backtest": "Kontroll — ska inte ha någon fördel.",
              "make": lambda earn: E.RandomEvents(seed=0, rate=0.06)},
}
INFO_KEYS = {"trailingPE": "P/E", "forwardPE": "P/E (prognos)", "priceToBook": "P/B", "enterpriseToEbitda": "EV/EBITDA",
             "returnOnEquity": "ROE", "profitMargins": "Vinstmarginal", "debtToEquity": "Skuld/EK",
             "dividendYield": "Direktavk.", "revenueGrowth": "Omsättningstillväxt", "marketCap": "Börsvärde"}


# ------------------------------------------------------------------ data
def fetch_data(work: Path) -> Path:
    from .universe_fetch import download_earnings, download_prices, nasdaq_shares
    try:
        uni = nasdaq_shares()
        if len(uni) < 300:
            raise ValueError("short list")
    except Exception as e:  # noqa: BLE001
        print("Nasdaq list failed, using config/universe.csv:", e)
        uni = pd.read_csv("config/universe.csv")
    uni.to_csv(work / "universe.csv", index=False)
    start = (datetime.now(TZ) - timedelta(days=1150)).strftime("%Y-%m-%d")
    got = download_prices(uni["yahoo"].tolist() + ["^OMX"], work / "prices", start=start)
    # earnings only for liquid names (the only ones the strategies can trade)
    liquid = [t for t in got if t != "^OMX"]
    download_earnings(liquid).to_csv(work / "earnings.csv.gz", index=False, compression="gzip")
    return work


def _easter(y: int) -> date:
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(y, month, day + 1)


def se_holidays(y: int) -> set[date]:
    """Days Nasdaq Stockholm is closed on weekdays."""
    e = _easter(y)
    midsummer_eve = next(date(y, 6, d) for d in range(19, 26) if date(y, 6, d).weekday() == 4)
    return {date(y, 1, 1), date(y, 1, 6), e - timedelta(days=2), e + timedelta(days=1), date(y, 5, 1),
            e + timedelta(days=39), date(y, 6, 6), midsummer_eve, date(y, 12, 24), date(y, 12, 25),
            date(y, 12, 26), date(y, 12, 31)}


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in se_holidays(d.year)


def add_trading_days(d: date, n: int) -> date:
    while n > 0:
        d += timedelta(days=1)
        if is_trading_day(d):
            n -= 1
    return d


def first_trading_day_next_month(d: date) -> date:
    nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    while not is_trading_day(nxt):
        nxt += timedelta(days=1)
    return nxt


HOLD_RULES = {
    "S2": ("Upp till 5 handelsdagar", "Säljs tidigare om kursen studsar, alltså stänger över sitt 5-dagars snitt, eller om stop-lossen löser ut."),
    "S3": ("Minst till månadsskiftet", "Omprövas sista handelsdagen varje månad. Behålls så länge aktien är bland de 2 starkaste och marknaden ligger i upptrend."),
    "S6": ("30 handelsdagar, cirka 6 veckor", "Säljs tidigare bara om stop-lossen löser ut."),
    "S7": ("30 handelsdagar, cirka 6 veckor", "Säljs tidigare bara om stop-lossen löser ut."),
    "SLUMP": ("30 handelsdagar, cirka 6 veckor", "Säljs tidigare bara om stop-lossen löser ut."),
}


def planned_exit(key: str, entry: date, strat) -> tuple[date, str]:
    """Latest planned sale (at that day's open) for a position bought at the open of `entry`."""
    if key == "S3":
        return first_trading_day_next_month(entry), "omprövas"
    days = getattr(strat, "max_days", None) or getattr(strat, "hold", 30)
    return add_trading_days(entry, days), "senast"


def expected_last_session(now: datetime) -> pd.Timestamp:
    d = now.date()
    if now.hour < 18:                      # before today's bar is reliably available
        d -= timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return pd.Timestamp(d)


# ------------------------------------------------------------------ helpers
def r4(x):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), 4)


def valuation(ticker: str) -> dict:
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info or {}
        return {label: info.get(k) for k, label in INFO_KEYS.items() if info.get(k) is not None}
    except Exception:  # noqa: BLE001
        return {}


def recent_miss(earn: pd.DataFrame, ticker: str, asof: pd.Timestamp, days: int = 45):
    e = earn[(earn.ticker == ticker) & earn.surprise_pct.notna()].copy()
    if e.empty:
        return None
    e["d"] = pd.to_datetime(e["ts"], utc=True).dt.tz_convert(TZ).dt.tz_localize(None)
    e = e[(e.d <= asof + pd.Timedelta(days=1)) & (e.d >= asof - pd.Timedelta(days=days))]
    if e.empty:
        return None
    last = e.sort_values("d").iloc[-1]
    return {"date": str(last.d.date()), "surprise_pct": r4(last.surprise_pct)} if last.surprise_pct <= -10 else None


def last_report(earn: pd.DataFrame, ticker: str, asof: pd.Timestamp):
    e = earn[(earn.ticker == ticker)].copy()
    if e.empty:
        return None, None
    e["d"] = pd.to_datetime(e["ts"], utc=True).dt.tz_convert(TZ).dt.tz_localize(None)
    past = e[(e.d <= asof + pd.Timedelta(hours=23)) & e.surprise_pct.notna()].sort_values("d")
    fut = e[e.d > asof + pd.Timedelta(hours=23)].sort_values("d")
    lp = None if past.empty else {"date": str(past.iloc[-1].d.date()), "surprise_pct": r4(past.iloc[-1].surprise_pct),
                                  "eps": r4(past.iloc[-1].eps_reported), "estimate": r4(past.iloc[-1].eps_estimate)}
    nx = None if fut.empty else str(fut.iloc[0].d.date())
    return lp, nx


# ------------------------------------------------------------------ main run
def run(univ_dir: Path, out: Path, now: datetime | None = None) -> dict:
    now = now or datetime.now(TZ)
    uni = pd.read_csv(univ_dir / "universe.csv")
    names = dict(zip(uni["yahoo"], uni["name"]))
    full = D.load_universe_panel(univ_dir)
    omx_path = univ_dir / "prices" / "IDX_OMX.csv.gz"
    if "IDX_OMX" in full.tickers:      # the index is not a tradeable stock
        full = D.Panel({t: pd.DataFrame({k: full.f[k][t] for k in full.f}) for t in full.tickers if t != "IDX_OMX"},
                       full.calendar)
    large = [t for t in U.STOCKS if t in full.tickers]
    panels = {"all": full,
              "large": D.Panel({t: pd.DataFrame({k: full.f[k][t] for k in full.f}) for t in large}, full.calendar)}
    earn = D.load_earnings(univ_dir)
    cal = full.calendar
    asof = cal[-1]
    fs = pd.Timestamp(FORWARD_START)

    state = {"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "data_date": str(asof.date()), "expected_date": str(expected_last_session(now).date()),
             "forward_start": FORWARD_START, "capital": CAPITAL, "mode": "papper",
             "app_url": APP_URL, "strategies": {}, "actions": []}
    state["stale"] = asof < expected_last_session(now)

    # benchmarks over the forward-test period
    bench = {}
    if omx_path.exists():
        omx = pd.read_csv(omx_path, index_col="date", parse_dates=True)["close"].loc[fs:]
        bench["OMXS30"] = omx / omx.iloc[0] * CAPITAL if len(omx) else omx
    r = full.close.pct_change(fill_method=None)
    m = pd.DataFrame(E.event_eligible(full), index=r.index, columns=r.columns).shift(1, fill_value=False)
    ew = (1 + r.where(m).mean(axis=1).fillna(0).loc[fs:].iloc[1:]).cumprod()
    bench["Alla aktier (lika vikt)"] = pd.concat([pd.Series([1.0], index=[fs]), ew]) * CAPITAL if len(ew) else ew
    state["benchmarks"] = {k: {"dates": [str(d.date()) for d in v.index], "values": [r4(x) for x in v]} for k, v in bench.items()}

    vcache = {}
    for key, spec in STRATEGIES.items():
        panel = panels[spec["universe"]]
        strat = spec["make"](earn)
        res = S.run_stocks(strat, panel, COSTS, start=fs, capital=CAPITAL, live=True)
        meta = res.meta
        eq = res.equity
        i_last = len(cal) - 1
        cands = {t: sc for sc, t in strat.cands[i_last]} if hasattr(strat, "cands") else {}
        held = {p["ticker"]: p for p in meta["open"]}
        actions = []
        for t in meta["next"]:
            if t in held:
                continue
            j = panel.close.columns.get_loc(t)
            last = float(panel.raw_close[t].iloc[-1])
            reason = {"S2": "Kraftig dipp i upptrend (RSI(2) under 10)", "S3": "Bland de 2 starkaste senaste 12 mån",
                      "S7": f"Volym {cands.get(t, 0):.1f}× normalt och slog marknaden".replace(".", ",", 1),
                      "S6": f"Rapport slog förväntan med {cands.get(t, 0):.0f} % och aktien steg",
                      "SLUMP": "Slumpvis vald (kontroll)"}[key]
            lp, nx = last_report(earn, t, asof)
            if t not in vcache:
                vcache[t] = valuation(t)
            buy_day = add_trading_days(asof.date(), 1)
            sell_by, kind = planned_exit(key, buy_day, strat)
            actions.append({"strategy": key, "action": "KÖP", "ticker": t, "name": names.get(t, t),
                            "last_close": r4(last), "limit": r4(last * 1.02),
                            "stop_pct": getattr(strat, "stop", 0.0), "reason": reason,
                            "weight": r4(1 / getattr(strat, "max_positions", getattr(strat, "top_n", 2))),
                            "last_report": lp, "next_report": nx, "report_miss": recent_miss(earn, t, asof),
                            "valuation": vcache[t], "buy_day": str(buy_day),
                            "hold": HOLD_RULES[key][0], "hold_detail": HOLD_RULES[key][1],
                            "sell_by": str(sell_by), "sell_by_kind": kind})
        for t, p in held.items():
            if t not in meta["next"]:
                why = "Hålltiden är slut" if key in ("S6", "S7", "SLUMP") else "Säljsignal enligt reglerna"
                if key == "S2" and p["days_held"] < getattr(strat, "max_days", 5):
                    why = "Kursen har studsat över 5-dagars snitt"
                actions.append({"strategy": key, "action": "SÄLJ", "ticker": t, "name": names.get(t, t),
                                "last_close": r4(float(panel.raw_close[t].iloc[-1])), "reason": why,
                                "days_held": p["days_held"]})
        st = M.stats(eq, res.trades if len(res.trades) else None, res.costs_paid, res.exposure) if len(eq) > 1 else {}
        trades = []
        for tr in res.trades.to_dict("records") if len(res.trades) else []:
            if tr["why"] == "end":
                continue
            trades.append({"ticker": tr["ticker"], "name": names.get(tr["ticker"], tr["ticker"]),
                           "entry": str(pd.Timestamp(tr["entry"]).date()), "exit": str(pd.Timestamp(tr["exit"]).date()),
                           "why": {"signal": "regel", "stop": "stop-loss", "stop_gap": "stop-loss (gap)"}.get(tr["why"], tr["why"]),
                           "ret": r4(tr["ret"]), "pnl": r4(tr["pnl"])})
        positions = []
        for p in meta["open"]:
            # entry_px is adjusted; express returns in % so they are valid regardless of adjustment
            ret = p["shares"] * p["last"] / p["cost_in"] - 1
            sb, kind = planned_exit(key, date.fromisoformat(p["entry_date"]), strat)
            positions.append({"sell_by": str(sb), "sell_by_kind": kind,"ticker": p["ticker"], "name": names.get(p["ticker"], p["ticker"]),
                              "entry_date": p["entry_date"], "days_held": p["days_held"],
                              "value": r4(p["shares"] * p["last"]), "ret": r4(ret),
                              "stop_dist": r4(p["last"] / p["stop_px"] - 1) if p["stop_px"] else None})
        state["strategies"][key] = {
            "name": spec["name"], "how": spec["how"], "backtest": spec["backtest"],
            "hold": HOLD_RULES[key][0], "hold_detail": HOLD_RULES[key][1],
            "equity": {"dates": [str(d.date()) for d in eq.index], "values": [r4(x) for x in eq]},
            "value": r4(eq.iloc[-1]) if len(eq) else CAPITAL, "cash": r4(meta["cash"]),
            "ret": r4(eq.iloc[-1] / CAPITAL - 1) if len(eq) else 0.0,
            "max_dd": r4(st.get("max_dd")), "n_trades": len(trades),
            "win_rate": r4(np.mean([t["ret"] > 0 for t in trades])) if trades else None,
            "positions": positions, "trades": trades[-30:][::-1], "actions": actions,
        }
        state["actions"] += actions

    out.mkdir(parents=True, exist_ok=True)
    (out / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=1))
    return state


def push(state: dict):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print("NTFY_TOPIC not set: no push")
        return
    import requests
    acts = state["actions"]
    if state.get("stale"):
        title, body = "Signalagenten: data saknas", f"Senaste kursdata är från {state['data_date']}. Inga nya signaler i kväll."
    elif not acts:
        return
    else:
        title = f"Signalagenten: {len(acts)} signal{'er' if len(acts) > 1 else ''} (papper)"
        lines = []
        for a in acts[:8]:
            name = state["strategies"][a["strategy"]]["name"]
            if a["action"] == "KÖP":
                sb = date.fromisoformat(a["sell_by"])
                when = ("omprövas " if a["sell_by_kind"] == "omprövas" else "sälj senast ") + f"{sb.day}/{sb.month}"
                lines.append(f"KÖP {a['name']} · {name} · limit {a['limit']:.2f} kr · {when}".replace(".", ","))
            else:
                lines.append(f"SÄLJ {a['name']} · {name}")
        body = "\n".join(lines) + "\nPappersportfölj: ingen riktig affär behövs."
    requests.post(f"https://ntfy.sh/{topic}", data=body.encode("utf-8"), timeout=20,
                  headers={"Title": title.encode("latin-1", "replace"), "Click": APP_URL, "Tags": "chart_with_upwards_trend"})
    print("pushed:", title)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="live")
    ap.add_argument("--universe", default=None, help="use downloaded data instead of fetching")
    ap.add_argument("--no-push", action="store_true")
    a = ap.parse_args()
    if a.universe:
        udir = Path(a.universe)
    else:
        udir = fetch_data(Path(tempfile.mkdtemp()))
    st = run(udir, Path(a.out))
    print(json.dumps({k: st[k] for k in ("data_date", "expected_date", "stale")}),
          f"{len(st['actions'])} actions")
    for k, s in st["strategies"].items():
        print(k, s["name"], s["value"], len(s["positions"]), "positions", len(s["actions"]), "actions")
    if not a.no_push:
        push(st)


if __name__ == "__main__":
    main()
