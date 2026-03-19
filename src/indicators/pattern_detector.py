# -*- coding: utf-8 -*-
"""
Pattern Detector — horizontal resistance levels and 123 bottom reversal.

Horizontal Resistance: clusters swing highs within a price band and counts
how many times price touched each zone.

123 Bottom Pattern:
  Point 1 — significant low (swing low)
  Point 2 — bounce high (swing high after Point 1)
  Point 3 — higher low (swing low above Point 1 after Point 2)
  Confirmation — close above Point 2
"""

from typing import Dict, Any, List

import numpy as np
import pandas as pd

from src.indicators.divergence_detector import find_swing_lows, find_swing_highs

MIN_BARS = 20
MIN_BARS_123 = 30


def _cluster_levels(
    values: List[float], tolerance_pct: float = 0.015
) -> List[Dict[str, Any]]:
    """
    Cluster nearby price levels and count touches per cluster.

    Returns list of {price, touches} sorted by touches descending.
    """
    if not values:
        return []

    sorted_vals = sorted(values)
    clusters: List[List[float]] = []
    current_cluster = [sorted_vals[0]]

    for val in sorted_vals[1:]:
        center = np.mean(current_cluster)
        if center == 0:
            current_cluster.append(val)
            continue
        if abs(val - center) / abs(center) <= tolerance_pct:
            current_cluster.append(val)
        else:
            clusters.append(current_cluster)
            current_cluster = [val]
    clusters.append(current_cluster)

    levels = [
        {"price": round(float(np.mean(c)), 4), "touches": len(c)}
        for c in clusters
        if len(c) >= 2
    ]
    levels.sort(key=lambda x: x["touches"], reverse=True)
    return levels


class PatternDetector:
    """Detect chart patterns from OHLC data."""

    @classmethod
    def detect_horizontal_resistance(
        cls,
        df: pd.DataFrame,
        swing_order: int = 5,
        tolerance_pct: float = 0.015,
    ) -> Dict[str, Any]:
        """
        Detect horizontal resistance levels from swing highs.

        Returns:
            Dict with 'levels': list of {price, touches}
        """
        if len(df) < MIN_BARS:
            return {"levels": []}

        high_series = df["high"].reset_index(drop=True) if "high" in df.columns else df["close"].reset_index(drop=True)
        swing_indices = find_swing_highs(high_series, order=swing_order)

        if len(swing_indices) < 2:
            return {"levels": []}

        swing_values = [float(high_series.iloc[i]) for i in swing_indices]
        levels = _cluster_levels(swing_values, tolerance_pct)

        return {"levels": levels}

    @classmethod
    def detect_123_bottom(
        cls,
        df: pd.DataFrame,
        swing_order: int = 5,
        lookback: int = 60,
    ) -> Dict[str, Any]:
        """
        Detect 123 bottom reversal pattern.

        Returns:
            Dict with found, point1, point2, point3, breakout_confirmed
        """
        empty = {
            "found": False,
            "point1": None, "point2": None, "point3": None,
            "breakout_confirmed": False,
        }

        if len(df) < MIN_BARS_123:
            return empty

        low_series = df["low"].reset_index(drop=True) if "low" in df.columns else df["close"].reset_index(drop=True)
        high_series = df["high"].reset_index(drop=True) if "high" in df.columns else df["close"].reset_index(drop=True)
        close = df["close"].reset_index(drop=True)

        cutoff = max(0, len(df) - lookback)
        lows = [i for i in find_swing_lows(low_series, order=swing_order) if i >= cutoff]
        highs = [i for i in find_swing_highs(high_series, order=swing_order) if i >= cutoff]

        if len(lows) < 2 or len(highs) < 1:
            return empty

        for i in range(len(lows) - 1):
            p1_idx = lows[i]
            p1_val = float(low_series.iloc[p1_idx])

            # Find Point 2: swing high after Point 1
            p2_candidates = [h for h in highs if h > p1_idx]
            if not p2_candidates:
                continue

            for p2_idx in p2_candidates:
                p2_val = float(high_series.iloc[p2_idx])
                if p2_val <= p1_val:
                    continue

                # Find Point 3: swing low after Point 2, higher than Point 1
                p3_candidates = [l for l in lows if l > p2_idx and l != p1_idx]
                if not p3_candidates:
                    continue

                for p3_idx in p3_candidates:
                    p3_val = float(low_series.iloc[p3_idx])
                    if p3_val <= p1_val:
                        continue

                    # Check breakout: close above Point 2 after Point 3
                    after_p3 = close.iloc[p3_idx:]
                    breakout = bool((after_p3 > p2_val).any())

                    return {
                        "found": True,
                        "point1": {"idx": int(p1_idx), "price": round(p1_val, 4)},
                        "point2": {"idx": int(p2_idx), "price": round(p2_val, 4)},
                        "point3": {"idx": int(p3_idx), "price": round(p3_val, 4)},
                        "breakout_confirmed": breakout,
                    }

        return empty
