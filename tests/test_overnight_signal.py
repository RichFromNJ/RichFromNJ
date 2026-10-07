import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import overnight_signal as sig  # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
MON = dt.date(2026, 10, 5)


def run(source, file, date, o, h, l, last):
    if source == "robinhood":
        history, _ = sig.load_robinhood(os.path.join(FIX, file), "EEM")
    else:
        history, _ = sig.load_tradingview(os.path.join(FIX, file))
    today = sig.todays_bar(date, o, h, l, last)
    return sig.decide(sig.build_series(history, today)), history, today


class KnownValues(unittest.TestCase):
    def test_robinhood_monday_3_53pm(self):
        v, _, _ = run("robinhood", "eem_robinhood_2026-10-05.json", MON, 68.4669, 68.87, 68.3584, 68.705)
        self.assertAlmostEqual(v["rsi2"], 93.17, places=2)
        self.assertAlmostEqual(v["adx"], 23.17, places=2)
        self.assertAlmostEqual(v["plus_di"], 42.32, places=2)
        self.assertAlmostEqual(v["minus_di"], 23.35, places=2)
        self.assertAlmostEqual(v["trix"], 0.2564, places=4)
        self.assertAlmostEqual(v["y_adx"], 21.74, places=2)
        self.assertEqual(v["y_position"], "below both")
        self.assertEqual(v["position"], "below both")
        self.assertEqual((v["signal"], v["rule"][:6]), ("PUTS", "Rule 4"))

    def test_tradingview_monday_close_matches_tradingview_levels(self):
        v, history, today = run("tradingview", "eem_tradingview_2026-10-05.json", MON, 68.45, 68.875, 68.3584, 68.73)
        self.assertAlmostEqual(v["rsi2"], 93.27, places=2)
        self.assertAlmostEqual(v["adx"], 23.19, places=2)
        self.assertAlmostEqual(v["plus_di"], 42.37, places=2)
        self.assertAlmostEqual(v["minus_di"], 23.33, places=2)
        self.assertAlmostEqual(v["trix_tradingview_scale"], 25.89, places=2)
        # Values TradingView itself reported for AMEX:EEM at Monday's close.
        c = sig.context_levels(history, today)
        self.assertAlmostEqual(c["bb2_low"], 65.4827, places=3)
        self.assertAlmostEqual(c["bb2_high"], 69.4203, places=3)
        self.assertAlmostEqual(c["ema20"], 67.4199, places=3)
        self.assertAlmostEqual(c["ema50"], 66.8771, places=3)
        self.assertAlmostEqual(c["sma200"], 63.0733, places=3)


class DataChecks(unittest.TestCase):
    def test_placeholder_bar_is_dropped(self):
        _, dropped = sig.load_robinhood(os.path.join(FIX, "eem_robinhood_2026-10-05.json"), "EEM")
        self.assertIn(MON, dropped)

    def test_missing_yesterday_blocks_trade(self):
        with self.assertRaisesRegex(sig.DataError, "yesterday"):
            run("robinhood", "eem_robinhood_2026-10-05.json", dt.date(2026, 10, 6), 68.8, 69, 68.5, 68.9)

    def test_no_trade_day_before_a_holiday(self):
        self.assertTrue(sig.holiday_tomorrow(dt.date(2026, 11, 25)))   # Thanksgiving
        self.assertTrue(sig.holiday_tomorrow(dt.date(2026, 12, 31)))   # New Year's Day
        self.assertTrue(sig.holiday_tomorrow(dt.date(2027, 3, 25)))    # Good Friday
        self.assertFalse(sig.holiday_tomorrow(MON))
        with self.assertRaisesRegex(sig.DataError, "holiday list"):
            sig.holiday_tomorrow(dt.date(2028, 1, 3))

    def test_previous_trading_day_skips_weekend_and_holiday(self):
        self.assertEqual(sig.previous_trading_day(MON), dt.date(2026, 10, 2))
        self.assertEqual(sig.previous_trading_day(dt.date(2026, 9, 8)), dt.date(2026, 9, 4))


class Selection(unittest.TestCase):
    def test_expiration(self):
        listed = [dt.date(2026, 10, d) for d in (5, 7, 9)]
        self.assertEqual(sig.choose_expiration(MON, listed), (dt.date(2026, 10, 7), "target"))
        wed = dt.date(2026, 10, 7)
        self.assertEqual(sig.choose_expiration(wed, [dt.date(2026, 10, 12)]), (dt.date(2026, 10, 12), "fallback"))
        self.assertIsNone(sig.choose_expiration(wed, [dt.date(2026, 10, 13)]))
        self.assertIsNone(sig.choose_expiration(dt.date(2026, 10, 9), listed))

    def test_strike_candidates(self):
        eem = [float(s) for s in range(52, 84)]
        self.assertEqual(sig.strike_candidates("PUTS", 68.705, eem), {"OTM": 68, "ITM": 69})
        self.assertEqual(sig.strike_candidates("CALLS", 68.705, eem), {"OTM": 69, "ITM": 68})
        # A strike exactly at the price counts as ITM.
        self.assertEqual(sig.strike_candidates("PUTS", 68.0, eem), {"OTM": 67, "ITM": 68})
        self.assertEqual(sig.strike_candidates("CALLS", 68.0, eem), {"OTM": 69, "ITM": 68})
        self.assertEqual(sig.strike_candidates("CALLS", 90.0, eem), {"OTM": None, "ITM": 83})

    def test_moneyness(self):
        self.assertEqual(sig.moneyness("PUTS", 68, 68.705), "OTM")
        self.assertEqual(sig.moneyness("PUTS", 69, 68.705), "ITM")
        self.assertEqual(sig.moneyness("CALLS", 69, 68.705), "OTM")
        self.assertEqual(sig.moneyness("CALLS", 68, 68.705), "ITM")

    def test_size_by_type(self):
        self.assertEqual(sig.quantity(0.62, "ITM"), 3)
        self.assertEqual(sig.quantity(0.62, "OTM"), 3)
        self.assertEqual(sig.quantity(2.45, "ITM"), 1)
        self.assertEqual(sig.quantity(2.46, "ITM"), 0)
        self.assertEqual(sig.quantity(2.45, "OTM"), 1)
        self.assertEqual(sig.quantity(2.46, "OTM"), 0)

    def test_size_counts_spend_already_made_today(self):
        self.assertEqual(sig.quantity(0.58, "ITM", spent=186.0), 1)
        self.assertEqual(sig.quantity(0.40, "OTM", spent=200.0), 1)
        self.assertEqual(sig.quantity(0.40, "OTM", spent=245.0), 0)

    def test_adx_on_a_di_line_is_not_between(self):
        self.assertEqual(sig.adx_position(20.0, 20.0, 30.0), "on a DI line")


if __name__ == "__main__":
    unittest.main()
