import math

import numpy as np
import pandas as pd
import pytest

from engine import data as D
from engine import metrics as M
from engine import sim as S
from engine import strategies as ST
from tests.synthetic import write_synthetic


@pytest.fixture(scope="module")
def ddir(tmp_path_factory):
    return write_synthetic(tmp_path_factory.mktemp("data"))


@pytest.fixture(scope="module")
def panel(ddir):
    return D.load_stock_panel(ddir)


@pytest.fixture(scope="module")
def levels(ddir):
    lv, info = D.fund_series(ddir)
    return lv


STOCK_STRATS = [lambda: ST.MeanReversion(rsi_threshold=30), lambda: ST.StockMomentum(lookback=120, skip=10, market_ma=50),
                lambda: ST.RandomEntry(seed=3, entry_prob=0.3)]


# ---------------------------------------------------------------- look-ahead guards
# The decision on day d must be identical whether or not prices after d exist.
SAMPLE_DAYS = [420, 555, 700, 801, 950, 1100, 1250, 1400]


@pytest.mark.parametrize("make", STOCK_STRATS)
def test_stock_decisions_never_use_future_prices(panel, make):
    full = make()
    full.prepare(panel)
    some = panel.tickers[0]
    for i in SAMPLE_DAYS:
        cut = panel.calendar[i]
        trunc = make()
        trunc.prepare(panel.truncate(cut))
        for positions in ({}, {some: {"entry_i": i - 2}}):
            assert full.decide(i, positions) == trunc.decide(i, positions), (full.name, cut)


@pytest.mark.parametrize("make", [lambda: ST.FundRotation(lookback=60, trend_ma=100), lambda: ST.TurnOfMonth()])
def test_fund_decisions_never_use_future_prices(levels, make):
    cal = levels.index
    full = make().targets(S.signal_view(levels), cal)
    for i in SAMPLE_DAYS:
        cut = cal[i]
        lv = levels.copy()
        lv.loc[lv.index > cut] = np.nan
        trunc = make().targets(S.signal_view(lv), cal)
        assert full.get(cut) == trunc.get(cut), cut


def test_lookahead_guard_catches_a_cheater(panel):
    class Cheat(ST.MeanReversion):
        def prepare(self, p):
            super().prepare(p)
            self.fut = (p.close.shift(-1) > p.close).to_numpy()

        def decide(self, i, positions):
            return {t: 0.5 for j, t in enumerate(self.tickers) if self.fut[i, j]}

    full = Cheat()
    full.prepare(panel)
    caught = 0
    for i in SAMPLE_DAYS:
        t = Cheat()
        t.prepare(panel.truncate(panel.calendar[i]))
        caught += full.decide(i, {}) != t.decide(i, {})
    assert caught > 0


def test_global_fund_signal_is_lagged_one_day(levels):
    v = S.signal_view(levels)
    assert v["GLOBAL_EQ"].iloc[10] == levels["GLOBAL_EQ"].iloc[9]
    assert v["SE_EQ"].iloc[10] == levels["SE_EQ"].iloc[10]


# ---------------------------------------------------------------- costs and fills
def test_courtage_classes():
    assert S.Costs(courtage="start").fee(500) == 0
    assert S.Costs(courtage="mini").fee(100) == 1.0          # minimum fee
    assert math.isclose(S.Costs(courtage="mini").fee(1000), 2.5)
    assert math.isclose(S.Costs(courtage="mini", mult=2).fee(1000), 5.0)


class _BuyOnce:
    name, kind, stop = "buy_once", "stock", 0.08

    def __init__(self, t, day):
        self.t, self.day = t, day

    def prepare(self, panel):
        pass

    def decide(self, i, positions):
        return {self.t: 1.0} if i >= self.day else {}


def _flat_panel(rows):
    cal = pd.bdate_range("2020-01-01", periods=len(rows))
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=cal)
    df["volume"] = 1e9
    df["raw_close"] = df["close"]
    return D.Panel({"AAA.ST": df}, cal)


def test_stop_gap_fills_at_open_not_at_stop():
    rows = [(100, 100, 100, 100)] * 3 + [(100, 101, 99, 100), (80, 82, 79, 81), (81, 81, 81, 81)]
    p = _flat_panel(rows)
    res = S.run_stocks(_BuyOnce("AAA.ST", 2), p, S.Costs(courtage="start", half_spread=0))
    tr = res.trades.iloc[0]
    assert tr["why"] == "stop_gap" and math.isclose(tr["exit_px"], 80)


def test_intraday_stop_fills_at_stop():
    rows = [(100, 100, 100, 100)] * 3 + [(100, 101, 99, 100), (99, 99, 90, 95), (95, 95, 95, 95)]
    res = S.run_stocks(_BuyOnce("AAA.ST", 2), _flat_panel(rows), S.Costs(courtage="start", half_spread=0))
    tr = res.trades.iloc[0]
    assert tr["why"] == "stop" and math.isclose(tr["exit_px"], 92.0)


def test_fill_is_next_open_and_costs_reduce_equity():
    rows = [(100, 100, 100, 100)] * 3 + [(110, 110, 110, 110)] * 3
    free = S.run_stocks(_BuyOnce("AAA.ST", 2), _flat_panel(rows), S.Costs(courtage="start", half_spread=0))
    paid = S.run_stocks(_BuyOnce("AAA.ST", 2), _flat_panel(rows), S.Costs())
    # decided at close of day 2 (100), filled at open of day 3 (110): no gain
    assert math.isclose(free.equity.iloc[-1], 1000)
    assert paid.equity.iloc[-1] < 1000 and paid.costs_paid > 0


# ---------------------------------------------------------------- funds
def test_turn_of_month_window():
    cal = pd.bdate_range("2021-01-01", "2021-03-31")
    tg = ST.TurnOfMonth(days_before=4, days_after=3).targets(pd.DataFrame(index=cal), cal)
    jan = cal[cal.month == 1]
    feb = cal[cal.month == 2]
    # holding at the close of Jan's last 4 days and Feb's first 2 days
    held = {cal[cal.get_loc(d) + 1] for d, a in tg.items() if a == "SE_EQ"}
    assert set(jan[-4:]) <= held and set(feb[:2]) <= held
    assert feb[2] not in held and jan[-5] not in held


def test_fund_switch_waits_for_settlement(levels):
    class Flip:
        name, kind = "flip", "fund"

        def targets(self, lv, cal):
            return pd.Series({cal[100]: "SE_EQ", cal[200]: "GLOBAL_EQ"}, dtype=object)

    r = S.run_funds(Flip(), levels, S.Costs(settle_lag=2))
    t = r.trades
    assert t.iloc[0]["entry"] == levels.index[101] and t.iloc[0]["exit"] == levels.index[201]
    assert t.iloc[1]["entry"] == levels.index[203]


# ---------------------------------------------------------------- metrics
def test_deflated_sharpe_drops_with_more_trials():
    rng = np.random.default_rng(0)
    r = pd.Series(rng.normal(0.0004, 0.01, 2500))
    one = M.deflated_sharpe(r, 1, 0.0)
    many = M.deflated_sharpe(r, 200, 0.25)
    assert 0 < many < one < 1


def test_stats_basic():
    eq = pd.Series([100, 110, 99, 120], index=pd.bdate_range("2020-01-01", periods=4))
    s = M.stats(eq)
    assert math.isclose(s["max_dd"], 99 / 110 - 1)
