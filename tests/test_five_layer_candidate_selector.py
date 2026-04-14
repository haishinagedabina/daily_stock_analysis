# -*- coding: utf-8 -*-
"""TDD RED phase: Tests for CandidateSelector.

CandidateSelector reads ScreeningCandidate records from the DB
and extracts five-layer snapshot fields for backtest evaluation.
"""

import json
import os
import tempfile
import unittest
from datetime import date, datetime

import pytest


@pytest.mark.unit
class TestCandidateSelector(unittest.TestCase):
    """Integration tests for candidate selection from screening data."""

    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "test_selector.db")
        os.environ["DATABASE_PATH"] = self._db_path
        from src.config import Config
        Config._instance = None
        from src.storage import DatabaseManager
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()
        self._seed_data()

    def tearDown(self):
        from src.storage import DatabaseManager
        from src.config import Config
        DatabaseManager.reset_instance()
        Config._instance = None
        os.environ.pop("DATABASE_PATH", None)
        self._temp_dir.cleanup()

    def _seed_data(self):
        """Seed ScreeningRun + ScreeningCandidate records."""
        from src.storage import ScreeningRun, ScreeningCandidate
        with self.db.get_session() as session:
            run = ScreeningRun(
                run_id="sr-sel-001",
                trade_date=date(2024, 1, 15),
                market="cn",
                status="completed",
            )
            session.add(run)
            session.flush()

            candidates = [
                ScreeningCandidate(
                    run_id="sr-sel-001",
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
                    run_id="sr-sel-001",
                    code="000858",
                    name="五粮液",
                    rank=2,
                    rule_score=72.0,
                    trade_stage="watch",
                    setup_type=None,
                    entry_maturity="low",
                    market_regime="balanced",
                    theme_position="related_theme",
                    candidate_pool_level="follower_pool",
                    risk_level="low",
                ),
                ScreeningCandidate(
                    run_id="sr-sel-001",
                    code="601318",
                    name="中国平安",
                    rank=3,
                    rule_score=60.0,
                    trade_stage="focus",
                    ai_trade_stage="probe_entry",
                    ai_confidence=0.85,
                    setup_type="trend_pullback",
                    entry_maturity="medium",
                    market_regime="balanced",
                    theme_position="non_theme",
                    candidate_pool_level="follower_pool",
                    risk_level="medium",
                ),
            ]
            session.add_all(candidates)
            session.commit()

    def test_select_by_run_id(self):
        """Should return all candidates for a given screening run."""
        from src.backtest.services.candidate_selector import CandidateSelector
        selector = CandidateSelector(self.db)
        candidates = selector.select_candidates(screening_run_id="sr-sel-001")
        self.assertEqual(len(candidates), 3)

    def test_select_returns_snapshot_fields(self):
        """Each candidate should have all five-layer snapshot fields populated."""
        from src.backtest.services.candidate_selector import CandidateSelector
        selector = CandidateSelector(self.db)
        candidates = selector.select_candidates(screening_run_id="sr-sel-001")
        entry_candidate = [c for c in candidates if c["code"] == "600519"][0]
        self.assertEqual(entry_candidate["trade_stage"], "probe_entry")
        self.assertEqual(entry_candidate["setup_type"], "trend_breakout")
        self.assertEqual(entry_candidate["entry_maturity"], "high")
        self.assertEqual(entry_candidate["market_regime"], "balanced")
        self.assertEqual(entry_candidate["theme_position"], "main_theme")
        self.assertEqual(entry_candidate["candidate_pool_level"], "leader_pool")
        self.assertEqual(entry_candidate["risk_level"], "medium")

    def test_select_includes_ai_fields(self):
        """AI override fields should be included when present."""
        from src.backtest.services.candidate_selector import CandidateSelector
        selector = CandidateSelector(self.db)
        candidates = selector.select_candidates(screening_run_id="sr-sel-001")
        ai_candidate = [c for c in candidates if c["code"] == "601318"][0]
        self.assertEqual(ai_candidate["ai_trade_stage"], "probe_entry")
        self.assertAlmostEqual(ai_candidate["ai_confidence"], 0.85)

    def test_select_includes_trade_plan(self):
        """Trade plan JSON should be parsed when available."""
        from src.backtest.services.candidate_selector import CandidateSelector
        selector = CandidateSelector(self.db)
        candidates = selector.select_candidates(screening_run_id="sr-sel-001")
        entry_candidate = [c for c in candidates if c["code"] == "600519"][0]
        self.assertIsNotNone(entry_candidate.get("trade_plan"))
        self.assertAlmostEqual(entry_candidate["trade_plan"]["take_profit"], 5.0)

    def test_select_empty_run(self):
        """Non-existent run should return empty list."""
        from src.backtest.services.candidate_selector import CandidateSelector
        selector = CandidateSelector(self.db)
        candidates = selector.select_candidates(screening_run_id="non-existent")
        self.assertEqual(len(candidates), 0)

    def test_select_by_date_range(self):
        """Should select candidates across runs within a date range."""
        from src.backtest.services.candidate_selector import CandidateSelector
        selector = CandidateSelector(self.db)
        candidates = selector.select_candidates_by_date_range(
            date_from=date(2024, 1, 1),
            date_to=date(2024, 1, 31),
        )
        self.assertEqual(len(candidates), 3)

    def test_select_by_date_range_no_results(self):
        """Date range with no runs should return empty list."""
        from src.backtest.services.candidate_selector import CandidateSelector
        selector = CandidateSelector(self.db)
        candidates = selector.select_candidates_by_date_range(
            date_from=date(2025, 1, 1),
            date_to=date(2025, 1, 31),
        )
        self.assertEqual(len(candidates), 0)

    def test_candidate_dict_has_screening_metadata(self):
        """Each candidate dict should include screening_run_id, screening_candidate_id, trade_date."""
        from src.backtest.services.candidate_selector import CandidateSelector
        selector = CandidateSelector(self.db)
        candidates = selector.select_candidates(screening_run_id="sr-sel-001")
        c = candidates[0]
        self.assertIn("screening_run_id", c)
        self.assertIn("screening_candidate_id", c)
        self.assertIn("trade_date", c)
        self.assertEqual(c["screening_run_id"], "sr-sel-001")


if __name__ == "__main__":
    unittest.main()
