import contextlib
import datetime as dt
import io
import json
import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import earnings_condor as ec  # noqa: E402
import overnight_signal as sig  # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
D = dt.date
TUE, WED, THU = D(2026, 10, 13), D(2026, 10, 14), D(2026, 10, 15)   # MS reports Wed 10/14 am
EXP = D(2026, 10, 16)
TICKS = ec.Ticks(0.01, 0.05, 3.00)
P = ec.Params()


def mk_book(legs, exp=EXP):
    """legs: (kind, strike, bid, ask, delta, oi, volume) -> book dict."""
    book = {}
    for kind, strike, bid, ask, delta, oi, vol in legs:
        book[(kind, exp, float(strike))] = ec.Leg(f"{kind}{strike}", "X", exp, float(strike), kind,
                                                 bid, ask, delta, 0.5, oi, vol)
    return book


def ladder_book(long_1=(0.39, 0.41), long_25=(0.09, 0.11), with_2=False):
    """Price 100, ATM straddle 4.00 -> shorts 96/104. $1 wings pay too little, $2 wings
    are unlisted and $2.5 wings pass."""
    legs = [("call", 100, 1.95, 2.05, 0.50, 1000, 500), ("put", 100, 1.95, 2.05, -0.50, 1000, 500),
            ("put", 96, 0.50, 0.54, -0.20, 500, 100), ("call", 104, 0.50, 0.54, 0.20, 500, 100),
            ("put", 95, *long_1, -0.15, 500, 100), ("call", 105, *long_1, 0.15, 500, 100),
            ("put", 93.5, *long_25, -0.08, 500, 100), ("call", 106.5, *long_25, 0.08, 500, 100),
            ("put", 91, 0.04, 0.06, -0.04, 500, 100), ("call", 109, 0.04, 0.06, 0.04, 500, 100)]
    if with_2:
        legs += [("put", 94, 0.19, 0.21, -0.1, 500, 100), ("call", 106, 0.19, 0.21, 0.1, 500, 100)]
    return mk_book(legs)


CHAIN = ec.Chain("X", "chain", [EXP, D(2026, 10, 23)], TICKS)


class Calendar(unittest.TestCase):
    def test_holiday_list_matches_overnight_signal(self):
        self.assertEqual(ec.NYSE_HOLIDAYS, sig.NYSE_HOLIDAYS)
        self.assertEqual(ec.previous_trading_day(D(2026, 11, 27)), D(2026, 11, 25))

    def test_reaction_day(self):
        self.assertEqual(ec.reaction_day(WED, "am"), WED)                       # am: the report day itself
        self.assertEqual(ec.reaction_day(TUE, "pm"), WED)                       # pm: next trading day
        self.assertEqual(ec.reaction_day(D(2026, 10, 16), "pm"), D(2026, 10, 19))   # Friday pm -> Monday
        self.assertEqual(ec.reaction_day(D(2026, 11, 25), "pm"), D(2026, 11, 27))   # skips Thanksgiving
        with self.assertRaisesRegex(ec.DataError, "timing"):
            ec.reaction_day(WED, None)
        with self.assertRaisesRegex(ec.DataError, "holiday list"):
            ec.reaction_day(D(2028, 1, 3), "pm")

    def test_is_candidate(self):
        self.assertTrue(ec.is_candidate(TUE, WED, "am"))             # sell Tue for Wed am
        self.assertTrue(ec.is_candidate(TUE, TUE, "pm"))             # sell Tue for Tue pm
        self.assertFalse(ec.is_candidate(TUE, TUE, "am"))            # already reported
        self.assertFalse(ec.is_candidate(TUE, WED, "pm"))            # tomorrow's pm is tomorrow's trade
        self.assertFalse(ec.is_candidate(TUE, THU, "am"))
        self.assertTrue(ec.is_candidate(D(2026, 10, 16), D(2026, 10, 19), "am"))     # Fri for Mon am
        self.assertTrue(ec.is_candidate(D(2026, 11, 25), D(2026, 11, 27), "am"))     # Wed for Fri am (holiday Thu)
        self.assertFalse(ec.is_candidate(D(2026, 11, 25), D(2026, 11, 26), "am"))
        self.assertFalse(ec.is_candidate(TUE, WED, None))
        self.assertFalse(ec.is_candidate(TUE, WED, "am", verified=False))

    def test_candidates_from_fixture_calendar(self):
        reports = ec.load_calendar(os.path.join(FIX, "earnings_calendar_2026-10-13.json"))
        prices = ec.load_prices(os.path.join(FIX, "ms_equity_quote_2026-10-13.json"))
        picked, skipped = ec.candidates(reports, TUE, prices)
        self.assertEqual([c["symbol"] for c in picked], ["MS"])
        self.assertEqual((picked[0]["reaction_day"], picked[0]["timing"], picked[0]["price"]), (WED, "am", 190.01))
        reasons = {s["symbol"]: s["reason"] for s in skipped}
        self.assertIn("already reported", reasons["JPM"])
        self.assertIn("not verified", reasons["PNFP"])
        self.assertIn("no price", reasons["BAC"])
        # Without a prices file every verified am-tomorrow / pm-today name qualifies.
        picked, _ = ec.candidates(reports, TUE)
        self.assertIn("BAC", [c["symbol"] for c in picked])
        self.assertNotIn("JPM", [c["symbol"] for c in picked])

    def test_candidates_apply_min_price_and_timing_null(self):
        reports = [{"symbol": "CHEAP", "report_date": WED, "timing": "am", "verified": True},
                   {"symbol": "NOTIME", "report_date": WED, "timing": None, "verified": True}]
        picked, skipped = ec.candidates(reports, TUE, {"CHEAP": 9.99, "NOTIME": 50.0})
        self.assertEqual(picked, [])
        self.assertIn("below 10", skipped[0]["reason"])
        self.assertIn("timing unknown", skipped[1]["reason"])


class Expiration(unittest.TestCase):
    def test_first_listed_on_or_after_reaction_day_within_8_days(self):
        self.assertEqual(ec.choose_expiration(WED, [D(2026, 10, 16), D(2026, 10, 23)]), D(2026, 10, 16))
        self.assertEqual(ec.choose_expiration(WED, [D(2026, 10, 9), D(2026, 10, 16)]), D(2026, 10, 16))
        self.assertEqual(ec.choose_expiration(WED, [WED]), WED)                      # same-day expiration allowed
        self.assertEqual(ec.choose_expiration(WED, [D(2026, 10, 22)]), D(2026, 10, 22))  # 8 days: in
        self.assertIsNone(ec.choose_expiration(WED, [D(2026, 10, 23)]))             # 9 days: out
        self.assertIsNone(ec.choose_expiration(WED, [D(2026, 10, 9)]))


class Strikes(unittest.TestCase):
    def test_atm_strike_nearest_tie_lower(self):
        self.assertEqual(ec.atm_strike(190.01, [187.5, 190, 192.5]), 190)
        self.assertEqual(ec.atm_strike(191.25, [187.5, 190, 192.5]), 190)      # exact tie -> lower
        self.assertEqual(ec.atm_strike(191.26, [187.5, 190, 192.5]), 192.5)
        with self.assertRaises(ec.DataError):
            ec.atm_strike(100, [])

    def test_straddle_and_implied_move(self):
        book = mk_book([("call", 190, 4.05, 4.30, 0.51, 1, 1), ("put", 190, 3.85, 4.30, -0.49, 1, 1)])
        s = ec.straddle(book, EXP, 190.0)
        self.assertAlmostEqual(s, 8.25)
        self.assertAlmostEqual(ec.implied_move_pct(s, 190.01), 4.3419, places=4)
        book[("put", EXP, 190.0)].bid = 0.0
        with self.assertRaisesRegex(ec.DataError, "no usable quote"):
            ec.straddle(book, EXP, 190.0)
        with self.assertRaisesRegex(ec.DataError, "not listed"):
            ec.straddle(book, EXP, 195.0)

    def test_short_strikes_round_outward_each_side(self):
        ms = [175, 177.5, 180, 182.5, 185, 187.5, 190, 192.5, 195, 197.5, 200, 202.5, 205]
        self.assertEqual(ec.short_strikes(190.01, 8.25, ms), (180, 200))       # 181.76 -> 180, 198.26 -> 200
        self.assertEqual(ec.short_strikes(100, 5, [95, 100, 105]), (95, 105))   # exactly one straddle: taken
        self.assertEqual(ec.short_strikes(100, 4.9, [94, 95, 96, 100, 104, 105, 106]), (95, 105))
        self.assertEqual(ec.short_strikes(100, 4.9, [96, 100, 104]), (None, None))
        self.assertEqual(ec.short_strikes(100, 5, [90, 100], [100, 110]), (90, 110))   # separate put/call strikes

    def test_round_down_to_tick_each_side_of_the_cutoff(self):
        self.assertEqual(ec.round_down_tick(2.987, TICKS), 2.98)
        self.assertEqual(ec.round_down_tick(2.999, TICKS), 2.99)
        self.assertEqual(ec.round_down_tick(3.00, TICKS), 3.00)
        self.assertEqual(ec.round_down_tick(3.049, TICKS), 3.00)
        self.assertEqual(ec.round_down_tick(3.07, TICKS), 3.05)
        self.assertEqual(ec.round_down_tick(0.655, TICKS), 0.65)
        self.assertEqual(ec.round_down_tick(0.83 + 0.955 - 0.535 - 0.595, TICKS), 0.65)
        self.assertEqual(ec.round_down_tick(0.29 - 1e-12, TICKS), 0.29)    # float noise is not a tick
        self.assertEqual(ec.round_down_tick(0.2899, TICKS), 0.28)


class Wings(unittest.TestCase):
    def build(self, book, **kw):
        params = kw.pop("params", P)
        return ec.build("X", 100.0, TUE, WED, "am", CHAIN, book, params, **kw)

    def test_ladder_fails_1_skips_2_passes_2_5(self):
        out = self.build(ladder_book())
        self.assertEqual(out["decision"], "TRADE")
        self.assertEqual([w["width"] for w in out["widths"]], [1.0, 2.0, 2.5])      # stops at the first pass
        w1, w2, w25 = out["widths"]
        self.assertEqual([f["check"] for f in w1["failed"]], ["roi"])                 # 0.24 / 0.76 = 31.6%
        self.assertAlmostEqual(w1["mid_credit"], 0.24)
        self.assertAlmostEqual(w1["natural_credit"], 0.18)                            # exactly 0.75 x mid: passes
        self.assertEqual([f["check"] for f in w2["failed"]], ["listed"])
        self.assertTrue(w25["ok"])
        c = out["condor"]
        self.assertEqual((c["short_put"], c["long_put"], c["short_call"], c["long_call"]), (96, 93.5, 104, 106.5))
        self.assertEqual((c["credit"], c["risk"], c["qty"], c["max_loss"]), (0.84, 166.0, 1, 166.0))
        self.assertAlmostEqual(c["roi"], 0.84 / 1.66, places=4)
        self.assertEqual(c["ids"]["long_put"], "put93.5")
        self.assertEqual(out["history"]["applied"], False)
        self.assertIn("skipped", out["history"]["note"])

    def test_natural_vs_mid_named(self):
        # Zero-bid long wings (buyable, ask 0.20): mid credit 0.84 but natural 1.00 - 0.40 = 0.60 < 0.75 x 0.84.
        out = self.build(ladder_book(long_25=(0.00, 0.20)), params=ec.Params(widths=(2.5,)))
        self.assertEqual(out["decision"], "NO TRADE")
        self.assertEqual([f["check"] for f in out["widths"][0]["failed"]], ["natural_vs_mid"])
        self.assertIn("natural_vs_mid", out["reason"])

    def test_short_leg_checks_named(self):
        wide = ec.Leg("a", "X", EXP, 96.0, "put", 0.40, 0.60, -0.20, 0.5, 500, 100)       # 40% spread
        self.assertEqual([f["check"] for f in ec.leg_checks(wide)], ["spread"])
        thin = ec.Leg("b", "X", EXP, 96.0, "put", 0.50, 0.54, -0.20, 0.5, 99, 14)        # vol < 15 and OI < 100
        self.assertEqual([f["check"] for f in ec.leg_checks(thin)], ["liquidity"])
        self.assertEqual(ec.leg_checks(ec.Leg("c", "X", EXP, 96.0, "put", 0.50, 0.54, -0.20, 0.5, 100, 0)), [])
        self.assertEqual(ec.leg_checks(ec.Leg("d", "X", EXP, 96.0, "put", 0.50, 0.54, -0.20, 0.5, 0, 15)), [])
        hot = ec.Leg("e", "X", EXP, 96.0, "put", 0.50, 0.54, -0.36, 0.5, 500, 100)
        self.assertEqual([f["check"] for f in ec.leg_checks(hot)], ["delta"])
        nodelta = ec.Leg("f", "X", EXP, 96.0, "put", 0.50, 0.54, None, 0.5, 500, 100)
        self.assertEqual([f["check"] for f in ec.leg_checks(nodelta)], ["delta"])
        # A failing short leg fails every width, by name, in the build report.
        book = ladder_book()
        book[("call", EXP, 104.0)].delta = 0.40
        out = self.build(book)
        self.assertEqual(out["decision"], "NO TRADE")
        self.assertTrue(all("delta" in [f["check"] for f in w["failed"]] for w in out["widths"]))
        self.assertEqual(out["short_leg_failed"][0]["leg"], "call 104 2026-10-16")

    def test_qty_and_the_250_cap(self):
        # $5 wings for a 2.00 credit risk $300 per condor: qty 0 -> NO TRADE, named "qty".
        book = mk_book([("call", 100, 1.95, 2.05, 0.5, 1000, 500), ("put", 100, 1.95, 2.05, -0.5, 1000, 500),
                        ("put", 96, 1.20, 1.24, -0.20, 500, 100), ("call", 104, 1.20, 1.24, 0.20, 500, 100),
                        ("put", 91, 0.20, 0.24, -0.05, 500, 100), ("call", 109, 0.20, 0.24, 0.05, 500, 100)])
        out = self.build(book, params=ec.Params(widths=(5.0,)))
        w = out["widths"][0]
        self.assertEqual((w["limit_credit"], w["risk"], w["qty"]), (2.0, 300.0, 0))
        self.assertEqual([f["check"] for f in w["failed"]], ["qty"])
        self.assertEqual(out["decision"], "NO TRADE")
        # A 2.60 credit risks $240: one condor fits; $240 x 1 <= $250.
        for s in (96.0, 104.0):
            book[(("put" if s < 100 else "call"), EXP, s)].bid = 1.50
            book[(("put" if s < 100 else "call"), EXP, s)].ask = 1.54
        out = self.build(book, params=ec.Params(widths=(5.0,)))
        c = out["condor"]
        self.assertEqual((c["credit"], c["risk"], c["qty"]), (2.6, 240.0, 1))
        self.assertLessEqual(c["risk"] * c["qty"], 250)
        # Raising the cap buys more.
        out = self.build(book, params=ec.Params(widths=(5.0,), max_loss=1000))
        self.assertEqual(out["condor"]["qty"], 4)

    def test_history_filter(self):
        h = ec.history_filter([1.2, 3.4, 0.8, 2.0], 2.5)
        self.assertEqual((h["applied"], h["within"], h["ok"]), (True, 3, True))
        h = ec.history_filter([1.2, 3.4, 0.8, 2.0], 1.0)
        self.assertEqual((h["within"], h["ok"]), (1, False))
        h = ec.history_filter([-1.2, 3.4, 0.8], 2.5)                        # fewer than 4: skipped, and says so
        self.assertEqual((h["applied"], h["ok"]), (False, True))
        self.assertIn("skipped", h["note"])
        h = ec.history_filter([9, 9, 9, 9, 1.0, 1.0, 1.0, 1.0], 2.0)        # only the last 4 count
        self.assertEqual((h["within"], h["ok"]), (4, True))
        self.assertEqual(ec.history_filter([2.5, 2.5, 2.5, 9], 2.5)["ok"], True)   # equal counts as within
        # In a build the filter vetoes a condor that passed every other check.
        out = self.build(ladder_book(), history_moves=[5, 6, 7, 1])
        self.assertEqual(out["decision"], "NO TRADE")
        self.assertTrue(out["reason"].startswith("history filter failed"))
        self.assertTrue(out["widths"][-1]["ok"])

    def test_build_data_checks(self):
        out = ec.build("X", 9.5, TUE, WED, "am", CHAIN, ladder_book())
        self.assertIn("below min_price", out["reason"])
        out = ec.build("X", 100.0, TUE, THU, "am", CHAIN, ladder_book())
        self.assertIn("not a candidate", out["reason"])
        out = ec.build("X", 100.0, TUE, WED, "am", ec.Chain("X", "c", [D(2026, 10, 23)], TICKS), ladder_book())
        self.assertIn("no expiration", out["reason"])
        out = ec.build("X", 100.0, TUE, WED, "am", CHAIN, ladder_book(), ec.Params(widths=(3.0,)))
        self.assertEqual([f["check"] for f in out["widths"][0]["failed"]], ["listed"])


class Exit(unittest.TestCase):
    CONDOR = ec.Condor("MS", EXP, 180, 177.5, 200, 202.5, 2.5, 0.36, 1)

    def decide(self, day, hhmm, buyback, exp=EXP, price=185.0):
        now = dt.datetime.combine(day, dt.time.fromisoformat(hhmm))
        return ec.exit_decision(now, WED, exp, price, self.CONDOR, buyback)

    def test_reaction_day_timeline(self):
        self.assertEqual(self.decide(WED, "09:39", 0.01)["action"], "HOLD")
        cheap = self.decide(WED, "09:41", 0.09)
        self.assertEqual((cheap["action"], cheap["profit_target"]), ("CLOSE_ALL", 0.108))
        self.assertEqual(self.decide(WED, "09:41", 0.108)["action"], "CLOSE_ALL")     # at the target
        self.assertEqual(self.decide(WED, "09:41", 0.11)["action"], "HOLD")           # a tick above it
        self.assertEqual(self.decide(WED, "09:41", 0.30)["action"], "HOLD")
        self.assertEqual(self.decide(WED, "15:29", 0.90)["action"], "HOLD")
        self.assertEqual(self.decide(WED, "15:30", 0.90)["action"], "CLOSE_ALL")
        self.assertEqual(self.decide(WED, "15:55", 0.01)["action"], "CLOSE_ALL")
        self.assertEqual(self.decide(WED, "10:00", None)["action"], "HOLD")           # no buyback quote: wait
        self.assertEqual(self.decide(WED, "10:00", 0.05)["price_vs_shorts"], "inside")

    def test_before_and_after_the_reaction_day(self):
        before = self.decide(TUE, "15:45", 0.01)
        self.assertEqual((before["action"], before["flag"]), ("HOLD", None))
        after = self.decide(THU, "09:35", 0.90)
        self.assertEqual(after["action"], "CLOSE_ALL")
        self.assertIn("should not happen", after["flag"])

    def test_never_hold_into_expiration(self):
        self.assertEqual(self.decide(EXP, "09:40", 0.90)["action"], "CLOSE_ALL")
        self.assertEqual(self.decide(EXP, "14:00", 0.90)["action"], "CLOSE_ALL")
        # Reaction day is also the expiration day: the 09:40 start still applies.
        now = dt.datetime.combine(WED, dt.time(9, 39))
        self.assertEqual(ec.exit_decision(now, WED, WED, 185.0, self.CONDOR, 0.90)["action"], "HOLD")
        now = dt.datetime.combine(WED, dt.time(9, 40))
        self.assertEqual(ec.exit_decision(now, WED, WED, 185.0, self.CONDOR, 0.90)["action"], "CLOSE_ALL")
        past = self.decide(D(2026, 10, 19), "10:00", 0.90)
        self.assertEqual((past["action"], past["flag"]), ("CLOSE_ALL", "past expiration; should not happen"))

    def test_dict_condor_and_profit_take_param(self):
        now = dt.datetime.combine(WED, dt.time(10, 0))
        out = ec.exit_decision(now, WED, EXP, None, {"credit": 1.0}, 0.45, ec.Params(profit_take=0.5))
        self.assertEqual((out["action"], out["profit_target"]), ("CLOSE_ALL", 0.5))
        self.assertNotIn("price_vs_shorts", out)


class LiveMSFixture(unittest.TestCase):
    """Robinhood's MS chain, 2026-10-16 contracts and Monday-close quotes, saved 2026-10-13
    before the open. MS reports Wednesday 2026-10-14 before the open."""

    @classmethod
    def setUpClass(cls):
        cls.chain = ec.load_chain(os.path.join(FIX, "ms_chain_2026-10-13.json"), "MS")
        cls.book = ec.load_book([os.path.join(FIX, f"ms_instruments_2026-10-16_{k}.json") for k in ("puts", "calls")],
                                [os.path.join(FIX, f"ms_quotes_2026-10-16_{k}.json") for k in ("puts", "calls")], "MS")
        cls.out = ec.build("MS", 190.01, TUE, WED, "am", cls.chain, cls.book)

    def test_chain_and_book(self):
        self.assertEqual(self.chain.chain_id, "962effc1-0b52-4648-b577-846096301fa7")
        self.assertEqual(self.chain.expirations[0], EXP)
        self.assertEqual((self.chain.ticks.below_tick, self.chain.ticks.above_tick, self.chain.ticks.cutoff_price),
                         (0.01, 0.05, 3.0))
        self.assertEqual(len(ec.listed_strikes(self.book, "put", EXP)), 56)
        quoted = [l for l in self.book.values() if l.quoted]
        self.assertEqual(len(quoted), 26)
        put190 = self.book[("put", EXP, 190.0)]
        self.assertEqual((put190.bid, put190.ask, put190.open_interest, put190.volume), (3.85, 4.30, 2556, 308))
        self.assertAlmostEqual(put190.delta, -0.485976)

    def test_strikes_sit_one_straddle_away_and_risk_is_capped(self):
        o = self.out
        self.assertEqual((o["reaction_day"], o["expiration"], o["atm_strike"]), (WED, EXP, 190.0))
        s = o["straddle"]
        self.assertAlmostEqual(s, self.book[("call", EXP, 190.0)].mid + self.book[("put", EXP, 190.0)].mid, places=4)
        self.assertLessEqual(o["short_put"]["strike"], 190.01 - s)
        self.assertGreaterEqual(o["short_call"]["strike"], 190.01 + s)
        self.assertEqual(o["short_put"]["strike"] + 2.5, ec.short_strikes(190.01, s, ec.listed_strikes(self.book, "put", EXP))[0] + 2.5)
        self.assertEqual([w["width"] for w in o["widths"]][:3], [1.0, 2.0, 2.5])
        for w in o["widths"]:
            self.assertTrue(w["ok"] or w["failed"], w)
            if w.get("qty", 0) >= 1:
                self.assertLessEqual(w["risk"] * w["qty"], 250.0)
            if "mid_credit" in w:
                self.assertLessEqual(w["limit_credit"], w["mid_credit"] + 1e-9)
                self.assertEqual(w["limit_credit"], ec.round_down_tick(w["mid_credit"], self.chain.ticks))
        if o["condor"]:
            c = o["condor"]
            self.assertLessEqual(c["risk"] * c["qty"], 250.0)
            self.assertLessEqual(c["short_put"], 190.01 - s)
            self.assertGreaterEqual(c["short_call"], 190.01 + s)
            self.assertEqual((c["short_put"] - c["long_put"], c["long_call"] - c["short_call"]), (c["width"], c["width"]))

    def test_monday_close_values(self):
        """Pins the numbers in the saved quotes: ATM 190, straddle 8.25, shorts 180/200;
        $1 and $2 wings unlisted, $2.5 wings fail natural-vs-mid, $5 wings fail ROI and the cap."""
        o = self.out
        self.assertAlmostEqual(o["straddle"], 8.25)
        self.assertAlmostEqual(o["implied_move_pct"], 4.3419, places=3)
        self.assertEqual((o["short_put"]["strike"], o["short_call"]["strike"]), (180.0, 200.0))
        self.assertEqual(o["short_leg_failed"], [])
        checks = {w["width"]: sorted({f["check"] for f in w["failed"]}) for w in o["widths"]}
        self.assertEqual(checks, {1.0: ["listed"], 2.0: ["listed"], 2.5: ["natural_vs_mid"], 5.0: ["qty", "roi"]})
        w25 = o["widths"][2]
        self.assertEqual((w25["mid_credit"], w25["natural_credit"], w25["limit_credit"], w25["risk"], w25["qty"]),
                         (0.655, 0.47, 0.65, 185.0, 1))
        self.assertEqual(w25["ids"]["short_put"], "adf1cfca-05f3-4e53-9e0f-92b779ddfcd1")
        self.assertEqual(o["decision"], "NO TRADE")
        # Loosening natural-vs-mid to 0.70 would make the $2.5 condor tradeable: 1 x $185 risk.
        loose = ec.build("MS", 190.01, TUE, WED, "am", self.chain, self.book, ec.Params(natural_vs_mid=0.70))
        self.assertEqual(loose["decision"], "TRADE")
        c = loose["condor"]
        self.assertEqual((c["short_put"], c["long_put"], c["short_call"], c["long_call"], c["credit"], c["qty"]),
                         (180.0, 177.5, 200.0, 202.5, 0.65, 1))
        self.assertLessEqual(c["max_loss"], 250.0)


class Scorer(unittest.TestCase):
    def bars(self, exit_closes):
        day = lambda d, c: {"begins_at": f"{d}T00:00:00Z", "open_price": str(c), "high_price": str(c),
                            "low_price": str(c), "close_price": str(c)}
        entry = {"sp": 0.60, "lp": 0.30, "sc": 0.50, "lc": 0.44}
        results = []
        for leg, c in entry.items():
            bars = [day("2026-10-12", 0.99), day("2026-10-13", c), day("2026-10-14", exit_closes[leg]),
                    dict(day("2026-10-15", 9.99), interpolated=True)]
            results.append({"instrument_id": leg, "occ_symbol": leg, "bars": bars})
        results.append({"instrument_id": "atmc", "bars": [day("2026-10-13", 2.10)]})
        results.append({"instrument_id": "atmp", "bars": [day("2026-10-13", 1.90)]})
        return {"data": {"results": results}}

    EVENT = {"symbol": "X", "entry_date": "2026-10-13", "reaction_day": "2026-10-14", "width": 1.0, "price": 100.0,
             "reaction_close": 101.5, "legs": {"short_put": "sp", "long_put": "lp", "short_call": "sc", "long_call": "lc"},
             "straddle": {"call": "atmc", "put": "atmp"}}

    def test_score_event_arithmetic(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "x.json"), "w") as f:
                json.dump(self.bars({"sp": 0.10, "lp": 0.02, "sc": 0.08, "lc": 0.01}), f)
            bars = ec.load_bars_dir(d)
        self.assertNotIn(D(2026, 10, 15), bars["sp"])                       # interpolated bar dropped
        r = ec.score_event(self.EVENT, bars)
        self.assertAlmostEqual(r["credit"], 0.36)                            # 0.60 + 0.50 - 0.30 - 0.44
        self.assertAlmostEqual(r["exit_cost"], 0.15)                         # 0.10 + 0.08 - 0.02 - 0.01
        self.assertEqual((r["risk"], r["qty"]), (64.0, 3))                   # floor(250 / 64)
        self.assertAlmostEqual(r["gross"], 63.0)                             # 0.21 x 100 x 3
        self.assertAlmostEqual(r["fees"], 1.20)                              # 4 legs x 2 sides x 3 x 0.05
        self.assertAlmostEqual(r["slippage"], 24.0)                          # 4 legs x 2 sides x 3 x 0.01 x 100
        self.assertAlmostEqual(r["pnl"], 37.80)
        self.assertTrue(r["win"] and r["traded"])
        self.assertAlmostEqual(r["straddle"], 4.0)
        self.assertAlmostEqual(r["implied_move_pct"], 4.0)
        self.assertAlmostEqual(r["actual_move_pct"], 1.5)
        self.assertAlmostEqual(ec.score_event(dict(self.EVENT, qty=1), bars)["pnl"], 12.60)   # qty given: 21 - 0.40 - 8

    def test_loss_missing_bars_and_aggregate(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "x.json"), "w") as f:
                json.dump(self.bars({"sp": 0.70, "lp": 0.05, "sc": 0.30, "lc": 0.05}), f)
            bars = ec.load_bars_dir(d)
        loss = ec.score_event(self.EVENT, bars)
        self.assertAlmostEqual(loss["exit_cost"], 0.90)
        self.assertAlmostEqual(loss["pnl"], -162.0 - 1.20 - 24.0)
        self.assertFalse(loss["win"])
        with self.assertRaisesRegex(ec.DataError, "no 2026-10-20 bar"):
            ec.score_event(dict(self.EVENT, reaction_day="2026-10-20"), bars)
        with self.assertRaisesRegex(ec.DataError, "no bars for long_call"):
            ec.score_event(dict(self.EVENT, legs=dict(self.EVENT["legs"], long_call="zz")), bars)
        agg = ec.aggregate([loss, {"traded": True, "pnl": 37.80}, {"traded": False, "pnl": 0.0}])
        self.assertEqual((agg["trades"], agg["wins"], agg["win_rate"]), (2, 1, 0.5))
        self.assertEqual((agg["avg_win"], agg["avg_loss"], agg["worst_loss"]), (37.80, -187.20, -187.20))
        self.assertAlmostEqual(agg["profit_factor"], 37.80 / 187.20, places=3)
        self.assertAlmostEqual(agg["total_pnl"], -149.40)
        lo, hi = agg["win_rate_95"]
        self.assertAlmostEqual(lo, 0.0945, places=3)
        self.assertAlmostEqual(hi, 0.9055, places=3)
        self.assertIsNone(ec.aggregate([{"traded": True, "pnl": 37.80}])["worst_loss"])   # no losses: n/a, not the win
        self.assertEqual(ec.aggregate([{"traded": True, "pnl": 37.80}])["profit_factor"], math.inf)

    def test_bars_by_leg_name_as_raw_lists(self):
        """research/earnings_condor_check.py keys bars by leg name, as raw bar lists, and
        gives the straddle as a number and the quantity; both forms must score the same."""
        raw = self.bars({"sp": 0.10, "lp": 0.02, "sc": 0.08, "lc": 0.01})["data"]["results"]
        by_id = {r["instrument_id"]: r["bars"] for r in raw}                     # interpolated bars kept
        leg_bars = {"short_put": by_id["sp"], "long_put": by_id["lp"], "short_call": by_id["sc"],
                    "long_call": by_id["lc"], "atm_put": by_id["atmp"], "atm_call": by_id["atmc"]}
        event = dict(self.EVENT, straddle=4.0, qty=2, legs={l: "uuid-" + l for l in ec.LEGS})
        r = ec.score_event(event, leg_bars)
        self.assertEqual((r["qty"], r["credit"], r["exit_cost"]), (2, 0.36, 0.15))
        self.assertAlmostEqual(r["pnl"], 42.0 - 0.80 - 16.0)
        self.assertEqual(r["implied_move_pct"], 4.0)
        no_straddle = {k: v for k, v in event.items() if k != "straddle"}
        self.assertEqual(ec.score_event(no_straddle, leg_bars)["straddle"], 4.0)   # from the atm bars
        with self.assertRaisesRegex(ec.DataError, "no 2026-10-15 bar"):           # interpolated bar is dropped
            ec.score_event(dict(event, reaction_day="2026-10-15"), leg_bars)

    def test_wilson(self):
        lo, hi = ec.wilson(75, 100)
        self.assertAlmostEqual(lo, 0.6569, places=3)
        self.assertAlmostEqual(hi, 0.8245, places=3)
        self.assertEqual(ec.wilson(0, 0), (0.0, 0.0))


class CLI(unittest.TestCase):
    def run_cli(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = ec.main(list(argv))
        return rc, buf.getvalue()

    def test_candidates(self):
        rc, out = self.run_cli("candidates", "--calendar", os.path.join(FIX, "earnings_calendar_2026-10-13.json"),
                               "--date", "2026-10-13", "--prices", os.path.join(FIX, "ms_equity_quote_2026-10-13.json"), "--json")
        self.assertEqual(rc, 0)
        self.assertEqual([c["symbol"] for c in json.loads(out)["candidates"]], ["MS"])

    def test_build(self):
        argv = ["build", "--symbol", "MS", "--price", "190.01", "--date", "2026-10-13", "--report-date", "2026-10-14",
                "--timing", "am", "--chain", os.path.join(FIX, "ms_chain_2026-10-13.json"),
                "--instruments", os.path.join(FIX, "ms_instruments_2026-10-16_puts.json"), os.path.join(FIX, "ms_instruments_2026-10-16_calls.json"),
                "--quotes", os.path.join(FIX, "ms_quotes_2026-10-16_puts.json"), os.path.join(FIX, "ms_quotes_2026-10-16_calls.json"),
                "--history-moves", "1.2,3.4,0.8,2.0"]
        rc, out = self.run_cli(*argv, "--json")
        self.assertEqual(rc, 0)
        j = json.loads(out)
        self.assertEqual((j["decision"], j["atm_strike"], j["history"]["within"]), ("NO TRADE", 190.0, 4))
        rc, out = self.run_cli(*argv)
        self.assertIn("short put 180", out)
        self.assertIn("$2.5 wings", out)
        rc, out = self.run_cli(*argv[:-2], "--max-loss", "400", "--json")
        self.assertEqual(json.loads(out)["params"]["max_loss"], 400.0)

    def test_exit(self):
        rc, out = self.run_cli("exit", "--time", "09:41", "--date", "2026-10-14", "--reaction-day", "2026-10-14",
                               "--expiration", "2026-10-16", "--credit", "0.36", "--buyback", "0.09", "--json")
        self.assertEqual(json.loads(out)["action"], "CLOSE_ALL")
        rc, out = self.run_cli("exit", "--time", "09:41", "--date", "2026-10-14", "--reaction-day", "2026-10-14",
                               "--expiration", "2026-10-16", "--credit", "0.36", "--buyback", "0.20")
        self.assertTrue(out.startswith("HOLD"))

    def test_bad_chain_is_no_trade(self):
        rc, out = self.run_cli("build", "--symbol", "ZZZ", "--price", "100", "--date", "2026-10-13", "--report-date", "2026-10-14",
                               "--timing", "am", "--chain", os.path.join(FIX, "ms_chain_2026-10-13.json"),
                               "--instruments", os.path.join(FIX, "ms_instruments_2026-10-16_puts.json"),
                               "--quotes", os.path.join(FIX, "ms_quotes_2026-10-16_puts.json"))
        self.assertEqual(rc, 1)
        self.assertIn("NO TRADE: Data check failed: 0 option chains for ZZZ", out)


if __name__ == "__main__":
    unittest.main()
