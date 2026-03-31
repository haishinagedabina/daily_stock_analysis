# -*- coding: utf-8 -*-
"""
L1 市场环境引擎 — 输出 MarketEnvironment (regime + risk_level)。

将 MarketGuard 的 MA100 检查 + 指数日线 + 涨跌家数赚钱效应综合判定 market_regime。

判定规则:
  aggressive : 指数>MA100, MA20↑, 赚钱效应好（涨停 > 跌停×2）
  balanced   : 指数>MA100, 赚钱效应中性 或 MA20 横盘
  defensive  : 指数<MA100, MA20 企稳 或 涨跌比>0.8
  stand_aside: 指数<MA100, MA20↓, 赚钱效应差（跌停 > 涨停）
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from src.core.market_guard import MarketGuardResult
from src.schemas.trading_types import MarketEnvironment, MarketRegime, RiskLevel

logger = logging.getLogger(__name__)

# ── 可配置常量 ──────────────────────────────────────────────────────────────
MIN_BARS_FOR_MA20 = 20
MA20_SLOPE_THRESHOLD = 0.5        # 每日平均涨跌 > 此值视为上升
MA20_SLOPE_DOWN_THRESHOLD = -0.5  # 每日平均涨跌 < 此值视为下降
UP_DOWN_RATIO_DEFENSIVE = 0.8     # 涨跌比 > 此值视为市场尚可
AGGRESSIVE_LIMIT_RATIO = 2.0      # 涨停 > 跌停×此倍数 = 赚钱效应好


class MarketEnvironmentEngine:
    """L1 市场环境判定器。"""

    def assess(
        self,
        guard_result: MarketGuardResult,
        index_bars: Optional[pd.DataFrame],
        market_stats: Optional[dict],
    ) -> MarketEnvironment:
        is_safe = guard_result.is_safe
        index_price = guard_result.index_price
        index_ma100 = guard_result.index_ma100

        ma20_slope = self._compute_ma20_slope(index_bars)
        money_effect = self._assess_money_effect(market_stats)

        regime = self._determine_regime(is_safe, ma20_slope, money_effect, market_stats)
        risk_level = _regime_to_risk(regime)
        message = self._build_message(regime, is_safe, ma20_slope, money_effect, guard_result)

        return MarketEnvironment(
            regime=regime,
            risk_level=risk_level,
            index_price=index_price,
            index_ma100=index_ma100,
            is_safe=is_safe,
            message=message,
        )

    # ── 内部方法 ─────────────────────────────────────────────────────────────

    def _compute_ma20_slope(self, bars: Optional[pd.DataFrame]) -> float:
        """计算 MA20 斜率（每日平均涨跌点数）。数据不足返回 0.0。"""
        if bars is None or bars.empty or len(bars) < MIN_BARS_FOR_MA20:
            return 0.0

        closes = bars["close"].astype(float)
        ma20 = closes.rolling(window=20).mean()
        recent_ma20 = ma20.dropna()
        if len(recent_ma20) < 5:
            return 0.0

        # 最近 5 日 MA20 的线性斜率
        last5 = recent_ma20.iloc[-5:].values
        slope = (last5[-1] - last5[0]) / 4.0
        return float(slope)

    def _assess_money_effect(self, stats: Optional[dict]) -> str:
        """评估赚钱效应: 'good' / 'neutral' / 'bad' / 'unknown'。"""
        if not stats:
            return "unknown"

        limit_up = stats.get("limit_up_count", 0)
        limit_down = stats.get("limit_down_count", 0)

        if limit_up > limit_down * AGGRESSIVE_LIMIT_RATIO and limit_up > 10:
            return "good"
        if limit_down > limit_up and limit_down > 10:
            return "bad"
        return "neutral"

    def _determine_regime(
        self,
        is_safe: bool,
        ma20_slope: float,
        money_effect: str,
        market_stats: Optional[dict],
    ) -> MarketRegime:
        if is_safe:
            return self._regime_above_ma100(ma20_slope, money_effect)
        else:
            return self._regime_below_ma100(ma20_slope, money_effect, market_stats)

    def _regime_above_ma100(self, ma20_slope: float, money_effect: str) -> MarketRegime:
        """指数 > MA100 的分支。"""
        ma20_up = ma20_slope > MA20_SLOPE_THRESHOLD
        if ma20_up and money_effect == "good":
            return MarketRegime.AGGRESSIVE
        return MarketRegime.BALANCED

    def _regime_below_ma100(
        self, ma20_slope: float, money_effect: str, market_stats: Optional[dict],
    ) -> MarketRegime:
        """指数 < MA100 的分支。"""
        ma20_down = ma20_slope < MA20_SLOPE_DOWN_THRESHOLD

        # 涨跌比 > 0.8 → 市场尚可，不至于 stand_aside
        up_down_ratio = self._up_down_ratio(market_stats)
        if up_down_ratio is not None and up_down_ratio > UP_DOWN_RATIO_DEFENSIVE:
            return MarketRegime.DEFENSIVE

        # MA20 企稳 → defensive
        if not ma20_down:
            return MarketRegime.DEFENSIVE

        # MA20↓ + 赚钱效应差 → stand_aside
        if ma20_down and money_effect == "bad":
            return MarketRegime.STAND_ASIDE

        # MA20↓ 但赚钱效应不差 → defensive
        return MarketRegime.DEFENSIVE

    def _up_down_ratio(self, stats: Optional[dict]) -> Optional[float]:
        if not stats:
            return None
        up = stats.get("up_count", 0)
        down = stats.get("down_count", 0)
        if down == 0:
            return None if up == 0 else 999.0
        return up / down

    def _build_message(
        self,
        regime: MarketRegime,
        is_safe: bool,
        ma20_slope: float,
        money_effect: str,
        guard: MarketGuardResult,
    ) -> str:
        parts = [f"regime={regime.value}"]
        parts.append(f"MA100={'above' if is_safe else 'below'}")
        parts.append(f"MA20_slope={ma20_slope:+.1f}")
        parts.append(f"money_effect={money_effect}")
        if guard.message:
            parts.append(guard.message)
        return " | ".join(parts)


def _regime_to_risk(regime: MarketRegime) -> RiskLevel:
    return {
        MarketRegime.AGGRESSIVE: RiskLevel.LOW,
        MarketRegime.BALANCED: RiskLevel.MEDIUM,
        MarketRegime.DEFENSIVE: RiskLevel.HIGH,
        MarketRegime.STAND_ASIDE: RiskLevel.HIGH,
    }[regime]
