"""Re-price the 2026 spread trades with REAL Robinhood option prices.

Step 1  python3 research/robinhood_check.py contracts
        prints every option leg the 2026 trades need (symbol, expiration, strike, type, dates).
Step 2  those legs' daily bars are pulled from Robinhood (get_option_instruments with
        state=expired, then get_option_historicals, interval=day) and saved, one JSON per
        call, in research/data/robinhood_options/.
Step 3  python3 research/robinhood_check.py score
        re-prices each trade at the real daily closes (Robinhood's marks), charges the same
        bid-ask spread and fees as the model, and compares the result with the model.
"""
import glob
import json
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import spreads as sp  # noqa: E402
import system  # noqa: E402

RAW = os.path.join(HERE, "data", "robinhood_options")


def legs_needed(trades):
    rows = []
    for t in trades.itertuples():
        long_k, short_k, call = t.legs
        for k in (long_k, short_k):
            rows.append(dict(sym=t.sym, exp=t.exp, strike=float(k), type="call" if call else "put",
                             start=t.entry_date, end=t.exit_date))
    return pd.DataFrame(rows).drop_duplicates(["sym", "exp", "strike", "type"])


def load_bars():
    """{(sym, exp, strike, type): {date: close}} from the saved Robinhood responses."""
    ids, bars = {}, {}
    for f in glob.glob(os.path.join(RAW, "*.json")):
        d = json.load(open(f))
        data = d.get("data", d)
        for ins in data.get("instruments", []):
            ids[ins["id"]] = (ins["chain_symbol"], ins["expiration_date"], float(ins["strike_price"]), ins["type"])
        for res in data.get("results", []):
            key = res["instrument_id"]
            series = {}
            for b in res.get("bars", []):
                if b.get("interpolated"):
                    continue
                series[b["begins_at"][:10]] = float(b["close_price"])
            bars.setdefault(key, {}).update(series)
    out = {}
    for iid, key in ids.items():
        if iid in bars:
            out[key] = bars[iid]
    return out


def score(trades, bars):
    rows = []
    for t in trades.itertuples():
        long_k, short_k, call = t.legs
        kind = "call" if call else "put"
        exp = t.exp.isoformat()
        lk, sk = (t.sym, exp, float(long_k), kind), (t.sym, exp, float(short_k), kind)
        if lk not in bars or sk not in bars:
            rows.append(dict(sym=t.sym, entry_date=t.entry_date, missing=True))
            continue
        d0, d1 = t.entry_date.isoformat(), t.exit_date.isoformat()
        try:
            mid0 = bars[lk][d0] - bars[sk][d0]
            mid1 = bars[lk][d1] - bars[sk][d1]
        except KeyError:
            rows.append(dict(sym=t.sym, entry_date=t.entry_date, missing=True))
            continue
        hs = sp.HALF_SPREAD[t.sym]
        cost = 2 * hs + 2 * sp.FEE
        if t.kind == "put_credit":
            entry = -mid0 - cost
            exit_ = mid1 - (0 if t.exit_date >= t.exp else cost)
            pnl = entry + exit_
        else:
            entry = mid0 + cost
            exit_ = mid1 - (0 if t.exit_date >= t.exp else cost)
            pnl = exit_ - entry
        rows.append(dict(sym=t.sym, entry_date=t.entry_date, exit_date=t.exit_date, legs=t.legs,
                         real_entry=round(entry, 3), model_entry=round(t.entry, 3),
                         real_pnl=round(pnl * 100, 2), model_pnl=round(t.pnl, 2), missing=False))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    variant = sys.argv[2] if len(sys.argv) > 2 else "A"
    trades = system.trades_2026(variant)
    if sys.argv[1:2] == ["contracts"]:
        print(legs_needed(trades).to_string(index=False))
    else:
        r = score(trades, load_bars())
        print(r.to_string(index=False))
        ok = r[~r.missing]
        if len(ok):
            w = (ok.real_pnl > 0).mean() * 100
            print(f"\nreal Robinhood prices: {len(ok)} trades, win {w:.1f}%, total ${ok.real_pnl.sum():+.0f}, "
                  f"avg ${ok.real_pnl.mean():+.1f}  |  model: win {(ok.model_pnl > 0).mean() * 100:.1f}%, "
                  f"total ${ok.model_pnl.sum():+.0f}")
