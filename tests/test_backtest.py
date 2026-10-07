import datetime as dt
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "research"))

try:
    import backtest as bt
except ImportError:  # numpy / pandas / scipy not installed
    bt = None
import overnight_signal as sig  # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


@unittest.skipIf(bt is None, "research dependencies missing")
class Indicators(unittest.TestCase):
    def test_rsi_matches_the_live_rules(self):
        history, _ = sig.load_robinhood(os.path.join(FIX, "eem_robinhood_2026-10-05.json"), "EEM")
        closes = [b.c for b in history if b.date < dt.date(2026, 10, 5)]
        live = sig.rsi(closes + [68.705])[-1]
        au, ad = bt.wilder_state(bt.np.array(closes))
        self.assertAlmostEqual(bt.rsi_next(au[-1], ad[-1], closes[-1], 68.705), live, places=9)

    def test_wilson_interval(self):
        lo, hi = bt.wilson(75, 100)
        self.assertAlmostEqual(lo, 0.6569, places=3)
        self.assertAlmostEqual(hi, 0.8245, places=3)

    def test_black_scholes_put_call_parity(self):
        S, K, T, v = 68.27, 67.0, 17 / 365, 0.22
        lhs = bt.bs(S, K, T, v, call=True) - bt.bs(S, K, T, v, call=False)
        self.assertAlmostEqual(lhs, S - K * bt.math.exp(-bt.R * T), places=9)


@unittest.skipIf(bt is None, "research dependencies missing")
class ProposedRoutine(unittest.TestCase):
    """Pins the headline numbers in research/README.md."""

    @classmethod
    def setUpClass(cls):
        cls.long_run, cls.ytd_close, cls.ytd_345, cls.open_pos = bt.routine_results()

    def test_long_run(self):
        s = bt.stats(self.long_run)
        self.assertEqual((s["n"], s["wins"]), (167, 125))
        self.assertGreater(s["lo"], 65.0)  # lower end of the 95% interval clears 65%
        self.assertGreater(s["pf"], 1.0)

    def test_2026_at_345pm(self):
        s = bt.stats(self.ytd_345)
        self.assertEqual((s["n"], s["wins"]), (13, 11))
        self.assertEqual(list(self.ytd_345.sym[:3]), ["QQQ", "SPY", "IWM"])
        self.assertIsNone(self.open_pos)

    def test_never_holds_two_positions(self):
        t = self.long_run.sort_values("entry_date")
        self.assertTrue((t.entry_date.values[1:] >= t.exit_date.values[:-1]).all())
        self.assertTrue((t.days <= bt.MAX_HOLD).all())


@unittest.skipIf(bt is None, "research dependencies missing")
class Baseline(unittest.TestCase):
    def test_live_rules_are_a_coin_flip_in_2026(self):
        t = bt.live_rules_2026("EEM")
        s = bt.stats(t.assign(ret=t.ret_0945, days=1))
        self.assertEqual(s["n"], 147)
        self.assertLess(s["win"], 55.0)


if __name__ == "__main__":
    unittest.main()
