# Research report — development (in-sample)

Generated 2026-10-25 09:46 UTC · period None → 2018-12-31 · **126 variants tested** (all counted in the deflated Sharpe).

Base costs: Avanza Mini courtage (0.25 %, min 1 kr) + 0.10 % half-spread per side on stocks, fills at next day's open. Funds: no courtage, 0.15 %/yr fee, NAV of the next day, 2-day settlement on switches, 0 % on cash. Capital 1,000 kr, fractional shares.

Fund proxies: SE_EQ = ^OMX (price index + assumed dividend yield); GLOBAL_EQ = ^SP500TR (total return) x SEK=X

**Changes since run 1** (archived in research/archive/report_dev_run1.md): (1) stock calendar now built from the stocks themselves, and stock tests start in 2006 (Yahoo opening prices before 2006 are broken, see Data check); (2) the deflated Sharpe keeps the full trial count but uses each strategy's own Sharpe dispersion; (3) the benchmark check now follows the pre-registered spec (beat the Swedish index fund; stock strategies must also beat equal-weight of the same stocks). The global fund is shown for information.

## Summary

| Strategy | CAGR | Sharpe | Max DD | Trades/yr | Win rate | Profit factor | Cost share | Sharpe 2× costs | Neighbours >0 | Deflated Sharpe | Required benchmark Sharpe | Global fund Sharpe (info) | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S1_fund_rotation | 10.9% | 0.79 | -20.9% | 5.4 | 69% | 3.13 | 0% | 0.79 | 100% | 0.89 | 0.66 | 0.87 | **REJECT** |
| S2_mean_reversion | -6.4% | -0.08 | -85.5% | 86.2 | 49% | 0.94 | 111% | -0.86 | 10% | 0.00 | 0.66 | 0.87 | **REJECT** |
| S3_stock_momentum | 10.1% | 0.52 | -40.2% | 7.5 | 49% | 1.57 | 28% | 0.41 | 100% | 0.74 | 0.66 | 0.87 | **REJECT** |
| S4_turn_of_month | 4.2% | 0.41 | -16.8% | 12.2 | 53% | 1.28 | 0% | 0.41 | 100% | 0.73 | 0.66 | 0.87 | **REJECT** |

**Control (random entries, 20 seeds):** median Sharpe -1.37 (range -2.29 to -0.20), median CAGR -15.8%, 32 trades/yr; 0% of seeds clear the stock Sharpe bar. Equal-weight universe Sharpe: 0.60.

## Details

### S1_fund_rotation — REJECT

2008-11-20 → 2018-12-28 (10.1 yrs) · CAGR 10.9% · vol 14.4% · Sharpe 0.79 · Sortino 1.03 · max DD -20.9% · longest drawdown 426 trading days · time invested 79% · 54 trades · avg trade 2.15%

Sensitivity (Sharpe): settle_lag_0 0.78 · settle_lag_4 0.71 · cash_yield_2pct 0.82
Neighbourhood (9 variants): 100% positive, median Sharpe 0.65, worst 0.39
Benchmarks: B&H SE_EQ (2008–2018): CAGR 12.2%, Sharpe 0.66 vs strategy 0.79, max DD -25.9% · B&H GLOBAL_EQ (2008–2018): CAGR 15.8%, Sharpe 0.87 vs strategy 0.79, max DD -18.1%

| Check | Pass |
|---|---|
| sharpe > 0.5 | ✅ |
| positive at 2x costs | ✅ |
| profit factor > 1.2 | ✅ |
| >= 80% of neighbours positive | ✅ |
| deflated Sharpe > 0.9 | ❌ |
| beats B&H SE_EQ (Sharpe, same dates) | ✅ |

### S2_mean_reversion — REJECT

2006-01-02 → 2018-12-28 (13.0 yrs) · CAGR -6.4% · vol 32.8% · Sharpe -0.08 · Sortino -0.19 · max DD -85.5% · longest drawdown 2878 trading days · time invested 64% · 1121 trades · avg trade -0.07%

Sensitivity (Sharpe): start_class 0.62 · cost_3x -0.90 · fill_next_close -1.67
Neighbourhood (81 variants): 10% positive, median Sharpe -0.78, worst -1.74
Benchmarks: EW universe (2006–2018): CAGR 11.7%, Sharpe 0.60 vs strategy -0.08, max DD -58.5% · B&H SE_EQ (2008–2018): CAGR 12.2%, Sharpe 0.66 vs strategy -0.80, max DD -25.9% · B&H GLOBAL_EQ (2008–2018): CAGR 15.8%, Sharpe 0.87 vs strategy -0.80, max DD -18.1%

| Check | Pass |
|---|---|
| sharpe > 0.7 | ❌ |
| positive at 2x costs | ❌ |
| profit factor > 1.2 | ❌ |
| >= 80% of neighbours positive | ❌ |
| deflated Sharpe > 0.9 | ❌ |
| beats B&H SE_EQ and EW universe (Sharpe, same dates) | ❌ |

### S3_stock_momentum — REJECT

2006-01-02 → 2018-12-28 (13.0 yrs) · CAGR 10.1% · vol 24.3% · Sharpe 0.52 · Sortino 0.65 · max DD -40.2% · longest drawdown 930 trading days · time invested 78% · 97 trades · avg trade 3.17%

Sensitivity (Sharpe): start_class 0.60 · cost_3x 0.31 · fill_next_close 0.50
Neighbourhood (27 variants): 100% positive, median Sharpe 0.63, worst 0.42
Benchmarks: EW universe (2006–2018): CAGR 11.7%, Sharpe 0.60 vs strategy 0.52, max DD -58.5% · B&H SE_EQ (2008–2018): CAGR 12.2%, Sharpe 0.66 vs strategy 0.47, max DD -25.9% · B&H GLOBAL_EQ (2008–2018): CAGR 15.8%, Sharpe 0.87 vs strategy 0.47, max DD -18.1%

| Check | Pass |
|---|---|
| sharpe > 0.7 | ❌ |
| positive at 2x costs | ✅ |
| profit factor > 1.2 | ✅ |
| >= 80% of neighbours positive | ✅ |
| deflated Sharpe > 0.9 | ❌ |
| beats B&H SE_EQ and EW universe (Sharpe, same dates) | ❌ |

### S4_turn_of_month — REJECT

2008-11-20 → 2018-12-28 (10.1 yrs) · CAGR 4.2% · vol 11.8% · Sharpe 0.41 · Sortino 0.33 · max DD -16.8% · longest drawdown 1318 trading days · time invested 29% · 123 trades · avg trade 0.38%

Sensitivity (Sharpe): settle_lag_0 0.41 · settle_lag_4 0.41 · cash_yield_2pct 0.53
Neighbourhood (9 variants): 100% positive, median Sharpe 0.29, worst 0.15
Benchmarks: B&H SE_EQ (2008–2018): CAGR 12.2%, Sharpe 0.66 vs strategy 0.41, max DD -25.9% · B&H GLOBAL_EQ (2008–2018): CAGR 15.8%, Sharpe 0.87 vs strategy 0.41, max DD -18.1%

| Check | Pass |
|---|---|
| sharpe > 0.5 | ❌ |
| positive at 2x costs | ✅ |
| profit factor > 1.2 | ✅ |
| >= 80% of neighbours positive | ✅ |
| deflated Sharpe > 0.9 | ❌ |
| beats B&H SE_EQ (Sharpe, same dates) | ❌ |

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

## Data check: opening prices

Average annualised log return overnight vs intraday across our stocks. Real markets show values near zero; large opposite numbers mean the open prices are wrong. Stock tests start in 2006.

| Year | Overnight | Intraday |
|---|---|---|
| 2000 | -1.50 | +1.43 |
| 2001 | -1.73 | +1.75 |
| 2002 | -0.95 | +0.64 |
| 2003 | -0.84 | +1.18 |
| 2004 | -0.72 | +0.88 |
| 2005 | -0.40 | +0.76 |
| 2006 | +0.03 | +0.26 |
| 2007 | +0.10 | -0.15 |
| 2008 | +0.21 | -0.76 |
| 2009 | +0.43 | +0.08 |
| 2010 | +0.27 | -0.02 |
| 2011 | -0.08 | -0.09 |
| 2012 | +0.05 | +0.13 |
| 2013 | +0.09 | +0.13 |
| 2014 | +0.35 | +0.00 |
| 2015 | +0.22 | -0.05 |
| 2016 | +0.21 | -0.08 |
| 2017 | +0.12 | +0.01 |
| 2018 | +0.17 | -0.24 |
| 2019 | +0.14 | +0.22 |
| 2020 | +0.16 | -0.01 |
| 2021 | +0.22 | +0.08 |
| 2022 | +0.05 | -0.25 |
| 2023 | +0.09 | +0.05 |
| 2024 | +0.05 | -0.01 |
| 2025 | +0.16 | +0.00 |
| 2026 | +0.06 | +0.03 |

## Data

Downloaded 2026-10-25T09:44:56.868597+00:00; 52 tickers ok, failed: XACTOMXS30.ST.
Data warnings: ABB.ST: 2 daily moves >35%: 2002-10-22, 2002-11-04; ELUX-B.ST: 1 daily moves >35%: 2026-05-19; SBB-B.ST: 4 daily moves >35%: 2011-01-05, 2014-11-12, 2023-06-02, 2025-05-13; SINCH.ST: 1 daily moves >35%: 2022-11-02; ADDT-B.ST: 1 daily moves >35%: 2001-08-28; XACT-OMXS30.ST: rows with missing OHLC

*Survivorship: Yahoo has no delisted Swedish stocks, so S2/S3 and the EW universe are biased upward. S2/S3 need Sharpe > 0.7 and must beat the EW universe of the same stocks.*
*No numbers here are forecasts. Development-period results are used only to shortlist; the held-out period decides.*