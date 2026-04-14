# -*- coding: utf-8 -*-
"""TDD: Tests for RankingEffectivenessCalculator.

Validates that the screening system's tiered ranking (pool levels,
theme positions, maturity grades) actually predicts forward performance.
"""

import os
import tempfile
import unittest
from datetime import date

import pytest


@pytest.mark.unit
class TestRankingEffectivenessCalculator(unittest.TestCase):

    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "test_rank.db")
        os.environ["DATABASE_PATH"] = self._db_path
        from src.config import Config
        Config._instance = None
        from src.storage import DatabaseManager
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()
        self._seed_summaries()

    def tearDown(self):
        from src.storage import DatabaseManager
        from src.config import Config
        DatabaseManager.reset_instance()
        Config._instance = None
        os.environ.pop("DATABASE_PATH", None)
        self._temp_dir.cleanup()

    def _seed_summaries(self):
        """Seed group summaries simulating tiered performance.

        Pool levels: leader_pool (avg 5%) > focus_list (avg 2%) > watchlist (avg -1%)
        Theme positions: main_theme (avg 4%) > non_theme (avg 0%)
        Maturity: HIGH (avg 6%) > LOW (avg 1%)
        """
        from src.backtest.repositories.run_repo import RunRepository
        from src.backtest.repositories.summary_repo import SummaryRepository

        RunRepository(self.db).create_run(
            backtest_run_id="run-rank",
            evaluation_mode="historical_snapshot",
            execution_model="conservative",
            trade_date_from=date(2024, 1, 1),
            trade_date_to=date(2024, 3, 31),
            market="cn",
        )

        sr = SummaryRepository(self.db)

        # candidate_pool_level tiers
        sr.upsert_summary("run-rank", "candidate_pool_level", "leader_pool",
                          sample_count=20, avg_return_pct=5.0, win_rate_pct=65.0)
        sr.upsert_summary("run-rank", "candidate_pool_level", "focus_list",
                          sample_count=30, avg_return_pct=2.0, win_rate_pct=55.0)
        sr.upsert_summary("run-rank", "candidate_pool_level", "watchlist",
                          sample_count=40, avg_return_pct=-1.0, win_rate_pct=35.0)

        # theme_position tiers
        sr.upsert_summary("run-rank", "theme_position", "main_theme",
                          sample_count=25, avg_return_pct=4.0, win_rate_pct=60.0)
        sr.upsert_summary("run-rank", "theme_position", "non_theme",
                          sample_count=15, avg_return_pct=0.0, win_rate_pct=45.0)

        # entry_maturity tiers
        sr.upsert_summary("run-rank", "entry_maturity", "HIGH",
                          sample_count=10, avg_return_pct=6.0, win_rate_pct=70.0)
        sr.upsert_summary("run-rank", "entry_maturity", "LOW",
                          sample_count=12, avg_return_pct=1.0, win_rate_pct=48.0)

    def test_compute_returns_report(self):
        from src.backtest.aggregators.ranking_effectiveness import RankingEffectivenessCalculator
        from src.backtest.repositories.summary_repo import SummaryRepository
        summaries = SummaryRepository(self.db).get_by_run("run-rank")
        report = RankingEffectivenessCalculator.compute(summaries)
        self.assertIsNotNone(report)
        self.assertGreater(len(report.comparisons), 0)

    def test_pool_level_leader_outperforms_watchlist(self):
        from src.backtest.aggregators.ranking_effectiveness import RankingEffectivenessCalculator
        from src.backtest.repositories.summary_repo import SummaryRepository
        summaries = SummaryRepository(self.db).get_by_run("run-rank")
        report = RankingEffectivenessCalculator.compute(summaries)
        pool_comps = [c for c in report.comparisons
                      if c.dimension == "candidate_pool_level"
                      and c.tier_high == "leader_pool" and c.tier_low == "watchlist"]
        self.assertEqual(len(pool_comps), 1)
        self.assertTrue(pool_comps[0].is_effective)
        self.assertAlmostEqual(pool_comps[0].excess_return_pct, 6.0)

    def test_theme_position_main_outperforms_non(self):
        from src.backtest.aggregators.ranking_effectiveness import RankingEffectivenessCalculator
        from src.backtest.repositories.summary_repo import SummaryRepository
        summaries = SummaryRepository(self.db).get_by_run("run-rank")
        report = RankingEffectivenessCalculator.compute(summaries)
        theme_comps = [c for c in report.comparisons
                       if c.dimension == "theme_position"
                       and c.tier_high == "main_theme" and c.tier_low == "non_theme"]
        self.assertEqual(len(theme_comps), 1)
        self.assertTrue(theme_comps[0].is_effective)

    def test_maturity_high_outperforms_low(self):
        from src.backtest.aggregators.ranking_effectiveness import RankingEffectivenessCalculator
        from src.backtest.repositories.summary_repo import SummaryRepository
        summaries = SummaryRepository(self.db).get_by_run("run-rank")
        report = RankingEffectivenessCalculator.compute(summaries)
        mat_comps = [c for c in report.comparisons
                     if c.dimension == "entry_maturity"
                     and c.tier_high == "HIGH" and c.tier_low == "LOW"]
        self.assertEqual(len(mat_comps), 1)
        self.assertTrue(mat_comps[0].is_effective)
        self.assertAlmostEqual(mat_comps[0].excess_return_pct, 5.0)

    def test_overall_effectiveness_ratio(self):
        """All tiers should be effective → ratio = 1.0."""
        from src.backtest.aggregators.ranking_effectiveness import RankingEffectivenessCalculator
        from src.backtest.repositories.summary_repo import SummaryRepository
        summaries = SummaryRepository(self.db).get_by_run("run-rank")
        report = RankingEffectivenessCalculator.compute(summaries)
        self.assertAlmostEqual(report.overall_effectiveness_ratio, 1.0)

    def test_excess_return_leader_vs_watchlist(self):
        """excess_return_pct = leader(5%) - watchlist(-1%) = 6%."""
        from src.backtest.aggregators.ranking_effectiveness import RankingEffectivenessCalculator
        from src.backtest.repositories.summary_repo import SummaryRepository
        summaries = SummaryRepository(self.db).get_by_run("run-rank")
        report = RankingEffectivenessCalculator.compute(summaries)
        self.assertAlmostEqual(report.excess_return_pct, 6.0)

    def test_ranking_consistency(self):
        """All comparisons effective → consistency = 1.0."""
        from src.backtest.aggregators.ranking_effectiveness import RankingEffectivenessCalculator
        from src.backtest.repositories.summary_repo import SummaryRepository
        summaries = SummaryRepository(self.db).get_by_run("run-rank")
        report = RankingEffectivenessCalculator.compute(summaries)
        self.assertAlmostEqual(report.ranking_consistency, 1.0)

    def test_top_k_hit_rate(self):
        """leader_pool wins / total wins across pool levels."""
        from src.backtest.aggregators.ranking_effectiveness import RankingEffectivenessCalculator
        from src.backtest.repositories.summary_repo import SummaryRepository
        summaries = SummaryRepository(self.db).get_by_run("run-rank")
        report = RankingEffectivenessCalculator.compute(summaries)
        # leader: 20*0.65=13 wins, focus: 30*0.55=16.5, watchlist: 40*0.35=14
        # top_k = 13 / (13+16.5+14) = 13/43.5 ≈ 0.2989
        self.assertIsNotNone(report.top_k_hit_rate)
        self.assertAlmostEqual(report.top_k_hit_rate, 0.2989, places=3)


if __name__ == "__main__":
    unittest.main()
