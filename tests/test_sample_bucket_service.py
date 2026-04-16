from __future__ import annotations

import unittest

import pytest


@pytest.mark.unit
class TestSampleBucketService(unittest.TestCase):
    def test_entry_high_maturity_maps_to_core_bucket(self):
        from src.backtest.services.sample_bucket_service import SampleBucketService

        bucket = SampleBucketService.resolve_sample_bucket(
            signal_family="entry",
            effective_trade_stage="probe_entry",
            entry_maturity="high",
        )

        self.assertEqual(bucket, "core")

    def test_medium_or_focus_maps_to_boundary_bucket(self):
        from src.backtest.services.sample_bucket_service import SampleBucketService

        bucket = SampleBucketService.resolve_sample_bucket(
            signal_family="observation",
            effective_trade_stage="focus",
            entry_maturity="medium",
        )

        self.assertEqual(bucket, "boundary")

    def test_low_or_reject_maps_to_noise_bucket(self):
        from src.backtest.services.sample_bucket_service import SampleBucketService

        bucket = SampleBucketService.resolve_sample_bucket(
            signal_family="observation",
            effective_trade_stage="stand_aside",
            entry_maturity="low",
        )

        self.assertEqual(bucket, "noise")

    def test_entry_timing_uses_too_early_when_mae_exceeds_threshold(self):
        from src.backtest.services.sample_bucket_service import SampleBucketService

        timing = SampleBucketService.resolve_entry_timing(
            signal_family="entry",
            entry_fill_status="filled",
            mae=-4.2,
            mfe=6.0,
            forward_return_5d=3.5,
        )

        self.assertEqual(timing["entry_timing_label"], "too_early")
        self.assertAlmostEqual(timing["early_pullback_pct"], 4.2)
        self.assertFalse(timing["missed_best_entry"])

    def test_entry_timing_uses_too_late_for_exhausted_move(self):
        from src.backtest.services.sample_bucket_service import SampleBucketService

        timing = SampleBucketService.resolve_entry_timing(
            signal_family="entry",
            entry_fill_status="filled",
            mae=-0.4,
            mfe=1.5,
            forward_return_5d=-0.8,
        )

        self.assertEqual(timing["entry_timing_label"], "too_late")
        self.assertTrue(timing["missed_best_entry"])
        self.assertAlmostEqual(timing["late_entry_gap_pct"], 1.5)

    def test_entry_timing_uses_not_applicable_for_observation(self):
        from src.backtest.services.sample_bucket_service import SampleBucketService

        timing = SampleBucketService.resolve_entry_timing(
            signal_family="observation",
            entry_fill_status="filled",
            mae=None,
            mfe=None,
            forward_return_5d=None,
        )

        self.assertEqual(timing["entry_timing_label"], "not_applicable")
        self.assertIsNone(timing["early_pullback_pct"])
        self.assertIsNone(timing["late_entry_gap_pct"])
        self.assertFalse(timing["missed_best_entry"])

    def test_entry_timing_does_not_use_too_late_without_forward_return_5d(self):
        from src.backtest.services.sample_bucket_service import SampleBucketService

        timing = SampleBucketService.resolve_entry_timing(
            signal_family="entry",
            entry_fill_status="filled",
            mae=-0.4,
            mfe=1.5,
            forward_return_5d=None,
        )

        self.assertEqual(timing["entry_timing_label"], "on_time")
        self.assertFalse(timing["missed_best_entry"])

    def test_entry_timing_marks_unfilled_entries_as_not_evaluable(self):
        from src.backtest.services.sample_bucket_service import SampleBucketService

        timing = SampleBucketService.resolve_entry_timing(
            signal_family="entry",
            entry_fill_status="limit_blocked",
            mae=None,
            mfe=None,
            forward_return_5d=None,
        )

        self.assertEqual(timing["entry_timing_label"], "not_evaluable")
        self.assertIsNone(timing["early_pullback_pct"])
        self.assertIsNone(timing["late_entry_gap_pct"])
        self.assertFalse(timing["missed_best_entry"])
