# -*- coding: utf-8 -*-
"""TDD RED: Tests for RecommendationRepository CRUD."""

import os
import tempfile
import unittest
from datetime import date

import pytest


@pytest.mark.unit
class TestRecommendationRepository(unittest.TestCase):

    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "test_rec.db")
        os.environ["DATABASE_PATH"] = self._db_path
        from src.config import Config
        Config._instance = None
        from src.storage import DatabaseManager
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()
        self._create_run()

    def tearDown(self):
        from src.storage import DatabaseManager
        from src.config import Config
        DatabaseManager.reset_instance()
        Config._instance = None
        os.environ.pop("DATABASE_PATH", None)
        self._temp_dir.cleanup()

    def _create_run(self):
        from src.backtest.repositories.run_repo import RunRepository
        RunRepository(self.db).create_run(
            backtest_run_id="run-rec",
            evaluation_mode="historical_snapshot",
            execution_model="conservative",
            trade_date_from=date(2024, 1, 1),
            trade_date_to=date(2024, 1, 31),
            market="cn",
        )

    def test_save_and_get(self):
        from src.backtest.repositories.recommendation_repo import RecommendationRepository
        from src.backtest.models.backtest_models import FiveLayerBacktestRecommendation
        repo = RecommendationRepository(self.db)
        rec = FiveLayerBacktestRecommendation(
            backtest_run_id="run-rec",
            recommendation_type="threshold_adjustment",
            target_scope="setup_type",
            target_key="trend_breakout",
            current_rule="win_rate >= 50%",
            suggested_change="win_rate >= 55%",
            recommendation_level="hypothesis",
            sample_count=80,
            confidence=0.72,
        )
        repo.save_batch([rec])
        results = repo.get_by_run("run-rec")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].recommendation_type, "threshold_adjustment")

    def test_save_batch_multiple(self):
        from src.backtest.repositories.recommendation_repo import RecommendationRepository
        from src.backtest.models.backtest_models import FiveLayerBacktestRecommendation
        repo = RecommendationRepository(self.db)
        recs = [
            FiveLayerBacktestRecommendation(
                backtest_run_id="run-rec",
                recommendation_type="threshold_adjustment",
                target_scope="setup_type",
                target_key=f"type_{i}",
                recommendation_level="observation",
            )
            for i in range(3)
        ]
        repo.save_batch(recs)
        self.assertEqual(len(repo.get_by_run("run-rec")), 3)

    def test_get_empty(self):
        from src.backtest.repositories.recommendation_repo import RecommendationRepository
        repo = RecommendationRepository(self.db)
        self.assertEqual(len(repo.get_by_run("non-existent")), 0)


if __name__ == "__main__":
    unittest.main()
