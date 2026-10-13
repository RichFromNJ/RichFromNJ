"""When the Green Goose rules give EEM and SPY opposite signals, which one is right?

For every Mon-Thu entry day (skipping the day before a holiday) both symbols get a
signal from overnight_signal.decide. SPY skips the TRIX rule, as its live routine does.
A signal is "right" when the next session moves its way.

  2026      decision at the 3:45pm price (15-minute bars), exit at the next open and at 9:45am
  2007-2025 decision at the daily close, exit at the next open (daily bars only)

    python3 research/disagreement.py
"""
import datetime as dt
import math
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import backtest as bt  # noqa: E402
import overnight_signal as sig  # noqa: E402


def decide(sym, series):
    """overnight_signal.decide, with TRIX switched off for SPY."""
    saved = sig.TRIX_LIMIT
    if sym == "SPY":
        sig.TRIX_LIMIT = math.inf
    try:
        return sig.decide(series)
    finally:
        sig.TRIX_LIMIT = saved


def signals_2026(sym):
    d, sp = bt.daily(sym), bt.session_points(sym)
    days = [x for x in sp.index if x >= bt.YTD[0]]
    out = {}
    for i, day in enumerate(days[:-1]):
        if day.weekday() > 3 or sig.holiday_tomorrow(day):
            continue
        hist = [sig.Bar(k, r.o, r.h, r.l, r.c) for k, r in d[d.index < day].tail(120).iterrows()]
        p, q = sp.loc[day], sp.loc[days[i + 1]]
        today = sig.todays_bar(day, p.o, max(p.h1545, p.o, p.p1545), min(p.l1545, p.o, p.p1545), p.p1545)
        try:
            v = decide(sym, sig.build_series(hist, today))
        except sig.DataError:
            continue
        if v["signal"] in ("CALLS", "PUTS"):
            side = 1 if v["signal"] == "CALLS" else -1
            out[day] = dict(signal=v["signal"], open=side * (q.o / p.p1545 - 1), m945=side * (q.p0945 / p.p1545 - 1))
    return out


def signals_daily(sym, start, end):
    d = bt.daily(sym)
    bars = [sig.Bar(k, r.o, r.h, r.l, r.c) for k, r in d.iterrows()]
    out = {}
    for i in range(130, len(bars) - 1):
        day = bars[i].date
        if not (start <= day <= end) or day.weekday() > 3:
            continue
        try:
            if sig.holiday_tomorrow(day):
                continue
        except sig.DataError:
            pass
        series = bars[i - 80:i + 1]
        try:
            v = decide(sym, series)
        except Exception:
            continue
        if v["signal"] in ("CALLS", "PUTS"):
            side = 1 if v["signal"] == "CALLS" else -1
            out[day] = dict(signal=v["signal"], open=side * (bars[i + 1].o / bars[i].c - 1))
    return out



def table(e, s, exit_key, label):
    days = sorted(set(e) & set(s))
    rows = []
    for day in days:
        a, b = e[day], s[day]
        rows.append(dict(date=day, eem=a["signal"], spy=b["signal"], agree=a["signal"] == b["signal"],
                         eem_right=a[exit_key] > 0, spy_right=b[exit_key] > 0,
                         eem_ret=a[exit_key], spy_ret=b[exit_key]))
    df = pd.DataFrame(rows)
    print(f"\n== {label} ==  days with a signal on both: {len(df)}")
    for name, g in (("agree", df[df.agree]), ("disagree", df[~df.agree])):
        n = len(g)
        if not n:
            print(f"  {name}: none")
            continue
        ke, ks = int(g.eem_right.sum()), int(g.spy_right.sum())
        le, he = bt.wilson(ke, n)
        ls, hs = bt.wilson(ks, n)
        print(f"  {name:8s} n={n:4d}  EEM right {100 * ke / n:5.1f}% ({100 * le:.0f}-{100 * he:.0f})  "
              f"SPY right {100 * ks / n:5.1f}% ({100 * ls:.0f}-{100 * hs:.0f})  "
              f"avg move EEM {100 * g.eem_ret.mean():+.3f}%  SPY {100 * g.spy_ret.mean():+.3f}%")
        if name == "disagree":
            both = int((g.eem_right & g.spy_right).sum())
            neither = int((~g.eem_right & ~g.spy_right).sum())
            only_e = int((g.eem_right & ~g.spy_right).sum())
            only_s = int((~g.eem_right & g.spy_right).sum())
            print(f"           only EEM right {only_e}, only SPY right {only_s}, both right {both}, neither {neither}")
            for combo, h in g.groupby(["eem", "spy"]):
                k1, k2 = int(h.eem_right.sum()), int(h.spy_right.sum())
                print(f"           EEM {combo[0]:5s} / SPY {combo[1]:5s}: n={len(h):4d}  EEM right {100 * k1 / len(h):5.1f}%  SPY right {100 * k2 / len(h):5.1f}%")
    return df


if __name__ == "__main__":
    e26, s26 = signals_2026("EEM"), signals_2026("SPY")
    table(e26, s26, "open", "2026, 3:45pm signal, exit at the next open")
    table(e26, s26, "m945", "2026, 3:45pm signal, exit at 9:45am")
    eh = signals_daily("EEM", dt.date(2007, 1, 1), dt.date(2025, 12, 31))
    sh = signals_daily("SPY", dt.date(2007, 1, 1), dt.date(2025, 12, 31))
    table(eh, sh, "open", "2007-2025, close signal, exit at the next open")
