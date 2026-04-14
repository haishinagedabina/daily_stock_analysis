# -*- coding: utf-8 -*-
"""TDD RED phase: Backtest pipeline integration tests.

Full flow: create_run → select_candidates → classify → get_forward_bars →
resolve_execution → evaluate → save_evaluations → update_run_status.
"""

import json
import os
import tempfile
import unittest
from datetime import date, timedelta

import pytest


@pytest.mark.unit
class TestFiveLayerBacktestPipeline(unittest.TestCase):
    """Integration tests for the complete backtest pipeline."""

    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "test_bt_pipeline.db")
        os.environ["DATABASE_PATH"] = self._db_path
        from src.config import Config
        Config._instance = None
        from src.storage import DatabaseManager
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()
        self._seed_screening_data()
        self._seed_stock_daily_data()

    def tearDown(self):
        from src.storage import DatabaseManager
        from src.config import Config
        DatabaseManager.reset_instance()
        Config._instance = None
        os.environ.pop("DATABASE_PATH", None)
        self._temp_dir.cleanup()

    def _seed_screening_data(self):
        from src.storage import ScreeningRun, ScreeningCandidate
        with self.db.get_session() as session:
            run = ScreeningRun(
                run_id="sr-pipe-001",
                trade_date=date(2024, 1, 15),
                market="cn",
                status="completed",
            )
            session.add(run)
            session.flush()

            candidates = [
                ScreeningCandidate(
                    run_id="sr-pipe-001",
                    code="600519",
                    name="贵州茅台",
                    rank=1,
                    rule_score=85.0,
                    trade_stage="probe_entry",
                    setup_type="trend_breakout",
                    entry_maturity="high",
                    market_regime="balanced",
                    theme_position="main_theme",
                    candidate_pool_level="leader_pool",
                    risk_level="medium",
                    trade_plan_json=json.dumps({"take_profit": 5.0, "stop_loss": -3.0}),
                ),
                ScreeningCandidate(
                    run_id="sr-pipe-001",
                    code="000858",
                    name="五粮液",
                    rank=2,
                    rule_score=72.0,
                    trade_stage="watch",
                    market_regime="balanced",
                    theme_position="related_theme",
                    candidate_pool_level="follower_pool",
                    risk_level="low",
                ),
                ScreeningCandidate(
                    run_id="sr-pipe-001",
                    code="601318",
                    name="中国平安",
                    rank=3,
                    rule_score=60.0,
                    trade_stage="stand_aside",
                    market_regime="balanced",
                    theme_position="non_theme",
                    candidate_pool_level="follower_pool",
                    risk_level="medium",
                ),
            ]
            session.add_all(candidates)
            session.commit()

    def _seed_stock_daily_data(self):
        from src.storage import StockDaily
        with self.db.get_session() as session:
            base_date = date(2024, 1, 15)
            for code, base_price in [("600519", 100.0), ("000858", 50.0), ("601318", 40.0)]:
                for i in range(1, 12):
                    d = base_date + timedelta(days=i)
                    price = base_price + i * 0.5
                    bar = StockDaily(
                        code=code,
                        date=d,
                        open=price - 0.5,
                        high=price + 2.0,
                        low=price - 2.0,
                        close=price,
                        pct_chg=0.5,
                        volume=1000000.0,
                        amount=100000000.0,
                    )
                    session.add(bar)
            session.commit()

    def test_pipeline_creates_run(self):
        """Pipeline should create a run with correct metadata."""
        from src.backtest.services.backtest_service import FiveLayerBacktestService
        svc = FiveLayerBacktestService(db_manager=self.db)
        run = svc.run_backtest_pipeline(
            screening_run_id="sr-pipe-001",
            evaluation_mode="historical_snapshot",
            execution_model="conservative",
        )
        self.assertIsNotNone(run)
        self.assertEqual(run.evaluation_mode, "historical_snapshot")
        self.assertEqual(run.execution_model, "conservative")

    def test_pipeline_run_status_completed(self):
        from src.backtest.services.backtest_service import FiveLayerBacktestService
        svc = FiveLayerBacktestService(db_manager=self.db)
        run = svc.run_backtest_pipeline(
            screening_run_id="sr-pipe-001",
            evaluation_mode="historical_snapshot",
            execution_model="conservative",
        )
        self.assertEqual(run.status, "completed")

    def test_pipeline_creates_evaluations(self):
        """Should create one evaluation per candidate."""
        from src.backtest.services.backtest_service import FiveLayerBacktestService
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        svc = FiveLayerBacktestService(db_manager=self.db)
        run = svc.run_backtest_pipeline(
            screening_run_id="sr-pipe-001",
            evaluation_mode="historical_snapshot",
            execution_model="conservative",
        )
        eval_repo = EvaluationRepository(self.db)
        evals = eval_repo.get_by_run(run.backtest_run_id)
        self.assertEqual(len(evals), 3)

    def test_pipeline_entry_signal_has_metrics(self):
        """Entry signal (probe_entry) should have forward_return_1d and MAE/MFE."""
        from src.backtest.services.backtest_service import FiveLayerBacktestService
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        svc = FiveLayerBacktestService(db_manager=self.db)
        run = svc.run_backtest_pipeline(
            screening_run_id="sr-pipe-001",
            evaluation_mode="historical_snapshot",
            execution_model="conservative",
        )
        eval_repo = EvaluationRepository(self.db)
        entries = eval_repo.get_by_run(run.backtest_run_id, signal_family="entry")
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry.code, "600519")
        self.assertIsNotNone(entry.forward_return_1d)
        self.assertIsNotNone(entry.mae)
        self.assertIsNotNone(entry.mfe)

    def test_pipeline_observation_signal_has_metrics(self):
        """Observation signal should have risk_avoided_pct and opportunity_cost_pct."""
        from src.backtest.services.backtest_service import FiveLayerBacktestService
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        svc = FiveLayerBacktestService(db_manager=self.db)
        run = svc.run_backtest_pipeline(
            screening_run_id="sr-pipe-001",
            evaluation_mode="historical_snapshot",
            execution_model="conservative",
        )
        eval_repo = EvaluationRepository(self.db)
        observations = eval_repo.get_by_run(run.backtest_run_id, signal_family="observation")
        self.assertEqual(len(observations), 2)
        for obs in observations:
            self.assertIsNotNone(obs.risk_avoided_pct)
            self.assertIsNotNone(obs.opportunity_cost_pct)

    def test_pipeline_snapshot_fields_populated(self):
        """Snapshot fields should be populated from screening candidates."""
        from src.backtest.services.backtest_service import FiveLayerBacktestService
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        svc = FiveLayerBacktestService(db_manager=self.db)
        run = svc.run_backtest_pipeline(
            screening_run_id="sr-pipe-001",
            evaluation_mode="historical_snapshot",
            execution_model="conservative",
        )
        eval_repo = EvaluationRepository(self.db)
        entries = eval_repo.get_by_run(run.backtest_run_id, signal_family="entry")
        entry = entries[0]
        self.assertEqual(entry.snapshot_trade_stage, "probe_entry")
        self.assertEqual(entry.snapshot_setup_type, "trend_breakout")
        self.assertEqual(entry.snapshot_market_regime, "balanced")

    def test_pipeline_replayed_fields_null_in_snapshot_mode(self):
        """In historical_snapshot mode, replayed_* fields must be NULL."""
        from src.backtest.services.backtest_service import FiveLayerBacktestService
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        svc = FiveLayerBacktestService(db_manager=self.db)
        run = svc.run_backtest_pipeline(
            screening_run_id="sr-pipe-001",
            evaluation_mode="historical_snapshot",
            execution_model="conservative",
        )
        eval_repo = EvaluationRepository(self.db)
        evals = eval_repo.get_by_run(run.backtest_run_id)
        for ev in evals:
            self.assertIsNone(ev.replayed_trade_stage)
            self.assertIsNone(ev.replayed_setup_type)
            self.assertIsNone(ev.replayed_market_regime)

    def test_pipeline_run_counters_updated(self):
        from src.backtest.services.backtest_service import FiveLayerBacktestService
        svc = FiveLayerBacktestService(db_manager=self.db)
        run = svc.run_backtest_pipeline(
            screening_run_id="sr-pipe-001",
            evaluation_mode="historical_snapshot",
            execution_model="conservative",
        )
        self.assertEqual(run.sample_count, 3)
        self.assertEqual(run.completed_count, 3)
        self.assertEqual(run.error_count, 0)

    def test_pipeline_entry_fill_status(self):
        """Entry evaluation should have fill status from execution model."""
        from src.backtest.services.backtest_service import FiveLayerBacktestService
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        svc = FiveLayerBacktestService(db_manager=self.db)
        run = svc.run_backtest_pipeline(
            screening_run_id="sr-pipe-001",
            evaluation_mode="historical_snapshot",
            execution_model="conservative",
        )
        eval_repo = EvaluationRepository(self.db)
        entries = eval_repo.get_by_run(run.backtest_run_id, signal_family="entry")
        entry = entries[0]
        self.assertEqual(entry.entry_fill_status, "filled")
        self.assertIsNotNone(entry.entry_fill_price)

    def test_pipeline_empty_screening_run(self):
        """Pipeline with non-existent screening_run_id should complete with 0 samples."""
        from src.backtest.services.backtest_service import FiveLayerBacktestService
        svc = FiveLayerBacktestService(db_manager=self.db)
        run = svc.run_backtest_pipeline(
            screening_run_id="non-existent",
            evaluation_mode="historical_snapshot",
            execution_model="conservative",
        )
        self.assertEqual(run.status, "completed")
        self.assertEqual(run.sample_count, 0)

    def test_pipeline_eval_status_evaluated(self):
        """Each evaluation should have eval_status='evaluated'."""
        from src.backtest.services.backtest_service import FiveLayerBacktestService
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        svc = FiveLayerBacktestService(db_manager=self.db)
        run = svc.run_backtest_pipeline(
            screening_run_id="sr-pipe-001",
            evaluation_mode="historical_snapshot",
            execution_model="conservative",
        )
        eval_repo = EvaluationRepository(self.db)
        evals = eval_repo.get_by_run(run.backtest_run_id)
        for ev in evals:
            self.assertEqual(ev.eval_status, "evaluated")


if __name__ == "__main__":
    unittest.main()
