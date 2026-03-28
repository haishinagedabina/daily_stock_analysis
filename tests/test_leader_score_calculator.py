# -*- coding: utf-8 -*-
"""Unit tests for LeaderScoreCalculator."""

import unittest
from src.services.leader_score_calculator import LeaderScoreCalculator


class LeaderScoreCalculatorTestCase(unittest.TestCase):
    """Test LeaderScoreCalculator."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.calculator = LeaderScoreCalculator()

    def test_theme_match_score_full(self) -> None:
        """Test theme_match_score at maximum."""
        score = self.calculator.calculate_theme_match_score(1.0)
        self.assertEqual(score, 35)

    def test_theme_match_score_half(self) -> None:
        """Test theme_match_score at 50%."""
        score = self.calculator.calculate_theme_match_score(0.5)
        self.assertEqual(score, 17.5)

    def test_theme_match_score_zero(self) -> None:
        """Test theme_match_score at zero."""
        score = self.calculator.calculate_theme_match_score(0.0)
        self.assertEqual(score, 0)

    def test_small_circ_mv_score_small(self) -> None:
        """Test small_circ_mv_score for small market cap."""
        # < 50 billion
        score = self.calculator.calculate_small_circ_mv_score(30_000_000_000)
        self.assertEqual(score, 20)

    def test_small_circ_mv_score_medium(self) -> None:
        """Test small_circ_mv_score for medium market cap."""
        # 50-100 billion
        score = self.calculator.calculate_small_circ_mv_score(75_000_000_000)
        self.assertEqual(score, 10)

    def test_small_circ_mv_score_large(self) -> None:
        """Test small_circ_mv_score for large market cap."""
        # > 100 billion
        score = self.calculator.calculate_small_circ_mv_score(150_000_000_000)
        self.assertEqual(score, 0)

    def test_small_circ_mv_score_missing_is_neutral(self) -> None:
        """Missing circulation market value should not receive small-cap bonus."""
        score = self.calculator.calculate_small_circ_mv_score(None)
        self.assertEqual(score, 0)

    def test_turnover_score_high(self) -> None:
        """Test turnover_score for high turnover."""
        # > 5%
        score = self.calculator.calculate_turnover_score(0.08)
        self.assertEqual(score, 20)

    def test_turnover_score_medium(self) -> None:
        """Test turnover_score for medium turnover."""
        # 2-5%
        score = self.calculator.calculate_turnover_score(0.03)
        self.assertEqual(score, 10)

    def test_turnover_score_low(self) -> None:
        """Test turnover_score for low turnover."""
        # < 2%
        score = self.calculator.calculate_turnover_score(0.01)
        self.assertEqual(score, 0)

    def test_turnover_score_accepts_percent_values(self) -> None:
        """Turnover scores should accept 8.0 as 8% instead of 800%."""
        high = self.calculator.calculate_turnover_score(8.0)
        medium = self.calculator.calculate_turnover_score(3.0)
        self.assertEqual(high, 20)
        self.assertEqual(medium, 10)

    def test_breakout_strength_strong(self) -> None:
        """Test breakout_strength for strong breakout."""
        score = self.calculator.calculate_breakout_strength(
            is_limit_up=True,
            gap_breakaway=True,
        )
        self.assertEqual(score, 15)

    def test_breakout_strength_medium(self) -> None:
        """Test breakout_strength for medium breakout."""
        score = self.calculator.calculate_breakout_strength(
            is_limit_up=True,
            gap_breakaway=False,
        )
        self.assertEqual(score, 10)

    def test_breakout_strength_weak(self) -> None:
        """Test breakout_strength for weak breakout."""
        score = self.calculator.calculate_breakout_strength(
            is_limit_up=False,
            gap_breakaway=False,
        )
        self.assertEqual(score, 0)

    def test_trend_strength_strong(self) -> None:
        """Test trend_strength for strong trend."""
        score = self.calculator.calculate_trend_strength(
            above_ma100=True,
            ma100_breakout_days=3,
        )
        self.assertEqual(score, 10)

    def test_trend_strength_medium(self) -> None:
        """Test trend_strength for medium trend."""
        score = self.calculator.calculate_trend_strength(
            above_ma100=True,
            ma100_breakout_days=10,
        )
        self.assertEqual(score, 5)

    def test_trend_strength_weak(self) -> None:
        """Test trend_strength for weak trend."""
        score = self.calculator.calculate_trend_strength(
            above_ma100=False,
            ma100_breakout_days=0,
        )
        self.assertEqual(score, 0)

    def test_calculate_leader_score_full(self) -> None:
        """Test calculate_leader_score with all factors at maximum."""
        score = self.calculator.calculate_leader_score(
            theme_match_score=1.0,
            circ_mv=30_000_000_000,
            turnover_rate=0.08,
            is_limit_up=True,
            gap_breakaway=True,
            above_ma100=True,
            ma100_breakout_days=3,
        )
        # 35 + 20 + 20 + 15 + 10 = 100
        self.assertEqual(score, 100)

    def test_calculate_leader_score_zero(self) -> None:
        """Test calculate_leader_score with all factors at minimum."""
        score = self.calculator.calculate_leader_score(
            theme_match_score=0.0,
            circ_mv=150_000_000_000,
            turnover_rate=0.01,
            is_limit_up=False,
            gap_breakaway=False,
            above_ma100=False,
            ma100_breakout_days=0,
        )
        self.assertEqual(score, 0)

    def test_calculate_leader_score_partial(self) -> None:
        """Test calculate_leader_score with partial factors."""
        score = self.calculator.calculate_leader_score(
            theme_match_score=0.8,
            circ_mv=75_000_000_000,
            turnover_rate=0.03,
            is_limit_up=True,
            gap_breakaway=False,
            above_ma100=True,
            ma100_breakout_days=5,
        )
        # 28 + 10 + 10 + 10 + 10 = 68
        self.assertEqual(score, 68)


if __name__ == "__main__":
    unittest.main()
