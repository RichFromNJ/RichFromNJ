You are executing a rules-based earnings iron condor in my Robinhood account: a four-leg credit spread sold on the last session before a company reports, sized so the most it can lose is $250, and closed by the exit routine the next session. Follow these instructions exactly. Do not improvise, do not ask questions, and if any step fails, any data is missing, or anything is ambiguous, place NO trade and report why. There is no judgment call in this prompt: the script picks the symbol's strikes, width, credit and quantity, and you place only what it prints.

AUTHORIZATION
I pre-authorize you to review, place, cancel, and re-place the four-leg iron condor credit LIMIT orders described in this prompt, including the one re-placement one tick below the first limit, without asking me first. This authorization covers nothing else.

ACCOUNT
Use the single Robinhood account that is agent-enabled (nickname "Agentic"). Never touch any other account. The account must show option level 3 (multi-leg orders); if it does not, NO TRADE.

RISK
- Maximum loss per condor = $250: (width − limit credit) × 100 × quantity must never exceed $250. The script enforces this; if the order review shows a larger maximum loss or collateral, NO TRADE.
- At most 2 condors open across all symbols, and the open condors' risk plus this one must not exceed $500.
- One new condor per day, in one symbol, as one four-leg order. Legs are never placed separately.

TIMES (all ET; on a half-day, use the earlier time in each pair)
- Start = 3:38pm, or 22 minutes before today's close.
- Final-order time = 3:48pm, or 12 minutes before today's close. No new order may be placed after this time.
- Purchase deadline = 3:49pm, or 11 minutes before today's close. Cancel anything still unfilled at this time. Never hold an unfilled order past it.

HOLIDAYS
NYSE full-day closures:
- 2026: Thu Nov 26, Fri Dec 25.
- 2027: Fri Jan 1, Mon Jan 18, Mon Feb 15, Fri Mar 26, Mon May 31, Fri Jun 18, Mon Jul 5, Mon Sep 6, Thu Nov 25, Fri Dec 24.
This list runs through December 31, 2027. From January 1, 2028, NO TRADE until the list is updated.

SCRIPT
- Every number in this run comes from the repository's earnings_condor.py, run from the RichFromNJ checkout as `python3 earnings_condor.py <subcommand> ... --json`. Never compute strikes, straddles, credits, ROI, ticks, quantities or risk yourself; the script does, from the saved files.
- Save every connector response to its own file, exactly as returned, in a folder named after today's date (for example condor/2026-10-13/). Pass those files to the script. Never retype, trim or summarize a response into a file.
- If the script is missing, fails, or prints an error, NO TRADE. Report the error verbatim.

PRE-CHECKS (skip the trade if any fail)
1. Today must be a trading day, the market must be open right now, and it must be before the final-order time. If the market is closed tomorrow for a holiday (see HOLIDAYS), NO TRADE.
2. Today must be Mon–Thu, or a Friday on which the chosen expiration (DATA step 4) falls in a later week. Never open a condor that expires today.
3. The pick. If this run was given a symbol (in the Routine's message, or on the scan report's "PICK:" line), evaluate only that symbol. Otherwise run the scan prompt's DATA and RANKING steps now and take its pick. If there is no pick, NO TRADE. If DATA is not finished by the final-order time, NO TRADE.
4. Open orders: get_option_orders for today. If any open (queued, confirmed or partially filled) option order exists in the pick's symbol, NO TRADE. Report it.
5. Positions: get_option_positions (nonzero).
   - If the account holds any option position in the pick's symbol, NO TRADE. Report it.
   - An open condor is the set of open legs of one symbol and expiration that form exactly four legs: a short put, a long put below it, a short call and a long call above it, all with the same quantity. Its risk = (the wider of its two spreads − the credit received) × 100 × quantity, where the credit is the average price of its filled opening order in get_option_orders; if that credit is not visible, use width × 100 × quantity.
   - If 2 or more condors are open, NO TRADE. If the open condors' risk plus this condor's total risk (from the script) exceeds $500, NO TRADE.
   - A symbol whose open legs include a short option but do not form a complete condor is a broken condor: NO TRADE, and report it on the first line. Long-only positions in other symbols (for example the overnight EEM or SPY options) are ignored here.

DATA (the same pulls as the scan, done fresh for the pick)
1. Price: get_equity_quotes for the symbol; save it. Price = quote.last_trade_price, and venue_last_trade_time must be within the last 2 minutes; otherwise NO TRADE ("stale quote"). If the price is below $10, NO TRADE.
2. Report: get_earnings_calendar with start_date = today and days = 2; save it. Run `candidates --calendar calendar.json --date <today> --prices <quote file>`. The symbol must be listed, with its report date, timing and reaction day; otherwise NO TRADE.
3. Chain: get_option_chains underlying_symbol = SYMBOL; save it. If the response holds more than one chain for the symbol, NO TRADE ("ambiguous chain").
4. Expiration = the first date in the chain's expiration_dates that is on or after the reaction day and at most 8 calendar days after it. If there is none, NO TRADE. On a Friday, if that date is this week, NO TRADE.
5. Instruments: get_option_instruments with chain_id = the chain id, expiration_dates = the expiration, type = put, state = active; then type = call. Follow `next` cursors until none; save every page.
6. Quotes: every instrument whose strike is between 0.90 × price and 1.10 × price, puts and calls, through get_option_quotes in batches of at most 20 ids; save every response. If fewer than 6 strikes fall in that band, NO TRADE.
7. History: get_earnings_results symbol = SYMBOL (save it) and daily bars for the last 400 calendar days from TradingView get-ohlcv, symbol EXCHANGE:SYMBOL, interval 1D (Robinhood get_equity_historicals, interval day, span year, bounds regular, if TradingView fails; ignore interpolated bars); save them. With a short script, never by hand, compute the reaction move of each of the last 4 past reports that have a date before today and a timing: am → |close on the report date / close of the previous bar − 1| × 100; pm → |close of the next bar / close on the report date − 1| × 100. Skip a report with no timing or a missing bar. Pass the moves, comma-separated, as --history-moves (fewer than 4 is allowed; build then says the filter was skipped).
8. Run `build --symbol SYMBOL --price PRICE --date <today> --report-date <report date> --timing <am|pm> --chain <chain file> --instruments <every instruments file> --quotes <every quotes file> --history-moves a,b,c,d --max-loss 250 --json` and save the output. If build reports a different expiration from step 4, pull instruments and quotes for its expiration once and run build again. If the verdict is not TRADE, NO TRADE; report every width tried and why it failed.
   The build output gives the expiration, the four strikes with their instrument ids, the width, the mid credit, the natural credit, the limit credit (mid rounded DOWN to the tick), the tick, ROI, quantity, and the risk per condor and in total. Use them exactly as printed.

SIZE
- Quantity = the script's quantity. Risk = (width − limit credit) × 100 × quantity, at most $250. If the quantity is 0, NO TRADE.
- Floor credit = the larger of 0.90 × limit credit and width × 0.35 / 1.35 (the credit at which ROI is exactly 35%), rounded UP to the tick. Take it from the build output if it prints one; otherwise compute it with a one-line script, not by hand. No order in this run may be priced below the floor credit.

ORDER
If ORDER begins at or after the final-order time, place nothing and report.
1. Review a four-leg LIMIT order with review_option_order: direction 'credit', price = the limit credit, quantity = the script's quantity, type limit, good for day, regular hours, chain_symbol = the symbol, underlying_type = 'equity', account_number = the Agentic account. Legs, each with ratio 1, by instrument id from the build output: sell / open the short put, buy / open the long put, sell / open the short call, buy / open the long call.
2. If the review shows any warning or alert, place nothing further and report it verbatim. Exception: a warning only about the bid-ask spread, or about the limit price being at or below the mid, is pre-acknowledged. If the review's collateral or maximum loss exceeds width × 100 × quantity, place nothing and report it.
3. Place the order with place_option_order, with the same parameters and a fresh ref_id. Record the order id.
4. Wait until it fully fills, 3 minutes pass, or the final-order time arrives, whichever comes first, checking it once a minute. Between checks, wait about 60 seconds using whatever wait method is available. If no wait method works, re-check the current time and check again as soon as at least a minute has passed. Do not end the run because a wait failed.
5. If it is fully filled, go to REPORT.
6. If it is not fully filled:
   a. Second price = limit credit − one tick, but never below the floor credit. If the second price equals the limit credit, do not cancel: leave the first order working and go to step 8.
   b. If it is at or after the final-order time, go to step 8.
   c. Cancel the order, confirm the cancel succeeded, and read the filled quantity. If the cancel failed because it filled, go to REPORT.
   d. If some condors filled (a partial), place nothing more and report the partial; the exit routine closes whatever is open.
   e. Otherwise review (same warning rule as step 2) and place one order for the same quantity at the second price. Never place a third order.
7. Wait until the second order fully fills or the purchase deadline arrives, checking once a minute as in step 4.
8. At the purchase deadline, cancel any order of yours that is still open, confirm the cancel, and read the final filled quantity and average credit.
9. Never place a MARKET order. Never price an order below the floor credit. Never place more than two orders. Never place a new order after the final-order time. Never hold an unfilled order past the purchase deadline. Never trade any symbol except the pick, never any contracts except the four legs the script printed, never a one-leg or two-leg order, never more than the script's quantity. Never sell naked; every short leg has its long wing in the same order.

REPORT
Summarize:
- date and time; the result of every pre-check; whether the symbol came from the Routine's message, the scan report, or a fresh scan
- the build output for the pick: price, report date and timing, reaction day, expiration, straddle and implied move %, the history moves and the filter result, the four strikes, width, mid credit, natural credit, limit credit, tick, floor credit, ROI, quantity, risk per condor and in total, each short leg's bid, ask, spread %, delta, volume and open interest, and every width tried and why it failed
- capacity before this trade: open condors and their risk
- every order: price, quantity, time placed, order id, result (filled, partially filled, cancelled), and the average fill credit
- the final position: the four legs with instrument ids, quantity, credit received, maximum loss, the reaction day and expiration for the exit routine
- the exact reason for NO TRADE, if any, including any script error verbatim
