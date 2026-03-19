# -*- coding: utf-8 -*-
"""
Multi-Timeframe Analyzer — combines daily and intraday (60min) analysis
to produce trend alignment scores and entry timing signals.

Design:
- Daily trend: determined by MA arrangement (MA5 > MA20 > MA60 = bullish)
- Intraday trend: determined by short-term MA arrangement on 60min bars
- MACD divergence: checked on 60min bars for precise entry
- Alignment score: 0-100, higher means stronger confirmation across timeframes
- Entry timing: strong / moderate / weak / none
"""

from typing import Dict, Any, Optional

import numpy as np
import pandas as pd

from src.indicators.divergence_detector import DivergenceDetector, compute_macd

MIN_DAILY_BARS = 60
MIN_INTRADAY_BARS = 40


def _classify_trend(close: pd.Series, ma_short: int = 5, ma_mid: int = 20, ma_long: int = 60) -> str:
    """
    Classify trend as 'up', 'down', or 'neutral' based on MA arrangement.
    """
    if len(close) < ma_long:
        if len(close) < ma_mid:
            return "neutral"
        ma_s = close.rolling(ma_short, min_periods=1).mean().iloc[-1]
        ma_m = close.rolling(ma_mid, min_periods=1).mean().iloc[-1]
        if ma_s > ma_m:
            return "up"
        elif ma_s < ma_m:
            return "down"
        return "neutral"

    ma_s = close.rolling(ma_short, min_periods=1).mean().iloc[-1]
    ma_m = close.rolling(ma_mid, min_periods=1).mean().iloc[-1]
    ma_l = close.rolling(ma_long, min_periods=1).mean().iloc[-1]

    if ma_s > ma_m > ma_l:
        return "up"
    elif ma_s < ma_m < ma_l:
        return "down"
    return "neutral"


def _compute_alignment_score(daily_trend: str, intraday_trend: Optional[str]) -> int:
    """
    Compute alignment score 0-100.

    Rules:
    - daily up + intraday up = 100
    - daily up + intraday neutral = 70
    - daily up + intraday down = 30
    - daily neutral = 50 base
    - daily down = 20 base
    - no intraday: daily-only score
    """
    base_scores = {"up": 70, "neutral": 50, "down": 20}
    base = base_scores.get(daily_trend, 50)

    if intraday_trend is None:
        return base

    if daily_trend == "up":
        if intraday_trend == "up":
            return 100
        elif intraday_trend == "neutral":
            return 70
        else:
            return 30
    elif daily_trend == "down":
        if intraday_trend == "down":
            return 0
        elif intraday_trend == "neutral":
            return 20
        else:
            return 40
    else:
        if intraday_trend == "up":
            return 65
        elif intraday_trend == "down":
            return 35
        return 50


def _determine_entry_timing(
    alignment_score: int,
    macd_bull_divergence: bool,
) -> str:
    """
    Determine entry timing signal.

    - strong: alignment >= 80 OR (alignment >= 60 AND MACD bull divergence)
    - moderate: alignment >= 60
    - weak: alignment >= 40
    - none: alignment < 40
    """
    if alignment_score >= 80:
        return "strong"
    if alignment_score >= 60 and macd_bull_divergence:
        return "strong"
    if alignment_score >= 60:
        return "moderate"
    if alignment_score >= 40:
        return "weak"
    return "none"


class MultiTimeframeAnalyzer:
    """Combine daily and intraday analysis for entry decisions."""

    def analyze(
        self,
        daily_df: pd.DataFrame,
        intraday_df: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        """
        Run multi-timeframe analysis.

        Args:
            daily_df: Daily OHLCV with 'close' column
            intraday_df: 60-min OHLCV with 'close' column (optional)

        Returns:
            Dict with daily_trend, intraday_trend, alignment_score,
            entry_timing, intraday_macd_bull_divergence,
            intraday_macd_bear_divergence
        """
        daily_close = daily_df["close"].reset_index(drop=True)
        daily_trend = _classify_trend(daily_close)

        intraday_trend = None
        macd_bull = False
        macd_bear = False

        has_intraday = (
            intraday_df is not None
            and len(intraday_df) >= MIN_INTRADAY_BARS
        )

        if has_intraday:
            intra_close = intraday_df["close"].reset_index(drop=True)
            intraday_trend = _classify_trend(intra_close, ma_short=5, ma_mid=10, ma_long=20)

            intra_for_div = intraday_df[["close"]].copy()
            if "high" in intraday_df.columns:
                intra_for_div["high"] = intraday_df["high"].values
            if "low" in intraday_df.columns:
                intra_for_div["low"] = intraday_df["low"].values

            bull_result = DivergenceDetector.detect_bullish(intra_for_div)
            bear_result = DivergenceDetector.detect_bearish(intra_for_div)
            macd_bull = bull_result.get("found", False)
            macd_bear = bear_result.get("found", False)

        alignment = _compute_alignment_score(daily_trend, intraday_trend)
        timing = _determine_entry_timing(alignment, macd_bull)

        result: Dict[str, Any] = {
            "daily_trend": daily_trend,
            "intraday_trend": intraday_trend,
            "alignment_score": alignment,
            "entry_timing": timing,
            "intraday_macd_bull_divergence": macd_bull,
            "intraday_macd_bear_divergence": macd_bear,
        }

        return result
