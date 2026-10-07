# Finding a strategy that wins more than 65% of the time

Research run on Oct 6–7, 2026 using the TradingView connector. Every number below comes from
`python3 research/backtest.py`, run on the bars saved in `research/data/`, and is pinned by
`tests/test_backtest.py`.

## What the TradingView connector offers

| Tool | What it gives | Useful for a backtest? |
|---|---|---|
| `get_ohlcv` | Price bars: 20 years of daily bars, about 9 months of 15-minute bars | **Yes, the core data used here** |
| `run_screener`, `get_symbol_data(_batch)`, `get_technicals_rating` | Today's indicator values, technical ratings and fundamentals | No: current values only, no history |
| `get_economic_calendar`, `get_economic_data` | Macro events (CPI, FOMC, jobs) back to 2003 | Possible as a filter later; not used, so as not to over-fit |
| `get_earnings_calendar`, `get_dividends_calendar`, `get_news`, `get_documents`, `get_forecasts` | Company events, news, filings, analyst targets | No for index ETFs |
| alerts, watchlists | Price alerts and lists | No |

TradingView data is delayed 15 minutes, so the proposed Routine trades on Robinhood's real-time
quotes. TradingView is only the research source.

Data used:
- SPY, QQQ, IWM, DIA and EEM: daily bars since Nov 2006, plus 15-minute bars since Dec 30, 2025.
- VIX and VIX9D: daily bars.

## 1. The current overnight rules (baseline)

The live EEM entry rules (ADX/TRIX/ADX-stab/RSI(2)/open), run at 3:45pm on every eligible 2026 day:

| Exit | Trades | Direction right |
|---|---|---|
| EEM, next open | 147 | 52.4% |
| EEM, next 9:45am | 147 | 50.3% |
| SPY / QQQ / IWM / DIA, next 9:45am | 138–148 each | 50–56% |
| EEM as the nearest **ITM** option (modeled) | 147 | **46.3%** win |
| EEM as the nearest **OTM** option (modeled) | 147 | **32.0%** win |

The rules call direction about as well as a coin flip. The option has to beat overnight time
decay and the bid-ask spread on top of that, so the option win rate is lower still. Only one round trip
in the account has finished so far: 10 × $68 puts bought at $0.22 and sold at $0.15.

## 2. Published strategies on five ETFs

The parameters come from the original publications (Connors & Alvarez, 2008–2009). None was tuned
here. The first column (2007–2025) is the long test; 2026 is the period you asked about.

| Strategy | 2007–2025 trades | Win % (95% range) | 2026 trades | 2026 win % |
|---|---|---|---|---|
| **RSI(2) < 5 pullback** in an uptrend, sell above 5-day avg | 365 | **76.4% (72–81)** | 23 | **100%** |
| RSI(2) < 10 pullback | 678 | 70.9% (67–74) | 44 | 81.8% |
| Double 7s | 923 | 71.4% (68–74) | 55 | 69.1% |
| VIX stretch (VIX 5% above its 10-day avg) | 1313 | 74.3% (72–77) | 82 | 84.1% |
| IBS < 0.2, hold 1 day | 3793 | 56.3% | 141 | 53.9% |
| Overnight hold, every day | 23900 | 54.3% | 950 | 56.1% |
| Overnight, RSI(2) < 10 + uptrend | 1296 | 60.4% | 70 | 82.9% |
| Short (puts) RSI(2) > 90 in a downtrend | 292 | 64.4% | 2 | 0% |

No overnight-only strategy reaches 65% over the long run. The pullback strategies do, because they
hold for 2–5 days and let the bounce finish.

## 3. Why these are not option trades

The same swing trades were priced as calls. The model uses Black-Scholes with IV equal to a
ratio × VIX on each day, buys at the ask and sells at the bid.

| RSI(2) < 5 trades bought as… | 2007–2025 win % | 2026 win % | 2026 cost per contract |
|---|---|---|---|
| Shares | 76.4% | 100% | any amount |
| 0.70-delta call, ~3 weeks | 63.6% | 78.3% | SPY ~$2,700, IWM ~$1,200, EEM ~$320 |
| 0.50-delta call, ~3 weeks | 52.9% | 69.6% | SPY ~$1,500, EEM ~$175 |
| 0.30-delta call, ~3 weeks | 39.7% | 60.9% | SPY ~$710, EEM ~$84 |

- Many winning trades bounce only 0.2–0.5%, which is not enough to pay for 3–5 days of time decay
  plus the spread.
- Over the long run, every option version falls below 65%. Most also lose money on average.
- At $250, only EEM calls are affordable. EEM options would also clash with your Routines: the
  morning close sells every EEM option the next day, and the entry Routine skips any day an EEM
  option is held. You asked for those Routines to stay unchanged.

## 4. Proposed Routine: RSI(2) pullback in shares

Rules (full prompt in `etf-rsi2-pullback.md`), checked at 3:45pm each trading day:
1. **Exit:** sell the held ETF if its price is above its 5-day average, or after 10 trading days.
2. **Entry:** if nothing is held, find the ETFs among SPY, QQQ, IWM, DIA and EEM that are above
   their 200-day average with RSI(2) < 5. Buy $250 of the one with the lowest RSI(2).
3. Only one position at a time, and at most $250 per day.

Results:

| Period | Trades | Win % (95% range) | Avg trade | Avg win / loss | Worst | $ per $250 trade |
|---|---|---|---|---|---|---|
| 2007–2025, daily closes | 167 | **74.9% (68–81)** | +0.31% | +1.24% / −2.45% | −17.4% | +$0.77 |
| 2026, daily closes | 15 | **100% (80–100)** | +1.25% | +1.25% / — | +0.1% | +$3.12 |
| 2026, **3:45pm prices** (how the Routine trades) | 13 | **84.6% (58–96)** | +1.16% | +1.41% / −0.23% | −0.3% | +$2.90 |

2026 trades at 3:45pm prices:

| ETF | Bought | Sold | Entry | Exit | Result |
|---|---|---|---|---|---|
| QQQ | Jan 2 | Jan 5 | 613.22 | 618.27 | +0.82% |
| SPY | Jan 20 | Jan 22 | 676.95 | 688.17 | +1.66% |
| IWM | Jan 30 | Feb 6 | 259.36 | 265.17 | +2.24% |
| EEM | Mar 3 | Mar 9 | 58.54 | 58.36 | −0.32% |
| DIA | Mar 12 | Mar 17 | 468.61 | 471.12 | +0.54% |
| DIA | Apr 29 | Apr 30 | 488.29 | 497.34 | +1.85% |
| IWM | May 19 | May 20 | 273.14 | 279.51 | +2.33% |
| QQQ | Jun 5 | Jun 11 | 707.37 | 717.38 | +1.42% |
| DIA | Jul 20 | Jul 22 | 518.13 | 521.66 | +0.68% |
| QQQ | Jul 28 | Jul 30 | 676.35 | 683.60 | +1.07% |
| DIA | Aug 18 | Aug 21 | 533.45 | 532.71 | −0.14% |
| IWM | Sep 1 | Sep 3 | 290.36 | 294.97 | +1.59% |
| IWM | Sep 16 | Sep 21 | 282.53 | 286.24 | +1.31% |

Robustness checks:
- **Without look-ahead:** the per-ETF version (365 trades) still wins 72.1% over 2007–2025 when
  it buys and sells at the next morning's open instead of the signal close.
- **Both halves of the history:** 2007–2016 won 78.0% (82 trades) and 2017–2025 won 72.1% (86 trades).
- **Thresholds:** RSI(2) < 3, < 5 and < 7 all win 72–77%, with either exit (above the 5-day
  average, or RSI(2) > 65). The result does not depend on one exact setting.
- **Slippage:** with 0.04% slippage per round trip, it wins 74.4%.
- **Individual ETFs:** within the Routine's trades, every ETF won 75–83%.

## Read this before turning it on

- **A high win rate is not the same as high profit.** The average loss (−2.45%) is about twice the
  average win (+1.24%). The worst trade lost 17.4% (IWM, Aug 2011), which is $43 on $250. Over
  2007–2025 it still made money: profit factor 1.50, +$129 total on a $250 stake.
- **Some years fell below 65%:** 2018 (50%), 2019 and 2020 (57%), 2021 (64%) and 2023 (56%).
  The other 15 of the 20 years were at or above 65%.
- **2026 has been a strong up-market.** That flatters any buy-the-dip strategy, so expect
  something closer to the 2007–2025 figure (about 75%) going forward.
- **It trades rarely:** about 9 trades a year. It holds about 3.6 days and is in the market roughly
  13% of the time. It stays out when an ETF is below its 200-day average, such as most of 2022.
- **Fractional shares need market orders on Robinhood.** That is fine for these very liquid ETFs at
  3:45pm. The contract cap that pushed the EEM Routines to limit orders applies only to options.
- **Small data differences:** the bars are split-adjusted but not dividend-adjusted, and holders of
  shares also collect dividends. The live Routine uses Robinhood's daily bars, which can differ
  from TradingView's by a cent or two.

## Reproduce

```
pip install numpy pandas scipy
python3 research/backtest.py                 # all sections
python3 research/backtest.py routine checks  # just the proposed Routine
python3 -m unittest discover -s tests
```

To refresh the data, re-download the bars with TradingView `get_ohlcv`. Use 1D with 5000 bars, and
15m with 5000 bars. Then convert them with `python3 research/tv_to_csv.py <tool-results dir> research/data`.
