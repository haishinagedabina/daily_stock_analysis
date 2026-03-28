# -*- coding: utf-8 -*-
"""Leader score calculator for hot theme stocks."""

from typing import Optional


class LeaderScoreCalculator:
    """Calculate leader score for hot theme stocks (100 point scale)."""

    def calculate_theme_match_score(self, theme_match_score: float) -> float:
        """Calculate theme match component (0-35 points)."""
        return theme_match_score * 35

    def calculate_small_circ_mv_score(self, circ_mv: Optional[float]) -> float:
        """
        Calculate small circulation market value component (0-20 points).
        < 50B: 20, 50-100B: 10, > 100B: 0
        """
        if circ_mv is None:
            return 0.0
        if circ_mv < 50_000_000_000:
            return 20.0
        elif circ_mv < 100_000_000_000:
            return 10.0
        else:
            return 0.0

    @staticmethod
    def normalize_turnover_rate(turnover_rate: Optional[float]) -> Optional[float]:
        """Normalize turnover to decimal form; accept either 0.05 or 5.0 as 5%."""
        if turnover_rate is None:
            return None
        if turnover_rate > 1:
            return turnover_rate / 100.0
        return turnover_rate

    def calculate_turnover_score(self, turnover_rate: Optional[float]) -> float:
        """
        Calculate turnover rate component (0-20 points).
        > 5%: 20, 2-5%: 10, < 2%: 0
        """
        turnover_rate = self.normalize_turnover_rate(turnover_rate)
        if turnover_rate is None:
            return 0.0
        if turnover_rate > 0.05:
            return 20.0
        elif turnover_rate >= 0.02:
            return 10.0
        else:
            return 0.0

    def calculate_breakout_strength(
        self,
        is_limit_up: bool,
        gap_breakaway: bool,
    ) -> float:
        """
        Calculate breakout strength component (0-15 points).
        Both: 15, One: 10, None: 0
        """
        count = sum([is_limit_up, gap_breakaway])
        if count == 2:
            return 15.0
        elif count == 1:
            return 10.0
        else:
            return 0.0

    def calculate_trend_strength(
        self,
        above_ma100: bool,
        ma100_breakout_days: int,
    ) -> float:
        """
        Calculate trend strength component (0-10 points).
        above_ma100 + recent breakout: 10, above_ma100 only: 5, neither: 0
        """
        if not above_ma100:
            return 0.0
        if ma100_breakout_days <= 5:
            return 10.0
        else:
            return 5.0

    def calculate_leader_score(
        self,
        theme_match_score: float,
        circ_mv: Optional[float],
        turnover_rate: Optional[float],
        is_limit_up: bool,
        gap_breakaway: bool,
        above_ma100: bool,
        ma100_breakout_days: int,
    ) -> float:
        """
        Calculate total leader score (0-100 points).
        Components:
        - theme_match: 0-35
        - small_circ_mv: 0-20
        - turnover: 0-20
        - breakout_strength: 0-15
        - trend_strength: 0-10
        """
        return (
            self.calculate_theme_match_score(theme_match_score)
            + self.calculate_small_circ_mv_score(circ_mv)
            + self.calculate_turnover_score(turnover_rate)
            + self.calculate_breakout_strength(is_limit_up, gap_breakaway)
            + self.calculate_trend_strength(above_ma100, ma100_breakout_days)
        )
