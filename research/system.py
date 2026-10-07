"""The options system: bull put credit spreads on SPY, QQQ or IWM after an oversold TradingView signal.

Rules (chosen on 2007-2018 data only, by the rule fixed before looking at later years:
"among structures that won at least 85% in 2007-2018 with 60+ trades, take the highest profit
factor"):
  1. Signal, at the 3:45pm check: the ETF is above its 200-day SMA and its Connors RSI(3,2,100)
     is below 10.                                   (variant B adds: or Bollinger %B(20,2) < 0)
  2. If several ETFs signal, take the lowest Connors RSI. Only one spread open at a time.
  3. Expiration: the first Friday at least 21 calendar days away.
  4. Sell the put whose delta is closest to -0.30; buy the put $W lower, with W the widest of
     $5/$4/$3/$2/$1 that keeps the maximum loss (W - credit) x 100 at or below $250.
  5. Hold. Close it at the 3:45pm check on the last trading day before expiration.

    python3 research/system.py
"""
import datetime as dt
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt  # noqa: E402
import spreads as sp  # noqa: E402

DELTA, DTE = 0.30, 21


def signals(f, variant="A"):
    up = f.c > f.sma200
    s = up & (f.crsi < 10)
    if variant == "B":
        s = s | (up & (f.bb_pct < 0))
    return s.fillna(False)


def simulate(markets, period, variant="A", take_profit=None):
    """One spread open at a time across all three ETFs."""
    sig = {s: signals(m.f, variant) for s, m in markets.items()}
    dates = sorted(set().union(*(set(m.dates) for m in markets.values())))
    dates = [d for d in dates if period[0] <= d <= period[1]]
    trades, busy_until = [], None
    for d in dates:
        if busy_until and d <= busy_until:
            continue
        cands = [(m.f.crsi.loc[d], s) for s, m in markets.items() if d in m.pos and bool(sig[s].loc[d])]
        if not cands:
            continue
        sym = min(cands)[1]
        m = markets[sym]
        t = sp.open_spread(m, d, "put_credit", DELTA, DTE)
        if t is None:
            continue
        r = sp.run_trade(m, t, "hold", take_profit, None)
        if r is None:
            break  # still open at the end of the data
        r["sym"] = sym
        trades.append(r)
        busy_until = r["exit_date"]
    return pd.DataFrame(trades)


_MARKETS = None


def markets():
    global _MARKETS
    if _MARKETS is None:
        vx = bt.vix()
        _MARKETS = {s: sp.Market(s, vx) for s in sp.UNIVERSE}
    return _MARKETS


def trades_2026(variant="A"):
    return simulate(markets(), bt.YTD, variant)


if __name__ == "__main__":
    M = markets()
    for variant in ("A", "B"):
        for label, period in sp.PERIODS.items():
            t = simulate(M, period, variant)
            print(f"variant {variant} {label:8s} {sp.fmt(sp.summarize(t))}  trades/yr="
                  f"{len(t) / max((period[1] - period[0]).days / 365.25, 0.01):.1f}")
        t = simulate(M, (dt.date(2007, 1, 1), bt.YTD[1]), variant)
        t["yr"] = [d.year for d in t.entry_date]
        print("   per year: " + " ".join(f"{y}:{100 * (g.pnl > 0).mean():.0f}%/{len(g)}/${g.pnl.sum():+.0f}"
                                         for y, g in t.groupby("yr")))
    print("\n2026 trades, variant B:")
    t = trades_2026("B")
    print(t[["sym", "entry_date", "exit_date", "exp", "legs", "width", "entry", "max_loss", "pnl"]].round(2).to_string(index=False))
