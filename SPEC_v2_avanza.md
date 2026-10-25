# Gate 1 (revised) — Signal Agent for Manual Trading on Avanza

**Status:** awaiting Chris's approval · **Date:** 2026-10-25 · **Replaces** the Kraken spec as the live plan. Kraken stays available as an optional crypto track later.
> **Update 2026-10-25 (approved by Chris):** stocks and funds only, all within Avanza — no crypto, gold or ETPs. S1 now rotates between a Swedish index fund, a global index fund and cash (fixed income fund). Funds trade at the day's NAV (orders before 15:00), with no courtage. Courtage class unknown, so both Mini and Start are tested. Notifications via push to an installable phone app (as Tipsmotorn), with fills confirmed in the app instead of Telegram.

**Rule:** no performance numbers exist yet. Anything marked *assumption* or *estimate* is mine and has not been measured.

---

## 1. What changes

| | Before (Kraken spec) | Now |
|---|---|---|
| Who places orders | The agent, through the API | **Chris, by hand in the Avanza app.** The agent only sends signals |
| Account | Kraken Futures | **Avanza ISK.** No K4 per trade, and 1,000 kr is far below the tax-free level |
| Market | Crypto perps, 24/7 | **Nasdaq Stockholm instruments**: large-cap stocks, Stockholm-listed ETFs, crypto ETPs (e.g. Virtune VIRBTCP [1]) |
| Signal timing | Hourly / daily | **Once a day after the close (~17:30)**, with orders placed that evening for the next morning's opening auction |
| Credentials | Trade-only API key | **None.** The agent never touches Avanza, so no login is stored anywhere |
| Budget | USD 5k paper | **1,000 kr real money** after the backtest gate, then a pre-agreed ladder (§8) |

## 2. Why daily/weekly and not day trading

"Most profitable" is something the tests decide, not something I can promise. But the evidence going in strongly favours slower strategies for this setup:

1. **The base rates are brutal.** In Brazil, 97% of people who day-traded index futures for more than 300 days lost money [2]. In Taiwan, fewer than 1% of day traders were reliably profitable after fees [3].
2. **Manual execution doesn't suit it.** Day trading needs someone reacting during market hours, and Chris has a day job. A signal that arrives at 18:00 and is executed in the 09:00 opening auction takes about a minute and needs no screen time.
3. **Costs grow with turnover.** On Avanza's Mini class, a trade costs 0.25% (min 1 kr) [4], plus the spread. A strategy trading daily pays that about 250 times a year, and a weekly one about 25 times.
4. **We can't test it properly.** There is no free historical intraday data for Stockholm stocks, and we don't trade anything we can't backtest.

So every candidate below works on **daily bars**, with **holding periods from 2 days to several weeks**. One candidate (S2) is the closest thing to "day trading" that this setup can test honestly.

## 3. How a signal reaches Chris (the agent loop)

```
18:30 Stockholm (Mon–Fri)               07:30 (Mon–Fri)
┌──────────────────────────┐            ┌──────────────────────────┐
│ fetch today's closes     │            │ read Chris's replies     │
│ read confirmed positions │            │ resend reminder if an    │
│ compute signals (rules)  │            │ action is still open     │
│ size in whole shares     │            └──────────────────────────┘
│ risk checks              │
│ send Telegram message    │──► Chris places the order in Avanza (runs in 09:00 auction)
│ log everything           │◄── Chris replies: /fill BUY VIRBTCP 3 @ 41.20  or /skip
└──────────────────────────┘
```

- **Message format** (example only; illustrative numbers, not a recommendation):
  `BUY 3 × VIRBTCP — limit 42.00 kr (last close 41.35 + 1.5%) · stop-loss 38.10 kr · reason: S1 rotation, BTC 6m momentum ranked #1 and price above its 200-day MA · strategy S1`
- It only messages when an action is needed. A short summary arrives every Sunday, so no message means nothing to do.
- **Chris's replies decide what the agent thinks he holds.** If he skips or misses a signal, the agent works from his real position, not the theoretical one, and logs how often signals were acted on.
- **Commands:** `/fill`, `/skip`, `/positions`, `/pause` (stops new buy signals until `/resume`), `/status`.
- **Stops:** every buy signal includes a stop level, which Chris enters as a stop-loss order in Avanza [5]. That way the stop works even if the agent goes down. Note that in a gap, a stop fills at the next available price, not at the stop level.
- **Hosting:** a GitHub Actions scheduled workflow runs the agent. It's free and needs no server; the code, positions file and logs live in a private repo. Telegram bots are free. *Note:* GitHub's schedules run in UTC and can start a few minutes late, which doesn't matter for daily signals.
- **No LLM in the signal path.** Signals come only from tested, deterministic rules. An LLM may write the Sunday summary text if wanted.

## 4. Candidate strategies (rules only, nothing tested yet)

All of them compute signals on the daily close and fill at the **next day's open** in the backtest, which matches the opening-auction workflow. Parameters are starting points, and the ±25% sweep tests them.

### S1. Weekly trend rotation (ETFs/ETPs, 1 position)
- **Edge:** Momentum across asset classes, combined with a trend filter to stay out of falling markets [L1][L2].
- **Universe:** Stockholm-listed instruments tracking Swedish equities (OMXS30), gold, and bitcoin, plus cash. *Research* uses the underlying prices converted to SEK (OMXS30 index, gold, BTC) for long history. Avanza tickers are confirmed at Gate 2.
- **Rule:** Every Friday close, rank the assets by 6-month return. Hold the top one if it is above its 200-day moving average, otherwise hold cash. Trade on Monday morning.
- **Size:** A volatility cap of 25% annualised. For example, a bitcoin ETP at about 60% volatility gets roughly 40% of the budget, and the rest stays in cash.
- **Frequency (*estimate*):** 6–15 trades a year. **Cost sensitivity:** low.
- **Risks:** Whipsaw in sideways markets. With only three assets, one asset can dominate results, and bitcoin history only goes back to 2014.

### S2. Short-term mean reversion (OMXS30 stocks, 1–2 positions) — the "active" candidate
- **Edge:** Short-term overreaction. Liquidity providers get paid for buying sharp dips in quality large caps [L3].
- **Rule:** Buy when the stock is above its 200-day MA and RSI(2) is below 10. Sell when the close is above its 5-day MA, or after 5 trading days. Stop at −8%.
- **Frequency (*estimate*):** 30–80 trades a year. Holding period: 2–5 days.
- **Cost sensitivity:** **high.** This is the strategy most likely to be killed by courtage and spread.
- **Risks:** Survivorship bias (§6), and the edge has been widely published, so it may have decayed. It also catches falling knives on real bad news.

### S3. Monthly stock momentum (OMXS30 stocks, 1–2 positions)
- **Edge:** Winners keep winning over 3–12 months, documented across markets [L4].
- **Rule:** At month end, hold the 1–2 stocks with the highest 12-month return excluding the latest month, but only while OMXS30 is above its 200-day MA. Otherwise hold cash.
- **Frequency:** about 10–24 trades a year. **Cost sensitivity:** low to medium.
- **Risks:** Very concentrated at 1,000 kr, so one stock decides the year. Momentum crashes happen at market turns. Survivorship bias.

### S4. Turn-of-month (OMXS30 ETF)
- **Edge:** Equity returns cluster around the turn of the month, plausibly because of salary and pension flows. This is documented across many countries [L5].
- **Rule:** Buy at the close 4 trading days before month end (in practice at the next open) and sell after the 3rd trading day of the new month.
- **Frequency:** about 24 trades a year, and invested only about 35% of the time. **Cost sensitivity:** medium.
- **Risks:** A small edge per trade, and well known.

### S5. Control — random entry
- **Rule:** Enter the same instruments at random, with the same frequency and holding period as S2.
- **Purpose:** If S5 passes, the validation is too loose and we tighten it before trusting anything else.

**Excluded:** intraday day trading (see §2), leveraged certificates and mini futures (they add issuer spread and knock-out risk, and can be revisited once a strategy has proven itself), and foreign-listed instruments (FX fees, and Avanza's Start class only covers the Stockholm exchange [4]).

## 5. Comparison table (no results exist yet)

| Strategy | Edge | Market | Timeframe | Sharpe | Max DD | Trades | Cost sensitivity (*prior*) | Verdict |
|---|---|---|---|---|---|---|---|---|
| S1 Trend rotation | Cross-asset momentum + trend filter | OMXS30 / gold / BTC ETPs | Weekly | not tested | not tested | not tested | Low | Test first |
| S2 Mean reversion | Short-term overreaction | OMXS30 stocks | Daily, 2–5 day holds | not tested | not tested | not tested | **High** | Test; likely fragile |
| S3 Stock momentum | 12-1 month momentum | OMXS30 stocks | Monthly | not tested | not tested | not tested | Low–medium | Test; concentration risk |
| S4 Turn-of-month | Calendar flows | OMXS30 ETF | Monthly | not tested | not tested | not tested | Medium | Test |
| S5 Random | None (control) | OMXS30 stocks | Daily | not tested | not tested | not tested | — | Expected to fail |

## 6. Validation protocol (pre-registered)

| Item | Rule |
|---|---|
| Data | Daily OHLC from Yahoo Finance via `fetch_data_se.py`. Adjusted closes are used for signals and returns, and raw opens for fills |
| Development period | Start of data (about 2000; BTC from 2014) → 2018-12-31. All tuning happens here, walk-forward |
| Held-out period | 2019-01-01 → 2026-09-30. **Touched once**, survivors only, on a pre-announced date. It covers COVID, the 2022 bear market and the 2025 crypto peak |
| Fills | Next day's open. Also tested at the next day's close, to cover a missed morning; a strategy must survive both |
| Costs (base) | Courtage 0.25% per side (Mini class [4]; conservative if Chris qualifies for Start), plus half-spread of 0.10% per side for large caps and 0.30% for ETPs (*assumptions*). The ETP's yearly product fee (e.g. 0.25% [1]) is deducted from returns |
| Stress | Results at 2× and 3× costs |
| Whole shares | The backtest buys whole shares from a 1,000 kr budget, and also from 10,000 kr. Any edge that only exists with fractional shares doesn't count at 1,000 kr |
| **Survivorship** | Yahoo has no delisted Swedish stocks, so S2/S3 results are **biased upward**. They need a held-out Sharpe of at least 0.7 instead of 0.5, or a dataset that includes delistings (check whether a paid source such as Börsdata covers them) |
| Pass thresholds | Held-out Sharpe > 0.5 net (0.7 for S2/S3); still positive at 2× costs; Deflated Sharpe > 0.90 given the trial count; profit factor > 1.2; at least 50 held-out trades, or a bootstrap confidence interval for S1/S4; positive across ±25% parameter changes; **beats simply holding an OMXS30 fund** on risk-adjusted terms |
| Report | Sharpe, Sortino, max drawdown and its duration, CAGR, win rate, profit factor, trades, time in market, cost share of gross P&L, and the full trial log |

If nothing passes, the agent sends no signals and the answer is "hold an index fund". That's a real, acceptable outcome.

## 7. Risk rules (enforced in the agent's code)

| Rule | Value | Action |
|---|---|---|
| Max positions | 2 (1 for S1) | No new buy signals |
| Max per position | 100% of the test budget for S1/S3/S4, 50% for S2. Volatility cap of 25% annualised | Size reduced |
| Stop-loss | Included in every buy signal, entered by Chris in Avanza | — |
| Account drawdown | −20% from peak (200 kr on 1,000 kr) | **Auto-pause:** no new buys, Chris reviews, and only Chris can `/resume` |
| Strategy kill | Drawdown beyond 1.5× the worst held-out drawdown; slippage above 2× the model over 20 fills; rolling performance below the 5th percentile of the bootstrap; live signals not matching a replay | That strategy stops |
| Stale data | Today's bar is missing or older than the last trading day | No signal; Chris gets a "data problem" message instead of a silent nothing |
| Holidays | Swedish exchange holiday calendar | No signals on closed days |
| Heartbeat | No run for more than 26 hours on a trading day | Alert from GitHub Actions to email/Telegram |

## 8. The budget ladder (agreed now, so a lucky month doesn't decide it)

| Step | Budget | Minimum time | Criteria to move up |
|---|---|---|---|
| 0 | 0 kr | Until the Gate 2 pass | A strategy passes §6 |
| 1 | **1,000 kr** | 3 months **and** at least 20 signals | Chris acted on ≥90% of signals; fills within 1.5× the modelled cost; live signals match a replay; no rule breaches; live result not below the 5th percentile of the backtest distribution |
| 2 | 5,000 kr | 3 months | Same criteria |
| 3 | 20,000 kr | 6 months | Same criteria, plus a review of whether the result beats the index fund after costs |

**Making money at step 1 is not a criterion.** Three months of trades is mostly noise. What step 1 proves is that the *process* works: signals arrive, Chris can follow them, and costs match the model. Losing money at step 1 isn't a fail either, unless it falls outside the bootstrap range.

*Because 1,000 kr is effectively tuition, we skip a separate paper-trading phase. Step 1 is the paper trading, with real fills.*

## 9. Build plan (detail at Gate 3)
```
trading-agent/
  config/        universe.yaml, strategies.yaml, risk.yaml, holidays.yaml
  agent/
    data/        Yahoo loader, freshness checks, adjusted/raw handling
    signals/     S1–S5 as pure functions: bars → target position
    risk/        sizing in whole shares, drawdown guard, pause state
    notify/      Telegram send, command parser for /fill, /skip, /pause …
    ledger/      positions.json (from Chris's replies), fills log, P&L vs replay
  research/      backtester, cost model, walk-forward, deflated Sharpe, trial log
  tests/         look-ahead guard, sizing, command parsing, replay equality
  .github/workflows/  evening.yml (18:30), morning.yml (07:30)
```
- **First module (Gate 2):** `research/` backtester with a look-ahead guard test, because no signal goes out until a strategy passes.
- **First live module (Gate 4):** `risk/` + `ledger/`, test-first.
- **Start command:** none yet. It will be enabling the GitHub workflow after Gate 4.

## 10. Open decisions for Chris
1. Approve the switch: signals only, manual execution on an Avanza ISK, daily/weekly timeframe, no day trading.
2. Approve candidates S1–S5, the thresholds (§6), the risk rules (§7) and the budget ladder (§8).
3. Courtage class: are you on Mini, or eligible for Start? The backtest assumes Mini to be safe. Start would make S2 much more viable.
4. Notification channel: Telegram (recommended, because you can reply) or something else.
5. Run `fetch_data_se.py` and send back the `data_se/` folder.

---

## HOW COULD THIS SYSTEM FAIL?
Ranked by likelihood × damage.

1. **Nothing beats the index fund after costs.** This is the most likely result, and the right response is to accept it.
2. **Human execution drift.** Skipped signals, late orders, or overriding the agent when it "feels wrong". Mitigation: the adherence metric, and the ledger reflecting real positions so the damage is measured, not hidden.
3. **Survivorship bias in the stock strategies.** This is the **weakest assumption** for S2/S3, because we can only test on companies that survived. Mitigations: higher thresholds, a paid dataset, or a preference for S1/S4, which are built on indices and don't have the problem.
4. **Costs at small size.** At 1,000 kr, the 1 kr minimum courtage, whole-share rounding and ETP spreads are a large share of every trade. The 1,000 kr step will show what it really costs.
5. **Overnight and weekend gaps.** Stops fill at the opening price, not the stop level. Crypto ETPs carry weekend crypto moves into Monday's open.
6. **Data problems.** Yahoo can deliver late, wrong or missing data with no SLA. Mitigations: freshness checks, a "data problem" message instead of a silent wrong signal, and a cross-check against a second source at Gate 3.
7. **Overfitting through research.** Mitigations: the trial log, Deflated Sharpe, a single held-out run, and control S5.
8. **Small-sample self-deception.** A good 3 months makes it tempting to raise the budget early. That's why the ladder is fixed now.
9. **Infrastructure.** GitHub Actions or the Telegram bot could go down. Mitigation: the heartbeat alert. Resting stop-losses in Avanza protect positions regardless.

---
### Sources
[1] Virtune — buying bitcoin ETP (VIRBTCP on Nasdaq Stockholm, 0.25% fee) — https://www.virtune.com/en/insights/handla-bitcoin-avanza
[2] Chague, De-Losso & Giovannetti, "Day Trading for a Living?" (2020), as summarised at https://faisalharoon.substack.com/p/day-trading-failure-rate-analysis
[3] Barber, Lee, Liu & Odean, "The Cross-Section of Speculator Skill: Evidence from Day Trading", *Journal of Financial Markets* (2014), same summary
[4] isk-guiden, Avanza courtage classes (Start, Mini), verified against Avanza's price list June 2026 — https://isk-guiden.se/maklare/avanza/
[5] Avanza, special terms for stop-loss orders — https://www.avanza.se/avanzabank/hem/konton/blanketter/allmanna/sarskilda_villkor_stoploss.pdf
[6] Opening auction and orders placed outside trading hours (forum, Feb 2025) — https://rikatillsammans.se/forum/t/kop-saljorder-nar-borsen-ar-stangd/98390
[L1] Moskowitz, Ooi & Pedersen (2012), "Time Series Momentum", *Journal of Financial Economics*
[L2] Faber (2007), "A Quantitative Approach to Tactical Asset Allocation", *Journal of Wealth Management*
[L3] Lehmann (1990), "Fads, Martingales, and Market Efficiency", *Quarterly Journal of Economics*
[L4] Jegadeesh & Titman (1993), "Returns to Buying Winners and Selling Losers", *Journal of Finance*
[L5] McConnell & Xu (2008), "Equity Returns at the Turn of the Month", *Financial Analysts Journal*
