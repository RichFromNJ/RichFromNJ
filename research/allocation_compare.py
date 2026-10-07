#!/usr/bin/env python3
"""Compare three ways to fund the overnight EEM and SPY entries in 2026.

  both  - EEM with its own budget ($130 OTM / $245 ITM) and SPY with $195
  eem   - EEM only, with SPY's $195 added to both EEM budgets
  spy   - SPY only, with EEM's $245 added ($440)

Signals come from overnight_signal.decide() on a 3:30pm snapshot, as in
spy_confirm_backtest.py. There are no historical option quotes here, so each
trade is priced with Black-Scholes:
  - IV = ratio x VIX9D of the day: 0.89 for SPY (spreads.py calibration) and
    1.70 for EEM (Robinhood quotes on Oct 7, 2026: EEM 2-day IV ~0.20 with
    VIX9D ~12; SPY 2-day IV ~0.11).
  - Expiration per the prompt: Mon/Tue entries use Wednesday, Wed/Thu use Friday.
  - Calendar time to the 4pm expiry; exit at 9:45am the next trading day with
    that day's VIX9D.
  - Buy at the ask, sell at the bid. Half-spreads from the same Oct 7 quotes:
    SPY $0.01, EEM $0.05. Fees $0.05 per contract per side.
  - Strike: the nearest ITM contract if its budget buys one at the ask,
    otherwise the nearest OTM if its budget does, otherwise no trade.
These are model prices, so treat the dollar results as rough.

Usage: [FILL=0.5] allocation_compare.py   (FILL=0.5: pay half the half-spread each side)
"""

import datetime as dt
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import overnight_signal as osig  # noqa: E402
import spy_confirm_backtest as sb  # noqa: E402

sb.FILES["EEM"] = "AMEX_EEM"
R = 0.04


def ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs(S, K, T, v, q, call):
    """Black-Scholes price, as in spreads.bs() without the scipy dependency."""
    if T <= 0:
        return max(S - K, 0.0) if call else max(K - S, 0.0)
    d1 = (math.log(S / K) + (R - q + v * v / 2) * T) / (v * math.sqrt(T))
    d2 = d1 - v * math.sqrt(T)
    if call:
        return S * math.exp(-q * T) * ncdf(d1) - K * math.exp(-R * T) * ncdf(d2)
    return K * math.exp(-R * T) * ncdf(-d2) - S * math.exp(-q * T) * ncdf(-d1)
IV_RATIO = {"SPY": 0.89, "EEM": 1.70}
DIV = {"SPY": 0.013, "EEM": 0.025}
STEP = {"SPY": 1.0, "EEM": 0.5}
HALF = {"SPY": 0.01, "EEM": 0.05}
FEE = 0.05  # dollars per contract per side
# Share of the half-spread paid on each side: 1 = buy at the ask, sell at the bid.
FILL = float(os.environ.get("FILL", "1"))

PLANS = {
    "both": {"EEM": {"OTM": 130, "ITM": 245}, "SPY": {"OTM": 195, "ITM": 195}},
    "eem":  {"EEM": {"OTM": 325, "ITM": 440}},
    "spy":  {"SPY": {"OTM": 440, "ITM": 440}},
}


def vix9d():
    out = {}
    with open(os.path.join(sb.DATA, "CBOE_VIX9D_1D.csv")) as f:
        next(f)
        for line in f:
            p = line.strip().split(",")
            out[dt.date.fromisoformat(p[1][:10])] = float(p[5]) / 100
    return out


def expiry(day):
    target = 2 if day.weekday() <= 1 else 4   # Wednesday or Friday
    return day + dt.timedelta(days=target - day.weekday())


def years(start, exp):
    end = dt.datetime.combine(exp, dt.time(16))
    return max((end - start).total_seconds(), 0) / (365 * 86400)


def trade(sym, v, day, nxt, budgets, vol, data):
    S, call = v["price"], v["signal"] == "CALLS"
    step = STEP[sym]
    above, below = math.ceil(S / step) * step, math.floor(S / step) * step
    if above == S:
        above += step
    strikes = {"OTM": above, "ITM": below} if call else {"OTM": below, "ITM": above}
    exp = expiry(day)
    t0 = years(dt.datetime.combine(day, dt.time(15, 30)), exp)
    t1 = years(dt.datetime.combine(nxt, dt.time(9, 45)), exp)
    iv0, iv1 = IV_RATIO[sym] * vol[day], IV_RATIO[sym] * vol.get(nxt, vol[day])
    S1 = next(b[4] for b in data[sym][1][nxt] if b[0] == sb.EXIT_BAR)
    for kind in ("ITM", "OTM"):
        K = strikes[kind]
        ask = round(bs(S, K, t0, iv0, DIV[sym], call) + FILL * HALF[sym], 2)
        qty = int(budgets[kind] // (ask * 100))
        if qty:
            bid = max(round(bs(S1, K, t1, iv1, DIV[sym], call) - FILL * HALF[sym], 2), 0.0)
            pnl = qty * ((bid - ask) * 100 - 2 * FEE)
            return dict(sym=sym, kind=kind, qty=qty, ask=ask, bid=bid, pnl=pnl,
                        cost=qty * ask * 100)
    return None


def main():
    vol = vix9d()
    data = {s: sb.load(s) for s in ("SPY", "EEM")}
    days = sorted(d for d in data["SPY"][1] if d >= sb.START and d in data["EEM"][1])
    signals = {}
    for i, day in enumerate(days[:-1]):
        if day.weekday() > 3 or osig.holiday_tomorrow(day):
            continue
        signals[day] = (days[i + 1], {s: sb.signal(s, day, data)[0] for s in ("SPY", "EEM")})

    print(f"{len(signals)} entry days, {days[0]} to {days[-2]}")
    for name, plan in PLANS.items():
        trades, unaffordable, equity, peak, dd = [], {s: 0 for s in plan}, 0.0, 0.0, 0.0
        for day, (nxt, sig) in signals.items():
            for sym, budgets in plan.items():
                v = sig[sym]
                if not v or v["signal"] == "NO TRADE":
                    continue
                t = trade(sym, v, day, nxt, budgets, vol, data)
                if t is None:
                    unaffordable[sym] += 1
                    continue
                trades.append(t)
                equity += t["pnl"]
            peak = max(peak, equity)
            dd = min(dd, equity - peak)
        n = len(trades)
        wins = sum(t["pnl"] > 0 for t in trades)
        print(f"\n== {name} ==  trades {n}  wins {wins} ({100 * wins / n:.0f}%)  "
              f"total P/L ${equity:+,.0f}  worst drawdown ${dd:,.0f}")
        for sym in plan:
            sub = [t for t in trades if t["sym"] == sym]
            if not sub:
                print(f"  {sym}: no affordable trades ({unaffordable[sym]} signals too expensive)")
                continue
            w = sum(t["pnl"] > 0 for t in sub)
            kinds = {k: sum(t["kind"] == k for t in sub) for k in ("ITM", "OTM")}
            print(f"  {sym}: {len(sub)} trades ({kinds['ITM']} ITM, {kinds['OTM']} OTM), "
                  f"{unaffordable[sym]} signals unaffordable, wins {w} ({100 * w / len(sub):.0f}%), "
                  f"P/L ${sum(t['pnl'] for t in sub):+,.0f}, avg cost ${sum(t['cost'] for t in sub) / len(sub):,.0f}, "
                  f"avg contracts {sum(t['qty'] for t in sub) / len(sub):.1f}")


if __name__ == "__main__":
    main()
