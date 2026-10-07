"""Signals-only (paper) runner for the options system in research/system.py.

The scheduled 3:45pm check uses it with live Robinhood data. It never places an order. It records
what the system WOULD do in research/paper_ledger.json.

    python3 research/paper.py signal --bars SPY.json QQQ.json IWM.json --last SPY=779.1,QQQ=759.7,IWM=281.3
    python3 research/paper.py pick --sym QQQ --chain chain.json      # chain: [{id, strike, bid, ask, delta}, ...]
    python3 research/paper.py open --pick pick.json
    python3 research/paper.py mark --short-bid 0.40 --short-ask 0.42 --long-bid 0.20 --long-ask 0.22 [--close]
    python3 research/paper.py status

Fills are recorded two ways:
- "natural" (the conservative fill): sell at the bid and buy at the ask.
- "mid": both legs at the middle of the bid and ask.
"""
import argparse
import datetime as dt
import json
import math
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import indicators as ind  # noqa: E402
import overnight_signal as sig  # noqa: E402

LEDGER = os.path.join(HERE, "paper_ledger.json")
UNIVERSE = ("SPY", "QQQ", "IWM")  # the wider 17-ETF scan (research/universe.py) tested worse
CRSI_MAX, DELTA, DTE, MAX_RISK, FEE = 10.0, 0.30, 21, 250.0, 0.0005


# ---------------------------------------------------------------- data

def load_bars(paths):
    """Robinhood get_equity_historicals JSON -> {symbol: [(date, close), ...]} without placeholder bars."""
    out = {}
    for p in paths:
        d = json.load(open(p))
        for r in d.get("data", d)["results"]:
            rows = [(dt.date.fromisoformat(b["begins_at"][:10]), float(b["close_price"]))
                    for b in r["bars"] if not b.get("interpolated")]
            out.setdefault(r["symbol"], []).extend(rows)
    return {s: sorted(set(v)) for s, v in out.items()}


def next_trading_day(day):
    d = day + dt.timedelta(days=1)
    while d.weekday() > 4 or sig.holiday_tomorrow(d - dt.timedelta(days=1)):
        d += dt.timedelta(days=1)
    return d


def target_expiration(day):
    """The first Friday at least 21 calendar days away."""
    e = day + dt.timedelta(days=DTE)
    while e.weekday() != 4:
        e += dt.timedelta(days=1)
    return e


# ---------------------------------------------------------------- the rules

def signal_table(bars, last, today):
    """Connors RSI and SMA200 with today's live price appended as today's close."""
    rows = []
    for s in UNIVERSE:
        hist = [c for d, c in bars.get(s, []) if d < today]
        if len(hist) < 220 or s not in last:
            rows.append(dict(sym=s, price=last.get(s), crsi=None, sma200=None, qualifies=False,
                             note=f"not enough data ({len(hist)} bars)"))
            continue
        closes = pd.Series(hist + [last[s]], dtype=float)
        crsi = float(ind.connors_rsi(closes).iloc[-1])
        sma200 = float(closes.iloc[-200:].mean())
        q = last[s] > sma200 and crsi < CRSI_MAX
        rows.append(dict(sym=s, price=last[s], crsi=round(crsi, 2), sma200=round(sma200, 2), qualifies=q, note=""))
    return rows


def choose(rows):
    q = [r for r in rows if r["qualifies"]]
    return min(q, key=lambda r: r["crsi"])["sym"] if q else None


def pick_spread(chain):
    """chain: puts of one expiration, [{id, strike, bid, ask, delta}]. Short put: delta closest to -0.30
    (trying the 3 closest if needed). Long put: the widest of $5..$1 below it that is listed and keeps
    the max loss (width - natural credit) x 100 at or below $250."""
    puts = sorted([c for c in chain if c.get("bid") is not None and c.get("ask") is not None and c.get("delta") is not None],
                  key=lambda c: c["strike"])
    by_strike = {round(c["strike"], 2): c for c in puts}
    shorts = sorted([c for c in puts if c["bid"] > 0], key=lambda c: abs(abs(c["delta"]) - DELTA))[:3]
    for sh in shorts:
        for width in (5, 4, 3, 2, 1):
            lg = by_strike.get(round(sh["strike"] - width, 2))
            if lg is None or lg["ask"] <= 0:
                continue
            natural = round(sh["bid"] - lg["ask"] - 2 * FEE, 4)
            mid = round((sh["bid"] + sh["ask"]) / 2 - (lg["bid"] + lg["ask"]) / 2, 4)
            if natural > 0 and (width - natural) * 100 <= MAX_RISK:
                return dict(short_strike=sh["strike"], long_strike=lg["strike"], short_id=sh["id"], long_id=lg["id"],
                            short_delta=sh["delta"], width=width, credit_natural=natural, credit_mid=mid,
                            max_loss=round((width - natural) * 100, 2))
    return None


# ---------------------------------------------------------------- ledger

def load_ledger():
    return json.load(open(LEDGER)) if os.path.exists(LEDGER) else []


def save_ledger(rows):
    json.dump(rows, open(LEDGER, "w"), indent=1, default=str)


def open_position(ledger):
    return next((t for t in ledger if t["status"] == "open"), None)


def must_close_today(t, today):
    return next_trading_day(today) >= dt.date.fromisoformat(t["exp"])


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("signal")
    a.add_argument("--bars", nargs="+", required=True)
    a.add_argument("--last", required=True, help="SPY=779.1,QQQ=759.7,IWM=281.3")
    a.add_argument("--date")
    b = sub.add_parser("pick")
    b.add_argument("--sym", required=True)
    b.add_argument("--chain", required=True)
    b.add_argument("--exp", required=True)
    c = sub.add_parser("open")
    c.add_argument("--pick", required=True)
    c.add_argument("--date")
    m = sub.add_parser("mark")
    for k in ("short-bid", "short-ask", "long-bid", "long-ask"):
        m.add_argument(f"--{k}", type=float, required=True)
    m.add_argument("--close", action="store_true")
    m.add_argument("--date")
    sub.add_parser("status")
    args = ap.parse_args(argv)
    today = dt.date.fromisoformat(args.date) if getattr(args, "date", None) else dt.date.today()
    ledger = load_ledger()
    pos = open_position(ledger)

    if args.cmd == "signal":
        last = {k: float(v) for k, v in (x.split("=") for x in args.last.split(","))}
        rows = signal_table(load_bars(args.bars), last, today)
        for r in rows:
            print(f"{r['sym']}: price {r['price']}  Connors RSI {r['crsi']}  SMA200 {r['sma200']}  "
                  f"qualifies={r['qualifies']} {r['note']}")
        if pos:
            print(f"OPEN PAPER SPREAD: {pos['sym']} {pos['exp']} {pos['short_strike']}/{pos['long_strike']} put, "
                  f"opened {pos['entry_date']}. Close today: {must_close_today(pos, today)}. No new entry.")
        else:
            pick = choose(rows)
            print(f"ENTRY: {pick} -> expiration {target_expiration(today)}" if pick else "ENTRY: none")
    elif args.cmd == "pick":
        p = pick_spread(json.load(open(args.chain)))
        print(json.dumps(dict(p, sym=args.sym, exp=args.exp) if p else None))
    elif args.cmd == "open":
        if pos:
            sys.exit("a paper spread is already open")
        p = json.load(open(args.pick))
        ledger.append(dict(p, status="open", entry_date=today.isoformat()))
        save_ledger(ledger)
        print(f"opened paper spread: {json.dumps(ledger[-1])}")
    elif args.cmd == "mark":
        if not pos:
            sys.exit("no open paper spread")
        debit_nat = args.short_ask - args.long_bid + 2 * FEE
        debit_mid = (args.short_bid + args.short_ask) / 2 - (args.long_bid + args.long_ask) / 2
        pnl_nat = round((pos["credit_natural"] - debit_nat) * 100, 2)
        pnl_mid = round((pos["credit_mid"] - debit_mid) * 100, 2)
        print(f"{pos['sym']} {pos['exp']} {pos['short_strike']}/{pos['long_strike']}: cost to close "
              f"{debit_nat:.2f} natural / {debit_mid:.2f} mid -> P&L ${pnl_nat:+.2f} natural / ${pnl_mid:+.2f} mid")
        if args.close:
            pos.update(status="closed", exit_date=today.isoformat(), debit_natural=round(debit_nat, 4),
                       debit_mid=round(debit_mid, 4), pnl_natural=pnl_nat, pnl_mid=pnl_mid)
            save_ledger(ledger)
            print("closed")
    else:
        done = [t for t in ledger if t["status"] == "closed"]
        wins = sum(1 for t in done if t["pnl_natural"] > 0)
        print(f"{len(done)} closed paper trades, {wins} wins, P&L ${sum(t['pnl_natural'] for t in done):+.2f} natural; "
              f"open: {json.dumps(pos) if pos else 'none'}")


if __name__ == "__main__":
    main()
