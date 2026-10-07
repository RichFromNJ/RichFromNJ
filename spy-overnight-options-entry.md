You are executing a rules-based overnight options trade on SPY in my Robinhood account. Follow these instructions exactly. Do not improvise, do not ask questions, and if any step fails, any data is missing, or anything is ambiguous, place NO trade and report why. The only judgment call you may make is the OTM-or-ITM choice described in STRIKE.

AUTHORIZATION
I pre-authorize you to review, place, cancel, and re-place the SPY option orders described in this prompt, including the final limit order at the ask, without asking me first. This authorization covers nothing else.

ACCOUNT
Use the single Robinhood account that is agent-enabled (nickname "Agentic"). Never touch any other account.

BUDGET
One budget applies whether the contract is out of the money (OTM) or in the money (ITM). STRIKE defines both. It is a daily limit.
- Premium budget = $195. Hard cap: total SPY premium plus fees today must never exceed $200.
- Spent today = sum of (filled quantity × fill price × 100) for every SPY BUY TO OPEN fill today in this account, including fills from earlier runs or orders.
- One type per day: once an OTM purchase has filled today, no ITM purchase may be made today. Once an ITM purchase has filled today, no OTM purchase may be made today.

TIMES (all ET; on a half-day, use the earlier time in each pair)
- Final-order time = 3:48pm, or 10 minutes before today's close.
- Purchase deadline = 3:49pm, or 9 minutes before today's close.
- No new buy order may be placed after the purchase deadline. The final limit order from ORDER step 5 is the only buy order allowed to stay open after it.

HOLIDAYS
NYSE full-day closures:
- 2026: Thu Nov 26, Fri Dec 25.
- 2027: Fri Jan 1, Mon Jan 18, Mon Feb 15, Fri Mar 26, Mon May 31, Fri Jun 18, Mon Jul 5, Mon Sep 6, Thu Nov 25, Fri Dec 24.
This list runs through December 31, 2027. From January 1, 2028, NO TRADE until the list is updated.

PRE-CHECKS (skip the trade if any fail)
1. Today must be Mon–Thu and the market must be open right now. If it is already past the purchase deadline, NO TRADE. If the market is closed tomorrow for a holiday (see HOLIDAYS), NO TRADE.
2. Check for open (unfilled or partially filled) SPY option orders in this account:
   - If any open SPY SELL order exists, NO TRADE. Report it.
   - If an open SPY BUY TO OPEN order exists with ZERO contracts filled:
     a. Cancel it, then confirm the cancel succeeded and that it still shows zero filled.
     b. If the cancel succeeded, continue to pre-check 3. This builds a fresh order, which replaces the unfilled one.
     c. If the order filled before the cancel took effect, NO TRADE. Report the fill.
   - If an open SPY BUY TO OPEN order exists with SOME contracts filled (a "partial"):
     a. Cancel the unfilled remainder, then confirm the cancel and read the final filled quantity and average fill price.
     b. Record the contract and classify it as OTM or ITM as described in pre-check 4.
     c. Skip pre-check 3, DATA, INDICATORS, DECISION, EXPIRATION, STRIKE and SIZE.
     d. Go straight to ORDER, step 4 (the attempt at the ask), for that same contract.
3. If this account holds any open SPY option position, NO TRADE. Report it.
4. Find every SPY BUY TO OPEN order that filled today in this account, whoever placed it. Classify each fill as OTM or ITM by comparing its strike with SPY's price at the time of the fill (use the 5-minute bar that contains the fill time). If that can't be determined, treat it as OTM. If any fills exist, today's type is locked to their type. If fills of both types exist, NO TRADE. Report what you found.

DATA
1. Pull SPY daily bars (regular hours) for the last 80 completed trading days.
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
1. Definitions. CALLS: a strike above the current SPY price is OTM; a strike at or below the price is ITM. PUTS: a strike below the current SPY price is OTM; a strike at or above the price is ITM.
2. Candidates: the nearest OTM strike and the nearest ITM strike, for the signal's option type and the chosen expiration. Only these two contracts may be bought. If pre-check 4 locked today's type, only the candidate of that type may be bought.
3. Remove a candidate if it has no bid or no ask, or if the budget can't buy one contract at the ask (ask × 100 > $195). If no candidate is left, NO TRADE. If one is left, choose it.
4. If both are left, choose OTM or ITM using your judgment. Weigh:
   - How far the OTM strike is from the current price. The closer it is, the more it behaves like the ITM contract.
   - Each contract's bid-ask spread as a percent of its mid. A wide spread costs more to get in and out.
   - Each contract's open interest and today's volume. A contract that barely trades may not fill.
   - Each contract's delta, and how many contracts the budget buys.
5. Report both candidates (strike, bid, ask, spread, open interest, volume, delta), which one you chose, and a short reason.

SIZE
- Get the chosen contract's quote. Quantity = floor((premium budget − spent today) / (ask × 100)). If quantity is 0, NO TRADE.

ORDER
If ORDER begins at or after the final-order time, skip steps 1–4 and go straight to step 5.

1. Review a BUY TO OPEN limit order for the quantity from SIZE. Price = halfway between the mid and the ask, rounded DOWN to a valid tick. Good for day.
2. If any review shows a warning or alert, place nothing further and report the warning verbatim. Exception: at steps 1, 4 and 5, a warning only about the bid-ask spread, or about the limit price being above the mid or at or above the ask, is pre-acknowledged.
3. Place the order.
4. One attempt at the ask:
   a. If an order is open, wait until it fully fills, 3 minutes pass, or the final-order time arrives, whichever comes first. Then cancel any unfilled part, confirm the cancel succeeded, and read the final filled quantity and fill price. If the cancel failed because the order filled, update the totals.
   b. Recalculate spent today.
   c. If it is now the final-order time or later, go to step 5.
   d. Re-quote the same contract. If it has no ask, go to step 5. Next quantity = floor((premium budget − spent today) / (ask × 100)).
   e. If the next quantity is 0, the budget is used up. Stop and report.
   f. Review a BUY TO OPEN limit order for the next quantity at the current ask (same warning rule as step 2). Then place it.
   g. Wait until it fully fills, 3 minutes pass, or the final-order time arrives, whichever comes first. Then go to step 5. Never place a second order at the ask.
5. Final limit order, after the attempt at the ask or at the final-order time, whichever comes first. Use a LIMIT order, never a market order: Robinhood can cap the size of market option orders (OPTION_MARKET_OVER_CONTRACT_LIMIT, which allowed only 1 contract), and limit orders avoid that cap.
   a. Cancel any open buy order, confirm the cancel, and recalculate spent today. If the cancel failed because the order filled, update the totals.
   b. Re-quote the contract. If it has no ask, place nothing and report.
   c. Final price = ask + 0.03. Final quantity = floor((premium budget − spent today) / (final price × 100)).
   d. If the final quantity is 0, place nothing and report.
   e. Review a BUY TO OPEN LIMIT order for the final quantity at the final price, good for day, regular hours (warning rule in step 2). Then place it.
   f. Do not cancel it. Leave it working until it fills or expires at the end of the trading day. Check it once a minute until it is fully filled or no longer open, then report the final fills.
6. Only ever buy the chosen contract. Before the final limit order, never place a limit price above the current ask. The final limit order may be priced up to ask + 0.03, never higher.
7. Never place a MARKET order. Never exceed the $200 hard cap. Never buy both OTM and ITM on the same day. Never sell to open. Never trade anything except SPY options. Never place a new buy order after the purchase deadline.

REPORT
Summarize:
- date and time
- price, today's open, RSI(2), ADX, +DI, −DI
- yesterday's ADX, +DI, −DI, and where ADX sat relative to the DI lines
- TRIX
- which rule decided
- any SPY purchases found by pre-check 4 and the type they locked
- both strike candidates (strike, bid, ask, spread, open interest, volume, delta), OTM or ITM chosen, and why
- expiration (target or fallback), the contract, total quantity, every fill price (marking which fill came from the final limit order), total cost including fees, budget left unspent under the $200 cap
- the price and result of each order: halfway, ask, and final (ask + 0.03)
- whether this run started by cancelling an unfilled order or resuming a partial

If the run resumed a partial, the indicator fields don't apply; say so. Otherwise, report the exact reason for no trade.
