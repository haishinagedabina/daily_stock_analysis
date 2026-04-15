# -*- coding: utf-8 -*-
"""Overall grading helpers for five-layer backtest summaries."""
from __future__ import annotations


class SystemGrader:
    """Maps summary metrics to a simple user-facing letter grade."""

    @staticmethod
    def grade(
        win_rate_pct: float | None,
        profit_factor: float | None,
        time_bucket_stability: float | None,
        sample_count: int,
    ) -> str:
        if sample_count < 10:
            return "N/A"

        score = 0.0

        if win_rate_pct is not None:
            if win_rate_pct >= 60:
                score += 40
            elif win_rate_pct >= 55:
                score += 35
            elif win_rate_pct >= 50:
                score += 25
            elif win_rate_pct >= 45:
                score += 15
            else:
                score += 5

        if profit_factor is not None:
            if profit_factor >= 2.0:
                score += 40
            elif profit_factor >= 1.5:
                score += 35
            elif profit_factor >= 1.2:
                score += 25
            elif profit_factor >= 1.0:
                score += 15
            else:
                score += 5

        if time_bucket_stability is not None:
            if time_bucket_stability <= 0.08:
                score += 20
            elif time_bucket_stability <= 0.12:
                score += 15
            elif time_bucket_stability <= 0.15:
                score += 10
            else:
                score += 5

        if score >= 90:
            return "A+"
        if score >= 80:
            return "A"
        if score >= 70:
            return "B+"
        if score >= 55:
            return "B"
        if score >= 40:
            return "C"
        return "D"
