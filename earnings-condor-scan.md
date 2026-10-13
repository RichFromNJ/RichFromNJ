You are scanning for a rules-based earnings iron condor in my Robinhood account. This run only looks: it pulls data, runs the repository's script on it, ranks the candidates and reports the single pick for the entry routine that runs at 3:38pm. It places NO orders. Follow these instructions exactly. Do not improvise, do not ask questions, and if any step fails, any data is missing, or anything is ambiguous for a symbol, drop that symbol from the ranking and report why. There is no judgment call in this prompt.

AUTHORIZATION
I pre-authorize you to read my Robinhood account, positions, orders, quotes, option chains and earnings data, to read TradingView price history, to save connector responses to files, and to run the repository's script on them, without asking me first. This authorization covers nothing else: never review, place, cancel or modify any order in this run.

ACCOUNT
Use the single Robinhood account that is agent-enabled (nickname "Agentic"). Never touch any other account.

THE TRADE (what the script checks; you compute none of this by hand)
An earnings iron condor is sold on the last session before a company reports, about 20 minutes before the close, and bought back the next session after the implied-volatility crush, win or lose. The script applies these rules: price at least $10; the first expiration on or after the reaction day and within 8 calendar days of it; the at-the-money straddle (ATM call mid plus ATM put mid) is the implied move; the short put is the highest listed strike at or below price minus straddle and the short call the lowest listed strike at or above price plus straddle; wings $1, $2, $2.50 or $5 below and above them, the first width that passes every check; credit at least 35% of the risk (ROI = credit / (width − credit)); each short leg's bid-ask at most 15% of its mid, absolute delta at most 0.35, and volume at least 15 or open interest at least 100; the natural credit (short bids minus long asks) at least 75% of the mid credit; the limit credit is the mid credit rounded DOWN to the tick; risk per condor = (width − limit credit) × 100; quantity = floor($250 / risk), at least 1; and the history filter: at least 3 of the last 4 post-earnings moves no bigger than today's implied move (skipped, and said so, when fewer than 4 past moves are supplied).

TIMES (all ET; on a half-day, use the time measured from today's actual close instead)
- Start = 3:25pm (35 minutes before the close).
- Scan deadline = 3:36pm (24 minutes before the close). Start no new symbol after this time; write the report with what you have so the entry routine can start at 3:38pm.

HOLIDAYS
NYSE full-day closures:
- 2026: Thu Nov 26, Fri Dec 25.
- 2027: Fri Jan 1, Mon Jan 18, Mon Feb 15, Fri Mar 26, Mon May 31, Fri Jun 18, Mon Jul 5, Mon Sep 6, Thu Nov 25, Fri Dec 24.
This list runs through December 31, 2027. From January 1, 2028, report "no candidate" until the list is updated.

SCRIPT
- Every number in this run comes from the repository's earnings_condor.py, run from the RichFromNJ checkout as `python3 earnings_condor.py <subcommand> ... --json`. Never compute strikes, straddles, implied moves, credits, ROI, quantities or ranks yourself; the script does, from the saved files.
- Save every connector response to its own file, exactly as returned, in a folder named after today's date (for example condor/2026-10-13/). Pass those files to the script. Never retype, trim or summarize a response into a file.
- If the script is missing, fails, or prints an error for a symbol, that symbol is dropped and the error is reported verbatim. If it fails before any symbol is evaluated, report "no candidate" and the error.

PRE-CHECKS (if any fail, report "PICK: none" with the reason and stop)
1. Today must be a trading day and the market must be open right now. If it is already past the scan deadline, stop.
2. Today must be Mon–Thu, or a Friday. On a Friday a symbol qualifies only if its expiration (DATA step 6b) falls in a later week; a condor is never opened on the day it expires.
3. If the market is closed tomorrow for a holiday (see HOLIDAYS), the entry routine will not trade. Report "PICK: none (holiday tomorrow)" and stop.

DATA
1. Earnings calendar: get_earnings_calendar with start_date = today, days = 2, filter = high_market_cap. Save it as calendar.json.
2. Run `candidates --calendar calendar.json --date <today>`. It lists every symbol whose report makes today the entry day (a report today after the close, or a report before the open on the next trading day), with the reaction day and timing. A report with no timing, or not verified, is never a candidate. If the list is empty, report "PICK: none (no report qualifies today)" and stop.
3. Prices: get_equity_quotes for the listed symbols, at most 20 symbols per call; save each response. Re-run `candidates` with `--prices` pointing at those files so the $10 minimum applies. A symbol's price is quote.last_trade_price, and its venue_last_trade_time must be within the last 5 minutes; otherwise drop the symbol ("stale quote").
4. Capacity: get_option_positions (nonzero) for the account. An open condor is the set of open legs of one symbol and expiration that form exactly four legs: a short put, a long put below it, a short call and a long call above it, all with the same quantity. Count the open condors and report their symbols. Drop any candidate that already has an open option position in the account ("position exists"). If 2 condors are already open, report "PICK: none (2 condors open)" after the ranking; the entry routine would refuse.
5. Evaluate at most 8 symbols, in the order `candidates` prints them; list the rest as "not evaluated (per-run limit)". Start no new symbol after the scan deadline.
6. For each symbol:
   a. Chain: get_option_chains underlying_symbol = SYMBOL. Save as SYMBOL_chain.json. If the response holds more than one chain for the symbol, drop it ("ambiguous chain").
   b. Expiration = the first date in the chain's expiration_dates that is on or after the reaction day and at most 8 calendar days after it. If there is none, drop ("no expiration"). On a Friday, if that date is this week, drop ("Friday, expires this week").
   c. Instruments: get_option_instruments with chain_id = the chain id, expiration_dates = the expiration, type = put, state = active; then the same with type = call. Follow `next` cursors until none; save every page (SYMBOL_instruments_puts_1.json, SYMBOL_instruments_calls_1.json, ...).
   d. Quotes: take every instrument whose strike is between 0.90 × price and 1.10 × price, puts and calls. Call get_option_quotes in batches of at most 20 ids and save every response (SYMBOL_quotes_1.json, ...). If fewer than 6 strikes fall in that band, drop ("too few strikes").
   e. History: get_earnings_results symbol = SYMBOL; save as SYMBOL_earnings.json. Daily bars for the last 400 calendar days: TradingView get-ohlcv with symbol EXCHANGE:SYMBOL, interval 1D (US listings are on NYSE, NASDAQ or AMEX; use search-symbols when the exchange is not known). If TradingView fails, use Robinhood get_equity_historicals (interval day, span year, bounds regular) and ignore bars marked interpolated. Save as SYMBOL_bars.json. With a short script (Python in the shell, never by hand) compute the reaction move of each of the last 4 past reports that have a date before today and a timing, reading only the two saved files: am → |close on the report date / close of the previous bar − 1| × 100; pm → |close of the next bar / close on the report date − 1| × 100. Skip a report with no timing or a missing bar. The moves, comma-separated, are the value for --history-moves; fewer than 4 is allowed, and build then says the filter was skipped.
   f. Run `build --symbol SYMBOL --price PRICE --date <today> --report-date <report date> --timing <am|pm> --chain SYMBOL_chain.json --instruments <every instruments file> --quotes <every quotes file> --history-moves a,b,c,d --max-loss 250 --json` and save the output as SYMBOL_build.json. If build reports a different expiration from step b, pull instruments and quotes for its expiration once and run build again. The verdict is TRADE or NO TRADE, with every width tried and why each failed.

RANKING
- Rank the TRADE verdicts by the build output's ROI, highest first. Ties: the larger natural credit, then alphabetical by symbol.
- The pick is the first in the ranking. Only one condor is opened per day.

RULES
- Place no order. Never call a review, place, cancel or replace order tool in this run.
- Never change watchlists, alerts or anything else in the account.
- Never compute a strike, credit, ROI, move or rank by hand; everything comes from the saved files through the script.

REPORT
Begin with one line: "PICK: SYMBOL" (or "PICK: none", with the reason), followed by the exact build command and files used for the pick, so the entry routine can re-run it.
Then summarize:
- date, start and end time, and how many symbols the calendar listed, candidates listed, you evaluated, and you did not evaluate
- capacity: the open condors (symbol, expiration, quantity) and whether the entry routine has room
- the ranked TRADE list: symbol, report date and timing, reaction day, expiration, price, straddle and implied move %, the history moves and whether the filter passed or was skipped, the four strikes, width, mid credit, natural credit, limit credit, tick, ROI, quantity, risk per condor and in total, each short leg's bid, ask, spread %, delta, volume and open interest, and the four instrument ids
- every NO TRADE symbol: each width tried and the reason it failed
- every dropped symbol and why (stale quote, position exists, ambiguous chain, no expiration, Friday, too few strikes, script error)
- any script error, verbatim
