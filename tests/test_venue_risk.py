"""Tests for venue-published risk parameter lookups."""

import unittest

from omni.venue_risk import (
    TierBand,
    _discount_coin,
    _pick_tier,
    effective_order_cap,
    mmr_for_notional,
    next_tier_above,
)


def _client_returning(payload):
    class FakeCall:
        def __init__(self, payload):
            self.data = payload

    class FakeClient:
        def __init__(self, payload):
            self._payload = payload

        def call(self, args, allow_failure=False):
            return FakeCall(self._payload)

    return FakeClient(payload)


class TestDiscountCoinMapping(unittest.TestCase):
    def test_rtoken_symbol_maps_to_discount_coin(self):
        self.assertEqual(_discount_coin("RNVDAUSDT"), "RNVDA")
        self.assertEqual(_discount_coin("RTSLAUSDT"), "RTSLA")
        self.assertEqual(_discount_coin("rNVDA"), "RNVDA")
        self.assertEqual(_discount_coin(""), "r")


class TestTierSelection(unittest.TestCase):
    def test_pick_tier_selects_band_containing_value(self):
        bands = [
            {"tierStartValue": "0", "discountRate": "0.95"},
            {"tierStartValue": "500000", "discountRate": "0.94"},
            {"tierStartValue": "1000000", "discountRate": "0.93"},
        ]
        self.assertEqual(_pick_tier(bands, 0)["discountRate"], "0.95")
        self.assertEqual(_pick_tier(bands, 109_000)["discountRate"], "0.95")
        self.assertEqual(_pick_tier(bands, 600_000)["discountRate"], "0.94")
        self.assertEqual(_pick_tier(bands, 5_000_000)["discountRate"], "0.93")

    def test_pick_tier_empty_returns_none(self):
        self.assertIsNone(_pick_tier([], 100))


class TestQueryHaircut(unittest.TestCase):
    def test_venue_haircut_resolves(self):
        data = [
            {"coin": "rSPY", "list": [{"tierStartValue": "0", "discountRate": "0.95"}]},
            {"coin": "rNVDA", "list": [
                {"tierStartValue": "0", "discountRate": "0.95"},
                {"tierStartValue": "500000", "discountRate": "0.94"},
            ]},
        ]
        from omni.venue_risk import query_haircut

        quote = query_haircut(_client_returning(data), "RNVDAUSDT", 109_000.0)
        self.assertIsNotNone(quote)
        self.assertAlmostEqual(quote.haircut_pct, 0.05)
        self.assertAlmostEqual(quote.discount_rate, 0.95)
        self.assertIn("discount-rate", quote.source)

    def test_unknown_coin_returns_none(self):
        from omni.venue_risk import query_haircut

        data = [{"coin": "rSPY", "list": [{"tierStartValue": "0", "discountRate": "0.95"}]}]
        self.assertIsNone(query_haircut(_client_returning(data), "RBTCUSDT", 100.0))

    def test_failed_call_returns_none(self):
        class Boom:
            def call(self, args, allow_failure=False):
                raise RuntimeError("venue down")

        from omni.venue_risk import query_haircut

        self.assertIsNone(query_haircut(Boom(), "RNVDAUSDT", 100.0))


class TestMmrLadder(unittest.TestCase):
    BANDS = [
        TierBand(tier=1, min_usdt=0, max_usdt=5000, mmr=0.005, max_leverage=100),
        TierBand(tier=2, min_usdt=5000, max_usdt=10000, mmr=0.0066, max_leverage=75),
        TierBand(tier=3, min_usdt=10000, max_usdt=20000, mmr=0.01, max_leverage=50),
    ]

    def test_mmr_for_notional(self):
        self.assertAlmostEqual(mmr_for_notional(self.BANDS, 2500), 0.005)
        self.assertAlmostEqual(mmr_for_notional(self.BANDS, 15000), 0.01)
        self.assertIsNone(mmr_for_notional(self.BANDS, 999_999))

    def test_next_tier_above(self):
        band = next_tier_above(self.BANDS, 2500)
        self.assertEqual(band.tier, 2)
        self.assertIsNone(next_tier_above(self.BANDS, 100_000))


class TestOrderCaps(unittest.TestCase):
    def test_effective_cap_is_stricter_value(self):
        caps = {"max_order_qty": 52000, "max_market_order_qty": 9500}
        self.assertAlmostEqual(effective_order_cap(caps), 9500)
        self.assertEqual(effective_order_cap({}), 0.0)
        self.assertEqual(effective_order_cap({"max_order_qty": 0, "max_market_order_qty": 0}), 0.0)


if __name__ == "__main__":
    unittest.main()
