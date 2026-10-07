"""What would it take to turn $500 into $10,000 in 90 days with the scanner's trades?

Replays the scanner's real trade sequence (research/universe_trades.csv, the 17 ETFs kept by the
2007-2018 rule) with an account that starts at $500, for every 90-calendar-day window starting on each
trading day from Jan 2019 to Jul 2026. Sizing rules:
  "1 contract"   one spread at a time, 1 contract (risk ~$60-$250), like the paper system
  f% of equity   each new trade risks f% of current equity (fractional contracts, an upper bound),
                 up to 3 open at once and no more than 100% of equity at risk in total

    python3 research/growth.py
"""
import datetime as dt
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from universe import KEEP  # noqa: E402


def load():
    t = pd.read_csv(os.path.join(HERE, "universe_trades.csv"), parse_dates=["entry_date", "exit_date"])
    t = t[t.sym.isin(KEEP)].copy()
    t["entry_date"], t["exit_date"] = t.entry_date.dt.date, t.exit_date.dt.date
    return t.sort_values(["entry_date", "crsi"]).reset_index(drop=True)


def run_window(t, start, days, mode, f=0.0, max_open=3, start_equity=500.0):
    end = start + dt.timedelta(days=days)
    w = t[(t.entry_date >= start) & (t.exit_date <= end)]
    equity, open_ = start_equity, []
    events = sorted(set(w.entry_date) | set(w.exit_date))
    by_entry = {d: g for d, g in w.groupby("entry_date")}
    low = equity
    for d in events:
        still = []
        for p in open_:
            if p["exit_date"] <= d:
                equity += p["dollars"] * p["R"]
            else:
                still.append(p)
        open_ = still
        low = min(low, equity)
        if equity <= 1:
            return equity, low
        for r in (by_entry.get(d, pd.DataFrame()).itertuples() if d in by_entry else []):
            if any(p["sym"] == r.sym for p in open_):
                continue
            per_contract = r.risk * 100
            if mode == "1 contract":
                if open_ or per_contract > equity:
                    continue
                dollars = per_contract
            else:
                at_risk = sum(p["dollars"] for p in open_)
                dollars = min(f * equity, equity - at_risk)
                if len(open_) >= max_open or dollars <= 0:
                    continue
            open_.append(dict(sym=r.sym, exit_date=r.exit_date, R=r.R, dollars=dollars))
    for p in open_:
        equity += p["dollars"] * p["R"]
    return equity, min(low, equity)


def run_window_with_deposits(t, start, end, monthly):
    """Trades 1 contract at a time from start to end, adding `monthly` dollars on each month's first trading day."""
    w = t[(t.entry_date >= start) & (t.exit_date <= end)]
    equity, busy_until, month = 500.0, None, (start.year, start.month)
    for r in w.itertuples():
        m = (r.entry_date.year, r.entry_date.month)
        while month < m:
            month = (month[0] + (month[1] == 12), month[1] % 12 + 1)
            equity += monthly
        if busy_until and r.entry_date <= busy_until:
            continue
        if r.risk * 100 > equity:
            continue
        equity += r.risk * 100 * r.R
        busy_until = r.exit_date
    while month < (end.year, end.month):
        month = (month[0] + (month[1] == 12), month[1] % 12 + 1)
        equity += monthly
    return equity


def study(t, days=90, first=dt.date(2019, 1, 1), last=dt.date(2026, 7, 7)):
    starts = [d.date() for d in pd.bdate_range(first, last)]
    rows = []
    for label, mode, f in (("1 contract at a time", "1 contract", 0), ("25% of equity per trade", "f", 0.25),
                           ("50% of equity per trade", "f", 0.50), ("100% of equity per trade", "f", 1.00)):
        ends = np.array([run_window(t, s, days, mode, f)[0] for s in starts])
        rows.append(dict(sizing=label, windows=len(ends), median=np.median(ends), p90=np.percentile(ends, 90),
                         best=ends.max(), hit_10k=100 * (ends >= 10000).mean(), hit_3k=100 * (ends >= 3000).mean(),
                         hit_1k=100 * (ends >= 1000).mean(),
                         lost_half=100 * (ends <= 250).mean(), lost_money=100 * (ends < 500).mean()))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    t = load()
    pd.set_option("display.width", 200)
    print(f"{len(t)} scanner trades, 2007-2026 (17 ETFs)")
    print("\n90-day windows starting each trading day, Jan 2019 - Jul 2026, $500 start:")
    print(study(t).round(1).to_string(index=False))
    for target in (10000, 3000):
        need = (target / 500) ** (1 / 63) - 1
        print(f"$500 -> ${target:,} in 63 trading days needs +{need * 100:.1f}% every trading day, compounded.")
    # Longer horizon and monthly deposits, 1 contract at a time while the account is small
    print("\nWhole 2019-2026 replay, 1 contract at a time, $500 start:")
    for deposit in (0, 250, 500, 800):
        eq = run_window_with_deposits(t, dt.date(2019, 1, 2), dt.date(2026, 10, 6), deposit)
        print(f"  ${deposit}/month deposits: ${eq:,.0f}")
