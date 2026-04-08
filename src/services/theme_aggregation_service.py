# -*- coding: utf-8 -*-
"""
L2 题材聚合服务 — 将 SectorHeatResult 列表聚合为题材级结果。

职责:
  - 通过 ThemeMappingRegistry 将多个相关板块合并为统一题材
  - 无 registry 时退化为 1:1 板块→题材映射（向后兼容）
  - 输出 ThemeAggregateResult 含 theme_score / status_rollup / stage_rollup
  - 不做 per-stock 判定（由 ThemePositionResolver 负责）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional

from src.services.sector_heat_engine import SectorHeatResult

if TYPE_CHECKING:
    from src.services.theme_mapping_registry import ThemeMappingRegistry

logger = logging.getLogger(__name__)

# ── 状态阈值 ────────────────────────────────────────────────────────────────
HOT_THEME_THRESHOLD = 70.0
WARM_THEME_THRESHOLD = 50.0
NEUTRAL_THEME_THRESHOLD = 30.0


# ── 技术阶段 → 交易语义映射 ──────────────────────────────────────────────────
_STAGE_TO_TRADE_STAGE = {
    "launch": "启动期",
    "ferment": "启动期",
    "expand": "加速期",
    "climax": "分歧高位",
    "fade": "退潮期",
}


@dataclass
class ThemeAggregateResult:
    """题材级聚合结果。"""
    theme_tag: str
    theme_score: float = 0.0
    related_sectors: List[str] = field(default_factory=list)
    primary_sector: str = ""
    sector_status_rollup: str = "neutral"
    sector_stage_rollup: str = "ferment"
    trade_theme_stage: str = "启动期"
    theme_reason: str = ""
    debug_info: dict = field(default_factory=dict)


class ThemeAggregationService:
    """L2 题材聚合。支持 ThemeMappingRegistry 合并板块，无 registry 时 1:1 fallback。"""

    def __init__(self, registry: Optional["ThemeMappingRegistry"] = None) -> None:
        self._registry = registry

    def aggregate(self, sector_results: List[SectorHeatResult]) -> List[ThemeAggregateResult]:
        if not sector_results:
            return []

        if self._registry is None:
            return self._aggregate_1to1(sector_results)
        return self._aggregate_with_registry(sector_results)

    # ── 无 registry: 1:1 映射（原始逻辑） ──────────────────────────────────

    def _aggregate_1to1(self, sector_results: List[SectorHeatResult]) -> List[ThemeAggregateResult]:
        results: List[ThemeAggregateResult] = []
        for sector in sector_results:
            theme_score = sector.sector_hot_score
            status_rollup = self._classify_status(theme_score)
            stage_rollup = sector.sector_stage

            trade_stage = _STAGE_TO_TRADE_STAGE.get(stage_rollup, stage_rollup)
            results.append(ThemeAggregateResult(
                theme_tag=sector.board_name,
                theme_score=theme_score,
                related_sectors=[sector.board_name],
                primary_sector=sector.board_name,
                sector_status_rollup=status_rollup,
                sector_stage_rollup=stage_rollup,
                trade_theme_stage=trade_stage,
                theme_reason=f"score={theme_score:.1f} status={status_rollup} stage={stage_rollup}",
            ))
        return sorted(results, key=lambda r: r.theme_score, reverse=True)

    # ── 有 registry: n:m 合并 ──────────────────────────────────────────────

    def _aggregate_with_registry(self, sector_results: List[SectorHeatResult]) -> List[ThemeAggregateResult]:
        assert self._registry is not None
        # 按 canonical_tag 分组
        tag_groups: Dict[str, List[SectorHeatResult]] = {}
        for sector in sector_results:
            tag = self._registry.resolve_tag(sector.board_name)
            tag_groups.setdefault(tag, []).append(sector)

        results: List[ThemeAggregateResult] = []
        for tag, sectors in tag_groups.items():
            # 取最高分板块作为 primary
            best = max(sectors, key=lambda s: s.sector_hot_score)
            theme_score = best.sector_hot_score
            status_rollup = self._classify_status(theme_score)
            stage_rollup = best.sector_stage

            trade_stage = _STAGE_TO_TRADE_STAGE.get(stage_rollup, stage_rollup)
            results.append(ThemeAggregateResult(
                theme_tag=tag,
                theme_score=theme_score,
                related_sectors=[s.board_name for s in sectors],
                primary_sector=best.board_name,
                sector_status_rollup=status_rollup,
                sector_stage_rollup=stage_rollup,
                trade_theme_stage=trade_stage,
                theme_reason=f"score={theme_score:.1f} status={status_rollup} stage={stage_rollup} merged={len(sectors)}",
                debug_info={"constituent_scores": {s.board_name: s.sector_hot_score for s in sectors}},
            ))

        return sorted(results, key=lambda r: r.theme_score, reverse=True)

    def _classify_status(self, theme_score: float) -> str:
        if theme_score >= HOT_THEME_THRESHOLD:
            return "hot"
        if theme_score >= WARM_THEME_THRESHOLD:
            return "warm"
        if theme_score >= NEUTRAL_THEME_THRESHOLD:
            return "neutral"
        return "cold"
