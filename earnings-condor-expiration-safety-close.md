You are running a safety check on earnings iron condors that expire today in my Robinhood account. Its job is to make sure no condor, or piece of one, is left open into its own expiration. Follow these instructions exactly. Do not improvise and do not ask questions. If any step fails or any data is missing, place NO order for the affected position and report why.

AUTHORIZATION
I pre-authorize you to review, place, cancel, and re-place the closing debit LIMIT orders described in this prompt, including the final attempt one tick above the natural debit, without asking me first. This authorization covers nothing else.

ACCOUNT
Use the single Robinhood account that is agent-enabled (nickname "Agentic"). Never touch any other account.

TIMES (all ET)
- Start = 10:00am.
- Final-order time = 10:27am.
- Deadline = 10:30am. Do not place any new order after this time.

PRE-CHECKS
1. The market must be open right now. If not, do nothing and report.
2. Find all open option positions in this account (get_option_positions, nonzero) whose expiration date is TODAY. Group them by symbol. If none, report "nothing expiring today" and stop.
3. Only positions held from before today qualify. If a group includes any leg opened today, take no action on it and report it.
4. If a qualifying group already has an open order that you did not place in this run, take no action on it and report it.
5. Classify each qualifying group:
   - a condor: exactly four legs, a short put, a long put below it, a short call and a long call above it, all with the same quantity. Close it with one four-leg order.
   - a vertical: exactly two legs of the same type, one short and one long, with the same quantity (a condor whose other side was already closed). Close it with one two-leg order.
   - anything else (a lone short leg, unequal quantities, three legs) is a broken position: place nothing, and begin the report with "STILL OPEN — EXPIRES TODAY" and its legs.
   Long-only positions (for example the overnight EEM or SPY options) belong to other routines; never touch them.

PRICES (from the repository's earnings_condor.py, run from the RichFromNJ checkout; never computed by hand)
- Instruments: get_option_instruments with ids = the group's instrument ids; save it (it carries the legs' min_ticks). Quotes: get_option_quotes for the same ids; save the response.
- Run `python3 earnings_condor.py buyback --quotes <quotes file> --instruments <instruments file> --short <every short leg id> --long <every long leg id> [--previous <previous price>] --json`. It prints the natural debit (short asks − long bids), the mid debit (short mids − long mids), the tick and:
  - first_price = the mid debit, rounded UP to the tick
  - reprice (with --previous) = the larger of the new mid debit rounded UP to the tick and the previous price plus one tick, but never above the natural debit
  - final_price = the natural debit plus one tick
- A quote field that is missing or null means no quote, and the script fails: place no order for the group this minute; re-check next minute and report it. A long leg's bid of 0.00 is a real bid of zero (the normal state of a worthless wing on expiration day): it counts as 0 in the natural debit and the close goes ahead. Only a short leg with no ask (null or 0.00) makes the natural debit unknown.
- Use a LIMIT order for every close, never a market order: Robinhood can cap the size of market option orders (OPTION_MARKET_OVER_CONTRACT_LIMIT, which allowed only 1 contract), and limit orders avoid that cap.

STEPS (for each qualifying group)
If this run starts at or after the final-order time, skip steps 1–3 and go straight to step 4.
1. Review a LIMIT order with review_option_order: direction 'debit', price = the first price, quantity = the group's quantity, type limit, good for day, regular hours, chain_symbol = the symbol, underlying_type = 'equity', account_number = the Agentic account. Legs, each with ratio 1: buy / close every short leg, sell / close every long leg.
   - If the review shows any warning or alert, place nothing for this group and report the warning verbatim. Exception: a warning only about the bid-ask spread, or about the limit price being at or above the mid, is pre-acknowledged.
   - Otherwise place it with place_option_order, same parameters, with a fresh ref_id. Record the order id.
2. Every 2 minutes until the final-order time, check the order:
   - If it is fully filled, the group is closed. Stop working it.
   - If it is not fully filled: cancel it, confirm the cancel succeeded, and read the filled quantity. If the cancel failed because it filled, the group is closed. Otherwise re-quote, re-run the buyback command with --previous = the cancelled price, review and re-place the remaining quantity at its reprice, with the same warning rule as step 1.
3. Between checks, wait about 120 seconds using whatever wait method is available. If no wait method works, re-check the current time and check again as soon as at least two minutes have passed. Do not end the run because a wait failed.
4. At the final-order time (10:27am), if the group is not fully closed:
   a. Cancel any open order you placed, confirm the cancel succeeded, and read the filled quantity.
   b. Re-quote and re-run the buyback command. If a short leg has no ask (the script fails), place nothing, report it, and try again next minute. A long leg's 0.00 bid is not a reason to wait.
   c. Otherwise review and place a LIMIT order for the remaining quantity at the final price, good for day, regular hours, with the same legs and warning rule as step 1.
   d. Once a minute until the deadline, if it is not fully filled: cancel it, confirm the cancel, read the filled quantity, re-quote and re-place at the new final price, as in b–c.
5. At the deadline (10:30am), cancel any order you placed that is still open, confirm the cancel, and read the final fills.

RULES
- Never place a MARKET order.
- Always close every leg of a group in one order. Never close one leg of a vertical or one side of a condor, and never more than the group's quantity.
- Never open new positions. Never sell to open. Never buy to open.
- Never touch anything other than the qualifying groups expiring today.
- Never cancel or modify an order you did not place in this run.

REPORT
If any qualifying leg expiring today is still open at the end, begin the report with "STILL OPEN — EXPIRES TODAY" and list each one (symbol, legs, quantity, last bid and ask of every leg), so it shows first in the notification.
Then, for each group:
- symbol, expiration, legs with instrument ids, quantity, and whether it was a condor or a vertical
- every order placed: type (mid, re-price or final), price, quantity, time, order id and result
- fill price(s), and whether it was fully closed
- credit received, if visible, and profit or loss in dollars and as a percent of the credit
Also report:
- any group skipped (opened today, an existing order, broken, no quotes, a warning) and why
- whether any wait between checks failed
