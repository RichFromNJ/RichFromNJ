You are executing a rules-based overnight options trade on EEM in my Robinhood account. Follow these instructions exactly. Do not improvise, do not ask questions, and if any step fails, any data is missing, or anything is ambiguous, place NO trade and report why.

AUTHORIZATION
I pre-authorize you to review, place, cancel, and re-place the EEM option orders described in this prompt, including the final limit order at the ask, without asking me first. This authorization covers nothing else.

ACCOUNT
Use the single Robinhood account that is agent-enabled (nickname "Agentic"). Never touch any other account.

BUDGET
- Budget = $245 of premium for today's trade, counting every contract already filled today in the chosen contract.
- Hard cap: total premium plus fees must never exceed $250.

TIMES (all ET; on a half-day, use the earlier time in each pair)
- Final-order time = 3:48pm, or 10 minutes before today's close.
- Purchase deadline = 3:49pm, or 9 minutes before today's close.
- No buy order may be placed or left open after the purchase deadline.

PRE-CHECKS (skip the trade if any fail)
1. Today must be Mon–Thu and the market must be open right now. If it is already past the purchase deadline, NO TRADE.
2. Check for open (unfilled or partially filled) EEM option orders in this account:
   - If any open EEM SELL order exists, NO TRADE. Report it.
   - If an open EEM BUY TO OPEN order exists with ZERO contracts filled:
     a. Cancel it, then confirm the cancel succeeded and that it still shows zero filled.
     b. If the cancel succeeded, continue to pre-check 3. This builds a fresh order, which replaces the unfilled one.
     c. If the order filled before the cancel took effect, NO TRADE. Report the fill.
   - If an open EEM BUY TO OPEN order exists with SOME contracts filled (a "partial"):
     a. Cancel the unfilled remainder, then confirm the cancel and read the final filled quantity and average fill price.
     b. Record the contract and the cost filled so far (filled quantity × average fill price × 100).
     c. Skip pre-check 3, DATA, INDICATORS, DECISION, EXPIRATION, STRIKE and SIZE.
     d. Go straight to ORDER, step 4 (top-up loop), for that same contract with the cost filled so far.
3. If this account holds any open EEM option position, NO TRADE. Report it.

DATA
1. Pull EEM daily bars (regular hours) for the last 80 completed trading days.
2. Remove every placeholder bar: any bar marked interpolated. These are gap-fill bars with no real trading (open, high, low and close all equal, zero volume). Never use them in any calculation.
3. If yesterday's completed bar is missing or was a placeholder, NO TRADE. Report it.
4. Build today's bar from today's open, today's high and low so far, and the current last price as the close.
5. If the historical data already contains a bar dated today, REPLACE it with the bar from step 4. Never count today twice.
6. If fewer than 60 completed bars remain, or today's open or the last price is missing, NO TRADE.

INDICATORS
Compute every indicator with a script (for example, Python in the shell), not by hand. Use the bar series from DATA, ending with today's bar.
- RSI(2): Wilder smoothing, period 2. Seed with the simple average of the first 2 gains/losses.
- ADX(5), +DI(5), -DI(5): standard Wilder method, period 5 for both DI and ADX smoothing.
- TRIX(3): triple EMA (period 3, alpha = 2/(3+1)) of close. TRIX = 100 × (today's triple EMA / yesterday's triple EMA − 1). TRIX is a percent; typical values are well under 1.
Compute yesterday's ADX, +DI and -DI from the series ending with yesterday's completed bar.

DECISION (check in this exact order; the first rule that applies decides)
1. If ADX(5) today > 60 → NO TRADE.
2. If TRIX > 0.60 → PUTS. If TRIX < −0.60 → CALLS.
3. ADX "stab". "Between" means strictly between the two DI lines; equal to either line is NOT between.
   - If yesterday's ADX was above BOTH DI lines and today's ADX is between them → CALLS.
   - If yesterday's ADX was below BOTH DI lines and today's ADX is between them → PUTS.
4. If RSI(2) ≥ 85 → PUTS. If RSI(2) ≤ 15 → CALLS.
5. Otherwise: if the current price > today's open → CALLS. If the current price < today's open → PUTS. If they're equal → NO TRADE.

EXPIRATION
- Mon or Tue → target this week's Wednesday expiration.
- Wed or Thu → target this week's Friday expiration.
- If the target expiration isn't listed, use the next listed expiration after it, as long as it's within 3 calendar days after the target. Otherwise NO TRADE.
- Never use an expiration earlier than the target or one that expires today.
- Report whether you used the target or the fallback.

STRIKE
- CALLS: take the lowest strike strictly above the current price. If it is ≤ $0.30 above the price, buy it. Otherwise, buy the highest strike at or below the price (in the money).
- PUTS: take the highest strike strictly below the current price. If it is ≤ $0.30 below the price, buy it. Otherwise, buy the lowest strike at or above the price (in the money).
- If the chosen contract has no bid or no ask, NO TRADE.

SIZE
- Get the option quote. Quantity = floor(245 / (ask × 100)). If quantity is 0, NO TRADE.

ORDER
If ORDER begins at or after the final-order time, skip steps 1–4 and go straight to step 5.

1. Review a BUY TO OPEN limit order for the quantity from SIZE. Price = mid, rounded DOWN to a valid tick. Good for day.
2. If any review shows a warning or alert, place nothing further and report the warning verbatim. Exception: at step 5, a warning only about the bid-ask spread, or about the limit price being above the mid or at or above the ask, is pre-acknowledged.
3. Place the order.
4. Limit top-up loop. Repeat steps a–g until the budget is used up or the final-order time is reached:
   a. If an order is open, wait 3 minutes or until the final-order time, whichever comes first. Then cancel it, confirm the cancel succeeded, and read the final filled quantity and fill price.
   b. If the cancel failed because the order filled, update the totals and continue to step c.
   c. Cost filled so far = sum of (filled quantity × fill price × 100) for every fill today in this contract.
   d. If it is now the final-order time or later, stop the loop and go to step 5.
   e. Re-quote the same contract. If it has no ask, stop the loop and report. Next quantity = floor((245 − cost filled so far) / (ask × 100)).
   f. If the next quantity is 0, the budget is used up. Stop and report.
   g. Review a BUY TO OPEN limit order for the next quantity at the current ask (same warning rule as step 2). Then place it, and go back to step a.
5. Final limit order, at the final-order time. Use a LIMIT order, never a market order: Robinhood can cap the size of market option orders (OPTION_MARKET_OVER_CONTRACT_LIMIT, which allowed only 1 contract), and limit orders avoid that cap.
   a. Cancel any open buy order, confirm the cancel, and update the cost filled so far.
   b. Re-quote the contract. If it has no ask, place nothing and report.
   c. Final price = ask + 0.05. Final quantity = floor((245 − cost filled so far) / (final price × 100)).
   d. If the final quantity is 0, place nothing and report.
   e. Review a BUY TO OPEN LIMIT order for the final quantity at the final price, good for day, regular hours (warning rule in step 2). Then place it.
   f. At the purchase deadline, if any part of it is still open, cancel it, confirm the cancel, and report the final fills.
6. Only ever buy the chosen contract. Before the final limit order, never place a limit price above the current ask. The final limit order may be priced up to ask + 0.05, never higher.
7. Never place a MARKET order. Never exceed the $250 hard cap. Never sell to open. Never trade anything except EEM options. Never buy after the purchase deadline.

REPORT
Summarize:
- date and time
- price, today's open, RSI(2), ADX, +DI, −DI
- yesterday's ADX, +DI, −DI, and where ADX sat relative to the DI lines
- TRIX
- which rule decided
- expiration (target or fallback), the contract, total quantity, every fill price (marking which fill came from the final limit order), total cost including fees, budget left unspent
- how many times the limit order was re-placed
- whether this run started by cancelling an unfilled order or resuming a partial

If the run resumed a partial, the indicator fields don't apply; say so. Otherwise, report the exact reason for no trade.
