You are closing earnings iron condors in my Robinhood account on the reaction day, the session after the company reported. The condor was sold the day before for the implied-volatility crush; it is bought back today, win or lose, and never held into expiration. Follow these instructions exactly. Do not improvise and do not ask questions. If any step fails or any data is missing, place NO order for the affected condor and report why.

AUTHORIZATION
I pre-authorize you to review, place, cancel, and re-place the four-leg closing debit LIMIT orders described in this prompt, including the final attempt one tick above the natural debit, without asking me first. This authorization covers nothing else.

ACCOUNT
Use the single Robinhood account that is agent-enabled (nickname "Agentic"). Never touch any other account.

TIMES (all ET; on a half-day, use the time measured from today's actual close for the afternoon run, and pass --close 13:00 to the script)
This prompt runs twice every trading day, so a condor still open after its reaction day is closed the next session instead of waiting for the expiration-day safety close. A run that starts before noon is the morning run; any other start is the afternoon run. On a day that is not a condor's reaction day the script returns HOLD before it and CLOSE_ALL after it.
- Morning run: start = 9:40am, final-order time = 9:52am, deadline = 9:55am (15 minutes after the start).
- Afternoon run: start = 3:30pm (30 minutes before the close), final-order time = 3:47pm (13 minutes before the close), deadline = 3:50pm (10 minutes before the close).
- No new order may be placed after the deadline of the run.

SCRIPT
- The debits, the order prices and the close decision come from the repository's earnings_condor.py, run from the RichFromNJ checkout as
  `python3 earnings_condor.py buyback --quotes <quotes file> --instruments <instruments file> --short <short put id> <short call id> --long <long put id> <long call id> [--previous <previous price>] --credit <credit received> --time HH:MM --date <today> --reaction-day <reaction day> --expiration <expiration> --close <today's close, 16:00 or 13:00> --json`
  It prints the natural debit (the buyback: short asks − long bids), the mid debit, the tick, the first price, the re-price (with --previous) and the final price, and `decision` (the same as the `exit` subcommand with --buyback = the natural debit). Omit --credit when the credit is unknown. Never compute a debit, tick or price yourself.
- The decision's rules: on the reaction day, from 9:40am until 30 minutes before the close (3:30pm; 12:30pm with --close 13:00), CLOSE_ALL when the buyback costs 30% of the credit or less, otherwise HOLD; from 30 minutes before the close, CLOSE_ALL regardless; before the reaction day, HOLD; after the reaction day, CLOSE_ALL and flag it; on the expiration day, CLOSE_ALL at any time from 9:40am.
- Save every connector response to its own file, exactly as returned, in a folder named after today's date (for example condor/2026-10-14/).
- If the script is missing or fails, the debits, prices and decision are unknown: place no order for that condor at this check, re-quote and run it again at the next check (once a minute after the final-order time), and report the error verbatim. Prices are never computed by hand.

PRE-CHECKS
1. The market must be open right now. If not, do nothing and report. If it is already past the deadline of this run, do nothing and report.
2. Find all open option positions in this account (get_option_positions, nonzero). Group them by symbol and expiration. A condor is a group of exactly four legs: a short put, a long put below it, a short call and a long call above it, all with the same quantity. If there is no condor, report "nothing to close" and stop.
3. A group that includes a short option but is not a complete condor is a broken condor. Take no action on it, and begin the report with "BROKEN CONDOR" and its legs. Long-only positions (for example the overnight EEM or SPY options) belong to other routines; never touch them.
4. If a condor already has an open order that you did not place in this run, take no action on it and report it.
5. A condor whose opening order filled today (ET) is never closed today; take no action on it. It is the entry routine's new position.

DATA (for each condor)
1. Opening order: get_option_orders for the account, filtered to the symbol's chain. Find the filled four-leg credit order whose legs match the condor. Its fill date (ET) is the entry date, and its average net price is the credit received per condor. If no such order is found, the credit is unknown: in the morning run take no action on the condor and report it; in the afternoon run continue and omit --credit, since the decision there does not depend on the credit.
2. Reaction day: get_earnings_results symbol = SYMBOL; save it. Run `python3 earnings_condor.py candidates --calendar <that file> --date <entry date> --json`; the symbol's line gives the report date, timing and reaction day. If the symbol is not listed, or the entry date is unknown, the reaction day is unknown: never assume one. Take no action on that condor and begin the report with "REACTION DAY UNKNOWN" for it, unless the expiration is today or earlier, in which case pass --reaction-day = the entry date's next trading day if known, else today (the script then returns CLOSE_ALL from 9:40am on the expiration day).
3. Expiration = the condor's expiration date. Instruments: get_option_instruments with ids = the four instrument ids; save it (it carries the legs' min_ticks, which the script uses for the tick).
4. Quotes: get_option_quotes for the four instrument ids; save the response. Run the buyback command on the saved files with --time = the current time. A quote field that is missing or null means no quote: the script then fails, the debits are unknown for this check; re-check at the next check and report it. A long leg's bid of 0.00 is a real bid of zero (a far wing is often worthless after the crush): it counts as 0 in the natural debit, its mid is half its ask, and the close goes ahead. Only a short leg with no ask (null or 0.00) makes the natural debit unknown.
5. The decision is the buyback output's `decision.action`: CLOSE_ALL or HOLD.

CHECKS
- Morning run: run DATA steps 4 and 5 at the start and then every 2 minutes until the deadline, waiting about 120 seconds between checks using whatever wait method is available. If no wait method works, re-check the current time and check again as soon as at least two minutes have passed. Do not end the run because a wait failed. The first check that returns CLOSE_ALL goes to ORDER. If every check returns HOLD, leave the condor open for the afternoon run and report the lowest buyback seen and when.
- Afternoon run: from 30 minutes before the close (3:30pm, or 12:30pm on a 13:00 half-day with --close 13:00) the decision is CLOSE_ALL on the reaction day and after it. Go to ORDER at once. If it returns HOLD in the afternoon run, the condor's reaction day is a later day: leave it open and report it.

PRICES (all from the buyback command's output; never computed by hand)
- First price = `first_price`: the mid debit, rounded UP to the tick.
- Re-price = `reprice` from a fresh buyback run with --previous = the previous order's price: the larger of the new mid debit rounded UP to the tick and the previous price plus one tick, but never above the natural debit.
- Final price = `final_price`: the natural debit plus one tick.
- Use a LIMIT order for every close, never a market order: Robinhood can cap the size of market option orders (OPTION_MARKET_OVER_CONTRACT_LIMIT, which allowed only 1 contract), and limit orders avoid that cap.

ORDER (for each condor with CLOSE_ALL)
If ORDER begins at or after the final-order time, skip steps 1–3 and go straight to step 4.
1. Review a four-leg LIMIT order with review_option_order: direction 'debit', price = the first price, quantity = the condor's quantity, type limit, good for day, regular hours, chain_symbol = the symbol, underlying_type = 'equity', account_number = the Agentic account. Legs, each with ratio 1: buy / close the short put, sell / close the long put, buy / close the short call, sell / close the long call.
   - If the review shows any warning or alert, place nothing for this condor and report the warning verbatim. Exception: a warning only about the bid-ask spread, or about the limit price being at or above the mid, is pre-acknowledged.
   - Otherwise place it with place_option_order, same parameters, with a fresh ref_id. Record the order id.
2. Every 2 minutes until the final-order time, check the order:
   - If it is fully filled, the condor is closed. Stop working it.
   - If it is not fully filled: cancel it, confirm the cancel succeeded, and read the filled quantity. If the cancel failed because it filled, the condor is closed. Otherwise re-quote (DATA step 4, with --previous = the cancelled price), review and re-place the remaining quantity at its reprice, with the same warning rule as step 1.
3. Between checks, wait about 120 seconds as in CHECKS.
4. At the final-order time, if the condor is not fully closed:
   a. Cancel any open order you placed, confirm the cancel succeeded, and read the filled quantity.
   b. Re-quote and re-run the buyback command. If a short leg has no ask (the script fails), place nothing, report it, and try again next minute. A long leg's 0.00 bid is not a reason to wait.
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
If the afternoon run ends with any condor still open on or after its reaction day, begin the report with "STILL OPEN" and list each one (symbol, expiration, legs, quantity, last natural debit), so it shows first in the notification. "BROKEN CONDOR" and "REACTION DAY UNKNOWN" lines also go first. If the script's decision carries a `flag` (for example "still open after the reaction day; should not happen"), begin the report with "FLAG: <flag>" for that condor.
Then, for each condor:
- symbol, expiration, the four legs with instrument ids, quantity, entry date, credit received
- reaction day and timing, from the earnings data (or "unknown")
- every check: time, natural debit, mid debit, decision
- every order placed: type (mid, re-price or final), price, quantity, time, order id and result
- fill price(s), whether it closed fully, and whether a mid, re-price or final order closed it
- profit or loss in dollars, as a percent of the credit received and as a percent of the maximum loss, after fees if visible
Also report:
- any condor skipped (no opening order, an existing order, no quotes, a warning, a script error) and why
- whether any wait between checks failed
