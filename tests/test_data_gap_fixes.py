# -*- coding: utf-8 -*-
"""
TDD RED 阶段：修复两个数据缺口。

Gap 2: leader_score / extreme_strength_score 在非热点模式下缺失
  - FactorService 应无条件计算这两个分数
  - theme_context=None 时使用 theme_match_score=0.0

Gap 1: InstrumentBoardMembership 可能为空导致 SectorHeatEngine 失效
  - _resolve_board_names_for_codes 应始终查询 DB
  - SectorHeatEngine 在无板块数据时应记录明确警告
"""

import unittest
from datetime import date
from unittest.mock import MagicMock

import pandas as pd

from src.services.extreme_strength_scorer import ExtremeStrengthScorer
from src.services.leader_score_calculator import LeaderScoreCalculator


# ── Gap 2: leader_score 无条件可计算 ──────────────────────────────────────────

class BaseScoreComputationTestCase(unittest.TestCase):
    """验证 leader_score / extreme_strength_score 可在无题材上下文时计算。"""

    def test_leader_score_without_theme_match(self):
        """theme_match_score=0 时，强势股仍有 leader_score > 0。"""
        calc = LeaderScoreCalculator()
        score = calc.calculate_leader_score(
            theme_match_score=0.0,
            circ_mv=30_000_000_000,
            turnover_rate=8.0,
            is_limit_up=True,
            gap_breakaway=True,
            above_ma100=True,
            ma100_breakout_days=3,
        )
        # circ_mv<50B=20, turnover>5%=20, both_signals=15, above+recent=10 = 65
        self.assertEqual(score, 65.0)

    def test_extreme_strength_without_theme(self):
        """无题材时极强分数仍可有意义。"""
        scorer = ExtremeStrengthScorer()
        score = scorer.calculate_extreme_strength_score(
            above_ma100=True,
            gap_breakaway=True,
            pattern_123_low_trendline=False,
            is_limit_up=True,
            bottom_divergence_double_breakout=False,
            theme_heat_score=0.0,
            leader_score=65.0,
            volume_ratio=1.5,
            turnover_rate=5.0,
            circ_mv=30_000_000_000,
            breakout_ratio=1.05,
        )
        # base=20, signal=25, aux>0 → 总分 > 45
        self.assertGreater(score, 45.0)

    def test_factor_service_enrich_base_scores(self):
        """FactorService._enrich_base_scores 为所有 snapshot 无条件计算基础分数。"""
        from src.services.factor_service import FactorService

        svc = FactorService.__new__(FactorService)

        snapshots = [{
            "code": "600519",
            "circ_mv": 30_000_000_000,
            "turnover_rate": 8.0,
            "is_limit_up": True,
            "gap_breakaway": True,
            "above_ma100": True,
            "ma100_breakout_days": 3,
            "pattern_123_low_trendline": False,
            "bottom_divergence_double_breakout": False,
            "volume_ratio": 1.5,
            "breakout_ratio": 1.05,
        }]

        svc._enrich_base_scores(snapshots)

        self.assertIn("leader_score", snapshots[0])
        self.assertIn("extreme_strength_score", snapshots[0])
        self.assertGreater(snapshots[0]["leader_score"], 0)
        self.assertGreater(snapshots[0]["extreme_strength_score"], 0)

    def test_base_scores_for_weak_stock(self):
        """弱势股基础分数低但不报错。"""
        from src.services.factor_service import FactorService

        svc = FactorService.__new__(FactorService)

        snapshots = [{
            "code": "000001",
            "circ_mv": 200_000_000_000,
            "turnover_rate": 1.5,  # 1.5% (normalized: 0.015 < 2% → 0)
            "is_limit_up": False,
            "gap_breakaway": False,
            "above_ma100": False,
            "ma100_breakout_days": 0,
            "pattern_123_low_trendline": False,
            "bottom_divergence_double_breakout": False,
            "volume_ratio": 0.8,
            "breakout_ratio": 0.95,
        }]

        svc._enrich_base_scores(snapshots)

        self.assertEqual(snapshots[0]["leader_score"], 0.0)
        self.assertGreaterEqual(snapshots[0]["extreme_strength_score"], 0.0)


# ── Gap 1: 板块数据可用性 ────────────────────────────────────────────────────

class BoardDataAvailabilityTestCase(unittest.TestCase):
    """验证板块数据解析不依赖 theme_context。"""

    def test_resolve_boards_without_theme_context(self):
        """_resolve_board_names_for_codes 在 theme_context=None 时仍查询 DB。"""
        from src.services.factor_service import FactorService

        svc = FactorService.__new__(FactorService)
        svc.theme_context = None
        svc.db = MagicMock()
        svc.db.batch_get_instrument_board_names.return_value = {
            "600519": ["白酒", "食品饮料"],
        }

        result = svc._resolve_board_names_for_codes(["600519"])

        self.assertEqual(len(result), 1)
        self.assertIn("600519", result)
        self.assertEqual(result["600519"], ["白酒", "食品饮料"])
        svc.db.batch_get_instrument_board_names.assert_called_once()

    def test_resolve_boards_empty_codes(self):
        """空代码列表返回空 dict。"""
        from src.services.factor_service import FactorService

        svc = FactorService.__new__(FactorService)
        svc.theme_context = None
        svc.db = MagicMock()

        result = svc._resolve_board_names_for_codes([])

        self.assertEqual(result, {})

    def test_sector_heat_engine_warns_on_empty_boards(self):
        """SectorHeatEngine 在无板块数据时记录警告。"""
        from src.services.sector_heat_engine import SectorHeatEngine

        db_mock = MagicMock()
        db_mock.list_active_boards_with_member_count.return_value = []

        engine = SectorHeatEngine(db_manager=db_mock)
        snapshot_df = pd.DataFrame([{
            "code": "600519", "pct_chg": 5.0,
        }])

        with self.assertLogs("src.services.sector_heat_engine", level="WARNING") as log:
            results = engine.compute_all_sectors(snapshot_df, date(2026, 3, 31))

        self.assertEqual(results, [])
        self.assertTrue(
            any("board" in msg.lower() or "板块" in msg for msg in log.output),
            f"Expected board-related warning, got: {log.output}",
        )


if __name__ == "__main__":
    unittest.main()
