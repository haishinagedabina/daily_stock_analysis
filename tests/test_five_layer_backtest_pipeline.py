# -*- coding: utf-8 -*-
"""Backtest pipeline integration tests.

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
                    matched_strategies_json=json.dumps(["trend_breakout", "ma100_60min_combined"]),
                    rule_hits_json=json.dumps(["trend_breakout_hit", "ma100_support_hit"]),
                    factor_snapshot_json=json.dumps({
                        "close": 100.0,
                        "ma20": 98.0,
                        "pattern_123_state": "confirmed",
                    }),
                    candidate_decision_json=json.dumps({
                        "primary_strategy": "trend_breakout",
                        "contributing_strategies": ["ma100_60min_combined"],
                        "strategy_scores": {
                            "trend_breakout": 88.5,
                            "ma100_60min_combined": 81.2,
                        },
                    }),
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

    def _seed_p0_screening_run(self):
        from src.storage import ScreeningRun, ScreeningCandidate
        with self.db.get_session() as session:
            run = ScreeningRun(
                run_id="sr-p0-001",
                trade_date=date(2024, 2, 20),
                market="cn",
                status="completed",
            )
            session.add(run)
            session.flush()

            candidates = [
                ScreeningCandidate(
                    run_id="sr-p0-001",
                    code="300750",
                    name="宁德时代",
                    rank=1,
                    rule_score=91.0,
                    matched_strategies_json=json.dumps(
                        ["bottom_divergence_double_breakout", "volume_breakout"]
                    ),
                    rule_hits_json=json.dumps(["bottom_divergence_hit", "volume_breakout_hit"]),
                    factor_snapshot_json=json.dumps(
                        {
                            "bottom_divergence_state": "confirmed",
                            "bottom_divergence_double_breakout": True,
                            "bottom_divergence_confirmation_days": 1,
                        }
                    ),
                    candidate_decision_json=json.dumps(
                        {
                            "primary_strategy": "bottom_divergence_double_breakout",
                            "contributing_strategies": ["volume_breakout"],
                            "strategy_scores": {
                                "bottom_divergence_double_breakout": 91.0,
                                "volume_breakout": 36.0,
                            },
                        }
                    ),
                    trade_stage="probe_entry",
                    setup_type="bottom_divergence_breakout",
                    entry_maturity="high",
                    market_regime="balanced",
                    theme_position="main_theme",
                    candidate_pool_level="leader_pool",
                    risk_level="medium",
                    trade_plan_json=json.dumps({"take_profit": 7.0, "stop_loss": -4.0}),
                ),
                ScreeningCandidate(
                    run_id="sr-p0-001",
                    code="002594",
                    name="比亚迪",
                    rank=2,
                    rule_score=88.0,
                    matched_strategies_json=json.dumps(
                        ["ma100_low123_combined", "volume_breakout"]
                    ),
                    rule_hits_json=json.dumps(["ma100_low123_hit", "volume_breakout_hit"]),
                    factor_snapshot_json=json.dumps(
                        {
                            "pattern_123_state": "confirmed",
                            "ma100_low123_confirmed": True,
                            "ma100_low123_data_complete": True,
                            "ma100_low123_validation_status": "confirmed",
                        }
                    ),
                    candidate_decision_json=json.dumps(
                        {
                            "primary_strategy": "ma100_low123_combined",
                            "contributing_strategies": ["volume_breakout"],
                            "strategy_scores": {
                                "ma100_low123_combined": 88.0,
                                "volume_breakout": 34.0,
                            },
                        }
                    ),
                    trade_stage="probe_entry",
                    setup_type="low123_breakout",
                    entry_maturity="high",
                    market_regime="balanced",
                    theme_position="main_theme",
                    candidate_pool_level="leader_pool",
                    risk_level="medium",
                    trade_plan_json=json.dumps({"take_profit": 6.0, "stop_loss": -3.5}),
                ),
            ]
            session.add_all(candidates)
            session.commit()

    def _seed_p0_stock_daily_data(self):
        from src.storage import StockDaily
        with self.db.get_session() as session:
            base_date = date(2024, 2, 20)
            for code, base_price in [("300750", 180.0), ("002594", 150.0)]:
                for i in range(1, 12):
                    d = base_date + timedelta(days=i)
                    price = base_price + i * 1.2
                    session.add(
                        StockDaily(
                            code=code,
                            date=d,
                            open=price - 1.0,
                            high=price + 2.5,
                            low=price - 2.0,
                            close=price,
                            pct_chg=0.8,
                            volume=1200000.0,
                            amount=150000000.0,
                        )
                    )
            session.commit()

    def _seed_stage_recovery_screening_run(self):
        from src.storage import ScreeningRun, ScreeningCandidate
        with self.db.get_session() as session:
            run = ScreeningRun(
                run_id="sr-stage-recovery-001",
                trade_date=date(2024, 3, 18),
                market="cn",
                status="completed",
            )
            session.add(run)
            session.flush()

            candidates = [
                ScreeningCandidate(
                    run_id="sr-stage-recovery-001",
                    code="600111",
                    name="鍖楁柟绋€鍦?",
                    rank=1,
                    rule_score=89.0,
                    matched_strategies_json=json.dumps(
                        ["ma100_low123_combined", "volume_breakout"]
                    ),
                    rule_hits_json=json.dumps(["ma100_low123_hit", "volume_breakout_hit"]),
                    factor_snapshot_json=json.dumps(
                        {
                            "pattern_123_state": "confirmed",
                            "ma100_low123_confirmed": True,
                            "ma100_low123_data_complete": True,
                            "ma100_low123_validation_status": "confirmed",
                        }
                    ),
                    candidate_decision_json=json.dumps(
                        {
                            "primary_strategy": "ma100_low123_combined",
                            "contributing_strategies": ["volume_breakout"],
                            "strategy_scores": {
                                "ma100_low123_combined": 89.0,
                                "volume_breakout": 35.0,
                            },
                        }
                    ),
                    trade_stage="focus",
                    setup_type="low123_breakout",
                    entry_maturity="high",
                    market_regime="balanced",
                    theme_position="main_theme",
                    candidate_pool_level="leader_pool",
                    risk_level="medium",
                    trade_plan_json=json.dumps({"take_profit": 6.5, "stop_loss": -3.2}),
                ),
                ScreeningCandidate(
                    run_id="sr-stage-recovery-001",
                    code="600222",
                    name="姹熻嫃闃冲厜",
                    rank=2,
                    rule_score=84.0,
                    matched_strategies_json=json.dumps(
                        ["ma100_low123_combined", "volume_breakout"]
                    ),
                    rule_hits_json=json.dumps(["ma100_low123_hit"]),
                    factor_snapshot_json=json.dumps(
                        {
                            "pattern_123_state": "confirmed",
                            "ma100_low123_confirmed": True,
                            "ma100_low123_data_complete": False,
                            "ma100_low123_validation_status": "confirmed_missing_breakout_bar_index",
                            "ma100_low123_validation_reason": "confirmed_missing_breakout_bar_index",
                        }
                    ),
                    candidate_decision_json=json.dumps(
                        {
                            "primary_strategy": "ma100_low123_combined",
                            "contributing_strategies": [],
                            "strategy_scores": {
                                "ma100_low123_combined": 84.0,
                            },
                        }
                    ),
                    trade_stage="focus",
                    setup_type="low123_breakout",
                    entry_maturity="high",
                    market_regime="balanced",
                    theme_position="main_theme",
                    candidate_pool_level="leader_pool",
                    risk_level="medium",
                    trade_plan_json=json.dumps({"take_profit": 6.0, "stop_loss": -3.0}),
                ),
            ]
            session.add_all(candidates)
            session.commit()

    def _seed_stage_recovery_stock_daily_data(self):
        from src.storage import StockDaily
        with self.db.get_session() as session:
            base_date = date(2024, 3, 18)
            for code, base_price in [("600111", 80.0), ("600222", 42.0)]:
                for i in range(1, 12):
                    d = base_date + timedelta(days=i)
                    price = base_price + i * 0.8
                    session.add(
                        StockDaily(
                            code=code,
                            date=d,
                            open=price - 0.4,
                            high=price + 1.5,
                            low=price - 1.0,
                            close=price,
                            pct_chg=0.6,
                            volume=900000.0,
                            amount=90000000.0,
                        )
                    )
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

    def test_pipeline_persists_factor_and_trade_plan_json(self):
        """Entry evaluation should retain factor snapshot and trade plan JSON for later tracing."""
        from src.backtest.services.backtest_service import FiveLayerBacktestService
        from src.backtest.repositories.evaluation_repo import EvaluationRepository

        svc = FiveLayerBacktestService(db_manager=self.db)
        run = svc.run_backtest_pipeline(
            screening_run_id="sr-pipe-001",
            evaluation_mode="historical_snapshot",
            execution_model="conservative",
        )
        eval_repo = EvaluationRepository(self.db)
        entry = eval_repo.get_by_run(run.backtest_run_id, signal_family="entry")[0]

        self.assertIsNotNone(entry.factor_snapshot_json)
        self.assertIn("pattern_123_state", entry.factor_snapshot_json)
        self.assertIsNotNone(entry.trade_plan_json)
        self.assertIn("take_profit", entry.trade_plan_json)

    def test_pipeline_persists_evidence_json_with_strategy_attribution(self):
        """Entry evaluation should retain matched strategies and attribution for strategy-cohort analysis."""
        from src.backtest.services.backtest_service import FiveLayerBacktestService
        from src.backtest.repositories.evaluation_repo import EvaluationRepository

        svc = FiveLayerBacktestService(db_manager=self.db)
        run = svc.run_backtest_pipeline(
            screening_run_id="sr-pipe-001",
            evaluation_mode="historical_snapshot",
            execution_model="conservative",
        )
        eval_repo = EvaluationRepository(self.db)
        entry = eval_repo.get_by_run(run.backtest_run_id, signal_family="entry")[0]

        self.assertIsNotNone(entry.evidence_json)
        evidence = json.loads(entry.evidence_json)
        self.assertCountEqual(
            evidence["matched_strategies"],
            ["trend_breakout", "ma100_60min_combined"],
        )
        self.assertEqual(evidence["primary_strategy"], "trend_breakout")
        self.assertCountEqual(
            evidence["contributing_strategies"],
            ["ma100_60min_combined"],
        )
        self.assertAlmostEqual(evidence["strategy_scores"]["trend_breakout"], 88.5)

    def test_pipeline_preserves_bottom_divergence_p0_strategy_in_evidence(self):
        """P0 sample: bottom divergence primary strategy should survive into backtest evidence."""
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        from src.backtest.services.backtest_service import FiveLayerBacktestService

        self._seed_p0_screening_run()
        self._seed_p0_stock_daily_data()

        svc = FiveLayerBacktestService(db_manager=self.db)
        run = svc.run_backtest_pipeline(
            screening_run_id="sr-p0-001",
            evaluation_mode="historical_snapshot",
            execution_model="conservative",
        )

        eval_repo = EvaluationRepository(self.db)
        entries = eval_repo.get_by_run(run.backtest_run_id, signal_family="entry")
        self.assertEqual({entry.code for entry in entries}, {"300750", "002594"})
        entries_by_code = {entry.code: entry for entry in entries}
        bottom_divergence = entries_by_code["300750"]

        evidence = json.loads(bottom_divergence.evidence_json)
        self.assertEqual(
            evidence["primary_strategy"],
            "bottom_divergence_double_breakout",
        )
        self.assertCountEqual(evidence["contributing_strategies"], ["volume_breakout"])
        self.assertEqual(bottom_divergence.snapshot_setup_type, "bottom_divergence_breakout")
        self.assertIn(
            "bottom_divergence_double_breakout",
            evidence["matched_strategies"],
        )

    def test_pipeline_preserves_low123_setup_and_ma100_strategy_in_evidence(self):
        """P0 sample: low123 setup should keep ma100_low123 strategy attribution."""
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        from src.backtest.services.backtest_service import FiveLayerBacktestService

        self._seed_p0_screening_run()
        self._seed_p0_stock_daily_data()

        svc = FiveLayerBacktestService(db_manager=self.db)
        run = svc.run_backtest_pipeline(
            screening_run_id="sr-p0-001",
            evaluation_mode="historical_snapshot",
            execution_model="conservative",
        )

        eval_repo = EvaluationRepository(self.db)
        entries = eval_repo.get_by_run(run.backtest_run_id, signal_family="entry")
        self.assertEqual({entry.code for entry in entries}, {"300750", "002594"})
        entries_by_code = {entry.code: entry for entry in entries}
        low123 = entries_by_code["002594"]

        evidence = json.loads(low123.evidence_json)
        factor_snapshot = json.loads(low123.factor_snapshot_json)
        self.assertEqual(evidence["primary_strategy"], "ma100_low123_combined")
        self.assertCountEqual(evidence["contributing_strategies"], ["volume_breakout"])
        self.assertEqual(low123.snapshot_setup_type, "low123_breakout")
        self.assertTrue(factor_snapshot["ma100_low123_confirmed"])
        self.assertEqual(factor_snapshot["ma100_low123_validation_status"], "confirmed")

    def test_pipeline_recovers_entry_from_snapshot_when_trade_stage_is_too_conservative(self):
        """Strong entry snapshots should still yield analyzable entry samples even when stored trade_stage is focus."""
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        from src.backtest.services.backtest_service import FiveLayerBacktestService

        self._seed_stage_recovery_screening_run()
        self._seed_stage_recovery_stock_daily_data()

        svc = FiveLayerBacktestService(db_manager=self.db)
        run = svc.run_backtest_pipeline(
            screening_run_id="sr-stage-recovery-001",
            evaluation_mode="historical_snapshot",
            execution_model="conservative",
        )

        eval_repo = EvaluationRepository(self.db)
        entries = eval_repo.get_by_run(run.backtest_run_id, signal_family="entry")
        self.assertEqual({entry.code for entry in entries}, {"600111"})

        recovered = entries[0]
        self.assertEqual(recovered.snapshot_trade_stage, "focus")
        self.assertEqual(recovered.signal_type, "probe_entry")
        self.assertIsNotNone(recovered.forward_return_5d)
        self.assertIsNotNone(recovered.plan_success)

        metrics = json.loads(recovered.metrics_json)
        self.assertEqual(metrics["effective_trade_stage"], "probe_entry")
        self.assertEqual(metrics["entry_timing_label"], "on_time")

        config = json.loads(run.config_json)
        self.assertEqual(config["sample_baseline"]["entry_sample_count"], 1)
        self.assertEqual(config["sample_baseline"]["observation_sample_count"], 1)

    def test_pipeline_keeps_missing_breakout_index_case_in_observation(self):
        """Conservative low123 rejection should remain observation when breakout_bar_index evidence is missing."""
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        from src.backtest.services.backtest_service import FiveLayerBacktestService

        self._seed_stage_recovery_screening_run()
        self._seed_stage_recovery_stock_daily_data()

        svc = FiveLayerBacktestService(db_manager=self.db)
        run = svc.run_backtest_pipeline(
            screening_run_id="sr-stage-recovery-001",
            evaluation_mode="historical_snapshot",
            execution_model="conservative",
        )

        eval_repo = EvaluationRepository(self.db)
        observations = eval_repo.get_by_run(run.backtest_run_id, signal_family="observation")
        guarded = next(item for item in observations if item.code == "600222")

        self.assertEqual(guarded.snapshot_trade_stage, "focus")
        self.assertEqual(guarded.signal_type, "focus")
        self.assertIsNotNone(guarded.risk_avoided_pct)

        factor_snapshot = json.loads(guarded.factor_snapshot_json)
        self.assertEqual(
            factor_snapshot["ma100_low123_validation_status"],
            "confirmed_missing_breakout_bar_index",
        )

    def test_pipeline_persists_sample_bucket_and_timing_metrics_for_entry(self):
        """Entry evaluation should persist selected/core bucket and timing labels in metrics_json."""
        from src.backtest.services.backtest_service import FiveLayerBacktestService
        from src.backtest.repositories.evaluation_repo import EvaluationRepository

        svc = FiveLayerBacktestService(db_manager=self.db)
        run = svc.run_backtest_pipeline(
            screening_run_id="sr-pipe-001",
            evaluation_mode="historical_snapshot",
            execution_model="conservative",
        )
        eval_repo = EvaluationRepository(self.db)
        entry = eval_repo.get_by_run(run.backtest_run_id, signal_family="entry")[0]

        self.assertIsNotNone(entry.metrics_json)
        metrics = json.loads(entry.metrics_json)
        self.assertEqual(metrics["sample_origin"], "selected")
        self.assertEqual(metrics["sample_bucket"], "core")
        self.assertEqual(metrics["entry_timing_label"], "on_time")
        self.assertIn("early_pullback_pct", metrics)
        self.assertIn("late_entry_gap_pct", metrics)

    def test_pipeline_persists_sample_bucket_for_observation(self):
        """Observation evaluation should persist selected origin and non-entry timing label."""
        from src.backtest.services.backtest_service import FiveLayerBacktestService
        from src.backtest.repositories.evaluation_repo import EvaluationRepository

        svc = FiveLayerBacktestService(db_manager=self.db)
        run = svc.run_backtest_pipeline(
            screening_run_id="sr-pipe-001",
            evaluation_mode="historical_snapshot",
            execution_model="conservative",
        )
        eval_repo = EvaluationRepository(self.db)
        observation = eval_repo.get_by_run(run.backtest_run_id, signal_family="observation")[0]

        self.assertIsNotNone(observation.metrics_json)
        metrics = json.loads(observation.metrics_json)
        self.assertEqual(metrics["sample_origin"], "selected")
        self.assertEqual(metrics["sample_bucket"], "boundary")
        self.assertEqual(metrics["entry_timing_label"], "not_applicable")

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

    def test_pipeline_persists_run_sample_baseline_in_config_json(self):
        """Completed runs should persist a sample baseline so API consumers can explain raw vs aggregatable counts."""
        from src.backtest.services.backtest_service import FiveLayerBacktestService

        svc = FiveLayerBacktestService(db_manager=self.db)
        run = svc.run_backtest_pipeline(
            screening_run_id="sr-pipe-001",
            evaluation_mode="historical_snapshot",
            execution_model="conservative",
        )

        self.assertIsNotNone(run.config_json)
        config = json.loads(run.config_json)
        self.assertEqual(
            config["sample_baseline"],
            {
                "raw_sample_count": 3,
                "evaluated_sample_count": 3,
                "aggregatable_sample_count": 3,
                "entry_sample_count": 1,
                "observation_sample_count": 2,
                "suppressed_sample_count": 0,
                "suppressed_reasons": {},
            },
        )

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
