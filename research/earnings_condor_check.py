#!/usr/bin/env python3
"""Check the course's earnings iron condor claim on REAL Robinhood option prices.

The course sold a four-leg iron condor on the last session before a report, with the short
strikes one at-the-money straddle away from the price and $1 (or $2, $2.50, $5) wings, sized to
a $250 maximum loss, and bought it back the next session. This script re-prices that trade at
the daily closes Robinhood reports for the expired contracts, the same way
research/robinhood_check.py re-prices the credit spreads.

Every connector response is saved as-is, one JSON per call, in BARS_DIR
(default research/data/earnings_condors/): instruments and underlying bars in BARS_DIR itself,
the get_option_historicals responses in BARS_DIR/historicals/. Both subcommands read both
folders; the module's own scorer (earnings_condor.py score --bars BARS_DIR/historicals) reads
only the historicals folder, since it treats every *.json there as option bars.

Step 1  python3 research/earnings_condor_check.py contracts --events EVENTS.json [--bars BARS_DIR]
        EVENTS.json is a list of past reports, for example
          [{"symbol": "MS", "report_date": "2026-07-16", "timing": "am"}, ...]
        An event may also carry "expiration" (YYYY-MM-DD) to override the guessed expiration
        (the first Friday on or after the reaction day, or the Thursday before it when that
        Friday is an NYSE holiday) and "price" to override the entry-day close.
        For each event it prints the entry day (the last session before the reaction day), the
        reaction day, the expiration and the entry-day and reaction-day closes of the
        underlying, read from research/data/<EXCHANGE>_<SYMBOL>_1D.csv when present, else from
        an underlying JSON saved in BARS_DIR (Robinhood get_equity_historicals output, or
        TradingView get-ohlcv output whose "symbol" ends in the ticker). Then it prints what to
        fetch next, in three rounds; each round appears only once the previous round's files
        are in BARS_DIR:
          round 1  get_option_instruments chain_symbol=SYMBOL expiration_dates=EXPIRATION
                   state=expired type=put, and again with type=call. Save both responses.
          round 2  the ATM put and call (the listed strike nearest the entry close, tie -> the
                   lower strike): get_option_historicals instrument_ids=[...] interval=day
                   start_time=<entry day - 7 days>T00:00:00Z end_time=<reaction day + 1>T00:00:00Z.
                   Save each response in BARS_DIR/historicals/.
          round 3  the straddle is the sum of the ATM legs' entry-day closes. The short put is
                   the highest listed strike <= close - straddle, the short call the lowest
                   listed strike >= close + straddle, and the wings sit one width outside them
                   for every listed width among $1, $2, $2.50 and $5. It prints every one of
                   those legs whose bars are still missing, with the same historicals call.
        Repeat `contracts` after each round until it prints "nothing left to fetch".

Step 2  python3 research/earnings_condor_check.py score --events EVENTS.json [--bars BARS_DIR]
        For each event with complete bars it builds the condor at the entry-day closes, takes
        the first width (in the order $1, $2, $2.50, $5) whose ROI = credit / (width - credit)
        is at least Params().min_roi and whose quantity floor(max_loss / risk) is at least 1,
        and hands it to earnings_condor.score_event, which charges $0.05 per contract per side
        in fees and half a $0.02 spread per leg per side. Then it prints one line per event and
        earnings_condor.aggregate's table: trades, win rate with a Wilson 95% interval, average
        win, average loss, profit factor and worst loss.

        With --write-events PATH it also saves the built events (legs, width, qty, price,
        reaction close and the straddle legs' ids) so the module's own scorer reproduces the
        table: python3 earnings_condor.py score --events PATH --bars BARS_DIR/historicals
        Keep PATH outside the historicals folder: the module reads every *.json there as bars.

Module names used (public only): Params, reaction_day(report_date, timing), score_event(event,
bars) and aggregate(results). `event` carries symbol, entry_date, reaction_day, width, qty, price
(the entry close), reaction_close, "legs" = {short_put, long_put, short_call, long_call: instrument
id} and "straddle" = {"put": id, "call": id}; `bars` maps an instrument id to {date: close} with
interpolated bars dropped. This script stays import-light: json, os, csv and the module.
"""
import argparse
import csv
import datetime as dt
import glob
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import overnight_signal as sig  # noqa: E402  (NYSE_HOLIDAYS, previous_trading_day)
import earnings_condor as ec  # noqa: E402  (Params, reaction_day, score_event, aggregate)

DEFAULT_BARS = os.path.join(HERE, "data", "earnings_condors")
LEGS = ("short_put", "long_put", "short_call", "long_call")


# ---------------------------------------------------------------- helpers

def params():
    p = ec.Params()
    return p


def widths(p):
    return tuple(getattr(p, "widths", (1.0, 2.0, 2.5, 5.0)))


def to_date(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    return dt.date.fromisoformat(str(v)[:10])


def reaction_day(report_date, timing):
    """Call the module's reaction_day with a date, falling back to an ISO string."""
    try:
        return to_date(ec.reaction_day(report_date, timing))
    except TypeError:
        return to_date(ec.reaction_day(report_date.isoformat(), timing))


def guess_expiration(rd):
    """First Friday on or after the reaction day; the Thursday before it when that Friday is
    a full-day NYSE holiday (Good Friday). Events may override this with "expiration"."""
    friday = rd + dt.timedelta(days=(4 - rd.weekday()) % 7)
    if friday in sig.NYSE_HOLIDAYS:
        return friday - dt.timedelta(days=1)
    return friday


def next_trading_day(day):
    day += dt.timedelta(days=1)
    while day.weekday() >= 5 or day in sig.NYSE_HOLIDAYS:
        day += dt.timedelta(days=1)
    return day


def load_events(path):
    with open(path) as f:
        raw = json.load(f)
    if isinstance(raw, dict):
        raw = raw.get("events", raw.get("data", raw))
    events = []
    for e in raw:
        timing = e.get("timing")
        if timing not in ("am", "pm"):
            print(f"skip {e.get('symbol')}: timing must be am or pm", file=sys.stderr)
            continue
        report = to_date(e["report_date"])
        rd = reaction_day(report, timing)
        events.append(dict(
            symbol=e["symbol"].upper(), report_date=report, timing=timing, reaction_day=rd,
            entry_date=sig.previous_trading_day(rd),
            expiration=to_date(e["expiration"]) if e.get("expiration") else guess_expiration(rd),
            price=float(e["price"]) if e.get("price") is not None else None,
        ))
    return events


# ---------------------------------------------------------------- data in BARS_DIR

def _json_files(bars_dir):
    """Every saved response in BARS_DIR and BARS_DIR/historicals/."""
    for f in sorted(glob.glob(os.path.join(bars_dir, "*.json")) + glob.glob(os.path.join(bars_dir, "historicals", "*.json"))):
        try:
            with open(f) as fh:
                yield f, json.load(fh)
        except (OSError, ValueError) as e:
            print(f"skip {f}: {e}", file=sys.stderr)


def underlying_closes(symbol, bars_dir):
    """{date: close} for the underlying, from research/data/*_SYMBOL_1D.csv or a saved
    equity-historicals / get-ohlcv JSON in BARS_DIR."""
    out = {}
    for f in glob.glob(os.path.join(HERE, "data", f"*_{symbol}_1D.csv")):
        with open(f) as fh:
            for r in csv.DictReader(fh):
                out[dt.date.fromisoformat(r["et"][:10])] = float(r["c"])
    if out:
        return out
    for f, d in _json_files(bars_dir):
        data = d.get("data", d) if isinstance(d, dict) else {}
        for res in data.get("results", []):              # Robinhood get_equity_historicals
            if res.get("symbol", "").upper() == symbol and "instrument_id" not in res:
                for b in res.get("bars", []):
                    if not b.get("interpolated"):
                        out[dt.date.fromisoformat(b["begins_at"][:10])] = float(b["close_price"])
        tv = d.get("symbol", "") if isinstance(d, dict) else ""
        if tv.upper().endswith(":" + symbol) or tv.upper() == symbol:   # TradingView get-ohlcv
            for b in d.get("bars", []):
                out[dt.datetime.fromtimestamp(b["t"], tz=sig.ET).date()] = float(b["c"])
    return out


def load_instruments(bars_dir):
    """{(symbol, expiration, type): {strike: instrument id}} from saved get_option_instruments."""
    out = {}
    for _, d in _json_files(bars_dir):
        data = d.get("data", d) if isinstance(d, dict) else {}
        for ins in data.get("instruments", []):
            key = (ins["chain_symbol"].upper(), to_date(ins["expiration_date"]), ins["type"])
            out.setdefault(key, {})[float(ins["strike_price"])] = ins["id"]
    return out


def load_option_bars(bars_dir):
    """{instrument id: [raw daily bars, interpolated dropped]} from saved get_option_historicals."""
    out = {}
    for _, d in _json_files(bars_dir):
        data = d.get("data", d) if isinstance(d, dict) else {}
        for res in data.get("results", []):
            if "instrument_id" not in res:
                continue
            bars = [b for b in res.get("bars", []) if not b.get("interpolated")]
            out.setdefault(res["instrument_id"], []).extend(bars)
    return out


def close_on(bars, day):
    for b in bars:
        if b["begins_at"][:10] == day.isoformat():
            return float(b["close_price"])
    return None


def series(bars):
    """Raw daily bars -> {date: close}, the shape score_event indexes."""
    return {dt.date.fromisoformat(b["begins_at"][:10]): float(b["close_price"]) for b in bars}


def atm_strike(strikes, price):
    """Listed strike nearest the price; a tie goes to the lower strike."""
    return min(sorted(strikes), key=lambda k: (abs(k - price), k))


def shorts(put_strikes, call_strikes, price, straddle):
    puts = [k for k in put_strikes if k <= price - straddle]
    calls = [k for k in call_strikes if k >= price + straddle]
    return (max(puts) if puts else None), (min(calls) if calls else None)


# ---------------------------------------------------------------- contracts

def historicals_hint(ids, ev):
    start = (ev["entry_date"] - dt.timedelta(days=7)).isoformat()
    end = (ev["reaction_day"] + dt.timedelta(days=1)).isoformat()
    return (f"get_option_historicals instrument_ids={json.dumps(ids)} interval=day "
            f"start_time={start}T00:00:00Z end_time={end}T00:00:00Z  -> save in BARS_DIR/historicals/")


def contracts(events, bars_dir):
    instruments, bars = load_instruments(bars_dir), load_option_bars(bars_dir)
    todo = 0
    for ev in events:
        sym, exp = ev["symbol"], ev["expiration"]
        closes = underlying_closes(sym, bars_dir)
        price = ev["price"] if ev["price"] is not None else closes.get(ev["entry_date"])
        rclose = closes.get(ev["reaction_day"])
        print(f"\n{sym}  report {ev['report_date']} {ev['timing']}  entry {ev['entry_date']}  "
              f"reaction {ev['reaction_day']}  expiration {exp}  "
              f"entry close {price if price is not None else 'MISSING'}  "
              f"reaction close {rclose if rclose is not None else 'MISSING'}")
        if price is None:
            print(f"  FETCH underlying daily bars for {sym} (research/data/<EXCH>_{sym}_1D.csv "
                  f"or save get_equity_historicals / get-ohlcv output in {bars_dir})")
            todo += 1
            continue
        puts, calls = instruments.get((sym, exp, "put")), instruments.get((sym, exp, "call"))
        if not puts or not calls:
            print(f"  FETCH round 1: get_option_instruments chain_symbol={sym} expiration_dates={exp} "
                  f"state=expired type=put  and  type=call  -> save both in {bars_dir}/")
            todo += 1
            continue
        atm = atm_strike(set(puts) & set(calls), price)
        atm_ids = {"atm_put": puts[atm], "atm_call": calls[atm]}
        missing = [i for i in atm_ids.values() if close_on(bars.get(i, []), ev["entry_date"]) is None]
        if missing:
            print(f"  ATM strike {atm:g}; FETCH round 2: {historicals_hint(missing, ev)}")
            todo += 1
            continue
        straddle = close_on(bars[atm_ids["atm_put"]], ev["entry_date"]) + close_on(bars[atm_ids["atm_call"]], ev["entry_date"])
        sp, sc = shorts(puts, calls, price, straddle)
        print(f"  ATM {atm:g}  straddle {straddle:.2f}  implied move {100 * straddle / price:.2f}%  "
              f"short put {sp}  short call {sc}")
        if sp is None or sc is None:
            print("  no listed short strike one straddle away; event cannot be scored")
            continue
        need = {}
        for w in widths(params()):
            if sp - w in puts and sc + w in calls:
                need.update({puts[sp]: f"{sp:g}P", puts[sp - w]: f"{sp - w:g}P",
                             calls[sc]: f"{sc:g}C", calls[sc + w]: f"{sc + w:g}C"})
        if not need:
            print("  no listed wings at any width; event cannot be scored")
            continue
        missing = [i for i in need if close_on(bars.get(i, []), ev["entry_date"]) is None
                   or close_on(bars.get(i, []), ev["reaction_day"]) is None]
        if missing:
            print(f"  legs {' '.join(need[i] for i in missing)}; FETCH round 3: {historicals_hint(missing, ev)}")
            todo += 1
        else:
            print("  all legs saved; ready to score")
    print(f"\n{todo} event(s) still need data" if todo else "\nnothing left to fetch")


# ---------------------------------------------------------------- score

def build_event(ev, price, rclose, puts, calls, bars, p):
    """The first width that passes ROI and sizing at the entry-day closes, or (None, reasons)."""
    atm = atm_strike(set(puts) & set(calls), price)
    ap, ac = bars.get(puts[atm], []), bars.get(calls[atm], [])
    ap_c, ac_c = close_on(ap, ev["entry_date"]), close_on(ac, ev["entry_date"])
    if ap_c is None or ac_c is None:
        return None, ["ATM bars missing"]
    straddle = ap_c + ac_c
    sp, sc = shorts(puts, calls, price, straddle)
    if sp is None or sc is None:
        return None, ["no short strike one straddle away"]
    reasons = []
    for w in widths(p):
        if sp - w not in puts or sc + w not in calls:
            reasons.append(f"${w:g}: wing not listed")
            continue
        ids = {"short_put": puts[sp], "long_put": puts[sp - w], "short_call": calls[sc], "long_call": calls[sc + w]}
        entry = {k: close_on(bars.get(i, []), ev["entry_date"]) for k, i in ids.items()}
        exit_ = {k: close_on(bars.get(i, []), ev["reaction_day"]) for k, i in ids.items()}
        if None in entry.values() or None in exit_.values():
            reasons.append(f"${w:g}: bars missing")
            continue
        credit = entry["short_put"] + entry["short_call"] - entry["long_put"] - entry["long_call"]
        if credit <= 0 or credit >= w:
            reasons.append(f"${w:g}: credit {credit:.2f} unusable")
            continue
        roi = credit / (w - credit)
        if roi < p.min_roi:
            reasons.append(f"${w:g}: ROI {roi:.2f} < {p.min_roi:g}")
            continue
        qty = math.floor(p.max_loss / ((w - credit) * 100) + 1e-9)
        if qty < 1:
            reasons.append(f"${w:g}: risk {(w - credit) * 100:.0f} > max loss")
            continue
        event = dict(symbol=ev["symbol"], report_date=ev["report_date"].isoformat(), timing=ev["timing"],
                     entry_date=ev["entry_date"].isoformat(), reaction_day=ev["reaction_day"].isoformat(),
                     expiration=ev["expiration"].isoformat(), price=price, reaction_close=rclose,
                     atm_strike=atm, straddle_price=straddle, implied_move_pct=100 * straddle / price,
                     short_put=sp, long_put=sp - w, short_call=sc, long_call=sc + w, width=w, qty=qty,
                     credit=credit, roi=roi, legs=ids, straddle={"put": puts[atm], "call": calls[atm]})
        leg_bars = {i: series(bars[i]) for i in ids.values()}
        leg_bars[puts[atm]], leg_bars[calls[atm]] = series(ap), series(ac)
        return (event, leg_bars), reasons
    return None, reasons


def score(events, bars_dir, write_events=None):
    p = params()
    instruments, bars = load_instruments(bars_dir), load_option_bars(bars_dir)
    results, built_events = [], []
    for ev in events:
        sym, exp = ev["symbol"], ev["expiration"]
        closes = underlying_closes(sym, bars_dir)
        price = ev["price"] if ev["price"] is not None else closes.get(ev["entry_date"])
        rclose = closes.get(ev["reaction_day"])
        puts, calls = instruments.get((sym, exp, "put")), instruments.get((sym, exp, "call"))
        if price is None or not puts or not calls:
            print(f"{sym} {ev['report_date']}: missing entry close or instruments (run `contracts`)")
            continue
        built, reasons = build_event(ev, price, rclose, puts, calls, bars, p)
        if built is None:
            print(f"{sym} {ev['report_date']}: not tradable  ({'; '.join(reasons)})")
            continue
        event, leg_bars = built
        try:
            r = ec.score_event(event, leg_bars)
        except Exception as e:  # the module's interface may differ; keep scoring the rest
            print(f"{sym} {ev['report_date']}: score_event failed: {e!r}")
            continue
        results.append(r)
        built_events.append(event)
        pnl = r.get("pnl")
        move = "n/a" if rclose is None else f"{100 * (rclose / price - 1):+.2f}%"
        print(f"{sym} {ev['report_date']} {ev['timing']}: ${event['width']:g} wings "
              f"{event['short_put']:g}/{event['short_call']:g}  credit {event['credit']:.2f}  "
              f"ROI {event['roi']:.2f}  qty {event['qty']}  implied {event['implied_move_pct']:.2f}%  "
              f"move {move}  pnl {pnl if pnl is None else f'{pnl:+.2f}'}  {'WIN' if r.get('win') else 'LOSS'}")
    if write_events:
        with open(write_events, "w") as f:
            json.dump(built_events, f, indent=1)
        print(f"\nwrote {len(built_events)} event(s) to {write_events}")
    if not results:
        print("\nno scored events")
        return
    agg = ec.aggregate(results)
    print("\naggregate:")
    if isinstance(agg, dict):
        for k, v in agg.items():
            print(f"  {k}: {v}")
    else:
        print(f"  {agg}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("contracts", "score"):
        s = sub.add_parser(name)
        s.add_argument("--events", required=True, help="JSON list of {symbol, report_date, timing[, expiration, price]}")
        s.add_argument("--bars", default=DEFAULT_BARS, help=f"folder of saved Robinhood responses (default {DEFAULT_BARS})")
    sub.choices["score"].add_argument("--write-events", help="save the built events for `earnings_condor.py score`")
    args = ap.parse_args(argv)
    events = load_events(args.events)
    if args.cmd == "contracts":
        contracts(events, args.bars)
    else:
        score(events, args.bars, args.write_events)


if __name__ == "__main__":
    main()
