You are running a safety check on SPY options that expire today in my Robinhood account. Its job is to make sure no position held overnight is left open into its own expiration. Follow these instructions exactly. Do not improvise and do not ask questions. If any step fails or any data is missing, place NO order for the affected position and report why.

AUTHORIZATION
I pre-authorize you to review, place, cancel, and re-place the SPY option SELL TO CLOSE limit orders described in this prompt without asking me first. This authorization covers nothing else.

ACCOUNT
Use the single Robinhood account that is agent-enabled (nickname "Agentic"). Never touch any other account.

TIMES (all ET)
- Start = 10:00am.
- Deadline = 10:30am. Do not place any new order after this time.

PRE-CHECKS
1. The market must be open right now. If not, do nothing and report.
2. Find all open LONG SPY option positions in this account whose expiration date is TODAY. If none, report "nothing expiring today" and stop.
3. Only positions held from before today qualify. If a position includes any contracts bought today, take no action on it and report it.
4. If a qualifying position already has an open sell order that you did not place in this run, take no action on that position and report it.

PRICES
- Final price = bid − 0.05, but never below 0.01.
- If a contract has no bid, place no order for it this minute; re-check next minute and report it.
- Use a LIMIT order for every sell, never a market order: Robinhood can cap the size of market option orders (OPTION_MARKET_OVER_CONTRACT_LIMIT, which allowed only 1 contract), and limit orders avoid that cap.

STEPS (for each qualifying position)
1. Re-quote the contract. If it has a bid, review a SELL TO CLOSE LIMIT order for the full quantity at the final price, good for day, regular hours, then place it.
   - A review warning only about the bid-ask spread, or about the limit price being below the mid or at or below the bid, is pre-acknowledged. Any other warning: place nothing for this position and report the warning verbatim.
2. Once a minute until the deadline, check the order:
   - If it is fully filled, the position is closed. Stop working it.
   - If it is not fully filled: cancel it, confirm the cancel succeeded, and read the filled quantity. If the cancel failed because it filled, the position is closed. Otherwise, re-quote and re-place the remaining quantity at the new final price, using the same rules as step 1.
   - If there was no bid at step 1, try step 1 again.
3. Between checks, wait about 60 seconds using whatever wait method is available. If no wait method works, re-check the current time and check again as soon as at least a minute has passed. Do not end the run because a wait failed.
4. At the deadline (10:30am), cancel any order you placed that is still open, confirm the cancel, and read the final fills.

RULES
- Never place a MARKET order.
- Never sell more contracts than the position holds.
- Never open new positions. Never buy anything. Never sell to open.
- Never touch anything other than long SPY options expiring today.
- Never cancel or modify an order you did not place in this run.

REPORT
If any contracts expiring today are still open at the end, begin the report with "STILL OPEN — EXPIRES TODAY" and list each one (contract, quantity, last bid and ask), so it shows first in the notification.
Then, for each position:
- contract and quantity
- every order placed: price, quantity, time, and result
- fill price(s), and whether it was fully closed
- entry cost, if visible, and profit or loss in dollars and percent
Also report:
- any position skipped (bought today, an existing sell order, no bid, a warning) and why
- whether any wait between checks failed
