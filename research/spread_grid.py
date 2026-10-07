"""Grid of spread structures x entry signals behind research/README.md section 6.

    python3 research/spread_grid.py      # about 8 minutes; writes research/spread_grid_results.csv
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import backtest as bt, indicators as ind, spreads as sp
vx = bt.vix()
M = {s: sp.Market(s, vx) for s in sp.UNIVERSE}
up = lambda f: f.c > f.sma200
SIG = {
 "RSI2<10 up": lambda f: up(f) & (f.rsi2 < 10),
 "BB%B<0 up": lambda f: up(f) & (f.bb_pct < 0),
 "ConnorsRSI<10 up": lambda f: up(f) & (f.crsi < 10),
 "VIX stretch up": lambda f: up(f) & (f.vix > 1.05 * f.vix_ma10),
 "Keltner low": lambda f: f.c < f.kc_low,
 "TV rating dip": lambda f: up(f) & (f.rating < -0.1),
 "ANY oversold": None,
 "Every Monday, up (no signal)": lambda f: up(f) & (pd.Series([d.weekday() == 0 for d in f.index], index=f.index)),
}
def sigs(f):
    out = {k: v(f) for k, v in SIG.items() if v}
    out["ANY oversold"] = sum(out[k].fillna(False).astype(int) for k in ["RSI2<10 up","BB%B<0 up","ConnorsRSI<10 up","VIX stretch up","Keltner low","TV rating dip"]) > 0
    return out
S = {s: sigs(M[s].f) for s in sp.UNIVERSE}
rows = []
t0 = time.time()
structs = [("put_credit", d, dte, ex, tp) for d in (0.2, 0.3, 0.4) for dte in (7, 14, 21) for ex, tp in (("hold", 0.5), ("hold", None), ("signal", 0.5))]
structs += [("call_debit", d, dte, ex, tp) for d in (0.5, 0.65) for dte in (14, 21) for ex, tp in (("signal", 0.5), ("signal", 1.0), ("hold", 0.5))]
for name in SIG:
    for kind, delta, dte, ex, tp in structs:
        allt = []
        for s in sp.UNIVERSE:
            t = sp.trades_for(M[s], S[s][name], kind, delta, dte, ex, tp)
            if len(t): t["sym"] = s; allt.append(t)
        t = pd.concat(allt, ignore_index=True) if allt else pd.DataFrame()
        r = dict(signal=name, kind=kind, delta=delta, dte=dte, exit=ex, tp=tp)
        for p, (a, b) in sp.PERIODS.items():
            x = t[(t.entry_date >= a) & (t.entry_date <= b)] if len(t) else t
            s_ = sp.summarize(x)
            r.update({f"{p}_n": s_.get("n", 0), f"{p}_win": s_.get("win"), f"{p}_avg": s_.get("avg"), f"{p}_pf": s_.get("pf")})
        rows.append(r)
    print(name, f"{time.time()-t0:.0f}s", flush=True)
g = pd.DataFrame(rows)
g.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "spread_grid_results.csv"), index=False)
