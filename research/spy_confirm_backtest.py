#!/usr/bin/env python3
"""Backtest the SPY overnight entry confirmed by a second ETF (QQQ).

Replays spy-overnight-options-entry.md day by day from 2026-01-01:
- Entry days are Mon-Thu, skipping the day before an NYSE holiday.
- Today's bar is a snapshot at 3:30pm ET built from 15-minute bars (open,
  high/low so far, last price), the nearest point at or before the routine's
  3:38pm start, so nothing after the decision leaks in.
- SPY and the confirming ETF each get the DECISION rules from
  overnight_signal.decide(); a trade happens only when both say CALLS or both
  say PUTS.
- "Correct" means SPY moved the signal's way from the 3:30pm entry price to
  the next trading day's exit price: 9:45am (the morning close routine's
  window), plus the next-day open and close for comparison.

Usage: spy_confirm_backtest.py [CONFIRM ...]   (default: QQQ; NONE = SPY alone)
"""

import csv
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import overnight_signal as osig  # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), "data")
FILES = {"SPY": "AMEX_SPY", "QQQ": "NASDAQ_QQQ", "IWM": "AMEX_IWM"}
START = dt.date(2026, 1, 1)
SNAPSHOT = dt.time(15, 30)   # last price = close of the 15:15 bar
EXIT_BAR = dt.time(9, 30)    # its close is the 9:45am price


def read(symbol, tf):
    rows = []
    with open(os.path.join(DATA, f"{FILES[symbol]}_{tf}.csv")) as f:
        for r in csv.DictReader(f):
            stamp = dt.datetime.strptime(r["et"], "%Y-%m-%d %H:%M")
            rows.append((stamp, float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"])))
    return rows


def load(symbol):
    daily = [osig.Bar(t.date(), o, h, l, c) for t, o, h, l, c in read(symbol, "1D")]
    intraday = {}
    for t, o, h, l, c in read(symbol, "15m"):
        intraday.setdefault(t.date(), []).append((t.time(), o, h, l, c))
    return daily, intraday


def snapshot(day, bars):
    """Today's bar as of SNAPSHOT, or None if the 15m data is incomplete."""
    early = [b for b in bars if b[0] < SNAPSHOT]
    if not early or early[0][0] != dt.time(9, 30) or early[-1][0] != dt.time(15, 15):
        return None
    return osig.todays_bar(day, early[0][1], max(b[2] for b in early),
                           min(b[3] for b in early), early[-1][4])


def signal(symbol, day, data):
    daily, intraday = data[symbol]
    today = snapshot(day, intraday.get(day, []))
    if today is None:
        return None, "no 15m data"
    try:
        return osig.decide(osig.build_series(daily, today)), None
    except osig.DataError as e:
        return None, str(e)


def main():
    confirms = [a.upper() for a in sys.argv[1:]] or ["QQQ"]
    symbols = {"SPY"} | {c for c in confirms if c != "NONE"}
    data = {s: load(s) for s in symbols}
    days = sorted(d for d in data["SPY"][1] if d >= START)

    for confirm in confirms:
        trades, skipped, disagree = [], [], 0
        for i, day in enumerate(days[:-1]):
            if day.weekday() > 3 or osig.holiday_tomorrow(day):
                continue
            nxt = days[i + 1]
            spy, err = signal("SPY", day, data)
            if spy is None:
                skipped.append((day, err))
                continue
            conf_sig = spy["signal"]
            if confirm != "NONE":
                other, err = signal(confirm, day, data)
                if other is None:
                    skipped.append((day, f"{confirm}: {err}"))
                    continue
                conf_sig = other["signal"]
            if spy["signal"] == "NO TRADE" or spy["signal"] != conf_sig:
                disagree += 1
                continue
            nb = data["SPY"][1][nxt]
            exit945 = next(b[4] for b in nb if b[0] == EXIT_BAR)
            nd = data["SPY"][0]
            nbar = next(b for b in nd if b.date == nxt)
            entry, sign = spy["price"], 1 if spy["signal"] == "CALLS" else -1
            trades.append(dict(day=day, sig=spy["signal"], conf=conf_sig, rule=spy["rule"],
                               entry=entry, x945=exit945, xopen=nbar.o, xclose=nbar.c,
                               r945=sign * (exit945 / entry - 1) * 100,
                               ropen=sign * (nbar.o / entry - 1) * 100,
                               rclose=sign * (nbar.c / entry - 1) * 100))

        label = "SPY alone" if confirm == "NONE" else f"SPY confirmed by {confirm}"
        print(f"\n=== {label}: {days[0]} to {days[-2]} entries, next-day exits ===")
        if confirm != "NONE":
            print(f"{'date':<11}{'SPY':<7}{confirm:<7}{'entry':>8}{'9:45':>9}{'move%':>8}  hit  rule")
        for t in trades:
            hit = "Y" if t["r945"] > 0 else "N"
            if confirm != "NONE":
                print(f"{t['day']!s:<11}{t['sig']:<7}{t['conf']:<7}{t['entry']:>8.2f}"
                      f"{t['x945']:>9.2f}{t['r945']:>8.2f}   {hit}   {t['rule']}")
        n = len(trades)
        print(f"\ntrade days: {n}   skipped for no-trade/disagreement: {disagree}   data skips: {len(skipped)}")
        for d, why in skipped:
            print(f"  data skip {d}: {why}")
        for key, name in (("r945", "next day 9:45am"), ("ropen", "next day open"), ("rclose", "next day close")):
            wins = sum(t[key] > 0 for t in trades)
            avg = sum(t[key] for t in trades) / n if n else 0
            print(f"correct by {name:<16}: {wins}/{n} ({100 * wins / n if n else 0:.0f}%)  avg SPY move {avg:+.3f}%")
        for s in ("CALLS", "PUTS"):
            sub = [t for t in trades if t["sig"] == s]
            wins = sum(t["r945"] > 0 for t in sub)
            print(f"  {s:<5} {wins}/{len(sub)} correct by 9:45am")


if __name__ == "__main__":
    main()
