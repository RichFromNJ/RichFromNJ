"""Convert saved TradingView get_ohlcv JSON responses into the CSV files in research/data.

Usage: python3 research/tv_to_csv.py <dir with mcp-Trading_View-mcp-tv-get-ohlcv-*.txt> research/data

Files are processed in name order, so a later download of the same symbol and
interval replaces an earlier one.
"""
import datetime as dt
import glob
import json
import os
import sys
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def main(src, out):
    for f in sorted(glob.glob(os.path.join(src, "mcp-Trading_View-mcp-tv-get-ohlcv-*.txt"))):
        d = json.load(open(f))
        sym, iv, bars = d.get("symbol") or "?", d.get("interval"), d["bars"]
        name = f"{sym.replace(':', '_')}_{iv}.csv"
        with open(os.path.join(out, name), "w") as w:
            w.write("t,et,o,h,l,c,v\n")
            for b in bars:
                et = dt.datetime.fromtimestamp(b["t"], ET).strftime("%Y-%m-%d %H:%M")
                w.write(f'{b["t"]},{et},{b["o"]},{b["h"]},{b["l"]},{b["c"]},{b.get("v", 0)}\n')
        first = dt.datetime.fromtimestamp(bars[0]["t"], ET)
        last = dt.datetime.fromtimestamp(bars[-1]["t"], ET)
        print(f"{name}: {len(bars)} bars, {first:%Y-%m-%d %H:%M} -> {last:%Y-%m-%d %H:%M}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
