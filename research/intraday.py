"""Intraday research behind research/README.md (sections 5 and 6).

    python3 research/intraday.py            # every intraday table
    python3 research/intraday.py hourly     # just the hourly-check pullback Routine

Sections:
  daytrades - same-day strategies: gap fills and open-to-close on daily bars (2007-2026), and
              hourly-checkpoint rules on TradingView hourly bars (Dec 2023 - Oct 2026)
  hourly    - the RSI(2) pullback checked every hour from 10:30 to 15:30 (swing holds allowed)

Hourly bars start at 9:30, 10:30, ... 15:30 ET, so their closes give checkpoints at 10:30, 11:30,
12:30, 13:30, 14:30, 15:30 and 16:00.
"""
import datetime as dt
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt  # noqa: E402

HOURLY_DEV = (dt.date(2023, 12, 1), dt.date(2025, 12, 31))
CHECKS = ["10:30", "11:30", "12:30", "13:30", "14:30", "15:30", "16:00"]


def hourly(sym):
    df = pd.read_csv(os.path.join(bt.DATA, f"{bt.FILES[sym]}_1h.csv"))
    df["date"] = pd.to_datetime(df.et.str[:10]).dt.date
    df["hm"] = df.et.str[11:]
    return df


# ---------------------------------------------------------------- same-day trades on daily bars

def daily_prep(sym):
    d = bt.daily(sym).copy()
    au, ad = bt.wilder_state(d.c.values)
    d["rsi2"] = bt.rsi_from(au, ad)
    d["pc"], d["prsi2"] = d.c.shift(1), d.rsi2.shift(1)
    d["psma200"] = d.c.rolling(200).mean().shift(1)
    d["gap"] = (d.o / d.pc - 1) * 100
    return d


def gap_fill(d, lo, hi, side, trend=None):
    """Gap of lo..hi % at the open. side=+1 buys a gap down, side=-1 shorts a gap up. Target is the
    prior close (a resting limit); otherwise exit at the close."""
    m = (d.gap >= lo) & (d.gap <= hi)
    if trend == "up":
        m &= d.pc > d.psma200
    t = d[m]
    if side == 1:
        hit = t.h >= t.pc
        ret = np.where(hit, (t.pc / t.o - 1) * 100, (t.c / t.o - 1) * 100)
    else:
        hit = t.l <= t.pc
        ret = np.where(hit, (t.o / t.pc - 1) * 100, (t.o / t.c - 1) * 100)
    return pd.DataFrame(dict(entry_date=t.index, ret=ret, days=0))


def open_to_close(d, mask):
    t = d[mask]
    return pd.DataFrame(dict(entry_date=t.index, ret=(t.c / t.o - 1).values * 100, days=0))


DAILY_DAYTRADES = {
    "Gap down 0.15-0.6%, buy open, target prior close": lambda d: gap_fill(d, -0.6, -0.15, 1),
    "  same, uptrend only": lambda d: gap_fill(d, -0.6, -0.15, 1, "up"),
    "Gap up 0.15-0.6%, short open, target prior close": lambda d: gap_fill(d, 0.15, 0.6, -1),
    "Open to close, every day": lambda d: open_to_close(d, d.pc.notna()),
    "Open to close after RSI(2)<10, uptrend": lambda d: open_to_close(d, (d.prsi2 < 10) & (d.pc > d.psma200)),
}


# ---------------------------------------------------------------- same-day trades on hourly bars

def hourly_days(sym):
    h = hourly(sym)
    d = bt.daily(sym).copy()
    d["sma200"] = d.c.rolling(200).mean()
    prev = d.shift(1)
    au, ad = bt.wilder_state(h.c.values)
    h["rsi2h"] = bt.rsi_from(au, ad)
    h["pv"] = (h.h + h.l + h.c) / 3 * h.v
    h["vwap"] = h.groupby("date").pv.cumsum() / h.groupby("date").v.cumsum()
    days = {}
    for day, g in h.groupby("date"):
        if len(g) != 7 or day not in d.index:
            continue
        p = prev.loc[day]
        days[day] = dict(g=g.reset_index(drop=True), open=g.o.iloc[0], pc=p.c, up=p.c > p.sma200)
    return days


def run_hourly(days, entry, side=1, target=None, exit_=None, first=0, last=4, time_exit=5):
    """One trade per day: enter at the first checkpoint first..last where entry() is true; exit at the
    target (a resting limit, filled when a later bar trades through it), when exit_() is true at a
    checkpoint, or at checkpoint time_exit (5 = 15:30, 6 = 16:00)."""
    out = []
    for day, D in days.items():
        g = D["g"]
        for i in range(first, last + 1):
            if not entry(D, g, i):
                continue
            e, tgt, res = g.c[i], (target(D, g, i) if target else None), None
            for j in range(i + 1, time_exit + 1):
                if tgt is not None and ((side == 1 and g.h[j] >= tgt) or (side == -1 and g.l[j] <= tgt)):
                    res = tgt
                    break
                if exit_ and j < time_exit and exit_(D, g, j):
                    res = g.c[j]
                    break
            res = g.c[time_exit] if res is None else res
            out.append(dict(entry_date=day, ret=side * (res / e - 1) * 100, days=0))
            break
    return pd.DataFrame(out)


HOURLY_DAYTRADES = {
    "Hourly RSI(2)<10, uptrend, exit RSI(2)>70 or 15:30":
        dict(entry=lambda D, g, i: D["up"] and g.rsi2h[i] < 10, exit_=lambda D, g, j: g.rsi2h[j] > 70),
    "0.5% below VWAP, uptrend, target VWAP or 15:30":
        dict(entry=lambda D, g, i: D["up"] and g.c[i] < g.vwap[i] * 0.995, target=lambda D, g, i: g.vwap[i]),
    "Down 0.75% from open, uptrend, target the open":
        dict(entry=lambda D, g, i: D["up"] and g.c[i] < D["open"] * 0.9925, target=lambda D, g, i: D["open"]),
    "Down 1% from prior close, uptrend, hold to 15:30":
        dict(entry=lambda D, g, i: D["up"] and g.c[i] < D["pc"] * 0.99),
    "Gap down unfilled at 10:30, target prior close":
        dict(entry=lambda D, g, i: D["up"] and D["open"] < D["pc"] * 0.9985 and g.c[0] < D["pc"],
             target=lambda D, g, i: D["pc"], last=0),
    "Hourly RSI(2)>90, downtrend, short, exit RSI(2)<30":
        dict(entry=lambda D, g, i: not D["up"] and g.rsi2h[i] > 90, exit_=lambda D, g, j: g.rsi2h[j] < 30, side=-1),
    "Up 0.5% at 15:30, ride the last half hour":
        dict(entry=lambda D, g, i: g.c[5] > D["pc"] * 1.005, first=5, last=5, time_exit=6),
}


# ---------------------------------------------------------------- the pullback, checked every hour

def checkpoints(sym):
    """Daily RSI(2), SMA200 and SMA5 at each hourly checkpoint, with the checkpoint price as today's close."""
    h, d = hourly(sym), bt.daily(sym)
    c = d.c.values
    pos = {k: i for i, k in enumerate(d.index)}
    au, ad = bt.wilder_state(c)
    rows = []
    for day, g in h.groupby("date"):
        if len(g) != 7 or day not in pos or pos[day] < 201:
            continue
        i = pos[day]
        for k, px in enumerate(g.c):
            rows.append(dict(date=day, k=k, t=CHECKS[k], price=px,
                             rsi2=bt.rsi_next(au[i - 1], ad[i - 1], c[i - 1], px),
                             sma200=(c[i - 199:i].sum() + px) / 200, sma5=(c[i - 4:i].sum() + px) / 5))
    return pd.DataFrame(rows)


def simulate_hourly(panels, period, threshold=5.0, max_hold=bt.MAX_HOLD, ks=range(0, 6)):
    """Checks at 10:30..15:30. Sell when price > SMA5, or at 15:30 once held max_hold sessions.
    If flat, buy the lowest-RSI(2) ETF above its SMA200 with RSI(2) < threshold. One buy per day,
    and no buy at the same check as a sale."""
    look = {s: p[p.k.isin(list(ks))].set_index(["date", "k"]) for s, p in panels.items()}
    keys = sorted(x for x in set().union(*(set(v.index) for v in look.values())) if period[0] <= x[0] <= period[1])
    pos, trades, last_day, bought_on = None, [], None, None
    for day, k in keys:
        if pos and day != last_day and day != pos["date"]:
            pos["held"] += 1
        last_day = day
        if pos and (day, k) in look[pos["sym"]].index:
            r = look[pos["sym"]].loc[(day, k)]
            if r.price > r.sma5 or (pos["held"] >= max_hold and k == max(ks)):
                trades.append(dict(sym=pos["sym"], entry_date=pos["date"], entry_t=pos["t"], exit_date=day,
                                   exit_t=r.t, entry=pos["entry"], exit=r.price,
                                   ret=(r.price / pos["entry"] - 1) * 100, days=pos["held"]))
                pos = None
                continue
        if pos is None and bought_on != day:
            cands = [(look[s].loc[(day, k)].rsi2, s) for s in panels if (day, k) in look[s].index
                     and look[s].loc[(day, k)].price > look[s].loc[(day, k)].sma200
                     and look[s].loc[(day, k)].rsi2 < threshold]
            if cands:
                s = min(cands)[1]
                r = look[s].loc[(day, k)]
                pos, bought_on = dict(sym=s, date=day, t=r.t, entry=r.price, held=0), day
    return pd.DataFrame(trades), pos


def hourly_results(threshold=5.0):
    panels = {s: checkpoints(s) for s in bt.ETFS}
    dev, _ = simulate_hourly(panels, HOURLY_DEV, threshold)
    ytd, open_pos = simulate_hourly(panels, bt.YTD, threshold)
    return dev, ytd, open_pos


# ---------------------------------------------------------------- report sections

def section_daytrades():
    print("\n== Same-day trades on daily bars (enter at the open) ==")
    P = {s: daily_prep(s) for s in bt.ETFS}
    for name, fn in DAILY_DAYTRADES.items():
        t = pd.concat([fn(P[s]) for s in bt.ETFS], ignore_index=True)
        print(f"{name:50s} 2007-25 {bt.fmt(bt.stats(bt.in_period(t, bt.LONG_RUN)), 3)}"
              f" | 2026 {bt.fmt(bt.stats(bt.in_period(t, bt.YTD)), 3)}")
    print("\n== Same-day trades on hourly bars ==")
    H = {s: hourly_days(s) for s in bt.ETFS}
    for name, cfg in HOURLY_DAYTRADES.items():
        t = pd.concat([run_hourly(H[s], **cfg) for s in bt.ETFS], ignore_index=True)
        print(f"{name:52s} Dec23-25 {bt.fmt(bt.stats(bt.in_period(t, HOURLY_DEV)), 3)}"
              f" | 2026 {bt.fmt(bt.stats(bt.in_period(t, bt.YTD)), 3)}")
    panels = {s: checkpoints(s) for s in bt.ETFS}
    print("\n== RSI(2) pullback, forced out the same day ==")
    for close_k, label in ((5, "15:30"), (6, "16:00")):
        rows = []
        for period in (HOURLY_DEV, bt.YTD):
            t = same_day_pullback(panels, period, close_k)
            rows.append(bt.fmt(bt.stats(t)))
        print(f"sell by {label}: Dec23-25 {rows[0]} | 2026 {rows[1]}")


def same_day_pullback(panels, period, close_k):
    """The pullback entry, but every position is sold the same day: at price > SMA5 or at close_k."""
    look = {s: p.set_index(["date", "k"]) for s, p in panels.items()}
    days = sorted({d for p in panels.values() for d in p.date if period[0] <= d <= period[1]})
    out = []
    for day in days:
        held = None
        for k in range(0, close_k + 1):
            if held:
                r = look[held[0]].loc[(day, k)]
                if r.price > r.sma5 or k == close_k:
                    out.append(dict(entry_date=day, ret=(r.price / held[1] - 1) * 100, days=0))
                    break
            elif k <= 5:
                c = [(look[s].loc[(day, k)].rsi2, s) for s in panels if (day, k) in look[s].index
                     and look[s].loc[(day, k)].price > look[s].loc[(day, k)].sma200 and look[s].loc[(day, k)].rsi2 < 5]
                if c and k < close_k:
                    s = min(c)[1]
                    held = (s, look[s].loc[(day, k)].price)
    return pd.DataFrame(out)


def section_hourly():
    print("\n== RSI(2) pullback checked hourly, 10:30-15:30 (swing holds allowed) ==")
    panels = {s: checkpoints(s) for s in bt.ETFS}
    for thr in (3, 5, 7, 10):
        a, _ = simulate_hourly(panels, HOURLY_DEV, thr)
        b, _ = simulate_hourly(panels, bt.YTD, thr)
        print(f"RSI(2) < {thr:<2d}: Dec23-25 {bt.fmt(bt.stats(a))} | 2026 {bt.fmt(bt.stats(b))}")
    dev, ytd, open_pos = hourly_results()
    for label, t in (("Dec 2023-2025", dev), ("2026", ytd)):
        s = bt.stats(t)
        print(f"{label}: avg win {s['avg_w']:+.2f}%, avg loss {s['avg_l']:+.2f}%, worst {s['worst']:+.2f}%, "
              f"hold {s['days']:.1f} sessions, $ per $250 trade {t.ret.mean() * 2.5:+.2f}, total ${t.ret.sum() * 2.5:+.0f}")
    print("\n2026 trades:")
    print(ytd.round(2).to_string(index=False))
    print(f"open at the end of the data: {open_pos}")


def main(argv):
    for w in argv[1:] or ["daytrades", "hourly"]:
        {"daytrades": section_daytrades, "hourly": section_hourly}[w]()


if __name__ == "__main__":
    main(sys.argv)
