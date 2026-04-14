# -*- coding: utf-8 -*-
"""TDD RED: Tests for GroupSummaryAggregator.

Aggregates evaluations into group summaries by:
- overall
- signal_family (entry/observation)
- snapshot_setup_type
- snapshot_market_regime
- combo (market_regime+signal_family)
"""

import json
import os
import tempfile
import unittest
from datetime import date, timedelta

import pytest


@pytest.mark.unit
class TestGroupSummaryAggregator(unittest.TestCase):

    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "test_agg.db")
        os.environ["DATABASE_PATH"] = self._db_path
        from src.config import Config
        Config._instance = None
        from src.storage import DatabaseManager
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()
        self._seed()

    def tearDown(self):
        from src.storage import DatabaseManager
        from src.config import Config
        DatabaseManager.reset_instance()
        Config._instance = None
        os.environ.pop("DATABASE_PATH", None)
        self._temp_dir.cleanup()

    def _seed(self):
        from src.backtest.repositories.run_repo import RunRepository
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        from src.backtest.models.backtest_models import FiveLayerBacktestEvaluation

        RunRepository(self.db).create_run(
            backtest_run_id="run-agg",
            evaluation_mode="historical_snapshot",
            execution_model="conservative",
            trade_date_from=date(2024, 1, 1),
            trade_date_to=date(2024, 1, 31),
            market="cn",
        )

        evals = [
            # 2 entry signals
            FiveLayerBacktestEvaluation(
                backtest_run_id="run-agg",
                screening_candidate_id=1,
                trade_date=date(2024, 1, 15),
                code="600519",
                signal_family="entry",
                evaluator_type="entry",
                snapshot_trade_stage="probe_entry",
                snapshot_setup_type="trend_breakout",
                snapshot_market_regime="balanced",
                forward_return_5d=5.0,
                forward_return_1d=2.0,
                mae=-3.0,
                mfe=8.0,
                max_drawdown_from_peak=-4.0,
                plan_success=True,
                signal_quality_score=0.7,
                outcome="win",
                eval_status="evaluated",
            ),
            FiveLayerBacktestEvaluation(
                backtest_run_id="run-agg",
                screening_candidate_id=2,
                trade_date=date(2024, 1, 16),
                code="000858",
                signal_family="entry",
                evaluator_type="entry",
                snapshot_trade_stage="probe_entry",
                snapshot_setup_type="trend_pullback",
                snapshot_market_regime="balanced",
                forward_return_5d=-2.0,
                forward_return_1d=-1.0,
                mae=-6.0,
                mfe=3.0,
                max_drawdown_from_peak=-7.0,
                plan_success=False,
                signal_quality_score=0.3,
                outcome="loss",
                eval_status="evaluated",
            ),
            # 2 observation signals
            FiveLayerBacktestEvaluation(
                backtest_run_id="run-agg",
                screening_candidate_id=3,
                trade_date=date(2024, 1, 15),
                code="601318",
                signal_family="observation",
                evaluator_type="observation",
                snapshot_trade_stage="watch",
                snapshot_setup_type=None,
                snapshot_market_regime="balanced",
                risk_avoided_pct=8.0,
                opportunity_cost_pct=3.0,
                stage_success=True,
                outcome="correct_wait",
                eval_status="evaluated",
            ),
            FiveLayerBacktestEvaluation(
                backtest_run_id="run-agg",
                screening_candidate_id=4,
                trade_date=date(2024, 1, 16),
                code="600036",
                signal_family="observation",
                evaluator_type="observation",
                snapshot_trade_stage="stand_aside",
                snapshot_setup_type=None,
                snapshot_market_regime="defensive",
                risk_avoided_pct=2.0,
                opportunity_cost_pct=10.0,
                stage_success=False,
                outcome="missed_opportunity",
                eval_status="evaluated",
            ),
        ]
        EvaluationRepository(self.db).save_batch(evals)

    def test_compute_all_returns_summaries(self):
        from src.backtest.aggregators.group_summary_aggregator import GroupSummaryAggregator
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        from src.backtest.repositories.summary_repo import SummaryRepository
        agg = GroupSummaryAggregator(EvaluationRepository(self.db), SummaryRepository(self.db))
        summaries = agg.compute_all_summaries("run-agg")
        self.assertGreater(len(summaries), 0)

    def test_overall_summary(self):
        from src.backtest.aggregators.group_summary_aggregator import GroupSummaryAggregator
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        from src.backtest.repositories.summary_repo import SummaryRepository
        agg = GroupSummaryAggregator(EvaluationRepository(self.db), SummaryRepository(self.db))
        summaries = agg.compute_all_summaries("run-agg")
        overall = [s for s in summaries if s.group_type == "overall"]
        self.assertEqual(len(overall), 1)
        self.assertEqual(overall[0].sample_count, 4)

    def test_signal_family_groups(self):
        from src.backtest.aggregators.group_summary_aggregator import GroupSummaryAggregator
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        from src.backtest.repositories.summary_repo import SummaryRepository
        agg = GroupSummaryAggregator(EvaluationRepository(self.db), SummaryRepository(self.db))
        summaries = agg.compute_all_summaries("run-agg")
        sf = {s.group_key: s for s in summaries if s.group_type == "signal_family"}
        self.assertIn("entry", sf)
        self.assertIn("observation", sf)
        self.assertEqual(sf["entry"].sample_count, 2)
        self.assertEqual(sf["observation"].sample_count, 2)

    def test_entry_win_rate(self):
        """Entry group should have 50% win rate (1 win, 1 loss)."""
        from src.backtest.aggregators.group_summary_aggregator import GroupSummaryAggregator
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        from src.backtest.repositories.summary_repo import SummaryRepository
        agg = GroupSummaryAggregator(EvaluationRepository(self.db), SummaryRepository(self.db))
        summaries = agg.compute_all_summaries("run-agg")
        entry = next(s for s in summaries if s.group_type == "signal_family" and s.group_key == "entry")
        self.assertAlmostEqual(entry.win_rate_pct, 50.0)

    def test_entry_avg_return(self):
        """Entry avg return = (5.0 + -2.0) / 2 = 1.5."""
        from src.backtest.aggregators.group_summary_aggregator import GroupSummaryAggregator
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        from src.backtest.repositories.summary_repo import SummaryRepository
        agg = GroupSummaryAggregator(EvaluationRepository(self.db), SummaryRepository(self.db))
        summaries = agg.compute_all_summaries("run-agg")
        entry = next(s for s in summaries if s.group_type == "signal_family" and s.group_key == "entry")
        self.assertAlmostEqual(entry.avg_return_pct, 1.5)

    def test_setup_type_groups(self):
        """Should have groups for non-None setup_types."""
        from src.backtest.aggregators.group_summary_aggregator import GroupSummaryAggregator
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        from src.backtest.repositories.summary_repo import SummaryRepository
        agg = GroupSummaryAggregator(EvaluationRepository(self.db), SummaryRepository(self.db))
        summaries = agg.compute_all_summaries("run-agg")
        st = {s.group_key: s for s in summaries if s.group_type == "setup_type"}
        self.assertIn("trend_breakout", st)
        self.assertIn("trend_pullback", st)

    def test_market_regime_groups(self):
        from src.backtest.aggregators.group_summary_aggregator import GroupSummaryAggregator
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        from src.backtest.repositories.summary_repo import SummaryRepository
        agg = GroupSummaryAggregator(EvaluationRepository(self.db), SummaryRepository(self.db))
        summaries = agg.compute_all_summaries("run-agg")
        mr = {s.group_key: s for s in summaries if s.group_type == "market_regime"}
        self.assertIn("balanced", mr)
        self.assertIn("defensive", mr)

    def test_combo_groups(self):
        """Should produce market_regime+signal_family combos."""
        from src.backtest.aggregators.group_summary_aggregator import GroupSummaryAggregator
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        from src.backtest.repositories.summary_repo import SummaryRepository
        agg = GroupSummaryAggregator(EvaluationRepository(self.db), SummaryRepository(self.db))
        summaries = agg.compute_all_summaries("run-agg")
        combos = [s for s in summaries if s.group_type == "combo"]
        self.assertGreater(len(combos), 0)
        keys = [s.group_key for s in combos]
        self.assertIn("balanced+entry", keys)

    def test_summaries_persisted(self):
        """Summaries should be saved to DB."""
        from src.backtest.aggregators.group_summary_aggregator import GroupSummaryAggregator
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        from src.backtest.repositories.summary_repo import SummaryRepository
        sr = SummaryRepository(self.db)
        agg = GroupSummaryAggregator(EvaluationRepository(self.db), sr)
        agg.compute_all_summaries("run-agg")
        persisted = sr.get_by_run("run-agg")
        self.assertGreater(len(persisted), 0)

    def test_observation_stage_success_rate(self):
        """Observation group: 1 correct_wait, 1 missed_opportunity → 50% stage_success."""
        from src.backtest.aggregators.group_summary_aggregator import GroupSummaryAggregator
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        from src.backtest.repositories.summary_repo import SummaryRepository
        agg = GroupSummaryAggregator(EvaluationRepository(self.db), SummaryRepository(self.db))
        summaries = agg.compute_all_summaries("run-agg")
        obs = next(s for s in summaries if s.group_type == "signal_family" and s.group_key == "observation")
        self.assertAlmostEqual(obs.win_rate_pct, 50.0)


if __name__ == "__main__":
    unittest.main()
