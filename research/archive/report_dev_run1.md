# Research report — development (in-sample)

Generated 2026-10-25 09:39 UTC · period None → 2018-12-31 · **126 variants tested** (all counted in the deflated Sharpe).

Base costs: Avanza Mini courtage (0.25 %, min 1 kr) + 0.10 % half-spread per side on stocks, fills at next day's open. Funds: no courtage, 0.15 %/yr fee, NAV of the next day, 2-day settlement on switches, 0 % on cash. Capital 1,000 kr, fractional shares.

Fund proxies: SE_EQ = ^OMX (price index + assumed dividend yield); GLOBAL_EQ = ^SP500TR (total return) x SEK=X

## Summary

| Strategy | CAGR | Sharpe | Max DD | Trades/yr | Win rate | Profit factor | Cost share | Sharpe 2× costs | Neighbours >0 | Deflated Sharpe | Best benchmark Sharpe | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S1_fund_rotation | 10.9% | 0.79 | -20.9% | 5.4 | 69% | 3.13 | 0% | 0.79 | 100% | 0.00 | 0.87 | **REJECT** |
| S2_mean_reversion | -32.8% | -2.11 | -98.4% | 73.6 | 39% | 0.66 | 192% | -2.56 | 0% | 0.00 | 0.87 | **REJECT** |
| S3_stock_momentum | 3.7% | 0.28 | -40.2% | 7.8 | 44% | 1.24 | 46% | 0.15 | 100% | 0.00 | 0.87 | **REJECT** |
| S4_turn_of_month | 4.2% | 0.41 | -16.8% | 12.2 | 53% | 1.28 | 0% | 0.41 | 100% | 0.00 | 0.87 | **REJECT** |

**Control (random entries, 20 seeds):** median Sharpe -1.05 (range -2.59 to -0.61), median CAGR -10.5%, 29 trades/yr; 0% of seeds clear the stock Sharpe bar. Equal-weight universe Sharpe: 0.70.

## Details

### S1_fund_rotation — REJECT

2008-11-20 → 2018-12-28 (10.1 yrs) · CAGR 10.9% · vol 14.4% · Sharpe 0.79 · Sortino 1.03 · max DD -20.9% · longest drawdown 426 trading days · time invested 79% · 54 trades · avg trade 2.15%

Sensitivity (Sharpe): settle_lag_0 0.78 · settle_lag_4 0.71 · cash_yield_2pct 0.82
Neighbourhood (9 variants): 100% positive, median Sharpe 0.65, worst 0.39
Benchmarks: B&H SE_EQ: CAGR 12.2%, Sharpe 0.66, max DD -25.9% · B&H GLOBAL_EQ: CAGR 15.8%, Sharpe 0.87, max DD -18.1%

| Check | Pass |
|---|---|
| sharpe > 0.5 | ✅ |
| positive at 2x costs | ✅ |
| profit factor > 1.2 | ✅ |
| >= 80% of neighbours positive | ✅ |
| deflated Sharpe > 0.9 | ❌ |
| beats best benchmark Sharpe | ❌ |

### S2_mean_reversion — REJECT

2008-11-20 → 2018-12-28 (10.1 yrs) · CAGR -32.8% · vol 18.0% · Sharpe -2.11 · Sortino -2.08 · max DD -98.4% · longest drawdown 2254 trading days · time invested 55% · 740 trades · avg trade -1.03%

Sensitivity (Sharpe): start_class 0.58 · cost_3x -2.66 · fill_next_close -2.18
Neighbourhood (81 variants): 0% positive, median Sharpe -2.24, worst -2.49
Benchmarks: EW universe: CAGR 11.3%, Sharpe 0.70, max DD -27.7% · B&H SE_EQ: CAGR 12.2%, Sharpe 0.66, max DD -25.9% · B&H GLOBAL_EQ: CAGR 15.8%, Sharpe 0.87, max DD -18.1%

| Check | Pass |
|---|---|
| sharpe > 0.7 | ❌ |
| positive at 2x costs | ❌ |
| profit factor > 1.2 | ❌ |
| >= 80% of neighbours positive | ❌ |
| deflated Sharpe > 0.9 | ❌ |
| beats best benchmark Sharpe | ❌ |

### S3_stock_momentum — REJECT

2008-11-20 → 2018-12-28 (10.1 yrs) · CAGR 3.7% · vol 21.2% · Sharpe 0.28 · Sortino 0.36 · max DD -40.2% · longest drawdown 926 trading days · time invested 75% · 78 trades · avg trade 1.31%

Sensitivity (Sharpe): start_class 0.37 · cost_3x 0.03 · fill_next_close 0.25
Neighbourhood (27 variants): 100% positive, median Sharpe 0.43, worst 0.23
Benchmarks: EW universe: CAGR 11.3%, Sharpe 0.70, max DD -27.7% · B&H SE_EQ: CAGR 12.2%, Sharpe 0.66, max DD -25.9% · B&H GLOBAL_EQ: CAGR 15.8%, Sharpe 0.87, max DD -18.1%

| Check | Pass |
|---|---|
| sharpe > 0.7 | ❌ |
| positive at 2x costs | ✅ |
| profit factor > 1.2 | ✅ |
| >= 80% of neighbours positive | ✅ |
| deflated Sharpe > 0.9 | ❌ |
| beats best benchmark Sharpe | ❌ |

### S4_turn_of_month — REJECT

2008-11-20 → 2018-12-28 (10.1 yrs) · CAGR 4.2% · vol 11.8% · Sharpe 0.41 · Sortino 0.33 · max DD -16.8% · longest drawdown 1318 trading days · time invested 29% · 123 trades · avg trade 0.38%

Sensitivity (Sharpe): settle_lag_0 0.41 · settle_lag_4 0.41 · cash_yield_2pct 0.53
Neighbourhood (9 variants): 100% positive, median Sharpe 0.29, worst 0.15
Benchmarks: B&H SE_EQ: CAGR 12.2%, Sharpe 0.66, max DD -25.9% · B&H GLOBAL_EQ: CAGR 15.8%, Sharpe 0.87, max DD -18.1%

| Check | Pass |
|---|---|
| sharpe > 0.5 | ❌ |
| positive at 2x costs | ✅ |
| profit factor > 1.2 | ✅ |
| >= 80% of neighbours positive | ✅ |
| deflated Sharpe > 0.9 | ❌ |
| beats best benchmark Sharpe | ❌ |

## Whole shares at today's prices

Stocks priced above 500 kr can't be bought with half of a 1,000 kr budget (S2 uses 2 slots).

| Ticker | Price | Shares for 500 kr | Shares for 1,000 kr |
|---|---|---|---|
| SBB-B.ST | 2.6 | 192 | 384 |
| ELUX-B.ST | 26.37 | 18 | 37 |
| NIBE-B.ST | 44.44 | 11 | 22 |
| SINCH.ST | 46.44 | 10 | 21 |
| TELIA.ST | 48.23 | 10 | 20 |
| KINV-B.ST | 68.38 | 7 | 14 |
| SSAB-A.ST | 97.86 | 5 | 10 |
| ERIC-B.ST | 105.05 | 4 | 9 |
| HEXA-B.ST | 106.05 | 4 | 9 |
| SCA-B.ST | 124.9 | 4 | 8 |
| SHB-A.ST | 149.85 | 3 | 6 |
| SECU-B.ST | 156.5 | 3 | 6 |
| ATCO-B.ST | 156.8 | 3 | 6 |
| TEL2-B.ST | 159.85 | 3 | 6 |
| NDA-SE.ST | 169.9 | 2 | 5 |
| HM-B.ST | 174.9 | 2 | 5 |
| ATCO-A.ST | 176.3 | 2 | 5 |
| SEB-A.ST | 201.1 | 2 | 4 |
| EPI-A.ST | 250.7 | 1 | 3 |
| GETI-B.ST | 267.7 | 1 | 3 |
| SKF-B.ST | 269.5 | 1 | 3 |
| SKA-B.ST | 270.7 | 1 | 3 |
| ESSITY-B.ST | 276.6 | 1 | 3 |
| AXFO.ST | 278.4 | 1 | 3 |
| LIFCO-B.ST | 280.4 | 1 | 3 |
| ADDT-B.ST | 300.2 | 1 | 3 |
| VOLV-B.ST | 307.7 | 1 | 3 |
| SAND.ST | 346.6 | 1 | 2 |
| ASSA-B.ST | 369.5 | 1 | 2 |
| SWED-A.ST | 379.0 | 1 | 2 |
| INVE-B.ST | 412.0 | 1 | 2 |
| TREL-B.ST | 450.4 | 1 | 2 |
| BOL.ST | 483.2 | 1 | 2 |
| INDU-C.ST | 502.8 | 0 | 1 |
| ALFA.ST | 539.8 | 0 | 1 |
| LUND-B.ST | 564.0 | 0 | 1 |
| SAAB-B.ST | 646.5 | 0 | 1 |
| ABB.ST | 817.0 | 0 | 1 |
| EVO.ST | 841.4 | 0 | 1 |
| AZN.ST | 1692.5 | 0 | 0 |

## Data

Downloaded 2026-10-25T09:38:36.248823+00:00; 52 tickers ok, failed: XACTOMXS30.ST.
Data warnings: ABB.ST: 2 daily moves >35%: 2002-10-22, 2002-11-04; ELUX-B.ST: 1 daily moves >35%: 2026-05-19; SBB-B.ST: 4 daily moves >35%: 2011-01-05, 2014-11-12, 2023-06-02, 2025-05-13; SINCH.ST: 1 daily moves >35%: 2022-11-02; ADDT-B.ST: 1 daily moves >35%: 2001-08-28; XACT-OMXS30.ST: rows with missing OHLC

*Survivorship: Yahoo has no delisted Swedish stocks, so S2/S3 and the EW universe are biased upward. S2/S3 need Sharpe > 0.7 and must beat the EW universe of the same stocks.*
*No numbers here are forecasts. Development-period results are used only to shortlist; the held-out period decides.*