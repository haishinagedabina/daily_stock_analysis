# -*- coding: utf-8 -*-
"""Tests for simplified sector leader detection rules."""

import unittest
from datetime import date

import pandas as pd

from src.services.sector_heat_engine import SectorHeatEngine


class _FakeDB:
    def list_active_boards_with_member_count(self, market: str, min_member_count: int):
        return [{"board_name": "AI", "board_type": "concept"}]

    def batch_get_board_member_codes(self, board_names, market: str):
        return {"AI": ["000001", "000002", "000003", "000004", "000005"]}

    def list_sector_heat_history(self, board_name: str, end_date: date, lookback_days: int):
        return []

    def save_sector_heat_batch(self, trade_date: date, records):
        self.saved = (trade_date, records)


class SectorHeatEngineSimplifiedTestCase(unittest.TestCase):

    def setUp(self) -> None:
        self.engine = SectorHeatEngine(db_manager=_FakeDB())

    def test_leader_candidate_count_counts_limit_up_stocks_only(self) -> None:
        snapshot_df = pd.DataFrame([
            {"code": "000001", "pct_chg": 10.0, "close": 10.0, "ma20": 9.0, "ma60": 8.0, "is_limit_up": True, "circ_mv": 12_000_000_000},
            {"code": "000002", "pct_chg": 10.0, "close": 10.0, "ma20": 9.0, "ma60": 8.0, "is_limit_up": True, "circ_mv": 5_000_000_000},
            {"code": "000003", "pct_chg": 7.0, "close": 10.0, "ma20": 9.0, "ma60": 8.0, "is_limit_up": False, "circ_mv": 2_000_000_000},
            {"code": "000004", "pct_chg": 3.0, "close": 10.0, "ma20": 9.0, "ma60": 8.0, "is_limit_up": False, "circ_mv": 1_000_000_000},
            {"code": "000005", "pct_chg": 1.0, "close": 10.0, "ma20": 9.0, "ma60": 8.0, "is_limit_up": False, "circ_mv": None},
        ])

        results = self.engine.compute_all_sectors(snapshot_df, date(2026, 4, 13))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].leader_candidate_count, 2)
        self.assertEqual(results[0].leader_codes[:2], ["000002", "000001"])
