# -*- coding: utf-8 -*-
"""
TDD RED 阶段：DailySectorHeat ORM + 3 个查询方法的单元测试。

测试目标：
1. DailySectorHeat 表创建 & CRUD
2. list_active_boards_with_member_count() — 列出活跃板块及成员数
3. batch_get_board_member_codes() — 板块→股票反向查询
4. list_sector_heat_history() — 多日热度历史查询
5. save_sector_heat_batch() — 批量写入热度数据
6. 唯一约束 (trade_date, board_name) 去重
7. 冷启动场景（空表查询不报错）
"""

import json
import os
import tempfile
import unittest
from datetime import date, datetime

from sqlalchemy import inspect

from src.config import Config
from src.storage import DatabaseManager


class DailySectorHeatModelTestCase(unittest.TestCase):
    """DailySectorHeat ORM 模型表创建与基础 CRUD 测试。"""

    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "sector_heat.db")
        os.environ["DATABASE_PATH"] = self._db_path
        Config.reset_instance()
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("DATABASE_PATH", None)
        self._temp_dir.cleanup()

    def test_daily_sector_heat_table_created(self) -> None:
        """表应在 DatabaseManager 初始化时自动创建。"""
        table_names = set(inspect(self.db._engine).get_table_names())
        self.assertIn("daily_sector_heat", table_names)

    def test_daily_sector_heat_columns_exist(self) -> None:
        """验证所有关键列存在。"""
        inspector = inspect(self.db._engine)
        columns = {col["name"] for col in inspector.get_columns("daily_sector_heat")}
        expected_columns = {
            "id", "trade_date", "board_name", "board_type",
            "breadth_score", "strength_score", "persistence_score", "leadership_score",
            "sector_hot_score",
            "sector_status", "sector_stage",
            "stock_count", "up_count", "limit_up_count", "avg_pct_chg",
            "leader_codes_json", "front_codes_json",
            "reason", "created_at",
        }
        for col in expected_columns:
            self.assertIn(col, columns, f"缺少列: {col}")

    def test_save_and_query_sector_heat(self) -> None:
        """基础写入 + 读取验证。"""
        heat_data = [
            {
                "trade_date": date(2026, 3, 28),
                "board_name": "白酒",
                "board_type": "industry",
                "breadth_score": 0.65,
                "strength_score": 0.72,
                "persistence_score": 0.45,
                "leadership_score": 0.80,
                "sector_hot_score": 66.5,
                "sector_status": "hot",
                "sector_stage": "expand",
                "stock_count": 30,
                "up_count": 25,
                "limit_up_count": 3,
                "avg_pct_chg": 3.5,
                "leader_codes_json": json.dumps(["600519", "000858"]),
                "front_codes_json": json.dumps(["600519", "000858", "002304"]),
                "reason": "板块涨幅居前，龙头贵州茅台涨停",
            },
        ]
        saved = self.db.save_sector_heat_batch(date(2026, 3, 28), heat_data)
        self.assertEqual(saved, 1)

        history = self.db.list_sector_heat_history(
            board_name="白酒",
            end_date=date(2026, 3, 28),
            lookback_days=5,
        )
        self.assertEqual(len(history), 1)
        self.assertAlmostEqual(history[0]["sector_hot_score"], 66.5, places=1)
        self.assertEqual(history[0]["sector_status"], "hot")

    def test_unique_constraint_trade_date_board_name(self) -> None:
        """同一 (trade_date, board_name) 写入两次应覆盖，不报错。"""
        heat_v1 = [
            {
                "trade_date": date(2026, 3, 28),
                "board_name": "锂电池",
                "board_type": "concept",
                "sector_hot_score": 50.0,
                "sector_status": "warm",
            },
        ]
        heat_v2 = [
            {
                "trade_date": date(2026, 3, 28),
                "board_name": "锂电池",
                "board_type": "concept",
                "sector_hot_score": 75.0,
                "sector_status": "hot",
            },
        ]
        self.db.save_sector_heat_batch(date(2026, 3, 28), heat_v1)
        self.db.save_sector_heat_batch(date(2026, 3, 28), heat_v2)

        history = self.db.list_sector_heat_history(
            board_name="锂电池",
            end_date=date(2026, 3, 28),
            lookback_days=1,
        )
        self.assertEqual(len(history), 1)
        self.assertAlmostEqual(history[0]["sector_hot_score"], 75.0, places=1)


class ListActiveBoardsTestCase(unittest.TestCase):
    """list_active_boards_with_member_count() 测试。"""

    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "boards_count.db")
        os.environ["DATABASE_PATH"] = self._db_path
        Config.reset_instance()
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()
        self._seed_boards_and_memberships()

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("DATABASE_PATH", None)
        self._temp_dir.cleanup()

    def _seed_boards_and_memberships(self) -> None:
        """写入测试数据：3 个板块，若干股票归属。"""
        self.db.upsert_instruments(
            [
                {"code": "600519", "name": "贵州茅台", "market": "cn", "listing_status": "active", "is_st": False},
                {"code": "000858", "name": "五粮液", "market": "cn", "listing_status": "active", "is_st": False},
                {"code": "002304", "name": "洋河股份", "market": "cn", "listing_status": "active", "is_st": False},
                {"code": "300750", "name": "宁德时代", "market": "cn", "listing_status": "active", "is_st": False},
                {"code": "002812", "name": "恩捷股份", "market": "cn", "listing_status": "active", "is_st": False},
            ]
        )
        self.db.upsert_boards(
            [
                {"board_name": "白酒", "board_type": "industry", "market": "cn", "source": "efinance"},
                {"board_name": "锂电池", "board_type": "concept", "market": "cn", "source": "efinance"},
                {"board_name": "冷门板块", "board_type": "concept", "market": "cn", "source": "efinance"},
            ]
        )
        # 白酒：3 只股票
        for code in ["600519", "000858", "002304"]:
            self.db.replace_instrument_board_memberships(
                instrument_code=code,
                memberships=[{"board_name": "白酒", "board_type": "industry", "market": "cn", "source": "efinance"}],
            )
        # 锂电池：2 只股票
        for code in ["300750", "002812"]:
            self.db.replace_instrument_board_memberships(
                instrument_code=code,
                memberships=[{"board_name": "锂电池", "board_type": "concept", "market": "cn", "source": "efinance"}],
            )
        # 冷门板块：0 只股票（无归属）

    def test_returns_boards_with_member_counts(self) -> None:
        """应返回所有活跃板块及其成员数。"""
        result = self.db.list_active_boards_with_member_count(market="cn")
        board_map = {item["board_name"]: item["member_count"] for item in result}
        self.assertEqual(board_map["白酒"], 3)
        self.assertEqual(board_map["锂电池"], 2)

    def test_min_member_count_filter(self) -> None:
        """min_member_count=3 应过滤掉成员不足 3 的板块。"""
        result = self.db.list_active_boards_with_member_count(market="cn", min_member_count=3)
        board_names = [item["board_name"] for item in result]
        self.assertIn("白酒", board_names)
        self.assertNotIn("锂电池", board_names)
        self.assertNotIn("冷门板块", board_names)

    def test_board_type_filter(self) -> None:
        """按 board_type 过滤。"""
        result = self.db.list_active_boards_with_member_count(market="cn", board_type="concept")
        board_names = [item["board_name"] for item in result]
        self.assertIn("锂电池", board_names)
        self.assertNotIn("白酒", board_names)

    def test_empty_database_returns_empty_list(self) -> None:
        """冷启动：空数据库不报错。"""
        temp_dir = tempfile.TemporaryDirectory()
        db_path = os.path.join(temp_dir.name, "empty.db")
        os.environ["DATABASE_PATH"] = db_path
        Config.reset_instance()
        DatabaseManager.reset_instance()
        db = DatabaseManager.get_instance()
        result = db.list_active_boards_with_member_count(market="cn")
        self.assertEqual(result, [])
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ["DATABASE_PATH"] = self._db_path
        Config.reset_instance()
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()
        temp_dir.cleanup()


class BatchGetBoardMemberCodesTestCase(unittest.TestCase):
    """batch_get_board_member_codes() 测试。"""

    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "board_members.db")
        os.environ["DATABASE_PATH"] = self._db_path
        Config.reset_instance()
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()
        self._seed_data()

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("DATABASE_PATH", None)
        self._temp_dir.cleanup()

    def _seed_data(self) -> None:
        self.db.upsert_instruments(
            [
                {"code": "600519", "name": "贵州茅台", "market": "cn", "listing_status": "active", "is_st": False},
                {"code": "000858", "name": "五粮液", "market": "cn", "listing_status": "active", "is_st": False},
                {"code": "300750", "name": "宁德时代", "market": "cn", "listing_status": "active", "is_st": False},
            ]
        )
        self.db.upsert_boards(
            [
                {"board_name": "白酒", "board_type": "industry", "market": "cn", "source": "efinance"},
                {"board_name": "锂电池", "board_type": "concept", "market": "cn", "source": "efinance"},
            ]
        )
        for code in ["600519", "000858"]:
            self.db.replace_instrument_board_memberships(
                instrument_code=code,
                memberships=[{"board_name": "白酒", "board_type": "industry", "market": "cn", "source": "efinance"}],
            )
        self.db.replace_instrument_board_memberships(
            instrument_code="300750",
            memberships=[{"board_name": "锂电池", "board_type": "concept", "market": "cn", "source": "efinance"}],
        )

    def test_returns_codes_per_board(self) -> None:
        """白酒应返回 2 只股票，锂电池应返回 1 只。"""
        result = self.db.batch_get_board_member_codes(["白酒", "锂电池"], market="cn")
        self.assertEqual(sorted(result["白酒"]), ["000858", "600519"])
        self.assertEqual(result["锂电池"], ["300750"])

    def test_unknown_board_returns_empty(self) -> None:
        """查询不存在的板块应返回空列表。"""
        result = self.db.batch_get_board_member_codes(["不存在板块"], market="cn")
        self.assertEqual(result["不存在板块"], [])

    def test_empty_input_returns_empty(self) -> None:
        """空输入不报错，返回空字典。"""
        result = self.db.batch_get_board_member_codes([], market="cn")
        self.assertEqual(result, {})

    def test_multiple_boards_batch(self) -> None:
        """批量查询多个板块，结果互不干扰。"""
        result = self.db.batch_get_board_member_codes(["白酒", "锂电池", "不存在"], market="cn")
        self.assertEqual(len(result), 3)
        self.assertEqual(len(result["白酒"]), 2)
        self.assertEqual(len(result["锂电池"]), 1)
        self.assertEqual(result["不存在"], [])


class ListSectorHeatHistoryTestCase(unittest.TestCase):
    """list_sector_heat_history() 测试。"""

    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "heat_history.db")
        os.environ["DATABASE_PATH"] = self._db_path
        Config.reset_instance()
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("DATABASE_PATH", None)
        self._temp_dir.cleanup()

    def _seed_multi_day_heat(self) -> None:
        """写入 7 天的板块热度数据。"""
        for day_offset in range(7):
            trade_date = date(2026, 3, 22 + day_offset)  # 3/22 ~ 3/28
            self.db.save_sector_heat_batch(
                trade_date,
                [
                    {
                        "trade_date": trade_date,
                        "board_name": "白酒",
                        "board_type": "industry",
                        "sector_hot_score": 50.0 + day_offset * 5,  # 50, 55, 60, 65, 70, 75, 80
                        "sector_status": "warm" if day_offset < 4 else "hot",
                        "sector_stage": "ferment" if day_offset < 4 else "expand",
                    },
                ],
            )

    def test_lookback_5_days(self) -> None:
        """查询最近 5 天，应返回 5 条记录。"""
        self._seed_multi_day_heat()
        history = self.db.list_sector_heat_history(
            board_name="白酒",
            end_date=date(2026, 3, 28),
            lookback_days=5,
        )
        self.assertEqual(len(history), 5)
        # 按日期升序排列
        dates = [h["trade_date"] for h in history]
        self.assertEqual(dates, sorted(dates))
        # 最后一条是 3/28
        self.assertEqual(history[-1]["trade_date"], date(2026, 3, 28))

    def test_lookback_exceeds_available_data(self) -> None:
        """lookback_days > 实际数据天数，应返回所有可用数据。"""
        self._seed_multi_day_heat()
        history = self.db.list_sector_heat_history(
            board_name="白酒",
            end_date=date(2026, 3, 28),
            lookback_days=30,
        )
        self.assertEqual(len(history), 7)

    def test_cold_start_empty_table(self) -> None:
        """冷启动：空表查询不报错，返回空列表。"""
        history = self.db.list_sector_heat_history(
            board_name="白酒",
            end_date=date(2026, 3, 28),
            lookback_days=5,
        )
        self.assertEqual(history, [])

    def test_board_name_isolation(self) -> None:
        """不同板块的数据互相隔离。"""
        self._seed_multi_day_heat()
        # 另加锂电池数据
        self.db.save_sector_heat_batch(
            date(2026, 3, 28),
            [{"trade_date": date(2026, 3, 28), "board_name": "锂电池", "board_type": "concept", "sector_hot_score": 40.0, "sector_status": "neutral"}],
        )
        history = self.db.list_sector_heat_history(
            board_name="锂电池",
            end_date=date(2026, 3, 28),
            lookback_days=5,
        )
        self.assertEqual(len(history), 1)
        self.assertAlmostEqual(history[0]["sector_hot_score"], 40.0, places=1)

    def test_history_returns_all_score_fields(self) -> None:
        """验证返回字典包含四维分数和状态字段。"""
        self.db.save_sector_heat_batch(
            date(2026, 3, 28),
            [
                {
                    "trade_date": date(2026, 3, 28),
                    "board_name": "白酒",
                    "board_type": "industry",
                    "breadth_score": 0.65,
                    "strength_score": 0.72,
                    "persistence_score": 0.45,
                    "leadership_score": 0.80,
                    "sector_hot_score": 66.5,
                    "sector_status": "hot",
                    "sector_stage": "expand",
                    "stock_count": 30,
                    "up_count": 25,
                    "limit_up_count": 3,
                    "avg_pct_chg": 3.5,
                    "leader_codes_json": json.dumps(["600519"]),
                    "front_codes_json": json.dumps(["600519", "000858"]),
                    "reason": "test reason",
                },
            ],
        )
        history = self.db.list_sector_heat_history("白酒", date(2026, 3, 28), lookback_days=1)
        record = history[0]
        expected_keys = {
            "trade_date", "board_name", "board_type",
            "breadth_score", "strength_score", "persistence_score", "leadership_score",
            "sector_hot_score", "sector_status", "sector_stage",
            "stock_count", "up_count", "limit_up_count", "avg_pct_chg",
            "leader_codes_json", "front_codes_json", "reason",
        }
        for key in expected_keys:
            self.assertIn(key, record, f"返回字典缺少键: {key}")
        self.assertAlmostEqual(record["breadth_score"], 0.65, places=2)
        self.assertAlmostEqual(record["leadership_score"], 0.80, places=2)
        self.assertEqual(record["stock_count"], 30)


if __name__ == "__main__":
    unittest.main()
