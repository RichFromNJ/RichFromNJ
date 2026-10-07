"""Vertical-spread backtests on SPY, QQQ and IWM driven by the TradingView indicator signals.

Option prices for 2007-2025 come from a Black-Scholes model calibrated to Robinhood quotes taken on
Oct 6, 2026 (17-day SPY / QQQ / IWM puts):
  at-the-money IV = ratio x VIX9D, with ratio 0.89 (SPY), 1.29 (QQQ), 1.45 (IWM)
  skew:  IV(K) = ATM IV x (1 - s x z), z = ln(K/S) / (ATM IV x sqrt(T)), s = 0.22 (SPY, QQQ), 0.15 (IWM)
2026 trades are re-priced with real Robinhood option bars in robinhood_check.py.

A trade is a WIN when it closes for more than it cost, after the bid-ask spread and fees.
"""
import datetime as dt
import math
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import norm

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt  # noqa: E402
import indicators as ind  # noqa: E402

UNIVERSE = ["SPY", "QQQ", "IWM"]
ATM_RATIO = {"SPY": 0.89, "QQQ": 1.29, "IWM": 1.45}
SKEW = {"SPY": 0.22, "QQQ": 0.22, "IWM": 0.15}
DIV = {"SPY": 0.013, "QQQ": 0.006, "IWM": 0.012}
HALF_SPREAD = {"SPY": 0.01, "QQQ": 0.02, "IWM": 0.02}  # per leg, per side, in $ per share
FEE = 0.0005  # $0.05 per contract per side, per share
R = 0.04
MAX_RISK = 250.0
PERIODS = {"train": (dt.date(2007, 1, 1), dt.date(2018, 12, 31)),
           "validate": (dt.date(2019, 1, 1), dt.date(2025, 12, 31)),
           "holdout": bt.YTD}


def bs(S, K, T, v, q, call):
    if T <= 0:
        return max(S - K, 0.0) if call else max(K - S, 0.0)
    d1 = (math.log(S / K) + (R - q + v * v / 2) * T) / (v * math.sqrt(T))
    d2 = d1 - v * math.sqrt(T)
    if call:
        return S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-R * T) * norm.cdf(d2)
    return K * math.exp(-R * T) * norm.cdf(-d2) - S * math.exp(-q * T) * norm.cdf(-d1)


def bs_delta(S, K, T, v, q, call):
    d1 = (math.log(S / K) + (R - q + v * v / 2) * T) / (v * math.sqrt(T))
    return math.exp(-q * T) * (norm.cdf(d1) if call else norm.cdf(d1) - 1)


class Market:
    """Daily closes, VIX9D and indicator columns for one ETF."""

    def __init__(self, sym, vix):
        self.sym = sym
        d = bt.daily(sym)
        self.f = ind.build(d, vix)
        v9 = vix.vix9d.reindex(d.index).ffill()
        fallback = 0.9 * vix.vix.reindex(d.index).ffill()  # VIX9D starts in 2011
        self.v9 = v9.fillna(fallback) / 100
        self.dates = list(d.index)
        self.pos = {x: i for i, x in enumerate(self.dates)}
        self.c = d.c.values

    def atm(self, date):
        return ATM_RATIO[self.sym] * self.v9.loc[date]

    def iv(self, date, S, K, T):
        a = self.atm(date)
        z = math.log(K / S) / (a * math.sqrt(max(T, 1 / 365)))
        return a * min(max(1 - SKEW[self.sym] * z, 0.6), 2.5)

    def price(self, date, S, K, T, call):
        return bs(S, K, T, self.iv(date, S, K, T), DIV[self.sym], call)

    def strike_for_delta(self, date, S, T, target, call):
        """Whole-dollar strike whose model delta is closest to the target (absolute value): solve
        with the at-the-money IV, then refine with the skewed IV at that strike."""
        q = DIV[self.sym]
        v = self.atm(date)
        for _ in range(4):
            d1 = norm.ppf(target * math.exp(q * T)) if call else -norm.ppf(target * math.exp(q * T))
            K = S * math.exp((R - q + v * v / 2) * T - d1 * v * math.sqrt(T))
            v = self.iv(date, S, K, T)
        cands = [math.floor(K), math.ceil(K)]
        return min(cands, key=lambda k: abs(abs(bs_delta(S, k, T, self.iv(date, S, k, T), q, call)) - target))


def expiry_on_or_after(date, days):
    e = date + dt.timedelta(days=days)
    while e.weekday() != 4:
        e += dt.timedelta(days=1)
    return e


def spread_value(m, date, S, legs, exp):
    """Mid value of a vertical (long leg minus short leg), per share."""
    T = max((exp - date).days, 0) / 365
    long_k, short_k, call = legs
    return m.price(date, S, long_k, T, call) - m.price(date, S, short_k, T, call)


def open_spread(m, date, kind, delta, dte):
    """kind 'put_credit' (bull put) or 'call_debit' (bull call). Returns the trade or None if it
    can't fit the $250 max-loss limit."""
    S = m.c[m.pos[date]]
    exp = expiry_on_or_after(date, dte)
    T = (exp - date).days / 365
    hs = HALF_SPREAD[m.sym]
    if kind == "put_credit":
        short_k = m.strike_for_delta(date, S, T, delta, call=False)
        for width in (5, 4, 3, 2, 1):
            long_k = short_k - width
            mid = spread_value(m, date, S, (long_k, short_k, False), exp)  # negative: a credit
            credit = -mid - 2 * hs - 2 * FEE
            if credit <= 0:
                continue
            if (width - credit) * 100 <= MAX_RISK:
                return dict(kind=kind, entry_date=date, S0=S, exp=exp, legs=(long_k, short_k, False),
                            width=width, entry=credit, max_loss=(width - credit) * 100)
        return None
    long_k = m.strike_for_delta(date, S, T, delta, call=True)
    for width in (5, 4, 3, 2, 1):
        short_k = long_k + width
        mid = spread_value(m, date, S, (long_k, short_k, True), exp)
        debit = mid + 2 * hs + 2 * FEE
        if debit * 100 <= MAX_RISK and debit < width:
            return dict(kind=kind, entry_date=date, S0=S, exp=exp, legs=(long_k, short_k, True),
                        width=width, entry=debit, max_loss=debit * 100)
    return None


def close_value(m, t, date):
    """What closing the spread on `date` returns per share (positive = cash received)."""
    S = m.c[m.pos[date]]
    hs = HALF_SPREAD[m.sym]
    mid = spread_value(m, date, S, t["legs"], t["exp"])
    if date >= t["exp"]:  # settles at intrinsic, no closing costs
        return mid
    return mid - 2 * hs - 2 * FEE


def run_trade(m, t, exit_rule, take_profit=0.5, signal_exit=None):
    """Walk forward day by day. Exits: take-profit (fraction of max profit), the signal exit, or the
    last trading day before expiration (closed at that day's close)."""
    i = m.pos[t["entry_date"]]
    credit = t["kind"] == "put_credit"
    for j in range(i + 1, len(m.dates)):
        d = m.dates[j]
        if d > t["exp"]:
            break
        v = close_value(m, t, d)
        pnl = (t["entry"] + v) if credit else (v - t["entry"])  # credit: received entry, pays -v
        max_profit = t["entry"] if credit else t["width"] - t["entry"]
        last = j + 1 >= len(m.dates) or m.dates[j + 1] >= t["exp"]
        hit_tp = take_profit is not None and pnl >= take_profit * max_profit
        hit_sig = exit_rule == "signal" and signal_exit is not None and bool(signal_exit.iloc[j])
        if hit_tp or hit_sig or last:
            return dict(t, exit_date=d, pnl=pnl * 100, ret=100 * pnl * 100 / t["max_loss"], days=j - i,
                        why="target" if hit_tp else ("signal" if hit_sig else "time"))
    return None


def trades_for(m, entry, kind, delta, dte, exit_rule, take_profit, one_at_a_time=True):
    sig_exit = m.f.c > m.f.sma5
    out, busy_until = [], None
    for d in m.f.index[entry.fillna(False).astype(bool).values]:
        if one_at_a_time and busy_until and d <= busy_until:
            continue
        t = open_spread(m, d, kind, delta, dte)
        if t is None:
            continue
        r = run_trade(m, t, exit_rule, take_profit, sig_exit)
        if r:
            out.append(r)
            busy_until = r["exit_date"]
    return pd.DataFrame(out)


def summarize(t):
    if len(t) == 0:
        return dict(n=0)
    w = t.pnl > 0
    lo, hi = bt.wilson(int(w.sum()), len(t))
    gain, loss = t.pnl[w].sum(), -t.pnl[~w].sum()
    return dict(n=len(t), win=100 * w.mean(), lo=100 * lo, hi=100 * hi, avg=t.pnl.mean(),
                pf=gain / loss if loss > 0 else float("inf"), worst=t.pnl.min(), avg_w=t.pnl[w].mean() if w.any() else 0,
                avg_l=t.pnl[~w].mean() if (~w).any() else 0, days=t.days.mean())


def fmt(s):
    if not s.get("n"):
        return "n=0"
    return (f"n={s['n']:4d} win={s['win']:5.1f}% [{s['lo']:.0f}-{s['hi']:.0f}] avg=${s['avg']:+6.1f} "
            f"PF={s['pf']:.2f} W/L=${s['avg_w']:+.0f}/${s['avg_l']:+.0f}")
