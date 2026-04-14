# -*- coding: utf-8 -*-
"""TDD: Tests for RecommendationEngine.

Validates graded recommendation generation:
- observation level (sample >= 5)
- hypothesis level (sample >= 20, stability passed)
- actionable level (sample >= 50, stability + consistency + evidence)
- RED LINE: never modifies rules/thresholds/parameters
"""

import json
import os
import tempfile
import unittest
from datetime import date

import pytest


@pytest.mark.unit
class TestRecommendationEngine(unittest.TestCase):

    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "test_rec.db")
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
        from src.backtest.repositories.summary_repo import SummaryRepository
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        from src.backtest.models.backtest_models import FiveLayerBacktestEvaluation

        RunRepository(self.db).create_run(
            backtest_run_id="run-rec",
            evaluation_mode="historical_snapshot",
            execution_model="conservative",
            trade_date_from=date(2024, 1, 1),
            trade_date_to=date(2024, 6, 30),
            market="cn",
        )

        sr = SummaryRepository(self.db)

        # Overall — should be skipped (group_type == "overall")
        sr.upsert_summary("run-rec", "overall", "all", sample_count=100,
                          avg_return_pct=2.0, win_rate_pct=55.0)

        # Strong signal_family=entry: high win_rate + positive return → weight_increase
        # sample=60, stability + consistency → actionable
        sr.upsert_summary("run-rec", "signal_family", "entry", sample_count=60,
                          avg_return_pct=4.5, win_rate_pct=65.0,
                          time_bucket_stability=0.08, extreme_sample_ratio=0.03)

        # Weak setup_type=mean_reversion: low win_rate + negative return → weight_decrease
        # sample=25, stability ok → hypothesis
        sr.upsert_summary("run-rec", "setup_type", "mean_reversion", sample_count=25,
                          avg_return_pct=-3.0, win_rate_pct=30.0,
                          time_bucket_stability=0.10, extreme_sample_ratio=0.05)

        # Small setup_type=event: sample=8 → observation only
        sr.upsert_summary("run-rec", "setup_type", "event", sample_count=8,
                          avg_return_pct=-2.0, win_rate_pct=35.0,
                          time_bucket_stability=0.05, extreme_sample_ratio=0.02)

        # Borderline: positive win_rate but negative return → execution_review
        # sample=30, stability ok → hypothesis
        sr.upsert_summary("run-rec", "market_regime", "volatile", sample_count=30,
                          avg_return_pct=-1.0, win_rate_pct=52.0,
                          time_bucket_stability=0.12, extreme_sample_ratio=0.04)

        # No recommendation: mediocre metrics
        sr.upsert_summary("run-rec", "market_regime", "balanced", sample_count=50,
                          avg_return_pct=1.0, win_rate_pct=50.0,
                          time_bucket_stability=0.10, extreme_sample_ratio=0.05)

        # Tiny group below observation min → should be skipped
        sr.upsert_summary("run-rec", "entry_maturity", "ULTRA", sample_count=3,
                          avg_return_pct=10.0, win_rate_pct=100.0)

        # Seed some evaluations for evidence building
        evals = [
            FiveLayerBacktestEvaluation(
                backtest_run_id="run-rec",
                screening_candidate_id=i,
                trade_date=date(2024, 1, 15),
                code=f"60051{i}",
                signal_family="entry",
                evaluator_type="entry",
                snapshot_setup_type="trend_breakout",
                snapshot_market_regime="balanced",
                forward_return_5d=3.0,
                outcome="win",
                eval_status="evaluated",
            )
            for i in range(1, 6)
        ]
        EvaluationRepository(self.db).save_batch(evals)

    def test_generates_recommendations(self):
        from src.backtest.recommendations.recommendation_engine import RecommendationEngine
        from src.backtest.repositories.summary_repo import SummaryRepository
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        from src.backtest.repositories.recommendation_repo import RecommendationRepository
        engine = RecommendationEngine(
            SummaryRepository(self.db),
            EvaluationRepository(self.db),
            RecommendationRepository(self.db),
        )
        recs = engine.generate_recommendations("run-rec")
        self.assertGreater(len(recs), 0)

    def test_skips_overall_group(self):
        """Overall summary should never produce a recommendation."""
        from src.backtest.recommendations.recommendation_engine import RecommendationEngine
        from src.backtest.repositories.summary_repo import SummaryRepository
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        from src.backtest.repositories.recommendation_repo import RecommendationRepository
        engine = RecommendationEngine(
            SummaryRepository(self.db),
            EvaluationRepository(self.db),
            RecommendationRepository(self.db),
        )
        recs = engine.generate_recommendations("run-rec")
        scopes = [r.target_scope for r in recs]
        self.assertNotIn("overall", scopes)

    def test_actionable_for_strong_signal(self):
        """Entry with 60 samples + stability + consistency → actionable."""
        from src.backtest.recommendations.recommendation_engine import RecommendationEngine
        from src.backtest.repositories.summary_repo import SummaryRepository
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        from src.backtest.repositories.recommendation_repo import RecommendationRepository
        engine = RecommendationEngine(
            SummaryRepository(self.db),
            EvaluationRepository(self.db),
            RecommendationRepository(self.db),
        )
        recs = engine.generate_recommendations("run-rec")
        entry_rec = next((r for r in recs if r.target_key == "entry"), None)
        self.assertIsNotNone(entry_rec)
        self.assertEqual(entry_rec.recommendation_level, "actionable")
        self.assertEqual(entry_rec.recommendation_type, "weight_increase")

    def test_hypothesis_for_medium_sample(self):
        """mean_reversion with 25 samples + stability → hypothesis."""
        from src.backtest.recommendations.recommendation_engine import RecommendationEngine
        from src.backtest.repositories.summary_repo import SummaryRepository
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        from src.backtest.repositories.recommendation_repo import RecommendationRepository
        engine = RecommendationEngine(
            SummaryRepository(self.db),
            EvaluationRepository(self.db),
            RecommendationRepository(self.db),
        )
        recs = engine.generate_recommendations("run-rec")
        mr_rec = next((r for r in recs if r.target_key == "mean_reversion"), None)
        self.assertIsNotNone(mr_rec)
        self.assertEqual(mr_rec.recommendation_level, "hypothesis")
        self.assertEqual(mr_rec.recommendation_type, "weight_decrease")

    def test_observation_for_small_sample(self):
        """event with 8 samples → observation only."""
        from src.backtest.recommendations.recommendation_engine import RecommendationEngine
        from src.backtest.repositories.summary_repo import SummaryRepository
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        from src.backtest.repositories.recommendation_repo import RecommendationRepository
        engine = RecommendationEngine(
            SummaryRepository(self.db),
            EvaluationRepository(self.db),
            RecommendationRepository(self.db),
        )
        recs = engine.generate_recommendations("run-rec")
        ev_rec = next((r for r in recs if r.target_key == "event"), None)
        self.assertIsNotNone(ev_rec)
        self.assertEqual(ev_rec.recommendation_level, "observation")

    def test_skips_below_observation_min(self):
        """ULTRA with 3 samples → no recommendation."""
        from src.backtest.recommendations.recommendation_engine import RecommendationEngine
        from src.backtest.repositories.summary_repo import SummaryRepository
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        from src.backtest.repositories.recommendation_repo import RecommendationRepository
        engine = RecommendationEngine(
            SummaryRepository(self.db),
            EvaluationRepository(self.db),
            RecommendationRepository(self.db),
        )
        recs = engine.generate_recommendations("run-rec")
        ultra_rec = next((r for r in recs if r.target_key == "ULTRA"), None)
        self.assertIsNone(ultra_rec)

    def test_execution_review_for_inconsistent(self):
        """volatile: win_rate>50 but return<0 → execution_review."""
        from src.backtest.recommendations.recommendation_engine import RecommendationEngine
        from src.backtest.repositories.summary_repo import SummaryRepository
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        from src.backtest.repositories.recommendation_repo import RecommendationRepository
        engine = RecommendationEngine(
            SummaryRepository(self.db),
            EvaluationRepository(self.db),
            RecommendationRepository(self.db),
        )
        recs = engine.generate_recommendations("run-rec")
        vol_rec = next((r for r in recs if r.target_key == "volatile"), None)
        self.assertIsNotNone(vol_rec)
        self.assertEqual(vol_rec.recommendation_type, "execution_review")

    def test_evidence_json_populated(self):
        """Each recommendation should have evidence_json with audit trail."""
        from src.backtest.recommendations.recommendation_engine import RecommendationEngine
        from src.backtest.repositories.summary_repo import SummaryRepository
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        from src.backtest.repositories.recommendation_repo import RecommendationRepository
        engine = RecommendationEngine(
            SummaryRepository(self.db),
            EvaluationRepository(self.db),
            RecommendationRepository(self.db),
        )
        recs = engine.generate_recommendations("run-rec")
        for rec in recs:
            self.assertIsNotNone(rec.evidence_json)
            evidence = json.loads(rec.evidence_json)
            self.assertIn("source_summary", evidence)
            self.assertIn("threshold_check", evidence)

    def test_recommendations_persisted(self):
        """Recommendations should be saved to DB."""
        from src.backtest.recommendations.recommendation_engine import RecommendationEngine
        from src.backtest.repositories.summary_repo import SummaryRepository
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        from src.backtest.repositories.recommendation_repo import RecommendationRepository
        rec_repo = RecommendationRepository(self.db)
        engine = RecommendationEngine(
            SummaryRepository(self.db),
            EvaluationRepository(self.db),
            rec_repo,
        )
        engine.generate_recommendations("run-rec")
        persisted = rec_repo.get_by_run("run-rec")
        self.assertGreater(len(persisted), 0)

    def test_confidence_score_range(self):
        """All confidence scores should be between 0 and 1."""
        from src.backtest.recommendations.recommendation_engine import RecommendationEngine
        from src.backtest.repositories.summary_repo import SummaryRepository
        from src.backtest.repositories.evaluation_repo import EvaluationRepository
        from src.backtest.repositories.recommendation_repo import RecommendationRepository
        engine = RecommendationEngine(
            SummaryRepository(self.db),
            EvaluationRepository(self.db),
            RecommendationRepository(self.db),
        )
        recs = engine.generate_recommendations("run-rec")
        for rec in recs:
            self.assertGreaterEqual(rec.confidence, 0.0)
            self.assertLessEqual(rec.confidence, 1.0)


if __name__ == "__main__":
    unittest.main()
