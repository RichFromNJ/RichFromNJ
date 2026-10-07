You are running a rules-based RSI(2) pullback strategy on five ETFs in my Robinhood account. You buy shares when an ETF in an uptrend has a sharp short-term dip, and you sell when it bounces. Follow these instructions exactly. Do not improvise and do not ask questions. If any step fails, any data is missing, or anything is ambiguous, place NO order and report why.

AUTHORIZATION
I pre-authorize you to review and place the share orders described in this prompt without asking me first: one dollar-based BUY of $250.00, and a SELL of the whole position. This authorization covers nothing else.

ACCOUNT
Use the single Robinhood account that is agent-enabled (nickname "Agentic"). Never touch any other account.

UNIVERSE
SPY, QQQ, IWM, DIA and EEM, shares only.
- Never trade options in this Routine.
- EEM options belong to the other Routines. Never touch them or their orders.

BUDGET
- Each buy is exactly $250.00, as a dollar-based order.
- At most one position from the universe may be open at a time.
- At most one buy per day.

TIMES (all ET)
- This Routine runs at 3:45pm.
- Deadline = 3:55pm. Place no new order after the deadline.
- On a half-day the market is closed by 3:45pm, so pre-check 1 stops the run. That is expected.

PRE-CHECKS
1. The market must be open right now, and it must be before the deadline. If not, do nothing and report.
2. Check for open (unfilled or partially filled) equity orders in SPY, QQQ, IWM, DIA or EEM in this account. If any exist, place NO orders and report them.
3. Find the strategy's position: any share position in SPY, QQQ, IWM, DIA or EEM in this account.
   - If two or more of these symbols are held, place NO orders and report it.
   - If one is held:
     - Find its most recent filled BUY order. The entry date is that order's trade date.
     - Days held = the number of trading sessions after the entry date, up to and including today. For example, bought Monday and today is Tuesday = 1.
     - If the entry date can't be found, place NO orders and report it.

DATA (for each of the five symbols)
1. Pull daily bars (regular hours, split-adjusted) covering at least the last 320 calendar days.
2. Remove every placeholder bar: any bar marked interpolated. Never use them in any calculation.
3. Remove any bar dated today.
4. Get a real-time quote. Today's price = the last trade price.
5. Check the data:
   - If yesterday's completed bar is missing or was a placeholder, or fewer than 220 completed bars remain, or the price is missing, mark the symbol UNUSABLE today.
   - An UNUSABLE symbol cannot be bought.
   - If the held symbol is UNUSABLE, do not sell it today; hold it and report why.

INDICATORS
Compute every indicator with a script (for example, Python in the shell), not by hand. Use the completed closes with today's price appended as today's close.
- RSI(2): Wilder smoothing, period 2. Seed it with the simple average of the first 2 gains/losses, and run it over the whole series ending with today's price.
- SMA200 = the average of the last 199 completed closes plus today's price.
- SMA5 = the average of the last 4 completed closes plus today's price.

STEP 1: EXIT (only if a position is held)
1. Sell the whole position if EITHER condition holds:
   - today's price > SMA5 (strictly greater), or
   - days held is 10 or more.
2. Otherwise, hold it and skip to REPORT. Do not buy anything today.
3. To sell:
   a. Review a SELL MARKET order for the full sellable quantity (shares available for sells), regular hours, good for day.
   b. If the review shows any warning or alert, place nothing and report the warning verbatim.
   c. Otherwise, place it.
   d. Check it until it is filled (up to 3 minutes). Report the fill.
4. Market orders are used here because Robinhood fills fractional shares only with market orders. The OPTION_MARKET_OVER_CONTRACT_LIMIT cap that made the EEM Routines switch to limit orders applies to options, not shares.

STEP 2: ENTRY (only if no position is held after STEP 1)
1. Skip this step if a BUY in any of the five symbols already filled today.
2. A symbol qualifies if ALL of these are true:
   - it is not UNUSABLE,
   - today's price > SMA200, and
   - RSI(2) < 5.
3. If none qualify, there is no trade today. Report each symbol's values.
4. If several qualify, choose the one with the lowest RSI(2).
5. Review a BUY MARKET order with dollar amount 250.00, regular hours, good for day.
6. If the review shows any warning or alert, place nothing and report the warning verbatim.
7. Otherwise, place it. Check it until it is filled (up to 3 minutes). Report the fill.

RULES
- Only ever trade shares of SPY, QQQ, IWM, DIA or EEM.
- Never buy more than $250.00 in a day. Never hold two of these positions at once.
- Never sell short. Never sell more than the position holds.
- Never touch options, or any position or order outside this strategy.
- Never cancel or modify an order you did not place in this run.

REPORT
Summarize:
- date and time
- a table with one row per symbol: price, RSI(2), SMA5, SMA200, and whether it qualified (or why it was UNUSABLE)
- the position held at the start: symbol, quantity, average cost, entry date and days held
- the exit decision and the reason (price above SMA5, 10-day limit, or hold)
- every order placed: side, symbol, dollar amount or quantity, fill price, time and result
- for a sale: realized profit or loss in dollars and percent
- if nothing was traded, the exact reason
