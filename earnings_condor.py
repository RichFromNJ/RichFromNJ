#!/usr/bin/env python3
"""Rules-based earnings iron condor: candidates, build, exit and a research scorer.

Implements the mechanical form of the course's earnings trade. On the last
session before a company reports, about 20 minutes before the close, sell a
four-leg iron condor whose short strikes sit one at-the-money straddle away
from the price on each side, with the narrowest wings that pay enough, in the
first expiration after the report, sized so the most that can be lost is $250.
Close it the next session, after the implied-volatility crush, win or lose.

Every number the routine needs is computed here so a run uses the same tested
math instead of code written on the fly. Any missing or ambiguous input is a
DataError, which the routine reports as NO TRADE.

Inputs are the JSON a Robinhood connector returned, saved to files. A top-level
"data" key is optional.
  - get_option_chains        chain id, expirations, min_ticks
  - get_option_instruments   listed contracts (puts and calls, any number of files)
  - get_option_quotes        bid/ask/delta/OI/volume per contract (up to 20 ids each)
  - get_earnings_calendar    report date, timing (am/pm) and verified flag
  - get_earnings_results     the same, for one symbol's past and coming reports
  - get_equity_quotes        last trade price per symbol (optional, for min_price)
  - get_equity_historicals   daily bars (or TradingView get-ohlcv), for the history moves
  - get_option_historicals   daily bars per contract, for the research scorer

Usage:
  earnings_condor.py candidates --calendar CAL.json --date 2026-10-13 [--prices P1.json P2.json ...]
  earnings_condor.py moves --results MS_earnings.json --bars MS_bars.json --symbol MS --date 2026-10-13
  earnings_condor.py build --symbol MS --price 190.01 --date 2026-10-13 \\
      --report-date 2026-10-14 --timing am --chain CHAIN.json \\
      --instruments PUTS.json CALLS.json --quotes Q1.json Q2.json \\
      [--calendar CAL.json] [--history-moves 1.2,3.4,0.8,2.0] [--max-loss 250]
  earnings_condor.py rank MS_build.json JPM_build.json ...
  earnings_condor.py exit --time 09:41 --date 2026-10-14 --reaction-day 2026-10-14 \\
      --expiration 2026-10-16 --credit 0.36 --buyback 0.09 [--close 16:00]
  earnings_condor.py buyback --quotes Q.json --instruments I.json \\
      --short SHORT_PUT_ID SHORT_CALL_ID --long LONG_PUT_ID LONG_CALL_ID [--previous 0.20] \\
      [--credit 0.36 --time 09:41 --date 2026-10-14 --reaction-day 2026-10-14 --expiration 2026-10-16]
  earnings_condor.py score --events EVENTS.json --bars BARS_DIR
"""

import argparse
import datetime as dt
import glob
import json
import math
import os
import sys
from dataclasses import asdict, dataclass, field
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
EXIT_START = dt.time(9, 40)      # first minute an exit order may go in (ET)
CLOSE_DEFAULT = dt.time(16, 0)   # a full session's close (ET); a half-day passes 13:00
FINAL_BEFORE_CLOSE = dt.timedelta(minutes=30)   # CLOSE_ALL regardless from close minus this
EXIT_FINAL = dt.time(15, 30)     # the regardless-close time on a full day (close - 30 minutes)
FEE_PER_CONTRACT_SIDE = 0.05     # dollars per contract per side, charged by the scorer
SPREAD_ASSUMED = 0.02            # per-share bid-ask the scorer assumes; half is paid per leg per side
LEGS = ("short_put", "long_put", "short_call", "long_call")

# NYSE full-day closures, used to find the next trading day. Same list as
# overnight_signal.NYSE_HOLIDAYS; tests/test_earnings_condor.py checks they agree.
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
HOLIDAYS_THROUGH = 2027  # last year NYSE_HOLIDAYS covers


class DataError(Exception):
    """The input data fails a check; the routine says NO TRADE."""


@dataclass(frozen=True)
class Params:
    """Every number in the mechanical reformulation, with the course's defaults."""
    max_loss: float = 250.0            # hard cap on (width - credit) x 100 x qty
    min_price: float = 10.0            # underlying price floor
    min_roi: float = 0.35              # limit credit / (width - limit credit)
    max_spread_pct: float = 0.15       # (ask - bid) / mid on each short leg
    natural_vs_mid: float = 0.75       # natural credit must be >= this x mid credit
    min_volume: int = 15               # a short leg is liquid with volume >= this ...
    min_oi: int = 100                  # ... or open interest >= this
    max_short_delta: float = 0.35      # |delta| of each short leg
    widths: tuple = (1.0, 2.0, 2.5, 5.0)   # wing widths tried in this order
    max_days_to_expiration: int = 8    # calendar days from the reaction day
    profit_take: float = 0.30          # buy back when the condor costs <= this x credit
    hist_need: int = 3                 # past moves that must fit inside the implied move ...
    hist_of: int = 4                   # ... out of this many most recent reports
    floor_vs_limit: float = 0.90       # no entry order below this x limit credit (or the ROI floor)


@dataclass
class Ticks:
    below_tick: float
    above_tick: float
    cutoff_price: float


@dataclass
class Chain:
    symbol: str
    chain_id: str
    expirations: list
    ticks: Ticks


@dataclass
class Leg:
    """One listed contract and, when a quote was loaded for it, its quote."""
    id: str
    symbol: str
    expiration: dt.date
    strike: float
    kind: str                 # "put" or "call"
    bid: float = None
    ask: float = None
    delta: float = None
    iv: float = None
    open_interest: int = 0
    volume: int = 0
    ticks: Ticks = None       # the contract's min_ticks, when the instrument row carried them

    @property
    def quoted(self):
        """Has an ask above zero and a bid; a far wing's bid may be zero."""
        return self.bid is not None and self.ask is not None and self.ask > 0 and self.bid >= 0

    @property
    def two_sided(self):
        """Has a bid above zero as well, as a leg that is sold or a straddle leg must."""
        return self.quoted and self.bid > 0

    @property
    def mid(self):
        return (self.bid + self.ask) / 2

    @property
    def spread_pct(self):
        return (self.ask - self.bid) / self.mid

    def name(self):
        return f"{self.kind} {self.strike:g} {self.expiration}"


@dataclass
class Condor:
    symbol: str
    expiration: dt.date
    short_put: float
    long_put: float
    short_call: float
    long_call: float
    width: float
    credit: float             # limit credit per condor, in dollars per share
    qty: int
    ids: dict = field(default_factory=dict)   # leg name -> instrument id

    @property
    def risk(self):
        """Dollars at risk per condor: (width - credit) x 100."""
        return round((self.width - self.credit) * 100, 2)

    @property
    def max_loss(self):
        return round(self.risk * self.qty, 2)


# ---------------------------------------------------------------- loading

def _load(path):
    """A saved connector response, with a top-level "data" key unwrapped. A
    missing or unreadable file, or one that is not JSON, is a DataError."""
    try:
        with open(path) as f:
            raw = json.load(f)
    except OSError as e:
        raise DataError(f"cannot read {path}: {e.strerror or e}")
    except ValueError as e:
        raise DataError(f"{path} is not JSON: {e}")
    return raw["data"] if isinstance(raw, dict) and "data" in raw else raw


def _require(d, key, path):
    """d[key] from a saved response, or a DataError naming the file (an error
    response, for example, has no "results")."""
    if not isinstance(d, dict) or key not in d or d[key] is None:
        have = ", ".join(sorted(d)) if isinstance(d, dict) else type(d).__name__
        raise DataError(f"{path} has no {key!r} (has: {have})")
    return d[key]


def _date(s):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        raise DataError(f"date {s!r} is not YYYY-MM-DD")


def _time(s):
    """HH:MM (a one-digit hour and trailing seconds are accepted), else a DataError."""
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return dt.datetime.strptime(str(s).strip(), fmt).time()
        except ValueError:
            pass
    raise DataError(f"time {s!r} is not HH:MM")


def _float(v):
    return None if v in (None, "") else float(v)


def _ticks(t):
    return Ticks(float(t["below_tick"]), float(t["above_tick"]), float(t["cutoff_price"]))


def load_chain(path, symbol):
    """get_option_chains output -> Chain for `symbol`. Exactly one chain must match
    the symbol; none or several is ambiguous and a DataError (NO TRADE)."""
    chains = [c for c in _require(_load(path), "chains", path) if c["symbol"].upper() == symbol.upper()]
    if len(chains) != 1:
        raise DataError(f"{len(chains)} option chains for {symbol} in {path}; need exactly 1")
    c = chains[0]
    return Chain(symbol.upper(), c["id"], sorted(_date(e) for e in c["expiration_dates"]), _ticks(c["min_ticks"]))


def load_legs_by_id(instrument_paths, quote_paths=(), symbol=None):
    """get_option_instruments and get_option_quotes output (any number of files each)
    -> {instrument id: Leg}. Only active, tradable contracts count as listed; a quote
    whose instrument is not listed, or a null quote entry, is ignored."""
    by_id = {}
    for path in instrument_paths:
        for i in _require(_load(path), "instruments", path):
            if i.get("state", "active") != "active" or i.get("tradability", "tradable") != "tradable":
                continue
            if symbol and i["chain_symbol"].upper() != symbol.upper():
                continue
            t = i.get("min_ticks")
            by_id[i["id"]] = Leg(i["id"], i["chain_symbol"].upper(), _date(i["expiration_date"]),
                                 float(i["strike_price"]), i["type"], ticks=_ticks(t) if t else None)
    for path in quote_paths:
        for r in _require(_load(path), "results", path):
            q = (r or {}).get("quote") or {}
            leg = by_id.get(q.get("instrument_id")) if q.get("instrument_id") else None
            if leg is None:
                continue
            leg.bid, leg.ask = _float(q.get("bid_price")), _float(q.get("ask_price"))
            leg.delta, leg.iv = _float(q.get("delta")), _float(q.get("implied_volatility"))
            leg.open_interest = int(q.get("open_interest") or 0)
            leg.volume = int(q.get("volume") or 0)
    return by_id


def load_book(instrument_paths, quote_paths=(), symbol=None):
    """The legs of load_legs_by_id keyed by (kind, expiration, strike)."""
    return {(l.kind, l.expiration, l.strike): l for l in load_legs_by_id(instrument_paths, quote_paths, symbol).values()}


def load_calendar(path):
    """get_earnings_calendar / get_earnings_results output -> list of reports:
    {symbol, report_date, timing, verified}. Entries without a date are dropped."""
    out = []
    for r in _require(_load(path), "results", path):
        rep = r.get("report") or {}
        if not rep.get("date"):
            continue
        out.append({"symbol": r["symbol"].upper(), "report_date": _date(rep["date"]),
                    "timing": rep.get("timing"), "verified": bool(rep.get("verified"))})
    return out


def load_prices(paths):
    """get_equity_quotes output (one path or several, at most 20 symbols each) ->
    {symbol: last trade price}."""
    out = {}
    for path in ([paths] if isinstance(paths, str) else paths):
        for r in _require(_load(path), "results", path):
            q = (r or {}).get("quote") or {}
            if q.get("last_trade_price") and q.get("symbol"):
                out[q["symbol"].upper()] = float(q["last_trade_price"])
    return out


def load_daily_closes(path, symbol=None):
    """Daily closes {date: close} from saved Robinhood get_equity_historicals output
    (bars marked interpolated dropped) or TradingView get-ohlcv output (bar times
    are epoch seconds; the session date is taken in ET). With `symbol`, the file
    must hold that symbol."""
    raw = _load(path)
    out = {}
    if isinstance(raw, dict) and "results" in raw:
        for r in raw["results"]:
            if symbol and str(r.get("symbol", "")).upper() != symbol.upper():
                continue
            for b in r.get("bars", []):
                if b.get("interpolated"):
                    continue
                out[_date(b["begins_at"])] = float(b["close_price"])
    elif isinstance(raw, dict) and "bars" in raw:
        tv = str(raw.get("symbol", "")).upper()
        if symbol and not (tv == symbol.upper() or tv.endswith(":" + symbol.upper())):
            raise DataError(f"{path} holds {tv or 'no symbol'}, not {symbol}")
        for b in raw["bars"]:
            out[dt.datetime.fromtimestamp(b["t"], tz=ET).date()] = float(b["c"])
    else:
        raise DataError(f"{path} is neither get_equity_historicals nor get-ohlcv output")
    if not out:
        raise DataError(f"no daily bars for {symbol or 'the symbol'} in {path}")
    return out


def load_option_bars(path):
    """get_option_historicals output -> {instrument_id: {date: close}}. Bars marked
    interpolated are gap-fill placeholders, not real trading, and are dropped."""
    out = {}
    for r in _require(_load(path), "results", path):
        closes = {}
        for b in r["bars"]:
            if b.get("interpolated"):
                continue
            closes[_date(b["begins_at"])] = float(b["close_price"])
        out[r["instrument_id"]] = closes
    return out


def load_bars_dir(directory):
    """Every *.json in `directory` is a saved get_option_historicals output; merge them."""
    bars = {}
    for path in sorted(glob.glob(os.path.join(directory, "*.json"))):
        bars.update(load_option_bars(path))
    return bars


# --------------------------------------------------------------- calendar

def _check_holidays(day):
    if day.year > HOLIDAYS_THROUGH:
        raise DataError(f"holiday list ends {HOLIDAYS_THROUGH}; update NYSE_HOLIDAYS")


def previous_trading_day(day):
    day -= dt.timedelta(days=1)
    while day.weekday() >= 5 or day in NYSE_HOLIDAYS:
        day -= dt.timedelta(days=1)
    return day


def next_trading_day(day):
    _check_holidays(day)
    day += dt.timedelta(days=1)
    while day.weekday() >= 5 or day in NYSE_HOLIDAYS:
        day += dt.timedelta(days=1)
    return day


def reaction_day(report_date, timing):
    """CALENDAR: the first session that trades on the report. A pre-market ('am')
    report reacts that day; an after-close ('pm') report reacts the next trading
    day. Any other timing is unknown and a DataError (NO TRADE)."""
    if timing == "am":
        return report_date
    if timing == "pm":
        return next_trading_day(report_date)
    raise DataError(f"report timing {timing!r} is not 'am' or 'pm'")


def is_candidate(today, report_date, timing, verified=True):
    """CANDIDATES: the condor is sold on the last session before the report, so a
    'pm' report qualifies on its own date and an 'am' report qualifies on the
    trading day before it. Unverified dates and unknown timings never qualify."""
    if not verified or timing not in ("am", "pm"):
        return False
    if timing == "pm":
        return report_date == today
    return report_date == next_trading_day(today)


def candidates(reports, today, prices=None, params=Params()):
    """CANDIDATES: the reports that qualify today, each with its reaction day, and
    the reports in today's window that were skipped, each with the reason. When a
    prices map is given, names under min_price are skipped (course: avoid cheap
    stocks whose strikes are too coarse for a one-straddle condor)."""
    window = {today, next_trading_day(today)}
    picked, skipped = [], []
    for r in reports:
        if r["report_date"] not in window:
            continue
        price = (prices or {}).get(r["symbol"])
        why = None
        if not r["verified"]:
            why = "report date not verified"
        elif r["timing"] not in ("am", "pm"):
            why = "report timing unknown"
        elif not is_candidate(today, r["report_date"], r["timing"]):
            why = ("already reported before today's open" if r["report_date"] == today
                   else "pm report tomorrow; sell it tomorrow, not today")
        elif prices is not None and price is None:
            why = "no price in the prices file"
        elif prices is not None and price < params.min_price:
            why = f"price {price:.2f} below {params.min_price:g}"
        row = dict(r, price=price)
        if why:
            skipped.append(dict(row, reason=why))
        else:
            picked.append(dict(row, reaction_day=reaction_day(r["report_date"], r["timing"])))
    return picked, skipped


def verify_report(reports, symbol, report_date, timing):
    """BUILD with an earnings file: the symbol's report must be listed, verified,
    dated report_date and timed `timing`; anything else is a DataError (NO TRADE),
    so a tentative date can never be traded on the strength of the CLI flags."""
    rows = [r for r in reports if r["symbol"] == symbol.upper()]
    if not rows:
        raise DataError(f"{symbol} is not in the earnings file")
    match = [r for r in rows if r["report_date"] == report_date]
    if not match:
        listed = ", ".join(sorted(r["report_date"].isoformat() for r in rows))
        raise DataError(f"{symbol} reports on {listed} in the earnings file, not {report_date}")
    r = match[0]
    if not r["verified"]:
        raise DataError(f"{symbol} {report_date} report is not verified")
    if r["timing"] != timing:
        raise DataError(f"{symbol} {report_date} timing is {r['timing']!r} in the earnings file, not {timing!r}")
    return r


def history_moves(reports, closes, today, symbol=None, params=Params()):
    """HISTORY: the absolute post-earnings moves, percent of price, of the last
    hist_of reports of `symbol` dated before `today`, oldest first, from daily
    closes: am -> report-day close against the previous bar's close; pm -> the next
    bar's close against the report-day close. A report with no timing or a missing
    bar is skipped (and listed) and the next older report is used instead, so the
    filter gets hist_of moves whenever the data allows."""
    days = sorted(closes)
    past = sorted((r for r in reports
                   if (symbol is None or r["symbol"] == symbol.upper()) and r["report_date"] < today),
                  key=lambda r: r["report_date"])
    moves, skipped = [], []
    for r in reversed(past):
        if len(moves) >= params.hist_of:
            break
        row = {"report_date": r["report_date"], "timing": r["timing"]}
        rep = r["report_date"]
        if r["timing"] not in ("am", "pm"):
            skipped.append(dict(row, reason="report timing unknown"))
            continue
        if rep not in closes:
            skipped.append(dict(row, reason=f"no bar on the report date {rep}"))
            continue
        i = days.index(rep)
        if r["timing"] == "am":
            if i == 0:
                skipped.append(dict(row, reason=f"no bar before {rep}"))
                continue
            frm, to = days[i - 1], rep
        else:
            if i + 1 >= len(days):
                skipped.append(dict(row, reason=f"no bar after {rep}"))
                continue
            frm, to = rep, days[i + 1]
        moves.append(dict(row, reaction_day=to, from_date=frm, from_close=closes[frm], to_close=closes[to],
                          move_pct=round(100 * abs(closes[to] / closes[frm] - 1), 4)))
    moves.reverse()
    return {"symbol": symbol.upper() if symbol else None, "date": today, "need": params.hist_of,
            "moves": moves, "skipped": skipped,
            "history_moves": ",".join(f"{m['move_pct']:.4f}" for m in moves),
            "note": (f"{len(moves)} of the last {params.hist_of} reports measured"
                     + (f"; {len(skipped)} skipped" if skipped else ""))}


# ------------------------------------------------------------- selection

def choose_expiration(reaction, expirations, params=Params()):
    """EXPIRATION: the first listed expiration on or after the reaction day and no
    more than max_days_to_expiration calendar days after it (course: the first
    expiration after the report). None means NO TRADE."""
    last = reaction + dt.timedelta(days=params.max_days_to_expiration)
    listed = sorted(e for e in expirations if reaction <= e <= last)
    return listed[0] if listed else None


def listed_strikes(book, kind, expiration):
    return sorted(l.strike for l in book.values() if l.kind == kind and l.expiration == expiration)


def leg(book, kind, expiration, strike, two_sided=True):
    """The listed, quoted contract at (kind, expiration, strike), or a DataError.
    A leg that is sold, and each straddle leg, needs a bid and an ask above zero;
    a long wing needs only an ask (two_sided=False), since a far wing's bid is
    often zero. A listed contract with no quote loaded says so, so the routine
    knows to pull the quote rather than treat the strike as missing."""
    l = book.get((kind, expiration, strike))
    if l is None:
        raise DataError(f"{kind} {strike:g} {expiration} is not listed")
    if l.bid is None or l.ask is None:
        raise DataError(f"{l.name()} is listed but has no quote loaded (bid {l.bid} ask {l.ask}); pull its quote")
    if not (l.two_sided if two_sided else l.quoted):
        raise DataError(f"{l.name()} has no usable quote (bid {l.bid} ask {l.ask})")
    return l


def atm_strike(price, strikes):
    """STRIKES step 1: the listed strike nearest the price; a tie goes to the lower."""
    if not strikes:
        raise DataError("no strikes listed")
    return min(sorted(set(strikes)), key=lambda s: (abs(s - price), s))


def straddle(book, expiration, atm):
    """STRIKES step 2: the ATM straddle is the mid of the ATM call plus the mid of
    the ATM put (course: the straddle price is the market's expected move). Both
    legs need a bid and an ask above zero."""
    return leg(book, "call", expiration, atm).mid + leg(book, "put", expiration, atm).mid


def implied_move_pct(straddle_, price):
    """STRIKES step 2: the implied move as a percent of the price."""
    return 100.0 * straddle_ / price


def short_strikes(price, straddle_, put_strikes, call_strikes=None):
    """STRIKES step 3: short put = highest listed strike at or below price - straddle;
    short call = lowest listed strike at or above price + straddle. Each side rounds
    outward on its own (course: one straddle away). None where nothing is listed."""
    call_strikes = put_strikes if call_strikes is None else call_strikes
    puts = [s for s in sorted(set(put_strikes)) if s <= price - straddle_ + 1e-9]
    calls = [s for s in sorted(set(call_strikes)) if s >= price + straddle_ - 1e-9]
    return (puts[-1] if puts else None), (calls[0] if calls else None)


def tick_for(price, ticks):
    """PRICES: the tick that applies at `price`: below_tick under the cutoff price,
    above_tick at or above it (Robinhood min_ticks)."""
    return ticks.below_tick if price < ticks.cutoff_price - 1e-9 else ticks.above_tick


def round_down_tick(price, ticks):
    """PRICES: round down to the contract's tick."""
    tick = tick_for(price, ticks)
    return round(math.floor(round(price / tick, 6)) * tick, 4)


def round_up_tick(price, ticks):
    """PRICES: round up to the contract's tick."""
    tick = tick_for(price, ticks)
    return round(math.ceil(round(price / tick, 6)) * tick, 4)


def one_tick_below(price, ticks):
    """PRICES: the price one tick under `price`. Just under the cutoff the smaller
    tick applies, so one tick below 3.00 is 2.99 when the cutoff is 3.00."""
    tick = ticks.below_tick if price <= ticks.cutoff_price + 1e-9 else ticks.above_tick
    return round(price - tick, 4)


def floor_credit(limit, width, ticks, params=Params()):
    """SIZE: the lowest credit any entry order may carry: the larger of floor_vs_limit
    x the limit credit and the credit at which ROI is exactly min_roi (width x
    min_roi / (1 + min_roi)), rounded UP to the tick."""
    roi_floor = width * params.min_roi / (1 + params.min_roi)
    return round_up_tick(max(params.floor_vs_limit * limit, roi_floor), ticks)


def second_price(limit, floor, ticks):
    """ORDER: the re-placement price, one tick under the limit credit but never
    under the floor credit; the limit itself when one tick down would breach it
    (then there is no second order)."""
    second = one_tick_below(limit, ticks)
    return second if second >= floor - 1e-9 else limit


def leg_checks(l, params=Params()):
    """LIQUIDITY and DELTA on one short leg: bid-ask within max_spread_pct of the
    mid (course: 10-15%), volume >= min_volume (course: above ~15) or open interest
    >= min_oi, and |delta| <= max_short_delta. Returns the checks that failed."""
    failed = []
    if l.spread_pct > params.max_spread_pct + 1e-9:
        failed.append({"check": "spread", "leg": l.name(),
                       "detail": f"(ask - bid) / mid {l.spread_pct:.1%} > {params.max_spread_pct:.0%}"})
    if not (l.volume >= params.min_volume or l.open_interest >= params.min_oi):
        failed.append({"check": "liquidity", "leg": l.name(),
                       "detail": f"volume {l.volume} < {params.min_volume} and OI {l.open_interest} < {params.min_oi}"})
    if l.delta is None:
        failed.append({"check": "delta", "leg": l.name(), "detail": "no delta in the quote"})
    elif abs(l.delta) > params.max_short_delta + 1e-9:
        failed.append({"check": "delta", "leg": l.name(),
                       "detail": f"|delta| {abs(l.delta):.2f} > {params.max_short_delta:g}"})
    return failed


def leg_report(l):
    return {"strike": l.strike, "id": l.id, "bid": l.bid, "ask": l.ask, "mid": round(l.mid, 4),
            "spread_pct": round(100 * l.spread_pct, 2), "delta": l.delta, "iv": l.iv,
            "open_interest": l.open_interest, "volume": l.volume}


def try_width(width, short_put, short_call, book, expiration, ticks, params=Params(), short_failed=()):
    """WINGS: for one width, long put = short put - width and long call = short call
    + width, both listed and quoted. Mid credit = short mids - long mids; natural
    credit = short bids - long asks; entry limit = mid credit rounded down to the
    tick; risk = (width - limit) x 100; qty = floor(max_loss / risk). The width
    passes when the limit credit is positive, ROI >= min_roi, natural >= natural_vs_mid
    x mid, the short-leg checks pass and qty >= 1. Every failure is named: "listed"
    for a wing that is not listed, "quote" for one listed without a quote loaded.
    Also reports the tick at the limit, the floor credit, and the second (re-
    placement) price with the quantity that keeps max_loss at that price."""
    r = {"width": width, "long_put": short_put.strike - width, "long_call": short_call.strike + width,
         "failed": list(short_failed), "ok": False}
    unlisted, unquoted = [], []
    for kind, strike in (("put", r["long_put"]), ("call", r["long_call"])):
        l = book.get((kind, expiration, strike))
        if l is None:
            unlisted.append(f"{kind} {strike:g} {expiration}")
        elif not l.quoted:
            unquoted.append(f"{l.name()} (bid {l.bid} ask {l.ask})")
    if unlisted:
        r["failed"].append({"check": "listed", "leg": None, "detail": ", ".join(unlisted) + " not listed"})
    if unquoted:
        r["failed"].append({"check": "quote", "leg": None,
                            "detail": ", ".join(unquoted) + " listed but no usable quote loaded; pull the quote"})
    if unlisted or unquoted:
        return r
    lp, lc = book[("put", expiration, r["long_put"])], book[("call", expiration, r["long_call"])]
    r["ids"] = {"short_put": short_put.id, "long_put": lp.id, "short_call": short_call.id, "long_call": lc.id}
    r["long_put_quote"], r["long_call_quote"] = leg_report(lp), leg_report(lc)
    mid = short_put.mid + short_call.mid - lp.mid - lc.mid
    natural = short_put.bid + short_call.bid - lp.ask - lc.ask
    limit = round_down_tick(mid, ticks) if mid > 0 else 0.0
    risk = round((width - limit) * 100, 2)
    r.update(mid_credit=round(mid, 4), natural_credit=round(natural, 4), limit_credit=limit, risk=risk,
             tick=tick_for(limit, ticks), ticks=asdict(ticks),
             natural_vs_mid=round(natural / mid, 4) if mid > 0 else None,
             roi=round(limit / (width - limit), 4) if 0 < limit < width else None,
             qty=math.floor(params.max_loss / risk + 1e-9) if risk > 0 else 0)
    r["max_loss"] = round(risk * r["qty"], 2)
    if limit > 0:
        fl = floor_credit(limit, width, ticks, params)
        second = second_price(limit, fl, ticks)
        srisk = round((width - second) * 100, 2)
        sqty = math.floor(params.max_loss / srisk + 1e-9) if srisk > 0 else 0
        r.update(floor_credit=fl, second_price=second, second_risk=srisk, second_qty=sqty,
                 second_max_loss=round(srisk * sqty, 2))
    if limit <= 0:
        r["failed"].append({"check": "credit", "leg": None, "detail": f"limit credit {limit:.2f} is not positive"})
    elif r["roi"] is None or r["roi"] < params.min_roi - 1e-9:
        r["failed"].append({"check": "roi", "leg": None,
                            "detail": f"ROI {limit:.2f} / ({width:g} - {limit:.2f}) = {(r['roi'] or 0):.1%} < {params.min_roi:.0%}"})
    if mid <= 0 or natural < params.natural_vs_mid * mid - 1e-9:
        r["failed"].append({"check": "natural_vs_mid", "leg": None,
                            "detail": f"natural {natural:.2f} < {params.natural_vs_mid:g} x mid {mid:.3f}"})
    if r["qty"] < 1:
        r["failed"].append({"check": "qty", "leg": None,
                            "detail": f"risk ${risk:.0f} per condor exceeds max loss ${params.max_loss:g}"})
    r["ok"] = not r["failed"]
    return r


def history_filter(moves, implied_pct, params=Params()):
    """HISTORY: at least hist_need of the last hist_of post-earnings moves (absolute,
    percent of price) must be no larger than today's implied move percent (course:
    "3 of the last 4 would have won"). With fewer than hist_of moves supplied the
    filter is skipped and says so."""
    moves = [abs(float(m)) for m in (moves or [])]
    out = {"implied_move_pct": round(implied_pct, 4), "need": params.hist_need, "of": params.hist_of}
    if len(moves) < params.hist_of:
        out.update(applied=False, ok=True, moves=moves, within=None,
                   note=f"history filter skipped: {len(moves)} past moves supplied, need {params.hist_of}")
        return out
    recent = moves[-params.hist_of:]
    within = sum(1 for m in recent if m <= implied_pct + 1e-9)
    out.update(applied=True, ok=within >= params.hist_need, moves=recent, within=within,
               note=f"{within} of the last {params.hist_of} moves within the implied move "
                    f"{implied_pct:.2f}% (need {params.hist_need})")
    return out


def build(symbol, price, today, report_date, timing, chain, book, params=Params(), history_moves=None, reports=None):
    """BUILD: run CANDIDATES, EXPIRATION, STRIKES, WINGS, SIZE and HISTORY in order
    and return a dict with every input and every value computed, with decision
    "TRADE" or "NO TRADE" and the reason. The condor, when there is one, is the
    first width that passed every check, with the tick, floor credit and second
    price (one tick under the limit, never under the floor) and the quantity that
    keeps max_loss at the second price. With `reports` (a saved earnings file) the
    report must be listed there, verified, on report_date with `timing`."""
    out = {"symbol": symbol.upper(), "price": price, "date": today, "report_date": report_date,
           "timing": timing, "decision": "NO TRADE", "reason": None, "widths": [], "condor": None,
           "params": asdict(params), "ticks": asdict(chain.ticks)}
    try:
        if price is None or price < params.min_price:
            raise DataError(f"price {price} below min_price {params.min_price:g}")
        if reports is not None:
            verify_report(reports, symbol, report_date, timing)
            out["report_verified"] = True
        if not is_candidate(today, report_date, timing):
            raise DataError(f"not a candidate on {today}: reports {report_date} {timing}")
        rd = reaction_day(report_date, timing)
        out["reaction_day"] = rd
        exp = choose_expiration(rd, chain.expirations, params)
        if exp is None:
            raise DataError(f"no expiration between {rd} and {rd + dt.timedelta(days=params.max_days_to_expiration)}; "
                            f"listed: {', '.join(e.isoformat() for e in chain.expirations[:4])}")
        out["expiration"] = exp
        put_strikes, call_strikes = listed_strikes(book, "put", exp), listed_strikes(book, "call", exp)
        both = sorted(set(put_strikes) & set(call_strikes))
        if not both:
            raise DataError(f"no strikes listed for both a put and a call expiring {exp}")
        atm = atm_strike(price, both)
        st = straddle(book, exp, atm)
        out.update(atm_strike=atm, straddle=round(st, 4), implied_move_pct=round(implied_move_pct(st, price), 4))
        out["history"] = history_filter(history_moves, out["implied_move_pct"], params)
        sp_strike, sc_strike = short_strikes(price, st, put_strikes, call_strikes)
        if sp_strike is None or sc_strike is None:
            raise DataError(f"no listed strike one straddle away (put <= {price - st:.2f}, call >= {price + st:.2f})")
        sp, sc = leg(book, "put", exp, sp_strike), leg(book, "call", exp, sc_strike)
        out["short_put"], out["short_call"] = leg_report(sp), leg_report(sc)
        short_failed = leg_checks(sp, params) + leg_checks(sc, params)
        out["short_leg_failed"] = short_failed
        chosen = None
        for w in params.widths:
            r = try_width(w, sp, sc, book, exp, chain.ticks, params, short_failed)
            out["widths"].append(r)
            if r["ok"]:
                chosen = r
                break
        if chosen is None:
            why = "; ".join(f"${w['width']:g}: " + ", ".join(sorted({f['check'] for f in w['failed']}))
                            for w in out["widths"])
            out["reason"] = f"no width passed every check ({why})"
        elif not out["history"]["ok"]:
            out["reason"] = f"history filter failed: {out['history']['note']}"
        else:
            out["condor"] = asdict(Condor(out["symbol"], exp, sp.strike, chosen["long_put"], sc.strike,
                                          chosen["long_call"], chosen["width"], chosen["limit_credit"],
                                          chosen["qty"], chosen["ids"]))
            out["condor"].update({k: chosen[k] for k in ("risk", "max_loss", "roi", "natural_credit", "mid_credit",
                                                         "tick", "ticks", "floor_credit", "second_price",
                                                         "second_risk", "second_qty", "second_max_loss")})
            out["decision"], out["reason"] = "TRADE", f"${chosen['width']:g} wings passed every check"
    except DataError as e:
        out["reason"] = f"Data check failed: {e}"
    return out


def rank(builds):
    """RANKING: the TRADE verdicts by ROI, highest first; ties go to the larger
    natural credit, then alphabetical by symbol. The pick is the first."""
    trades = [b for b in builds if b.get("decision") == "TRADE" and b.get("condor")]
    ranked = sorted(trades, key=lambda b: (-b["condor"]["roi"], -b["condor"]["natural_credit"], b["symbol"]))
    rows = [{"symbol": b["symbol"], "roi": b["condor"]["roi"], "natural_credit": b["condor"]["natural_credit"],
             "width": b["condor"]["width"], "credit": b["condor"]["credit"], "qty": b["condor"]["qty"],
             "max_loss": b["condor"]["max_loss"], "expiration": b["condor"]["expiration"]} for b in ranked]
    others = [{"symbol": b.get("symbol"), "reason": b.get("reason")} for b in builds if b not in trades]
    return {"pick": rows[0]["symbol"] if rows else None, "ranked": rows, "no_trade": others}


# ------------------------------------------------------------------- exit

def exit_final(close=CLOSE_DEFAULT):
    """EXIT: the time from which the reaction-day close is unconditional: 30 minutes
    before the session's close (15:30 on a full day, 12:30 on a 13:00 half-day)."""
    return (dt.datetime.combine(dt.date(2000, 1, 1), close) - FINAL_BEFORE_CLOSE).time()


def exit_decision(now_et, reaction_day_, expiration, price, condor, buyback_cost, params=Params(), close=CLOSE_DEFAULT):
    """EXIT: close the next session after the crush, win or lose. Before the reaction
    day HOLD. On the reaction day, from 09:40 until close - 30 minutes CLOSE_ALL once
    the condor can be bought back for <= profit_take x credit, else HOLD; from
    close - 30 minutes CLOSE_ALL regardless. After the reaction day CLOSE_ALL and flag
    it. Never hold into expiration: on the expiration day CLOSE_ALL at any time from
    09:40. With no credit known the profit target cannot be tested (HOLD until the
    unconditional close)."""
    today, t = now_et.date(), now_et.time()
    final = exit_final(close)
    if isinstance(condor, Condor):
        credit, sp, sc = condor.credit, condor.short_put, condor.short_call
    else:
        credit, sp, sc = condor.get("credit"), condor.get("short_put"), condor.get("short_call")
    credit = None if credit is None else float(credit)
    target = None if credit is None else round(params.profit_take * credit, 4)
    out = {"time": now_et.isoformat(sep=" "), "reaction_day": reaction_day_, "expiration": expiration,
           "close": close.isoformat(timespec="minutes"), "final": final.isoformat(timespec="minutes"),
           "price": price, "credit": credit, "buyback_cost": buyback_cost, "profit_target": target,
           "action": "HOLD", "reason": "", "flag": None}
    if sp is not None and sc is not None and price is not None:
        out["price_vs_shorts"] = "inside" if sp < price < sc else "outside"
    if today > expiration:
        out.update(action="CLOSE_ALL", reason="past expiration", flag="past expiration; should not happen")
    elif today == expiration and t >= EXIT_START:
        out.update(action="CLOSE_ALL", reason="expiration day: never hold into expiration")
    elif today < reaction_day_:
        out.update(reason="before the reaction day")
    elif today == reaction_day_:
        if t < EXIT_START:
            out.update(reason=f"before {EXIT_START:%H:%M} on the reaction day")
        elif t < final:
            if credit is None:
                out.update(reason=f"credit unknown; cannot test the profit target; CLOSE_ALL from {final:%H:%M}")
            elif buyback_cost is None:
                out.update(reason="no buyback cost supplied; re-quote")
            elif buyback_cost <= target + 1e-9:
                out.update(action="CLOSE_ALL", reason=f"buyback {buyback_cost:.2f} <= {params.profit_take:.0%} of credit ({target:.2f})")
            else:
                out.update(reason=f"buyback {buyback_cost:.2f} > {params.profit_take:.0%} of credit ({target:.2f})")
        else:
            out.update(action="CLOSE_ALL", reason=f"{final:%H:%M} or later on the reaction day (close {close:%H:%M})")
    else:
        out.update(action="CLOSE_ALL", reason="after the reaction day",
                   flag="still open after the reaction day; should not happen")
    return out


def closing_debits(shorts, longs):
    """CLOSE: natural debit = short asks - long bids; mid debit = short mids - long
    mids. Every leg needs a quote loaded (bid and ask present) and each short leg
    an ask above zero; a long wing's bid of 0.00 is a real quote and counts as
    zero (far wings often have no bid after the crush)."""
    for l in list(shorts) + list(longs):
        if l.bid is None or l.ask is None:
            raise DataError(f"{l.name()} has no quote loaded (bid {l.bid} ask {l.ask})")
    for l in shorts:
        if l.ask <= 0:
            raise DataError(f"short {l.name()} has no ask; the natural debit is unknown")
    natural = sum(l.ask for l in shorts) - sum(l.bid for l in longs)
    mid = sum(l.mid for l in shorts) - sum(l.mid for l in longs)
    return round(natural, 4), round(mid, 4)


def closing_prices(natural, mid, ticks, previous=None):
    """PRICES for a closing order: first = the mid debit rounded UP to the tick;
    re-price = the larger of the new mid rounded up and the previous price plus one
    tick, never above the natural debit; final = the natural debit plus one tick.
    No price goes under one tick."""
    low = ticks.below_tick
    first = max(round_up_tick(max(mid, 0.0), ticks), low)
    final = max(round(max(natural, 0.0) + tick_for(max(natural, 0.0), ticks), 4), low)
    out = {"natural_debit": natural, "mid_debit": mid, "tick": tick_for(first, ticks), "ticks": asdict(ticks),
           "first_price": first, "final_price": final, "reprice": None}
    if previous is not None:
        up = round(previous + tick_for(previous, ticks), 4)
        out["reprice"] = max(min(max(first, up), round(natural, 4)), low)
    return out


# ----------------------------------------------------------------- scorer

def wilson(k, n, z=1.96):
    """Wilson 95% interval for k successes in n trials."""
    if n == 0:
        return 0.0, 0.0
    p, z2 = k / n, z * z
    d, c = 1 + z2 / n, p + z2 / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return (c - r) / d, (c + r) / d


def _closes(series):
    """A contract's bars as {date: close}: already that, or the raw bar list from
    get_option_historicals (interpolated bars dropped)."""
    if isinstance(series, dict):
        return series
    return {_date(b["begins_at"]): float(b["close_price"]) for b in series if not b.get("interpolated")}


def score_event(event, bars, params=Params()):
    """SCORER: one past earnings condor from daily option bars. Credit = entry-day
    closes (shorts - longs); exit cost = reaction-day closes; qty = floor(max_loss /
    risk) unless the event gives one; pnl = (credit - exit) x 100 x qty minus $0.05
    per contract per side and half a $0.02 spread per leg per side; win = pnl > 0.

    The event has entry_date, reaction_day, width, the underlying's entry-day close
    ("price") and reaction-day close, "legs" (leg name -> instrument id) and
    optionally qty and the straddle, as a number or {"call": id, "put": id}. `bars`
    maps instrument ids or leg names (short_put, long_put, short_call, long_call,
    atm_put, atm_call) to that contract's bars, as {date: close} or the raw bar list."""
    for k in ("entry_date", "reaction_day", "width"):
        if event.get(k) is None:
            raise DataError(f"event missing {k}")
    entry, rd = _date(event["entry_date"]), _date(event["reaction_day"])
    legs = event.get("legs") or {}

    def close(name, day, iid=None):
        series = bars.get(iid) if iid is not None else None
        if series is None:
            series = bars.get(name)
        if series is None:
            raise DataError(f"no bars for {name} ({iid})")
        closes = _closes(series)
        if day not in closes:
            raise DataError(f"no {day} bar for {name} ({iid})")
        return closes[day]

    entry_closes = {l: close(l, entry, legs.get(l)) for l in LEGS}
    exit_closes = {l: close(l, rd, legs.get(l)) for l in LEGS}
    credit = entry_closes["short_put"] + entry_closes["short_call"] - entry_closes["long_put"] - entry_closes["long_call"]
    exit_cost = exit_closes["short_put"] + exit_closes["short_call"] - exit_closes["long_put"] - exit_closes["long_call"]
    width = float(event["width"])
    risk = round((width - credit) * 100, 2)
    qty = int(event["qty"]) if event.get("qty") is not None else (math.floor(params.max_loss / risk + 1e-9) if risk > 0 else 0)
    fees = round(2 * len(LEGS) * qty * FEE_PER_CONTRACT_SIDE, 2)
    slippage = round(2 * len(LEGS) * qty * (SPREAD_ASSUMED / 2) * 100, 2)
    gross = round((credit - exit_cost) * 100 * qty, 2)
    out = {"symbol": event.get("symbol"), "entry_date": entry, "reaction_day": rd, "width": width,
           "entry_closes": entry_closes, "exit_closes": exit_closes, "credit": round(credit, 4),
           "exit_cost": round(exit_cost, 4), "risk": risk, "qty": qty, "traded": qty >= 1,
           "gross": gross, "fees": fees, "slippage": slippage, "pnl": round(gross - fees - slippage, 2),
           "price": event.get("price"), "reaction_close": event.get("reaction_close")}
    out["win"] = out["traded"] and out["pnl"] > 0
    if event.get("price") and event.get("reaction_close") is not None:
        out["actual_move_pct"] = round(100 * abs(event["reaction_close"] - event["price"]) / event["price"], 4)
    st = event.get("straddle")
    if isinstance(st, dict):
        st = close("atm_call", entry, st.get("call")) + close("atm_put", entry, st.get("put"))
    elif st is None and "atm_call" in bars and "atm_put" in bars:
        st = close("atm_call", entry) + close("atm_put", entry)
    if st is not None and event.get("price"):
        out["straddle"] = round(float(st), 4)
        out["implied_move_pct"] = round(implied_move_pct(float(st), event["price"]), 4)
    return out


def aggregate(results):
    """SCORER: trades, win rate with a Wilson 95% interval, average win, average
    loss, profit factor, worst loss and total pnl over the traded events."""
    pnls = [r["pnl"] for r in results if r.get("traded")]
    wins, losses = [p for p in pnls if p > 0], [p for p in pnls if p <= 0]
    lo, hi = wilson(len(wins), len(pnls))
    return {"trades": len(pnls), "wins": len(wins), "win_rate": len(wins) / len(pnls) if pnls else None,
            "win_rate_95": (round(lo, 4), round(hi, 4)),
            "avg_win": round(sum(wins) / len(wins), 2) if wins else None,
            "avg_loss": round(sum(losses) / len(losses), 2) if losses else None,
            "profit_factor": (round(sum(wins) / -sum(losses), 3) if losses and sum(losses) < 0
                              else (math.inf if wins else None)),
            "worst_loss": round(min(losses), 2) if losses else None, "total_pnl": round(sum(pnls), 2)}


# --------------------------------------------------------------------- CLI

def _json(obj):
    print(json.dumps(obj, indent=2, default=str))


def _fmt(v, nd=2):
    return "n/a" if v is None else f"{v:.{nd}f}"


def _moves_arg(s):
    """--history-moves a,b,c,d -> [floats], or a DataError."""
    if not s:
        return None
    try:
        return [float(x) for x in s.split(",") if x.strip()]
    except ValueError:
        raise DataError(f"--history-moves {s!r} is not a comma-separated list of numbers")


def run_candidates(args):
    today = _date(args.date)
    prices = load_prices(args.prices) if args.prices else None
    picked, skipped = candidates(load_calendar(args.calendar), today, prices)
    if args.json:
        _json({"date": today, "candidates": picked, "skipped": skipped})
        return
    print(f"{today}: {len(picked)} candidate(s)")
    for c in picked:
        price = f"  price {c['price']:.2f}" if c["price"] is not None else ""
        print(f"  {c['symbol']:6s} reports {c['report_date']} {c['timing']}  reaction day {c['reaction_day']}{price}")
    for s in skipped:
        print(f"  skip {s['symbol']:6s} reports {s['report_date']} {s['timing']}: {s['reason']}")


def run_moves(args):
    reports = load_calendar(args.results)
    symbol = args.symbol or (reports[0]["symbol"] if reports else None)
    if not symbol:
        raise DataError(f"no reports in {args.results}; pass --symbol")
    out = history_moves(reports, load_daily_closes(args.bars, symbol), _date(args.date), symbol)
    if args.json:
        _json(out)
        return
    print(f"{out['symbol']} before {out['date']}: {out['note']}")
    for m in out["moves"]:
        print(f"  {m['report_date']} {m['timing']}: {m['from_date']} {m['from_close']:.2f} -> "
              f"{m['reaction_day']} {m['to_close']:.2f}  move {m['move_pct']:.2f}%")
    for s in out["skipped"]:
        print(f"  skip {s['report_date']} {s['timing']}: {s['reason']}")
    print(f"--history-moves {out['history_moves'] or '(none)'}")


def run_build(args):
    params = Params(max_loss=args.max_loss)
    chain = load_chain(args.chain, args.symbol)
    book = load_book(args.instruments, args.quotes, args.symbol)
    reports = load_calendar(args.calendar) if args.calendar else None
    out = build(args.symbol, args.price, _date(args.date), _date(args.report_date),
                args.timing, chain, book, params, _moves_arg(args.history_moves), reports)
    if args.json:
        _json(out)
        return
    s = out
    print(f"{s['symbol']} on {s['date']} (reports {s['report_date']} {s['timing']}): {s['decision']}  ({s['reason']})")
    if "expiration" in s:
        print(f"  price {s['price']:.2f}  reaction day {s['reaction_day']}  expiration {s['expiration']}")
    if "straddle" in s:
        print(f"  ATM {s['atm_strike']:g}  straddle {s['straddle']:.2f}  implied move {s['implied_move_pct']:.2f}%")
    for side in ("short_put", "short_call"):
        if side in s:
            q = s[side]
            print(f"  {side.replace('_', ' ')} {q['strike']:g}: bid {q['bid']:.2f} ask {q['ask']:.2f} mid {q['mid']:.3f} "
                  f"spread {q['spread_pct']:.1f}%  delta {_fmt(q['delta'])}  OI {q['open_interest']}  vol {q['volume']}")
    for w in s["widths"]:
        line = f"  ${w['width']:g} wings: long put {w['long_put']:g} / long call {w['long_call']:g}"
        if "mid_credit" in w:
            line += (f"  mid {w['mid_credit']:.3f} natural {w['natural_credit']:.2f} limit {w['limit_credit']:.2f} "
                     f"(tick {w['tick']:g}) roi {_fmt(100 * w['roi'] if w['roi'] is not None else None, 1)}%  "
                     f"risk ${w['risk']:.0f}  qty {w['qty']}")
        if "second_price" in w:
            line += f"  floor {w['floor_credit']:.2f}  second {w['second_price']:.2f} x {w['second_qty']}"
        status = "PASS" if w["ok"] else "FAIL " + "; ".join(f"{f['check']}: {f['detail']}" for f in w["failed"])
        print(f"{line}  -> {status}")
    if "history" in s:
        print(f"  history: {s['history']['note']}")
    if s["condor"]:
        c = s["condor"]
        print(f"  condor: SELL {c['qty']} x {c['symbol']} {c['expiration']} put {c['short_put']:g}/{c['long_put']:g} "
              f"call {c['short_call']:g}/{c['long_call']:g}  limit credit {c['credit']:.2f}  "
              f"risk ${c['risk']:.0f} per condor, max loss ${c['max_loss']:.0f}")
        second = (f"second order {c['second_price']:.2f} x {c['second_qty']} (risk ${c['second_risk']:.0f}, "
                  f"max loss ${c['second_max_loss']:.0f})" if c["second_price"] < c["credit"] and c["second_qty"] >= 1
                  else "no second order (one tick down would breach the floor or the cap)")
        print(f"  tick {c['tick']:g}  floor credit {c['floor_credit']:.2f}  {second}")


def run_rank(args):
    builds = []
    for path in args.builds:
        b = _load(path)
        if not isinstance(b, dict) or "decision" not in b:
            raise DataError(f"{path} is not a saved build output")
        builds.append(b)
    out = rank(builds)
    if args.json:
        _json(out)
        return
    print(f"PICK: {out['pick'] or 'none'}")
    for i, r in enumerate(out["ranked"], 1):
        print(f"  {i}. {r['symbol']:6s} roi {100 * r['roi']:.1f}%  natural {r['natural_credit']:.2f}  "
              f"${r['width']:g} wings  credit {r['credit']:.2f} x {r['qty']}  max loss ${r['max_loss']:.0f}")
    for r in out["no_trade"]:
        print(f"  no trade {r['symbol']}: {r['reason']}")


def _exit_args(args):
    """The exit_decision inputs shared by `exit` and `buyback`."""
    now = dt.datetime.combine(_date(args.date), _time(args.time))
    return now, _date(args.reaction_day), _date(args.expiration), _time(args.close)


def _print_exit(out):
    print(f"{out['action']}  ({out['reason']})")
    print(f"  {out['time']} ET  reaction day {out['reaction_day']}  expiration {out['expiration']}  "
          f"close {out['close']}  credit {_fmt(out['credit'])}  target {_fmt(out['profit_target'])}  "
          f"buyback {_fmt(out['buyback_cost'])}")
    if out["flag"]:
        print(f"  FLAG: {out['flag']}")


def run_exit(args):
    now, rd, exp, close = _exit_args(args)
    condor = {"credit": args.credit, "short_put": args.short_put, "short_call": args.short_call}
    out = exit_decision(now, rd, exp, args.price, condor, args.buyback, Params(profit_take=args.profit_take), close)
    if args.json:
        _json(out)
        return
    _print_exit(out)


def run_buyback(args):
    legs = load_legs_by_id(args.instruments, args.quotes)
    shorts, longs = [], []
    for ids, into, side in ((args.short, shorts, "short"), (args.long, longs, "long")):
        for iid in ids:
            if iid not in legs:
                raise DataError(f"{side} leg {iid} is not in the instruments file(s)")
            into.append(legs[iid])
    ticks = next((l.ticks for l in shorts + longs if l.ticks), None)
    if ticks is None and args.chain:
        ticks = load_chain(args.chain, shorts[0].symbol).ticks
    if ticks is None:
        raise DataError("no min_ticks in the instruments file(s); pass --chain")
    natural, mid = closing_debits(shorts, longs)
    out = closing_prices(natural, mid, ticks, args.previous)
    out["legs"] = {"short": [leg_report(l) for l in shorts], "long": [leg_report(l) for l in longs]}
    if args.time or args.date or args.reaction_day or args.expiration:
        if not (args.time and args.date and args.reaction_day and args.expiration):
            raise DataError("the decision needs --time, --date, --reaction-day and --expiration together")
        now, rd, exp, close = _exit_args(args)
        put_strikes = sorted(l.strike for l in shorts if l.kind == "put")
        call_strikes = sorted(l.strike for l in shorts if l.kind == "call")
        condor = {"credit": args.credit, "short_put": put_strikes[0] if put_strikes else None,
                  "short_call": call_strikes[0] if call_strikes else None}
        out["decision"] = exit_decision(now, rd, exp, args.price, condor, natural, Params(profit_take=args.profit_take), close)
    if args.json:
        _json(out)
        return
    for side in ("short", "long"):
        for q in out["legs"][side]:
            print(f"  {side:5s} strike {q['strike']:g}: bid {_fmt(q['bid'])} ask {_fmt(q['ask'])}  id {q['id']}")
    print(f"natural debit {natural:.2f}  mid debit {mid:.4f}  tick {out['tick']:g}")
    print(f"first price {out['first_price']:.2f}  re-price {_fmt(out['reprice'])}  final price {out['final_price']:.2f}")
    if "decision" in out:
        _print_exit(out["decision"])


def run_score(args):
    try:
        with open(args.events) as f:
            events = json.load(f)
    except OSError as e:
        raise DataError(f"cannot read {args.events}: {e.strerror or e}")
    except ValueError as e:
        raise DataError(f"{args.events} is not JSON: {e}")
    bars = load_bars_dir(args.bars)
    results, errors = [], []
    for e in events:
        try:
            results.append(score_event(e, bars))
        except DataError as err:
            errors.append({"symbol": e.get("symbol"), "entry_date": e.get("entry_date"), "error": str(err)})
    agg = aggregate(results)
    if args.json:
        _json({"events": results, "errors": errors, "aggregate": agg})
        return
    for r in results:
        print(f"  {str(r['symbol']):6s} {r['entry_date']} -> {r['reaction_day']}  ${r['width']:g} wings  credit {r['credit']:.2f} "
              f"exit {r['exit_cost']:.2f}  qty {r['qty']}  pnl {r['pnl']:+.2f}  {'WIN' if r['win'] else 'LOSS'}")
    for e in errors:
        print(f"  skip {e['symbol']} {e['entry_date']}: {e['error']}")
    lo, hi = agg["win_rate_95"]
    print(f"trades {agg['trades']}  wins {agg['wins']}  win rate {_fmt(100 * agg['win_rate'] if agg['win_rate'] is not None else None, 1)}% "
          f"(95% {100 * lo:.1f}-{100 * hi:.1f}%)  avg win {_fmt(agg['avg_win'])}  avg loss {_fmt(agg['avg_loss'])}  "
          f"profit factor {_fmt(agg['profit_factor'])}  worst loss {_fmt(agg['worst_loss'])}  total {agg['total_pnl']:+.2f}")


def _add_exit_timing(parser, required):
    parser.add_argument("--time", required=required, help="now, HH:MM ET")
    parser.add_argument("--date", required=required, help="today, YYYY-MM-DD")
    parser.add_argument("--reaction-day", required=required)
    parser.add_argument("--expiration", required=required)
    parser.add_argument("--close", default="16:00", help="today's close, HH:MM ET (13:00 on a half-day)")
    parser.add_argument("--credit", type=float, help="credit received per condor; omit when unknown")
    parser.add_argument("--price", type=float, help="current underlying price, for the report")
    parser.add_argument("--profit-take", type=float, default=Params.profit_take)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("candidates", help="symbols whose report makes today the entry day")
    c.add_argument("--calendar", required=True, help="saved get_earnings_calendar output")
    c.add_argument("--date", required=True, help="today, YYYY-MM-DD")
    c.add_argument("--prices", nargs="+", help="saved get_equity_quotes output(s), to apply min_price")
    c.add_argument("--json", action="store_true")

    m = sub.add_parser("moves", help="past post-earnings moves for --history-moves")
    m.add_argument("--results", required=True, help="saved get_earnings_results output")
    m.add_argument("--bars", required=True, help="saved get_equity_historicals or TradingView get-ohlcv output")
    m.add_argument("--symbol", help="the symbol (default: the one in the results file)")
    m.add_argument("--date", required=True, help="today, YYYY-MM-DD; only reports before it count")
    m.add_argument("--json", action="store_true")

    b = sub.add_parser("build", help="pick expiration, strikes, wings, limit credit and quantity")
    b.add_argument("--symbol", required=True)
    b.add_argument("--price", type=float, required=True, help="current underlying price")
    b.add_argument("--date", required=True, help="today, YYYY-MM-DD")
    b.add_argument("--report-date", required=True)
    b.add_argument("--timing", choices=["am", "pm"], required=True)
    b.add_argument("--chain", required=True, help="saved get_option_chains output")
    b.add_argument("--instruments", nargs="+", required=True, help="saved get_option_instruments output(s)")
    b.add_argument("--quotes", nargs="+", required=True, help="saved get_option_quotes output(s)")
    b.add_argument("--calendar", help="saved earnings output; the report must be listed there and verified")
    b.add_argument("--history-moves", help="comma-separated past post-earnings moves, percent of price")
    b.add_argument("--max-loss", type=float, default=Params.max_loss)
    b.add_argument("--json", action="store_true")

    r = sub.add_parser("rank", help="rank saved build outputs: ROI, then natural credit, then symbol")
    r.add_argument("builds", nargs="+", help="saved `build --json` outputs")
    r.add_argument("--json", action="store_true")

    x = sub.add_parser("exit", help="HOLD or CLOSE_ALL for an open condor")
    _add_exit_timing(x, required=True)
    x.add_argument("--buyback", type=float, help="current cost to buy the condor back (natural debit)")
    x.add_argument("--short-put", type=float)
    x.add_argument("--short-call", type=float)
    x.add_argument("--json", action="store_true")

    k = sub.add_parser("buyback", help="closing debits and prices from saved quotes, and the exit decision")
    k.add_argument("--quotes", nargs="+", required=True, help="saved get_option_quotes output(s) for the legs")
    k.add_argument("--instruments", nargs="+", required=True, help="saved get_option_instruments output(s) for the legs")
    k.add_argument("--short", nargs="+", required=True, help="instrument ids of the short legs")
    k.add_argument("--long", nargs="+", required=True, help="instrument ids of the long legs")
    k.add_argument("--previous", type=float, help="the previous order's price, for the re-price")
    k.add_argument("--chain", help="saved get_option_chains output, if the instruments carry no min_ticks")
    _add_exit_timing(k, required=False)
    k.add_argument("--json", action="store_true")

    s = sub.add_parser("score", help="research scorer over saved option historicals")
    s.add_argument("--events", required=True, help="JSON list of events (see score_event)")
    s.add_argument("--bars", required=True, help="directory of saved get_option_historicals outputs")
    s.add_argument("--json", action="store_true")

    args = p.parse_args(argv)
    runners = {"candidates": run_candidates, "moves": run_moves, "build": run_build, "rank": run_rank,
               "exit": run_exit, "buyback": run_buyback, "score": run_score}
    try:
        runners[args.cmd](args)
    except DataError as e:
        print(f"NO TRADE: Data check failed: {e}")
        return 1
    except (OSError, KeyError, ValueError, TypeError) as e:
        print(f"NO TRADE: Data check failed: {type(e).__name__}: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
