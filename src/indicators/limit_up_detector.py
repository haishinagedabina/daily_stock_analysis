# -*- coding: utf-8 -*-
"""
Limit-Up Detector — identifies daily limit-up events and whether they
constitute a breakout above the recent high.

Board types:
- main: 10% limit (default)
- star: 20% limit (科创板 688xxx)
- gem_new: 20% limit (创业板 300xxx post-reform)
"""

from typing import Dict, Any

import numpy as np
import pandas as pd


LIMIT_THRESHOLDS = {
    "main": 9.8,
    "star": 19.5,
    "gem_new": 19.5,
}


class LimitUpDetector:
    """Stateless detector for limit-up events."""

    @classmethod
    def is_limit_up(cls, pct_chg: float, board: str = "main") -> bool:
        threshold = LIMIT_THRESHOLDS.get(board, 9.8)
        return pct_chg >= threshold

    @classmethod
    def is_breakout_limit_up(
        cls, df: pd.DataFrame, lookback: int = 20, board: str = "main"
    ) -> Dict[str, Any]:
        if df is None or len(df) < 3:
            return {"is_limit_up": False, "is_breakout_high": False}

        latest = df.iloc[-1]
        pct = float(latest.get("pct_chg", 0))
        is_lu = cls.is_limit_up(pct, board)

        if not is_lu:
            return {"is_limit_up": False, "is_breakout_high": False, "pct_chg": pct}

        start = max(0, len(df) - 1 - lookback)
        prev_high = float(df["high"].iloc[start:-1].max())
        curr_close = float(latest["close"])
        is_breakout = curr_close > prev_high

        return {
            "is_limit_up": True,
            "is_breakout_high": is_breakout,
            "pct_chg": pct,
            "prev_high": prev_high,
            "close": curr_close,
        }
