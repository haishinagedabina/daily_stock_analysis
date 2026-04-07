# -*- coding: utf-8 -*-
"""
TDD RED 阶段：ThemeAggregationService + ThemePositionResolver 单元测试。

测试目标：
1. ThemeAggregationService — 多板块聚合为题材
2. ThemePositionResolver — per-stock theme_position 推算
3. 双通道融合（盘面 + OpenClaw）
4. 冷启动 / 非热点模式优雅降级
"""

import os
import tempfile
import unittest
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.schemas.trading_types import ThemeDecision, ThemePosition
from src.services.sector_heat_engine import SectorHeatResult
from src.services.theme_aggregation_service import (
    ThemeAggregateResult,
    ThemeAggregationService,
)
from src.services.theme_mapping_registry import ThemeMappingRegistry
from src.services.theme_position_resolver import ThemePositionResolver


def _hot_sector(name: str = "白酒", score: float = 75.0,
                status: str = "hot", stage: str = "expand") -> SectorHeatResult:
    return SectorHeatResult(
        board_name=name, board_type="industry",
        sector_hot_score=score, sector_status=status, sector_stage=stage,
        breadth_score=0.7, strength_score=0.7,
        persistence_score=0.5, leadership_score=0.6,
        stock_count=30, up_count=25, limit_up_count=3, avg_pct_chg=3.5,
        leader_codes=["600519", "000858"], front_codes=["600519", "000858", "002304"],
    )


def _warm_sector(name: str = "锂电池", score: float = 55.0) -> SectorHeatResult:
    return SectorHeatResult(
        board_name=name, board_type="concept",
        sector_hot_score=score, sector_status="warm", sector_stage="ferment",
        breadth_score=0.4, strength_score=0.4,
        stock_count=20, up_count=12, avg_pct_chg=1.5,
    )


def _cold_sector(name: str = "钢铁", score: float = 20.0) -> SectorHeatResult:
    return SectorHeatResult(
        board_name=name, board_type="industry",
        sector_hot_score=score, sector_status="cold", sector_stage="fade",
        breadth_score=0.1, strength_score=0.1,
        stock_count=15, up_count=3, avg_pct_chg=-2.0,
    )


# ── ThemeAggregationService 测试 ─────────────────────────────────────────────

class ThemeAggregationBasicTestCase(unittest.TestCase):
    """ThemeAggregationService 基本聚合。"""

    def setUp(self) -> None:
        self.service = ThemeAggregationService()

    def test_single_hot_sector_produces_theme(self) -> None:
        """单个热门板块 → 输出对应题材。"""
        sectors = [_hot_sector("白酒", 75.0)]
        results = self.service.aggregate(sectors)

        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], ThemeAggregateResult)
        self.assertGreater(results[0].theme_score, 50.0)
        self.assertEqual(results[0].primary_sector, "白酒")

    def test_multiple_sectors_multiple_themes(self) -> None:
        """多个板块 → 各自独立题材。"""
        sectors = [
            _hot_sector("白酒", 75.0),
            _warm_sector("锂电池", 55.0),
            _cold_sector("钢铁", 20.0),
        ]
        results = self.service.aggregate(sectors)

        self.assertEqual(len(results), 3)
        theme_tags = [r.theme_tag for r in results]
        self.assertIn("白酒", theme_tags)

    def test_empty_sectors_returns_empty(self) -> None:
        results = self.service.aggregate([])
        self.assertEqual(results, [])

    def test_status_rollup_from_theme_score(self) -> None:
        """theme_score ≥ 70 → hot。"""
        sectors = [_hot_sector("白酒", 80.0)]
        results = self.service.aggregate(sectors)

        self.assertEqual(results[0].sector_status_rollup, "hot")

    def test_cold_theme_status(self) -> None:
        sectors = [_cold_sector("钢铁", 20.0)]
        results = self.service.aggregate(sectors)

        self.assertIn(results[0].sector_status_rollup, ["neutral", "cold"])


# ── ThemePositionResolver 测试 ───────────────────────────────────────────────

class ThemePositionResolverBasicTestCase(unittest.TestCase):
    """ThemePositionResolver per-stock theme_position 推算。"""

    def test_hot_expand_sector_gives_main_theme(self) -> None:
        """stock 归属 hot+expand 板块 → MAIN_THEME。"""
        sectors = [_hot_sector("白酒", 75.0, status="hot", stage="expand")]
        themes = ThemeAggregationService().aggregate(sectors)

        resolver = ThemePositionResolver(
            sector_results=sectors, theme_results=themes,
        )
        decision = resolver.resolve(stock_boards=["白酒"])

        self.assertEqual(decision.theme_position, ThemePosition.MAIN_THEME)
        self.assertEqual(decision.theme_tag, "白酒")

    def test_warm_sector_gives_secondary_theme(self) -> None:
        """stock 归属 warm 板块 → SECONDARY_THEME。"""
        sectors = [_warm_sector("锂电池", 55.0)]
        themes = ThemeAggregationService().aggregate(sectors)

        resolver = ThemePositionResolver(sector_results=sectors, theme_results=themes)
        decision = resolver.resolve(stock_boards=["锂电池"])

        self.assertEqual(decision.theme_position, ThemePosition.SECONDARY_THEME)

    def test_cold_sector_gives_non_theme(self) -> None:
        """stock 归属 cold 板块 → NON_THEME。"""
        sectors = [_cold_sector("钢铁", 20.0)]
        themes = ThemeAggregationService().aggregate(sectors)

        resolver = ThemePositionResolver(sector_results=sectors, theme_results=themes)
        decision = resolver.resolve(stock_boards=["钢铁"])

        self.assertEqual(decision.theme_position, ThemePosition.NON_THEME)

    def test_fading_sector_gives_fading_theme(self) -> None:
        """hot + climax/fade → FADING_THEME。"""
        sectors = [_hot_sector("白酒", 72.0, status="hot", stage="fade")]
        themes = ThemeAggregationService().aggregate(sectors)

        resolver = ThemePositionResolver(sector_results=sectors, theme_results=themes)
        decision = resolver.resolve(stock_boards=["白酒"])

        self.assertEqual(decision.theme_position, ThemePosition.FADING_THEME)

    def test_warm_fade_sector_gives_fading_theme(self) -> None:
        """warm + fade 板块 → FADING_THEME（而非 SECONDARY_THEME）。"""
        sectors = [SectorHeatResult(
            board_name="锂电池", board_type="concept",
            sector_hot_score=55.0, sector_status="warm", sector_stage="fade",
            breadth_score=0.3, strength_score=0.3,
            stock_count=20, up_count=8, avg_pct_chg=0.5,
        )]
        themes = ThemeAggregationService().aggregate(sectors)

        resolver = ThemePositionResolver(sector_results=sectors, theme_results=themes)
        decision = resolver.resolve(stock_boards=["锂电池"])

        self.assertEqual(decision.theme_position, ThemePosition.FADING_THEME)

    def test_no_board_gives_non_theme(self) -> None:
        """stock 无板块归属 → NON_THEME。"""
        sectors = [_hot_sector("白酒")]
        themes = ThemeAggregationService().aggregate(sectors)

        resolver = ThemePositionResolver(sector_results=sectors, theme_results=themes)
        decision = resolver.resolve(stock_boards=[])

        self.assertEqual(decision.theme_position, ThemePosition.NON_THEME)

    def test_unknown_board_gives_non_theme(self) -> None:
        """stock 归属不在热度计算中的板块 → NON_THEME。"""
        sectors = [_hot_sector("白酒")]
        themes = ThemeAggregationService().aggregate(sectors)

        resolver = ThemePositionResolver(sector_results=sectors, theme_results=themes)
        decision = resolver.resolve(stock_boards=["不存在板块"])

        self.assertEqual(decision.theme_position, ThemePosition.NON_THEME)


class ThemePositionMultiBoardTestCase(unittest.TestCase):
    """多板块归属冲突处理。"""

    def test_picks_hottest_board_as_primary(self) -> None:
        """stock 同时归属 hot 和 cold 板块 → 取 hot 板块。"""
        sectors = [
            _hot_sector("白酒", 75.0, status="hot", stage="expand"),
            _cold_sector("钢铁", 20.0),
        ]
        themes = ThemeAggregationService().aggregate(sectors)

        resolver = ThemePositionResolver(sector_results=sectors, theme_results=themes)
        decision = resolver.resolve(stock_boards=["白酒", "钢铁"])

        self.assertEqual(decision.theme_position, ThemePosition.MAIN_THEME)
        self.assertEqual(decision.theme_tag, "白酒")


class ThemePositionDualChannelTestCase(unittest.TestCase):
    """双通道融合：盘面 + OpenClaw。"""

    def test_openclaw_does_not_override_cold_sector(self) -> None:
        """盘面弱 + OpenClaw 强 → NON_THEME（盘面先行原则）。"""
        sectors = [_cold_sector("钢铁", 20.0)]
        themes = ThemeAggregationService().aggregate(sectors)

        openclaw_context = {
            "钢铁": {"heat_score": 90, "match_score": 0.95},
        }

        resolver = ThemePositionResolver(
            sector_results=sectors, theme_results=themes,
            theme_context=openclaw_context,
        )
        decision = resolver.resolve(stock_boards=["钢铁"])

        self.assertEqual(decision.theme_position, ThemePosition.NON_THEME)

    def test_no_openclaw_still_works(self) -> None:
        """OpenClaw 为 None 时系统正常运行。"""
        sectors = [_hot_sector("白酒")]
        themes = ThemeAggregationService().aggregate(sectors)

        resolver = ThemePositionResolver(
            sector_results=sectors, theme_results=themes,
            theme_context=None,
        )
        decision = resolver.resolve(stock_boards=["白酒"])

        self.assertIsInstance(decision, ThemeDecision)


class ThemeDecisionFieldsTestCase(unittest.TestCase):
    """ThemeDecision 输出字段完整性。"""

    def test_decision_has_all_fields(self) -> None:
        sectors = [_hot_sector("白酒", 75.0)]
        themes = ThemeAggregationService().aggregate(sectors)

        resolver = ThemePositionResolver(sector_results=sectors, theme_results=themes)
        decision = resolver.resolve(stock_boards=["白酒"])

        self.assertIsInstance(decision.theme_tag, str)
        self.assertIsInstance(decision.theme_score, float)
        self.assertIsInstance(decision.theme_position, ThemePosition)
        self.assertIsInstance(decision.sector_strength, float)


# ── ThemeMappingRegistry 集成测试 ──────────────────────────────────────────

_INTEGRATION_YAML = """\
themes:
  - canonical_tag: "AI大模型"
    boards:
      - board_name: "AIGC概念"
        priority: 100
      - board_name: "多模态AI"
        priority: 90
  - canonical_tag: "半导体"
    boards:
      - board_name: "半导体概念"
        priority: 100
"""


def _write_temp_yaml(content: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    return path


class ThemeAggregationWithRegistryTestCase(unittest.TestCase):
    """ThemeAggregationService + ThemeMappingRegistry 集成。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls._yaml_path = _write_temp_yaml(_INTEGRATION_YAML)
        cls.registry = ThemeMappingRegistry(config_path=cls._yaml_path)

    @classmethod
    def tearDownClass(cls) -> None:
        os.unlink(cls._yaml_path)

    def test_merges_boards_with_same_tag(self) -> None:
        """两板块映射同一 canonical_tag → 合并为一个 ThemeAggregateResult。"""
        sectors = [
            _hot_sector("AIGC概念", 80.0, status="hot", stage="expand"),
            _warm_sector("多模态AI", 60.0),
        ]
        service = ThemeAggregationService(registry=self.registry)
        results = service.aggregate(sectors)

        # 应合并为一个 "AI大模型" 题材
        tags = [r.theme_tag for r in results]
        self.assertIn("AI大模型", tags)
        self.assertNotIn("AIGC概念", tags)
        self.assertNotIn("多模态AI", tags)

        ai_theme = [r for r in results if r.theme_tag == "AI大模型"][0]
        self.assertIn("AIGC概念", ai_theme.related_sectors)
        self.assertIn("多模态AI", ai_theme.related_sectors)
        self.assertEqual(ai_theme.primary_sector, "AIGC概念")  # 高分
        self.assertEqual(ai_theme.theme_score, 80.0)

    def test_unmapped_boards_pass_through(self) -> None:
        """未映射板块仍以 board_name 作为 theme_tag。"""
        sectors = [_hot_sector("白酒", 75.0)]
        service = ThemeAggregationService(registry=self.registry)
        results = service.aggregate(sectors)

        tags = [r.theme_tag for r in results]
        self.assertIn("白酒", tags)

    def test_no_registry_unchanged(self) -> None:
        """无 registry → 与原始行为一致。"""
        sectors = [
            _hot_sector("AIGC概念", 80.0),
            _warm_sector("多模态AI", 60.0),
        ]
        service = ThemeAggregationService()  # no registry
        results = service.aggregate(sectors)

        tags = [r.theme_tag for r in results]
        self.assertIn("AIGC概念", tags)
        self.assertIn("多模态AI", tags)
        self.assertEqual(len(results), 2)


class ThemePositionWithRegistryTestCase(unittest.TestCase):
    """ThemePositionResolver + ThemeMappingRegistry 集成。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls._yaml_path = _write_temp_yaml(_INTEGRATION_YAML)
        cls.registry = ThemeMappingRegistry(config_path=cls._yaml_path)

    @classmethod
    def tearDownClass(cls) -> None:
        os.unlink(cls._yaml_path)

    def test_resolver_uses_canonical_tag(self) -> None:
        """有 registry 时 theme_tag 使用 canonical_tag。"""
        sectors = [_hot_sector("AIGC概念", 80.0, status="hot", stage="expand")]
        service = ThemeAggregationService(registry=self.registry)
        themes = service.aggregate(sectors)

        resolver = ThemePositionResolver(
            sector_results=sectors, theme_results=themes,
            registry=self.registry,
        )
        decision = resolver.resolve(stock_boards=["AIGC概念"])

        self.assertEqual(decision.theme_tag, "AI大模型")
        self.assertEqual(decision.theme_position, ThemePosition.MAIN_THEME)

    def test_resolver_no_registry_uses_board_name(self) -> None:
        """无 registry 时 theme_tag = board_name（向后兼容）。"""
        sectors = [_hot_sector("AIGC概念", 80.0, status="hot", stage="expand")]
        themes = ThemeAggregationService().aggregate(sectors)

        resolver = ThemePositionResolver(
            sector_results=sectors, theme_results=themes,
        )
        decision = resolver.resolve(stock_boards=["AIGC概念"])

        self.assertEqual(decision.theme_tag, "AIGC概念")


if __name__ == "__main__":
    unittest.main()
