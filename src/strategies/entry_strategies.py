# -*- coding: utf-8 -*-
"""
Entry Strategies C, D, and D-Enhanced.

Strategy C: Gap/Limit-Up Breakout
  - Breakaway gap (gap-up + volume surge) OR
  - Limit-up that breaks above the recent high
  - Volume confirmation (> 1.5x 5-day average)

Strategy D: MA100 Selection (daily, no 60-min yet)
  Step 1: Price must be above MA100
  Step 2: MA100/MA20 breakout confirmed
  Step 3: Pullback to MA support (optional entry refinement)
  Output: stop-loss price based on the highest MA below price

Strategy D-Enhanced: MA100 Selection with 60-min precise entry
  Extends Strategy D with multi-timeframe alignment and MACD divergence
  from 60-minute bars for more precise entry timing.
"""

from typing import Dict, Any, Optional

import numpy as np
import pandas as pd

from src.indicators.ma_breakout_detector import MABreakoutDetector
from src.indicators.gap_detector import GapDetector
from src.indicators.limit_up_detector import LimitUpDetector
from src.indicators.multi_timeframe_analyzer import MultiTimeframeAnalyzer


class EntryStrategyC:
    """Gap/Limit-Up Breakout strategy."""

    @classmethod
    def evaluate(cls, df: pd.DataFrame, board: str = "main") -> Dict[str, Any]:
        if df is None or len(df) < 10:
            return {"triggered": False, "reason": "insufficient data", "score": 0}

        gap_result = GapDetector.detect_breakaway_gap(df)
        limit_result = LimitUpDetector.is_breakout_limit_up(df, board=board)

        gap_triggered = gap_result.get("is_breakaway", False)
        limit_triggered = (
            limit_result.get("is_limit_up", False)
            and limit_result.get("is_breakout_high", False)
        )

        triggered = gap_triggered or limit_triggered

        score = 0
        reasons = []

        if gap_triggered:
            score += 50
            reasons.append(f"breakaway gap (+{gap_result.get('gap_pct', 0):.1f}%)")
        if limit_triggered:
            score += 50
            reasons.append(f"limit-up breakout (pct={limit_result.get('pct_chg', 0):.1f}%)")

        # Volume bonus
        vol_avg = float(df["volume"].iloc[-6:-1].mean()) if len(df) >= 6 else 0
        vol_curr = float(df["volume"].iloc[-1])
        vol_ratio = vol_curr / vol_avg if vol_avg > 0 else 0
        if vol_ratio >= 2.0:
            score = min(100, score + 20)
        elif vol_ratio >= 1.5:
            score = min(100, score + 10)

        return {
            "triggered": triggered,
            "reason": " + ".join(reasons) if reasons else "no signal",
            "score": score,
            "gap": gap_result,
            "limit_up": limit_result,
            "volume_ratio": vol_ratio,
        }


class EntryStrategyD:
    """MA100 Selection strategy (daily version)."""

    @classmethod
    def evaluate(
        cls,
        df: pd.DataFrame,
        ma100_confirm_days: int = 3,
        support_tolerance: float = 0.02,
    ) -> Dict[str, Any]:
        if df is None or len(df) < 100:
            return {
                "triggered": False,
                "above_ma100": False,
                "ma20_breakout": False,
                "ma100_breakout_days": 0,
                "pullback_support": False,
                "stop_loss_price": 0.0,
                "stop_loss_ma": "",
                "score": 0,
                "reason": "insufficient data",
            }

        # Step 1: MA100 filter
        ma100_result = MABreakoutDetector.detect_breakout(df, ma_period=100)
        above_ma100 = ma100_result["is_breakout"]
        breakout_days = ma100_result["breakout_days"]

        if not above_ma100:
            return {
                "triggered": False,
                "above_ma100": False,
                "ma20_breakout": False,
                "ma100_breakout_days": 0,
                "pullback_support": False,
                "stop_loss_price": 0.0,
                "stop_loss_ma": "",
                "score": 0,
                "reason": "price below MA100",
            }

        # Step 2: MA20 breakout
        ma20_result = MABreakoutDetector.detect_breakout(df, ma_period=20)
        ma20_breakout = ma20_result["is_breakout"]

        # Step 3: Pullback support (MA20 or MA100)
        pullback_ma20 = MABreakoutDetector.detect_pullback_support(
            df, ma_period=20, tolerance=support_tolerance
        )
        pullback_ma100 = MABreakoutDetector.detect_pullback_support(
            df, ma_period=100, tolerance=support_tolerance
        )

        has_pullback = (
            pullback_ma20["is_pullback_support"]
            or pullback_ma100["is_pullback_support"]
        )

        # Trigger logic: above MA100 + confirmed + (MA20 breakout or pullback support)
        confirmed = breakout_days >= ma100_confirm_days
        triggered = confirmed and (ma20_breakout or has_pullback)

        # Stop-loss: use the highest MA below price as stop reference
        price = float(df["close"].iloc[-1])
        ma20_val = ma20_result.get("ma_value", 0)
        ma100_val = ma100_result.get("ma_value", 0)

        stop_loss_price = 0.0
        stop_loss_ma = ""
        if ma20_val > 0 and ma20_val < price:
            stop_loss_price = ma20_val
            stop_loss_ma = "MA20"
        if ma100_val > 0 and ma100_val < price and ma100_val > stop_loss_price:
            stop_loss_price = ma100_val
            stop_loss_ma = "MA100"
        # Use a tighter stop if MA20 is closer to price
        if ma20_val > 0 and ma20_val < price and ma20_val < ma100_val:
            stop_loss_price = ma20_val
            stop_loss_ma = "MA20"

        # Scoring
        score = 0
        if above_ma100:
            score += 30
        if confirmed:
            score += 20
        if ma20_breakout:
            score += 20
        if has_pullback:
            score += 20
        # Volume bonus
        if len(df) >= 6:
            vol_avg = float(df["volume"].iloc[-6:-1].mean())
            vol_curr = float(df["volume"].iloc[-1])
            vol_ratio = vol_curr / vol_avg if vol_avg > 0 else 0
            if vol_ratio >= 1.5:
                score = min(100, score + 10)

        return {
            "triggered": triggered,
            "above_ma100": above_ma100,
            "ma100_breakout_days": breakout_days,
            "ma20_breakout": ma20_breakout,
            "pullback_support": has_pullback,
            "stop_loss_price": stop_loss_price,
            "stop_loss_ma": stop_loss_ma,
            "score": min(100, score),
            "reason": "MA100 selection" if triggered else "conditions not fully met",
        }


class EntryStrategyDEnhanced:
    """
    MA100 Selection with 60-minute precise entry.

    Combines daily EntryStrategyD logic with multi-timeframe alignment
    and 60-min MACD divergence for better entry timing.
    """

    _mtf = MultiTimeframeAnalyzer()

    @classmethod
    def evaluate(
        cls,
        daily_df: pd.DataFrame,
        intraday_df: Optional[pd.DataFrame] = None,
        ma100_confirm_days: int = 3,
        support_tolerance: float = 0.02,
    ) -> Dict[str, Any]:
        base_result = EntryStrategyD.evaluate(
            daily_df, ma100_confirm_days=ma100_confirm_days,
            support_tolerance=support_tolerance,
        )

        mtf_result = cls._mtf.analyze(
            daily_df=daily_df, intraday_df=intraday_df
        )

        alignment = mtf_result["alignment_score"]
        timing = mtf_result["entry_timing"]
        bull_div = mtf_result["intraday_macd_bull_divergence"]
        bear_div = mtf_result["intraday_macd_bear_divergence"]

        score = base_result["score"]
        if alignment >= 80:
            score = min(100, score + 15)
        elif alignment >= 60:
            score = min(100, score + 5)
        elif alignment < 40:
            score = max(0, score - 10)

        if bull_div:
            score = min(100, score + 10)

        triggered = base_result["triggered"]
        if triggered and alignment < 30:
            triggered = False

        base_result.update({
            "alignment_score": alignment,
            "entry_timing": timing,
            "daily_trend": mtf_result["daily_trend"],
            "intraday_trend": mtf_result["intraday_trend"],
            "intraday_macd_bull_divergence": bull_div,
            "intraday_macd_bear_divergence": bear_div,
            "score": min(100, score),
        })
        if not triggered:
            base_result["triggered"] = False

        return base_result
