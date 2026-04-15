# -*- coding: utf-8 -*-
"""
Gap Detector — identifies price gaps and breakaway gaps.

A gap-up occurs when the current bar's low is above the previous bar's high.
A gap-down occurs when the current bar's high is below the previous bar's low.
A breakaway gap is a gap-up accompanied by above-average volume.
"""

from typing import Dict, Any, List

import numpy as np
import pandas as pd


class GapDetector:
    """Stateless detector for price gaps."""

    VOLUME_RATIO_THRESHOLD = 1.5

    @classmethod
    def detect_gaps(cls, df: pd.DataFrame, lookback: int = 20) -> List[Dict[str, Any]]:
        if df is None or len(df) < 2:
            return []

        gaps = []
        start = max(0, len(df) - lookback)
        for i in range(max(start, 1), len(df)):
            prev_high = float(df["high"].iloc[i - 1])
            prev_low = float(df["low"].iloc[i - 1])
            curr_high = float(df["high"].iloc[i])
            curr_low = float(df["low"].iloc[i])

            if curr_low > prev_high:
                gaps.append({
                    "index": i,
                    "date": df["date"].iloc[i] if "date" in df.columns else i,
                    "direction": "up",
                    "gap_low": prev_high,
                    "gap_high": curr_low,
                    "gap_pct": (curr_low - prev_high) / prev_high * 100,
                })
            elif curr_high < prev_low:
                gaps.append({
                    "index": i,
                    "date": df["date"].iloc[i] if "date" in df.columns else i,
                    "direction": "down",
                    "gap_low": curr_high,
                    "gap_high": prev_low,
                    "gap_pct": (curr_high - prev_low) / prev_low * 100,
                })

        return gaps

    @classmethod
    def detect_breakaway_gap(cls, df: pd.DataFrame) -> Dict[str, Any]:
        """Check if the latest bar is a breakaway gap (gap-up + volume surge).

        Also detects potential exhaustion gaps: a gap-up after an extended
        rally (>30% in 20 days) is more likely an exhaustion gap than a
        breakaway gap, and should not trigger buy signals.
        """
        if df is None or len(df) < 6:
            return {"is_breakaway": False, "is_exhaustion_risk": False}

        prev_high = float(df["high"].iloc[-2])
        curr_low = float(df["low"].iloc[-1])

        is_gap_up = curr_low > prev_high

        vol_avg = float(df["volume"].iloc[-6:-1].mean())
        curr_vol = float(df["volume"].iloc[-1])
        vol_ratio = curr_vol / vol_avg if vol_avg > 0 else 0

        # ── Exhaustion gap risk: gap after extended rally ──
        is_exhaustion_risk = False
        if is_gap_up and len(df) >= 21:
            close_col = df["close"]
            close_20d_ago = float(close_col.iloc[-21])
            close_now = float(close_col.iloc[-1])
            if close_20d_ago > 0:
                rally_pct = (close_now - close_20d_ago) / close_20d_ago
                if rally_pct > 0.30:
                    is_exhaustion_risk = True

        return {
            "is_breakaway": is_gap_up and vol_ratio >= cls.VOLUME_RATIO_THRESHOLD and not is_exhaustion_risk,
            "is_gap_up": is_gap_up,
            "is_exhaustion_risk": is_exhaustion_risk,
            "volume_ratio": vol_ratio,
            "gap_pct": (curr_low - prev_high) / prev_high * 100 if is_gap_up else 0,
        }
