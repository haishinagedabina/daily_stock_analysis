import unittest

from src.schemas.trading_types import (
    AiReviewDecision,
    CandidateDecision,
    CandidatePoolLevel,
    EntryMaturity,
    MarketRegime,
    RiskLevel,
    SetupType,
    ThemePosition,
    TradePlan,
    TradeStage,
)
from src.services.ai_review_protocol import AiReviewProtocol
from src.services.setup_freshness_assessor import SetupFreshnessAssessor
from src.services.trade_plan_builder import TradePlanBuilder


class CandidateDecisionGoldenCase(unittest.TestCase):
    def test_probe_entry_payload_round_trip_golden_case(self) -> None:
        decision = CandidateDecision(
            code="600519",
            name="贵州茅台",
            rank=1,
            selected_for_ai=True,
            rule_score=92.5,
            rule_hits=["trend_aligned", "volume_expanding"],
            factor_snapshot={"close": 1520.0, "ma20": 1488.0, "ma100": 1380.0},
            matched_strategies=["ma100_60min_combined", "volume_breakout"],
            market_regime=MarketRegime.BALANCED,
            risk_level=RiskLevel.MEDIUM,
            theme_tag="白酒",
            theme_score=88.0,
            theme_position=ThemePosition.MAIN_THEME,
            theme_duration="expanding",
            trade_theme_stage="expanding",
            candidate_pool_level=CandidatePoolLevel.LEADER_POOL,
            setup_type=SetupType.TREND_BREAKOUT,
            entry_maturity=EntryMaturity.HIGH,
            setup_freshness=0.9,
            trade_stage=TradeStage.PROBE_ENTRY,
            trade_plan=TradePlan(
                initial_position="1/5仓",
                stop_loss_rule="跌破MA20止损",
                take_profit_plan="沿MA10移动止盈",
                invalidation_rule="3日未启动离场",
                risk_level=RiskLevel.MEDIUM,
                holding_expectation="1~2周波段",
                execution_note="围绕趋势延续与关键均线支撑执行，现价1520.00，MA20=1488.00，MA100=1380.00",
            ),
            ai_review=AiReviewDecision(
                ai_query_id="golden-query-1",
                ai_summary="趋势完整，等待回踩后试错。",
                ai_operation_advice="关注",
                ai_trade_stage=TradeStage.FOCUS,
                ai_reasoning="市场中性偏强，题材一致。",
                ai_confidence=0.78,
                ai_environment_ok=True,
                ai_theme_alignment=True,
                ai_entry_quality="high",
                stage_conflict=False,
            ),
        )

        payload = decision.to_payload()
        restored = CandidateDecision.from_payload(payload)

        self.assertEqual(payload["trade_stage"], "probe_entry")
        self.assertEqual(payload["setup_type"], "trend_breakout")
        self.assertEqual(payload["theme_tag"], "白酒")
        self.assertEqual(payload["setup_freshness"], 0.9)
        self.assertEqual(payload["trade_plan"]["execution_note"], decision.trade_plan.execution_note)
        self.assertEqual(payload["ai_review"]["ai_trade_stage"], "focus")
        self.assertEqual(restored.trade_stage, TradeStage.PROBE_ENTRY)
        self.assertEqual(restored.trade_plan.execution_note, decision.trade_plan.execution_note)
        self.assertEqual(restored.ai_review.ai_trade_stage, TradeStage.FOCUS)

    def test_ai_review_conflict_is_capped_by_market_regime_golden_case(self) -> None:
        protocol = AiReviewProtocol()

        result = protocol.parse_ai_response(
            ai_summary='{"suggested_stage":"add_on_strength","confidence":0.91,"reasoning":"强势延续","risk_flags":[],"summary":"可加仓","environment_ok":true,"theme_alignment":true,"entry_quality":"high"}',
            ai_operation_advice="加仓",
            rule_trade_stage="focus",
            market_regime="defensive",
        )

        self.assertEqual(result.ai_trade_stage, "probe_entry")
        self.assertTrue(result.stage_conflict)
        self.assertEqual(result.ai_entry_quality, "high")

    def test_setup_freshness_and_execution_note_golden_case(self) -> None:
        freshness = SetupFreshnessAssessor().assess(
            SetupType.TREND_BREAKOUT,
            {"ma100_breakout_days": 2, "close": 25.5, "ma20": 24.8, "ma100": 22.0},
        )
        plan = TradePlanBuilder().build(
            trade_stage=TradeStage.PROBE_ENTRY,
            setup_type=SetupType.TREND_BREAKOUT,
            entry_maturity=EntryMaturity.HIGH,
            risk_level=RiskLevel.MEDIUM,
            pool_level=CandidatePoolLevel.LEADER_POOL,
            factor_snapshot={"close": 25.5, "ma20": 24.8, "ma100": 22.0},
        )

        self.assertEqual(freshness, 0.9)
        self.assertIsNotNone(plan)
        self.assertIn("MA20=24.80", plan.execution_note)
        self.assertIn("MA100=22.00", plan.execution_note)

