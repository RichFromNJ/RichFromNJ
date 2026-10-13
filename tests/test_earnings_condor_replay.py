"""Pins the headline result of research/earnings_condor_replay.py on the saved 2026 data."""
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "research"))
import earnings_condor_replay as rp  # noqa: E402
import earnings_condor as ec  # noqa: E402

DATA = os.path.join(ROOT, "research", "data", "earnings_condor_2026")


class Replay2026(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import glob
        files = sorted(glob.glob(os.path.join(DATA, "events", "*.json")))
        cls.rows = [rp.replay_event(f) for f in files]
        cls.traded = [r for r in cls.rows if r["status"] == "traded"]

    def test_counts(self):
        self.assertEqual(len(self.rows), 28)
        self.assertEqual(len(self.traded), 24)
        skipped = sorted(r["symbol"] for r in self.rows if r["status"] != "traded")
        self.assertEqual(skipped, ["BX", "PG", "PG", "PG"])

    def test_headline(self):
        agg = ec.aggregate([{"traded": True, "pnl": r["pnl"]} for r in self.traded])
        self.assertEqual(agg["wins"], 12)
        self.assertAlmostEqual(agg["total_pnl"], -875.0, places=2)
        self.assertAlmostEqual(agg["profit_factor"], 0.387, places=3)

    def test_every_condor_respects_the_cap_before_costs(self):
        for r in self.traded:
            self.assertLessEqual(r["max_loss"], 250.0 + 1e-9, r["symbol"])
            self.assertLessEqual(r["short_put"], r["price"] - r["straddle"] + 1e-9)
            self.assertGreaterEqual(r["short_call"], r["price"] + r["straddle"] - 1e-9)


if __name__ == "__main__":
    unittest.main()
