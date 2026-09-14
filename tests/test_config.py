"""Tests for config symbol mapping helpers."""

from __future__ import annotations

import unittest

from omni.config import (
    ALLOWED_ACTIONS,
    RTOKEN_TO_STOCK_PERP,
    mapped_stock_perps,
    rtoken_for_stock_perp,
    stock_code_for,
    stock_perp_for,
)


class TestSymbolMapping(unittest.TestCase):
    def test_rtoken_maps_to_stock_perp(self):
        self.assertEqual(stock_perp_for("RNVDAUSDT"), "NVDAUSDT")
        self.assertEqual(stock_perp_for("RTSLAUSDT"), "TSLAUSDT")
        self.assertEqual(stock_perp_for("rNVDAUSDT"), "NVDAUSDT")

    def test_already_mapped_perp_passes_through(self):
        self.assertEqual(stock_perp_for("NVDAUSDT"), "NVDAUSDT")

    def test_unknown_symbol_is_not_silently_substituted(self):
        # Refusing beats hedging the wrong instrument. An unmapped symbol must
        # return "" so callers can block the action.
        self.assertEqual(stock_perp_for("RZZZZUSDT"), "")
        self.assertEqual(stock_perp_for(""), "")
        self.assertEqual(stock_perp_for("nonsense"), "")

    def test_mapped_stock_perps_is_derived_from_the_map(self):
        perps = mapped_stock_perps()
        self.assertIsInstance(perps, tuple)
        self.assertEqual(set(perps), set(RTOKEN_TO_STOCK_PERP.values()))
        self.assertEqual(list(perps), sorted(perps), "must be deterministic order")
        self.assertIn("NVDAUSDT", perps)

    def test_rtoken_for_stock_perp_reverse_lookup(self):
        self.assertEqual(rtoken_for_stock_perp("NVDAUSDT"), "RNVDAUSDT")
        self.assertEqual(rtoken_for_stock_perp("nvdaUSDT"), "RNVDAUSDT")
        self.assertEqual(rtoken_for_stock_perp("NOPEUSDT"), "")
        self.assertEqual(rtoken_for_stock_perp(""), "")

    def test_stock_code_for_strips_prefix_and_quote(self):
        self.assertEqual(stock_code_for("RNVDAUSDT"), "NVDA")
        self.assertEqual(stock_code_for("RSPYUSDT"), "SPY")
        self.assertEqual(stock_code_for("rqqqusdt"), "QQQ")
        self.assertEqual(stock_code_for(""), "")

    def test_mapping_is_consistent_with_allowlist_sanity(self):
        # The hedge action must remain allowlisted, otherwise the mapped
        # instrument could never be executed.
        self.assertIn("HEDGE_STOCK_PERP", ALLOWED_ACTIONS)


if __name__ == "__main__":
    unittest.main()
