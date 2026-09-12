"""Tests for live-derived scenario shocks."""

from __future__ import annotations

import unittest

from omni.scenario import (
    ShockEstimate,
    close_to_close_returns,
    crypto_proxy_symbol,
    empirical_tail_shock,
)
from omni.risk import FuturesPosition


def _rows(closes):
    """Build OHLC rows shaped like the venue payload: [ts, o, h, l, c, ...]."""
    return [[str(1_700_000_000_000 + i * 86_400_000), str(c), str(c), str(c), str(c), "0", "0"]
            for i, c in enumerate(closes)]


class TestReturns(unittest.TestCase):
    def test_close_to_close_returns(self):
        rows = _rows([100.0, 110.0, 99.0])
        out = close_to_close_returns(rows)
        self.assertEqual(len(out), 2)
        self.assertAlmostEqual(out[0], 0.10, places=6)
        self.assertAlmostEqual(out[1], (99.0 - 110.0) / 110.0, places=6)

    def test_malformed_rows_are_skipped(self):
        rows = [["1", "x", "y", "z", "not-a-number"], ["2", "1", "1", "1", "100"], ["3", "1", "1", "1", "90"]]
        out = close_to_close_returns(rows)
        self.assertEqual(len(out), 1)
        self.assertAlmostEqual(out[0], -0.10, places=6)


class TestTailShock(unittest.TestCase):
    def test_quantile_used_when_enough_samples(self):
        # 24 returns, most slightly negative, one big drop.
        closes = [100.0]
        for i in range(23):
            closes.append(closes[-1] * 0.999)
        closes.append(closes[-1] * 0.80)
        # Patch the venue read by monkeypatching the module function.
        import omni.scenario as sc
        original = sc.bp.candles
        sc.bp.candles = lambda symbol, interval, limit: _rows(closes)
        try:
            out = empirical_tail_shock("RNVDAUSDT")
        finally:
            sc.bp.candles = original
        self.assertIsNotNone(out)
        self.assertLess(out.shock_pct, 0.0, "tail shock should be a loss")
        self.assertGreaterEqual(out.samples, 20)
        self.assertIn("quantile", out.method)
        self.assertIn("candles", out.source)

    def test_few_samples_use_minimum(self):
        import omni.scenario as sc
        original = sc.bp.candles
        sc.bp.candles = lambda symbol, interval, limit: _rows([100.0, 105.0, 95.0])
        try:
            out = empirical_tail_shock("RNVDAUSDT")
        finally:
            sc.bp.candles = original
        self.assertIsNotNone(out)
        self.assertEqual(out.samples, 2)
        self.assertIn("sample minimum", out.method)

    def test_venue_failure_returns_none(self):
        import omni.scenario as sc
        original = sc.bp.candles

        def boom(*a, **k):
            raise RuntimeError("venue down")

        sc.bp.candles = boom
        try:
            self.assertIsNone(empirical_tail_shock("RNVDAUSDT"))
        finally:
            sc.bp.candles = original

    def test_no_history_returns_none(self):
        import omni.scenario as sc
        original = sc.bp.candles
        sc.bp.candles = lambda symbol, interval, limit: []
        try:
            self.assertIsNone(empirical_tail_shock("RNVDAUSDT"))
        finally:
            sc.bp.candles = original


class TestCryptoProxy(unittest.TestCase):
    def test_picks_largest_crypto_position(self):
        positions = [
            FuturesPosition("BTCUSDT", "long", 0.05, 77_000.0, 77_000.0, 0.0, 0.004, 20.0, "crypto"),
            FuturesPosition("NVDAUSDT", "short", 45.0, 219.0, 219.0, 0.0, 0.03, 20.0, "stock"),
        ]
        # BTC notional 3,850; NVDA 9,855 but is stock, so BTC wins the crypto leg.
        self.assertEqual(crypto_proxy_symbol(positions), "BTCUSDT")

    def test_no_crypto_exposure_returns_empty(self):
        positions = [
            FuturesPosition("NVDAUSDT", "short", 45.0, 219.0, 219.0, 0.0, 0.03, 20.0, "stock"),
        ]
        self.assertEqual(crypto_proxy_symbol(positions), "")

    def test_empty_book_returns_empty(self):
        self.assertEqual(crypto_proxy_symbol([]), "")


class TestShockEstimateShape(unittest.TestCase):
    def test_serialises_with_provenance(self):
        est = ShockEstimate(
            symbol="RNVDAUSDT", shock_pct=-0.031, method="m", samples=30,
            interval="1D", lookback_bars=30, source="s",
        )
        d = est.to_dict()
        self.assertEqual(d["symbol"], "RNVDAUSDT")
        self.assertIn("method", d)
        self.assertIn("samples", d)
        self.assertIn("source", d)


if __name__ == "__main__":
    unittest.main()
