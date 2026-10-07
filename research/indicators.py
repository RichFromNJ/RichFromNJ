"""TradingView's built-in indicators, rebuilt from price history with TradingView's default settings.

TradingView's connector only reports today's indicator values (screener / technicals rating), so to
backtest them every indicator is recomputed here from the daily bars it supplies. Each entry in
SIGNALS turns one indicator into a bullish and a bearish condition, following the rules TradingView
uses in its Technical Ratings where it has one, and the indicator's textbook reading otherwise.
"""
import numpy as np
import pandas as pd


def rma(s, n):
    """Wilder's moving average (TradingView ta.rma): seeded with the SMA of the first n values."""
    s = pd.Series(s, dtype=float)
    out = np.full(len(s), np.nan)
    v = s.values
    start = np.argmax(~np.isnan(v)) if (~np.isnan(v)).any() else len(v)
    if start + n > len(v):
        return pd.Series(out, index=s.index)
    out[start + n - 1] = np.nanmean(v[start:start + n])
    for i in range(start + n, len(v)):
        out[i] = (out[i - 1] * (n - 1) + v[i]) / n
    return pd.Series(out, index=s.index)


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def sma(s, n):
    return s.rolling(n).mean()


def wma(s, n):
    w = np.arange(1, n + 1)
    return s.rolling(n).apply(lambda x: np.dot(x, w) / w.sum(), raw=True)


def rsi(c, n=14):
    d = c.diff()
    up, dn = rma(d.clip(lower=0), n), rma((-d).clip(lower=0), n)
    return 100 - 100 / (1 + up / dn)


def streaks(c):
    """Consecutive up (+n) or down (-n) closes; 0 after an unchanged close."""
    cv = np.asarray(c, dtype=float)
    streak = np.zeros(len(cv))
    for i in range(1, len(cv)):
        if cv[i] > cv[i - 1]:
            streak[i] = streak[i - 1] + 1 if streak[i - 1] > 0 else 1
        elif cv[i] < cv[i - 1]:
            streak[i] = streak[i - 1] - 1 if streak[i - 1] < 0 else -1
    return streak


def connors_rsi(c):
    """Connors RSI(3, 2, 100): the average of RSI(3) of price, RSI(2) of the up/down streak, and the
    percent rank of today's 1-day return among the previous 100."""
    streak = streaks(c)
    c = pd.Series(np.asarray(c, dtype=float), index=getattr(c, "index", None))
    rank = c.pct_change().rolling(101).apply(lambda x: (x[:-1] < x[-1]).mean() * 100, raw=True)
    return (rsi(c, 3) + rsi(pd.Series(streak, index=c.index), 2) + rank) / 3


def true_range(d):
    pc = d.c.shift(1)
    return pd.concat([d.h - d.l, (d.h - pc).abs(), (d.l - pc).abs()], axis=1).max(axis=1)


def dmi(d, n=14):
    up, dn = d.h.diff(), -d.l.diff()
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = rma(true_range(d), n)
    pdi = 100 * rma(pd.Series(plus, index=d.index), n) / tr
    mdi = 100 * rma(pd.Series(minus, index=d.index), n) / tr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi)
    return rma(dx, n), pdi, mdi


def stoch(d, n=14, k=3, s=3):
    raw = 100 * (d.c - d.l.rolling(n).min()) / (d.h.rolling(n).max() - d.l.rolling(n).min())
    kk = sma(raw, k)
    return kk, sma(kk, s)


def build(d, vix=None):
    """All indicator columns for one symbol's daily bars (columns o, h, l, c, v)."""
    f = pd.DataFrame(index=d.index)
    c, h, l, o, v = d.c, d.h, d.l, d.o, d.v.astype(float)
    hl2, hlc3 = (h + l) / 2, (h + l + c) / 3
    f["c"], f["h"], f["l"] = c, h, l
    # --- Technical Ratings oscillators
    f["rsi14"] = rsi(c, 14)
    f["stoch_k"], f["stoch_d"] = stoch(d)
    tp = hlc3
    md = tp.rolling(20).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True)
    f["cci20"] = (tp - sma(tp, 20)) / (0.015 * md)
    f["adx14"], f["pdi14"], f["mdi14"] = dmi(d, 14)
    f["ao"] = sma(hl2, 5) - sma(hl2, 34)
    f["mom10"] = c - c.shift(10)
    f["macd"] = ema(c, 12) - ema(c, 26)
    f["macd_sig"] = ema(f.macd, 9)
    r14 = f.rsi14
    srsi = 100 * (r14 - r14.rolling(14).min()) / (r14.rolling(14).max() - r14.rolling(14).min())
    f["srsi_k"] = sma(srsi, 3)
    f["srsi_d"] = sma(f.srsi_k, 3)
    f["wr14"] = -100 * (h.rolling(14).max() - c) / (h.rolling(14).max() - l.rolling(14).min())
    e13 = ema(c, 13)
    f["bbp"] = (h - e13) + (l - e13)
    bp = c - pd.concat([l, c.shift(1)], axis=1).min(axis=1)
    tr = true_range(d)
    avg = lambda n: bp.rolling(n).sum() / tr.rolling(n).sum()  # noqa: E731
    f["uo"] = 100 * (4 * avg(7) + 2 * avg(14) + avg(28)) / 7
    # --- Technical Ratings moving averages
    for n in (10, 20, 30, 50, 100, 200):
        f[f"sma{n}"], f[f"ema{n}"] = sma(c, n), ema(c, n)
    f["sma5"] = sma(c, 5)
    f["ichi_base"] = (h.rolling(26).max() + l.rolling(26).min()) / 2
    f["ichi_conv"] = (h.rolling(9).max() + l.rolling(9).min()) / 2
    f["ichi_lead_a"] = ((f.ichi_conv + f.ichi_base) / 2).shift(25)
    f["ichi_lead_b"] = ((h.rolling(52).max() + l.rolling(52).min()) / 2).shift(25)
    f["vwma20"] = (c * v).rolling(20).sum() / v.rolling(20).sum()
    f["hma9"] = wma(2 * wma(c, 4) - wma(c, 9), 3)
    # --- other built-ins
    f["rsi2"] = rsi(c, 2)
    f["rsi5"] = rsi(c, 5)
    mid, sd = sma(c, 20), c.rolling(20).std(ddof=0)
    f["bb_pct"] = (c - (mid - 2 * sd)) / (4 * sd)
    f["bb_width"] = 4 * sd / mid
    atr10 = rma(tr, 10)
    f["kc_low"], f["kc_up"] = ema(c, 20) - 2 * atr10, ema(c, 20) + 2 * atr10
    f["dc_low"], f["dc_up"] = l.rolling(20).min(), h.rolling(20).max()
    f["atr14"] = rma(tr, 14)
    mf = tp * v
    pos = mf.where(tp > tp.shift(1), 0).rolling(14).sum()
    neg = mf.where(tp < tp.shift(1), 0).rolling(14).sum()
    f["mfi14"] = 100 - 100 / (1 + pos / neg)
    mfm = ((c - l) - (h - c)) / (h - l).replace(0, np.nan)
    f["cmf20"] = (mfm * v).rolling(20).sum() / v.rolling(20).sum()
    f["obv"] = (np.sign(c.diff()).fillna(0) * v).cumsum()
    f["roc9"] = 100 * (c / c.shift(9) - 1)
    t3 = ema(ema(ema(np.log(c), 18), 18), 18)
    f["trix18"] = 10000 * t3.diff()
    f["dpo21"] = c.shift(11) - sma(c, 21)
    f["aroon_up"] = 100 * h.rolling(15).apply(lambda x: np.argmax(x), raw=True) / 14
    f["aroon_dn"] = 100 * l.rolling(15).apply(lambda x: np.argmin(x), raw=True) / 14
    f["cmo9"] = 100 * (c.diff().clip(lower=0).rolling(9).sum() - (-c.diff()).clip(lower=0).rolling(9).sum()) / \
        c.diff().abs().rolling(9).sum()
    f["efi13"] = ema(c.diff() * v, 13)
    f["chop14"] = 100 * np.log10(tr.rolling(14).sum() / (h.rolling(14).max() - l.rolling(14).min())) / np.log10(14)
    vmp, vmm = (h - l.shift(1)).abs().rolling(14).sum(), (l - h.shift(1)).abs().rolling(14).sum()
    f["vi_plus"], f["vi_minus"] = vmp / tr.rolling(14).sum(), vmm / tr.rolling(14).sum()
    pc = c.diff()
    f["tsi"] = 100 * ema(ema(pc, 25), 13) / ema(ema(pc.abs(), 25), 13)
    f["crsi"] = connors_rsi(c)
    f["ibs"] = ((c - l) / (h - l)).where(h > l, 0.5)
    # Parabolic SAR (0.02, 0.02, 0.2)
    sar, bull, af, ep = np.zeros(len(c)), True, 0.02, h.iloc[0]
    sar[0] = l.iloc[0]
    hv, lv = h.values, l.values
    for i in range(1, len(c)):
        s = sar[i - 1] + af * (ep - sar[i - 1])
        if bull:
            s = min(s, lv[i - 1], lv[i - 2] if i > 1 else lv[i - 1])
            if lv[i] < s:
                bull, s, ep, af = False, ep, lv[i], 0.02
            elif hv[i] > ep:
                ep, af = hv[i], min(af + 0.02, 0.2)
        else:
            s = max(s, hv[i - 1], hv[i - 2] if i > 1 else hv[i - 1])
            if hv[i] > s:
                bull, s, ep, af = True, ep, hv[i], 0.02
            elif lv[i] < ep:
                ep, af = lv[i], min(af + 0.02, 0.2)
        sar[i] = s
    f["psar"] = sar
    # SuperTrend (10, 3)
    atr = rma(tr, 10).values
    cv = c.values
    ub, lb = (hl2 + 3 * atr).values, (hl2 - 3 * atr).values
    fu, fl, trend = ub.copy(), lb.copy(), np.ones(len(c))
    for i in range(1, len(c)):
        fu[i] = ub[i] if (ub[i] < fu[i - 1] or cv[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lb[i] if (lb[i] > fl[i - 1] or cv[i - 1] < fl[i - 1]) else fl[i - 1]
        trend[i] = 1 if cv[i] > fu[i - 1] else (-1 if cv[i] < fl[i - 1] else trend[i - 1])
    f["supertrend"] = trend
    f["ret1"] = 100 * c.pct_change()
    st = streaks(c)
    f["down_streak"] = pd.Series(np.where(st < 0, -st, 0), index=c.index)
    f["dist_sma200"] = 100 * (c / f.sma200 - 1)
    if vix is not None:
        vx = vix.reindex(d.index).ffill()
        f["vix"], f["vix9d"] = vx.vix, vx.vix9d
        f["vix_ma10"] = sma(f.vix, 10)
        f["vix_rsi2"] = rsi(f.vix, 2)
    f["rating"], f["rating_osc"], f["rating_ma"] = technical_rating(f)
    return f


def rising(s):
    return s > s.shift(1)


def falling(s):
    return s < s.shift(1)


def _up(f):
    return f.c > f.sma200


# Each signal: name -> (bullish condition, bearish condition). Conditions use only data up to the close.
SIGNALS = {
    # TradingView Technical Ratings rules
    "RSI(14) <30 rising / >70 falling": lambda f: (f.rsi14.lt(30) & rising(f.rsi14), f.rsi14.gt(70) & falling(f.rsi14)),
    "Stoch(14,3,3) <20 K>D / >80 K<D": lambda f: ((f.stoch_k < 20) & (f.stoch_d < 20) & (f.stoch_k > f.stoch_d),
                                                  (f.stoch_k > 80) & (f.stoch_d > 80) & (f.stoch_k < f.stoch_d)),
    "CCI(20) <-100 rising / >100 falling": lambda f: (f.cci20.lt(-100) & rising(f.cci20), f.cci20.gt(100) & falling(f.cci20)),
    "ADX(14) >20, +DI>-DI / -DI>+DI": lambda f: ((f.adx14 > 20) & (f.pdi14 > f.mdi14) & rising(f.adx14),
                                                 (f.adx14 > 20) & (f.mdi14 > f.pdi14) & rising(f.adx14)),
    "Awesome Osc >0 rising / <0 falling": lambda f: (f.ao.gt(0) & rising(f.ao), f.ao.lt(0) & falling(f.ao)),
    "Momentum(10) rising / falling": lambda f: (rising(f.mom10), falling(f.mom10)),
    "MACD above / below signal": lambda f: (f.macd > f.macd_sig, f.macd < f.macd_sig),
    "Stoch RSI <20 K>D in downtrend / >80 K<D in uptrend": lambda f: (
        ~_up(f) & (f.srsi_k < 20) & (f.srsi_d < 20) & (f.srsi_k > f.srsi_d),
        _up(f) & (f.srsi_k > 80) & (f.srsi_d > 80) & (f.srsi_k < f.srsi_d)),
    "Williams %R <-80 rising / >-20 falling": lambda f: (f.wr14.lt(-80) & rising(f.wr14), f.wr14.gt(-20) & falling(f.wr14)),
    "Bull Bear Power <0 rising, uptrend / >0 falling, downtrend": lambda f: (
        _up(f) & f.bbp.lt(0) & rising(f.bbp), ~_up(f) & f.bbp.gt(0) & falling(f.bbp)),
    "Ultimate Osc >70 / <30": lambda f: (f.uo > 70, f.uo < 30),
    **{f"Price vs SMA({n})": (lambda n: lambda f: (f.c > f[f"sma{n}"], f.c < f[f"sma{n}"]))(n) for n in (10, 20, 30, 50, 100, 200)},
    **{f"Price vs EMA({n})": (lambda n: lambda f: (f.c > f[f"ema{n}"], f.c < f[f"ema{n}"]))(n) for n in (10, 20, 30, 50, 100, 200)},
    "Ichimoku base line": lambda f: (f.c > f.ichi_base, f.c < f.ichi_base),
    "VWMA(20)": lambda f: (f.c > f.vwma20, f.c < f.vwma20),
    "Hull MA(9)": lambda f: (f.c > f.hma9, f.c < f.hma9),
    # Other TradingView built-ins: mean reversion
    "RSI(2) <10 / >90": lambda f: (f.rsi2 < 10, f.rsi2 > 90),
    "RSI(2) <5 / >95": lambda f: (f.rsi2 < 5, f.rsi2 > 95),
    "RSI(2) <10 in uptrend / >90 in downtrend": lambda f: (_up(f) & (f.rsi2 < 10), ~_up(f) & (f.rsi2 > 90)),
    "RSI(5) <20 / >80": lambda f: (f.rsi5 < 20, f.rsi5 > 80),
    "Connors RSI <10 / >90": lambda f: (f.crsi < 10, f.crsi > 90),
    "Connors RSI <10 in uptrend / >90 in downtrend": lambda f: (_up(f) & (f.crsi < 10), ~_up(f) & (f.crsi > 90)),
    "Bollinger %B <0 / >1": lambda f: (f.bb_pct < 0, f.bb_pct > 1),
    "Bollinger %B <0 in uptrend / >1 in downtrend": lambda f: (_up(f) & (f.bb_pct < 0), ~_up(f) & (f.bb_pct > 1)),
    "Keltner below lower / above upper": lambda f: (f.c < f.kc_low, f.c > f.kc_up),
    "Donchian(20) new low / new high": lambda f: (f.l <= f.dc_low, f.h >= f.dc_up),
    "MFI(14) <20 / >80": lambda f: (f.mfi14 < 20, f.mfi14 > 80),
    "CMF(20) >0.05 / <-0.05": lambda f: (f.cmf20 > 0.05, f.cmf20 < -0.05),
    "OBV above / below its 20-day avg": lambda f: (f.obv > sma(f.obv, 20), f.obv < sma(f.obv, 20)),
    "ROC(9) <-5 / >5": lambda f: (f.roc9 < -5, f.roc9 > 5),
    "TRIX(18) rising above 0 / falling below 0": lambda f: (f.trix18.gt(0) & rising(f.trix18), f.trix18.lt(0) & falling(f.trix18)),
    "DPO(21) <0 rising / >0 falling": lambda f: (f.dpo21.lt(0) & rising(f.dpo21), f.dpo21.gt(0) & falling(f.dpo21)),
    "Aroon up>70 & down<30 / reverse": lambda f: ((f.aroon_up > 70) & (f.aroon_dn < 30), (f.aroon_dn > 70) & (f.aroon_up < 30)),
    "Chande MO(9) <-50 / >50": lambda f: (f.cmo9 < -50, f.cmo9 > 50),
    "Elder Force Index(13) >0 / <0": lambda f: (f.efi13 > 0, f.efi13 < 0),
    "Vortex VI+ > VI- / reverse": lambda f: (f.vi_plus > f.vi_minus, f.vi_minus > f.vi_plus),
    "TSI(25,13) <-25 rising / >25 falling": lambda f: (f.tsi.lt(-25) & rising(f.tsi), f.tsi.gt(25) & falling(f.tsi)),
    "Parabolic SAR below / above price": lambda f: (f.c > f.psar, f.c < f.psar),
    "SuperTrend(10,3) up / down": lambda f: (f.supertrend > 0, f.supertrend < 0),
    "IBS <0.2 / >0.8": lambda f: (f.ibs < 0.2, f.ibs > 0.8),
    "3+ down days in uptrend / 3+ up days in downtrend": lambda f: (_up(f) & (f.down_streak >= 3), ~_up(f) & (f.ret1 > 0) & (f.ret1.shift(1) > 0) & (f.ret1.shift(2) > 0)),
    "Choppiness <38 (trending) with SMA50 direction": lambda f: ((f.chop14 < 38.2) & (f.c > f.sma50), (f.chop14 < 38.2) & (f.c < f.sma50)),
    # VIX (TradingView TVC:VIX, CBOE:VIX9D)
    "VIX 5% above 10-day avg, uptrend / VIX 5% below, downtrend": lambda f: (
        _up(f) & (f.vix > 1.05 * f.vix_ma10), ~_up(f) & (f.vix < 0.95 * f.vix_ma10)),
    "VIX RSI(2) >90 / <10": lambda f: (f.vix_rsi2 > 90, f.vix_rsi2 < 10),
    "VIX9D above VIX (inverted) / far below": lambda f: (f.vix9d > f.vix, f.vix9d < 0.85 * f.vix),
    # TradingView's overall Technical Rating (Recommend.All), rebuilt below
    "TV rating Strong Buy / Strong Sell": lambda f: (f.rating > 0.5, f.rating < -0.5),
    "TV rating Buy / Sell": lambda f: (f.rating > 0.1, f.rating < -0.1),
    "TV rating Sell in uptrend (buy the dip) / Buy in downtrend": lambda f: (_up(f) & (f.rating < -0.1), ~_up(f) & (f.rating > 0.1)),
}


def crosses_above(a, b):
    return (a > b) & (a.shift(1) <= b.shift(1))


def crosses_below(a, b):
    return (a < b) & (a.shift(1) >= b.shift(1))


def technical_rating(f):
    """TradingView's Technical Rating ('Recommend.All') rebuilt: the average of the oscillator votes
    and the moving-average votes, each +1 (buy), 0 (neutral) or -1 (sell), using TradingView's
    published rules (crossovers where TradingView uses crossovers)."""
    up = f.c > f.sma50
    k, dd = f.stoch_k, f.stoch_d
    ao_saucer_up = (f.ao > 0) & (f.ao.shift(1) < f.ao.shift(2)) & (f.ao > f.ao.shift(1))
    ao_saucer_dn = (f.ao < 0) & (f.ao.shift(1) > f.ao.shift(2)) & (f.ao < f.ao.shift(1))
    votes = [
        (f.rsi14.lt(30) & rising(f.rsi14), f.rsi14.gt(70) & falling(f.rsi14)),
        ((k < 20) & crosses_above(k, dd), (k > 80) & crosses_below(k, dd)),
        (f.cci20.lt(-100) & rising(f.cci20), f.cci20.gt(100) & falling(f.cci20)),
        ((f.adx14 > 20) & crosses_above(f.pdi14, f.mdi14), (f.adx14 > 20) & crosses_below(f.pdi14, f.mdi14)),
        (crosses_above(f.ao, 0 * f.ao) | ao_saucer_up, crosses_below(f.ao, 0 * f.ao) | ao_saucer_dn),
        (rising(f.mom10), falling(f.mom10)),
        (f.macd > f.macd_sig, f.macd < f.macd_sig),
        (~up & (f.srsi_k < 20) & (f.srsi_d < 20) & crosses_above(f.srsi_k, f.srsi_d),
         up & (f.srsi_k > 80) & (f.srsi_d > 80) & crosses_below(f.srsi_k, f.srsi_d)),
        (f.wr14.lt(-80) & rising(f.wr14), f.wr14.gt(-20) & falling(f.wr14)),
        (up & f.bbp.lt(0) & rising(f.bbp), ~up & f.bbp.gt(0) & falling(f.bbp)),
        (f.uo > 70, f.uo < 30),
    ]
    osc = pd.concat([b.astype(int) - s.astype(int) for b, s in votes], axis=1).mean(axis=1)
    ma = [np.sign(f.c - f[f"{kind}{n}"]) for n in (10, 20, 30, 50, 100, 200) for kind in ("sma", "ema")]
    ma += [np.sign(f.c - f.vwma20), np.sign(f.c - f.hma9)]
    lead_a, lead_b = f.ichi_lead_a, f.ichi_lead_b
    ichi = np.where((f.c > lead_a) & (f.c > lead_b) & (f.ichi_conv > f.ichi_base) & (lead_a > lead_b), 1,
                    np.where((f.c < lead_a) & (f.c < lead_b) & (f.ichi_conv < f.ichi_base) & (lead_a < lead_b), -1, 0))
    ma.append(pd.Series(ichi, index=f.index))
    m = pd.concat(ma, axis=1).mean(axis=1)
    return (osc + m) / 2, osc, m
