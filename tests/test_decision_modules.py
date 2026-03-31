# -*- coding: utf-8 -*-
"""
TDD：EntryMaturityAssessor + CandidatePoolClassifier + TradeStageJudge 测试。
"""

import unittest

from src.schemas.trading_types import (
    CandidatePoolLevel,
    EntryMaturity,
    MarketEnvironment,
    MarketRegime,
    RiskLevel,
    SetupType,
    ThemePosition,
    TradeStage,
)
from src.services.entry_maturity_assessor import EntryMaturityAssessor
from src.services.candidate_pool_classifier import CandidatePoolClassifier
from src.services.trade_stage_judge import TradeStageJudge


# ═══════════════════════════════════════════════════════════════════════════════
# EntryMaturityAssessor
# ═══════════════════════════════════════════════════════════════════════════════


class EntryMaturityAssessorTestCase(unittest.TestCase):

    def setUp(self) -> None:
        self.assessor = EntryMaturityAssessor()

    def test_bottom_divergence_confirmed_high(self) -> None:
        """底背离 confirmed → HIGH。"""
        fs = {"bottom_divergence_state": "confirmed", "bottom_divergence_signal_strength": 80}
        result = self.assessor.assess(SetupType.BOTTOM_DIVERGENCE_BREAKOUT, fs)
        self.assertEqual(result, EntryMaturity.HIGH)

    def test_bottom_divergence_structure_ready_medium(self) -> None:
        """底背离 structure_ready → MEDIUM。"""
        fs = {"bottom_divergence_state": "structure_ready"}
        result = self.assessor.assess(SetupType.BOTTOM_DIVERGENCE_BREAKOUT, fs)
        self.assertEqual(result, EntryMaturity.MEDIUM)

    def test_bottom_divergence_pending_low(self) -> None:
        """底背离 divergence_only/pending → LOW。"""
        fs = {"bottom_divergence_state": "divergence_only"}
        result = self.assessor.assess(SetupType.BOTTOM_DIVERGENCE_BREAKOUT, fs)
        self.assertEqual(result, EntryMaturity.LOW)

    def test_low123_confirmed_fresh_high(self) -> None:
        """Low123 confirmed + 新鲜 → HIGH。"""
        fs = {"pattern_123_state": "confirmed", "pattern_123_signal_strength": 0.8}
        result = self.assessor.assess(SetupType.LOW123_BREAKOUT, fs)
        self.assertEqual(result, EntryMaturity.HIGH)

    def test_trend_breakout_fresh_high(self) -> None:
        """趋势突破 ≤5 天 → HIGH。"""
        fs = {"ma100_breakout_days": 3}
        result = self.assessor.assess(SetupType.TREND_BREAKOUT, fs)
        self.assertEqual(result, EntryMaturity.HIGH)

    def test_trend_breakout_stale_medium(self) -> None:
        """趋势突破 6-10 天 → MEDIUM。"""
        fs = {"ma100_breakout_days": 8}
        result = self.assessor.assess(SetupType.TREND_BREAKOUT, fs)
        self.assertEqual(result, EntryMaturity.MEDIUM)

    def test_trend_breakout_old_low(self) -> None:
        """趋势突破 > 10 天 → LOW。"""
        fs = {"ma100_breakout_days": 15}
        result = self.assessor.assess(SetupType.TREND_BREAKOUT, fs)
        self.assertEqual(result, EntryMaturity.LOW)

    def test_gap_breakout_with_limitup_high(self) -> None:
        """缺口 + 涨停 → HIGH。"""
        fs = {"gap_breakaway": True, "is_limit_up": True}
        result = self.assessor.assess(SetupType.GAP_BREAKOUT, fs)
        self.assertEqual(result, EntryMaturity.HIGH)

    def test_gap_breakout_without_limitup_medium(self) -> None:
        """缺口无涨停 → MEDIUM。"""
        fs = {"gap_breakaway": True, "is_limit_up": False}
        result = self.assessor.assess(SetupType.GAP_BREAKOUT, fs)
        self.assertEqual(result, EntryMaturity.MEDIUM)

    def test_none_setup_always_low(self) -> None:
        """setup_type=NONE → LOW。"""
        result = self.assessor.assess(SetupType.NONE, {})
        self.assertEqual(result, EntryMaturity.LOW)


# ═══════════════════════════════════════════════════════════════════════════════
# CandidatePoolClassifier
# ═══════════════════════════════════════════════════════════════════════════════


class CandidatePoolClassifierTestCase(unittest.TestCase):

    def setUp(self) -> None:
        self.classifier = CandidatePoolClassifier()

    def test_leader_pool_via_leader_score_and_theme(self) -> None:
        """leader_score≥70 + MAIN_THEME → LEADER_POOL。"""
        result = self.classifier.classify(
            leader_score=75.0,
            extreme_strength_score=50.0,
            theme_position=ThemePosition.MAIN_THEME,
            entry_maturity=EntryMaturity.MEDIUM,
            has_entry_core_hit=True,
        )
        self.assertEqual(result, CandidatePoolLevel.LEADER_POOL)

    def test_leader_pool_via_extreme_strength(self) -> None:
        """extreme_strength≥80 + entry_core → LEADER_POOL。"""
        result = self.classifier.classify(
            leader_score=30.0,
            extreme_strength_score=85.0,
            theme_position=ThemePosition.NON_THEME,
            entry_maturity=EntryMaturity.HIGH,
            has_entry_core_hit=True,
        )
        self.assertEqual(result, CandidatePoolLevel.LEADER_POOL)

    def test_focus_list_via_extreme_strength(self) -> None:
        """extreme_strength≥60 → FOCUS_LIST。"""
        result = self.classifier.classify(
            leader_score=30.0,
            extreme_strength_score=65.0,
            theme_position=ThemePosition.NON_THEME,
            entry_maturity=EntryMaturity.LOW,
            has_entry_core_hit=False,
        )
        self.assertEqual(result, CandidatePoolLevel.FOCUS_LIST)

    def test_focus_list_via_entry_core_and_maturity(self) -> None:
        """entry_core + maturity≥MEDIUM → FOCUS_LIST。"""
        result = self.classifier.classify(
            leader_score=20.0,
            extreme_strength_score=40.0,
            theme_position=ThemePosition.NON_THEME,
            entry_maturity=EntryMaturity.MEDIUM,
            has_entry_core_hit=True,
        )
        self.assertEqual(result, CandidatePoolLevel.FOCUS_LIST)

    def test_watchlist_default(self) -> None:
        """无特殊条件 → WATCHLIST。"""
        result = self.classifier.classify(
            leader_score=20.0,
            extreme_strength_score=30.0,
            theme_position=ThemePosition.NON_THEME,
            entry_maturity=EntryMaturity.LOW,
            has_entry_core_hit=False,
        )
        self.assertEqual(result, CandidatePoolLevel.WATCHLIST)


# ═══════════════════════════════════════════════════════════════════════════════
# TradeStageJudge
# ═══════════════════════════════════════════════════════════════════════════════


def _make_env(regime: MarketRegime = MarketRegime.BALANCED) -> MarketEnvironment:
    return MarketEnvironment(
        regime=regime,
        risk_level=RiskLevel.MEDIUM,
        is_safe=regime != MarketRegime.STAND_ASIDE,
    )


class TradeStageJudgeTestCase(unittest.TestCase):

    def setUp(self) -> None:
        self.judge = TradeStageJudge()

    # ── 环境硬门控 ───────────────────────────────────────────────────────────

    def test_stand_aside_caps_at_watch(self) -> None:
        """stand_aside 环境 → 最高 WATCH。"""
        result = self.judge.judge(
            env=_make_env(MarketRegime.STAND_ASIDE),
            setup_type=SetupType.TREND_BREAKOUT,
            entry_maturity=EntryMaturity.HIGH,
            pool_level=CandidatePoolLevel.LEADER_POOL,
            theme_position=ThemePosition.MAIN_THEME,
            has_stop_loss=True,
        )
        self.assertIn(result, [TradeStage.STAND_ASIDE, TradeStage.WATCH])

    def test_defensive_blocks_add_on(self) -> None:
        """defensive 环境 → 禁止 ADD_ON_STRENGTH。"""
        result = self.judge.judge(
            env=_make_env(MarketRegime.DEFENSIVE),
            setup_type=SetupType.TREND_BREAKOUT,
            entry_maturity=EntryMaturity.HIGH,
            pool_level=CandidatePoolLevel.LEADER_POOL,
            theme_position=ThemePosition.MAIN_THEME,
            has_stop_loss=True,
        )
        self.assertNotEqual(result, TradeStage.ADD_ON_STRENGTH)

    # ── 题材约束 ─────────────────────────────────────────────────────────────

    def test_fading_theme_caps_at_watch(self) -> None:
        """FADING_THEME → 最高 WATCH。"""
        result = self.judge.judge(
            env=_make_env(MarketRegime.AGGRESSIVE),
            setup_type=SetupType.TREND_BREAKOUT,
            entry_maturity=EntryMaturity.HIGH,
            pool_level=CandidatePoolLevel.LEADER_POOL,
            theme_position=ThemePosition.FADING_THEME,
            has_stop_loss=True,
        )
        self.assertIn(result, [TradeStage.WATCH, TradeStage.FOCUS])

    def test_non_theme_blocks_add_on(self) -> None:
        """NON_THEME → 禁止 ADD_ON_STRENGTH。"""
        result = self.judge.judge(
            env=_make_env(MarketRegime.AGGRESSIVE),
            setup_type=SetupType.TREND_BREAKOUT,
            entry_maturity=EntryMaturity.HIGH,
            pool_level=CandidatePoolLevel.LEADER_POOL,
            theme_position=ThemePosition.NON_THEME,
            has_stop_loss=True,
        )
        self.assertNotEqual(result, TradeStage.ADD_ON_STRENGTH)

    # ── 买点成熟度 ───────────────────────────────────────────────────────────

    def test_no_setup_caps_at_watch(self) -> None:
        """setup_type=NONE → 最高 WATCH。"""
        result = self.judge.judge(
            env=_make_env(MarketRegime.AGGRESSIVE),
            setup_type=SetupType.NONE,
            entry_maturity=EntryMaturity.LOW,
            pool_level=CandidatePoolLevel.WATCHLIST,
            theme_position=ThemePosition.MAIN_THEME,
            has_stop_loss=False,
        )
        self.assertIn(result, [TradeStage.STAND_ASIDE, TradeStage.WATCH])

    def test_low_maturity_caps_at_focus(self) -> None:
        """entry_maturity=LOW → 最高 FOCUS。"""
        result = self.judge.judge(
            env=_make_env(MarketRegime.AGGRESSIVE),
            setup_type=SetupType.TREND_BREAKOUT,
            entry_maturity=EntryMaturity.LOW,
            pool_level=CandidatePoolLevel.FOCUS_LIST,
            theme_position=ThemePosition.MAIN_THEME,
            has_stop_loss=True,
        )
        self.assertIn(result, [TradeStage.WATCH, TradeStage.FOCUS])

    def test_medium_maturity_with_stop_loss_probe_entry(self) -> None:
        """entry_maturity=MEDIUM + 有止损 → PROBE_ENTRY。"""
        result = self.judge.judge(
            env=_make_env(MarketRegime.BALANCED),
            setup_type=SetupType.TREND_BREAKOUT,
            entry_maturity=EntryMaturity.MEDIUM,
            pool_level=CandidatePoolLevel.FOCUS_LIST,
            theme_position=ThemePosition.MAIN_THEME,
            has_stop_loss=True,
        )
        self.assertEqual(result, TradeStage.PROBE_ENTRY)

    def test_no_stop_loss_caps_at_focus(self) -> None:
        """无止损锚点 → 最高 FOCUS。"""
        result = self.judge.judge(
            env=_make_env(MarketRegime.AGGRESSIVE),
            setup_type=SetupType.TREND_BREAKOUT,
            entry_maturity=EntryMaturity.HIGH,
            pool_level=CandidatePoolLevel.LEADER_POOL,
            theme_position=ThemePosition.MAIN_THEME,
            has_stop_loss=False,
        )
        self.assertEqual(result, TradeStage.FOCUS)

    def test_high_maturity_leader_pool_add_on(self) -> None:
        """HIGH + LEADER_POOL + aggressive + MAIN_THEME + stop_loss → ADD_ON_STRENGTH。"""
        result = self.judge.judge(
            env=_make_env(MarketRegime.AGGRESSIVE),
            setup_type=SetupType.TREND_BREAKOUT,
            entry_maturity=EntryMaturity.HIGH,
            pool_level=CandidatePoolLevel.LEADER_POOL,
            theme_position=ThemePosition.MAIN_THEME,
            has_stop_loss=True,
        )
        self.assertEqual(result, TradeStage.ADD_ON_STRENGTH)

    def test_high_maturity_balanced_probe_entry(self) -> None:
        """HIGH + balanced → 至少 PROBE_ENTRY。"""
        result = self.judge.judge(
            env=_make_env(MarketRegime.BALANCED),
            setup_type=SetupType.TREND_BREAKOUT,
            entry_maturity=EntryMaturity.HIGH,
            pool_level=CandidatePoolLevel.FOCUS_LIST,
            theme_position=ThemePosition.MAIN_THEME,
            has_stop_loss=True,
        )
        self.assertIn(result, [TradeStage.PROBE_ENTRY, TradeStage.ADD_ON_STRENGTH])


if __name__ == "__main__":
    unittest.main()
