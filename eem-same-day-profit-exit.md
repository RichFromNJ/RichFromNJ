You are monitoring EEM option positions bought TODAY and selling them at a profit target in my Robinhood account. Follow these instructions exactly. Do not improvise, do not ask questions, and if any step fails, any data is missing, or anything is ambiguous, place NO order for the affected position and report why.

AUTHORIZATION
I pre-authorize you to review, place, cancel, and re-place the EEM option SELL TO CLOSE orders described in this prompt, including the final limit orders below the bid, without asking me first. This authorization covers nothing else.

ACCOUNT
Use the single Robinhood account that is agent-enabled (nickname "Agentic"). Never touch any other account.

TIMES (all ET; on a half-day, use the time measured from today's actual close instead)
- Start = 3:54pm (6 minutes before today's close).
- Final-order time = 3:56pm (4 minutes before today's close).
- Last order time = 3:59pm (1 minute before today's close). No new order may be placed after this time.
- Close = 4:00pm (today's actual close).

PRE-CHECKS
1. Today must be Mon–Fri and the market must be open right now. If not, do nothing and report.
2. If it is already at or past the close, do nothing and report.
3. If any open EEM BUY order exists in this account, do not touch it. Report it, and continue with the positions that qualify.

QUALIFYING POSITIONS
A position qualifies only if ALL of these are true:
1. It is an open LONG EEM option position (calls or puts) in this account.
2. Every contract in it was bought with a BUY TO OPEN order that FILLED TODAY. Check today's filled option orders to confirm.
3. If a position contains any contracts bought before today, it does NOT qualify. Take no action on it and report it. Those positions belong to the next-morning exit routine.
Average cost for a qualifying position = the quantity-weighted average fill price per share of today's buy fills in that contract, excluding fees. Record it once at the start and use it for the whole run.

PROFIT
- Profit % = (current bid − average cost) / average cost × 100, using per-share option prices as quoted.
- Compute it with a script (for example, Python in the shell), not by hand.
- If the contract has no bid, profit % is unknown. Treat it as below 40% for that check and report it.

PRICES
- Final price = bid − 0.05, but never below 1.39 × average cost (rounded UP to a valid tick).
- Use a LIMIT order for every sell, never a market order: Robinhood can cap the size of market option orders (OPTION_MARKET_OVER_CONTRACT_LIMIT, which allowed only 1 contract), and limit orders avoid that cap.

LOOP
1. Run a CHECK immediately at the start.
2. Then run a CHECK once every minute until the close. Between checks, wait about 60 seconds using whatever wait method is available. If no wait method works, re-check the current time and run the next CHECK as soon as at least a minute has passed since the last one.
3. Do not end the run early just because a check found nothing to do, and do not end it because a wait method failed.
4. End the run at the close, or earlier once every qualifying position is fully closed.
5. Keep track of every order you place (order ID, type, price, quantity, time) for the whole run.

CHECK (for each qualifying position that is not yet fully closed)
1. Re-quote the contract and compute profit % from the current bid.
2. If it is before the final-order time:
   a. If no sell order of yours is working for this position and profit % is 40% or more:
      - Limit price = the mid price rounded DOWN to a valid tick, but never below the bid and never below 1.40 × average cost (rounded UP to a valid tick).
      - Review a SELL TO CLOSE LIMIT order for the full remaining quantity at that price, good for day.
      - If the review shows any warning or alert, place nothing for this position and report the warning verbatim.
      - Otherwise, place it.
   b. If a sell limit order of yours is already working, leave it in place. Do not cancel or re-price it.
   c. If profit % is below 40% and no sell order is working, do nothing this minute.
3. If it is at or after the final-order time and at or before the last order time:
   a. If a sell limit order of yours is still working (unfilled or partially filled):
      - If profit % is greater than 39%: cancel the limit order, confirm the cancel succeeded, and read the final filled quantity. Re-quote, and if profit % is still greater than 39%, review a SELL TO CLOSE LIMIT order for the remaining quantity at the final price, good for day, regular hours, and place it.
      - If the cancel failed because the order filled, update the totals and place nothing further for this position.
      - If profit % is 39% or less, leave the limit order working and check again next minute.
   b. If no sell order of yours exists and profit % is 40% or more: re-confirm profit % is greater than 39%, then review a SELL TO CLOSE LIMIT order for the full remaining quantity at the final price, good for day, regular hours, and place it.
   c. If profit % is below 40% and no sell order is working, do nothing this minute.
   d. At the final-order step, a review warning only about the bid-ask spread, or about the limit price being below the mid or at or below the bid, is pre-acknowledged. Any other warning: place nothing for this position and report it verbatim.
4. After the last order time: place no new orders. Any working order stays until the close and then expires. An unsold position stays open for the next-morning exit routine.

RULES
1. Never place a MARKET order.
2. Never place a sell order priced below 1.39 × average cost (rounded UP to a valid tick), and never place a final-price order when profit % is 39% or less.
3. Never sell more contracts than the qualifying position holds.
4. Never open new positions. Never buy anything. Never sell to open.
5. Never touch any option or position other than qualifying long EEM options.
6. Never cancel or modify an order you did not place in this run.

REPORT
Summarize:
- date, start time, end time, and how many checks ran
- each qualifying position: contract, quantity, average cost, highest profit % seen and when
- every order placed: type (mid limit or final limit), price, quantity, time, and result (filled, partially filled, cancelled, expired)
- final outcome for each position: sold (fill prices and realized profit %) or held for the next-morning exit
- any positions skipped (bought before today, no bid, warnings) and why
- any open EEM buy orders found at the start
- whether any wait between checks failed, and how you handled it
