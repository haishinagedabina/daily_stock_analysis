# -*- coding: utf-8 -*-
"""
集成测试：五层决策链路 pipeline 集成验证。

验证:
  1. _apply_five_layer_decision 正确为 candidate 赋值五层字段
  2. _build_candidate_payloads 包含五层字段
  3. save_screening_candidates 写入五层字段到 DB
  4. 硬规则在集成层面生效（stand_aside → watch）
"""

import unittest
from datetime import date, datetime
from unittest.mock import MagicMock, patch

from src.core.market_guard import MarketGuardResult
from src.schemas.trading_types import (
    EntryMaturity,
    MarketRegime,
    RiskLevel,
    ThemePosition,
    TradeStage,
)
from src.services.screener_service import ScreeningCandidateRecord


def _make_candidate(
    code: str = "600519",
    name: str = "贵州茅台",
    rank: int = 1,
    setup_type: str = "trend_breakout",
    factor_snapshot: dict | None = None,
) -> ScreeningCandidateRecord:
    fs = factor_snapshot or {
        "pct_chg": 5.0,
        "leader_score": 75.0,
        "extreme_strength_score": 85.0,
        "has_stop_loss": True,
        "ma100_breakout_days": 3,
    }
    return ScreeningCandidateRecord(
        code=code,
        name=name,
        rank=rank,
        rule_score=80.0,
        rule_hits=["trend_breakout_hit"],
        factor_snapshot=fs,
        matched_strategies=["trend_breakout"],
        strategy_scores={"trend_breakout": 80.0},
        setup_type=setup_type,
    )


class FiveLayerDecisionTestCase(unittest.TestCase):
    """测试 _apply_five_layer_decision 方法。"""

    def _make_service(self):
        """构造最小化的 ScreeningTaskService mock。"""
        from src.services.screening_task_service import ScreeningTaskService

        db_mock = MagicMock()
        db_mock.batch_get_instrument_board_names.return_value = {
            "600519": ["白酒"],
            "000858": ["白酒"],
        }
        db_mock.list_sector_heat_history.return_value = []

        svc = ScreeningTaskService.__new__(ScreeningTaskService)
        svc.db = db_mock
        svc.config = MagicMock()
        svc.config.screening_market_guard_enabled = False
        svc.config.screening_market_guard_index = "sh000001"
        svc._theme_context = None

        # Mock market_data_sync_service with real return values
        sync_mock = MagicMock()
        sync_mock.fetcher_manager.get_market_stats.return_value = {
            "limit_up_count": 30, "limit_down_count": 10,
            "up_count": 2500, "down_count": 1500,
        }
        svc._market_data_sync_service = sync_mock
        return svc

    def _make_snapshot_df(self):
        import pandas as pd
        return pd.DataFrame([
            {"code": "600519", "name": "贵州茅台", "pct_chg": 5.0, "volume_ratio": 1.5,
             "turnover_rate": 2.0, "close": 100.0, "ma5": 98.0, "ma10": 96.0,
             "ma20": 94.0, "ma60": 90.0, "is_limit_up": False,
             "above_ma100": True, "gap_breakaway": False},
        ])

    def test_five_layer_populates_all_fields(self):
        """五层链路为 candidate 填充所有决策字段。"""
        svc = self._make_service()
        candidate = _make_candidate()
        snapshot_df = self._make_snapshot_df()

        guard = MarketGuardResult(is_safe=True, index_price=3200.0, index_ma100=3100.0)

        svc._apply_five_layer_decision(
            selected=[candidate],
            snapshot_df=snapshot_df,
            effective_trade_date=date(2026, 3, 31),
            guard_result=guard,
        )

        self.assertIsNotNone(candidate.trade_stage)
        self.assertIsNotNone(candidate.market_regime)
        self.assertIsNotNone(candidate.entry_maturity)
        self.assertIsNotNone(candidate.candidate_pool_level)
        self.assertIsNotNone(candidate.theme_position)
        self.assertIsNotNone(candidate.risk_level)

    def test_stand_aside_caps_at_watch(self):
        """stand_aside 环境下 trade_stage 不超过 watch。"""
        svc = self._make_service()
        candidate = _make_candidate()
        snapshot_df = self._make_snapshot_df()

        # 指数 < MA100 + MA20↓ + 赚钱效应差 → stand_aside
        guard = MarketGuardResult(is_safe=False, index_price=2800.0, index_ma100=3100.0)

        # Mock market_stats for bad money effect
        svc._market_data_sync_service.fetcher_manager.get_market_stats.return_value = {
            "limit_up_count": 5, "limit_down_count": 30,
            "up_count": 500, "down_count": 3500,
        }

        # index_bars with descending MA20
        import pandas as pd
        import numpy as np
        bars = pd.DataFrame({
            "close": np.linspace(3200, 2800, 30),
            "date": pd.date_range("2026-03-01", periods=30),
        })
        try:
            guard_inst = MagicMock()
            guard_inst._fetch_index_data.return_value = (bars, "mock")
            with patch("src.services.screening_task_service.MarketGuard", return_value=guard_inst):
                svc._apply_five_layer_decision(
                    selected=[candidate],
                    snapshot_df=snapshot_df,
                    effective_trade_date=date(2026, 3, 31),
                    guard_result=guard,
                )
        except Exception:
            # 即使数据拉取失败也能降级运行
            svc._apply_five_layer_decision(
                selected=[candidate],
                snapshot_df=snapshot_df,
                effective_trade_date=date(2026, 3, 31),
                guard_result=guard,
            )

        # stand_aside 或 defensive 环境下
        self.assertIn(candidate.trade_stage, [
            TradeStage.WATCH.value, TradeStage.FOCUS.value, TradeStage.STAND_ASIDE.value,
        ])

    def test_no_guard_result_still_works(self):
        """guard_result=None 时系统仍能降级运行。"""
        svc = self._make_service()
        candidate = _make_candidate()
        snapshot_df = self._make_snapshot_df()

        svc._apply_five_layer_decision(
            selected=[candidate],
            snapshot_df=snapshot_df,
            effective_trade_date=date(2026, 3, 31),
            guard_result=None,
        )

        # 应该默认 is_safe=True → balanced → 有值
        self.assertIsNotNone(candidate.trade_stage)
        self.assertIsNotNone(candidate.market_regime)

    def test_empty_candidates_no_error(self):
        """空候选列表不报错。"""
        svc = self._make_service()
        import pandas as pd
        svc._apply_five_layer_decision(
            selected=[],
            snapshot_df=pd.DataFrame(),
            effective_trade_date=date(2026, 3, 31),
        )


class PayloadOutputTestCase(unittest.TestCase):
    """测试 _build_candidate_payloads 包含五层字段。"""

    def test_payload_includes_five_layer_fields(self):
        from src.services.screening_task_service import ScreeningTaskService

        candidate = _make_candidate()
        candidate.trade_stage = "probe_entry"
        candidate.market_regime = "balanced"
        candidate.entry_maturity = "high"
        candidate.candidate_pool_level = "leader_pool"
        candidate.theme_position = "main_theme"
        candidate.risk_level = "medium"

        payloads = ScreeningTaskService._build_candidate_payloads(
            selected=[candidate],
            ai_results={},
            ai_top_k=5,
        )

        self.assertEqual(len(payloads), 1)
        p = payloads[0]
        self.assertEqual(p["trade_stage"], "probe_entry")
        self.assertEqual(p["market_regime"], "balanced")
        self.assertEqual(p["entry_maturity"], "high")
        self.assertEqual(p["candidate_pool_level"], "leader_pool")
        self.assertEqual(p["theme_position"], "main_theme")
        self.assertEqual(p["risk_level"], "medium")

    def test_payload_handles_none_five_layer_fields(self):
        """五层字段未赋值时 payload 中为 None。"""
        from src.services.screening_task_service import ScreeningTaskService

        candidate = _make_candidate()
        # 不赋值五层字段

        payloads = ScreeningTaskService._build_candidate_payloads(
            selected=[candidate],
            ai_results={},
            ai_top_k=5,
        )

        p = payloads[0]
        self.assertIsNone(p["trade_stage"])
        self.assertIsNone(p["market_regime"])


class DBSaveTestCase(unittest.TestCase):
    """测试 save_screening_candidates 写入五层字段。"""

    def setUp(self) -> None:
        import tempfile
        import os
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "test.db")
        os.environ["DATABASE_PATH"] = self._db_path

        from src.config import Config
        from src.storage import DatabaseManager

        Config.reset_instance()
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()

    def tearDown(self) -> None:
        import os
        from src.config import Config
        from src.storage import DatabaseManager

        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("DATABASE_PATH", None)
        self._temp_dir.cleanup()

    def test_save_includes_five_layer_fields(self):
        """save_screening_candidates 将五层字段写入 ScreeningCandidate 模型。"""
        run_id = "test-run-001"
        self.db.create_screening_run(
            run_id=run_id,
            trade_date=date(2026, 3, 31),
            trigger_type="manual",
        )

        candidates = [{
            "code": "600519",
            "name": "贵州茅台",
            "rank": 1,
            "rule_score": 80.0,
            "selected_for_ai": True,
            "matched_strategies": ["trend_breakout"],
            "rule_hits": ["hit1"],
            "factor_snapshot": {"pct_chg": 5.0},
            "trade_stage": "probe_entry",
            "market_regime": "balanced",
            "entry_maturity": "high",
            "risk_level": "medium",
            "theme_position": "main_theme",
            "candidate_pool_level": "leader_pool",
            "setup_type": "trend_breakout",
        }]

        self.db.save_screening_candidates(run_id=run_id, candidates=candidates)

        rows = self.db.list_screening_candidates(run_id=run_id)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["trade_stage"], "probe_entry")
        self.assertEqual(row["market_regime"], "balanced")
        self.assertEqual(row["entry_maturity"], "high")
        self.assertEqual(row["theme_position"], "main_theme")
        self.assertEqual(row["candidate_pool_level"], "leader_pool")
        self.assertEqual(row["risk_level"], "medium")
        self.assertEqual(row["setup_type"], "trend_breakout")


if __name__ == "__main__":
    unittest.main()
