# -*- coding: utf-8 -*-
"""
L2 题材聚合服务 — 将 SectorHeatResult 列表聚合为题材级结果。

职责:
  - 每个板块暂时视为独立题材（MVP 简化，后续用 ThemeMappingRegistry 合并）
  - 输出 ThemeAggregateResult 含 theme_score / status_rollup / stage_rollup
  - 不做 per-stock 判定（由 ThemePositionResolver 负责）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from src.services.sector_heat_engine import SectorHeatResult

logger = logging.getLogger(__name__)

# ── 状态阈值 ────────────────────────────────────────────────────────────────
HOT_THEME_THRESHOLD = 70.0
WARM_THEME_THRESHOLD = 50.0
NEUTRAL_THEME_THRESHOLD = 30.0


@dataclass
class ThemeAggregateResult:
    """题材级聚合结果。"""
    theme_tag: str
    theme_score: float = 0.0
    related_sectors: List[str] = field(default_factory=list)
    primary_sector: str = ""
    sector_status_rollup: str = "neutral"
    sector_stage_rollup: str = "ferment"
    theme_reason: str = ""
    debug_info: dict = field(default_factory=dict)


class ThemeAggregationService:
    """L2 题材聚合。MVP: 板块 1:1 映射为题材。"""

    def aggregate(self, sector_results: List[SectorHeatResult]) -> List[ThemeAggregateResult]:
        if not sector_results:
            return []

        results: List[ThemeAggregateResult] = []
        for sector in sector_results:
            theme_score = sector.sector_hot_score
            status_rollup = self._classify_status(theme_score)
            stage_rollup = sector.sector_stage

            results.append(ThemeAggregateResult(
                theme_tag=sector.board_name,
                theme_score=theme_score,
                related_sectors=[sector.board_name],
                primary_sector=sector.board_name,
                sector_status_rollup=status_rollup,
                sector_stage_rollup=stage_rollup,
                theme_reason=f"score={theme_score:.1f} status={status_rollup} stage={stage_rollup}",
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
