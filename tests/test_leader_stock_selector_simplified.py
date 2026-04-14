# -*- coding: utf-8 -*-
"""Tests for simplified leader stock selection rules."""

import unittest

from src.services.leader_stock_selector import LeaderStockSelector


class LeaderStockSelectorSimplifiedTestCase(unittest.TestCase):

    def setUp(self) -> None:
        self.selector = LeaderStockSelector()

    def test_limit_up_stock_is_preferred_over_non_limit_up_stock(self) -> None:
        leader_code, reason = self.selector.select_leader(
            theme_stocks=["000001", "000002"],
            stock_snapshots={
                "000001": {"code": "000001", "is_limit_up": True, "circ_mv": 8_000_000_000},
                "000002": {"code": "000002", "is_limit_up": False, "circ_mv": 2_000_000_000},
            },
        )

        self.assertEqual(leader_code, "000001")
        self.assertEqual(reason, "涨停且流通市值最小")

    def test_smallest_circ_mv_wins_when_multiple_limit_up_stocks_exist(self) -> None:
        leader_code, reason = self.selector.select_leader(
            theme_stocks=["000001", "000002", "000003"],
            stock_snapshots={
                "000001": {"code": "000001", "is_limit_up": True, "circ_mv": 12_000_000_000},
                "000002": {"code": "000002", "is_limit_up": True, "circ_mv": 4_000_000_000},
                "000003": {"code": "000003", "is_limit_up": True, "circ_mv": 9_000_000_000},
            },
        )

        self.assertEqual(leader_code, "000002")
        self.assertEqual(reason, "涨停且流通市值最小")

    def test_missing_circ_mv_ranks_after_known_circ_mv(self) -> None:
        leader_code, reason = self.selector.select_leader(
            theme_stocks=["000001", "000002"],
            stock_snapshots={
                "000001": {"code": "000001", "is_limit_up": True, "circ_mv": None},
                "000002": {"code": "000002", "is_limit_up": True, "circ_mv": 5_000_000_000},
            },
        )

        self.assertEqual(leader_code, "000002")
        self.assertEqual(reason, "涨停且流通市值最小")

    def test_no_limit_up_means_no_clear_leader(self) -> None:
        leader_code, reason = self.selector.select_leader(
            theme_stocks=["000001", "000002"],
            stock_snapshots={
                "000001": {"code": "000001", "is_limit_up": False, "circ_mv": 1_000_000_000},
                "000002": {"code": "000002", "is_limit_up": False, "circ_mv": 2_000_000_000},
            },
        )

        self.assertIsNone(leader_code)
        self.assertIsNone(reason)
