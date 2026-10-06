#!/usr/bin/env python3
"""Rules-based overnight options signal: RSI(2), ADX/DMI(5) and TRIX(3).

Implements the DATA, INDICATORS, DECISION, EXPIRATION, STRIKE and SIZE
sections of eem-overnight-options-entry.md so every run uses the same tested
math instead of code written on the fly. For STRIKE it lists the two
candidates (nearest OTM and nearest ITM); choosing between them is the one
judgment call the prompt leaves to the routine.

Daily bars are read from the JSON a connector returned, saved to a file:
  - Robinhood get_equity_historicals   ({"data": {"results": [...]}})
  - TradingView get-ohlcv              ({"bars": [{"t", "o", "h", "l", "c"}]})

Usage:
  overnight_signal.py signal --source robinhood --file BARS.json --symbol EEM \
      --date 2026-10-05 --open 68.4669 --high 68.87 --low 68.3584 --last 68.705 \
      [--expirations 2026-10-07,2026-10-09]
  overnight_signal.py strike --signal PUTS --price 68.705 --strikes 68,69,70
  overnight_signal.py size --type ITM --ask 0.62 [--spent 0]
"""

import argparse
import datetime as dt
import json
import math
import sys
from dataclasses import dataclass
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
LOOKBACK = 80           # completed trading days used for the rule indicators
MIN_BARS = 60           # fewer completed bars than this -> NO TRADE
RSI_PERIOD, DMI_PERIOD, TRIX_PERIOD = 2, 5, 3
ADX_MAX, TRIX_LIMIT, RSI_HIGH, RSI_LOW = 60.0, 0.60, 85.0, 15.0
# Daily limits by moneyness: (premium budget, hard cap including fees), dollars.
LIMITS = {"OTM": (130.0, 135.0), "ITM": (245.0, 250.0)}

# NYSE full-day closures, used to find "yesterday's" trading day.
NYSE_HOLIDAYS = {
    dt.date(2026, 1, 1), dt.date(2026, 1, 19), dt.date(2026, 2, 16),
    dt.date(2026, 4, 3), dt.date(2026, 5, 25), dt.date(2026, 6, 19),
    dt.date(2026, 7, 3), dt.date(2026, 9, 7), dt.date(2026, 11, 26),
    dt.date(2026, 12, 25),
    dt.date(2027, 1, 1), dt.date(2027, 1, 18), dt.date(2027, 2, 15),
    dt.date(2027, 3, 26), dt.date(2027, 5, 31), dt.date(2027, 6, 18),
    dt.date(2027, 7, 5), dt.date(2027, 9, 6), dt.date(2027, 11, 25),
    dt.date(2027, 12, 24),
}


class DataError(Exception):
    """The input data fails a check; the prompt says NO TRADE."""


@dataclass
class Bar:
    date: dt.date
    o: float
    h: float
    l: float
    c: float


# ---------------------------------------------------------------- loading

def load_robinhood(path, symbol):
    """Return (bars, dropped) from saved get_equity_historicals output.

    Bars marked interpolated are gap-fill placeholders, not real trading,
    and are dropped.
    """
    with open(path) as f:
        raw = json.load(f)
    results = [r for r in raw["data"]["results"] if r["symbol"].upper() == symbol.upper()]
    if not results:
        raise DataError(f"{symbol} not found in {path}")
    bars, dropped = [], []
    for b in results[0]["bars"]:
        day = dt.date.fromisoformat(b["begins_at"][:10])
        if b.get("interpolated"):
            dropped.append(day)
            continue
        bars.append(Bar(day, float(b["open_price"]), float(b["high_price"]),
                        float(b["low_price"]), float(b["close_price"])))
    return bars, dropped


def load_tradingview(path):
    """Return (bars, dropped) from saved TradingView get-ohlcv output."""
    with open(path) as f:
        raw = json.load(f)
    bars = [Bar(dt.datetime.fromtimestamp(b["t"], tz=ET).date(),
                float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"]))
            for b in raw["bars"]]
    return bars, []


def previous_trading_day(day):
    day -= dt.timedelta(days=1)
    while day.weekday() >= 5 or day in NYSE_HOLIDAYS:
        day -= dt.timedelta(days=1)
    return day


def build_series(history, today):
    """Apply DATA steps 1-4: validate, drop any bar dated today, take the last
    LOOKBACK completed bars and append today's bar."""
    completed = [b for b in history if b.date < today.date]
    for prev, cur in zip(completed, completed[1:]):
        if cur.date <= prev.date:
            raise DataError(f"bars out of order or duplicated at {cur.date}")
    for b in completed + [today]:
        if min(b.o, b.h, b.l, b.c) <= 0:
            raise DataError(f"non-positive price on {b.date}")
        if b.h + 1e-9 < max(b.o, b.c) or b.l - 1e-9 > min(b.o, b.c):
            raise DataError(f"high/low inconsistent with open/close on {b.date}")
    expected = previous_trading_day(today.date)
    if not completed or completed[-1].date != expected:
        last = completed[-1].date if completed else None
        raise DataError(f"yesterday's bar ({expected}) is missing; latest completed bar is {last}")
    completed = completed[-LOOKBACK:]
    if len(completed) < MIN_BARS:
        raise DataError(f"only {len(completed)} completed bars (need {MIN_BARS})")
    return completed + [today]


def todays_bar(date, open_, high, low, last):
    """Today's bar so far. The high/low are widened to include the last price,
    since a session high/low can lag the latest trade by a moment."""
    return Bar(date, open_, max(high, open_, last), min(low, open_, last), last)


# ------------------------------------------------------------- indicators

def wilder(values, n, start):
    """Wilder's smoothing (RMA): seeded with the simple average of
    values[start:start+n], then avg = (prev * (n - 1) + x) / n."""
    out = [None] * len(values)
    if len(values) < start + n:
        return out
    out[start + n - 1] = sum(values[start:start + n]) / n
    for i in range(start + n, len(values)):
        out[i] = (out[i - 1] * (n - 1) + values[i]) / n
    return out


def ema(values, n):
    a = 2 / (n + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(out[-1] + a * (v - out[-1]))
    return out


def rsi(closes, n=RSI_PERIOD):
    gains = [0.0] + [max(closes[i] - closes[i - 1], 0.0) for i in range(1, len(closes))]
    losses = [0.0] + [max(closes[i - 1] - closes[i], 0.0) for i in range(1, len(closes))]
    ag, al = wilder(gains, n, 1), wilder(losses, n, 1)
    out = []
    for g, l in zip(ag, al):
        if g is None:
            out.append(None)
        else:
            out.append(100.0 if l == 0 else 100 - 100 / (1 + g / l))
    return out


def dmi(bars, n=DMI_PERIOD):
    """Wilder ADX, +DI, -DI with period n for both DI and ADX smoothing."""
    tr, pdm, mdm = [0.0], [0.0], [0.0]
    for prev, cur in zip(bars, bars[1:]):
        tr.append(max(cur.h - cur.l, abs(cur.h - prev.c), abs(cur.l - prev.c)))
        up, down = cur.h - prev.h, prev.l - cur.l
        pdm.append(up if up > down and up > 0 else 0.0)
        mdm.append(down if down > up and down > 0 else 0.0)
    atr, pav, mav = wilder(tr, n, 1), wilder(pdm, n, 1), wilder(mdm, n, 1)
    plus, minus, dx = [None] * len(bars), [None] * len(bars), [None] * len(bars)
    for i in range(len(bars)):
        if atr[i]:
            plus[i] = 100 * pav[i] / atr[i]
            minus[i] = 100 * mav[i] / atr[i]
            total = plus[i] + minus[i]
            dx[i] = 0.0 if total == 0 else 100 * abs(plus[i] - minus[i]) / total
    adx = wilder(dx, n, n)
    return adx, plus, minus


def trix(closes, n=TRIX_PERIOD):
    """Prompt definition: 100 x (triple EMA today / yesterday - 1), a percent."""
    t = ema(ema(ema(closes, n), n), n)
    return [None] + [100 * (t[i] / t[i - 1] - 1) for i in range(1, len(t))]


def trix_tradingview(closes, n=TRIX_PERIOD):
    """TradingView's built-in scale: 10000 x change in triple EMA of log(close)."""
    t = ema(ema(ema([math.log(c) for c in closes], n), n), n)
    return [None] + [10000 * (t[i] - t[i - 1]) for i in range(1, len(t))]


def adx_position(adx, plus, minus):
    if adx > max(plus, minus):
        return "above both"
    if adx < min(plus, minus):
        return "below both"
    if min(plus, minus) < adx < max(plus, minus):
        return "between"
    return "on a DI line"


def context_levels(history, today):
    """Chart levels that the rules don't use: Bollinger Bands, EMAs, SMA 200.
    Computed on the full history so the long averages are fully warmed up."""
    closes = [b.c for b in history if b.date < today.date] + [today.c]
    out = {}
    if len(closes) >= 20:
        window = closes[-20:]
        mid = sum(window) / 20
        sd = math.sqrt(sum((c - mid) ** 2 for c in window) / 20)
        out.update(bb_mid=mid, bb2_low=mid - 2 * sd, bb2_high=mid + 2 * sd,
                   bb3_low=mid - 3 * sd, bb3_high=mid + 3 * sd)
    for n in (13, 48, 20, 50):
        if len(closes) >= 3 * n:
            out[f"ema{n}"] = ema(closes, n)[-1]
    if len(closes) >= 200:
        out["sma200"] = sum(closes[-200:]) / 200
    return out


# ---------------------------------------------------------------- decision

def decide(series):
    """DECISION rules 1-5. Returns a dict with every reported value."""
    closes = [b.c for b in series]
    r = rsi(closes)
    adx, plus, minus = dmi(series)
    tx = trix(closes)
    tx_tv = trix_tradingview(closes)
    today, yday = len(series) - 1, len(series) - 2
    v = {
        "date": series[today].date.isoformat(),
        "price": closes[today], "open": series[today].o,
        "high": series[today].h, "low": series[today].l,
        "rsi2": r[today], "adx": adx[today], "plus_di": plus[today], "minus_di": minus[today],
        "y_adx": adx[yday], "y_plus_di": plus[yday], "y_minus_di": minus[yday],
        "trix": tx[today], "trix_tradingview_scale": tx_tv[today],
        "bars_used": len(series) - 1,
    }
    v["position"] = adx_position(v["adx"], v["plus_di"], v["minus_di"])
    v["y_position"] = adx_position(v["y_adx"], v["y_plus_di"], v["y_minus_di"])

    if v["adx"] > ADX_MAX:
        signal, rule = "NO TRADE", f"Rule 1: ADX {v['adx']:.2f} > {ADX_MAX:g}"
    elif v["trix"] > TRIX_LIMIT:
        signal, rule = "PUTS", f"Rule 2: TRIX {v['trix']:.4f} > {TRIX_LIMIT}"
    elif v["trix"] < -TRIX_LIMIT:
        signal, rule = "CALLS", f"Rule 2: TRIX {v['trix']:.4f} < -{TRIX_LIMIT}"
    elif v["y_position"] == "above both" and v["position"] == "between":
        signal, rule = "CALLS", "Rule 3: ADX stab down into the DI zone"
    elif v["y_position"] == "below both" and v["position"] == "between":
        signal, rule = "PUTS", "Rule 3: ADX stab up into the DI zone"
    elif v["rsi2"] >= RSI_HIGH:
        signal, rule = "PUTS", f"Rule 4: RSI(2) {v['rsi2']:.2f} >= {RSI_HIGH:g}"
    elif v["rsi2"] <= RSI_LOW:
        signal, rule = "CALLS", f"Rule 4: RSI(2) {v['rsi2']:.2f} <= {RSI_LOW:g}"
    elif v["price"] > v["open"]:
        signal, rule = "CALLS", "Rule 5: price above today's open"
    elif v["price"] < v["open"]:
        signal, rule = "PUTS", "Rule 5: price below today's open"
    else:
        signal, rule = "NO TRADE", "Rule 5: price equals today's open"
    v["signal"], v["rule"] = signal, rule
    return v


def choose_expiration(today, expirations):
    """Mon/Tue -> this week's Wednesday, Wed/Thu -> this week's Friday.
    Falls back to the next listed date within 3 calendar days of the target.
    Returns (date, "target" | "fallback") or None for NO TRADE."""
    wd = today.weekday()
    if wd > 3:
        return None
    target = today + dt.timedelta(days=(2 if wd <= 1 else 4) - wd)
    listed = sorted(e for e in expirations if e > today)
    if target in listed:
        return target, "target"
    later = [e for e in listed if target < e <= target + dt.timedelta(days=3)]
    return (later[0], "fallback") if later else None


def moneyness(signal, strike, price):
    """STRIKE definitions: calls are OTM above the price, puts are OTM below
    it. A strike exactly at the price counts as ITM."""
    if signal == "CALLS":
        return "OTM" if strike > price else "ITM"
    return "OTM" if strike < price else "ITM"


def strike_candidates(signal, price, strikes):
    """STRIKE step 2: the nearest OTM and nearest ITM strikes (None if absent)."""
    strikes = sorted(set(strikes))
    otm = [s for s in strikes if moneyness(signal, s, price) == "OTM"]
    itm = [s for s in strikes if moneyness(signal, s, price) == "ITM"]
    if signal == "CALLS":
        return {"OTM": otm[0] if otm else None, "ITM": itm[-1] if itm else None}
    return {"OTM": otm[-1] if otm else None, "ITM": itm[0] if itm else None}


def quantity(ask, kind, spent=0.0):
    """SIZE: contracts the remaining OTM or ITM premium budget buys at `ask`.
    Zero also means the candidate is removed in STRIKE step 3."""
    budget = LIMITS[kind][0] - spent
    if ask <= 0 or budget <= 0:
        return 0
    return math.floor(budget / (ask * 100) + 1e-9)


# --------------------------------------------------------------------- CLI

def _fmt(v, nd=2):
    return "n/a" if v is None else f"{v:.{nd}f}"


def run_signal(args):
    today_date = dt.date.fromisoformat(args.date)
    if args.source == "robinhood":
        history, dropped = load_robinhood(args.file, args.symbol)
    else:
        history, dropped = load_tradingview(args.file)
    today = todays_bar(today_date, args.open, args.high, args.low, args.last)
    out = {"symbol": args.symbol.upper(), "source": args.source,
           "dropped_interpolated": [d.isoformat() for d in dropped[-5:]]}
    try:
        if today_date.weekday() > 3:
            raise DataError("today is not Mon-Thu")
        series = build_series(history, today)
        out.update(decide(series))
        out["context"] = context_levels(history, today)
        if args.expirations and out["signal"] != "NO TRADE":
            exps = [dt.date.fromisoformat(e) for e in args.expirations.split(",")]
            pick = choose_expiration(today_date, exps)
            out["expiration"] = (pick[0].isoformat(), pick[1]) if pick else None
    except DataError as e:
        out.update(signal="NO TRADE", rule=f"Data check failed: {e}")
    if args.json:
        print(json.dumps(out, indent=2, default=str))
        return
    s = out
    print(f"{s['symbol']} via {s['source']} on {args.date}: {s['signal']}  ({s['rule']})")
    if "rsi2" in s:
        print(f"  price {s['price']:.4f}  open {s['open']:.4f}  high {s['high']:.4f}  low {s['low']:.4f}  ({s['bars_used']} completed bars)")
        print(f"  RSI(2) {_fmt(s['rsi2'])}  ADX {_fmt(s['adx'])}  +DI {_fmt(s['plus_di'])}  -DI {_fmt(s['minus_di'])}  -> ADX {s['position']}")
        print(f"  yesterday: ADX {_fmt(s['y_adx'])}  +DI {_fmt(s['y_plus_di'])}  -DI {_fmt(s['y_minus_di'])}  -> ADX {s['y_position']}")
        print(f"  TRIX(3) {s['trix']:.4f}%  (TradingView scale {s['trix_tradingview_scale']:.1f})")
        c = s["context"]
        if c:
            print("  context: " + "  ".join(f"{k} {v:.2f}" for k, v in c.items()))
        if "expiration" in s:
            print(f"  expiration: {s['expiration']}")
    if s["dropped_interpolated"]:
        print(f"  dropped placeholder bars: {', '.join(s['dropped_interpolated'])}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("signal")
    s.add_argument("--source", choices=["robinhood", "tradingview"], required=True)
    s.add_argument("--file", required=True)
    s.add_argument("--symbol", required=True)
    s.add_argument("--date", required=True)
    for k in ("open", "high", "low", "last"):
        s.add_argument(f"--{k}", type=float, required=True)
    s.add_argument("--expirations", help="comma-separated YYYY-MM-DD listed expirations")
    s.add_argument("--json", action="store_true")
    k = sub.add_parser("strike")
    k.add_argument("--signal", choices=["CALLS", "PUTS"], required=True)
    k.add_argument("--price", type=float, required=True)
    k.add_argument("--strikes", required=True, help="comma-separated strikes")
    z = sub.add_parser("size")
    z.add_argument("--type", choices=["OTM", "ITM"], required=True)
    z.add_argument("--ask", type=float, required=True)
    z.add_argument("--spent", type=float, default=0.0, help="premium already spent today on this type")
    args = p.parse_args(argv)
    if args.cmd == "signal":
        run_signal(args)
    elif args.cmd == "strike":
        cands = strike_candidates(args.signal, args.price, [float(x) for x in args.strikes.split(",")])
        for kind, strike in cands.items():
            if strike is None:
                print(f"{kind}: none listed")
            else:
                print(f"{kind}: strike {strike:g}  ({abs(strike - args.price):.2f} from the price)")
    else:
        budget, cap = LIMITS[args.type]
        print(f"quantity {quantity(args.ask, args.type, args.spent)}  "
              f"({args.type} budget ${budget:g}, cap ${cap:g}, spent ${args.spent:g})")


if __name__ == "__main__":
    sys.exit(main())
