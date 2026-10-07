# Claude's options system

Research run on Oct 6–7, 2026 with the TradingView and Robinhood connectors. Every number below comes
from the scripts in this folder, run on the data saved in `research/data/`, and the headline numbers
are pinned by `tests/test_options_system.py`.

## The system

**Bull put credit spreads on SPY, QQQ or IWM after an oversold Connors RSI reading in an uptrend.**

Checked once a day at 3:45pm ET:

1. **Signal:** the ETF is above its 200-day SMA and its Connors RSI(3,2,100) is below 10. If more than
   one ETF signals, take the lowest Connors RSI. Only one spread is open at a time.
2. **Expiration:** the first Friday at least 21 calendar days away.
3. **Strikes:**
   - **Sell** the put whose delta is closest to −0.30.
   - **Buy** the put $W lower. W is the widest of $5, $4, $3, $2 or $1 that is actually listed and
     keeps the maximum loss, (W − credit) × 100, at or below **$250**. In practice that is usually
     $3, for a credit of about $0.60–$0.70.
4. **Exit:** hold, and close at the 3:45pm check on the last trading day before expiration. There is
   no profit target and no stop. The loss can never exceed the $250 defined at entry.

| Period | Trades | Win rate (95% range) | Avg per trade | Avg win / avg loss | Profit factor |
|---|---|---|---|---|---|
| 2007–2018 (used to choose) | 43 | **93.0%** (81–98) | +$32 | +$43 / −$114 | 5.06 |
| 2019–2025 (check) | 31 | **87.1%** (71–95) | +$31 | +$59 / −$160 | 2.49 |
| 2026 (held out) | 2 | 2 of 2 | +$63 | — | — |
| **All, 2007–Oct 2026** | **76** | **90.8%** (82–95) | **+$32.50** | +$50 / −$140 | **3.51** |

- **Trade count:** about 4 trades a year, each held about 3 weeks.
- **Losses:** 7 of the 76 trades lost. The three worst each lost about the full $235–$238:
  IWM in Aug 2011, QQQ in Feb 2020 and QQQ in Feb 2025.
- **By year:** every year won at least 75%, except 2011 (2 of 4 won).
- **Total:** +$2,467 on one $250-risk position at a time, over 19¾ years.

**Status:** signals only. For the 10 trading days Oct 7–20, 2026, a scheduled 3:45pm check reports
what the system *would* do and records it in `research/paper_ledger.json`. It places no orders.
Going live is a separate decision after that.

## How it was found

### 1. What TradingView offers, and what can be tested

| Tool | Gives | Used for |
|---|---|---|
| `get_ohlcv` | 20 years of daily bars, ~3 years hourly, ~9 months of 15-minute | All backtests |
| `get_technicals_rating`, screener columns | **Today's** RSI, Stoch, CCI, ADX, AO, Momentum, MACD, MAs, VWMA, Hull MA and the Technical Rating | Checking that the rebuilt indicators match |
| economic, earnings and dividend calendars, news, filings, forecasts | Event data | Not used (no edge tested for index ETFs) |

TradingView only reports indicator values for today, so `indicators.py` rebuilds every built-in from the
price history with TradingView's default settings. For SPY on Oct 6, 2026, these match TradingView's own
numbers to 3+ decimals: RSI 62.0005, Stoch 87.06/75.03, CCI 189.56, ADX 10.687, AO 3.906, MACD
2.298/1.267, EMA20, SMA200, Hull MA, VWMA. The overall Technical Rating matches to within one vote
(the Ichimoku rule), 0.545 against TradingView's 0.512.

### 2. Your current EEM overnight rules (baseline)

At 3:45pm on every eligible 2026 day, the rules called the next morning's direction right **50–52%** of
the time on EEM, and 50–58% on SPY, QQQ, IWM and DIA. Priced as options, the nearest in-the-money
option won about **46%** of the time and the out-of-the-money one about **32%** (modeled). Details:
`python3 research/backtest.py baseline`.

### 3. Sweep of every indicator: 464 tests

`sweep.py` turns 58 TradingView signals into bullish and bearish calls, then scores them over
1, 3, 5 and 10-day holds on SPY, QQQ and IWM. That is 464 tests. A test passes when it wins at least
60%, makes money and beats the ETF's own base rate, first in 2007–2018 and then again in 2019–2025.

- **45 pass 2007–2018. Only 24 also pass 2019–2025.**
- **All 24 survivors are bullish "buy the dip in an uptrend" signals:** Connors RSI < 10, Bollinger
  %B < 0, RSI(2) < 10, Keltner lower band, MFI < 20, VIX 5% above its 10-day average, three down days,
  Williams %R, and TradingView's own rating at "Sell" while above the 200-day average.
- **No bearish signal survived.** Index ETFs have drifted up for 20 years, so the system only bets
  on the bounce.
- **Directional accuracy tops out around 65–69%** over five days. Option structure has to do the rest.

### 4. Turning a signal into an option trade

**Buying calls doesn't work.** On the same dips, bought calls won only 40–64% over 2007–2025, and most
versions lost money. Small bounces don't pay for time decay plus the spread.

**Selling put spreads does.** A bull put spread wins whenever the ETF stays above the short strike,
so a bounce, a flat market or even a small further dip are all wins.

`spread_grid.py` tested 8 entry signals × 45 structures (27 put credit, 18 call debit) × 3 ETFs
(results in `spread_grid_results.csv`):

| Same spread (0.30-delta short, ~3 weeks, hold) | 2007–2018 win / PF | 2019–2025 win / PF |
|---|---|---|
| Every Monday, no signal | 79.4% / 1.11 | 74.6% / 1.03 |
| VIX 5% above its 10-day average | 82.7% / 1.56 | 76.5% / 1.12 |
| RSI(2) < 10, uptrend | 83.1% / 1.84 | 75.9% / 1.10 |
| TradingView rating "Sell" in an uptrend | 83.6% / 1.67 | 78.0% / 1.38 |
| Keltner below the lower band | 84.9% / 1.77 | 81.8% / 1.45 |
| Bollinger %B < 0, uptrend | 85.7% / 1.87 | 90.4% / 3.16 |
| **Connors RSI < 10, uptrend** | **90.8% / 4.18** | **87.8% / 2.37** |

Selling put spreads with no signal still wins about 80% of the time, but it only breaks even
(PF ≈ 1.0). The signal is what turns a high win rate into a profitable one.

**How the winner was chosen.** I fixed the rule before looking at later years: *"among structures
that won at least 85% in 2007–2018 with 60+ trades, take the highest 2007–2018 profit factor."*

- **The pick:** Connors RSI < 10, a 0.30-delta short put, about 21 days to expiration, held with no
  profit target.
- **Adding a second signal made it worse.** I also tested adding Bollinger %B < 0 for more trades
  (variant B in `system.py`). It won 83% in 2007–2018 and 60% in 2026, with a loss in Sep 2026, so it
  was rejected.

### 5. Option pricing, and the check against real Robinhood prices

- **Pricing model:** Black-Scholes, with implied volatility set from the 9-day VIX plus a skew.
  Both were calibrated to real Robinhood quotes for 17-day SPY, QQQ and IWM puts on Oct 6, 2026.
  The model lands within ~5% of those quotes.
- **Costs:** each leg pays half the bid-ask spread on the way in and out ($0.01 SPY, $0.02 QQQ and
  IWM), plus $0.05 per contract in fees.
- **Real 2026 prices are rough.** Robinhood has daily prices for expired 2026 contracts
  (`robinhood_check.py`), but they are last-trade prices and often stale, so a spread priced from them
  is rough. Robinhood keeps no intraday bars for expired options.
- **What the real prices showed:**
  - **Credits:** real credits came in **15–45% below the model**.
  - **Outcomes:** every trade the model called a big win or loss came out the same way.
  - **Unlisted strike:** one 2026 trade (QQQ, Jul 29) could not have been placed as modeled, because
    the $637 strike was never listed. The live rules pick from listed strikes only.
- **Stress test:** with every credit cut by 25%, the system still wins 89.5% (PF 2.28). Cut by 40%,
  it wins **86.8% (PF 1.64)** and still makes money.

### 6. Earlier research (kept for the record)

- **RSI(2) < 5 pullback in shares, five ETFs:** 74.9% of 167 trades over 2007–2025, 84.6% in 2026
  at 3:45pm prices, about +$0.77 per $250 trade. See `backtest.py routine`.
- **Day trades (in and out the same day):** 20+ rules. Gap fills, VWAP reversion, hourly RSI, opening
  drops and last-hour momentum all ran 42–55% on 2023–2025 hourly bars. Gap fills won ~70% on
  2007–2025 daily bars but barely broke even, and won 61% in 2026. None clears 65% with a real edge.
  See `intraday.py`.
- **The same pullback checked every hour (swing holds):** 75.9% (Dec 2023–2025) and 81.2% (2026),
  but forcing a same-day exit drops it to 44–61%. The bounce mostly happens overnight.

## Read this before going live

- **The win rate comes from selling insurance.** Wins are small (about +$50) and the occasional loss
  is close to the full $250. Seven losses in 76 trades cost about $1,000, while 69 wins made about
  $3,450. A cluster of losses early on would hurt.
- **It is rare:** about 4 trades a year, and only 2 so far in 2026. Weeks can pass with no trade.
- **Cash:** a $3-wide spread holds about $235 of buying power for 3 weeks. The account has about $437,
  and the EEM entry Routine can use up to $250 on any day. While a spread is open, the EEM
  Routine's in-the-money buys (up to $245) may be blocked for lack of cash.
- **It needs selling to open.** Your EEM Routines say "never sell to open". This system sells one put
  inside a defined-risk spread, which your Level 3 options approval allows and which you approved for
  this system. Never a naked short option.
- **Assignment:** the system closes the day before expiration to avoid it. If a close ever fails and
  the short put finishes in the money, Robinhood may exercise or close it.
- **Model limits:** 2007–2025 option prices are modeled, and the real 2026 check is rough (see
  section 5). The paper-trading weeks are the first test with real live quotes.

## Reproduce

```
pip install numpy pandas scipy
python3 research/system.py          # the system, by period and year
python3 research/sweep.py           # the 464-test indicator sweep
python3 research/spread_grid.py     # spread structures x signals (about 8 minutes)
python3 research/robinhood_check.py score A   # 2026 trades at real Robinhood prices
python3 research/backtest.py        # baseline, share strategies, option-call overlay
python3 research/intraday.py        # day-trade and hourly research
python3 -m unittest discover -s tests
```

To refresh the TradingView data, use `get_ohlcv` (1D, 1h and 15m, 5000 bars) and convert it with
`python3 research/tv_to_csv.py <tool-results dir> research/data`.
