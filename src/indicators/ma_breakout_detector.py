# -*- coding: utf-8 -*-
"""
MA Breakout Detector — detects price breakout above a moving average and
pullback-to-support patterns.
"""

from typing import Dict, Any

import numpy as np
import pandas as pd


class MABreakoutDetector:
    """Stateless detector for MA breakout and pullback-to-support."""

    SUPPORT_TOLERANCE = 0.02

    @classmethod
    def detect_breakout(cls, df: pd.DataFrame, ma_period: int = 100) -> Dict[str, Any]:
        if df is None or len(df) < ma_period:
            return {"is_breakout": False, "breakout_days": 0, "ma_value": 0.0}

        ma = df["close"].rolling(window=ma_period).mean()
        latest_price = float(df["close"].iloc[-1])
        latest_ma = float(ma.iloc[-1])

        if np.isnan(latest_ma):
            return {"is_breakout": False, "breakout_days": 0, "ma_value": 0.0}

        is_breakout = latest_price > latest_ma

        breakout_days = 0
        close_vals = df["close"].values
        ma_vals = ma.values
        for i in range(len(df) - 1, -1, -1):
            if np.isnan(ma_vals[i]) or close_vals[i] <= ma_vals[i]:
                break
            breakout_days += 1

        return {
            "is_breakout": is_breakout,
            "breakout_days": breakout_days,
            "ma_value": latest_ma,
            "price": latest_price,
            "distance_pct": (latest_price - latest_ma) / latest_ma * 100 if latest_ma > 0 else 0,
        }

    @classmethod
    def detect_pullback_support(
        cls, df: pd.DataFrame, ma_period: int = 20, tolerance: float = None
    ) -> Dict[str, Any]:
        """Detect if price has pulled back to MA and found support."""
        tol = tolerance if tolerance is not None else cls.SUPPORT_TOLERANCE
        if df is None or len(df) < ma_period:
            return {"is_pullback_support": False, "ma_value": 0.0}

        ma = df["close"].rolling(window=ma_period).mean()
        latest_price = float(df["close"].iloc[-1])
        latest_ma = float(ma.iloc[-1])
        latest_low = float(df["low"].iloc[-1])

        if np.isnan(latest_ma) or latest_ma <= 0:
            return {"is_pullback_support": False, "ma_value": 0.0}

        distance = (latest_price - latest_ma) / latest_ma
        low_distance = (latest_low - latest_ma) / latest_ma

        is_pullback = (
            latest_price >= latest_ma
            and abs(distance) <= tol
            and low_distance <= tol
        )

        return {
            "is_pullback_support": is_pullback,
            "ma_value": latest_ma,
            "price": latest_price,
            "distance_pct": distance * 100,
        }
