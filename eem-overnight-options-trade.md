You are executing a rules-based overnight options trade on EEM in my Robinhood account. Follow these instructions exactly. Do not improvise, do not ask questions, and if any step fails or any data is missing, place NO trade and report why.

ACCOUNT
Use the single Robinhood account that is agent-enabled (nickname "Agentic"). Never touch any other account.

PRE-CHECKS (skip the trade if any fail)
1. Today must be Mon–Thu and the market must be open today.
2. If I already hold any open EEM option position in this account, do not trade. Report it.

DATA
Pull EEM daily bars (regular hours) for the last 120 trading days, plus today's bar so far. For today's bar, use today's open, today's high and low so far, and the current last price as the close.

INDICATORS (compute yourself from the bars)
- RSI(2): Wilder smoothing, period 2.
- ADX(5), +DI(5), -DI(5): standard Wilder method, period 5.
- TRIX(3): triple EMA (period 3) of close; TRIX = 100 × (today's triple EMA / yesterday's triple EMA − 1).

DECISION (check in this exact order; the first rule that applies decides)
1. If ADX(5) today > 60 → NO TRADE.
2. If TRIX > 60 → PUTS. If TRIX < −60 → CALLS.
3. ADX "stab": if yesterday ADX was above BOTH DI lines and today ADX is between them → CALLS. If yesterday ADX was below BOTH DI lines and today ADX is between them → PUTS. (Only the first day ADX enters the zone counts.)
4. If RSI(2) ≥ 85 → PUTS. If RSI(2) ≤ 15 → CALLS.
5. Otherwise: if current price > today's open → CALLS. If current price < today's open → PUTS. If equal → NO TRADE.

EXPIRATION
- Mon or Tue → this week's Wednesday expiration.
- Wed or Thu → this week's Friday expiration.
- If that exact expiration isn't listed, use the next listed expiration after it, as long as it's within 3 calendar days. Otherwise NO TRADE.

STRIKE
- CALLS: take the lowest strike above the current price. If it is ≤ $0.30 above the price, buy it. If not, buy the highest strike at or below the price (in the money).
- PUTS: take the highest strike below the current price. If it is ≤ $0.30 below the price, buy it. If not, buy the lowest strike at or above the price (in the money).

SIZE AND ORDER
- Get the option quote. Quantity = floor(250 / (ask × 100)). If quantity is 0, NO TRADE.
- Review the order first, then place a BUY TO OPEN limit order at the mid price (rounded to a valid tick), good for day.
- If not filled within 3 minutes, cancel and re-place at the ask, as long as quantity × ask × 100 ≤ $250. If still unfilled by 3:58pm ET, cancel and report.
- Never spend more than $250. Never sell to open. Never trade anything except EEM options.

REPORT
Summarize: date, price, open, RSI(2), ADX, +DI, −DI, yesterday's ADX position, TRIX, which rule decided, the contract, quantity, fill price, total cost — or the reason for no trade.
