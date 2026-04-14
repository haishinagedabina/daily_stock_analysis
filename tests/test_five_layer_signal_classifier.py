# -*- coding: utf-8 -*-
"""TDD RED phase: Tests for SignalClassifier.

Maps trade_stage → (signal_family, evaluator_type) with AI override support.
"""

import unittest

import pytest


@pytest.mark.unit
class TestSignalClassifier(unittest.TestCase):
    """Pure logic: trade_stage → signal_family + evaluator_type."""

    def _classify(self, trade_stage, ai_trade_stage=None, ai_confidence=None,
                  has_exit_plan=False):
        from src.backtest.classifiers.signal_classifier import SignalClassifier
        return SignalClassifier.classify(
            trade_stage=trade_stage,
            ai_trade_stage=ai_trade_stage,
            ai_confidence=ai_confidence,
            has_exit_plan=has_exit_plan,
        )

    # ── Entry signals ─────────────────────────────────────────────────────

    def test_probe_entry_is_entry(self):
        result = self._classify("probe_entry")
        self.assertEqual(result.signal_family, "entry")
        self.assertEqual(result.evaluator_type, "entry")

    def test_add_on_strength_is_entry(self):
        result = self._classify("add_on_strength")
        self.assertEqual(result.signal_family, "entry")
        self.assertEqual(result.evaluator_type, "entry")

    # ── Observation signals ───────────────────────────────────────────────

    def test_watch_is_observation(self):
        result = self._classify("watch")
        self.assertEqual(result.signal_family, "observation")
        self.assertEqual(result.evaluator_type, "observation")

    def test_focus_is_observation(self):
        result = self._classify("focus")
        self.assertEqual(result.signal_family, "observation")
        self.assertEqual(result.evaluator_type, "observation")

    def test_stand_aside_is_observation(self):
        result = self._classify("stand_aside")
        self.assertEqual(result.signal_family, "observation")
        self.assertEqual(result.evaluator_type, "observation")

    def test_reject_is_observation(self):
        result = self._classify("reject")
        self.assertEqual(result.signal_family, "observation")
        self.assertEqual(result.evaluator_type, "observation")

    # ── Exit signals ──────────────────────────────────────────────────────

    def test_exit_plan_overrides_to_exit(self):
        """If has_exit_plan is True, signal_family should be exit regardless of trade_stage."""
        result = self._classify("probe_entry", has_exit_plan=True)
        self.assertEqual(result.signal_family, "exit")
        self.assertEqual(result.evaluator_type, "exit")

    # ── AI override ───────────────────────────────────────────────────────

    def test_ai_override_high_confidence(self):
        """AI trade_stage overrides when ai_confidence >= 0.6."""
        result = self._classify(
            "watch",
            ai_trade_stage="probe_entry",
            ai_confidence=0.8,
        )
        self.assertEqual(result.signal_family, "entry")
        self.assertEqual(result.evaluator_type, "entry")
        self.assertTrue(result.ai_overridden)

    def test_ai_override_low_confidence_ignored(self):
        """AI trade_stage ignored when ai_confidence < 0.6."""
        result = self._classify(
            "watch",
            ai_trade_stage="probe_entry",
            ai_confidence=0.4,
        )
        self.assertEqual(result.signal_family, "observation")
        self.assertFalse(result.ai_overridden)

    def test_ai_override_none_confidence_ignored(self):
        """AI trade_stage ignored when ai_confidence is None."""
        result = self._classify(
            "watch",
            ai_trade_stage="probe_entry",
            ai_confidence=None,
        )
        self.assertEqual(result.signal_family, "observation")

    # ── Edge cases ────────────────────────────────────────────────────────

    def test_none_trade_stage_defaults_observation(self):
        result = self._classify(None)
        self.assertEqual(result.signal_family, "observation")
        self.assertEqual(result.evaluator_type, "observation")

    def test_unknown_trade_stage_defaults_observation(self):
        result = self._classify("some_unknown_stage")
        self.assertEqual(result.signal_family, "observation")
        self.assertEqual(result.evaluator_type, "observation")


if __name__ == "__main__":
    unittest.main()
