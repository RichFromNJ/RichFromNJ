"""Replay the course's earnings iron condor on real 2026 Robinhood option closes.

The course's claim: sell a condor one ATM straddle wide the session before the
report, buy it back the next session, and win about 65% of the time with a
profit factor near 3. This script scores that trade, with the live rules from
earnings_condor.py, on every event file in a data folder.

Data (one JSON per event, saved by the data-fetch workflow of Oct 13, 2026):
  research/data/earnings_condor_2026/events/SYMBOL_REPORTDATE.json
    symbol, report_date, timing, entry_date, reaction_day, expiration,
    entry_close, reaction_close (TradingView daily closes),
    atm_strike, straddle (ATM put close + ATM call close on the entry day),
    instruments: {"puts": [raw get_option_instruments rows], "calls": [...]},
    historicals: [raw get_option_historicals responses for the ATM legs, the
                  short strikes, one strike beyond each, and the wing candidates]

Scoring (earnings_condor.score_event): credit = entry-day closes of the shorts
minus the longs; exit = reaction-day closes; qty = floor($250 / risk);
fees $0.05 per contract per side; slippage half of --slippage per leg per side.
Daily closes are last-trade prices, not quotes, so a real fill is somewhat worse
than the "credit" here; the --slippage stress covers part of that.

    python3 research/earnings_condor_replay.py                  # table + aggregates
    python3 research/earnings_condor_replay.py --dates research/data/earnings_condor_2026/earnings_dates.json \
        --ohlcv research/data/earnings_condor_2026/ohlcv     # adds the "3 of the last 4 moves" history filter
    python3 research/earnings_condor_replay.py --slippage 0.06  # stress the spread
    python3 research/earnings_condor_replay.py --json > out.json
"""
import argparse
import datetime as dt
import glob
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import earnings_condor as ec  # noqa: E402

DATA = os.path.join(HERE, "data", "earnings_condor_2026", "events")


def _date(s):
    return dt.date.fromisoformat(str(s)[:10])


def load_event(path):
    d = json.load(open(path))
    book = {}
    for kind in ("puts", "calls"):
        for i in d["instruments"].get(kind, []):
            book[(i["type"], float(i["strike_price"]))] = i["id"]
    bars = {}
    for h in d["historicals"]:
        data = h.get("data", h)
        for r in data.get("results", []):
            closes = {}
            for b in r.get("bars", []):
                if b.get("interpolated"):
                    continue
                closes[_date(b["begins_at"])] = float(b["close_price"])
            bars.setdefault(r["instrument_id"], {}).update(closes)
    return d, book, bars


def load_closes(ohlcv_dirs):
    """{symbol: {date: close}} from saved TradingView get-ohlcv responses named SYMBOL_*.json."""
    out = {}
    for d in ohlcv_dirs or []:
        for path in sorted(glob.glob(os.path.join(d, "*.json"))):
            sym = os.path.basename(path).split("_")[0].upper()
            raw = json.load(open(path))
            for b in raw.get("bars", []):
                # TradingView stamps a daily bar at the US session open (13:30 UTC), so the UTC date is the session date.
                day = dt.datetime.fromtimestamp(b["t"], tz=dt.timezone.utc).date()
                out.setdefault(sym, {})[day] = float(b["c"])
    return out


def reaction_moves(symbol, before, dates, closes):
    """The absolute post-earnings moves, percent of price, of the reports of `symbol`
    dated before `before`, oldest first: am -> report-day close vs the previous
    close; pm -> next close vs the report-day close. Reports without both closes
    are skipped."""
    series = closes.get(symbol.upper(), {})
    days = sorted(series)
    moves = []
    for rep, timing in dates.get(symbol.upper(), []):
        rd = _date(rep)
        if rd >= before or timing not in ("am", "pm") or rd not in series:
            continue
        i = days.index(rd)
        if timing == "am":
            if i == 0:
                continue
            a, b = series[days[i - 1]], series[rd]
        else:
            if i + 1 >= len(days):
                continue
            a, b = series[rd], series[days[i + 1]]
        moves.append(round(100 * abs(b / a - 1), 4))
    return moves


def replay_event(path, params=ec.Params(), dates=None, closes=None):
    """Rebuild the condor from the saved closes with the live rules: ATM strike
    nearest the entry close, straddle from the ATM closes, shorts one straddle
    away rounded outward, the first width in the ladder whose four legs have
    closes on both days and buys at least one condor. Returns one row."""
    d, book, bars = load_event(path)
    entry, rd = _date(d["entry_date"]), _date(d["reaction_day"])
    price = float(d["entry_close"])
    row = {"symbol": d["symbol"], "report_date": d["report_date"], "timing": d["timing"],
           "entry_date": entry, "reaction_day": rd, "expiration": d.get("expiration"),
           "price": price, "reaction_close": d.get("reaction_close"), "status": "skipped", "note": ""}
    puts = sorted(k for (t, k) in book if t == "put")
    calls = sorted(k for (t, k) in book if t == "call")
    both = sorted(set(puts) & set(calls))
    if not both:
        row["note"] = "no strikes"
        return row
    atm = ec.atm_strike(price, both)

    def close(kind, strike, day):
        iid = book.get((kind, strike))
        if iid is None or iid not in bars or day not in bars[iid]:
            return None
        return bars[iid][day]

    ap, ac = close("put", atm, entry), close("call", atm, entry)
    if ap is None or ac is None:
        row["note"] = f"no ATM closes on {entry} (saved straddle {d.get('straddle')})"
        return row
    straddle = ap + ac
    row.update(atm_strike=atm, straddle=round(straddle, 2),
               implied_move_pct=round(ec.implied_move_pct(straddle, price), 2),
               saved_straddle=d.get("straddle"))
    if dates is not None and closes is not None:
        moves = reaction_moves(d["symbol"], _date(d["report_date"]), dates, closes)
        h = ec.history_filter(moves, row["implied_move_pct"], params)
        row.update(history_moves=moves, history_applied=h["applied"], history_ok=h["ok"], history_note=h["note"])
    sp, sc = ec.short_strikes(price, straddle, puts, calls)
    if sp is None or sc is None:
        row["note"] = "no listed strike one straddle away"
        return row
    row.update(short_put=sp, short_call=sc)
    tried = []
    for w in params.widths:
        lp, lc = round(sp - w, 2), round(sc + w, 2)
        legs = {"short_put": ("put", sp), "long_put": ("put", lp), "short_call": ("call", sc), "long_call": ("call", lc)}
        missing = [n for n, (k, s) in legs.items() if close(k, s, entry) is None or close(k, s, rd) is None]
        if missing:
            tried.append({"width": w, "fail": "no closes for " + ", ".join(missing)})
            continue
        credit = close("put", sp, entry) + close("call", sc, entry) - close("put", lp, entry) - close("call", lc, entry)
        if credit <= 0:
            tried.append({"width": w, "fail": f"credit {credit:.2f} <= 0"})
            continue
        risk = (w - credit) * 100
        qty = math.floor(params.max_loss / risk + 1e-9) if risk > 0 else 0
        roi = credit / (w - credit) if credit < w else math.inf
        if qty < 1:
            tried.append({"width": w, "fail": f"risk ${risk:.0f} > ${params.max_loss:g}", "credit": round(credit, 2), "roi": round(roi, 3)})
            continue
        event = {"symbol": d["symbol"], "entry_date": entry, "reaction_day": rd, "width": w, "qty": qty,
                 "price": price, "reaction_close": d.get("reaction_close"), "straddle": straddle,
                 "legs": {n: book[(k, s)] for n, (k, s) in legs.items()}}
        r = ec.score_event(event, bars, params)
        row.update(status="traded", width=w, long_put=lp, long_call=lc, credit=round(credit, 4), roi=round(roi, 4),
                   risk=round(risk, 2), qty=qty, exit_cost=r["exit_cost"], pnl=r["pnl"], win=r["win"],
                   gross=r["gross"], fees=r["fees"], slippage=r["slippage"], max_loss=round(risk * qty, 2),
                   actual_move_pct=r.get("actual_move_pct"), passes_roi=roi >= params.min_roi - 1e-9,
                   inside_shorts=(sp < float(d["reaction_close"]) < sc) if d.get("reaction_close") is not None else None)
        break
    row["widths_tried"] = tried
    if row["status"] != "traded":
        row["note"] = "no width buys a condor: " + "; ".join(f"${t['width']:g} {t['fail']}" for t in tried)
    return row


def summarize(rows, label):
    traded = [r for r in rows if r["status"] == "traded"]
    agg = ec.aggregate([{"traded": True, "pnl": r["pnl"]} for r in traded])
    agg["label"] = label
    agg["avg_credit_pct_width"] = round(100 * sum(r["credit"] / r["width"] for r in traded) / len(traded), 1) if traded else None
    agg["inside_shorts"] = sum(1 for r in traded if r.get("inside_shorts")) if traded else 0
    return agg


def fmt_agg(a):
    if not a["trades"]:
        return f"{a['label']:34s} no trades"
    lo, hi = a["win_rate_95"]
    pf = a["profit_factor"]
    pf = "inf" if pf == math.inf else (f"{pf:.2f}" if pf is not None else "n/a")
    return (f"{a['label']:34s} n={a['trades']:3d}  win {100 * a['win_rate']:5.1f}% ({100 * lo:.0f}-{100 * hi:.0f})  "
            f"inside shorts {a['inside_shorts']:3d}  avg win {a['avg_win'] or 0:+7.2f}  avg loss {a['avg_loss'] or 0:+8.2f}  "
            f"PF {pf:>5s}  worst {a['worst_loss'] or 0:+8.2f}  total {a['total_pnl']:+9.2f}  credit/width {a['avg_credit_pct_width']}%")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dir", default=DATA)
    p.add_argument("--min-roi", type=float, default=ec.Params.min_roi)
    p.add_argument("--max-loss", type=float, default=ec.Params.max_loss)
    p.add_argument("--slippage", type=float, default=ec.SPREAD_ASSUMED, help="assumed bid-ask per leg; half is paid per side")
    p.add_argument("--dates", help="JSON {symbol: [[report_date, am|pm], ...]} for the history filter")
    p.add_argument("--ohlcv", nargs="*", default=[], help="folders of saved TradingView get-ohlcv responses, SYMBOL_*.json")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    dates = json.load(open(a.dates)) if a.dates else None
    closes = load_closes(a.ohlcv) if a.dates else None
    ec.SPREAD_ASSUMED = a.slippage
    params = ec.Params(max_loss=a.max_loss, min_roi=a.min_roi)
    rows = [replay_event(f, params, dates, closes) for f in sorted(glob.glob(os.path.join(a.dir, "*.json")))]
    traded = [r for r in rows if r["status"] == "traded"]
    aggs = [summarize(rows, "all events with a condor"),
            summarize([r for r in traded if r["passes_roi"]], f"ROI >= {a.min_roi:.0%} (live rule)"),
            summarize([r for r in traded if not r["passes_roi"]], f"ROI < {a.min_roi:.0%} (would be skipped)"),
            summarize([r for r in traded if r["timing"] == "am"], "am reports (enter day before)"),
            summarize([r for r in traded if r["timing"] == "pm"], "pm reports (enter report day)"),
            summarize([r for r in traded if r["width"] <= 1], "$1 wings"),
            summarize([r for r in traded if 1 < r["width"] <= 2.5], "$2-$2.50 wings"),
            summarize([r for r in traded if r["width"] >= 5], "$5 wings")]
    if dates is not None:
        aggs += [summarize([r for r in traded if r.get("history_applied") and r.get("history_ok")], "history filter passed (3 of 4)"),
                 summarize([r for r in traded if r.get("history_applied") and not r.get("history_ok")], "history filter failed"),
                 summarize([r for r in traded if not r.get("history_applied")], "history filter skipped (<4 moves)"),
                 summarize([r for r in traded if r["passes_roi"] and (r.get("history_ok") or not r.get("history_applied"))],
                           "LIVE RULES: ROI >= 35% and history ok/skipped")]
    if a.json:
        print(json.dumps({"rows": rows, "aggregates": aggs, "slippage": a.slippage}, indent=1, default=str))
        return 0
    print(f"{'symbol':6s} {'report':10s} {'tm':2s} {'entry':10s} {'price':>8s} {'strad':>6s} {'imp%':>5s} {'act%':>5s} "
          f"{'shorts':>13s} {'w':>4s} {'credit':>6s} {'roi':>5s} {'qty':>3s} {'exit':>6s} {'pnl':>8s} result")
    for r in rows:
        if r["status"] != "traded":
            print(f"{r['symbol']:6s} {r['report_date']:10s} {r['timing']:2s} {r['entry_date']}  skipped: {r['note'][:90]}")
            continue
        print(f"{r['symbol']:6s} {r['report_date']:10s} {r['timing']:2s} {r['entry_date']} {r['price']:8.2f} {r['straddle']:6.2f} "
              f"{r['implied_move_pct']:5.2f} {r['actual_move_pct'] or 0:5.2f} {r['short_put']:6g}/{r['short_call']:<6g} "
              f"{r['width']:4g} {r['credit']:6.2f} {100 * r['roi']:4.0f}% {r['qty']:3d} {r['exit_cost']:6.2f} {r['pnl']:+8.2f} "
              f"{'WIN ' if r['win'] else 'LOSS'}{'' if r['passes_roi'] else ' (ROI below rule)'}"
              f"{'' if r.get('history_applied') is None else ('  hist ' + ('ok' if r['history_ok'] else 'FAIL') if r['history_applied'] else '  hist skip')}")
    print()
    print(f"slippage assumed {a.slippage:.2f} per leg (half per side); fees $0.05 per contract per side; max loss ${a.max_loss:g}")
    for agg in aggs:
        print(fmt_agg(agg))
    skipped = [r for r in rows if r["status"] != "traded"]
    print(f"\n{len(rows)} events, {len(traded)} traded, {len(skipped)} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
