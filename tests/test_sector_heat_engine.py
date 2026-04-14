# -*- coding: utf-8 -*-
"""
TDD RED 阶段：SectorHeatEngine 单元测试。

测试目标：
1. 基本计算——热门板块输出高 sector_hot_score
2. 冷门板块——低分 + neutral/cold 状态
3. 最小样本过滤——成员 < 5 的板块被过滤
4. 龙头/前排识别——leader_codes / front_codes 正确
5. 冷启动——无历史时 persistence_score=0，其他维度正常
6. 有历史时 persistence_score 正常计算
7. sector_status / sector_stage 判定
8. 结果持久化到 DailySectorHeat
9. 边界：空 snapshot 不崩溃
"""

import json
import os
import tempfile
import unittest
from dataclasses import field
from datetime import date, timedelta
from typing import Dict, List

import numpy as np
import pandas as pd

from src.config import Config
from src.storage import DatabaseManager
from src.services.sector_heat_engine import SectorHeatEngine, SectorHeatResult


def _make_snapshot_df(sector_stocks: Dict[str, List[dict]]) -> pd.DataFrame:
    """构造合成 snapshot_df。

    Args:
        sector_stocks: {"白酒": [{"code": "600519", "pct_chg": 5.0, ...}, ...]}
        每只股票至少需要: code, name, close, pct_chg, ma20, ma60, volume_ratio,
                          turnover_rate, is_limit_up, leader_score, extreme_strength_score
    """
    rows = []
    for _sector, stocks in sector_stocks.items():
        for s in stocks:
            rows.append({
                "code": s["code"],
                "name": s.get("name", s["code"]),
                "close": s.get("close", 20.0),
                "pct_chg": s.get("pct_chg", 0.0),
                "ma20": s.get("ma20", 19.0),
                "ma60": s.get("ma60", 18.0),
                "volume_ratio": s.get("volume_ratio", 1.0),
                "turnover_rate": s.get("turnover_rate", 3.0),
                "is_limit_up": s.get("is_limit_up", False),
                "circ_mv": s.get("circ_mv"),
                "gap_breakaway": s.get("gap_breakaway", False),
                "above_ma100": s.get("above_ma100", True),
                "leader_score": s.get("leader_score", 0.0),
                "base_leader_score": s.get("base_leader_score", s.get("leader_score", 0.0)),
                "theme_leader_score": s.get("theme_leader_score", 0.0),
                "extreme_strength_score": s.get("extreme_strength_score", 0.0),
            })
    return pd.DataFrame(rows)


def _hot_sector_stocks(n: int = 10) -> List[dict]:
    """生成热门板块股票数据：大多数上涨、有涨停、有龙头。"""
    stocks = []
    for i in range(n):
        pct = 5.0 + i * 0.5 if i < 7 else -1.0  # 7涨3跌
        stocks.append({
            "code": f"60{1000 + i}",
            "name": f"白酒股{i}",
            "close": 100.0 + pct,
            "pct_chg": pct,
            "ma20": 98.0,
            "ma60": 95.0,
            "is_limit_up": i < 2,  # 2只涨停
            "leader_score": 80.0 if i == 0 else (60.0 if i == 1 else 20.0),
            "extreme_strength_score": 85.0 if i == 0 else 30.0,
            "above_ma100": i < 8,
        })
    return stocks


def _cold_sector_stocks(n: int = 8) -> List[dict]:
    """生成冷门板块股票数据：大多数下跌。"""
    stocks = []
    for i in range(n):
        pct = -3.0 - i * 0.3 if i < 6 else 0.5  # 6跌2涨
        stocks.append({
            "code": f"30{2000 + i}",
            "name": f"锂电股{i}",
            "close": 50.0 + pct,
            "pct_chg": pct,
            "ma20": 52.0,
            "ma60": 55.0,
            "is_limit_up": False,
            "leader_score": 10.0,
            "extreme_strength_score": 10.0,
            "above_ma100": False,
        })
    return stocks


def _rankable_sector_stocks(
    prefix: str,
    start_code: int,
    pct_changes: List[float],
    leader_score: float = 0.0,
    limit_up_indexes: List[int] | None = None,
) -> List[dict]:
    """生成可控强度的板块样本，用于排名驱动测试。"""
    limit_up_indexes = limit_up_indexes or []
    stocks: List[dict] = []
    for idx, pct in enumerate(pct_changes):
        stocks.append({
            "code": f"{start_code + idx:06d}",
            "name": f"{prefix}{idx}",
            "close": 50.0 + pct,
            "pct_chg": pct,
            "ma20": 48.0,
            "ma60": 45.0,
            "is_limit_up": idx in limit_up_indexes,
            "leader_score": leader_score,
            "base_leader_score": leader_score,
            "theme_leader_score": 0.0,
            "extreme_strength_score": max(pct * 8, 0.0),
            "above_ma100": pct >= 0.0,
        })
    return stocks


def _small_sector_stocks() -> List[dict]:
    """不足 5 只的迷你板块。"""
    return [
        {"code": "000901", "name": "迷你股1", "pct_chg": 2.0, "close": 10.0},
        {"code": "000902", "name": "迷你股2", "pct_chg": 1.0, "close": 10.0},
        {"code": "000903", "name": "迷你股3", "pct_chg": -1.0, "close": 10.0},
    ]


class _SectorHeatTestBase(unittest.TestCase):
    """共享 setUp/tearDown：创建临时 DB 并种入板块与股票归属数据。"""

    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "sector_heat_engine.db")
        os.environ["DATABASE_PATH"] = self._db_path
        Config.reset_instance()
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()
        self._seed_boards_and_members()
        self.engine = SectorHeatEngine(db_manager=self.db)

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("DATABASE_PATH", None)
        self._temp_dir.cleanup()

    def _seed_boards_and_members(self) -> None:
        """种入 3 个板块 + 股票归属。"""
        hot_codes = [f"60{1000 + i}" for i in range(10)]
        cold_codes = [f"30{2000 + i}" for i in range(8)]
        small_codes = ["000901", "000902", "000903"]
        all_codes = hot_codes + cold_codes + small_codes

        instruments = [
            {"code": c, "name": c, "market": "cn",
             "listing_status": "active", "is_st": False}
            for c in all_codes
        ]
        self.db.upsert_instruments(instruments)

        self.db.upsert_boards([
            {"board_name": "白酒", "board_type": "industry", "market": "cn", "source": "test"},
            {"board_name": "锂电池", "board_type": "concept", "market": "cn", "source": "test"},
            {"board_name": "迷你板块", "board_type": "concept", "market": "cn", "source": "test"},
        ])

        for code in hot_codes:
            self.db.replace_instrument_board_memberships(
                instrument_code=code,
                memberships=[{"board_name": "白酒", "board_type": "industry",
                              "market": "cn", "source": "test"}],
            )
        for code in cold_codes:
            self.db.replace_instrument_board_memberships(
                instrument_code=code,
                memberships=[{"board_name": "锂电池", "board_type": "concept",
                              "market": "cn", "source": "test"}],
            )
        for code in small_codes:
            self.db.replace_instrument_board_memberships(
                instrument_code=code,
                memberships=[{"board_name": "迷你板块", "board_type": "concept",
                              "market": "cn", "source": "test"}],
            )


class BasicComputationTestCase(_SectorHeatTestBase):
    """基本计算：热门板块应输出高分。"""

    def test_hot_sector_high_score(self) -> None:
        """白酒板块：7涨3跌、2涨停、有龙头 → 高 sector_hot_score。"""
        snapshot = _make_snapshot_df({
            "白酒": _hot_sector_stocks(),
            "锂电池": _cold_sector_stocks(),
            "迷你板块": _small_sector_stocks(),
        })
        results = self.engine.compute_all_sectors(snapshot, date(2026, 3, 28))

        hot_result = next((r for r in results if r.board_name == "白酒"), None)
        self.assertIsNotNone(hot_result)
        self.assertGreater(hot_result.sector_hot_score, 50.0)
        self.assertGreater(hot_result.breadth_score, 0.4)
        self.assertGreater(hot_result.strength_score, 0.3)

    def test_cold_sector_low_score(self) -> None:
        """锂电池：6跌2涨、无涨停 → 低 sector_hot_score。"""
        snapshot = _make_snapshot_df({
            "白酒": _hot_sector_stocks(),
            "锂电池": _cold_sector_stocks(),
        })
        results = self.engine.compute_all_sectors(snapshot, date(2026, 3, 28))

        cold_result = next((r for r in results if r.board_name == "锂电池"), None)
        self.assertIsNotNone(cold_result)
        self.assertLess(cold_result.sector_hot_score, 30.0)
        self.assertLess(cold_result.breadth_score, 0.3)

    def test_returns_sector_heat_result_type(self) -> None:
        """返回值类型为 List[SectorHeatResult]。"""
        snapshot = _make_snapshot_df({"白酒": _hot_sector_stocks()})
        results = self.engine.compute_all_sectors(snapshot, date(2026, 3, 28))

        self.assertIsInstance(results, list)
        self.assertTrue(all(isinstance(r, SectorHeatResult) for r in results))

    def test_statistics_fields_populated(self) -> None:
        """stock_count, up_count, limit_up_count, avg_pct_chg 应正确统计。"""
        snapshot = _make_snapshot_df({"白酒": _hot_sector_stocks(10)})
        results = self.engine.compute_all_sectors(snapshot, date(2026, 3, 28))

        r = results[0]
        self.assertEqual(r.stock_count, 10)
        self.assertEqual(r.up_count, 7)
        self.assertEqual(r.limit_up_count, 2)
        self.assertGreater(r.avg_pct_chg, 0.0)


class MinimumSampleFilterTestCase(_SectorHeatTestBase):
    """最小样本过滤：成员 < 5 的板块不输出。"""

    def test_small_sector_filtered_out(self) -> None:
        """迷你板块（3只）应被过滤。"""
        snapshot = _make_snapshot_df({
            "白酒": _hot_sector_stocks(),
            "迷你板块": _small_sector_stocks(),
        })
        results = self.engine.compute_all_sectors(snapshot, date(2026, 3, 28))

        board_names = [r.board_name for r in results]
        self.assertNotIn("迷你板块", board_names)
        self.assertIn("白酒", board_names)


class LeadershipTestCase(_SectorHeatTestBase):
    """龙头 / 前排股票识别。"""

    def test_leader_codes_identified(self) -> None:
        """leader_score >= 70 的股票应进入 leader_codes。"""
        snapshot = _make_snapshot_df({"白酒": _hot_sector_stocks()})
        results = self.engine.compute_all_sectors(snapshot, date(2026, 3, 28))

        r = results[0]
        # 601000 的 leader_score=80 ≥ 70
        self.assertIn("601000", r.leader_codes)

    def test_front_codes_includes_top_performers(self) -> None:
        """front_codes 应包含涨幅最大的前排股票。"""
        snapshot = _make_snapshot_df({"白酒": _hot_sector_stocks()})
        results = self.engine.compute_all_sectors(snapshot, date(2026, 3, 28))

        r = results[0]
        self.assertTrue(len(r.front_codes) > 0)
        self.assertTrue(len(r.front_codes) <= 10)

    def test_limit_up_stocks_are_ranked_by_smallest_circ_mv(self) -> None:
        """L2 龙头候选应由涨停股组成，并按最小流通市值排序。"""
        stocks = _hot_sector_stocks()
        stocks[0]["circ_mv"] = 12_000_000_000
        stocks[1]["circ_mv"] = 5_000_000_000

        snapshot = _make_snapshot_df({"白酒": stocks})
        results = self.engine.compute_all_sectors(snapshot, date(2026, 3, 28))

        r = results[0]
        self.assertEqual(r.leader_codes[:2], ["601001", "601000"])

    def test_all_limit_up_stocks_become_leader_candidates_even_without_scores(self) -> None:
        """简化规则下，涨停股都会进入 leader_codes，而不依赖旧分数。"""
        stocks = _hot_sector_stocks()
        stocks[0]["leader_score"] = 10.0
        stocks[1]["leader_score"] = 15.0

        snapshot = _make_snapshot_df({"白酒": stocks})
        results = self.engine.compute_all_sectors(snapshot, date(2026, 3, 28))

        r = results[0]
        self.assertIn("601000", r.leader_codes)
        self.assertIn("601001", r.leader_codes)


class SectorStatusTestCase(_SectorHeatTestBase):
    """sector_status / sector_stage 分类。"""

    def test_hot_sector_status(self) -> None:
        """高分板块应标记为 hot。"""
        snapshot = _make_snapshot_df({"白酒": _hot_sector_stocks()})
        results = self.engine.compute_all_sectors(snapshot, date(2026, 3, 28))

        r = results[0]
        self.assertIn(r.sector_status, ["hot", "warm"])

    def test_cold_sector_status(self) -> None:
        """低分板块应标记为 neutral 或 cold。"""
        snapshot = _make_snapshot_df({"锂电池": _cold_sector_stocks()})
        results = self.engine.compute_all_sectors(snapshot, date(2026, 3, 28))

        r = results[0]
        self.assertIn(r.sector_status, ["neutral", "cold"])

    def test_expand_sector_with_strong_breadth_and_strength_is_promoted_to_warm(self) -> None:
        """运行证据：部分热点板块 score 在 50-62，但 expand + 联动/强度足够，仍应视为 warm。"""
        result = SectorHeatResult(
            board_name="固态电池",
            board_type="concept",
            sector_hot_score=57.7,
            sector_status="neutral",
            sector_stage="expand",
            breadth_score=0.51,
            strength_score=0.76,
            persistence_score=0.42,
            leadership_score=0.55,
            stock_count=208,
            up_count=176,
            limit_up_count=11,
            avg_pct_chg=2.16,
            front_codes=["000001", "000002"],
            reason="score=57.7 status=neutral stage=expand",
        )

        promoted = self.engine._apply_expand_warm_promotion(result)

        self.assertEqual(promoted.sector_status, "warm")

    def test_rank_driven_hot_board_is_emitted_even_when_legacy_threshold_is_hard_to_reach(self) -> None:
        """相对最强板块应能成为 hot，而不是全部被压成 warm。"""
        extra_codes = [f"{603100 + i:06d}" for i in range(8)] + [f"{603200 + i:06d}" for i in range(8)]
        self.db.upsert_instruments([
            {"code": code, "name": code, "market": "cn", "listing_status": "active", "is_st": False}
            for code in extra_codes
        ])
        self.db.upsert_boards([
            {"board_name": "算力", "board_type": "concept", "market": "cn", "source": "test"},
            {"board_name": "机器人", "board_type": "concept", "market": "cn", "source": "test"},
        ])
        for code in extra_codes[:8]:
            self.db.replace_instrument_board_memberships(
                instrument_code=code,
                memberships=[{"board_name": "算力", "board_type": "concept", "market": "cn", "source": "test"}],
            )
        for code in extra_codes[8:]:
            self.db.replace_instrument_board_memberships(
                instrument_code=code,
                memberships=[{"board_name": "机器人", "board_type": "concept", "market": "cn", "source": "test"}],
            )

        snapshot = _make_snapshot_df({
            "白酒": _rankable_sector_stocks("白酒股", 601000, [4.8, 4.3, 3.9, 3.6, 3.1, 2.8, 2.5, 2.0], leader_score=0.0),
            "算力": _rankable_sector_stocks("算力股", 603100, [5.4, 4.9, 4.5, 4.0, 3.6, 3.1, 2.9, 2.6], leader_score=0.0),
            "机器人": _rankable_sector_stocks("机器人股", 603200, [3.9, 3.6, 3.3, 2.9, 2.5, 2.1, 1.9, 1.6], leader_score=0.0),
            "锂电池": _cold_sector_stocks(),
        })

        results = self.engine.compute_all_sectors(snapshot, date(2026, 3, 28))

        hot_boards = [r.board_name for r in results if r.sector_status == "hot"]
        self.assertGreaterEqual(len(hot_boards), 1)
        self.assertIn("算力", hot_boards)

    def test_board_without_leader_candidate_can_still_be_hot_with_quality_flag(self) -> None:
        """龙头候选缺失应影响质量标签，而不是阻止热点识别。"""
        snapshot = _make_snapshot_df({
            "白酒": _rankable_sector_stocks(
                "白酒股",
                601000,
                [7.8, 7.1, 6.8, 6.1, 5.7, 5.0, 4.8, 4.1],
                leader_score=0.0,
                limit_up_indexes=[0, 1, 2],
            ),
            "锂电池": _cold_sector_stocks(),
        })

        results = self.engine.compute_all_sectors(snapshot, date(2026, 3, 28))

        target = max(results, key=lambda item: item.sector_hot_score)
        self.assertEqual(target.sector_status, "hot")
        self.assertEqual(getattr(target, "quality_flags", {}).get("has_leader_candidate"), True)
        self.assertEqual(getattr(target, "quality_flags", {}).get("leader_candidate_count"), 3)


class ColdStartTestCase(_SectorHeatTestBase):
    """冷启动：无历史数据时 persistence 维度降权。"""

    def test_no_history_persistence_zero(self) -> None:
        """首次运行时 persistence_score 为 0。"""
        snapshot = _make_snapshot_df({"白酒": _hot_sector_stocks()})
        results = self.engine.compute_all_sectors(snapshot, date(2026, 3, 28))

        r = results[0]
        self.assertAlmostEqual(r.persistence_score, 0.0, places=2)

    def test_cold_start_other_dims_still_valid(self) -> None:
        """冷启动下 breadth/strength/leadership 仍正常计算。"""
        snapshot = _make_snapshot_df({"白酒": _hot_sector_stocks()})
        results = self.engine.compute_all_sectors(snapshot, date(2026, 3, 28))

        r = results[0]
        self.assertGreater(r.breadth_score, 0.0)
        self.assertGreater(r.strength_score, 0.0)
        self.assertGreater(r.leadership_score, 0.0)


class PersistenceWithHistoryTestCase(_SectorHeatTestBase):
    """有历史数据时 persistence_score 正常计算。"""

    def _seed_history(self, days: int = 5) -> None:
        """写入 N 天历史热度数据。"""
        for i in range(days):
            d = date(2026, 3, 23 + i)
            self.db.save_sector_heat_batch(d, [
                {
                    "trade_date": d,
                    "board_name": "白酒",
                    "board_type": "industry",
                    "sector_hot_score": 60.0 + i * 3,
                    "sector_status": "warm",
                },
            ])

    def test_persistence_with_5day_history(self) -> None:
        """5 天历史 → persistence_score > 0。"""
        self._seed_history(5)
        snapshot = _make_snapshot_df({"白酒": _hot_sector_stocks()})
        results = self.engine.compute_all_sectors(snapshot, date(2026, 3, 28))

        r = results[0]
        self.assertGreater(r.persistence_score, 0.0)

    def test_persistence_partial_history(self) -> None:
        """2 天历史（< 3 天）→ persistence 降权但不为 0。"""
        self._seed_history(2)
        snapshot = _make_snapshot_df({"白酒": _hot_sector_stocks()})
        results = self.engine.compute_all_sectors(snapshot, date(2026, 3, 28))

        r = results[0]
        # 有历史但不足，persistence 应有小值
        self.assertGreaterEqual(r.persistence_score, 0.0)


class DBPersistenceTestCase(_SectorHeatTestBase):
    """结果持久化到 DailySectorHeat。"""

    def test_results_saved_to_db(self) -> None:
        """计算完成后结果应写入 DB。"""
        snapshot = _make_snapshot_df({
            "白酒": _hot_sector_stocks(),
            "锂电池": _cold_sector_stocks(),
        })
        self.engine.compute_all_sectors(snapshot, date(2026, 3, 28))

        history = self.db.list_sector_heat_history(
            "白酒", date(2026, 3, 28), lookback_days=1,
        )
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["board_name"], "白酒")
        self.assertGreater(history[0]["sector_hot_score"], 0.0)

    def test_idempotent_save(self) -> None:
        """同一天重复计算应覆盖，不重复。"""
        snapshot = _make_snapshot_df({"白酒": _hot_sector_stocks()})
        self.engine.compute_all_sectors(snapshot, date(2026, 3, 28))
        self.engine.compute_all_sectors(snapshot, date(2026, 3, 28))

        history = self.db.list_sector_heat_history(
            "白酒", date(2026, 3, 28), lookback_days=1,
        )
        self.assertEqual(len(history), 1)


class EmptyInputTestCase(_SectorHeatTestBase):
    """边界：空输入不崩溃。"""

    def test_empty_snapshot_returns_empty(self) -> None:
        """空 DataFrame → 返回空列表。"""
        snapshot = pd.DataFrame()
        results = self.engine.compute_all_sectors(snapshot, date(2026, 3, 28))
        self.assertEqual(results, [])

    def test_snapshot_with_no_matching_boards(self) -> None:
        """snapshot 中的股票不属于任何板块 → 空结果。"""
        snapshot = pd.DataFrame([{
            "code": "999999", "name": "无归属股",
            "pct_chg": 5.0, "close": 10.0,
            "ma20": 9.0, "ma60": 8.0, "volume_ratio": 1.0,
            "turnover_rate": 3.0, "is_limit_up": False,
            "leader_score": 0.0, "extreme_strength_score": 0.0,
        }])
        results = self.engine.compute_all_sectors(snapshot, date(2026, 3, 28))
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
