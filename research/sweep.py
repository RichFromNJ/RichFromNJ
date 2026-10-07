"""Sweep every rebuilt TradingView indicator signal on SPY, QQQ and IWM.

For each signal, direction (bullish / bearish) and holding period (1, 3, 5, 10 days), it scores how
often the ETF moved the predicted way from the signal day's close. Periods:
  train      2007-2018  (used to choose)
  validate   2019-2025  (used to confirm)
  holdout    2026       (reported, never used to choose)

    python3 research/sweep.py
"""
import datetime as dt
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest as bt  # noqa: E402
import indicators as ind  # noqa: E402

UNIVERSE = ["SPY", "QQQ", "IWM"]
HORIZONS = (1, 3, 5, 10)
PERIODS = {"train": (dt.date(2007, 1, 1), dt.date(2018, 12, 31)),
           "validate": (dt.date(2019, 1, 1), dt.date(2025, 12, 31)),
           "holdout": bt.YTD}


def features():
    vx = bt.vix()
    out = {}
    for s in UNIVERSE:
        f = ind.build(bt.daily(s), vx)
        for h in HORIZONS:
            f[f"fwd{h}"] = 100 * (f.c.shift(-h) / f.c - 1)
        out[s] = f
    return out


def score(feats, name, side, h):
    rows = []
    for s, f in feats.items():
        bull, bear = ind.SIGNALS[name](f)
        cond = (bull if side == "bull" else bear).fillna(False).astype(bool)
        x = f.loc[cond, [f"fwd{h}"]].dropna()
        x["ret"] = x[f"fwd{h}"] * (1 if side == "bull" else -1)
        rows.append(x)
    x = pd.concat(rows)
    res = {}
    for p, (a, b) in PERIODS.items():
        y = x[(x.index >= a) & (x.index <= b)]
        res[p] = (len(y), 100 * (y.ret > 0).mean() if len(y) else float("nan"), y.ret.mean() if len(y) else float("nan"))
    return res


def base_rates(feats):
    """How often the ETFs simply rose over each holding period: the bar every bullish signal must beat."""
    out = {}
    for h in HORIZONS:
        x = pd.concat([f[[f"fwd{h}"]].dropna() for f in feats.values()])
        out[h] = {p: 100 * (x[(x.index >= a) & (x.index <= b)][f"fwd{h}"] > 0).mean() for p, (a, b) in PERIODS.items()}
    return out


def run(min_train=100, min_val=50, min_win=60.0):
    feats = features()
    base = base_rates(feats)
    rows = []
    for name in ind.SIGNALS:
        for side in ("bull", "bear"):
            for h in HORIZONS:
                r = score(feats, name, side, h)
                b = {p: (base[h][p] if side == "bull" else 100 - base[h][p]) for p in PERIODS}
                rows.append(dict(signal=name, side=side, h=h,
                                 n_tr=r["train"][0], win_tr=r["train"][1], avg_tr=r["train"][2], edge_tr=r["train"][1] - b["train"],
                                 n_va=r["validate"][0], win_va=r["validate"][1], avg_va=r["validate"][2], edge_va=r["validate"][1] - b["validate"],
                                 n_ho=r["holdout"][0], win_ho=r["holdout"][1], avg_ho=r["holdout"][2]))
    t = pd.DataFrame(rows)
    t["pass_train"] = (t.n_tr >= min_train) & (t.win_tr >= min_win) & (t.avg_tr > 0) & (t.edge_tr > 0)
    t["pass_both"] = t.pass_train & (t.n_va >= min_val) & (t.win_va >= min_win) & (t.avg_va > 0) & (t.edge_va > 0)
    return t, base


if __name__ == "__main__":
    t, base = run()
    pd.set_option("display.width", 250)
    print("Base rate (ETF rose over the period), train / validate / holdout:")
    for h, r in base.items():
        print(f"  {h:2d} days: " + " / ".join(f"{v:.1f}%" for v in r.values()))
    print(f"\n{len(ind.SIGNALS)} signals x 2 directions x {len(HORIZONS)} holding periods = {len(t)} tests")
    print(f"pass train: {int(t.pass_train.sum())}, pass train AND validate: {int(t.pass_both.sum())}\n")
    cols = ["signal", "side", "h", "n_tr", "win_tr", "edge_tr", "n_va", "win_va", "edge_va", "avg_va", "n_ho", "win_ho", "avg_ho"]
    print(t[t.pass_both].sort_values(["win_va"], ascending=False)[cols].round(2).to_string(index=False))
    t.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sweep_results.csv"), index=False)
