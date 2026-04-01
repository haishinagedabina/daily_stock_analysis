# -*- coding: utf-8 -*-
"""
L2 本地板块热度引擎 — 从 snapshot_df 聚合计算板块热度。

四维评分: breadth × strength × persistence × leadership → sector_hot_score
状态判定: hot / warm / neutral / cold
阶段判定: launch / ferment / expand / climax / fade

设计约束:
  - 从内存 snapshot_df 聚合（不从 DB 读因子），确保有完整扩展因子
  - persistence 从 DailySectorHeat 历史表读取
  - 冷启动时 persistence 维度降权
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── 可配置常量 ──────────────────────────────────────────────────────────────
MIN_SECTOR_STOCK_COUNT = 5
HOT_THRESHOLD = 70.0
WARM_THRESHOLD = 50.0
NEUTRAL_THRESHOLD = 30.0
LEADER_SCORE_THRESHOLD = 70.0
FRONT_TOP_N = 10


@dataclass
class SectorHeatResult:
    """单个板块的热度计算结果。"""
    board_name: str
    board_type: str = "concept"
    breadth_score: float = 0.0
    strength_score: float = 0.0
    persistence_score: float = 0.0
    leadership_score: float = 0.0
    sector_hot_score: float = 0.0
    sector_status: str = "neutral"
    sector_stage: str = "ferment"
    stock_count: int = 0
    up_count: int = 0
    limit_up_count: int = 0
    avg_pct_chg: float = 0.0
    leader_codes: List[str] = field(default_factory=list)
    front_codes: List[str] = field(default_factory=list)
    reason: str = ""


class SectorHeatEngine:
    """L2 本地板块热度引擎。"""

    def __init__(self, db_manager) -> None:
        self._db = db_manager

    def compute_all_sectors(
        self, snapshot_df: pd.DataFrame, trade_date: date,
    ) -> List[SectorHeatResult]:
        if snapshot_df is None or snapshot_df.empty or "code" not in snapshot_df.columns:
            return []

        boards = self._db.list_active_boards_with_member_count(
            market="cn", min_member_count=MIN_SECTOR_STOCK_COUNT,
        )
        if not boards:
            logger.warning(
                "SectorHeatEngine: 未找到满足条件的活跃板块数据（min_member_count=%d）。"
                "请确认 InstrumentBoardMembership 表已通过 backfill_instrument_boards.py "
                "或 BoardSyncScheduleService 填充。",
                MIN_SECTOR_STOCK_COUNT,
            )
            return []

        board_names = [b["board_name"] for b in boards]
        board_type_map = {b["board_name"]: b["board_type"] for b in boards}
        member_map = self._db.batch_get_board_member_codes(board_names, market="cn")

        snapshot_index = snapshot_df.set_index("code") if "code" in snapshot_df.columns else snapshot_df

        results: List[SectorHeatResult] = []
        for board_name in board_names:
            member_codes = member_map.get(board_name, [])
            if len(member_codes) < MIN_SECTOR_STOCK_COUNT:
                continue

            sector_df = snapshot_index.loc[
                snapshot_index.index.isin(member_codes)
            ].copy()
            if len(sector_df) < MIN_SECTOR_STOCK_COUNT:
                continue

            result = self._compute_single_sector(
                board_name=board_name,
                board_type=board_type_map.get(board_name, "concept"),
                sector_df=sector_df,
                trade_date=trade_date,
            )
            results.append(result)

        # 持久化
        self._persist_results(results, trade_date)

        return results

    # ── 单板块计算 ───────────────────────────────────────────────────────────

    def _compute_single_sector(
        self, board_name: str, board_type: str,
        sector_df: pd.DataFrame, trade_date: date,
    ) -> SectorHeatResult:
        pct_chg = sector_df["pct_chg"].astype(float) if "pct_chg" in sector_df.columns else pd.Series(dtype=float)
        n = len(sector_df)

        # 基础统计
        up_count = int((pct_chg > 0).sum())
        limit_up_count = int(sector_df["is_limit_up"].sum()) if "is_limit_up" in sector_df.columns else 0
        avg_pct = float(pct_chg.mean()) if len(pct_chg) > 0 else 0.0

        # 四维计算
        breadth = self._calc_breadth(sector_df, pct_chg, n)
        strength = self._calc_strength(sector_df, pct_chg, n)
        leadership, leader_codes, front_codes = self._calc_leadership(sector_df, pct_chg)
        persistence, heat_history = self._calc_persistence(board_name, trade_date)

        # 综合分数（冷启动时调整权重）
        hot_score = self._weighted_score(breadth, strength, persistence, leadership)

        # 状态和阶段
        status = self._classify_status(hot_score)
        stage = self._classify_stage(persistence, hot_score, heat_history)

        reason = (
            f"breadth={breadth:.2f} strength={strength:.2f} "
            f"persist={persistence:.2f} leader={leadership:.2f} "
            f"score={hot_score:.1f} up={up_count}/{n} limit_up={limit_up_count}"
        )

        return SectorHeatResult(
            board_name=board_name,
            board_type=board_type,
            breadth_score=breadth,
            strength_score=strength,
            persistence_score=persistence,
            leadership_score=leadership,
            sector_hot_score=hot_score,
            sector_status=status,
            sector_stage=stage,
            stock_count=n,
            up_count=up_count,
            limit_up_count=limit_up_count,
            avg_pct_chg=round(avg_pct, 2),
            leader_codes=leader_codes,
            front_codes=front_codes,
            reason=reason,
        )

    # ── 四维评分 ─────────────────────────────────────────────────────────────

    def _calc_breadth(self, df: pd.DataFrame, pct_chg: pd.Series, n: int) -> float:
        if n == 0:
            return 0.0
        up_ratio = (pct_chg > 0).sum() / n
        strong_3pct = (pct_chg > 3.0).sum() / n
        strong_5pct = (pct_chg > 5.0).sum() / n

        # MA 对齐度: close > ma20 AND close > ma60
        ma_aligned = 0.0
        if "close" in df.columns and "ma20" in df.columns and "ma60" in df.columns:
            close = df["close"].astype(float)
            ma20 = df["ma20"].astype(float)
            ma60 = df["ma60"].astype(float)
            aligned = ((close > ma20) & (close > ma60)).sum()
            ma_aligned = aligned / n

        return float(
            0.35 * up_ratio
            + 0.25 * strong_3pct
            + 0.20 * strong_5pct
            + 0.20 * ma_aligned
        )

    def _calc_strength(self, df: pd.DataFrame, pct_chg: pd.Series, n: int) -> float:
        if n == 0 or len(pct_chg) == 0:
            return 0.0

        avg_pct = float(pct_chg.mean())
        median_pct = float(pct_chg.median())
        top3_avg = float(pct_chg.nlargest(3).mean()) if n >= 3 else float(pct_chg.max())

        limit_up_count = int(df["is_limit_up"].sum()) if "is_limit_up" in df.columns else 0
        limit_score = min(limit_up_count / 3.0, 1.0)

        # 超额收益 = avg_pct - 市场平均（简化为 0）
        excess_return = avg_pct

        return float(
            0.30 * _normalize(avg_pct, -2.0, 6.0)
            + 0.20 * _normalize(median_pct, -2.0, 5.0)
            + 0.20 * _normalize(top3_avg, 0.0, 10.0)
            + 0.15 * limit_score
            + 0.15 * _normalize(excess_return, -2.0, 4.0)
        )

    def _calc_leadership(
        self, df: pd.DataFrame, pct_chg: pd.Series,
    ) -> tuple[float, List[str], List[str]]:
        leader_codes: List[str] = []
        front_codes: List[str] = []

        if "leader_score" in df.columns:
            leaders = df[df["leader_score"].astype(float) >= LEADER_SCORE_THRESHOLD]
            leader_codes = leaders.index.tolist()

        # front = 涨幅 top N
        if len(pct_chg) > 0:
            top_n = min(FRONT_TOP_N, len(pct_chg))
            front_idx = pct_chg.nlargest(top_n).index
            front_codes = [str(c) for c in front_idx if pct_chg.loc[c] > 0]

        leader_count = len(leader_codes)
        front_count = len(front_codes)

        # front spread: 前排涨幅分散度
        front_spread = 0.0
        if front_count >= 2:
            front_pcts = pct_chg.loc[[c for c in front_codes if c in pct_chg.index]]
            if len(front_pcts) >= 2:
                spread = float(front_pcts.max() - front_pcts.min())
                front_spread = _normalize(spread, 0.0, 8.0)

        score = float(
            0.35 * min(leader_count / 2.0, 1.0)
            + 0.25 * front_spread
            + 0.20 * 0.5  # leader_continuation placeholder (需要历史)
            + 0.20 * min(front_count / 5.0, 1.0)
        )
        return score, leader_codes, front_codes

    def _calc_persistence(self, board_name: str, trade_date: date) -> tuple[float, list]:
        """返回 (persistence_score, history_rows) 以避免重复查询。"""
        history = self._db.list_sector_heat_history(
            board_name=board_name,
            end_date=trade_date - timedelta(days=1),
            lookback_days=5,
        )
        history_count = len(history)

        if history_count == 0:
            return 0.0, history

        scores = [h["sector_hot_score"] for h in history]

        if history_count < 3:
            avg_hot = float(np.mean(scores))
            return float(_normalize(avg_hot, 20.0, 80.0) * 0.5), history

        if history_count < 5:
            avg_hot = float(np.mean(scores))
            return float(_normalize(avg_hot, 20.0, 80.0)), history

        hot_3d = float(np.mean(scores[-3:]))
        hot_5d = float(np.mean(scores[-5:]))
        slope = (scores[-1] - scores[0]) / max(history_count - 1, 1)

        return float(
            0.40 * _normalize(hot_3d, 20.0, 80.0)
            + 0.30 * _normalize(hot_5d, 20.0, 80.0)
            + 0.30 * _sigmoid(slope)
        ), history

    # ── 综合分数 ─────────────────────────────────────────────────────────────

    def _weighted_score(
        self, breadth: float, strength: float,
        persistence: float, leadership: float,
    ) -> float:
        # 冷启动: persistence=0 时调整权重
        if persistence < 0.01:
            return float(
                (0.35 * breadth + 0.35 * strength + 0.30 * leadership) * 100
            )
        return float(
            (0.30 * breadth + 0.30 * strength
             + 0.20 * persistence + 0.20 * leadership) * 100
        )

    # ── 状态 / 阶段分类 ─────────────────────────────────────────────────────

    def _classify_status(self, hot_score: float) -> str:
        if hot_score >= HOT_THRESHOLD:
            return "hot"
        if hot_score >= WARM_THRESHOLD:
            return "warm"
        if hot_score >= NEUTRAL_THRESHOLD:
            return "neutral"
        return "cold"

    def _classify_stage(
        self, persistence: float, hot_score: float,
        history: list,
    ) -> str:
        if persistence < 0.01:
            return "launch" if hot_score >= WARM_THRESHOLD else "ferment"

        if not history:
            return "launch"

        prev_scores = [h["sector_hot_score"] for h in history]
        prev_avg = float(np.mean(prev_scores))

        if hot_score > prev_avg * 1.1:
            return "expand"
        if hot_score >= HOT_THRESHOLD and prev_avg >= HOT_THRESHOLD:
            return "climax"
        if hot_score < prev_avg * 0.85:
            return "fade"
        return "ferment"

    # ── 持久化 ───────────────────────────────────────────────────────────────

    def _persist_results(self, results: List[SectorHeatResult], trade_date: date) -> None:
        if not results:
            return
        records = [
            {
                "trade_date": trade_date,
                "board_name": r.board_name,
                "board_type": r.board_type,
                "breadth_score": r.breadth_score,
                "strength_score": r.strength_score,
                "persistence_score": r.persistence_score,
                "leadership_score": r.leadership_score,
                "sector_hot_score": r.sector_hot_score,
                "sector_status": r.sector_status,
                "sector_stage": r.sector_stage,
                "stock_count": r.stock_count,
                "up_count": r.up_count,
                "limit_up_count": r.limit_up_count,
                "avg_pct_chg": r.avg_pct_chg,
                "leader_codes_json": json.dumps(r.leader_codes),
                "front_codes_json": json.dumps(r.front_codes),
                "reason": r.reason,
            }
            for r in results
        ]
        self._db.save_sector_heat_batch(trade_date, records)


# ── 工具函数 ─────────────────────────────────────────────────────────────────

def _normalize(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def _sigmoid(x: float, k: float = 0.1) -> float:
    """简易 sigmoid 映射到 [0, 1]。"""
    return float(1.0 / (1.0 + np.exp(-k * x)))
