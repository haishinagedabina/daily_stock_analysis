# -*- coding: utf-8 -*-
"""
MACD Divergence Detector — identifies bullish and bearish divergences
between price and MACD histogram.

Bullish divergence: price makes a lower low while MACD histogram makes
a higher low (momentum weakening on the downside).

Bearish divergence: price makes a higher high while MACD histogram makes
a lower high (momentum weakening on the upside).
"""

from typing import Dict, Any, List, Tuple

import numpy as np
import pandas as pd

MIN_BARS_FOR_MACD = 35


def compute_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Compute MACD line, signal line, and histogram.

    Returns:
        (macd_line, signal_line, histogram)
    """
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def find_swing_lows(series: pd.Series, order: int = 5) -> List[int]:
    """
    Find local minima indices using a simple rolling window comparison.

    Args:
        series: 1-D numeric series
        order: number of bars on each side to compare

    Returns:
        List of integer indices where local minima occur.
    """
    lows = []
    values = series.values
    n = len(values)
    for i in range(order, n - order):
        window = values[i - order: i + order + 1]
        if np.all(np.isfinite(window)) and values[i] == np.min(window):
            if values[i] < values[i - 1] or values[i] < values[i + 1]:
                lows.append(i)
    return lows


def find_swing_highs(series: pd.Series, order: int = 5) -> List[int]:
    """
    Find local maxima indices using a simple rolling window comparison.

    Args:
        series: 1-D numeric series
        order: number of bars on each side to compare

    Returns:
        List of integer indices where local maxima occur.
    """
    highs = []
    values = series.values
    n = len(values)
    for i in range(order, n - order):
        window = values[i - order: i + order + 1]
        if np.all(np.isfinite(window)) and values[i] == np.max(window):
            if values[i] > values[i - 1] or values[i] > values[i + 1]:
                highs.append(i)
    return highs


class DivergenceDetector:
    """Detect MACD divergences on a price DataFrame."""

    MIN_SWING_GAP = 5

    @classmethod
    def detect_bullish(
        cls,
        df: pd.DataFrame,
        fast: int = 12,
        slow: int = 26,
        signal_period: int = 9,
        swing_order: int = 5,
        lookback: int = 60,
    ) -> Dict[str, Any]:
        """
        Detect bullish divergence: price lower-low + MACD higher-low.

        Args:
            df: DataFrame with 'close' column (and optionally 'low')
            lookback: only consider swings within the last N bars

        Returns:
            Dict with keys: found, price_low1, price_low2, macd_low1, macd_low2,
            idx1, idx2
        """
        empty = {
            "found": False,
            "price_low1": None, "price_low2": None,
            "macd_low1": None, "macd_low2": None,
            "idx1": None, "idx2": None,
        }

        if len(df) < MIN_BARS_FOR_MACD:
            return empty

        close = df["close"].reset_index(drop=True)
        price_series = df["low"].reset_index(drop=True) if "low" in df.columns else close
        _, _, histogram = compute_macd(close, fast, slow, signal_period)

        cutoff = max(0, len(df) - lookback)

        price_lows = [i for i in find_swing_lows(price_series, swing_order) if i >= cutoff]
        hist_lows = [i for i in find_swing_lows(histogram, swing_order) if i >= cutoff]

        if len(price_lows) < 2 or len(hist_lows) < 2:
            return empty

        for i in range(len(price_lows) - 1):
            idx1 = price_lows[i]
            idx2 = price_lows[i + 1]
            if idx2 - idx1 < cls.MIN_SWING_GAP:
                continue
            if price_series.iloc[idx2] >= price_series.iloc[idx1]:
                continue

            h_low1 = cls._nearest_hist_low(idx1, hist_lows, histogram)
            h_low2 = cls._nearest_hist_low(idx2, hist_lows, histogram)
            if h_low1 is None or h_low2 is None:
                continue

            if histogram.iloc[h_low2] > histogram.iloc[h_low1]:
                return {
                    "found": True,
                    "price_low1": float(price_series.iloc[idx1]),
                    "price_low2": float(price_series.iloc[idx2]),
                    "macd_low1": float(histogram.iloc[h_low1]),
                    "macd_low2": float(histogram.iloc[h_low2]),
                    "idx1": int(idx1),
                    "idx2": int(idx2),
                }

        return empty

    @classmethod
    def detect_bearish(
        cls,
        df: pd.DataFrame,
        fast: int = 12,
        slow: int = 26,
        signal_period: int = 9,
        swing_order: int = 5,
        lookback: int = 60,
    ) -> Dict[str, Any]:
        """
        Detect bearish divergence: price higher-high + MACD lower-high.
        """
        empty = {
            "found": False,
            "price_high1": None, "price_high2": None,
            "macd_high1": None, "macd_high2": None,
            "idx1": None, "idx2": None,
        }

        if len(df) < MIN_BARS_FOR_MACD:
            return empty

        close = df["close"].reset_index(drop=True)
        price_series = df["high"].reset_index(drop=True) if "high" in df.columns else close
        _, _, histogram = compute_macd(close, fast, slow, signal_period)

        cutoff = max(0, len(df) - lookback)

        price_highs = [i for i in find_swing_highs(price_series, swing_order) if i >= cutoff]
        hist_highs = [i for i in find_swing_highs(histogram, swing_order) if i >= cutoff]

        if len(price_highs) < 2 or len(hist_highs) < 2:
            return empty

        for i in range(len(price_highs) - 1):
            idx1 = price_highs[i]
            idx2 = price_highs[i + 1]
            if idx2 - idx1 < cls.MIN_SWING_GAP:
                continue
            if price_series.iloc[idx2] <= price_series.iloc[idx1]:
                continue

            h_high1 = cls._nearest_hist_high(idx1, hist_highs, histogram)
            h_high2 = cls._nearest_hist_high(idx2, hist_highs, histogram)
            if h_high1 is None or h_high2 is None:
                continue

            if histogram.iloc[h_high2] < histogram.iloc[h_high1]:
                return {
                    "found": True,
                    "price_high1": float(price_series.iloc[idx1]),
                    "price_high2": float(price_series.iloc[idx2]),
                    "macd_high1": float(histogram.iloc[h_high1]),
                    "macd_high2": float(histogram.iloc[h_high2]),
                    "idx1": int(idx1),
                    "idx2": int(idx2),
                }

        return empty

    @staticmethod
    def _nearest_hist_low(
        target_idx: int, hist_lows: List[int], histogram: pd.Series, tolerance: int = 8
    ) -> int | None:
        """Find the histogram swing-low index nearest to target_idx."""
        best = None
        best_dist = tolerance + 1
        for hi in hist_lows:
            dist = abs(hi - target_idx)
            if dist < best_dist:
                best_dist = dist
                best = hi
        return best

    @staticmethod
    def _nearest_hist_high(
        target_idx: int, hist_highs: List[int], histogram: pd.Series, tolerance: int = 8
    ) -> int | None:
        """Find the histogram swing-high index nearest to target_idx."""
        best = None
        best_dist = tolerance + 1
        for hi in hist_highs:
            dist = abs(hi - target_idx)
            if dist < best_dist:
                best_dist = dist
                best = hi
        return best
