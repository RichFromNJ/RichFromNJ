# Course evaluation: Swing Trading & ER Strategies and Systems

Spring 2022 course by Michael for OptionsPlayers.com. Based on sessions 1, 3, 4, 5, 6, 7 and 8. Session 2 has no content. Session 4 is a Green Goose session, not part of the swing course.

## Verdict

The course's one systematic trade, the earnings iron condor, lost money when replayed on real 2026 option prices. Do not trade it live. Run it signals-only for one earnings season and decide on the forward record.

- **The replay.** 24 condors across 9 names, January to October 2026, built with the course's own strike rule from Robinhood's daily closes of the actual contracts. Half won. The average loss was 2.6 times the average win.
- **The course's claim.** 13 of 20 condors won, profit factor 2.93. That rests on 20 paper trades with no trade list, so it cannot be told apart from a coin flip.
- **What to keep.** The $250 hard cap per trade, limit orders without chasing, the liquidity gate and the next-session exit.
- **What to leave out.** The directional layer, the Elliott and Fibonacci overlays, the Bollinger setups and the adjustment menu. Bullocks and the other double-down rules are dangerous.

None of the instructor's numbers rest on enough trades to trust. Most are paper trades, hindsight demos, or samples of three or four.

### 2026 replay of the earnings condor

Shorts one ATM straddle from the entry-day close, the narrowest listed wing from $1 to $5 that keeps the loss at or below $250. Entered at the close the session before the reaction day and closed at the reaction-day close. Fees are $0.05 per contract per side, plus $0.01 per leg per side for the bid-ask. Reproduce with `python3 research/earnings_condor_replay.py`.

| Sample | Trades | Won | Win rate, 95% range | Avg win | Avg loss | Profit factor | Total |
|---|---|---|---|---|---|---|---|
| All condors | 24 | 12 | 31-69% | +$46 | -$119 | 0.39 | -$875 |
| Credit at least 35% of risk | 22 | 11 | 31-69% | +$46 | -$122 | 0.38 | -$835 |
| Bid-ask cost tripled | 24 | 7 | 15-49% | +$32 | -$112 | 0.12 | -$1,675 |

- **Names.** JPM, C, MS, BX, DAL, WMT, IBM and MSFT, three reports each. PG could not be built because its put and call strikes are spaced differently.
- **How certain.** A bootstrap puts the average result at -$36 per condor, with a 95% range of -$76 to +$1. The chance that the true profit factor is 1 or better is about 3%.
- **Why it loses.** 10 of 24 reaction-day closes landed outside the short strikes. The 12 losses ran from $7 to $222, while no win topped $80. With $1-$2.50 wings, a condor that finishes just outside a short strike loses most of its risk.
- **The "3 of the last 4" history filter did not help.** Condors that passed it did worse than those that failed it, on samples of 9 and 6.
- **Caveat.** Daily closes are last-trade prices, not 3:40pm quotes. The sample is 24 trades on mostly large, liquid names, not the off-radar names the instructor preferred. Those were not fetched before the session hit its usage limit.

## What the course actually teaches

Every trade is built around the earnings calendar [s1]. There are three phases:

- **Before earnings:** buy premium so the trade rides the IV rise, then get out before the report [s1, s3, s6, s8].
- **Over earnings:** sell premium the session before the report and buy it back after the IV crush [s3, s5, s6].
- **After earnings:** use butterflies and calendars in the quiet period [s3, s5].

The course runs on a $10,000 paper account. Each trade risks $250, which is 2.5% [s1, s3, s5, s6]. A paid analytics tool is mandatory. It builds the candidate scans, the risk graphs and the backtests [s1, s3]. Charting is done in TradingView [s1].

The real driver of the account is the earnings condor. The instructor calls condors the "bread and butter" and the directional plays the "cream" [s7]. Twenty of the 26 course trades were condors [s7].

## Strategy catalog

All deltas are absolute values. "ER" means the earnings report. "Double" means a 100% gain on the option.

| # | Strategy | Phase | Trigger | Structure | Exit | Size | Src |
|---|---|---|---|---|---|---|---|
| 1 | Earnings iron condor | Over ER | Report timing from the calendar. Price it about 3:40 pm ET on the session before the report | Shorts one ATM straddle price from spot. Wings $1 on cheap names, $2.50-$5 on expensive ones. Same width on both sides. Skip if the credit is poor, about 25% ROI rejected and 45% accepted | Close the next session at whatever the price is. Thursday reporters may be held to Friday | Max loss $250 or less | s3, s5, s6, s7, s8 |
| 2 | Earnings iron butterfly | Over ER | Same as 1. Used on names that rarely move | Sell the ATM straddle. Wings at about the sum of the ATM premiums or 1 SD | Next day, close the losing side. Exit everything at about 90% of max | About $250 | s5, s6, s7, s8 |
| 3 | Pre-ER directional long option | Pre ER | 7-14 days before ER. Close above or below the 13 EMA, or an SSL 8 and TRIX 4 cross, with ADX 13 | 30-delta call or put, 25-35 allowed. First expiry after ER | Half off at a double. Stop on a close back through the 13 EMA. Everything out the day before ER | Up to $500 in, $250 loss cap | s1, s3, s6, s7 |
| 4 | Pre-ER ATM straddle | Pre ER | About 4 days before ER, only if IV is low | One ATM call plus one ATM put | Out before ER. $250 stop | Debit may exceed $250 | s3 |
| 5 | Pre-ER calendar | Pre ER | IV expected to rise. Entry if the open is flat or down, otherwise at EOD | Short weekly before ER, long expiry after ER, strike near target or 30 delta | Half at a double. Stop on a close below the 200 SMA. Time stop on ER day | $250 | s5, s8 |
| 6 | Credit spread expiring before ER | Pre ER | Bullish or flat outlook | Bull put spread near the money | Let it expire. Take half off at 50% of credit if that comes fast | Max loss $250 | s1 |
| 7 | SSL-cross swing | No ER | SSL 8 cross agreeing with TRIX 4. Low ADX 13 | 30 delta, about 45 DTE | Half at a double. Rest exits on a chart signal | Up to $500 | s1 |
| 8 | Triangle strangle | No ER | ADX 13 below 14 and a visible triangle | 30-delta call and put, a couple of cycles out | Target is the triangle height. $250 stop | About $1,000 debit | s3 |
| 9 | Gap-and-go credit spread | No ER | First close beyond the gap edge. No ER before expiry | Vertical with the short strike in the gap zone, 2-3 weeks out | Take profit at 50% of credit. Stop after 2 closes beyond the short strike | $500, 1 contract | s8 |
| 10 | Bollinger drill and fill | No ER | Intraday touch of the 3 SD band | Weekly options | Half off at the 2 SD band. Stop the rest at entry | $250 | s7, s8 |
| 11 | Bollinger squeeze | No ER | Bands squeeze with ADX 13 below 14. Contingent order on the break | About 45 DTE | Half at a double. A quarter off at the 3 SD band | $250 | s7, s8 |
| 12 | 48 EMA or 50 SMA at the band | No ER | Price at the band near the MA, then a green candle | Weekly options | Stop to entry. Exit on an indicator cross | $250 | s5, s6, s8 |
| 13 | Post-ER OTM call butterfly | Post ER | Close above the 200 SMA | AAPL 167.5/175/182.5, 3 weeks out | Half at a double. Rest at the target price. $250 stop | About $486 | s5 |
| 14 | Post-ER broken-wing butterfly | Post ER | Target from a Fib level and resistance | Wider wing on the risk side, about 21 DTE | $250 stop | About $236 | s5 |
| 15 | Flying Goose | No ER | 13 EMA above 48 EMA above 200 SMA for longs, reversed for shorts | 30 delta at about 43 DTE, or a $1 spread 3 weeks out | Target a double. Stop at -50%. Out at 30 DTE | About $750 | s4 |
| 16 | Bullocks | Overnight | Green Goose signal on AAPL | ATM weekly | If the gap is wrong, buy the same dollar amount again and sell everything at +10% | $500 plus $500 | s4 |
| 17 | Dow dividend puts and Puppies of the Dow | Investing | Rank the DJ-30 by yield. Puppies are the 5 cheapest of the top 10 | Cash-secured puts at about 35 DTE, or stock with married puts | Hold for years, or rebalance once a year | Large | s7 |
| 18 | ATR exit ladder | Any | Set at entry | Levels are on the underlying | Half off at 1x ATR. Stop at 1.5x ATR, then breakeven, then a 1.5x ATR trail | 2% of equity | s6, s8 |
| 19 | Repairs and adjustments | Any | Trade going against you | Add credit spreads, roll, close one side | Discretionary | Raises risk | s4, s5, s7, s8 |
| 20 | Elliott wave and Fibonacci overlay | Bias | 38.2/50/61.8 retracements | Not a structure | 100% or 161.8% extension | None | s1, s3 |

## Performance claims

The intervals are Wilson 95% intervals on the win rate. "None" means the instructor gave no sample, so no interval can be computed.

| Claim | Reported | n | 95% interval | Src |
|---|---|---|---|---|
| Course will succeed at least 75% of the time | 75% | None | Not estimable | s1 |
| Instructor's own win rate | About 60%, sometimes 40% | None | Not estimable | s1 |
| Condors partway through the season | 12 of 16, PF 1.98 | 16 | 50-90% | s5 |
| Condors in the course account | 13 of 20, PF 2.93 | 20 | 43-82% | s7 |
| Condors by season end | 22 closed, PF 3.2, worst loss $138 | 22 | Win count not given | s8 |
| One week of condors | 50% | 4 | 15-85% | s5 |
| Condor win rate benchmark | 65% | None | Not estimable | s8 |
| Course account return | +21% in about two months | 24 closed | Not a win rate | s7 |
| Season income at $250 per play | About $1,000 per six weeks | None | Not estimable | s8 |
| Candidate screen "at least 75%" | 3 of 4 typical | 4 | 30-95% | s5, s6, s8 |
| EA and SE condor history | 4 of 4 | 4 | 51-100% | s6, s7 |
| LOW condor history | 3 of 3 | 3 | 44-100% | s7 |
| TGT condor history | 2 of 4 | 4 | 15-85% | s7 |
| WMT iron butterfly backtest | 3 of 4, net about +$253 | 4 | 30-95% | s7 |
| Green Goose journal | 58% wins, 4% breakeven | 178 | 51-65% | s4 |
| Bullocks | 100% | About 3, paper | 44-100% | s4 |
| PFE pre-ER call backtest | $480 to $984 | 1 | Not estimable | s1 |
| SFIX pre-ER straddle backtest | +26% | 1 | Not estimable | s3 |
| AAPL pre-ER straddle backtest | -6.4% | 1 | Not estimable | s3 |
| AAPL pre-ER straddle typical | 10-15% ROI | None | Not estimable | s3 |
| Flying Goose EEM walk-through | +78.9% | 1, hindsight | Not estimable | s4 |
| Elliott wave reliability | Fails as much as it succeeds | None | Not estimable | s3 |

Notes on the table:

- The s5 count is garbled in the transcript. It can also be read as 6 of 10. The verified reading is 12 of 16.
- The condor record includes a LOW trade the instructor never filled. He copied a student's result [s8].
- The record also includes a SPY condor that was not an earnings trade [s7].
- Every condor result is from a paper account [s3].

### Break-even win rates

These are the win rates the condor needs if every loss is a full max loss.

| Trade | Credit | Risk | Break-even win rate | Src |
|---|---|---|---|---|
| MS condor | 0.31 | 0.69 | 69% | s3 |
| DIS condor | 0.76 | 1.74 | 70% | s6 |
| NVDA condor | $202 | $298 | 60% | s8 |

Early exits lower these numbers in practice. The Delta trade lost $63 against more than $200 at risk [s3]. The reported 60-75% sits close to the full-loss break-even.

## What is sound

- **The vega reasoning is correct.** Before earnings he buys straight options, not spreads [s1]. When he fears a crush he buys ITM [s4]. He avoids long butterflies into rising IV [s7]. He sells condors before the report and buys them back after [s6].
- **Exiting after the crush is right.** Once the crush has happened, the thesis is done. Holding on keeps short-gamma risk that is roughly fairly priced [s3, s5, s6]. This cuts variance. It does not add edge.
- **The condor is built from live quotes.** The ATM straddle stands in for the expected move [s3]. No IV history is needed.
- **The fill discipline is good.** He uses limit orders at mid, does not chase, and skips the trade if it does not fill [s3, s5, s6].
- **The liquidity gate is right in spirit.** It checks bid-ask width and volume [s5, s6], even though the thresholds move around.
- **The $250 cap is structural.** A condor sized "all-in" cannot lose more than the cap [s3, s8].
- **He sets a validation bar.** He wants 100 forward-tested trades before going live [s6].
- **Some arithmetic is right.** Six losses at 2.5% is about 15%. A 10% drawdown needs about 11% to recover [s3].

## What is not sound

- **The condor edge is unproven.** Twenty paper trades cannot tell 65% apart from 50-55% [s7]. A coin flip passes the 3-of-4 screen 31% of the time.
- **Fills were never tested against reality.** Credits were priced at the tool's mid [s3]. Your own research found real credits 15-45% below model.
- **The pre-ER long calls are untested.** The PFE drift rests on about four reports [s1]. "Even if this goes flat. We're gonna win" is false for an OTM long call unless IV outruns theta [s3]. Your sweep found that bought calls on dips lose.
- **The calendar targets are too high.** Most of the pre-ER IV rise is a shrinking-DTE effect. His own TGT check "can't double" [s6]. "Double" targets do not belong in a calendar exit [s5, s8].
- **The indicator settings are fitted by eye.** SSL 7, TRIX 4-5 and Vortex 8 were tuned "all visual" on one FX chart [s6]. He says it is not his real system [s6].
- **Martingale rules.** Bullocks doubles after a wrong gap [s4]. Green Goose sizing goes up after a bad month [s4]. Repairs add risk to losing trades [s4].
- **He broke his own cap.** The DLTR repair took risk from $250 to $1,230 at 3:30 am. He called it a mistake [s8]. Before that, he said condor profits "let me do that" [s8].
- **The streak math is loose.** His streak table mixes horizons. His worked week nets $1,000, not the $1,100 he states [s1].
- **The backtests are hindsight.** He forced fills: "force this so it looks like 34 cents" [s1]. He picked dates after seeing the outcome [s4]. He did the WMT arithmetic hungover [s7].
- **There is a conflict of interest.** He keeps his tool tier only while enough students subscribe [s3]. He told students to cancel the course without the tool [s1]. Mid-course he moved to a paid service [s7, s8].

## Ranking by evidence of edge and automatability

| Rank | Strategy | Evidence of edge | Automatability with your connectors | Src |
|---|---|---|---|---|
| 1 | Earnings iron condor | Negative in the 2026 replay: PF 0.39 on 24 trades | High. Calendar timing, chain, quotes and 4-leg limit orders are all available | s3, s5, s6, s8 |
| 2 | Earnings iron butterfly with losing-side close | Weak. n=4 backtest, managed in hindsight | High | s7 |
| 3 | $250 cap and one play per day | Not an edge. Pure risk control | High | s3, s5, s8 |
| 4 | Gap-and-go credit spread | None. Picked charts only | High from daily OHLCV | s8 |
| 5 | ATR exit ladder | None for options | High | s6, s8 |
| 6 | Candidate scan without IV ranking | Not an edge | Medium. The IV ranking cannot be reproduced | s3, s6, s7, s8 |
| 7 | Pre-ER ATM straddle | Plausible if IV starts low | Low until you have an IV history | s3 |
| 8 | Pre-ER calendar | Neutral | Medium | s5, s8 |
| 9 | Pre-ER directional 30-delta option | Untested, probably negative | Medium | s1, s3, s6, s7 |
| 10 | Bollinger setups | None. Hindsight only | Medium. Contingent orders have to be emulated | s7, s8 |
| 11 | Flying Goose | None. Shorts conflict with your research | Medium | s4 |
| 12 | Elliott, Fibonacci, trendlines | Instructor says about 50% | Low | s1, s3 |
| 13 | Repairs, Bullocks, up-sizing | Negative. Martingale | High, which makes them dangerous | s4, s8 |

## What this means for your automated plan

### Automate

- **Hard risk engine.** Reject any order whose worst-case loss for the whole position exceeds min of $250 and 2.5% of equity. This directly blocks a DLTR-style repair [s8].
- **No adds to losers.** Refuse any order on a position marked at a loss unless it closes the position. This blocks martingale recovery [s4, s8].
- **Entry session from the calendar only.** For a "pm" report, enter that day. For "am", enter the session before. If the report is unverified or the sources disagree, NO TRADE. The instructor misspoke dates on stream [s8].
- **Liquidity gate.** Require spread to mid of 10% or less on every leg, OI of at least 100 on the shorts, and no zero bids. The course's own thresholds drift [s5, s6].
- **Limit orders only, no chasing.** One reprice, then cancel [s3, s5].
- **Next-session close of any open earnings condor.** Buy it back after the crush, at a loss if necessary [s3, s5].
- **Daily ATM-IV snapshot job.** It only collects data and places no trades. It is the prerequisite for every IV-ramp strategy [s3, s6, s7].
- **Trade journal with strategy and rule-break tags.** This mirrors his TraderSync "mistake" tag [s8].

### Paper-trade first

- **Earnings iron condor, signals-only.** The code and routines are built and tested. Run only the scan for one season and score its picks. Go live only if the forward record clears the gate in AUTOMATION-PLAN.md. The 2026 replay says to expect a loss [replay].
- **The condor needs a sell-to-open carve-out.** Write it like the one for the Connors RSI put spread.
- **WMT-style iron butterfly with next-day losing-side close.** The rule is mechanical. The 3-of-4 evidence is hindsight-managed [s7].
- **Gap-and-go credit spread.** It is fully codable. He says he "hasn't done this in a while" [s8].
- **Pre-ER ATM straddle.** Wait until the IV snapshot store holds two to three quarters of history. Enter only if current IV is below its pre-ER norm [s3].
- **ATR exit ladder.** Use it as an exit overlay on the underlying, not as a signal [s6].

### Do not automate

- **Pre-ER 30-delta long calls and puts.** They are untested, and your dip-buying result points against them [s1, s3].
- **Bullocks.** It is a martingale with a 3-trade paper record [s4].
- **Raising size after a losing month.** It adds risk in drawdowns [s4].
- **Repairs, rolls, closing only the shorts, converting to a butterfly.** They add risk and depend on judgment [s4, s5, s8].
- **The SSL/TRIX/Vortex formula as published.** The parameters were fitted by eye [s6].
- **Flying Goose shorts.** No bearish signal survived in your research [s4].
- **Elliott wave, Fibonacci targets, trendlines, Bollinger fades and squeezes.** These are chart reads tested on hindsight [s1, s3, s7].
- **The 20% after-hours EEM exit.** It depends on EEM options trading until 4:15 pm, which has not been tested on Robinhood [s4].
- **Calendars with a "double" target.** If you ever add a calendar, use 25-50% of the debit [s5, s6].
- **Any Green Goose change based on the course's 58%.** Your measured 50-52% is the baseline [s4].

## Open questions the transcripts cannot answer

1. What is the true per-trade condor win count and P&L, net of commissions and real fills? No trade list was shown [s7, s8].
2. Which short-strike multiplier did he actually use? The base is one straddle, but MS landed at about 1.7x [s3].
3. What is the minimum credit-to-width ratio? Only 25% rejected and 45% accepted are known [s3].
4. Should Thursday reporters be held to Friday? He describes both choices [s6, s7].
5. What were the RSI, ADX and TRIX settings and the strike rule for Green Goose? He withholds them "from a license perspective" [s4].
6. How large is the real pre-ER IV ramp per name? The paid tool's ranking was never shown as data [s3, s6].
7. Does Robinhood fill EEM options between 4:00 and 4:15 pm [s4]?
8. How did the open DLTR, TGT and AAPL positions end [s7, s8]?
9. What is his real system? He says the demo is not it [s6].

## Appendix: verification

Each finding was checked against the transcripts by an independent verifier. "Corrected" means the claim was softened to what the transcript supports. "Dropped" findings are not used above.


| ID | Status | Dimension |
|---|---|---|
| F1 | corrected | Options-theory and strategy soundness |
| F2 | corrected | Options-theory and strategy soundness |
| F3 | corrected | Options-theory and strategy soundness |
| F4 | corrected | Options-theory and strategy soundness |
| F5 | corrected | Options-theory and strategy soundness |
| F6 | corrected | Options-theory and strategy soundness |
| MM-01 | corrected | Money management, risk and psychology |
| MM-02 | corrected | Money management, risk and psychology |
| MM-03 | corrected | Money management, risk and psychology |
| MM-04 | dropped | Money management, risk and psychology |
| MM-05 | corrected | Money management, risk and psychology |
| MM-06 | corrected | Money management, risk and psychology |
| EV-01 | corrected | Evidence quality and credibility |
| EV-02 | corrected | Evidence quality and credibility |
| EV-03 | corrected | Evidence quality and credibility |
| EV-04 | corrected | Evidence quality and credibility |
| EV-05 | dropped | Evidence quality and credibility |
| EV-06 | corrected | Evidence quality and credibility |
| A1 | corrected | Automatability with the repository's connectors |
| A2 | corrected | Automatability with the repository's connectors |
| A3 | corrected | Automatability with the repository's connectors |
| A4 | confirmed | Automatability with the repository's connectors |
| A5 | corrected | Automatability with the repository's connectors |
| A6 | corrected | Automatability with the repository's connectors |
| F1 | corrected | Consistency with the owner's research and routines |
| F2 | corrected | Consistency with the owner's research and routines |
| F3 | confirmed | Consistency with the owner's research and routines |
| F4 | confirmed | Consistency with the owner's research and routines |
| F5 | corrected | Consistency with the owner's research and routines |
| F6 | corrected | Consistency with the owner's research and routines |
