# Pre-registration — S6 Report drift and S7 Volume-surge drift

Written and committed **before** any S6/S7 backtest has been run (2026-10-25). Approved by Chris ("Go ahead", 11:13).
Changes after the first run are allowed only for bugs or data errors, and each must be listed in the report with the original kept in `research/archive/`.

## Universe
- All shares on Nasdaq Stockholm's main market (Large, Mid and Small Cap) per Nasdaq's public list on the download date (about 410), mapped to Yahoo symbols. **Survivorship-biased:** companies delisted before the download are missing.
- Tradeable on day *t* only if: at least 120 trading days of history, and a 60-day median daily turnover of at least 1 MSEK.

## S6 — Report drift (company data, 2020–2026)
- **Event:** a quarterly report in Yahoo's earnings calendar with an EPS estimate above 0 and a surprise ≥ **+10 %**.
- **Reaction day:** the report day if it was published before 09:00 Stockholm time; otherwise the next trading day.
- **Confirmation:** the stock's return on the reaction day, minus the equal-weight return of the universe that day, is ≥ **+2 %**.
- **Entry:** the open of the trading day after the reaction day (the signal is sent the evening of the reaction day).
- **Exit:** after **30** trading days, or a resting stop-loss at **−10 %** from entry.
- **Slots:** at most 2 positions, 50 % each. If there are more events than free slots, the largest surprises are taken first.
- **Neighbourhood (±25 %), 81 variants:** surprise {7.5, 10, 12.5} % × reaction {1.5, 2, 2.5} % × hold {22, 30, 38} days × stop {7.5, 10, 12.5} %.
- **Periods:** development 2020-11-01 → 2023-12-31; held-out 2024-01-01 → 2026-09-30 (one run).

## S7 — Volume-surge drift (prices only, 2006–2026)
- **Event:** the stock's day return minus the equal-weight universe return is ≥ **+4 %**, and volume is ≥ **3×** its average volume over the previous 50 days.
- **Entry, exit and slots:** as S6, with 30 days, −10 % stop and 2 slots. When there are more events than slots, the highest volume ratios are taken first.
- **Neighbourhood, 81 variants:** excess return {3, 4, 5} % × volume multiple {2.25, 3, 3.75} × hold {22, 30, 38} × stop {7.5, 10, 12.5} %.
- **Periods:** development 2006-01-02 → 2018-12-31 (opening prices before 2006 are broken); held-out 2019-01-01 → 2026-09-30.

## Control
- Random entries into the same universe, with a 30-day hold, a −10 % stop and 2 slots, at a frequency similar to S6/S7. 20 seeds. It should fail.

## Costs
- **Base:** Avanza **Start** (0 kr courtage), with fills at the next open.
- **Spread by liquidity, half-spread per side (assumption):** 60-day median turnover ≥ 100 MSEK: 0.05 %; 20–100: 0.10 %; 5–20: 0.20 %; 1–5: 0.40 %. The report compares these tiers with today's actual bid/ask spreads from Nasdaq.
- **Sensitivity:** 2× and 3× spread; Avanza Mini courtage (in case savings pass 50,000 kr); fills at the next close.

## Pass rules (unchanged from SPEC_v2)
Every one of these must hold:
- Sharpe > 0.7 net of costs
- Still positive at 2× costs
- Profit factor > 1.2
- At least 80 % of neighbours positive
- Deflated Sharpe > 0.90, with N = **every variant tested in this project so far** (126 + 81 + 81 = 288)
- Higher Sharpe than both the equal-weight universe of the same stocks and the Swedish index fund, measured over the same dates

Only strategies that pass on development data get the single held-out run.
