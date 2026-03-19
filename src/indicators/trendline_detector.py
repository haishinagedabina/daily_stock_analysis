# -*- coding: utf-8 -*-
"""
Trendline Detector — fits linear trendlines to swing points and detects
breakouts.

Uptrend line: linear regression through swing lows (support).
Downtrend line: linear regression through swing highs (resistance).
Breakout: price crosses the projected trendline value.
"""

from typing import Dict, Any, List

import numpy as np
import pandas as pd

from src.indicators.divergence_detector import find_swing_lows, find_swing_highs

MIN_BARS = 20
MIN_TOUCHES = 2


def _fit_line(indices: List[int], values: List[float]) -> tuple:
    """Fit a line y = slope * x + intercept using least squares."""
    x = np.array(indices, dtype=float)
    y = np.array(values, dtype=float)
    A = np.vstack([x, np.ones(len(x))]).T
    result = np.linalg.lstsq(A, y, rcond=None)
    slope, intercept = result[0]
    return float(slope), float(intercept)


def _count_touches(
    indices: List[int], values: np.ndarray, slope: float, intercept: float,
    tolerance_pct: float = 0.02,
) -> int:
    """Count how many points are within tolerance of the fitted line."""
    count = 0
    for i in indices:
        if 0 <= i < len(values):
            line_val = slope * i + intercept
            if line_val == 0:
                continue
            diff_pct = abs(values[i] - line_val) / abs(line_val)
            if diff_pct <= tolerance_pct:
                count += 1
    return count


class TrendlineDetector:
    """Detect trendlines and breakouts from OHLC data."""

    @classmethod
    def detect_uptrend(
        cls,
        df: pd.DataFrame,
        swing_order: int = 5,
        tolerance_pct: float = 0.02,
    ) -> Dict[str, Any]:
        """
        Detect uptrend support line by fitting a line through swing lows.

        Returns:
            Dict with found, slope, intercept, touch_count, line_value_at_last
        """
        empty = {
            "found": False, "slope": 0.0, "intercept": 0.0,
            "touch_count": 0, "line_value_at_last": 0.0,
        }
        if len(df) < MIN_BARS:
            return empty

        low_series = df["low"].reset_index(drop=True) if "low" in df.columns else df["close"].reset_index(drop=True)
        swing_indices = find_swing_lows(low_series, order=swing_order)

        if len(swing_indices) < MIN_TOUCHES:
            return empty

        swing_values = [float(low_series.iloc[i]) for i in swing_indices]
        slope, intercept = _fit_line(swing_indices, swing_values)

        touches = _count_touches(
            swing_indices, low_series.values, slope, intercept, tolerance_pct
        )
        line_at_last = slope * (len(df) - 1) + intercept

        return {
            "found": touches >= MIN_TOUCHES,
            "slope": round(slope, 6),
            "intercept": round(intercept, 4),
            "touch_count": touches,
            "line_value_at_last": round(line_at_last, 4),
        }

    @classmethod
    def detect_downtrend(
        cls,
        df: pd.DataFrame,
        swing_order: int = 5,
        tolerance_pct: float = 0.02,
    ) -> Dict[str, Any]:
        """
        Detect downtrend resistance line by fitting a line through swing highs.

        Returns:
            Dict with found, slope, intercept, touch_count, line_value_at_last
        """
        empty = {
            "found": False, "slope": 0.0, "intercept": 0.0,
            "touch_count": 0, "line_value_at_last": 0.0,
        }
        if len(df) < MIN_BARS:
            return empty

        high_series = df["high"].reset_index(drop=True) if "high" in df.columns else df["close"].reset_index(drop=True)
        swing_indices = find_swing_highs(high_series, order=swing_order)

        if len(swing_indices) < MIN_TOUCHES:
            return empty

        swing_values = [float(high_series.iloc[i]) for i in swing_indices]
        slope, intercept = _fit_line(swing_indices, swing_values)

        touches = _count_touches(
            swing_indices, high_series.values, slope, intercept, tolerance_pct
        )
        line_at_last = slope * (len(df) - 1) + intercept

        return {
            "found": touches >= MIN_TOUCHES,
            "slope": round(slope, 6),
            "intercept": round(intercept, 4),
            "touch_count": touches,
            "line_value_at_last": round(line_at_last, 4),
        }

    @classmethod
    def detect_trendline_breakout(
        cls,
        df: pd.DataFrame,
        swing_order: int = 5,
    ) -> Dict[str, Any]:
        """
        Detect if the latest price has broken above a downtrend resistance
        or below an uptrend support.

        Returns:
            Dict with breakout (bool), direction ('up'/'down'/'none'),
            trendline details
        """
        result = {
            "breakout": False,
            "direction": "none",
            "downtrend": None,
            "uptrend": None,
        }

        if len(df) < MIN_BARS:
            return result

        close = float(df["close"].iloc[-1])

        downtrend = cls.detect_downtrend(df, swing_order=swing_order)
        result["downtrend"] = downtrend
        if downtrend["found"] and downtrend["line_value_at_last"] > 0:
            if close > downtrend["line_value_at_last"]:
                result["breakout"] = True
                result["direction"] = "up"
                return result

        uptrend = cls.detect_uptrend(df, swing_order=swing_order)
        result["uptrend"] = uptrend
        if uptrend["found"] and uptrend["line_value_at_last"] > 0:
            if close < uptrend["line_value_at_last"]:
                result["breakout"] = True
                result["direction"] = "down"
                return result

        return result
