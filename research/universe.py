"""The options system (research/system.py) run as a scanner across 28 liquid ETFs.

Rules are unchanged from system.py: Connors RSI(3,2,100) < 10 above the 200-day SMA, sell the
~0.30-delta put about 21 days out, buy a put one width lower, hold to the day before expiration.
Width uses the system's rule: the widest of $5/$4/$3/$2/$1 that keeps the max loss at or below $250
per spread. Results are also measured per dollar risked ("R" = profit / max loss) so the account
sizing can be studied separately.

Pricing: Black-Scholes. At-the-money IV = 0.89 x VIX9D x (the ETF's 60-day realized vol / SPY's),
which keeps the market's fear level and each ETF's relative riskiness; skew s = 0.18 for ETFs without
their own calibration. Each leg pays $0.025 of spread each way (SPY $0.01, QQQ/IWM $0.02) plus fees.

    python3 research/universe.py
"""
import datetime as dt
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt  # noqa: E402
import indicators as ind  # noqa: E402
import spreads as sp  # noqa: E402

FILES = {"SPY": "AMEX_SPY", "QQQ": "NASDAQ_QQQ", "IWM": "AMEX_IWM", "DIA": "AMEX_DIA",
         "XLF": "AMEX_XLF", "XLE": "AMEX_XLE", "XLK": "AMEX_XLK", "XLV": "AMEX_XLV", "XLI": "AMEX_XLI",
         "XLY": "AMEX_XLY", "XLP": "AMEX_XLP", "XLU": "AMEX_XLU", "XLB": "AMEX_XLB", "SMH": "NASDAQ_SMH",
         "GLD": "AMEX_GLD", "SLV": "AMEX_SLV", "TLT": "NASDAQ_TLT", "EFA": "AMEX_EFA", "FXI": "AMEX_FXI",
         "KRE": "AMEX_KRE", "XBI": "AMEX_XBI", "GDX": "AMEX_GDX", "XOP": "AMEX_XOP", "IYR": "AMEX_IYR",
         "EWZ": "AMEX_EWZ", "HYG": "AMEX_HYG", "ARKK": "AMEX_ARKK", "XRT": "AMEX_XRT"}
UNIVERSE = list(FILES)
# Kept by the rule fixed before looking at later years: 2007-2018 profit factor >= 1 (see __main__).
KEEP = ["ARKK", "DIA", "EFA", "FXI", "GDX", "GLD", "IWM", "KRE", "QQQ", "SMH", "SPY", "TLT", "XLF", "XLI",
        "XLY", "XOP", "XRT"]
HALF = {"SPY": 0.01, "QQQ": 0.02, "IWM": 0.02}
DEFAULT_HALF, DEFAULT_SKEW = 0.025, 0.18
TRAIN = (dt.date(2007, 1, 1), dt.date(2018, 12, 31))
LATER = (dt.date(2019, 1, 1), bt.YTD[1])


def load(sym):
    df = pd.read_csv(os.path.join(bt.DATA, f"{FILES[sym]}_1D.csv"))
    df["date"] = pd.to_datetime(df["et"].str[:10]).dt.date
    return df.drop_duplicates("date", keep="last").set_index("date")[["o", "h", "l", "c", "v"]]


def realized(c, n=60):
    return np.log(c).diff().rolling(n).std() * math.sqrt(252)


class ETF(sp.Market):
    """Same pricing as spreads.Market, with IV scaled by the ETF's realized vol relative to SPY."""

    def __init__(self, sym, vix, spy_rv):
        self.sym = sym
        d = load(sym)
        self.f = pd.DataFrame(index=d.index)
        self.f["c"] = d.c
        self.f["sma200"] = d.c.rolling(200).mean()
        self.f["crsi"] = ind.connors_rsi(d.c)
        rel = (realized(d.c) / spy_rv.reindex(d.index).ffill()).clip(0.5, 4.0)
        v9 = vix.vix9d.reindex(d.index).ffill().fillna(0.9 * vix.vix.reindex(d.index).ffill()) / 100
        self.v9 = v9 * rel.fillna(1.0) * (1.0 if sym == "SPY" else 1.0)
        self.dates = list(d.index)
        self.pos = {x: i for i, x in enumerate(self.dates)}
        self.c = d.c.values

    def atm(self, date):
        return 0.89 * self.v9.loc[date]

    def iv(self, date, S, K, T):
        a = self.atm(date)
        z = math.log(K / S) / (a * math.sqrt(max(T, 1 / 365)))
        s = sp.SKEW.get(self.sym, DEFAULT_SKEW)
        return a * min(max(1 - s * z, 0.6), 2.5)

    def step(self, S):
        return 0.5 if S < 60 else 1.0

    def strike_for_delta(self, date, S, T, target, call):
        q = sp.DIV.get(self.sym, 0.015)
        v = self.atm(date)
        for _ in range(4):
            d1 = -sp.norm.ppf(target * math.exp(q * T))
            K = S * math.exp((sp.R - q + v * v / 2) * T - d1 * v * math.sqrt(T))
            v = self.iv(date, S, K, T)
        st = self.step(S)
        cands = [math.floor(K / st) * st, math.ceil(K / st) * st]
        return min(cands, key=lambda k: abs(abs(sp.bs_delta(S, k, T, self.iv(date, S, k, T), q, call)) - target))

    def price(self, date, S, K, T, call):
        return sp.bs(S, K, T, self.iv(date, S, K, T), sp.DIV.get(self.sym, 0.015), call)


def open_trade(m, date, delta=0.30, dte=21):
    S = m.c[m.pos[date]]
    exp = sp.expiry_on_or_after(date, dte)
    T = (exp - date).days / 365
    hs = HALF.get(m.sym, DEFAULT_HALF)
    short_k = m.strike_for_delta(date, S, T, delta, call=False)
    for width in (5, 4, 3, 2, 1):  # the system's rule: widest that keeps max loss <= $250
        long_k = short_k - width
        if long_k <= 0:
            continue
        mid = m.price(date, S, short_k, T, False) - m.price(date, S, long_k, T, False)
        credit = mid - 2 * hs - 2 * sp.FEE
        if credit > 0 and (width - credit) * 100 <= sp.MAX_RISK:
            return dict(sym=m.sym, entry_date=date, exp=exp, short_k=short_k, long_k=long_k, width=width,
                        credit=credit, risk=width - credit)
    return None


def close_trade(m, t):
    """Hold to the last trading day before expiration; returns the trade with P&L per spread and R."""
    i = m.pos[t["entry_date"]]
    hs = HALF.get(m.sym, DEFAULT_HALF)
    for j in range(i + 1, len(m.dates)):
        d = m.dates[j]
        last = j + 1 >= len(m.dates) or m.dates[j + 1] >= t["exp"]
        if last:
            S = m.c[j]
            T = max((t["exp"] - d).days, 0) / 365
            mid = m.price(d, S, t["short_k"], T, False) - m.price(d, S, t["long_k"], T, False)
            debit = mid + 2 * hs + 2 * sp.FEE
            pnl = t["credit"] - debit
            if j + 1 >= len(m.dates) and m.dates[j] < t["exp"] - dt.timedelta(days=1):
                return None  # still open at the end of the data
            return dict(t, exit_date=d, pnl=pnl, R=pnl / t["risk"], days=j - i)
    return None


def all_signal_trades(markets):
    """Every signal, per ETF, one position at a time per ETF (portfolio limits are applied later)."""
    out = []
    for s, m in markets.items():
        sig = ((m.f.c > m.f.sma200) & (m.f.crsi < 10)).values
        busy = None
        for i, d in enumerate(m.dates):
            if not sig[i] or (busy and d <= busy) or i < 250:
                continue
            t = open_trade(m, d)
            if t is None:
                continue
            r = close_trade(m, t)
            if r is None:
                continue
            r["crsi"] = m.f.crsi.iloc[i]
            out.append(r)
            busy = r["exit_date"]
    return pd.DataFrame(out)


_M = None


def markets():
    global _M
    if _M is None:
        vx = bt.vix()
        spy = load("SPY")
        spy_rv = realized(spy.c)
        _M = {s: ETF(s, vx, spy_rv) for s in UNIVERSE}
    return _M


def per_etf(t):
    rows = []
    for s, g in t.groupby("sym"):
        a, b = g[(g.entry_date >= TRAIN[0]) & (g.entry_date <= TRAIN[1])], g[g.entry_date >= LATER[0]]
        pf = lambda x: x.R[x.R > 0].sum() / -x.R[x.R <= 0].sum() if (x.R <= 0).any() else float("inf")  # noqa: E731
        rows.append(dict(sym=s, n_train=len(a), win_train=100 * (a.R > 0).mean() if len(a) else np.nan,
                         pf_train=pf(a) if len(a) else np.nan, n_later=len(b),
                         win_later=100 * (b.R > 0).mean() if len(b) else np.nan, pf_later=pf(b) if len(b) else np.nan,
                         avgR_later=b.R.mean() if len(b) else np.nan))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    t = all_signal_trades(markets())
    t.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "universe_trades.csv"), index=False)
    pd.set_option("display.width", 200)
    e = per_etf(t)
    print(e.round(2).to_string(index=False))
    keep = e[e.pf_train >= 1.0].sym.tolist()
    print(f"\nKept by the 2007-2018 rule (profit factor >= 1): {len(keep)} of {len(e)}: {keep}")
    for label, x in (("all 28, 2007-2018", t[t.entry_date <= TRAIN[1]]), ("all 28, 2019-2026", t[t.entry_date >= LATER[0]]),
                     ("kept, 2019-2026", t[(t.entry_date >= LATER[0]) & t.sym.isin(keep)]),
                     ("kept, 2026", t[(t.entry_date >= bt.YTD[0]) & t.sym.isin(keep)])):
        w = (x.R > 0).mean() * 100
        pf = x.R[x.R > 0].sum() / -x.R[x.R <= 0].sum()
        print(f"{label:20s} trades={len(x):4d} win={w:5.1f}% avg R={x.R.mean():+.3f} PF={pf:.2f} per year={len(x) / max(1, len(set(d.year for d in x.entry_date))):.1f}")
