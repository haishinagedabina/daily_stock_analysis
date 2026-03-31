# -*- coding: utf-8 -*-
"""
L2 题材地位解析 — per-stock theme_position 推算 + 双通道融合。

构造函数注入上下文（sector_results / theme_results / theme_context），
resolve(stock_boards) 处理单只股票。

盘面先行原则:
  盘面强 + OpenClaw 强 → MAIN_THEME
  盘面强 + OpenClaw 弱/无 → SECONDARY_THEME（或由盘面独立判定）
  盘面弱 + OpenClaw 强 → NON_THEME
  盘面弱 + OpenClaw 弱 → NON_THEME
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from src.schemas.trading_types import ThemeDecision, ThemePosition
from src.services.sector_heat_engine import SectorHeatResult
from src.services.theme_aggregation_service import ThemeAggregateResult

logger = logging.getLogger(__name__)


class ThemePositionResolver:
    """L2 per-stock 题材地位解析器。"""

    def __init__(
        self,
        sector_results: List[SectorHeatResult],
        theme_results: List[ThemeAggregateResult],
        theme_context: Optional[Dict[str, dict]] = None,
    ) -> None:
        self._sector_map: Dict[str, SectorHeatResult] = {
            s.board_name: s for s in sector_results
        }
        self._theme_map: Dict[str, ThemeAggregateResult] = {
            t.theme_tag: t for t in theme_results
        }
        self._theme_context = theme_context or {}

    def resolve(self, stock_boards: List[str]) -> ThemeDecision:
        if not stock_boards:
            return self._non_theme_decision()

        # 选取 sector_hot_score 最高的板块作为 primary
        primary_board, primary_sector = self._pick_primary_board(stock_boards)
        if primary_sector is None:
            return self._non_theme_decision()

        # 基于盘面判定 theme_position
        position = self._position_from_sector(primary_sector)

        # 题材分数
        theme_result = self._theme_map.get(primary_board)
        theme_score = theme_result.theme_score if theme_result else primary_sector.sector_hot_score

        return ThemeDecision(
            theme_tag=primary_board,
            theme_score=theme_score,
            theme_position=position,
            leader_score=0.0,
            sector_strength=primary_sector.strength_score,
            leader_stocks=primary_sector.leader_codes,
            front_stocks=primary_sector.front_codes,
        )

    # ── 内部方法 ─────────────────────────────────────────────────────────────

    def _pick_primary_board(
        self, boards: List[str],
    ) -> tuple[str, Optional[SectorHeatResult]]:
        """选取 sector_hot_score 最高的板块。"""
        best_name = ""
        best_sector: Optional[SectorHeatResult] = None
        best_score = -1.0

        for name in boards:
            sector = self._sector_map.get(name)
            if sector and sector.sector_hot_score > best_score:
                best_score = sector.sector_hot_score
                best_name = name
                best_sector = sector

        return best_name, best_sector

    def _position_from_sector(self, sector: SectorHeatResult) -> ThemePosition:
        """theme_position 推算规则（MVP）。"""
        status = sector.sector_status
        stage = sector.sector_stage

        if status == "hot" and stage in ("ferment", "expand"):
            return ThemePosition.MAIN_THEME
        if status == "hot" and stage == "launch":
            return ThemePosition.SECONDARY_THEME
        if status == "warm":
            return ThemePosition.SECONDARY_THEME
        if status == "hot" and stage in ("climax", "fade"):
            return ThemePosition.FADING_THEME
        return ThemePosition.NON_THEME

    def _non_theme_decision(self) -> ThemeDecision:
        return ThemeDecision(
            theme_tag="",
            theme_score=0.0,
            theme_position=ThemePosition.NON_THEME,
        )
