You are producing my monthly review of my Robinhood options trading. Follow these instructions exactly. Do not ask questions. If any data cannot be retrieved, say so in the report instead of estimating it.

READ-ONLY
This task only reads data. Never place, review, cancel, replace or modify any order. Never exercise an option. Never change watchlists, alerts, scans or routines.

PERIOD
- Review the previous calendar month, first day through last day, based on today's date in US Eastern time. Example: run on November 1, 2026 → review October 1–31, 2026.
- Prior month = the calendar month before the review month.
- Trailing 3 months = the three full calendar months before the review month, combined.

ACCOUNTS
Review every brokerage account returned by get_accounts (currently the "Agentic" limited-margin account and the individual cash account). Combine them in the summaries, and show which account each trade was in. If an account had no options activity in the period, say so.

DATA TO PULL
- All filled options orders (bought and sold) opened or closed in the period
- Realized P&L per trade, plus positions still open at month end (unrealized P&L)

Suggested sources:
- get_option_orders (state filled) with created_at_gte early enough to catch positions opened before the period and closed in it. Follow `next` until it is empty.
- get_pnl_trade_history (span 3month, filtered to the period by timestamp) for realized P&L per closing trade. Reconcile its total with get_realized_pnl (asset_classes ["option"], start_date and end_date = the period). If the two disagree, report both and flag it.
- get_option_positions for positions open at month end and for contracts that expired, were exercised or were assigned without a closing order.
- get_option_quotes for marks on positions that are still open. If a month-end mark is not available, say the mark is as of the run time.
- get_equity_historicals (daily bars) for the SPY and EEM benchmark and for each trade's strike distance from the money at entry.
- get_portfolio for portfolio value. It only reports the current value; flag that if a month-end value is not available.

DEFINITIONS
- Correct option / winning trade: closed with positive realized P&L after fees. Anything else is a loss. Open positions are reported separately and not counted as wins or losses.
- One trade = one closing fill (or an expiration, exercise or assignment) matched first-in, first-out to its opening fills, the same way Robinhood's realized P&L list counts it.

TRADE LOG
Table of every options trade: ticker, call/put, strike, expiration, open date, close date, contracts, entry price, exit price, realized P&L ($ and %), result (Correct/Incorrect/Open), and how it ended (closed manually, expired, exercised/assigned).

SUMMARIES
Three sections: EEM, SPY, and Overall (all tickers). Each includes:
- Total trades, number of correct options, number incorrect, and % correct
- Total realized P&L ($), net of fees
- Average win, average loss, largest win, largest loss
- Expectancy per trade (win rate × avg win − loss rate × avg loss)
Include any tickers other than EEM and SPY in Overall and list them under "Other."

ANALYSIS
- Which trades drove most of the P&L
- Patterns in correct vs. incorrect trades: days to expiration at entry, strike distance from the money, holding period, call vs. put
- Compare to the prior month and trailing 3 months
- Open positions: unrealized P&L, expirations, assignment risk
- Position sizing: largest position as % of portfolio, and any outsized trades
- Benchmark: what the same capital would have returned in plain SPY/EEM shares

OUTPUT
Publish the report as a self-contained HTML artifact titled "Options Review – [Month YYYY]". Do not paste the full report in chat; reply with the artifact link and the 3-sentence headline summary only.

Layout, top to bottom:
1. Headline summary (3 sentences)
2. Summary cards for EEM, SPY, and Overall: P&L, % correct, trades, expectancy
3. Chart: cumulative P&L over the month, and a bar chart of P&L per trade (color wins vs. losses)
4. Full trade log table (scrolls horizontally on mobile)
5. Analysis sections
6. Open positions at month end
7. Closing 2-3 data-backed observations: what to repeat, what to stop

Be direct and don't soften losses. Flag any data you couldn't retrieve rather than estimating it. Keep it private (don't share).

If there were no trades in the period, still publish the report. Show every section with an explicit "no trades" state (n/a, not 0%, for rates and expectancy), and list exactly which data you checked.
