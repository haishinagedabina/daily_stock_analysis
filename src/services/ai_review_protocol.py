# -*- coding: utf-8 -*-
"""
Phase 3B-1 — AiReviewProtocol: AI 二筛协议。

优先从 AI 输出中解析固定 JSON schema，失败时 fallback 到关键词匹配。
规则层优先原则下处理冲突。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── AI Review JSON Schema 定义 ───────────────────────────────────────────────

AI_REVIEW_SCHEMA = {
    "suggested_stage": "probe_entry|focus|watch|stand_aside|reject",
    "confidence": "0.0~1.0",
    "reasoning": "string: 关键判断理由",
    "risk_flags": ["string: 风险标记列表"],
    "summary": "string: 一句话总结",
    "environment_ok": "bool: AI 对市场环境的独立判断",
    "theme_alignment": "bool: AI 对题材一致性的判断",
    "entry_quality": "low|medium|high: AI 对买点质量的判断",
}

_VALID_STAGES = frozenset({
    "probe_entry", "add_on_strength", "focus", "watch", "stand_aside", "reject",
})


@dataclass
class AiReviewResult:
    """AI 二筛结构化结果。"""

    ai_trade_stage: Optional[str]  # AI 建议的 trade_stage
    ai_reasoning: str  # 关键判断理由
    ai_confidence: float  # 0.0~1.0 置信度
    raw_advice: str  # 原始 operation_advice (兼容透传)
    risk_flags: List[str] = field(default_factory=list)  # 风险标记
    ai_environment_ok: Optional[bool] = None  # AI 对市场环境的独立判断
    ai_theme_alignment: Optional[bool] = None  # AI 对题材一致性的判断
    ai_entry_quality: Optional[str] = None  # low|medium|high
    stage_conflict: bool = False  # 规则层 vs AI 建议是否冲突


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
        """构建注入五层上下文的结构化 prompt 附加段，要求 AI 以 JSON 格式输出。"""
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
        lines.append("## 输出要求")
        lines.append("请严格以如下 JSON 格式输出你的分析结论，不要包含其他文字：")
        lines.append("```json")
        lines.append("{")
        lines.append('  "suggested_stage": "probe_entry|focus|watch|stand_aside|reject",')
        lines.append('  "confidence": 0.0,')
        lines.append('  "reasoning": "关键判断理由",')
        lines.append('  "risk_flags": ["风险标记1", "风险标记2"],')
        lines.append('  "summary": "一句话总结",')
        lines.append('  "environment_ok": true,')
        lines.append('  "theme_alignment": true,')
        lines.append('  "entry_quality": "low|medium|high"')
        lines.append("}")
        lines.append("```")
        lines.append("")
        lines.append("suggested_stage 取值范围: probe_entry, focus, watch, stand_aside, reject")
        lines.append("environment_ok: 你对当前市场环境是否适合操作的独立判断（bool）")
        lines.append("theme_alignment: 该股票是否与当前主流题材一致（bool）")
        lines.append("entry_quality: 买点质量评估（low/medium/high）")

        return "\n".join(lines)

    def parse_ai_response(
        self,
        ai_summary: Optional[str],
        ai_operation_advice: Optional[str],
        rule_trade_stage: str,
        market_regime: str,
    ) -> AiReviewResult:
        """从 AI 输出提取结构化字段 + 裁决冲突。

        优先尝试 JSON 解析，失败时 fallback 到关键词匹配。
        """
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

        # 优先尝试从 advice 或 summary 中解析 JSON
        json_result = self._try_parse_json(advice) or self._try_parse_json(summary)

        if json_result is not None:
            return self._build_from_json(json_result, advice, rule_trade_stage, market_regime)

        # Fallback: 关键词匹配
        return self._build_from_keywords(advice, summary, rule_trade_stage, market_regime)

    # ── JSON 解析路径 ──────────────────────────────────────────────────

    @staticmethod
    def _try_parse_json(text: str) -> Optional[dict]:
        """尝试从文本中提取并解析 JSON 对象。"""
        if not text:
            return None

        # 尝试直接解析
        try:
            obj = json.loads(text)
            if isinstance(obj, dict) and "suggested_stage" in obj:
                return obj
        except (json.JSONDecodeError, ValueError):
            pass

        # 尝试从 ```json ... ``` 代码块提取
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            try:
                obj = json.loads(match.group(1))
                if isinstance(obj, dict) and "suggested_stage" in obj:
                    return obj
            except (json.JSONDecodeError, ValueError):
                pass

        # 尝试提取第一个 {...} 块
        match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if match:
            try:
                obj = json.loads(match.group(0))
                if isinstance(obj, dict) and "suggested_stage" in obj:
                    return obj
            except (json.JSONDecodeError, ValueError):
                pass

        return None

    def _build_from_json(
        self,
        data: dict,
        raw_advice: str,
        rule_trade_stage: str,
        market_regime: str,
    ) -> AiReviewResult:
        """从 JSON 解析结果构建 AiReviewResult。"""
        raw_stage = data.get("suggested_stage")
        if raw_stage not in _VALID_STAGES:
            raw_stage = None

        reasoning = data.get("reasoning", "")
        risk_flags = data.get("risk_flags", [])
        if not isinstance(risk_flags, list):
            risk_flags = []
        json_confidence = data.get("confidence")
        ai_summary = data.get("summary", "")

        # 提取新增字段
        environment_ok = data.get("environment_ok")
        if not isinstance(environment_ok, bool):
            environment_ok = None
        theme_alignment = data.get("theme_alignment")
        if not isinstance(theme_alignment, bool):
            theme_alignment = None
        entry_quality = data.get("entry_quality")
        if entry_quality not in ("low", "medium", "high"):
            entry_quality = None

        # stage_conflict: 规则层 vs AI 建议不一致
        stage_conflict = (raw_stage is not None and raw_stage != rule_trade_stage)

        # 应用 regime ceiling
        final_stage, conflict_reason = self._apply_regime_ceiling(
            raw_stage, market_regime, rule_trade_stage, raw_advice
        )

        # 优先使用 AI 返回的 confidence，缺失时走计算逻辑
        if json_confidence is not None:
            try:
                confidence = max(0.0, min(1.0, float(json_confidence)))
            except (TypeError, ValueError):
                confidence = self._compute_confidence(
                    final_stage, raw_stage, rule_trade_stage, market_regime
                )
            # AI 被降级时扣减置信度
            if raw_stage != final_stage:
                confidence = max(0.0, confidence - 0.2)
        else:
            confidence = self._compute_confidence(
                final_stage, raw_stage, rule_trade_stage, market_regime
            )

        full_reasoning = conflict_reason if conflict_reason != f"AI建议: {raw_advice}" else reasoning
        if not full_reasoning:
            full_reasoning = ai_summary or f"AI建议: {raw_advice}"

        return AiReviewResult(
            ai_trade_stage=final_stage,
            ai_reasoning=full_reasoning,
            ai_confidence=confidence,
            raw_advice=raw_advice,
            risk_flags=risk_flags,
            ai_environment_ok=environment_ok,
            ai_theme_alignment=theme_alignment,
            ai_entry_quality=entry_quality,
            stage_conflict=stage_conflict,
        )

    # ── 关键词 Fallback 路径 ────────────────────────────────────────────

    def _build_from_keywords(
        self,
        advice: str,
        summary: str,
        rule_trade_stage: str,
        market_regime: str,
    ) -> AiReviewResult:
        """关键词匹配 fallback（兼容旧版 AI 输出）。"""
        raw_stage = self._map_advice_to_stage(advice)

        final_stage, reasoning = self._apply_regime_ceiling(
            raw_stage, market_regime, rule_trade_stage, advice
        )

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
