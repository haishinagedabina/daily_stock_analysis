# -*- coding: utf-8 -*-
"""
Phase 3B-1 — AiReviewProtocol: AI 二筛协议。

从现有 AI 自由文本输出 (operation_advice / ai_summary) 推断结构化字段，
并在规则层优先原则下处理冲突。不要求 AI 改为 JSON 输出。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class AiReviewResult:
    """AI 二筛结构化结果。"""

    ai_trade_stage: Optional[str]  # AI 建议的 trade_stage
    ai_reasoning: str  # 关键判断理由
    ai_confidence: float  # 0.0~1.0 置信度
    raw_advice: str  # 原始 operation_advice (兼容透传)


# ── operation_advice 关键词 → ai_trade_stage 映射 ──────────────────────────

_BULLISH_KEYWORDS: List[str] = ["买入", "加仓"]
_FOCUS_KEYWORDS: List[str] = ["关注"]
_BEARISH_KEYWORDS: List[str] = ["持有", "观望", "减仓", "卖出"]

# ── market_regime 对 ai_trade_stage 的上限约束 ─────────────────────────────

_REGIME_STAGE_CEILING: Dict[str, str] = {
    "stand_aside": "watch",
    "defensive": "probe_entry",
    # balanced / aggressive 无上限
}

# trade_stage 严格排序 (低→高)
_STAGE_ORDER: Dict[str, int] = {
    "reject": 0,
    "stand_aside": 1,
    "watch": 2,
    "focus": 3,
    "probe_entry": 4,
    "add_on_strength": 5,
}


class AiReviewProtocol:
    """构建结构化 prompt + 解析 AI 输出 + 规则层裁决冲突处理。"""

    # ── public API ──────────────────────────────────────────────────────

    def build_review_prompt(
        self,
        code: str,
        name: str,
        rule_trade_stage: str,
        setup_type: str,
        market_regime: str,
        theme_position: str,
        entry_maturity: str,
        trade_plan: Optional[dict],
        factor_snapshot: dict,
    ) -> str:
        """构建注入五层上下文的结构化 prompt 附加段。"""
        lines = [
            "",
            "## 五层决策上下文",
            f"- 股票: {name} ({code})",
            f"- 市场环境: {market_regime}",
            f"- 买点类型: {setup_type}, 成熟度: {entry_maturity}",
            f"- 题材地位: {theme_position}",
            f"- 规则层建议: {rule_trade_stage}",
        ]
        if trade_plan:
            stop_loss = trade_plan.get("stop_loss_rule", "")
            if stop_loss:
                lines.append(f"- 止损规则: {stop_loss}")
        lines.append("")
        lines.append("请在 operation_advice 中考虑以上约束。")
        return "\n".join(lines)

    def parse_ai_response(
        self,
        ai_summary: Optional[str],
        ai_operation_advice: Optional[str],
        rule_trade_stage: str,
        market_regime: str,
    ) -> AiReviewResult:
        """从 AI 输出提取结构化字段 + 裁决冲突。"""
        advice = (ai_operation_advice or "").strip()
        summary = (ai_summary or "").strip()

        # 无有效输出
        if not advice and not summary:
            return AiReviewResult(
                ai_trade_stage=None,
                ai_reasoning="AI 无输出",
                ai_confidence=0.0,
                raw_advice="",
            )

        # 映射 advice → raw_stage
        raw_stage = self._map_advice_to_stage(advice)

        # 规则层冲突处理
        final_stage, reasoning = self._apply_regime_ceiling(
            raw_stage, market_regime, rule_trade_stage, advice
        )

        # 置信度
        confidence = self._compute_confidence(
            final_stage, raw_stage, rule_trade_stage, market_regime
        )

        return AiReviewResult(
            ai_trade_stage=final_stage,
            ai_reasoning=reasoning,
            ai_confidence=confidence,
            raw_advice=advice,
        )

    # ── private helpers ─────────────────────────────────────────────────

    def _map_advice_to_stage(self, advice: str) -> Optional[str]:
        """将 operation_advice 关键词映射为 trade_stage。"""
        if not advice:
            return None
        for kw in _BULLISH_KEYWORDS:
            if kw in advice:
                return "probe_entry"
        for kw in _FOCUS_KEYWORDS:
            if kw in advice:
                return "focus"
        for kw in _BEARISH_KEYWORDS:
            if kw in advice:
                return "watch"
        return None

    def _apply_regime_ceiling(
        self,
        raw_stage: Optional[str],
        market_regime: str,
        rule_trade_stage: str,
        advice: str,
    ) -> Tuple[Optional[str], str]:
        """应用 market_regime 上限约束，返回 (final_stage, reasoning)。"""
        if raw_stage is None:
            return None, "AI 未给出明确建议"

        ceiling = _REGIME_STAGE_CEILING.get(market_regime)
        if ceiling is None:
            return raw_stage, f"AI建议: {advice}"

        raw_order = _STAGE_ORDER.get(raw_stage, 0)
        ceiling_order = _STAGE_ORDER.get(ceiling, 0)

        if raw_order > ceiling_order:
            # 冲突: AI 建议高于 regime 上限 → 降级
            return ceiling, (
                f"冲突: AI建议'{advice}'但{market_regime}环境限制，"
                f"降级为{ceiling}"
            )

        return raw_stage, f"AI建议: {advice}"

    def _compute_confidence(
        self,
        final_stage: Optional[str],
        raw_stage: Optional[str],
        rule_trade_stage: str,
        market_regime: str,
    ) -> float:
        """基于一致性计算置信度。"""
        if final_stage is None:
            return 0.0

        base = 0.5

        # AI 与规则层一致 → +0.2
        if final_stage == rule_trade_stage:
            base += 0.2

        # AI 被降级（冲突） → -0.2
        if raw_stage != final_stage:
            base -= 0.2

        # stand_aside 环境下 bullish → 额外 -0.1
        if market_regime == "stand_aside" and raw_stage in ("probe_entry", "add_on_strength"):
            base -= 0.1

        return max(0.0, min(1.0, base))
