from __future__ import annotations

from typing import Any, Dict, List

from src.services.theme_normalization_service import ThemeNormalizationService


class LocalThemePipelineService:
    """Build a normalized summary for local L2 hot/warm theme results."""

    def build_summary(
        self,
        trade_date: str,
        market: str,
        decision_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        normalizer = ThemeNormalizationService()
        sector_results = list(decision_context.get("sector_heat_results", []) or [])
        selected = [
            sector
            for sector in sector_results
            if str(sector.get("sector_status") or "") in {"hot", "warm"}
        ]
        selected.sort(
            key=lambda item: float(item.get("sector_hot_score", 0.0) or 0.0),
            reverse=True,
        )

        themes: List[Dict[str, Any]] = []
        for item in selected:
            raw_name = str(item.get("canonical_theme") or item.get("board_name") or "").strip()
            if not raw_name:
                continue
            normalized = normalizer.normalize_theme(raw_theme=raw_name, keywords=[raw_name])
            normalized_name = str(normalized.get("normalized_label") or raw_name).strip()
            themes.append(
                {
                    "name": normalized_name,
                    "normalized_name": normalized_name,
                    "raw_name": raw_name,
                    "normalization_status": normalized.get("status"),
                    "normalization_confidence": float(normalized.get("match_confidence", 0.0) or 0.0),
                    "normalization_match_reasons": list(normalized.get("match_reasons", []) or []),
                    "normalization_matched_boards": list(normalized.get("matched_boards", []) or []),
                    "source_board": item.get("board_name"),
                    "heat_score": float(item.get("sector_hot_score", 0.0) or 0.0),
                    "sector_status": item.get("sector_status"),
                    "sector_stage": item.get("sector_stage"),
                    "stock_count": int(item.get("stock_count", 0) or 0),
                    "up_count": int(item.get("up_count", 0) or 0),
                    "limit_up_count": int(item.get("limit_up_count", 0) or 0),
                }
            )

        return {
            "source": "local",
            "trade_date": trade_date,
            "market": market,
            "hot_theme_count": int(decision_context.get("hot_theme_count", 0) or 0),
            "warm_theme_count": int(decision_context.get("warm_theme_count", 0) or 0),
            "selected_theme_names": list(dict.fromkeys(theme["name"] for theme in themes)),
            "themes": themes,
        }
