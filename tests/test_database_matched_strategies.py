# -*- coding: utf-8 -*-
"""TDD: Test that database correctly stores and retrieves matched_strategies."""

import pytest
import pandas as pd
from src.services.screening_task_service import ScreeningTaskService
from src.storage import DatabaseManager


class TestDatabaseMatchedStrategies:
    """Test matched_strategies persistence in database."""

    def test_database_stores_only_filtered_strategies(self):
        """RED: Database should only store extreme_strength_combo when that's the only strategy used."""
        # Setup
        db = DatabaseManager()

        # Create a screening run with only extreme_strength_combo
        run_id = "test_run_extreme_only"

        # Create screening run first (required for foreign key)
        from datetime import date
        db.create_screening_run(
            run_id=run_id,
            trade_date=date.today(),
            market="A",
            config_snapshot={"mode": "balanced"},
        )

        # Mock candidate data
        candidates = [
            {
                "code": "301292",
                "name": "海科新源",
                "rank": 1,
                "rule_score": 85.0,
                "selected_for_ai": False,
                "matched_strategies": ["extreme_strength_combo"],  # Only this strategy
                "rule_hits": ["is_hot_theme_stock", "above_ma100"],
                "factor_snapshot": {
                    "is_hot_theme_stock": True,
                    "above_ma100": True,
                    "extreme_strength_score": 85.0,
                },
            }
        ]

        # Save to database
        db.save_screening_candidates(run_id=run_id, candidates=candidates)

        # Retrieve from database
        retrieved = db.list_screening_candidates(run_id=run_id, limit=10)

        # Verify
        assert len(retrieved) == 1, f"Expected 1 candidate, got {len(retrieved)}"
        candidate = retrieved[0]
        assert candidate["matched_strategies"] == ["extreme_strength_combo"], \
            f"Expected only ['extreme_strength_combo'], got {candidate['matched_strategies']}"

        # Cleanup
        db.delete_screening_run(run_id)
