# Automated plan for the Swing Trading & ER course

What to automate from the course, how it runs, and the gates before any of it trades real money. The reasoning is in [COURSE-EVALUATION.md](COURSE-EVALUATION.md).

## 1. Decision

The earnings iron condor is the only course strategy with fixed rules, so it is the only one built. It lost money in the 2026 replay: 24 trades, profit factor 0.39. So it runs **signals-only**. The scan routine reports a pick every afternoon, and nothing is ordered until the forward record clears the gate in section 6.

| Course strategy | Decision | Reason |
|---|---|---|
| Earnings iron condor | **Built, signals-only** | Fixed rules, all inputs on the Robinhood connector, but negative in the 2026 replay |
| Earnings iron butterfly | Not built | Same inputs and a narrower profit zone; only worth testing if the condor clears its gate |
| Pre-earnings calls, puts and straddles | Do not automate | Chart-read entries; your own research found bought calls lose |
| Calendars, post-earnings butterflies | Do not automate | Discretionary strikes and targets |
| Gap-and-go credit spread | Research backlog | Fully mechanical; backtest on the daily bars in research/data first |
| Bollinger setups, SSL/TRIX/vortex formula | Do not automate | Parameters fitted by eye on hindsight charts |
| Elliott wave, Fibonacci targets | Do not automate | Not testable as taught |
| Bullocks, repairs, up-sizing after losses | Never | Martingale: adds risk to losing positions |
| Green Goose EEM and SPY | Already automated | Keep your measured rules, not the course's 58% claim |

## 2. What was built

One tested module does every calculation. Each routine prompt pulls data, saves it, runs the module and acts only on what it prints, the same pattern as the EEM routines.

| File | Role |
|---|---|
| `earnings_condor.py` | Subcommands: candidates, moves, build, rank, exit, buyback, score |
| `tests/test_earnings_condor.py` | Unit tests plus a build on live MS fixtures from Oct 13, 2026 |
| `earnings-condor-scan.md` | 3:25pm ET: candidates, builds, ranked pick. Places no orders |
| `earnings-condor-entry.md` | 3:38pm ET: one 4-leg credit limit order for the pick. **Not scheduled in phase 1** |
| `earnings-condor-exit.md` | 9:40am and 3:30pm ET every trading day: close condors on or after their reaction day |
| `earnings-condor-expiration-safety-close.md` | 10:00am ET: close anything still open on its expiration day |
| `research/earnings_condor_replay.py` | Scores the rules on saved 2026 option closes |
| `research/earnings_condor_check.py` | Lists the expired contracts to fetch for new events and scores them |

## 3. The rules

Every number is a field of `earnings_condor.Params`.

| Rule | Value | Course source |
|---|---|---|
| Candidate | Verified report: pm today, or am on the next trading day | s3, s5 |
| Price floor | $10 | s1, s3 |
| Expiration | First listed date on or after the reaction day, at most 8 days later | s3, s7 |
| Expected move | ATM call mid plus ATM put mid | s3 |
| Short strikes | One straddle from the price on each side, rounded outward | s3, s5 |
| Wings | $1, then $2, $2.50, $5; the first that passes every check | s3, s5 |
| Credit | Limit = mid credit rounded down to the tick; ROI at least 35% | s3 |
| Liquidity | Short-leg spread at most 15% of mid; volume at least 15 or open interest at least 100; natural credit at least 75% of mid | s5, s6 |
| Short delta | At most 0.35 | s6 |
| Size | floor($250 / risk per condor); the second order is re-sized at its own price | s1, s3 |
| History | At least 3 of the last 4 reaction moves within today's implied move | s5, s7 |
| Exit | Reaction day: close at 9:40am if the buyback costs 30% of the credit or less, otherwise at 3:30pm | s5, s6 |
| Limits | One new condor a day, at most 2 open, $500 open risk, limit orders only | s5, s8 |

## 4. Schedule (ET)

| Time | Routine | Phase 1 | Phase 2+ |
|---|---|---|---|
| 3:25pm Mon to Fri | Scan | Runs, reports the pick | Runs |
| 3:38pm Mon to Fri | Entry | **Off** | One 4-leg credit limit; unfilled orders cancelled by 3:49pm |
| 9:40am and 3:30pm | Exit | Off, nothing to close | Closes condors on or after the reaction day |
| 10:00am | Expiration safety close | Off | Closes anything expiring today |

Earnings seasons run about six weeks from the second week of January, April, July and October. Outside them the scan mostly reports "PICK: none".

## 5. Hard limits

- Never a market order. Never a naked short leg. Never a condor that expires the day it opens.
- Maximum loss $250 per condor and $500 across open condors.
- Never add to a losing position, roll it, or repair it. Close it.
- Before phase 2, add a stop to the entry routine: no new condor after 3 full losses in a row, until you review and re-enable. The routines do not enforce this yet.
- Any check that cannot complete means no order and a report saying why.
- Condors sell two legs inside a defined-risk order. That needs the same carve-out from "never sell to open" that you approved for the Connors put spreads.

## 6. Phases and gates

| Phase | What runs | Gate to the next phase |
|---|---|---|
| 0. Replay (done) | 24 condors on 2026 closes: 12 wins, PF 0.39, -$875 | Failed. The plan stays signals-only |
| 1. Signals-only, Oct 13 to Nov 25, 2026 | Scan only. After each reaction day, fetch the picks' closes with `research/earnings_condor_check.py` and score them | At least 25 scored picks with PF at least 1.3, and the 2026 replay plus phase 1 together at PF 1.0 or better |
| 2. Live, 1 contract | Scan, entry, exit and safety close; at most one condor open | 25 live trades, realized PF at least 1.3, fills within 10% of the logged mid |
| 3. Live, up to 2 open | $500 open-risk cap | Reviewed each season |

If phase 1 fails too, retire the condor. Two variants could be tested on the same saved data first: short strikes 1.5 straddles out, and holding to expiration. Neither has been tested yet.

## 7. Cash and other routines

- The account holds about $437. A $1-wide condor at a $0.35 credit holds $65 per contract for one or two sessions. On a day when a condor and an EEM entry both qualify, the EEM entry's $250 budget may be partly blocked.
- The exit and safety-close routines only touch complete four-leg condors. They leave the long-only EEM and SPY positions alone.

## 8. Questions for you

1. Schedule the scan routine now for the season under way, as phase 1 proposes?
2. If phase 1 passes, should the condor get its own funding instead of sharing the EEM cash?
3. Spend another session extending the replay to the course's off-radar names and the two variants above before phase 1 ends?
