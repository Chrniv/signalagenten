# Signalagenten

A personal signal agent for Avanza. It tells you **what to buy and sell and when**; you place the orders yourself in the Avanza app. Swedish stocks and funds only. It never logs in to Avanza.

**Status:** Gate 2 — research. No signals are sent until a strategy passes the held-out test.

## How it works (when finished)
1. Every weekday evening a GitHub Action fetches the day's closing prices and runs the strategy rules.
2. If there's something to do, your phone gets a push notification: what, how much, limit price and stop-loss.
3. You place the order in Avanza (stocks run in the 09:00 opening auction; fund orders before 15:00 get that day's price).
4. You confirm it in the app ("Jag har köpt" + price). The agent always works from what you actually hold.

## Strategies under test
| | Strategy | Instruments | Rhythm |
|---|---|---|---|
| S1 | Fund rotation: Swedish vs global index fund vs cash, by momentum + trend filter | Index funds | Weekly |
| S2 | Short-term mean reversion: buy sharp dips in uptrending large caps, exit on bounce or after 5 days | OMXS30 stocks | Daily, 2–5 day holds |
| S3 | Stock momentum: hold the 2 strongest stocks while the market is above trend | OMXS30 stocks | Monthly |
| S4 | Turn of the month: own the Swedish index fund around month end | Index fund | Monthly |
| S5 | Random entries (control — should fail) | OMXS30 stocks | Daily |

Pre-registered rules, thresholds and risk limits: see `SPEC_v2_avanza.md` (in the project files). Development period: start of data → 2018-12-31. Held-out period 2019-01-01 → 2026-09-30, used **once**, unlocked by `research/HOLDOUT_UNLOCK.json`.

## Layout
```
engine/universe.py     stocks and fund proxies
engine/data.py         download (Actions) and load prices
engine/indicators.py   causal indicators
engine/strategies.py   S1–S5 rules
engine/sim.py          daily simulators: stocks (next-open fills, stops, Avanza courtage) and funds (NAV, settlement)
engine/metrics.py      Sharpe, drawdown, profit factor, deflated Sharpe
engine/research.py     runs every variant, writes reports/report_dev.md
tests/                 look-ahead guards, fills, stops, costs, fund timing
.github/workflows/fetch-data.yml   downloads data, tests, research → `data` branch
```

## Run locally
```
pip install -r requirements.txt
python -m pytest -q
python -m engine.research --data data --out reports
```

## Known limitations (read before trusting any number)
- **Survivorship:** Yahoo has no delisted Swedish stocks. Stock strategies must clear a higher Sharpe bar and beat an equal-weight portfolio of the same stocks.
- **Fund proxies:** funds are approximated by indices (S&P 500 TR in SEK for the global fund unless a better series is available). Fees are deducted; tracking differences are not modelled.
- **Fractional shares in backtests:** historical prices are split-adjusted, so whole-share rounding is checked on today's prices instead (report section "Whole shares").
- **Costs:** spread (0.10 % per side) and fund settlement (2 days) are assumptions; both are stress-tested.
