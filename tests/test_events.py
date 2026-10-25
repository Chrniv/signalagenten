import math

import numpy as np
import pandas as pd
import pytest

from engine import data as D
from engine import events as E
from engine import sim as S
from tests.synthetic import write_synthetic


@pytest.fixture(scope="module")
def panel(tmp_path_factory):
    p = D.load_stock_panel(write_synthetic(tmp_path_factory.mktemp("d"), n=1500, n_stocks=8))
    rng = np.random.default_rng(7)
    vol = p.f["volume"].copy()
    vol[:] = rng.lognormal(13, 0.3, vol.shape)
    # plant volume surges on up-days
    r = p.close.pct_change()
    surge = (r > 0.02) & (rng.random(vol.shape) < 0.5)
    p.f["volume"] = vol.where(~surge, vol * 5)
    return p


@pytest.fixture(scope="module")
def earnings(panel):
    rng = np.random.default_rng(3)
    rows = []
    for t in panel.tickers:
        for d in panel.calendar[200::63]:
            hour = 7 if rng.random() < 0.7 else 18
            ts = pd.Timestamp(d).tz_localize("Europe/Stockholm") + pd.Timedelta(hours=hour)
            rows.append({"ticker": t, "ts": ts.tz_convert("America/New_York").isoformat(),
                         "eps_estimate": 1.0, "eps_reported": 1.0 + rng.normal(0, 0.2),
                         "surprise_pct": rng.normal(5, 15)})
    return pd.DataFrame(rows)


def test_reaction_day_before_and_after_open(panel):
    cal = panel.calendar
    d = cal[300]
    e = pd.DataFrame([
        {"ticker": panel.tickers[0], "ts": (d.tz_localize("Europe/Stockholm") + pd.Timedelta(hours=7)).isoformat(),
         "eps_estimate": 1, "eps_reported": 1.2, "surprise_pct": 20},
        {"ticker": panel.tickers[1], "ts": (d.tz_localize("Europe/Stockholm") + pd.Timedelta(hours=18)).isoformat(),
         "eps_estimate": 1, "eps_reported": 1.2, "surprise_pct": 20},
        {"ticker": panel.tickers[2], "ts": (d.tz_localize("Europe/Stockholm") + pd.Timedelta(hours=7)).isoformat(),
         "eps_estimate": -1, "eps_reported": 1.2, "surprise_pct": 220},   # negative estimate: ignored
    ])
    ev = E.report_events(e, cal, panel.tickers).set_index("ticker")
    assert ev.loc[panel.tickers[0], "react_i"] == 300
    assert ev.loc[panel.tickers[1], "react_i"] == 301
    assert panel.tickers[2] not in ev.index


SAMPLE = [400, 520, 650, 777, 900, 1111, 1300]


@pytest.mark.parametrize("which", ["S6", "S7", "CTRL"])
def test_event_decisions_never_use_future_data(panel, earnings, which):
    def make():
        if which == "S6":
            return E.ReportDrift(earnings=earnings, surprise_min=5, reaction_min=0.0)
        if which == "S7":
            return E.VolumeSurge(excess_min=0.01, vol_mult=2.0)
        return E.RandomEvents(seed=1, rate=0.3)
    full = make()
    full.prepare(panel)
    n_cands = sum(1 for c in full.cands if c)
    assert n_cands > 10, "test needs events to be meaningful"
    t0 = panel.tickers[0]
    for i in SAMPLE:
        tr = make()
        tr.prepare(panel.truncate(panel.calendar[i]))
        for pos in ({}, {t0: {"entry_i": i - 5}}):
            assert full.decide(i, pos) == tr.decide(i, pos)


def test_hold_period_and_slots(panel):
    s = E.VolumeSurge(excess_min=0.01, vol_mult=2.0, hold=10)
    res = S.run_stocks(s, panel, S.Costs(courtage="start", half_spread=0))
    t = res.trades[res.trades.why == "signal"]
    held = [panel.calendar.get_loc(x) - panel.calendar.get_loc(y) for x, y in zip(t.exit, t.entry)]
    assert set(held) == {10}
    # never more than 2 positions at once
    days = pd.Series(0, index=panel.calendar)
    for r in res.trades.itertuples():
        days.loc[r.entry:r.exit] += 1
    assert days.max() <= 3   # exit and new entry can share a day


def test_tiered_spread():
    assert list(S.tier_half_spread(np.array([2e8, 5e7, 1e7, 2e6]))) == [0.0005, 0.0010, 0.0020, 0.0040]
