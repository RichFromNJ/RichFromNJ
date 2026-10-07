"""Backtests behind research/README.md, run on TradingView bars saved in research/data.

    python3 research/backtest.py            # every table in the report
    python3 research/backtest.py routine    # just the proposed Routine

Sections:
  baseline  - the live EEM overnight rules, scored at 3:45pm each 2026 day, exit next morning
  catalog   - published swing/overnight strategies on SPY, QQQ, IWM, DIA, EEM, 2007-2025 vs 2026
  options   - the same swing trades priced as calls (Black-Scholes, IV from VIX)
  routine   - the proposed Routine: one $250 share position at a time across the five ETFs
  checks    - per-year results, sub-periods, slippage, threshold sensitivity

Needs numpy, pandas and scipy.
"""
import datetime as dt
import math
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import norm

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
sys.path.insert(0, os.path.dirname(HERE))
import overnight_signal as sig  # noqa: E402

ETFS = ["SPY", "QQQ", "IWM", "DIA", "EEM"]
FILES = {"SPY": "AMEX_SPY", "QQQ": "NASDAQ_QQQ", "IWM": "AMEX_IWM", "DIA": "AMEX_DIA", "EEM": "AMEX_EEM",
         "VIX": "TVC_VIX", "VIX9D": "CBOE_VIX9D"}
LONG_RUN = (dt.date(2007, 1, 1), dt.date(2025, 12, 31))
YTD = (dt.date(2026, 1, 1), dt.date(2026, 10, 6))
STAKE = 250.0
MAX_HOLD = 10


# ---------------------------------------------------------------- data

def daily(sym):
    df = pd.read_csv(os.path.join(DATA, f"{FILES[sym]}_1D.csv"))
    df["date"] = pd.to_datetime(df["et"].str[:10]).dt.date
    return df.drop_duplicates("date", keep="last").set_index("date")[["o", "h", "l", "c", "v"]]


def session_points(sym):
    """Per 2026 day from 15-minute bars: open, 9:45 price, 3:45pm price, high/low through 3:45pm, close."""
    df = pd.read_csv(os.path.join(DATA, f"{FILES[sym]}_15m.csv"))
    df["date"] = pd.to_datetime(df["et"].str[:10]).dt.date
    df["hm"] = df["et"].str[11:]
    rows = {}
    for d, g in df.groupby("date"):
        g = g.set_index("hm")
        if "09:30" not in g.index or "15:30" not in g.index:
            continue
        upto = g.loc[:"15:30"]
        rows[d] = dict(o=g.loc["09:30", "o"], p0945=g.loc["09:30", "c"], p1545=g.loc["15:30", "c"],
                       h1545=upto["h"].max(), l1545=upto["l"].min(), close=g["c"].iloc[-1])
    return pd.DataFrame.from_dict(rows, orient="index").sort_index()


def vix():
    return pd.concat([daily("VIX")["c"].rename("vix"), daily("VIX9D")["c"].rename("vix9d")], axis=1)


# ---------------------------------------------------------------- indicators and scoring

def wilder_state(c, n=2):
    """Wilder average gain/loss after each bar, seeded with the simple average of the first n changes."""
    diff = np.diff(c, prepend=np.nan)
    au, ad = np.full(len(c), np.nan), np.full(len(c), np.nan)
    au[n] = np.mean(np.clip(diff[1:n + 1], 0, None))
    ad[n] = np.mean(np.clip(-diff[1:n + 1], 0, None))
    for i in range(n + 1, len(c)):
        au[i] = (au[i - 1] * (n - 1) + max(diff[i], 0)) / n
        ad[i] = (ad[i - 1] * (n - 1) + max(-diff[i], 0)) / n
    return au, ad


def rsi_from(au, ad):
    return np.where(ad == 0, 100.0, 100 - 100 / (1 + au / np.where(ad == 0, 1, ad)))


def rsi_next(au, ad, prev_close, price, n=2):
    """RSI(n) if today's close were `price`, given the Wilder state through yesterday."""
    d = price - prev_close
    au2 = (au * (n - 1) + max(d, 0)) / n
    ad2 = (ad * (n - 1) + max(-d, 0)) / n
    return 100.0 if ad2 == 0 else 100 - 100 / (1 + au2 / ad2)


def wilson(k, n, z=1.96):
    if n == 0:
        return float("nan"), float("nan")
    p, den = k / n, 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return c - h, c + h


def stats(t):
    if len(t) == 0:
        return dict(n=0)
    w = t.ret > 0
    k, n = int(w.sum()), len(t)
    lo, hi = wilson(k, n)
    gain, loss = t.ret[w].sum(), -t.ret[~w].sum()
    return dict(n=n, wins=k, win=100 * k / n, lo=100 * lo, hi=100 * hi, avg=t.ret.mean(),
                avg_w=t.ret[w].mean() if k else 0.0, avg_l=t.ret[~w].mean() if k < n else 0.0,
                pf=gain / loss if loss > 0 else float("inf"), days=t.days.mean(), worst=t.ret.min())


def fmt(s, pct_digits=2):
    if not s.get("n"):
        return "n=0"
    return (f"n={s['n']:4d} win={s['win']:5.1f}% [{s['lo']:.0f}-{s['hi']:.0f}] "
            f"avg={s['avg']:+.{pct_digits}f}% PF={s['pf']:.2f}")


def in_period(t, period, col="entry_date"):
    a, b = period
    return t[(t[col] >= a) & (t[col] <= b)]


# ---------------------------------------------------------------- baseline: the live overnight rules

def live_rules_2026(sym):
    """Signal from the live Routine's rules at 3:45pm each Mon-Thu (skipping days before a holiday),
    entered at the 3:45pm price, exited at the next session's open or 9:45 price."""
    d, sp = daily(sym), session_points(sym)
    days = [x for x in sp.index if x >= YTD[0]]
    out = []
    for i, day in enumerate(days[:-1]):
        if day.weekday() > 3 or sig.holiday_tomorrow(day):
            continue
        hist = [sig.Bar(date=k, o=r.o, h=r.h, l=r.l, c=r.c) for k, r in d[d.index < day].tail(120).iterrows()]
        p, q = sp.loc[day], sp.loc[days[i + 1]]
        today = sig.todays_bar(day, p.o, max(p.h1545, p.o, p.p1545), min(p.l1545, p.o, p.p1545), p.p1545)
        try:
            v = sig.decide(sig.build_series(hist, today))
        except sig.DataError:
            continue
        if v["signal"] not in ("CALLS", "PUTS"):
            continue
        side = 1 if v["signal"] == "CALLS" else -1
        out.append(dict(date=day, signal=v["signal"], rule=v["rule"][:6], entry=p.p1545,
                        x_open=q.o, x_0945=q.p0945, side=side,
                        ret_open=side * (q.o / p.p1545 - 1) * 100, ret_0945=side * (q.p0945 / p.p1545 - 1) * 100))
    return pd.DataFrame(out)


R = 0.04


def bs(S, K, T, v, call=True):
    if T <= 0:
        return max(S - K, 0.0) if call else max(K - S, 0.0)
    d1 = (math.log(S / K) + (R + v * v / 2) * T) / (v * math.sqrt(T))
    d2 = d1 - v * math.sqrt(T)
    if call:
        return S * norm.cdf(d1) - K * math.exp(-R * T) * norm.cdf(d2)
    return K * math.exp(-R * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def live_rules_options_2026():
    """Model the live EEM trade as the nearest ITM / OTM option: bought at ask 3:45pm, sold at bid 9:45am.
    IV = 1.4 x VIX9D (EEM's 1.4 ratio is from Robinhood quotes on 10/6), half-spread $0.01, fees $0.04."""
    t, vx = live_rules_2026("EEM"), vix()
    rows = []
    for r in t.itertuples():
        call, S0, S1 = r.signal == "CALLS", r.entry, r.x_0945
        wd = r.date.weekday()
        exp = r.date + dt.timedelta(days=(2 - wd) if wd <= 1 else (4 - wd))
        gap = 1 if wd < 4 else 3
        T0 = ((exp - r.date).days * 24 + 0.25) / (365 * 24)
        T1 = max(((exp - r.date).days * 24 - gap * 24 + 6.25) / (365 * 24), 0)
        v = 1.4 * vx.vix9d.loc[r.date] / 100
        for kind in ("ITM", "OTM"):
            if call:
                K = math.floor(S0) if kind == "ITM" else math.floor(S0) + 1
            else:
                K = math.ceil(S0) if kind == "ITM" else math.ceil(S0) - 1
            buy = bs(S0, K, T0, v, call) + 0.01 + 0.0004
            sell = max(bs(S1, K, T1, v, call) - 0.01, 0) - 0.0004
            rows.append(dict(kind=kind, ret=(sell / buy - 1) * 100, days=1))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- strategy catalog (daily closes)

def features(sym):
    d = daily(sym).copy()
    au, ad = wilder_state(d.c.values)
    d["rsi2"] = rsi_from(au, ad)
    d["sma200"] = d.c.rolling(200).mean()
    d["sma5"] = d.c.rolling(5).mean()
    d["ibs"] = ((d.c - d.l) / (d.h - d.l)).where(d.h > d.l, 0.5)
    d["low7"], d["high7"] = d.c.rolling(7).min(), d.c.rolling(7).max()
    d["next_o"] = d.o.shift(-1)
    d = d.join(vix(), how="left")
    d["vix"] = d.vix.ffill()
    d["vix_ma10"] = d.vix.rolling(10).mean()
    return d


def swing(d, entry, exit_rule, max_hold=MAX_HOLD, side=1):
    """Buy the signal day's close, sell the close of the first day the exit rule is true (or the
    max_hold-th day). One position at a time per symbol; a trade still open at the end is dropped."""
    trades, i, n = [], 0, len(d)
    E, X, C, idx = entry.values, exit_rule.values, d.c.values, d.index
    while i < n - 1:
        if not E[i]:
            i += 1
            continue
        j = i + 1
        while j < n - 1 and not X[j] and j - i < max_hold:
            j += 1
        if not X[j] and j - i < max_hold:
            break
        trades.append(dict(entry_date=idx[i], exit_date=idx[j], entry=C[i], exit=C[j],
                           ret=side * (C[j] / C[i] - 1) * 100, days=j - i))
        i = j + 1
    return pd.DataFrame(trades)


def swing_next_open(d, entry, exit_rule, max_hold=MAX_HOLD):
    """Same signals as swing(), but buy and sell at the NEXT session's open (no look-ahead)."""
    trades, i, n = [], 0, len(d)
    E, X, O, idx = entry.values, exit_rule.values, d.o.values, d.index
    while i < n - 2:
        if not E[i]:
            i += 1
            continue
        j = i + 1
        while j < n - 1 and not X[j] and j - i < max_hold:
            j += 1
        if j + 1 >= n:
            break
        trades.append(dict(entry_date=idx[i], exit_date=idx[j], entry=O[i + 1], exit=O[j + 1],
                           ret=(O[j + 1] / O[i + 1] - 1) * 100, days=j - i))
        i = j + 1
    return pd.DataFrame(trades)


def overnight(d, entry):
    t = d[entry & d.next_o.notna()]
    return pd.DataFrame(dict(entry_date=t.index, entry=t.c.values, exit=t.next_o.values,
                             ret=(t.next_o.values / t.c.values - 1) * 100, days=1))


ALWAYS = lambda d: pd.Series(True, index=d.index)  # noqa: E731
CATALOG = {
    # Connors & Alvarez (2008/2009): RSI(2) pullback in an uptrend, exit on a close above the 5-day SMA.
    "RSI2<5 pullback": lambda d: swing(d, (d.c > d.sma200) & (d.rsi2 < 5), d.c > d.sma5),
    "RSI2<10 pullback": lambda d: swing(d, (d.c > d.sma200) & (d.rsi2 < 10), d.c > d.sma5),
    # Connors: Double 7s.
    "Double 7s": lambda d: swing(d, (d.c > d.sma200) & (d.c <= d.low7), d.c >= d.high7),
    # Connors: VIX stretch (VIX 5% above its 10-day average), exit RSI(2) > 65.
    "VIX stretch": lambda d: swing(d, (d.c > d.sma200) & (d.vix > 1.05 * d.vix_ma10), d.rsi2 > 65),
    # Internal bar strength: close in the bottom 20% of the day's range, hold one day.
    "IBS<0.2, 1 day": lambda d: swing(d, d.ibs < 0.2, ALWAYS(d), max_hold=1),
    # Overnight holds (the live Routine's horizon), close to next open.
    "Overnight, every day": lambda d: overnight(d, ALWAYS(d)),
    "Overnight IBS<0.25 + trend": lambda d: overnight(d, (d.ibs < 0.25) & (d.c > d.sma200)),
    "Overnight RSI2<10 + trend": lambda d: overnight(d, (d.rsi2 < 10) & (d.c > d.sma200)),
    # Mirror image for puts: RSI(2) > 90 in a downtrend, exit on a close below the 5-day SMA.
    "Short RSI2>90 downtrend": lambda d: swing(d, (d.c < d.sma200) & (d.rsi2 > 90), d.c < d.sma5, side=-1),
}


def catalog_trades(name, feats):
    return pd.concat([CATALOG[name](feats[s]).assign(sym=s) for s in ETFS], ignore_index=True)


# ---------------------------------------------------------------- the same trades as calls

IV_RATIO = {"SPY": 1.0, "QQQ": 1.25, "IWM": 1.35, "DIA": 0.95, "EEM": 1.4}
STRIKE_STEP = {"SPY": 1.0, "QQQ": 1.0, "IWM": 1.0, "DIA": 1.0, "EEM": 0.5}


def call_overlay(trades, feats_sym, sym, delta, min_days, half_spread_pct=0.01):
    """Price each swing trade as one call: delta-targeted strike, first Friday at least min_days out,
    IV = ratio x VIX on each day, bought at mid + half-spread, sold at mid - half-spread."""
    vx = feats_sym.vix
    rows = []
    for t in trades.itertuples():
        v0 = IV_RATIO[sym] * vx.loc[t.entry_date] / 100
        v1 = IV_RATIO[sym] * vx.loc[t.exit_date] / 100
        exp = t.entry_date + dt.timedelta(days=min_days)
        while exp.weekday() != 4:
            exp += dt.timedelta(days=1)
        T0, T1 = (exp - t.entry_date).days / 365, (exp - t.exit_date).days / 365
        k = t.entry * math.exp(-norm.ppf(delta) * v0 * math.sqrt(T0) + (R + v0 * v0 / 2) * T0)
        K = round(k / STRIKE_STEP[sym]) * STRIKE_STEP[sym]
        m0, m1 = bs(t.entry, K, T0, v0), bs(t.exit, K, T1, v1)
        buy = m0 + max(0.01, half_spread_pct * m0) + 0.0004
        sell = max(m1 - max(0.01, half_spread_pct * m1), 0) - 0.0004
        rows.append(dict(entry_date=t.entry_date, ret=(sell / buy - 1) * 100, days=t.days, cost=buy * 100))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- the proposed Routine

def decision_panel(sym, at_345=False):
    """Values the Routine would compute each day, treating the decision price as today's close:
    the daily close, or (2026 only) the 3:45pm price from 15-minute bars."""
    d = daily(sym)
    c, idx = d.c.values, list(d.index)
    au, ad = wilder_state(c)
    sp = session_points(sym) if at_345 else None
    rows = []
    for i in range(201, len(c)):
        day = idx[i]
        if at_345 and day not in sp.index:
            continue
        p = sp.loc[day, "p1545"] if at_345 else c[i]
        rows.append(dict(date=day, price=p, rsi2=rsi_next(au[i - 1], ad[i - 1], c[i - 1], p),
                         sma200=(c[i - 199:i].sum() + p) / 200, sma5=(c[i - 4:i].sum() + p) / 5))
    return pd.DataFrame(rows).set_index("date")


def pullback_entry(row, threshold=5.0):
    return row.price > row.sma200 and row.rsi2 < threshold


def pullback_exit(row):
    return row.price > row.sma5


def simulate(panels, period, entry=pullback_entry, exit_=pullback_exit, max_hold=MAX_HOLD, stake=STAKE):
    """One position at a time. Each day: sell if the exit rule is true or the position has been held
    max_hold trading days; then, if flat, buy the ETF with the lowest RSI(2) among those signalling."""
    dates = sorted(x for x in set().union(*(set(p.index) for p in panels.values())) if period[0] <= x <= period[1])
    pos, trades = None, []
    for day in dates:
        if pos and day in panels[pos["sym"]].index:
            row = panels[pos["sym"]].loc[day]
            pos["held"] += 1
            if exit_(row) or pos["held"] >= max_hold:
                ret = (row.price / pos["entry"] - 1) * 100
                trades.append(dict(sym=pos["sym"], entry_date=pos["date"], exit_date=day, entry=pos["entry"],
                                   exit=row.price, ret=ret, pnl=stake * ret / 100, days=pos["held"]))
                pos = None
        if pos is None:
            cands = [(p.loc[day].rsi2, s, p.loc[day].price) for s, p in panels.items()
                     if day in p.index and entry(p.loc[day])]
            if cands:
                _, s, px = min(cands)
                pos = dict(sym=s, date=day, entry=px, held=0)
    return pd.DataFrame(trades), pos


# ---------------------------------------------------------------- report sections

def section_baseline():
    print("\n== Live EEM overnight rules, 2026, signal at 3:45pm ==")
    for sym in ETFS:
        t = live_rules_2026(sym)
        for col in ("ret_open", "ret_0945"):
            x = t.assign(ret=t[col], days=1)
            s = stats(x)
            print(f"{sym} exit {'open' if col == 'ret_open' else '9:45'}: {fmt(s, 3)}")
    o = live_rules_options_2026()
    for k, g in o.groupby("kind"):
        print(f"EEM modeled {k} option, exit 9:45: {fmt(stats(g), 1)}")


def section_catalog(feats):
    print("\n== Strategy catalog: ALL five ETFs (per-ETF lines for the pullbacks) ==")
    for name in CATALOG:
        t = catalog_trades(name, feats)
        print(f"{name:28s} 2007-25 {fmt(stats(in_period(t, LONG_RUN)))} | 2026 {fmt(stats(in_period(t, YTD)))}")


def section_options(feats):
    print("\n== The same swing trades bought as calls (modeled) ==")
    for name in ("RSI2<5 pullback", "RSI2<10 pullback", "VIX stretch"):
        for delta, days in ((0.70, 21), (0.50, 21), (0.30, 21)):
            parts, cost = [], {}
            for s in ETFS:
                t = CATALOG[name](feats[s])
                o = call_overlay(in_period(t, (LONG_RUN[0], YTD[1])), feats[s], s, delta, days)
                cost[s] = in_period(o, YTD).cost.median()
                parts.append(o)
            o = pd.concat(parts, ignore_index=True)
            print(f"{name:17s} delta {delta:.2f} {days}d: 2007-25 {fmt(stats(in_period(o, LONG_RUN)), 1)}"
                  f" | 2026 {fmt(stats(in_period(o, YTD)), 1)} | 2026 median cost: "
                  + " ".join(f"{k} ${v:,.0f}" for k, v in cost.items()))


def routine_results():
    close = {s: decision_panel(s) for s in ETFS}
    at345 = {s: decision_panel(s, at_345=True) for s in ETFS}
    long_run, _ = simulate(close, LONG_RUN)
    ytd_close, _ = simulate(close, YTD)
    ytd_345, open_pos = simulate(at345, YTD)
    return long_run, ytd_close, ytd_345, open_pos


def section_routine():
    long_run, ytd_close, ytd_345, open_pos = routine_results()
    print("\n== Proposed Routine: RSI(2) < 5 pullback, one $250 position at a time ==")
    for label, t in (("2007-2025, daily close", long_run), ("2026, daily close", ytd_close),
                     ("2026, 3:45pm prices", ytd_345)):
        s = stats(t)
        print(f"{label:24s} {fmt(s)} avgW={s['avg_w']:+.2f}% avgL={s['avg_l']:+.2f}% "
              f"hold={s['days']:.1f}d worst={s['worst']:+.1f}% $/trade={t.pnl.mean():+.2f} total=${t.pnl.sum():+.0f}")
    print("\n2026 trades at 3:45pm prices:")
    print(ytd_345[["sym", "entry_date", "exit_date", "entry", "exit", "ret", "pnl", "days"]]
          .round({"entry": 2, "exit": 2, "ret": 2, "pnl": 2}).to_string(index=False))
    print(f"open at the end of the data: {open_pos}")


def section_checks():
    feats = {s: features(s) for s in ETFS}
    nxt = pd.concat([swing_next_open(feats[s], (feats[s].c > feats[s].sma200) & (feats[s].rsi2 < 5),
                                     feats[s].c > feats[s].sma5).assign(sym=s) for s in ETFS], ignore_index=True)
    print(f"\nRSI2<5 per ETF, buy/sell at the next open: 2007-25 {fmt(stats(in_period(nxt, LONG_RUN)))}"
          f" | 2026 {fmt(stats(in_period(nxt, YTD)))}")
    close = {s: decision_panel(s) for s in ETFS}
    t, _ = simulate(close, (LONG_RUN[0], YTD[1]))
    print("Routine trades by ETF, 2007-2026: " + ", ".join(
        f"{s} {100 * (g.ret > 0).mean():.0f}% of {len(g)}" for s, g in t.groupby("sym")))
    t["yr"] = [d.year for d in t.entry_date]
    print("\n== Per year (RSI2<5 Routine, daily closes) ==")
    for y, g in t.groupby("yr"):
        print(f"{y}: {len(g):2d} trades, win {100 * (g.ret > 0).mean():5.1f}%, avg {g.ret.mean():+.2f}%, ${g.pnl.sum():+.1f}")
    for label, period in (("2007-2016", (LONG_RUN[0], dt.date(2016, 12, 31))),
                          ("2017-2025", (dt.date(2017, 1, 1), LONG_RUN[1]))):
        print(f"{label}: {fmt(stats(in_period(t, period)))}")
    slip = in_period(t, LONG_RUN).assign(ret=lambda x: x.ret - 0.04)
    print(f"2007-2025 with 0.04% round-trip slippage: {fmt(stats(slip))}")
    print("Worst trades:")
    print(t.nsmallest(5, "ret")[["sym", "entry_date", "exit_date", "ret", "days"]].round(2).to_string(index=False))
    print("\nThreshold / exit sensitivity (2007-2025 | 2026):")
    for thr in (3, 5, 7, 10):
        for xname, xf in (("close > SMA5", pullback_exit), ("RSI2 > 65", lambda r: r.rsi2 > 65)):
            e = lambda r, thr=thr: pullback_entry(r, thr)  # noqa: E731
            a, _ = simulate(close, LONG_RUN, entry=e, exit_=xf)
            b, _ = simulate(close, YTD, entry=e, exit_=xf)
            print(f"RSI2<{thr:<2d} exit {xname:12s}: {fmt(stats(a))} | {fmt(stats(b))}")


def main(argv):
    what = argv[1:] or ["baseline", "catalog", "options", "routine", "checks"]
    feats = {s: features(s) for s in ETFS} if {"catalog", "options"} & set(what) else None
    for w in what:
        {"baseline": section_baseline, "catalog": lambda: section_catalog(feats),
         "options": lambda: section_options(feats), "routine": section_routine, "checks": section_checks}[w]()


if __name__ == "__main__":
    main(sys.argv)
