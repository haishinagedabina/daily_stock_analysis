# -*- coding: utf-8 -*-
"""Stability and distribution metrics for backtest evaluation groups.

Computes median, percentiles, extreme sample ratio, and time-bucket
stability to assess whether a group's performance is robust or driven
by outliers / specific time windows.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import List, Optional


@dataclass(frozen=True)
class StabilityResult:
    """Immutable result of stability metric computation."""

    median: Optional[float]
    p25: Optional[float]
    p75: Optional[float]
    stddev: Optional[float]
    extreme_sample_ratio: Optional[float]
    time_bucket_stability: Optional[float]


class StabilityMetricsCalculator:
    """Computes distribution and time-stability metrics for a group of returns."""

    @staticmethod
    def compute(
        returns: List[float],
        trade_dates: Optional[List[date]] = None,
    ) -> StabilityResult:
        """Compute stability metrics from a list of return values.

        Args:
            returns: List of return percentages (e.g. forward_return_5d).
            trade_dates: Corresponding trade dates for time-bucket stability.
                         If None, time_bucket_stability is skipped.

        Returns:
            StabilityResult with all computed metrics.
        """
        if not returns:
            return StabilityResult(
                median=None, p25=None, p75=None, stddev=None,
                extreme_sample_ratio=None, time_bucket_stability=None,
            )

        n = len(returns)
        sorted_returns = sorted(returns)

        median_val = statistics.median(sorted_returns)
        p25 = _percentile(sorted_returns, 25)
        p75 = _percentile(sorted_returns, 75)

        stddev = statistics.stdev(returns) if n >= 2 else 0.0

        # Extreme sample ratio: |return| > 2 * stddev
        extreme_count = 0
        if stddev > 0:
            threshold = 2.0 * stddev
            mean_val = statistics.mean(returns)
            extreme_count = sum(1 for r in returns if abs(r - mean_val) > threshold)
        extreme_sample_ratio = extreme_count / n if n > 0 else 0.0

        # Time-bucket stability: stddev of per-week win rates
        time_bucket_stability = None
        if trade_dates and len(trade_dates) == n:
            time_bucket_stability = _compute_time_bucket_stability(
                returns, trade_dates,
            )

        return StabilityResult(
            median=round(median_val, 4),
            p25=round(p25, 4),
            p75=round(p75, 4),
            stddev=round(stddev, 4),
            extreme_sample_ratio=round(extreme_sample_ratio, 4),
            time_bucket_stability=(
                round(time_bucket_stability, 4)
                if time_bucket_stability is not None
                else None
            ),
        )


def _percentile(sorted_data: List[float], pct: int) -> float:
    """Compute percentile using linear interpolation."""
    if not sorted_data:
        return 0.0
    n = len(sorted_data)
    k = (pct / 100.0) * (n - 1)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_data[int(k)]
    return sorted_data[f] * (c - k) + sorted_data[c] * (k - f)


def _compute_time_bucket_stability(
    returns: List[float],
    trade_dates: List[date],
) -> Optional[float]:
    """Compute stddev of per-week win rates.

    Lower value = more stable across time.
    Returns None if fewer than 2 buckets have samples.
    """
    buckets: dict[str, List[float]] = defaultdict(list)
    for ret, td in zip(returns, trade_dates):
        # ISO week bucket: "2026-W14"
        iso = td.isocalendar()
        bucket_key = f"{iso[0]}-W{iso[1]:02d}"
        buckets[bucket_key].append(ret)

    if len(buckets) < 2:
        return None

    bucket_win_rates = []
    for vals in buckets.values():
        wins = sum(1 for v in vals if v > 0)
        bucket_win_rates.append(wins / len(vals) if vals else 0.0)

    if len(bucket_win_rates) < 2:
        return None

    return statistics.stdev(bucket_win_rates)
