# Report drift (S6) and volume-surge drift (S7) — development period

Generated 2026-10-25 10:33 UTC. Rules: research/PREREG_S6_S7.md (committed before this run). Deflated Sharpe uses N = 288 (every variant tested in the project).

Costs: Avanza Start (0 kr courtage), half-spread by liquidity tier, fills at the next open, 1,000 kr, 2 slots.

| Strategy | Period | CAGR | Sharpe | Max DD | Trades/yr | Win rate | Profit factor | Avg trade | Sharpe 2× spread | Sharpe w/ Mini | Neighbours >0 | Deflated Sharpe | EW universe Sharpe | Index fund Sharpe | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S6_report_drift | 2020-11-02 → 2023-12-29 | 3.0% | 0.25 | -44.6% | 14.5 | 41% | 1.08 | 0.85% | 0.06 | 0.09 | 84% | 0.15 | 0.58 | 0.82 | **REJECT** |
| S7_volume_surge | 2006-01-02 → 2018-12-28 | -4.8% | 0.04 | -79.9% | 22.5 | 40% | 0.94 | 0.25% | -0.24 | -0.19 | 78% | 0.02 | 0.68 | 0.66 | **REJECT** |

### S6_report_drift — REJECT

CAGR 3.0% · vol 23.6% · Sharpe 0.25 · Sortino 0.31 · max DD -44.6% · longest drawdown 536 days · invested 77% of the time · 46 trades · exits: {'signal': 26, 'stop': 19, 'stop_gap': 1}

Sensitivity: cost_2x: Sharpe 0.06 · cost_3x: Sharpe 0.11 · mini_courtage: Sharpe 0.09 · fill_next_close: Sharpe -0.06
Neighbourhood (81): 84% positive, median 0.22, worst -0.38
Benchmarks (same dates): EW universe: CAGR 10.1%, Sharpe 0.58 (strategy 0.25), max DD -35.4% · B&H SE_EQ: CAGR 13.7%, Sharpe 0.82 (strategy 0.25), max DD -25.4%
Random control (20 seeds, same opportunity rate): median Sharpe 0.06 (range -1.17 to 0.62), median CAGR -2.4%, 19 trades/yr, 0% clear the Sharpe bar.

| Check | Pass |
|---|---|
| Sharpe > 0.7 | ❌ |
| positive at 2x costs | ✅ |
| profit factor > 1.2 | ❌ |
| >= 80% of neighbours positive | ✅ |
| deflated Sharpe > 0.9 (N=288) | ❌ |
| beats EW universe and Swedish index fund (Sharpe, same dates) | ❌ |

Last trades in the period: G5EN.ST 2023-08-11→2023-08-21 stop -10.4%; ARJO-B.ST 2023-07-17→2023-08-28 signal -6.0%; SYNSAM.ST 2023-08-23→2023-09-26 stop -10.4%; SYSR.ST 2023-09-04→2023-10-03 stop -10.4%; ATRLJ-B.ST 2023-10-13→2023-10-20 stop -10.2%; SHB-A.ST 2023-10-19→2023-10-26 stop -10.0%; WALL-B.ST 2023-10-23→2023-12-04 signal 24.9%; ESSITY-B.ST 2023-10-27→2023-12-08 signal 5.0%

### S7_volume_surge — REJECT

CAGR -4.8% · vol 36.0% · Sharpe 0.04 · Sortino 0.06 · max DD -79.9% · longest drawdown 2990 days · invested 97% of the time · 292 trades · exits: {'signal': 153, 'stop': 126, 'stop_gap': 12, 'end': 1}

Sensitivity: cost_2x: Sharpe -0.24 · cost_3x: Sharpe -0.35 · mini_courtage: Sharpe -0.19 · fill_next_close: Sharpe -0.03
Neighbourhood (81): 78% positive, median 0.16, worst -0.53
Benchmarks (same dates): EW universe: CAGR 12.5%, Sharpe 0.68 (strategy 0.04), max DD -59.0% · B&H SE_EQ: CAGR 12.2%, Sharpe 0.66 (strategy 0.27), max DD -25.9%
Random control (20 seeds, same opportunity rate): median Sharpe 0.13 (range -0.15 to 0.56), median CAGR -0.5%, 20 trades/yr, 0% clear the Sharpe bar.

| Check | Pass |
|---|---|
| Sharpe > 0.7 | ❌ |
| positive at 2x costs | ❌ |
| profit factor > 1.2 | ❌ |
| >= 80% of neighbours positive | ❌ |
| deflated Sharpe > 0.9 (N=288) | ❌ |
| beats EW universe and Swedish index fund (Sharpe, same dates) | ❌ |

Last trades in the period: SKIS-B.ST 2018-10-04→2018-11-15 signal -3.6%; EMBRAC-B.ST 2018-11-15→2018-11-20 stop -10.1%; STAR-B.ST 2018-11-22→2018-11-23 stop_gap -23.0%; RROS.ST 2018-10-25→2018-12-05 stop -10.4%; STAR-A.ST 2018-12-06→2018-12-06 stop -10.4%; STAR-A.ST 2018-12-14→2018-12-14 stop -10.4%; BINV.ST 2018-12-19→2018-12-28 stop -10.4%; STEF-B.ST 2018-11-28→2018-12-28 end -0.9%

## Data checks

Usable reports: 8622 from 307 companies, first 2004-07-19; 71% published before 09:00; 2639 with surprise ≥ +10 %.

Average 30-day return after the reaction day, versus equal-weight market, by EPS surprise (all reports, before costs — descriptive only):

| Surprise | Reports | Mean excess | Median excess |
|---|---|---|---|
| < -10% | 2872 | -1.4% | -1.6% |
| -10..-2% | 1145 | -0.3% | -0.5% |
| -2..+2% | 703 | -0.7% | -0.8% |
| +2..+10% | 1180 | -0.5% | -0.9% |
| > +10% | 2589 | 0.2% | -0.5% |

Spread model vs today's real bid/ask (Nasdaq, half-spread):

| Model tier | Stocks | Actual median | Actual 75th pct |
|---|---|---|---|
| 0.05% | 44 | 0.04% | 0.07% |
| 0.10% | 78 | 0.09% | 0.14% |
| 0.20% | 84 | 0.14% | 0.24% |
| 0.40% | 188 | 0.46% | 0.78% |

*Survivorship: the universe is today's listed companies. Delisted companies are missing, which flatters both strategies and the EW benchmark. Nothing here is a forecast.*