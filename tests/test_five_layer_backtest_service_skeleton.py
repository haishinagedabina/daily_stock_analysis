# -*- coding: utf-8 -*-
"""TDD RED phase: Tests for FiveLayerBacktestService skeleton.

Verifies that the service can be instantiated and exposes the expected
public API (create_run, select_candidates stub, run_backtest stub).
"""

import os
import tempfile
import unittest
from datetime import date

import pytest


@pytest.mark.unit
class TestFiveLayerBacktestServiceSkeleton(unittest.TestCase):
    """Service skeleton should expose the intended public API."""

    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "test_svc.db")
        os.environ["DATABASE_PATH"] = self._db_path
        from src.config import Config
        Config._instance = None
        from src.storage import DatabaseManager
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()

    def tearDown(self):
        from src.storage import DatabaseManager
        from src.config import Config
        DatabaseManager.reset_instance()
        Config._instance = None
        os.environ.pop("DATABASE_PATH", None)
        self._temp_dir.cleanup()

    def test_service_instantiation(self):
        """Service should instantiate with db_manager."""
        from src.backtest.services.backtest_service import FiveLayerBacktestService
        svc = FiveLayerBacktestService(db_manager=self.db)
        self.assertIsNotNone(svc)

    def test_create_run_via_service(self):
        """Service.create_run should delegate to RunRepository and return a run."""
        from src.backtest.services.backtest_service import FiveLayerBacktestService
        svc = FiveLayerBacktestService(db_manager=self.db)
        run = svc.create_run(
            evaluation_mode="historical_snapshot",
            execution_model="conservative",
            trade_date_from=date(2024, 1, 1),
            trade_date_to=date(2024, 1, 31),
        )
        self.assertIsNotNone(run.backtest_run_id)
        self.assertEqual(run.status, "pending")
        self.assertEqual(run.evaluation_mode, "historical_snapshot")

    def test_run_backtest_stub_returns_run(self):
        """Service.run_backtest stub should create a run and return it (no real evaluation yet)."""
        from src.backtest.services.backtest_service import FiveLayerBacktestService
        svc = FiveLayerBacktestService(db_manager=self.db)
        run = svc.run_backtest(
            evaluation_mode="historical_snapshot",
            execution_model="conservative",
            trade_date_from=date(2024, 1, 1),
            trade_date_to=date(2024, 1, 31),
        )
        self.assertIsNotNone(run)
        self.assertIn(run.status, ("pending", "completed"))

    def test_get_run_via_service(self):
        """Service.get_run should retrieve a previously created run."""
        from src.backtest.services.backtest_service import FiveLayerBacktestService
        svc = FiveLayerBacktestService(db_manager=self.db)
        created = svc.create_run(
            evaluation_mode="historical_snapshot",
            execution_model="conservative",
            trade_date_from=date(2024, 1, 1),
            trade_date_to=date(2024, 1, 31),
        )
        found = svc.get_run(created.backtest_run_id)
        self.assertIsNotNone(found)
        self.assertEqual(found.backtest_run_id, created.backtest_run_id)


if __name__ == "__main__":
    unittest.main()
