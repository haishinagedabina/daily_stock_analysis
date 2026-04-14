from __future__ import annotations

import math
from typing import Any, Dict, List


class BoardStrengthRanker:
    """Convert per-board raw statistics into market-relative strength buckets."""

    _RANK_COMPONENT_WEIGHT = 0.35
    _ABSOLUTE_COMPONENT_WEIGHT = 0.65
    _WEIGHTS = {
        "day_return_rank_score": 0.35,
        "strong_stock_rank_score": 0.20,
        "limit_up_rank_score": 0.20,
        "breadth_rank_score": 0.15,
        "front_rank_score": 0.10,
    }

    def rank(self, raw_boards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not raw_boards:
            return []

        metrics = {
            "day_return_rank_score": self._metric_scores(
                raw_boards,
                metric_names=["avg_pct_chg", "median_pct"],
            ),
            "strong_stock_rank_score": self._metric_scores(
                raw_boards,
                metric_names=["strong_stock_ratio_5pct", "strong_stock_ratio_3pct"],
            ),
            "limit_up_rank_score": self._metric_scores(
                raw_boards,
                metric_names=["limit_up_ratio", "limit_up_count"],
            ),
            "breadth_rank_score": self._metric_scores(
                raw_boards,
                metric_names=["up_ratio", "breadth_score"],
            ),
            "front_rank_score": self._metric_scores(
                raw_boards,
                metric_names=["top3_avg", "front_concentration"],
            ),
        }

        enriched: List[Dict[str, Any]] = []
        for board in raw_boards:
            board_name = str(board["board_name"])
            board_metrics = {
                metric_name: metric_scores[board_name]
                for metric_name, metric_scores in metrics.items()
            }
            rank_component = sum(
                board_metrics[metric_name] * weight
                for metric_name, weight in self._WEIGHTS.items()
            )
            absolute_component = self._absolute_strength_score(board)
            board_strength_score = (
                rank_component * self._RANK_COMPONENT_WEIGHT
                + absolute_component * self._ABSOLUTE_COMPONENT_WEIGHT
            )
            enriched.append({
                **board,
                **board_metrics,
                "absolute_strength_score": round(absolute_component, 2),
                "board_strength_score": round(board_strength_score, 2),
            })

        enriched.sort(
            key=lambda item: (
                -float(item["board_strength_score"]),
                -float(item.get("avg_pct_chg", 0.0)),
                -float(item.get("limit_up_count", 0)),
                -float(item.get("strong_stock_ratio_5pct", 0.0)),
                str(item["board_name"]),
            )
        )

        hot_count = min(len(enriched), max(3, math.ceil(len(enriched) * 0.02),))
        hot_count = min(hot_count, 12)
        warm_count = min(max(10, math.ceil(len(enriched) * 0.08)), 40)
        warm_limit = min(len(enriched), hot_count + warm_count)

        for index, item in enumerate(enriched, start=1):
            percentile = 1.0 if len(enriched) == 1 else 1.0 - ((index - 1) / len(enriched))
            status_bucket = "cold"
            if index <= hot_count and float(item["board_strength_score"]) >= 60.0:
                status_bucket = "hot"
            elif index <= warm_limit and float(item["board_strength_score"]) >= 45.0:
                status_bucket = "warm"
            elif float(item["board_strength_score"]) >= 30.0:
                status_bucket = "neutral"

            item["board_strength_rank"] = index
            item["board_strength_percentile"] = round(percentile, 4)
            item["status_bucket"] = status_bucket

        return enriched

    def _metric_scores(
        self,
        raw_boards: List[Dict[str, Any]],
        metric_names: List[str],
    ) -> Dict[str, float]:
        ordered = sorted(
            raw_boards,
            key=lambda item: tuple(-float(item.get(metric_name, 0.0) or 0.0) for metric_name in metric_names)
            + (str(item["board_name"]),),
        )
        total = len(ordered)
        scores: Dict[str, float] = {}
        last_metric_values = None
        last_score = 100.0
        for index, item in enumerate(ordered, start=1):
            current_metric_values = tuple(float(item.get(metric_name, 0.0) or 0.0) for metric_name in metric_names)
            if current_metric_values == last_metric_values:
                score = last_score
            elif total == 1:
                score = 100.0
            else:
                score = 100.0 * (total - index) / (total - 1)
            scores[str(item["board_name"])] = round(score, 2)
            last_metric_values = current_metric_values
            last_score = score
        return scores

    def _absolute_strength_score(self, board: Dict[str, Any]) -> float:
        day_return = (
            self._normalize(float(board.get("avg_pct_chg", 0.0) or 0.0), -2.0, 7.0) * 0.7
            + self._normalize(float(board.get("median_pct", 0.0) or 0.0), -2.0, 6.0) * 0.3
        ) * 100.0
        strong_stock = (
            float(board.get("strong_stock_ratio_5pct", 0.0) or 0.0) * 0.6
            + float(board.get("strong_stock_ratio_3pct", 0.0) or 0.0) * 0.4
        ) * 100.0
        limit_up = (
            min(float(board.get("limit_up_count", 0.0) or 0.0) / 3.0, 1.0) * 0.5
            + float(board.get("limit_up_ratio", 0.0) or 0.0) * 0.5
        ) * 100.0
        breadth = (
            float(board.get("up_ratio", 0.0) or 0.0) * 0.6
            + float(board.get("breadth_score", 0.0) or 0.0) * 0.4
        ) * 100.0
        front = (
            self._normalize(float(board.get("top3_avg", 0.0) or 0.0), 0.0, 10.0) * 0.6
            + float(board.get("front_concentration", 0.0) or 0.0) * 0.4
        ) * 100.0
        return (
            day_return * self._WEIGHTS["day_return_rank_score"]
            + strong_stock * self._WEIGHTS["strong_stock_rank_score"]
            + limit_up * self._WEIGHTS["limit_up_rank_score"]
            + breadth * self._WEIGHTS["breadth_rank_score"]
            + front * self._WEIGHTS["front_rank_score"]
        )

    @staticmethod
    def _normalize(value: float, low: float, high: float) -> float:
        if high <= low:
            return 0.0
        return max(0.0, min(1.0, (value - low) / (high - low)))
