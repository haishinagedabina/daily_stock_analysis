# -*- coding: utf-8 -*-
"""AiReviewProtocol 单元测试 — Phase 3B-1 TDD red→green。"""

from __future__ import annotations

import unittest

from src.services.ai_review_protocol import AiReviewProtocol


class TestParseAiResponse(unittest.TestCase):
    """Tests for AiReviewProtocol.parse_ai_response()."""

    def setUp(self) -> None:
        self.protocol = AiReviewProtocol()

    # ── operation_advice → ai_trade_stage 映射 ──────────────────────

    def test_buy_maps_to_probe_entry(self) -> None:
        result = self.protocol.parse_ai_response(
            ai_summary="趋势强势",
            ai_operation_advice="买入",
            rule_trade_stage="probe_entry",
            market_regime="balanced",
        )
        self.assertEqual(result.ai_trade_stage, "probe_entry")

    def test_add_maps_to_probe_entry(self) -> None:
        result = self.protocol.parse_ai_response(
            ai_summary="强势加仓",
            ai_operation_advice="加仓",
            rule_trade_stage="add_on_strength",
            market_regime="aggressive",
        )
        self.assertEqual(result.ai_trade_stage, "probe_entry")

    def test_focus_maps_to_focus(self) -> None:
        result = self.protocol.parse_ai_response(
            ai_summary="关注",
            ai_operation_advice="关注",
            rule_trade_stage="focus",
            market_regime="balanced",
        )
        self.assertEqual(result.ai_trade_stage, "focus")

    def test_hold_maps_to_watch(self) -> None:
        result = self.protocol.parse_ai_response(
            ai_summary="持有观察",
            ai_operation_advice="持有",
            rule_trade_stage="watch",
            market_regime="balanced",
        )
        self.assertEqual(result.ai_trade_stage, "watch")

    def test_observe_maps_to_watch(self) -> None:
        result = self.protocol.parse_ai_response(
            ai_summary="观望",
            ai_operation_advice="观望",
            rule_trade_stage="watch",
            market_regime="balanced",
        )
        self.assertEqual(result.ai_trade_stage, "watch")

    def test_reduce_maps_to_watch(self) -> None:
        result = self.protocol.parse_ai_response(
            ai_summary="减仓离场",
            ai_operation_advice="减仓",
            rule_trade_stage="watch",
            market_regime="defensive",
        )
        self.assertEqual(result.ai_trade_stage, "watch")

    def test_sell_maps_to_watch(self) -> None:
        result = self.protocol.parse_ai_response(
            ai_summary="卖出",
            ai_operation_advice="卖出",
            rule_trade_stage="watch",
            market_regime="defensive",
        )
        self.assertEqual(result.ai_trade_stage, "watch")

    # ── 规则层优先冲突处理 ──────────────────────────────────────────

    def test_stand_aside_overrides_ai_buy(self) -> None:
        """stand_aside 下 AI 返回买入 → 强制降级 watch"""
        result = self.protocol.parse_ai_response(
            ai_summary="趋势看好",
            ai_operation_advice="买入",
            rule_trade_stage="watch",
            market_regime="stand_aside",
        )
        self.assertEqual(result.ai_trade_stage, "watch")
        self.assertIn("冲突", result.ai_reasoning)

    def test_defensive_overrides_ai_add(self) -> None:
        """defensive 下 AI 返回加仓 → 降级到 probe_entry 以下"""
        result = self.protocol.parse_ai_response(
            ai_summary="强势",
            ai_operation_advice="加仓",
            rule_trade_stage="probe_entry",
            market_regime="defensive",
        )
        # In defensive, add_on is not allowed; should cap at probe_entry or lower
        self.assertIn(result.ai_trade_stage, ("probe_entry", "focus", "watch"))

    # ── AI 无输出 ──────────────────────────────────────────────────

    def test_no_ai_output_returns_none_stage(self) -> None:
        result = self.protocol.parse_ai_response(
            ai_summary=None,
            ai_operation_advice=None,
            rule_trade_stage="focus",
            market_regime="balanced",
        )
        self.assertIsNone(result.ai_trade_stage)
        self.assertAlmostEqual(result.ai_confidence, 0.0)

    def test_empty_advice_returns_none_stage(self) -> None:
        result = self.protocol.parse_ai_response(
            ai_summary="",
            ai_operation_advice="",
            rule_trade_stage="focus",
            market_regime="balanced",
        )
        self.assertIsNone(result.ai_trade_stage)

    # ── ai_confidence ──────────────────────────────────────────────

    def test_confidence_higher_when_consistent(self) -> None:
        """AI agrees with rule layer → higher confidence."""
        result = self.protocol.parse_ai_response(
            ai_summary="趋势突破确认",
            ai_operation_advice="买入",
            rule_trade_stage="probe_entry",
            market_regime="balanced",
        )
        self.assertGreaterEqual(result.ai_confidence, 0.5)

    def test_confidence_lower_when_conflicting(self) -> None:
        """AI disagrees with rule layer → lower confidence."""
        result = self.protocol.parse_ai_response(
            ai_summary="趋势看好",
            ai_operation_advice="买入",
            rule_trade_stage="watch",
            market_regime="stand_aside",
        )
        self.assertLessEqual(result.ai_confidence, 0.5)

    # ── raw_advice 透传 ────────────────────────────────────────────

    def test_raw_advice_passthrough(self) -> None:
        result = self.protocol.parse_ai_response(
            ai_summary="趋势未破坏",
            ai_operation_advice="关注",
            rule_trade_stage="focus",
            market_regime="balanced",
        )
        self.assertEqual(result.raw_advice, "关注")

    def test_raw_advice_empty_when_none(self) -> None:
        result = self.protocol.parse_ai_response(
            ai_summary=None,
            ai_operation_advice=None,
            rule_trade_stage="focus",
            market_regime="balanced",
        )
        self.assertEqual(result.raw_advice, "")


class TestBuildReviewPrompt(unittest.TestCase):
    """Tests for AiReviewProtocol.build_review_prompt()."""

    def setUp(self) -> None:
        self.protocol = AiReviewProtocol()

    def test_prompt_contains_regime(self) -> None:
        prompt = self.protocol.build_review_prompt(
            code="600519",
            name="贵州茅台",
            rule_trade_stage="probe_entry",
            setup_type="trend_breakout",
            market_regime="balanced",
            theme_position="main_theme",
            entry_maturity="high",
            trade_plan={"stop_loss_rule": "跌破MA20"},
            factor_snapshot={},
        )
        self.assertIn("balanced", prompt)

    def test_prompt_contains_setup_type(self) -> None:
        prompt = self.protocol.build_review_prompt(
            code="600519",
            name="贵州茅台",
            rule_trade_stage="probe_entry",
            setup_type="trend_breakout",
            market_regime="balanced",
            theme_position="main_theme",
            entry_maturity="high",
            trade_plan=None,
            factor_snapshot={},
        )
        self.assertIn("trend_breakout", prompt)

    def test_prompt_contains_rule_trade_stage(self) -> None:
        prompt = self.protocol.build_review_prompt(
            code="600519",
            name="贵州茅台",
            rule_trade_stage="focus",
            setup_type="none",
            market_regime="defensive",
            theme_position="non_theme",
            entry_maturity="low",
            trade_plan=None,
            factor_snapshot={},
        )
        self.assertIn("focus", prompt)

    def test_prompt_contains_entry_maturity(self) -> None:
        prompt = self.protocol.build_review_prompt(
            code="600519",
            name="贵州茅台",
            rule_trade_stage="probe_entry",
            setup_type="trend_breakout",
            market_regime="balanced",
            theme_position="main_theme",
            entry_maturity="high",
            trade_plan=None,
            factor_snapshot={},
        )
        self.assertIn("high", prompt)


if __name__ == "__main__":
    unittest.main()
