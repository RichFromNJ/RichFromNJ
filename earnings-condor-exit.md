You are closing earnings iron condors in my Robinhood account on the reaction day, the session after the company reported. The condor was sold the day before for the implied-volatility crush; it is bought back today, win or lose, and never held into expiration. Follow these instructions exactly. Do not improvise and do not ask questions. If any step fails or any data is missing, place NO order for the affected condor and report why.

AUTHORIZATION
I pre-authorize you to review, place, cancel, and re-place the four-leg closing debit LIMIT orders described in this prompt, including the final attempt one tick above the natural debit, without asking me first. This authorization covers nothing else.

ACCOUNT
Use the single Robinhood account that is agent-enabled (nickname "Agentic"). Never touch any other account.

TIMES (all ET; on a half-day, use the time measured from today's actual close for the afternoon run)
This prompt runs twice on the reaction day. A run that starts before noon is the morning run; any other start is the afternoon run.
- Morning run: start = 9:40am, final-order time = 9:52am, deadline = 9:55am (15 minutes after the start).
- Afternoon run: start = 3:30pm (30 minutes before the close), final-order time = 3:47pm (13 minutes before the close), deadline = 3:50pm (10 minutes before the close).
- No new order may be placed after the deadline of the run.

SCRIPT
- The close decision comes from the repository's earnings_condor.py, run from the RichFromNJ checkout as `python3 earnings_condor.py exit --time HH:MM --date <today> --reaction-day <reaction day> --expiration <expiration> --credit <credit received> --buyback <natural debit> --json`. Its rules: on the reaction day, from 9:40am until 3:30pm, CLOSE_ALL when the buyback costs 30% of the credit or less, otherwise HOLD; at or after 3:30pm, CLOSE_ALL regardless; before the reaction day, HOLD; after the reaction day, CLOSE_ALL and flag it; on the expiration day, CLOSE_ALL at any time from 9:40am.
- Compute the buyback and mid debits with a short script (Python in the shell) from the saved quote file, never by hand.
- Save every connector response to its own file, exactly as returned, in a folder named after today's date (for example condor/2026-10-14/).
- If the script is missing or fails, treat the decision as unknown: place no order for that condor and report the error verbatim. Exception: in the afternoon run the rule is CLOSE_ALL regardless, so proceed to ORDER and report the error.

PRE-CHECKS
1. The market must be open right now. If not, do nothing and report. If it is already past the deadline of this run, do nothing and report.
2. Find all open option positions in this account (get_option_positions, nonzero). Group them by symbol and expiration. A condor is a group of exactly four legs: a short put, a long put below it, a short call and a long call above it, all with the same quantity. If there is no condor, report "nothing to close" and stop.
3. A group that includes a short option but is not a complete condor is a broken condor. Take no action on it, and begin the report with "BROKEN CONDOR" and its legs. Long-only positions (for example the overnight EEM or SPY options) belong to other routines; never touch them.
4. If a condor already has an open order that you did not place in this run, take no action on it and report it.

DATA (for each condor)
1. Opening order: get_option_orders for the account, filtered to the symbol's chain. Find the filled four-leg credit order whose legs match the condor. Its fill date (ET) is the entry date, and its average net price is the credit received per condor. If no such order is found, the credit is unknown: in the morning run take no action on the condor and report it; in the afternoon run continue, since the decision there does not depend on the credit.
2. Reaction day: get_earnings_results symbol = SYMBOL; save it. Run `python3 earnings_condor.py candidates --calendar <that file> --date <entry date> --json`; the symbol's line gives the report date, timing and reaction day. If the symbol is not listed, or the entry date is unknown, use today as the reaction day and begin the report with "REACTION DAY ASSUMED" for that condor.
3. Expiration = the condor's expiration date. Tick = the legs' min_ticks (from get_option_instruments with ids = the four instrument ids, saved): below_tick for a price under cutoff_price, above_tick at or above it.
4. Quotes: get_option_quotes for the four instrument ids; save the response. From the saved file, with a script:
   - natural debit (the buyback) = short put ask + short call ask − long put bid − long call bid
   - mid debit = (short put mid + short call mid) − (long put mid + long call mid), each mid = (bid + ask) / 2
   If a short leg has no ask or a long leg has no bid, the debits are unknown for this check; re-check at the next check and report it.
5. Run the exit command with --time = the current time, --credit = the credit received and --buyback = the natural debit. The decision is CLOSE_ALL or HOLD.

CHECKS
- Morning run: run DATA steps 4 and 5 at the start and then every 2 minutes until the deadline, waiting about 120 seconds between checks using whatever wait method is available. If no wait method works, re-check the current time and check again as soon as at least two minutes have passed. Do not end the run because a wait failed. The first check that returns CLOSE_ALL goes to ORDER. If every check returns HOLD, leave the condor open for the afternoon run and report the lowest buyback seen and when.
- Afternoon run: the exit command returns CLOSE_ALL at or after 3:30pm. Go to ORDER at once.

PRICES
- First price = the mid debit, rounded UP to the tick.
- Re-price = the larger of the new mid debit rounded UP to the tick and the previous price plus one tick, but never above the natural debit.
- Final price = the natural debit plus one tick.
- Use a LIMIT order for every close, never a market order: Robinhood can cap the size of market option orders (OPTION_MARKET_OVER_CONTRACT_LIMIT, which allowed only 1 contract), and limit orders avoid that cap.

ORDER (for each condor with CLOSE_ALL)
If ORDER begins at or after the final-order time, skip steps 1–3 and go straight to step 4.
1. Review a four-leg LIMIT order with review_option_order: direction 'debit', price = the first price, quantity = the condor's quantity, type limit, good for day, regular hours, chain_symbol = the symbol, underlying_type = 'equity', account_number = the Agentic account. Legs, each with ratio 1: buy / close the short put, sell / close the long put, buy / close the short call, sell / close the long call.
   - If the review shows any warning or alert, place nothing for this condor and report the warning verbatim. Exception: a warning only about the bid-ask spread, or about the limit price being at or above the mid, is pre-acknowledged.
   - Otherwise place it with place_option_order, same parameters, with a fresh ref_id. Record the order id.
2. Every 2 minutes until the final-order time, check the order:
   - If it is fully filled, the condor is closed. Stop working it.
   - If it is not fully filled: cancel it, confirm the cancel succeeded, and read the filled quantity. If the cancel failed because it filled, the condor is closed. Otherwise re-quote (DATA step 4), review and re-place the remaining quantity at the re-price, with the same warning rule as step 1.
3. Between checks, wait about 120 seconds as in CHECKS.
4. At the final-order time, if the condor is not fully closed:
   a. Cancel any open order you placed, confirm the cancel succeeded, and read the filled quantity.
   b. Re-quote. If a short leg has no ask, place nothing, report it, and try again next minute.
   c. Otherwise review and place a four-leg LIMIT order for the remaining quantity at the final price, good for day, regular hours, with the same legs and warning rule as step 1.
   d. Once a minute until the deadline, if it is not fully filled: cancel it, confirm the cancel, read the filled quantity, re-quote and re-place at the new final price, as in b–c.
5. At the deadline, cancel any order you placed that is still open, confirm the cancel, and read the final fills.

RULES
- Never place a MARKET order.
- Always close all four legs in one order. Never close one side, one leg, or more than the condor's quantity.
- Never open new positions. Never sell to open. Never buy to open.
- Never touch anything other than the condors found in PRE-CHECKS.
- Never cancel or modify an order you did not place in this run.

REPORT
If the afternoon run ends with any condor still open, begin the report with "STILL OPEN" and list each one (symbol, expiration, legs, quantity, last natural debit), so it shows first in the notification. "BROKEN CONDOR" and "REACTION DAY ASSUMED" lines also go first.
Then, for each condor:
- symbol, expiration, the four legs with instrument ids, quantity, entry date, credit received
- reaction day and timing, and whether it came from the earnings data or was assumed
- every check: time, natural debit, mid debit, decision
- every order placed: type (mid, re-price or final), price, quantity, time, order id and result
- fill price(s), whether it closed fully, and whether a mid, re-price or final order closed it
- profit or loss in dollars, as a percent of the credit received and as a percent of the maximum loss, after fees if visible
Also report:
- any condor skipped (no opening order, an existing order, no quotes, a warning, a script error) and why
- whether any wait between checks failed
