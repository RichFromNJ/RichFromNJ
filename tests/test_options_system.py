import datetime as dt
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "research"))

try:
    import pandas as pd
    import backtest as bt
    import indicators as ind
    import paper
    import spreads as sp
    import system
except ImportError:  # numpy / pandas / scipy not installed
    system = None


@unittest.skipIf(system is None, "research dependencies missing")
class TradingViewIndicators(unittest.TestCase):
    """Values TradingView's technicals snapshot reported for AMEX:SPY (1D) after the Oct 6, 2026 close."""

    @classmethod
    def setUpClass(cls):
        cls.f = ind.build(bt.daily("SPY"), bt.vix()).iloc[-1]

    def test_oscillators(self):
        self.assertAlmostEqual(self.f.rsi14, 62.0005, places=3)
        self.assertAlmostEqual(self.f.stoch_k, 87.0647, places=3)
        self.assertAlmostEqual(self.f.stoch_d, 75.0284, places=3)
        self.assertAlmostEqual(self.f.cci20, 189.5599, places=3)
        self.assertAlmostEqual(self.f.adx14, 10.6874, places=3)
        self.assertAlmostEqual(self.f.ao, 3.9059, places=3)
        self.assertAlmostEqual(self.f.mom10, 5.71, places=3)
        self.assertAlmostEqual(self.f.macd, 2.2981, places=3)
        self.assertAlmostEqual(self.f.macd_sig, 1.2671, places=3)

    def test_moving_averages(self):
        self.assertAlmostEqual(self.f.ema20, 767.7267, places=3)
        self.assertAlmostEqual(self.f.sma200, 721.4893, places=3)
        self.assertAlmostEqual(self.f.hma9, 774.2247, places=3)
        self.assertAlmostEqual(self.f.vwma20, 765.2468, places=3)

    def test_rating_within_one_vote(self):
        # TradingView: 0.5121212 (oscillators +1/11, moving averages 14/15); ours differs only in the Ichimoku vote.
        self.assertAlmostEqual(self.f.rating_osc, 1 / 11, places=6)
        self.assertLessEqual(abs(self.f.rating - 0.5121212121212121), 1 / 30 + 1e-9)


@unittest.skipIf(system is None, "research dependencies missing")
class OptionModel(unittest.TestCase):
    def test_model_close_to_robinhood_quotes(self):
        # Robinhood marks for SPY 2026-10-23 puts after the Oct 6 close.
        m = system.markets()["SPY"]
        d = dt.date(2026, 10, 6)
        S, T = m.c[m.pos[d]], 17 / 365
        for K, real in ((740, 0.725), (750, 1.16), (760, 1.995), (770, 3.685)):
            self.assertLess(abs(m.price(d, S, K, T, call=False) / real - 1), 0.10)


@unittest.skipIf(system is None, "research dependencies missing")
class SystemResults(unittest.TestCase):
    """Pins the numbers in research/README.md."""

    def test_periods(self):
        M = system.markets()
        expect = {"train": (43, 40), "validate": (31, 27), "holdout": (2, 2)}
        for label, period in sp.PERIODS.items():
            t = system.simulate(M, period)
            self.assertEqual((len(t), int((t.pnl > 0).sum())), expect[label], label)

    def test_whole_history_and_risk_cap(self):
        t = system.simulate(system.markets(), (dt.date(2007, 1, 1), bt.YTD[1]))
        self.assertEqual((len(t), int((t.pnl > 0).sum())), (76, 69))
        self.assertTrue((t.max_loss <= 250).all())
        self.assertGreaterEqual(t.pnl.min(), -250)
        self.assertTrue((t.entry_date.values[1:] > t.exit_date.values[:-1]).all())  # one at a time

    def test_still_profitable_with_40pct_lower_credits(self):
        t = system.simulate(system.markets(), (dt.date(2007, 1, 1), bt.YTD[1]))
        pnl = t.pnl - 0.40 * t.entry * 100
        self.assertGreater((pnl > 0).mean(), 0.65)
        self.assertGreater(pnl.sum(), 0)


@unittest.skipIf(system is None, "research dependencies missing")
class PaperRunner(unittest.TestCase):
    def test_connors_rsi_matches_research(self):
        d = bt.daily("SPY")
        f = ind.build(d, bt.vix())
        closes = pd.Series(d.c.tolist())
        self.assertAlmostEqual(float(ind.connors_rsi(closes).iloc[-1]), float(f.crsi.iloc[-1]), places=9)

    def test_pick_respects_the_250_cap(self):
        chain = [dict(id=str(k), strike=k, bid=b, ask=b + 0.02, delta=dl)
                 for k, b, dl in [(770, 3.68, -0.293), (767, 3.0, -0.24), (766, 2.8, -0.23), (765, 2.68, -0.222)]]
        p = paper.pick_spread(chain)
        self.assertEqual((p["short_strike"], p["long_strike"], p["width"]), (770, 767, 3))
        self.assertLessEqual(p["max_loss"], 250)

    def test_no_spread_when_nothing_fits(self):
        chain = [dict(id="a", strike=700, bid=3.0, ask=3.1, delta=-0.3), dict(id="b", strike=695, bid=1.0, ask=1.1, delta=-0.2)]
        self.assertIsNone(paper.pick_spread(chain))  # only a $5-wide spread exists and it risks $310

    def test_calendar(self):
        self.assertEqual(paper.target_expiration(dt.date(2026, 10, 7)), dt.date(2026, 10, 30))
        self.assertEqual(paper.next_trading_day(dt.date(2026, 11, 25)), dt.date(2026, 11, 27))


if __name__ == "__main__":
    unittest.main()


try:
    import growth
    import universe
except ImportError:
    growth = None


@unittest.skipIf(growth is None, "research dependencies missing")
class WiderScanAndGrowth(unittest.TestCase):
    """Pins research/README.md section 7 (uses the saved research/universe_trades.csv)."""

    @classmethod
    def setUpClass(cls):
        cls.t = growth.load()

    def test_kept_etfs_after_2018(self):
        x = self.t[self.t.entry_date >= dt.date(2019, 1, 1)]
        self.assertEqual(len(set(self.t.sym)), 17)
        self.assertEqual((len(x), int((x.R > 0).sum())), (256, 216))

    def test_no_90_day_window_reaches_3000(self):
        starts = [d.date() for d in pd.bdate_range(dt.date(2019, 1, 1), dt.date(2026, 7, 7))][::3]
        ends = [growth.run_window(self.t, s, 90, "f", 1.0)[0] for s in starts]
        self.assertLess(max(ends), 1200)

    def test_universe_list(self):
        self.assertEqual(len(universe.UNIVERSE), 28)
        self.assertNotIn("EEM", universe.UNIVERSE)
        self.assertTrue(set(universe.KEEP) <= set(universe.UNIVERSE))
