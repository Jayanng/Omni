"""Unit tests for the Omni engine. Standard library only: python3 -m unittest discover -s tests"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from omni import collateral as coll  # noqa: E402
from omni import metrics as metrics_mod  # noqa: E402
from omni.collateral import RTokenPosition  # noqa: E402
from omni.ledger import Ledger  # noqa: E402
from omni.policy import PolicyConfig, validate  # noqa: E402
from omni.risk import FuturesPosition, evaluate  # noqa: E402
from omni.session import classify  # noqa: E402

NY = ZoneInfo("America/New_York")


def book(asks, bids):
    return {"a": asks, "b": bids}


def states():
    return {
        "market": "US",
        "daylightType": "standard",
        "stateList": [
            {"state": "pre_market", "timeZone": "EST", "startTime": "04:00", "endTime": "09:30"},
            {"state": "regular", "timeZone": "EST", "startTime": "09:30", "endTime": "16:00"},
            {"state": "after_hours", "timeZone": "EST", "startTime": "16:00", "endTime": "20:00"},
        ],
    }


class TestSession(unittest.TestCase):
    def test_regular_session_on_a_weekday(self):
        # Wednesday 2026-09-09 at 11:00 New York is inside the regular window.
        now = datetime(2026, 9, 9, 11, 0, tzinfo=NY)
        state = classify(states(), {"tradingPeriod": ["regular"], "weekendTradable": "yes"},
                         {}, now=now)
        self.assertEqual(state.regime, "regular")
        self.assertEqual(state.liquidity_tier, "deep")
        self.assertEqual(state.mark_confidence, "high")
        self.assertTrue(state.cash_market_open)

    def test_pre_market_window(self):
        now = datetime(2026, 9, 9, 6, 0, tzinfo=NY)
        state = classify(states(), {"tradingPeriod": ["pre_market"], "weekendTradable": "yes"},
                         {}, now=now)
        self.assertEqual(state.regime, "pre_market")
        self.assertEqual(state.mark_confidence, "medium")

    def test_weekend_marks_are_low_confidence(self):
        now = datetime(2026, 9, 12, 12, 0, tzinfo=NY)  # Saturday
        state = classify(states(), {"tradingPeriod": ["overnight"], "weekendTradable": "yes"},
                         {}, now=now)
        self.assertTrue(state.is_weekend)
        self.assertEqual(state.regime, "weekend_tradable")
        self.assertEqual(state.mark_confidence, "low")
        self.assertFalse(state.cash_market_open)

    def test_weekend_frozen_when_not_tradable(self):
        now = datetime(2026, 9, 12, 12, 0, tzinfo=NY)
        state = classify(states(), {"tradingPeriod": [], "weekendTradable": "no"}, {}, now=now)
        self.assertEqual(state.regime, "weekend_frozen")
        self.assertEqual(state.liquidity_tier, "none")

    def test_holiday_window_overrides_everything(self):
        now = datetime(2026, 9, 9, 11, 0, tzinfo=NY)
        cal = {"specificConfig": [{"remark": "test holiday",
                                   "startTime": "2026-09-09 00:00", "endTime": "2026-09-10 00:00"}]}
        state = classify(states(), {"tradingPeriod": ["regular"], "weekendTradable": "yes"},
                         cal, now=now)
        self.assertTrue(state.in_holiday_window)
        self.assertEqual(state.regime, "holiday")
        self.assertEqual(state.liquidity_tier, "none")


class TestCollateral(unittest.TestCase):
    def test_fill_walks_levels_and_computes_vwap(self):
        b = book([[100.0, 1.0], [101.0, 1.0]], [[99.0, 1.0]])
        fill = coll.simulate_fill("RNVDAUSDT", "buy", 2.0, b, fee_rate=0.0005)
        self.assertAlmostEqual(fill.filled_qty, 2.0)
        self.assertAlmostEqual(fill.vwap, 100.5)
        self.assertAlmostEqual(fill.notional, 201.0)
        self.assertAlmostEqual(fill.fee, 201.0 * 0.0005)
        self.assertEqual(fill.levels_consumed, 2)
        self.assertTrue(fill.simulated)

    def test_partial_fill_when_depth_is_thin(self):
        b = book([[100.0, 0.5]], [[99.0, 0.5]])
        fill = coll.simulate_fill("RNVDAUSDT", "buy", 5.0, b)
        self.assertAlmostEqual(fill.filled_qty, 0.5)
        self.assertAlmostEqual(fill.unfilled_qty, 4.5)
        self.assertTrue(any("insufficient" in n for n in fill.notes))

    def test_sell_side_uses_bids(self):
        b = book([[100.0, 1.0]], [[98.0, 2.0]])
        fill = coll.simulate_fill("RNVDAUSDT", "sell", 1.0, b)
        self.assertAlmostEqual(fill.vwap, 98.0)

    def test_shock_worsens_the_exit_price(self):
        b = book([[100.0, 10.0]], [[99.0, 10.0]])
        fill = coll.simulate_fill("RNVDAUSDT", "sell", 1.0, b, shock_pct=-0.05)
        self.assertAlmostEqual(fill.vwap, 99.0 * 0.95)

    def test_effective_collateral_applies_haircut(self):
        self.assertAlmostEqual(coll.effective_collateral_value(10, 100, 0.15), 850.0)


class TestRisk(unittest.TestCase):
    def _state(self, **kw):
        defaults = dict(
            as_of="2026-09-11T10:00:00+00:00",
            observed_effective_equity=100_000.0,
            rtoken_positions=[RTokenPosition("RNVDAUSDT", "NVDA", 500, 219.0)],
            rtoken_marks={"RNVDAUSDT": 220.0},
            futures_positions=[],
            haircut_pct=0.15,
            rtoken_shock_pct=-0.04,
            crypto_shock_pct=-0.06,
            hedge_symbol="NVDAUSDT",
        )
        defaults.update(kw)
        return evaluate(**defaults)

    def test_collateral_math_is_exact(self):
        state = self._state().to_dict()
        self.assertAlmostEqual(state["modelled"]["rtoken_gross_value"], 110_000.0)
        self.assertAlmostEqual(state["modelled"]["rtoken_effective_collateral"], 93_500.0)

    def test_no_position_is_not_attention(self):
        state = self._state(rtoken_positions=[], rtoken_marks={}).to_dict()
        self.assertFalse(state["results"]["needs_attention"])
        self.assertFalse(state["results"]["breach"])

    def test_large_crypto_loss_triggers_attention_via_risk_budget(self):
        pos = FuturesPosition("BTCUSDT", "long", 2.0, 77_000.0, 77_000.0, 0.0, 0.004, 20.0,
                              asset_class="crypto")
        state = self._state(futures_positions=[pos], crypto_shock_pct=-0.25).to_dict()
        self.assertTrue(state["results"]["needs_attention"])
        self.assertGreater(state["results"]["modelled_loss_pct_of_equity"], 0.10)

    def test_short_position_gains_when_crypto_falls(self):
        pos = FuturesPosition("BTCUSDT", "short", 1.0, 100_000.0, 100_000.0, 0.0, 0.004, 20.0,
                              asset_class="crypto")
        state = self._state(futures_positions=[pos], crypto_shock_pct=-0.10).to_dict()
        self.assertGreater(state["results"]["futures_pnl_delta"], 0.0)

    def test_each_position_carries_its_own_shock(self):
        # A crypto long takes the crypto shock; a stock perp short takes the
        # equity gap. Neither may be shocked twice or left unshocked.
        crypto = FuturesPosition("BTCUSDT", "long", 2.0, 77_000.0, 77_000.0, 0.0, 0.004, 20.0,
                                 asset_class="crypto")
        stock = FuturesPosition("NVDAUSDT", "short", 20.0, 220.0, 220.0, 0.0, 0.02, 20.0,
                                asset_class="stock")
        state = self._state(futures_positions=[crypto, stock],
                            rtoken_shock_pct=-0.08, crypto_shock_pct=-0.25).to_dict()
        expected = (2.0 * 77_000.0 * -0.25 * 1) + (20.0 * 220.0 * -0.08 * -1)
        self.assertAlmostEqual(state["results"]["futures_pnl_delta"], expected, places=4)

    def test_unclassified_position_still_takes_the_crypto_shock(self):
        # Guard against a silent zero shock: the default asset class is crypto.
        pos = FuturesPosition("BTCUSDT", "long", 1.0, 50_000.0, 50_000.0, 0.0, 0.004, 20.0)
        state = self._state(futures_positions=[pos], crypto_shock_pct=-0.10).to_dict()
        self.assertAlmostEqual(state["results"]["futures_pnl_delta"], -5_000.0, places=4)

    def test_liquidation_shock_is_reported_when_plausible(self):
        # A large crypto loss eats most of the buffer, so the rToken shock that
        # would zero the buffer lands inside a plausible range.
        pos = FuturesPosition("BTCUSDT", "long", 6.2, 77_000.0, 77_000.0, 0.0, 0.004, 20.0,
                              asset_class="crypto")
        state = self._state(futures_positions=[pos], crypto_shock_pct=-0.25).to_dict()
        shock = state["results"]["liquidation_shock_pct"]
        self.assertIsNotNone(shock)
        self.assertLess(shock, 0.0)
        self.assertGreaterEqual(shock, -1.0)

    def test_liquidation_shock_is_withheld_when_implausible(self):
        # With a huge buffer the rToken leg alone cannot zero it, so publishing a
        # figure would be misleading. The engine withholds it and says why.
        state = self._state().to_dict()
        self.assertIsNone(state["results"]["liquidation_shock_pct"])
        self.assertTrue(state["results"]["liquidation_shock_note"])

    def test_assumptions_always_travel_with_the_result(self):
        state = self._state().to_dict()
        self.assertTrue(state["assumptions"])
        self.assertIn("Scenario estimate", state["disclaimer"])


class TestPolicy(unittest.TestCase):
    def _risk(self, needs_attention=True, positions=None, hedge_symbol="NVDAUSDT"):
        return {
            "results": {
                "needs_attention": needs_attention,
                "breach": False,
                "recommended_hedge": {
                    "notional_usdt": 1_000.0,
                    "side": "sell",
                    "symbol": hedge_symbol,
                },
            },
            "observed": {"positions": positions or []},
        }

    def test_allowlisted_action_is_approved(self):
        res = validate("HOLD", {}, self._risk(needs_attention=False), {"liquidity_tier": "deep"})
        self.assertTrue(res.approved)
        self.assertFalse(res.override)
        self.assertEqual(res.action, "HOLD")

    def test_unknown_action_is_vetoed(self):
        res = validate("WITHDRAW", {"amount": 1}, self._risk(), {"liquidity_tier": "deep"})
        self.assertTrue(res.override or not res.approved)
        self.assertNotEqual(res.action, "WITHDRAW")

    def test_forbidden_word_inside_params_is_vetoed(self):
        res = validate("HEDGE_STOCK_PERP", {"symbol": "NVDAUSDT", "notional_usdt": 100,
                                            "note": "then TRANSFER_OUT the rest"},
                       self._risk(), {"liquidity_tier": "deep"})
        self.assertTrue(res.override or not res.approved)
        self.assertNotEqual(res.action, "HEDGE_STOCK_PERP")

    def test_hedge_notional_is_capped(self):
        res = validate("HEDGE_STOCK_PERP", {"symbol": "NVDAUSDT", "notional_usdt": 999_999},
                       self._risk(), {"liquidity_tier": "deep"}, PolicyConfig(max_order_notional_usdt=500))
        self.assertTrue(res.approved)
        self.assertLessEqual(res.params["notional_usdt"], 500)

    def test_hold_is_overridden_when_risk_needs_attention(self):
        res = validate("HOLD", {}, self._risk(needs_attention=True), {"liquidity_tier": "deep"})
        self.assertTrue(res.override)
        self.assertEqual(res.action, "HEDGE_STOCK_PERP")

    def test_closed_market_blocks_hedging(self):
        res = validate("HEDGE_STOCK_PERP", {"symbol": "NVDAUSDT", "notional_usdt": 100},
                       self._risk(needs_attention=False), {"liquidity_tier": "none"})
        self.assertNotEqual(res.action, "HEDGE_STOCK_PERP")

    def test_reduce_requires_an_open_position(self):
        res = validate("REDUCE_PERP", {"symbol": "BTCUSDT"}, self._risk(needs_attention=False),
                       {"liquidity_tier": "deep"})
        self.assertTrue(res.override or not res.approved)

    def test_reduce_with_open_position_is_approved(self):
        res = validate("REDUCE_PERP", {"symbol": "BTCUSDT", "reduce_pct": 50},
                       self._risk(needs_attention=False, positions=[{"symbol": "BTCUSDT"}]),
                       {"liquidity_tier": "deep"})
        self.assertTrue(res.approved)
        self.assertEqual(res.action, "REDUCE_PERP")


class TestMetricsLedger(unittest.TestCase):
    def test_ledger_round_trip_and_metrics(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            led = Ledger(Path(tmp))
            led.record("account_snapshot", {"assets": {"effEquity": "1000"}})
            led.record("account_snapshot", {"assets": {"effEquity": "900"}})
            led.record("decision", {"decision": {"action": "HEDGE_STOCK_PERP"}})
            led.record("execution", {
                "policy": {"override": False, "approved": True, "action": "HEDGE_STOCK_PERP"},
                "execution": {"action": "HEDGE_STOCK_PERP", "executed": True},
            })
            out = metrics_mod.compute(Path(tmp))
            self.assertEqual(out["decisions"], 1)
            self.assertEqual(out["executions_completed"], 1)
            self.assertEqual(out["risk_violation_count"], 0)
            self.assertEqual(out["equity_observations"], 2)
            self.assertAlmostEqual(out["max_drawdown_pct"], 0.1)
            self.assertIsNone(out["sharpe"])
            self.assertIn("not reported", out["sharpe_note"])

    def test_empty_ledger_is_safe(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            out = metrics_mod.compute(Path(tmp))
            self.assertEqual(out["decisions"], 0)
            self.assertEqual(out["risk_violation_rate"], 0.0)

    def test_policy_override_is_not_counted_as_a_violation(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            led = Ledger(Path(tmp))
            led.record("execution", {
                "policy": {"override": True, "approved": True, "action": "HEDGE_STOCK_PERP"},
                "execution": {"action": "HEDGE_STOCK_PERP", "executed": True},
            })
            out = metrics_mod.compute(Path(tmp))
            self.assertEqual(out["policy_overrides"], 1)
            self.assertEqual(out["risk_violation_count"], 0)

    def test_executing_a_rejected_proposal_is_a_violation(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            led = Ledger(Path(tmp))
            led.record("execution", {
                "policy": {"override": False, "approved": False, "action": "HOLD"},
                "execution": {"action": "WITHDRAW", "executed": True},
            })
            out = metrics_mod.compute(Path(tmp))
            self.assertEqual(out["risk_violation_count"], 1)
            self.assertEqual(out["risk_violation_rate"], 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
