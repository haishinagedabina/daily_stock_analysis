# -*- coding: utf-8 -*-
"""
Phase 3A — TradePlanBuilder: 根据 trade_stage + setup_type 生成可执行交易计划。

仅 probe_entry / add_on_strength 生成 TradePlan，其余阶段返回 None。
"""

from __future__ import annotations

from typing import Dict, Optional

from src.schemas.trading_types import (
    CandidatePoolLevel,
    EntryMaturity,
    RiskLevel,
    SetupType,
    TradePlan,
    TradeStage,
)

# ── 止损模板 ─────────────────────────────────────────────────────────────────

_STOP_LOSS_TEMPLATES: Dict[SetupType, str] = {
    SetupType.BOTTOM_DIVERGENCE_BREAKOUT: "跌破底背离确认K线低点止损",
    SetupType.LOW123_BREAKOUT: "跌破123结构第3低点止损",
    SetupType.TREND_BREAKOUT: "跌破突破K线实体下沿或MA20止损",
    SetupType.TREND_PULLBACK: "跌破回踩MA20低点止损",
    SetupType.GAP_BREAKOUT: "回补缺口止损",
    SetupType.LIMITUP_STRUCTURE: "跌破涨停板开板价止损",
}

_DEFAULT_STOP_LOSS = "跌破近期支撑位止损"

# ── 止盈模板 ─────────────────────────────────────────────────────────────────

_TAKE_PROFIT_TEMPLATES: Dict[SetupType, str] = {
    SetupType.BOTTOM_DIVERGENCE_BREAKOUT: "目标前高压力位;分批止盈,首目标+10%减半",
    SetupType.LOW123_BREAKOUT: "目标前高或MA100;突破后逐步移动止盈",
    SetupType.TREND_BREAKOUT: "沿MA10移动止盈;跌破MA10减仓",
    SetupType.TREND_PULLBACK: "反弹至前高区域止盈;跌破MA20离场",
    SetupType.GAP_BREAKOUT: "持仓3日内冲高减仓;缩量回落离场",
    SetupType.LIMITUP_STRUCTURE: "次日高开冲高减半;3日内未续涨则离场",
}

_DEFAULT_TAKE_PROFIT = "分批止盈;跌破关键均线离场"

# ── 加仓模板 ─────────────────────────────────────────────────────────────────

_ADD_RULE_TEMPLATES: Dict[SetupType, str] = {
    SetupType.BOTTOM_DIVERGENCE_BREAKOUT: "突破前高+放量确认后加仓;最多加仓1次;跌破加仓K低点取消",
    SetupType.LOW123_BREAKOUT: "突破颈线+放量后加仓;最多加仓1次;跌破颈线取消",
    SetupType.TREND_BREAKOUT: "回踩MA20不破+放量反弹加仓;最多加仓1次;跌破MA20取消",
    SetupType.TREND_PULLBACK: "二次回踩MA20+缩量企稳加仓;最多加仓1次;跌破前低取消",
    SetupType.GAP_BREAKOUT: "缺口上方放量突破前高加仓;最多加仓1次;回补缺口取消",
    SetupType.LIMITUP_STRUCTURE: "连板次日竞价强势加仓;最多加仓1次;开板即取消",
}

_DEFAULT_ADD_RULE = "确认突破+放量后加仓;最多加仓1次;跌破关键位取消"

# ── 持仓期望 ─────────────────────────────────────────────────────────────────

_SWING_SETUPS = frozenset({
    SetupType.BOTTOM_DIVERGENCE_BREAKOUT,
    SetupType.LOW123_BREAKOUT,
    SetupType.TREND_BREAKOUT,
})

# ── probe_entry 仓位映射 ────────────────────────────────────────────────────

_PROBE_POSITION: Dict[RiskLevel, str] = {
    RiskLevel.HIGH: "1/10仓",
    RiskLevel.MEDIUM: "1/5仓",
    RiskLevel.LOW: "1/3仓",
}

# ── add_on_strength 仓位映射 ─────────────────────────────────────────────────

_ADD_ON_POSITION: Dict[RiskLevel, str] = {
    RiskLevel.HIGH: "1/5仓",
    RiskLevel.MEDIUM: "1/3仓",
    RiskLevel.LOW: "1/2仓",
}

_INVALIDATION_RULE = "买入后3个交易日未启动则离场"


def _build_execution_note(setup_type: SetupType, factor_snapshot: dict) -> str:
    ma20 = factor_snapshot.get("ma20")
    ma100 = factor_snapshot.get("ma100")
    close = factor_snapshot.get("close")
    anchors = []
    if close is not None:
        anchors.append(f"现价{float(close):.2f}")
    if ma20 is not None:
        anchors.append(f"MA20={float(ma20):.2f}")
    if ma100 is not None:
        anchors.append(f"MA100={float(ma100):.2f}")

    anchor_note = "，".join(anchors) if anchors else "以盘中结构低点与均线支撑作为执行锚点"
    if setup_type == SetupType.LIMITUP_STRUCTURE:
        return f"优先观察涨停结构是否继续封板或缩量承接，{anchor_note}"
    if setup_type == SetupType.GAP_BREAKOUT:
        return f"重点盯缺口不回补与前高突破，{anchor_note}"
    if setup_type in _SWING_SETUPS:
        return f"围绕趋势延续与关键均线支撑执行，{anchor_note}"
    return f"按结构确认和止损锚点执行，{anchor_note}"


class TradePlanBuilder:
    """根据 L5 trade_stage 和 L4 setup_type 生成可执行交易计划。"""

    def build(
        self,
        trade_stage: TradeStage,
        setup_type: SetupType,
        entry_maturity: EntryMaturity,
        risk_level: RiskLevel,
        pool_level: CandidatePoolLevel,
        factor_snapshot: dict,
    ) -> Optional[TradePlan]:
        if trade_stage not in (TradeStage.PROBE_ENTRY, TradeStage.ADD_ON_STRENGTH):
            return None

        is_add_on = trade_stage == TradeStage.ADD_ON_STRENGTH

        return TradePlan(
            initial_position=(
                _ADD_ON_POSITION.get(risk_level, "1/3仓")
                if is_add_on
                else _PROBE_POSITION.get(risk_level, "1/5仓")
            ),
            add_rule=(
                _ADD_RULE_TEMPLATES.get(setup_type, _DEFAULT_ADD_RULE)
                if is_add_on
                else None
            ),
            stop_loss_rule=_STOP_LOSS_TEMPLATES.get(setup_type, _DEFAULT_STOP_LOSS),
            take_profit_plan=_TAKE_PROFIT_TEMPLATES.get(setup_type, _DEFAULT_TAKE_PROFIT),
            invalidation_rule=_INVALIDATION_RULE,
            risk_level=risk_level,
            holding_expectation=(
                "1~2周波段" if setup_type in _SWING_SETUPS else "3~5日短线"
            ),
            execution_note=_build_execution_note(setup_type, factor_snapshot),
        )
