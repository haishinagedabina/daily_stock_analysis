# -*- coding: utf-8 -*-
"""
Pattern Detector — horizontal resistance levels and 123 bottom reversal.

Horizontal Resistance: clusters swing highs within a price band and counts
how many times price touched each zone.

123 Bottom Pattern:
  Point 1 — significant low (swing low)
  Point 2 — bounce high (swing high after Point 1)
  Point 3 — higher low (swing low above Point 1 after Point 2)
  Confirmation — close breaks above Point 2 within breakout_window bars after P3

Detection strategy (most-recent-first):
  - Iterate swing lows from newest → oldest to find P1
  - For each P1, take the most recent qualifying P2 and P3
  - Breakout must occur within the last breakout_window bars (not any historical bar)
  - This ensures the returned pattern is the one currently in play
"""

from typing import Dict, Any, List, Optional

import numpy as np
import pandas as pd

from src.indicators.divergence_detector import find_swing_lows, find_swing_highs

MIN_BARS = 20
MIN_BARS_123 = 30
_DEFAULT_BREAKOUT_WINDOW = 15  # breakout must occur within this many bars of P3


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
        swing_order: int = 3,
        lookback: int = 60,
        breakout_window: int = _DEFAULT_BREAKOUT_WINDOW,
    ) -> Dict[str, Any]:
        """
        Detect the most recent valid 123 bottom reversal pattern.

        Search strategy (newest → oldest):
          1. Iterate P1 candidates from most-recent swing low backwards.
          2. For each P1, find the most-recent P2 (swing high after P1 > P1).
          3. For that P2, find the most-recent P3 (swing low after P2 > P1).
          4. Breakout is confirmed only if close exceeds P2 within
             `breakout_window` bars after P3 — stale historical breakouts
             are ignored.

        Using swing_order=3 (instead of 5) so that swings forming within
        the last few bars are detectable.

        Args:
            df: OHLCV DataFrame, chronologically ordered.
            swing_order: bars on each side required for swing confirmation.
            lookback: only consider swings within the most-recent N bars.
            breakout_window: max bars after P3 in which breakout must occur.

        Returns:
            Dict with found, point1, point2, point3, breakout_confirmed,
            bars_since_p3, bars_since_breakout.
        """
        empty: Dict[str, Any] = {
            "found": False,
            "point1": None, "point2": None, "point3": None,
            "breakout_confirmed": False,
            "bars_since_p3": None,
            "bars_since_breakout": None,
        }

        if len(df) < MIN_BARS_123:
            return empty

        low_series = (
            df["low"].reset_index(drop=True)
            if "low" in df.columns
            else df["close"].reset_index(drop=True)
        )
        high_series = (
            df["high"].reset_index(drop=True)
            if "high" in df.columns
            else df["close"].reset_index(drop=True)
        )
        close = df["close"].reset_index(drop=True)
        last_idx = len(df) - 1

        cutoff = max(0, last_idx - lookback + 1)
        lows = [i for i in find_swing_lows(low_series, order=swing_order) if i >= cutoff]
        highs = [i for i in find_swing_highs(high_series, order=swing_order) if i >= cutoff]

        if len(lows) < 2 or len(highs) < 1:
            return empty

        # --- newest-first search ---
        # Reverse so we evaluate the most-recent P1 first and return immediately.
        for p1_idx in reversed(lows):
            p1_val = float(low_series.iloc[p1_idx])

            # P2: most-recent swing high after P1 that is above P1
            p2_idx: Optional[int] = None
            p2_val: float = 0.0
            for h in reversed(highs):
                if h <= p1_idx:
                    break
                v = float(high_series.iloc[h])
                if v > p1_val:
                    p2_idx = h
                    p2_val = v
                    break
            if p2_idx is None:
                continue

            # P3: most-recent swing low after P2 that is strictly above P1
            p3_idx: Optional[int] = None
            p3_val: float = 0.0
            for l in reversed(lows):
                if l <= p2_idx:
                    break
                v = float(low_series.iloc[l])
                if v > p1_val:
                    p3_idx = l
                    p3_val = v
                    break
            if p3_idx is None:
                continue

            bars_since_p3 = last_idx - p3_idx

            # Breakout: close must exceed P2 within breakout_window bars
            # after P3 — we only scan up to min(p3+breakout_window, last_idx).
            breakout_end = min(p3_idx + breakout_window, last_idx)
            # Include the bar at p3_idx itself in the window but a close at
            # P3 (which is a low) will almost never exceed P2, so this is safe.
            after_p3_window = close.iloc[p3_idx: breakout_end + 1]
            breakout_mask = after_p3_window > p2_val

            breakout_confirmed = bool(breakout_mask.any())
            bars_since_breakout: Optional[int] = None
            if breakout_confirmed:
                # Relative index of the breakout bar within the window slice
                first_bo_rel = int(np.argmax(breakout_mask.to_numpy()))
                first_bo_abs = p3_idx + first_bo_rel
                bars_since_breakout = last_idx - first_bo_abs

            return {
                "found": True,
                "point1": {"idx": int(p1_idx), "price": round(p1_val, 4)},
                "point2": {"idx": int(p2_idx), "price": round(p2_val, 4)},
                "point3": {"idx": int(p3_idx), "price": round(p3_val, 4)},
                "breakout_confirmed": breakout_confirmed,
                "bars_since_p3": bars_since_p3,
                "bars_since_breakout": bars_since_breakout,
            }

        return empty
