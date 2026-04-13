# -*- coding: utf-8 -*-
"""TradePlanBuilder 单元测试 — Phase 3A TDD red→green。"""

from __future__ import annotations

import json
import unittest

from src.schemas.trading_types import (
    CandidatePoolLevel,
    EntryMaturity,
    RiskLevel,
    SetupType,
    TradePlan,
    TradeStage,
)
from src.services.trade_plan_builder import TradePlanBuilder


class TestTradePlanBuilder(unittest.TestCase):

    def setUp(self) -> None:
        self.builder = TradePlanBuilder()
        self.base_fs: dict = {}

    # ── 非可执行阶段 → None ─────────────────────────────────────────

    def test_watch_returns_none(self) -> None:
        result = self.builder.build(
            trade_stage=TradeStage.WATCH,
            setup_type=SetupType.TREND_BREAKOUT,
            entry_maturity=EntryMaturity.MEDIUM,
            risk_level=RiskLevel.MEDIUM,
            pool_level=CandidatePoolLevel.FOCUS_LIST,
            factor_snapshot=self.base_fs,
        )
        self.assertIsNone(result)

    def test_focus_returns_none(self) -> None:
        result = self.builder.build(
            trade_stage=TradeStage.FOCUS,
            setup_type=SetupType.TREND_BREAKOUT,
            entry_maturity=EntryMaturity.MEDIUM,
            risk_level=RiskLevel.MEDIUM,
            pool_level=CandidatePoolLevel.FOCUS_LIST,
            factor_snapshot=self.base_fs,
        )
        self.assertIsNone(result)

    def test_stand_aside_returns_none(self) -> None:
        result = self.builder.build(
            trade_stage=TradeStage.STAND_ASIDE,
            setup_type=SetupType.NONE,
            entry_maturity=EntryMaturity.LOW,
            risk_level=RiskLevel.HIGH,
            pool_level=CandidatePoolLevel.WATCHLIST,
            factor_snapshot=self.base_fs,
        )
        self.assertIsNone(result)

    def test_reject_returns_none(self) -> None:
        result = self.builder.build(
            trade_stage=TradeStage.REJECT,
            setup_type=SetupType.NONE,
            entry_maturity=EntryMaturity.LOW,
            risk_level=RiskLevel.HIGH,
            pool_level=CandidatePoolLevel.WATCHLIST,
            factor_snapshot=self.base_fs,
        )
        self.assertIsNone(result)

    # ── probe_entry 基本测试 ────────────────────────────────────────

    def test_probe_entry_bottom_divergence_has_stop_loss(self) -> None:
        result = self.builder.build(
            trade_stage=TradeStage.PROBE_ENTRY,
            setup_type=SetupType.BOTTOM_DIVERGENCE_BREAKOUT,
            entry_maturity=EntryMaturity.MEDIUM,
            risk_level=RiskLevel.MEDIUM,
            pool_level=CandidatePoolLevel.FOCUS_LIST,
            factor_snapshot=self.base_fs,
        )
        self.assertIsNotNone(result)
        self.assertIsInstance(result, TradePlan)
        self.assertIsNotNone(result.stop_loss_rule)
        self.assertTrue(len(result.stop_loss_rule) > 0)

    def test_probe_entry_has_no_add_rule(self) -> None:
        result = self.builder.build(
            trade_stage=TradeStage.PROBE_ENTRY,
            setup_type=SetupType.TREND_BREAKOUT,
            entry_maturity=EntryMaturity.MEDIUM,
            risk_level=RiskLevel.MEDIUM,
            pool_level=CandidatePoolLevel.FOCUS_LIST,
            factor_snapshot=self.base_fs,
        )
        self.assertIsNotNone(result)
        self.assertIsNone(result.add_rule)

    def test_probe_entry_trend_breakout_holding_expectation(self) -> None:
        result = self.builder.build(
            trade_stage=TradeStage.PROBE_ENTRY,
            setup_type=SetupType.TREND_BREAKOUT,
            entry_maturity=EntryMaturity.MEDIUM,
            risk_level=RiskLevel.MEDIUM,
            pool_level=CandidatePoolLevel.FOCUS_LIST,
            factor_snapshot=self.base_fs,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.holding_expectation, "1~2周波段")

    def test_probe_entry_limitup_holding_expectation(self) -> None:
        result = self.builder.build(
            trade_stage=TradeStage.PROBE_ENTRY,
            setup_type=SetupType.LIMITUP_STRUCTURE,
            entry_maturity=EntryMaturity.HIGH,
            risk_level=RiskLevel.MEDIUM,
            pool_level=CandidatePoolLevel.FOCUS_LIST,
            factor_snapshot=self.base_fs,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.holding_expectation, "3~5日短线")

    def test_probe_entry_has_invalidation_rule(self) -> None:
        result = self.builder.build(
            trade_stage=TradeStage.PROBE_ENTRY,
            setup_type=SetupType.LOW123_BREAKOUT,
            entry_maturity=EntryMaturity.MEDIUM,
            risk_level=RiskLevel.MEDIUM,
            pool_level=CandidatePoolLevel.FOCUS_LIST,
            factor_snapshot=self.base_fs,
        )
        self.assertIsNotNone(result)
        self.assertIn("3个交易日", result.invalidation_rule)

    def test_probe_entry_has_take_profit_plan(self) -> None:
        result = self.builder.build(
            trade_stage=TradeStage.PROBE_ENTRY,
            setup_type=SetupType.GAP_BREAKOUT,
            entry_maturity=EntryMaturity.MEDIUM,
            risk_level=RiskLevel.MEDIUM,
            pool_level=CandidatePoolLevel.FOCUS_LIST,
            factor_snapshot=self.base_fs,
        )
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.take_profit_plan)
        self.assertTrue(len(result.take_profit_plan) > 0)

    # ── risk_level → initial_position 映射 ─────────────────────────

    def test_risk_high_small_position(self) -> None:
        result = self.builder.build(
            trade_stage=TradeStage.PROBE_ENTRY,
            setup_type=SetupType.TREND_BREAKOUT,
            entry_maturity=EntryMaturity.MEDIUM,
            risk_level=RiskLevel.HIGH,
            pool_level=CandidatePoolLevel.FOCUS_LIST,
            factor_snapshot=self.base_fs,
        )
        self.assertEqual(result.initial_position, "1/10仓")

    def test_risk_medium_moderate_position(self) -> None:
        result = self.builder.build(
            trade_stage=TradeStage.PROBE_ENTRY,
            setup_type=SetupType.TREND_BREAKOUT,
            entry_maturity=EntryMaturity.MEDIUM,
            risk_level=RiskLevel.MEDIUM,
            pool_level=CandidatePoolLevel.FOCUS_LIST,
            factor_snapshot=self.base_fs,
        )
        self.assertEqual(result.initial_position, "1/5仓")

    def test_risk_low_larger_position(self) -> None:
        result = self.builder.build(
            trade_stage=TradeStage.PROBE_ENTRY,
            setup_type=SetupType.TREND_BREAKOUT,
            entry_maturity=EntryMaturity.MEDIUM,
            risk_level=RiskLevel.LOW,
            pool_level=CandidatePoolLevel.FOCUS_LIST,
            factor_snapshot=self.base_fs,
        )
        self.assertEqual(result.initial_position, "1/3仓")

    # ── add_on_strength 测试 ────────────────────────────────────────

    def test_add_on_strength_has_add_rule(self) -> None:
        result = self.builder.build(
            trade_stage=TradeStage.ADD_ON_STRENGTH,
            setup_type=SetupType.LOW123_BREAKOUT,
            entry_maturity=EntryMaturity.HIGH,
            risk_level=RiskLevel.LOW,
            pool_level=CandidatePoolLevel.LEADER_POOL,
            factor_snapshot=self.base_fs,
        )
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.add_rule)
        self.assertIn("加仓", result.add_rule)

    def test_add_on_strength_has_stop_loss(self) -> None:
        result = self.builder.build(
            trade_stage=TradeStage.ADD_ON_STRENGTH,
            setup_type=SetupType.TREND_BREAKOUT,
            entry_maturity=EntryMaturity.HIGH,
            risk_level=RiskLevel.MEDIUM,
            pool_level=CandidatePoolLevel.LEADER_POOL,
            factor_snapshot=self.base_fs,
        )
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.stop_loss_rule)

    def test_add_on_strength_risk_low_larger_position(self) -> None:
        result = self.builder.build(
            trade_stage=TradeStage.ADD_ON_STRENGTH,
            setup_type=SetupType.TREND_BREAKOUT,
            entry_maturity=EntryMaturity.HIGH,
            risk_level=RiskLevel.LOW,
            pool_level=CandidatePoolLevel.LEADER_POOL,
            factor_snapshot=self.base_fs,
        )
        self.assertEqual(result.initial_position, "1/2仓")

    def test_add_on_strength_risk_high_small_position(self) -> None:
        result = self.builder.build(
            trade_stage=TradeStage.ADD_ON_STRENGTH,
            setup_type=SetupType.TREND_BREAKOUT,
            entry_maturity=EntryMaturity.HIGH,
            risk_level=RiskLevel.HIGH,
            pool_level=CandidatePoolLevel.LEADER_POOL,
            factor_snapshot=self.base_fs,
        )
        self.assertEqual(result.initial_position, "1/5仓")

    # ── 每种 setup_type 的止损模板覆盖 ─────────────────────────────

    def test_each_setup_type_has_stop_loss_template(self) -> None:
        actionable_setups = [
            SetupType.BOTTOM_DIVERGENCE_BREAKOUT,
            SetupType.LOW123_BREAKOUT,
            SetupType.TREND_BREAKOUT,
            SetupType.TREND_PULLBACK,
            SetupType.GAP_BREAKOUT,
            SetupType.LIMITUP_STRUCTURE,
        ]
        for st in actionable_setups:
            with self.subTest(setup_type=st):
                result = self.builder.build(
                    trade_stage=TradeStage.PROBE_ENTRY,
                    setup_type=st,
                    entry_maturity=EntryMaturity.MEDIUM,
                    risk_level=RiskLevel.MEDIUM,
                    pool_level=CandidatePoolLevel.FOCUS_LIST,
                    factor_snapshot=self.base_fs,
                )
                self.assertIsNotNone(result)
                self.assertIsNotNone(result.stop_loss_rule, f"{st} missing stop_loss_rule")
                self.assertTrue(len(result.stop_loss_rule) > 0)

    # ── setup_type=NONE 边界 ────────────────────────────────────────

    def test_setup_none_with_probe_entry_uses_default(self) -> None:
        """If somehow trade_stage is probe_entry but setup_type is NONE, still generates a plan."""
        result = self.builder.build(
            trade_stage=TradeStage.PROBE_ENTRY,
            setup_type=SetupType.NONE,
            entry_maturity=EntryMaturity.MEDIUM,
            risk_level=RiskLevel.MEDIUM,
            pool_level=CandidatePoolLevel.FOCUS_LIST,
            factor_snapshot=self.base_fs,
        )
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.stop_loss_rule)

    # ── risk_level 写入 TradePlan ───────────────────────────────────

    def test_risk_level_propagated(self) -> None:
        result = self.builder.build(
            trade_stage=TradeStage.PROBE_ENTRY,
            setup_type=SetupType.TREND_BREAKOUT,
            entry_maturity=EntryMaturity.MEDIUM,
            risk_level=RiskLevel.HIGH,
            pool_level=CandidatePoolLevel.FOCUS_LIST,
            factor_snapshot=self.base_fs,
        )
        self.assertEqual(result.risk_level, RiskLevel.HIGH)

    def test_execution_note_handles_non_numeric_anchor_values(self) -> None:
        result = self.builder.build(
            trade_stage=TradeStage.PROBE_ENTRY,
            setup_type=SetupType.TREND_BREAKOUT,
            entry_maturity=EntryMaturity.MEDIUM,
            risk_level=RiskLevel.MEDIUM,
            pool_level=CandidatePoolLevel.FOCUS_LIST,
            factor_snapshot={"close": "not-a-number", "ma20": object(), "ma100": None},
        )

        self.assertIsNotNone(result)
        self.assertIn("执行锚点", result.execution_note)

    def test_execution_note_keeps_existing_close_anchor_copy(self) -> None:
        result = self.builder.build(
            trade_stage=TradeStage.PROBE_ENTRY,
            setup_type=SetupType.TREND_BREAKOUT,
            entry_maturity=EntryMaturity.MEDIUM,
            risk_level=RiskLevel.MEDIUM,
            pool_level=CandidatePoolLevel.FOCUS_LIST,
            factor_snapshot={"close": 25.5, "ma20": 24.8, "ma100": 22.0},
        )

        self.assertIsNotNone(result)
        self.assertIn("现价25.50", result.execution_note)


if __name__ == "__main__":
    unittest.main()
