You are closing overnight SPY option positions in my Robinhood account. Follow these instructions exactly. Do not improvise and do not ask questions. If any step fails or any data is missing, place NO order for the affected position and report why.

AUTHORIZATION
I pre-authorize you to review, place, cancel, and re-place the SPY option SELL TO CLOSE orders described in this prompt, including the final limit orders below the bid, without asking me first. This authorization covers nothing else.

ACCOUNT
Use the single Robinhood account that is agent-enabled (nickname "Agentic"). Never touch any other account.

TIMES (all ET)
- Final-order time = 9:38am.
- Final-order deadline = 9:45am. Do not place any new order after this time.

PRE-CHECKS
1. The market must be open today and right now. If not, do nothing and report.
2. Find all open LONG SPY option positions in this account. If none, report "nothing to close" and stop.
3. If a position already has an open sell order that you did not place in this run, take no action on that position and report it.

PRICES
- Mid = (bid + ask) / 2, rounded DOWN to a valid tick, but never below the bid.
- Final price = bid − 0.05, but never below 0.01.
- If a contract has no bid, do not place a limit order for it this minute; re-check next minute and report it.

STEPS (for each position)
If this run starts at or after the final-order time, skip steps 1–3 and go straight to step 4.

1. Review a SELL TO CLOSE LIMIT order for the full quantity at the mid, good for day.
   - If the review shows any warning or alert, place nothing for this position and report the warning verbatim.
   - Otherwise, place it.
2. Once a minute until the final-order time, check the order:
   - If it is fully filled, the position is closed. Stop working it.
   - If it is not fully filled and it has been working for at least 2 minutes at the same price:
     a. Cancel it, confirm the cancel succeeded, and read the filled quantity.
     b. If the cancel failed because it filled, the position is closed.
     c. Otherwise, re-quote and re-place for the remaining quantity at the new mid (or the bid, if the mid hasn't changed). Use the same review and warning rule as step 1.
3. Between checks, wait about 60 seconds using whatever wait method is available. If no wait method works, re-check the current time and check again as soon as at least a minute has passed. Do not end the run because a wait failed.
4. At the final-order time (9:38am), if the position is not fully closed. Use a LIMIT order, never a market order: Robinhood can cap the size of market option orders (OPTION_MARKET_OVER_CONTRACT_LIMIT, which allowed only 1 contract), and limit orders avoid that cap.
   a. Cancel any open limit order you placed, confirm the cancel succeeded, and read the filled quantity.
   b. If the contract has no bid, place nothing. Report it and leave the position open.
   c. Otherwise, review a SELL TO CLOSE LIMIT order for the remaining quantity at the final price, good for day, regular hours, then place it.
   d. A review warning only about the bid-ask spread, or about the limit price being below the mid or at or below the bid, is pre-acknowledged. Any other warning: place nothing for this position and report it verbatim.
   e. Once a minute until the final-order deadline, if it is not fully filled: cancel it, confirm the cancel succeeded, and read the filled quantity. If the cancel failed because it filled, the position is closed. Otherwise, re-quote and re-place the remaining quantity at the new final price, using the same rules as steps b–d. Wait between checks as in step 3.
5. By the final-order deadline (9:45am), if any order you placed is still open, cancel it, confirm the cancel, and report the final fills.

RULES
- Never place a MARKET order.
- Never sell more contracts than the position holds.
- Never open new positions. Never buy anything. Never sell to open.
- Never touch anything other than long SPY options.
- Never cancel or modify an order you did not place in this run.

REPORT
For each position, report:
- contract and quantity
- every order placed: type (mid limit or final limit), price, quantity, time, and result
- fill price(s), and whether it closed by a mid limit or a final limit below the bid
- entry cost, if visible
- profit or loss in dollars and percent

Also report:
- any position skipped, and why
- whether any wait between checks failed
